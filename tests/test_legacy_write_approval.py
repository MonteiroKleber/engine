"""Tests for GAP 3: Legacy Write Approval Flow.

These tests verify that:
1. Legacy writes with approval rules return 202 PENDING_APPROVAL
2. Approval decisions (approve/reject) work correctly
3. Prod mode denies writes without approval rules
4. Dev mode allows admin role with mandate
5. approved_by is never set to requester (no self-approved)
"""

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from engine.core.approvals import (
    ApprovalsPolicy,
    set_approvals_policy,
    reset_all_approvals,
    ApprovalRule,
)
from engine.core.install_mode import InstallMode, get_install_mode, is_prod_mode, is_dev_mode
from engine.core.errors import (
    LEGACY_WRITE_PENDING_APPROVAL,
    LEGACY_WRITE_NO_APPROVAL_RULE_PROD,
    LEGACY_WRITE_NO_ADMIN_ROLE_DEV,
)
from engine.legacy_bridge.write_models import ActionStatus, LegacyWriteAction
from engine.legacy_bridge.write_registry import (
    LegacyWriteRegistry,
    WriteResult,
    LEGACY_WRITE_APPROVAL_REQUESTED,
)


@pytest.fixture
def temp_data_root(tmp_path):
    """Create a temporary data root for testing."""
    data_root = tmp_path / "var"
    data_root.mkdir()
    return data_root


@pytest.fixture
def institution_id():
    """Generate a test institution ID."""
    return str(uuid.uuid4())


@pytest.fixture
def test_registry(temp_data_root, institution_id):
    """Create a test write registry with mocked data root."""
    # Create institution directory structure
    inst_dir = temp_data_root / "institutions" / institution_id
    inst_dir.mkdir(parents=True)

    # Create ledger directory
    ledger_dir = inst_dir / "ledger"
    ledger_dir.mkdir()

    # Create outbox directory
    outbox_dir = inst_dir / "legacy_bridge" / "outbox"
    outbox_dir.mkdir(parents=True)

    with patch("engine.core.data_root.get_data_root", return_value=temp_data_root):
        with patch("engine.core.data_root.get_institution_root", return_value=inst_dir):
            with patch("engine.core.ledger.get_ledger_for_institution") as mock_ledger:
                # Mock ledger to accept appends
                mock_ledger.return_value = MagicMock()
                mock_ledger.return_value.append = MagicMock()

                registry = LegacyWriteRegistry(institution_id)
                yield registry


@pytest.fixture
def approvals_policy_with_rule():
    """Create an approvals policy with a legacy write rule."""
    policy_data = {
        "version": "1.0.0",
        "rules": [
            {
                "rule_name": "legacy.increase_limit",
                "trigger": {
                    "api": "POST /bridge/write/increase_limit"
                },
                "approver_roles": ["credit_manager"],
                "quorum": 1
            }
        ]
    }
    policy = ApprovalsPolicy(policy_data)
    return policy


@pytest.fixture(autouse=True)
def reset_approvals_after_test():
    """Reset approvals after each test."""
    yield
    reset_all_approvals()


# =============================================================================
# ENGINE_INSTALL_MODE Tests
# =============================================================================

class TestInstallMode:
    """Tests for ENGINE_INSTALL_MODE configuration."""

    def test_default_is_dev(self):
        """Default install mode should be dev."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ENGINE_INSTALL_MODE", None)
            assert get_install_mode() == InstallMode.DEV
            assert is_dev_mode() is True
            assert is_prod_mode() is False

    def test_dev_mode_explicit(self):
        """ENGINE_INSTALL_MODE=dev should set dev mode."""
        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "dev"}):
            assert get_install_mode() == InstallMode.DEV
            assert is_dev_mode() is True
            assert is_prod_mode() is False

    def test_prod_mode(self):
        """ENGINE_INSTALL_MODE=prod should set prod mode."""
        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "prod"}):
            assert get_install_mode() == InstallMode.PROD
            assert is_prod_mode() is True
            assert is_dev_mode() is False

    def test_prod_mode_case_insensitive(self):
        """ENGINE_INSTALL_MODE should be case insensitive."""
        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "PROD"}):
            assert get_install_mode() == InstallMode.PROD


# =============================================================================
# Approval Flow Tests
# =============================================================================

class TestLegacyWriteApprovalFlow:
    """Tests for legacy write approval flow."""

    def test_write_with_approval_rule_returns_pending(
        self, test_registry, approvals_policy_with_rule
    ):
        """Write with approval rule should return PENDING_APPROVAL."""
        # Set approvals policy
        set_approvals_policy(approvals_policy_with_rule)

        # Request write
        result = test_registry.request_write(
            action_type="increase_limit",
            params={"customer_id": "cust-123", "new_limit": 50000},
            actor_id="actor-requester",
            actor_roles=["operator"],
        )

        # Should return pending_approval
        assert result.pending_approval is True
        assert result.approval_id is not None
        assert result.error_code == LEGACY_WRITE_PENDING_APPROVAL
        assert result.action is not None
        assert result.action.status == ActionStatus.PENDING_APPROVAL.value
        assert result.action.approval_id == result.approval_id
        # No outbox created yet
        assert result.outbox_path is None

    def test_write_pending_action_can_be_retrieved(
        self, test_registry, approvals_policy_with_rule
    ):
        """Pending action should be retrievable by ID and approval_id."""
        set_approvals_policy(approvals_policy_with_rule)

        result = test_registry.request_write(
            action_type="increase_limit",
            params={"customer_id": "cust-123", "new_limit": 50000},
            actor_id="actor-requester",
            actor_roles=["operator"],
        )

        # Get by action_id
        action = test_registry.get_action(result.action.action_id)
        assert action is not None
        assert action.status == ActionStatus.PENDING_APPROVAL.value

        # Get by approval_id
        action_by_approval = test_registry.get_action_by_approval_id(result.approval_id)
        assert action_by_approval is not None
        assert action_by_approval.action_id == result.action.action_id

    def test_approve_action_creates_outbox(
        self, test_registry, approvals_policy_with_rule
    ):
        """Approving action should create outbox file."""
        set_approvals_policy(approvals_policy_with_rule)

        # First, create pending action
        pending_result = test_registry.request_write(
            action_type="increase_limit",
            params={"customer_id": "cust-123", "new_limit": 50000},
            actor_id="actor-requester",
            actor_roles=["operator"],
        )

        # Now complete with approval
        with patch("engine.legacy_bridge.write_registry.evaluate_mandates") as mock_mandate:
            with patch("engine.legacy_bridge.write_registry.evaluate_autonomy") as mock_autonomy:
                with patch("engine.legacy_bridge.write_registry.evaluate_policies") as mock_policy:
                    # Mock gates to allow
                    mock_mandate.return_value = MagicMock(allow=True, mandate_id="mandate-123")
                    mock_autonomy.return_value = MagicMock(decision="allow", current_level=5)
                    mock_policy.return_value = MagicMock(allow=True)

                    complete_result = test_registry.complete_approved_action(
                        action_id=pending_result.action.action_id,
                        approved_by="actor-approver",  # Different from requester!
                        approver_roles=["credit_manager"],
                    )

        assert complete_result.success is True
        assert complete_result.outbox_path is not None
        assert complete_result.action.status == ActionStatus.ENQUEUED.value
        # GAP 3: approved_by is the approver, NOT the requester
        assert complete_result.action.approved_by == "actor-approver"
        assert complete_result.action.approved_by != "actor-requester"

    def test_reject_action_marks_denied(
        self, test_registry, approvals_policy_with_rule
    ):
        """Rejecting action should mark it as denied."""
        set_approvals_policy(approvals_policy_with_rule)

        # Create pending action
        pending_result = test_registry.request_write(
            action_type="increase_limit",
            params={"customer_id": "cust-123", "new_limit": 50000},
            actor_id="actor-requester",
            actor_roles=["operator"],
        )

        # Reject
        reject_result = test_registry.reject_action(
            action_id=pending_result.action.action_id,
            rejected_by="actor-rejector",
            reason="Risk too high",
            rejector_roles=["credit_manager"],
        )

        assert reject_result.success is False  # Not successful (denied)
        assert reject_result.action.status == ActionStatus.DENIED.value
        assert reject_result.action.denied_by == "APPROVAL_REJECTED"
        assert reject_result.action.denied_reason == "Risk too high"
        # No outbox created
        assert reject_result.outbox_path is None


# =============================================================================
# Prod Mode Tests (No Self-Approved)
# =============================================================================

class TestProdModeNoSelfApproved:
    """Tests for prod mode: no self-approved behavior."""

    def test_prod_mode_no_rule_denies(self, test_registry):
        """Prod mode without approval rule should deny."""
        # No approvals policy set
        reset_all_approvals()

        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "prod"}):
            result = test_registry.request_write(
                action_type="increase_limit",
                params={"customer_id": "cust-123", "new_limit": 50000},
                actor_id="actor-requester",
                actor_roles=["operator"],
            )

            assert result.success is False
            assert result.error_code == LEGACY_WRITE_NO_APPROVAL_RULE_PROD
            assert result.action.status == ActionStatus.DENIED.value
            assert result.action.denied_by == "NO_APPROVAL_RULE"

    def test_prod_mode_no_rule_even_admin_denied(self, test_registry):
        """Prod mode without approval rule should deny even for admin."""
        reset_all_approvals()

        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "prod"}):
            result = test_registry.request_write(
                action_type="increase_limit",
                params={"customer_id": "cust-123", "new_limit": 50000},
                actor_id="actor-admin",
                actor_roles=["admin"],  # Even admin is denied
            )

            assert result.success is False
            assert result.error_code == LEGACY_WRITE_NO_APPROVAL_RULE_PROD


# =============================================================================
# Dev Mode Tests
# =============================================================================

class TestDevModeAdminBypass:
    """Tests for dev mode: admin role bypass."""

    def test_dev_mode_no_rule_no_admin_denied(self, test_registry):
        """Dev mode without approval rule and without admin role should deny."""
        reset_all_approvals()

        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "dev"}):
            result = test_registry.request_write(
                action_type="increase_limit",
                params={"customer_id": "cust-123", "new_limit": 50000},
                actor_id="actor-requester",
                actor_roles=["operator"],  # No admin role
            )

            assert result.success is False
            assert result.error_code == LEGACY_WRITE_NO_ADMIN_ROLE_DEV
            assert result.action.status == ActionStatus.DENIED.value
            assert result.action.denied_by == "NO_ADMIN_ROLE"

    def test_dev_mode_no_rule_admin_allowed(self, test_registry):
        """Dev mode without approval rule but with admin role should allow."""
        reset_all_approvals()

        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "dev"}):
            with patch("engine.legacy_bridge.write_registry.evaluate_mandates") as mock_mandate:
                with patch("engine.legacy_bridge.write_registry.evaluate_autonomy") as mock_autonomy:
                    with patch("engine.legacy_bridge.write_registry.evaluate_policies") as mock_policy:
                        # Mock gates to allow
                        mock_mandate.return_value = MagicMock(allow=True, mandate_id="mandate-123")
                        mock_autonomy.return_value = MagicMock(decision="allow", current_level=5)
                        mock_policy.return_value = MagicMock(allow=True)

                        result = test_registry.request_write(
                            action_type="increase_limit",
                            params={"customer_id": "cust-123", "new_limit": 50000},
                            actor_id="actor-admin",
                            actor_roles=["admin"],  # Admin role present
                        )

        assert result.success is True
        assert result.outbox_path is not None
        assert result.action.status == ActionStatus.ENQUEUED.value

    def test_dev_mode_admin_bypass_records_mode(self, test_registry):
        """Dev mode admin bypass should record approval_mode in ledger."""
        reset_all_approvals()

        ledger_events = []

        def capture_ledger_event(**kwargs):
            ledger_events.append(kwargs)

        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "dev"}):
            with patch("engine.legacy_bridge.write_registry.get_ledger_for_institution") as mock_ledger:
                mock_ledger.return_value = MagicMock()
                mock_ledger.return_value.append = capture_ledger_event

                with patch("engine.legacy_bridge.write_registry.evaluate_mandates") as mock_mandate:
                    with patch("engine.legacy_bridge.write_registry.evaluate_autonomy") as mock_autonomy:
                        with patch("engine.legacy_bridge.write_registry.evaluate_policies") as mock_policy:
                            mock_mandate.return_value = MagicMock(allow=True, mandate_id="mandate-123")
                            mock_autonomy.return_value = MagicMock(decision="allow", current_level=5)
                            mock_policy.return_value = MagicMock(allow=True)

                            result = test_registry.request_write(
                                action_type="increase_limit",
                                params={"customer_id": "cust-123", "new_limit": 50000},
                                actor_id="actor-admin",
                                actor_roles=["admin"],
                            )

        # Find LEGACY_WRITE_ALLOWED event
        allowed_event = None
        for event in ledger_events:
            if event.get("event_type") == "LEGACY_WRITE_ALLOWED":
                allowed_event = event
                break

        assert allowed_event is not None
        assert allowed_event["payload"]["approval_mode"] == "dev_admin_bypass"
        assert allowed_event["payload"]["admin_actor_id"] == "actor-admin"


# =============================================================================
# No Self-Approved Verification
# =============================================================================

class TestNoSelfApproved:
    """Tests verifying approved_by is never the requester."""

    def test_approval_flow_approved_by_is_different(
        self, test_registry, approvals_policy_with_rule
    ):
        """In approval flow, approved_by must be different from requested_by."""
        set_approvals_policy(approvals_policy_with_rule)

        # Request as requester
        pending_result = test_registry.request_write(
            action_type="increase_limit",
            params={"customer_id": "cust-123", "new_limit": 50000},
            actor_id="actor-requester",
            actor_roles=["operator"],
        )

        # Approve as different actor
        with patch("engine.legacy_bridge.write_registry.evaluate_mandates") as mock_mandate:
            with patch("engine.legacy_bridge.write_registry.evaluate_autonomy") as mock_autonomy:
                with patch("engine.legacy_bridge.write_registry.evaluate_policies") as mock_policy:
                    mock_mandate.return_value = MagicMock(allow=True, mandate_id="mandate-123")
                    mock_autonomy.return_value = MagicMock(decision="allow", current_level=5)
                    mock_policy.return_value = MagicMock(allow=True)

                    complete_result = test_registry.complete_approved_action(
                        action_id=pending_result.action.action_id,
                        approved_by="actor-approver",  # DIFFERENT from requester
                        approver_roles=["credit_manager"],
                    )

        # Verify approved_by != requested_by
        assert complete_result.action.requested_by == "actor-requester"
        assert complete_result.action.approved_by == "actor-approver"
        assert complete_result.action.approved_by != complete_result.action.requested_by

    def test_dev_admin_bypass_does_not_set_approved_by_as_requester(
        self, test_registry
    ):
        """Dev admin bypass should NOT set approved_by to requester."""
        reset_all_approvals()

        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "dev"}):
            with patch("engine.legacy_bridge.write_registry.evaluate_mandates") as mock_mandate:
                with patch("engine.legacy_bridge.write_registry.evaluate_autonomy") as mock_autonomy:
                    with patch("engine.legacy_bridge.write_registry.evaluate_policies") as mock_policy:
                        mock_mandate.return_value = MagicMock(allow=True, mandate_id="mandate-123")
                        mock_autonomy.return_value = MagicMock(decision="allow", current_level=5)
                        mock_policy.return_value = MagicMock(allow=True)

                        result = test_registry.request_write(
                            action_type="increase_limit",
                            params={"customer_id": "cust-123", "new_limit": 50000},
                            actor_id="actor-admin",
                            actor_roles=["admin"],
                        )

        # In dev admin bypass, approved_by should be None (not set to requester)
        # The ledger event records "dev_admin_bypass" as the approval_mode instead
        assert result.action.approved_by is None


# =============================================================================
# Ledger Event Tests
# =============================================================================

class TestLedgerEvents:
    """Tests for ledger events in approval flow."""

    def test_approval_requested_emits_events(
        self, test_registry, approvals_policy_with_rule
    ):
        """Creating approval request should emit ledger events."""
        set_approvals_policy(approvals_policy_with_rule)

        ledger_events = []

        def capture_event(**kwargs):
            ledger_events.append(kwargs)

        with patch("engine.legacy_bridge.write_registry.get_ledger_for_institution") as mock_ledger:
            with patch("engine.core.approvals.get_ledger") as mock_core_ledger:
                mock_ledger.return_value = MagicMock()
                mock_ledger.return_value.append = capture_event
                mock_core_ledger.return_value = MagicMock()
                mock_core_ledger.return_value.append = capture_event

                result = test_registry.request_write(
                    action_type="increase_limit",
                    params={"customer_id": "cust-123", "new_limit": 50000},
                    actor_id="actor-requester",
                    actor_roles=["operator"],
                )

        # Should have LEGACY_WRITE_INTENT_CREATED
        intent_events = [e for e in ledger_events if e.get("event_type") == "LEGACY_WRITE_INTENT_CREATED"]
        assert len(intent_events) == 1

        # Should have LEGACY_WRITE_APPROVAL_REQUESTED
        approval_req_events = [e for e in ledger_events if e.get("event_type") == LEGACY_WRITE_APPROVAL_REQUESTED]
        assert len(approval_req_events) == 1
        assert approval_req_events[0]["payload"]["approval_id"] == result.approval_id
        assert approval_req_events[0]["payload"]["action_id"] == result.action.action_id
