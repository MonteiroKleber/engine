"""Tests for Legacy Bridge Write-Mode (Etapa 4.3).

These tests verify:
1. Write actions with governance gates (mandate/autonomy/policy)
2. Outbox file creation with correct format
3. Ledger events for write flow
4. Isolation by institution/dept
5. Deny paths when gates fail
"""

import json
import os
import pytest
from pathlib import Path

from engine.core.data_root import get_institution_root
from engine.core.ledger import reset_institution_ledgers, get_ledger_for_institution
from engine.core.mandates import (
    set_mandates,
    clear_all_mandates,
    MandateDef,
    Mandate,
    ALLOWED_ENDPOINT_SIGS as MANDATE_ALLOWED_SIGS,
)
from engine.core.autonomy import (
    set_autonomy_for_dept,
    reset_all_autonomy,
    AutonomyDef,
    AutonomyRule,
    ALLOWED_ENDPOINT_SIGS as AUTONOMY_ALLOWED_SIGS,
)
from engine.core.policy import (
    set_policies,
    clear_all_policies,
    PolicyDef,
    PolicyRule,
    ALLOWED_ENDPOINT_SIGS as POLICY_ALLOWED_SIGS,
)
from engine.legacy_bridge.write_models import (
    LegacyWriteAction,
    ActionStatus,
    ACTION_SCHEMAS,
    validate_action_params,
    compute_intent_sha256,
)
from engine.legacy_bridge.connectors.outbox_connector import OutboxConnector
from engine.legacy_bridge.write_registry import (
    LegacyWriteRegistry,
    LEGACY_WRITE_INTENT_CREATED,
    LEGACY_WRITE_ALLOWED,
    LEGACY_WRITE_DENIED,
    LEGACY_WRITE_ENQUEUED,
)


# Add bridge write endpoints to allowed sigs for tests
BRIDGE_ENDPOINT = "POST /bridge/write/increase_limit"


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    reset_institution_ledgers()
    clear_all_mandates()
    reset_all_autonomy()
    clear_all_policies()

    # Patch allowed endpoint sigs to include our test endpoint
    monkeypatch.setattr(
        "engine.core.mandates.ALLOWED_ENDPOINT_SIGS",
        frozenset(MANDATE_ALLOWED_SIGS | {BRIDGE_ENDPOINT}),
    )
    monkeypatch.setattr(
        "engine.core.autonomy.ALLOWED_ENDPOINT_SIGS",
        frozenset(AUTONOMY_ALLOWED_SIGS | {BRIDGE_ENDPOINT}),
    )
    monkeypatch.setattr(
        "engine.core.policy.ALLOWED_ENDPOINT_SIGS",
        frozenset(POLICY_ALLOWED_SIGS | {BRIDGE_ENDPOINT}),
    )

    yield

    reset_institution_ledgers()
    clear_all_mandates()
    reset_all_autonomy()
    clear_all_policies()


@pytest.fixture
def institution_id() -> str:
    """Test institution ID."""
    return "test-inst-write-001"


@pytest.fixture
def dept_id() -> str:
    """Test department ID."""
    return "finance"


@pytest.fixture
def valid_params() -> dict:
    """Valid params for increase_limit action."""
    return {
        "customer_id": "CUST-123",
        "new_limit": 50000,
        "reason": "Credit review approved",
    }


class TestLegacyWriteActionModel:
    """Test LegacyWriteAction model."""

    def test_create_action_computes_intent_hash(self, valid_params):
        """Creating action computes intent_sha256."""
        action = LegacyWriteAction(
            action_id="test-action-001",
            action_type="increase_limit",
            params=valid_params,
            requested_by="user-123",
            institution_id="inst-001",
        )

        assert action.intent_sha256 != ""
        assert len(action.intent_sha256) == 64  # SHA256 hex
        assert action.status == ActionStatus.PENDING.value
        assert action.created_at != ""
        assert action.case_id == action.action_id

    def test_intent_hash_is_deterministic(self, valid_params):
        """Same params produce same hash."""
        hash1 = compute_intent_sha256(valid_params)
        hash2 = compute_intent_sha256(valid_params)
        assert hash1 == hash2

    def test_intent_hash_differs_for_different_params(self, valid_params):
        """Different params produce different hash."""
        hash1 = compute_intent_sha256(valid_params)
        modified_params = {**valid_params, "new_limit": 60000}
        hash2 = compute_intent_sha256(modified_params)
        assert hash1 != hash2

    def test_to_dict_and_from_dict_roundtrip(self, valid_params):
        """Action serializes and deserializes correctly."""
        action = LegacyWriteAction(
            action_id="test-action-001",
            action_type="increase_limit",
            params=valid_params,
            requested_by="user-123",
            institution_id="inst-001",
            dept_id="finance",
        )

        data = action.to_dict()
        restored = LegacyWriteAction.from_dict(data)

        assert restored.action_id == action.action_id
        assert restored.action_type == action.action_type
        assert restored.params == action.params
        assert restored.intent_sha256 == action.intent_sha256
        assert restored.dept_id == action.dept_id


class TestValidateActionParams:
    """Test action param validation."""

    def test_valid_increase_limit_params(self, valid_params):
        """Valid params pass validation."""
        errors = validate_action_params("increase_limit", valid_params)
        assert errors == []

    def test_missing_required_field(self):
        """Missing required field fails."""
        params = {"customer_id": "CUST-123"}  # missing new_limit
        errors = validate_action_params("increase_limit", params)
        assert any("new_limit" in e for e in errors)

    def test_invalid_type_for_number(self):
        """Wrong type for number field fails."""
        params = {
            "customer_id": "CUST-123",
            "new_limit": "fifty thousand",  # should be number
        }
        errors = validate_action_params("increase_limit", params)
        assert any("number" in e for e in errors)

    def test_negative_limit_fails_minimum(self):
        """Negative number fails minimum constraint."""
        params = {
            "customer_id": "CUST-123",
            "new_limit": -100,
        }
        errors = validate_action_params("increase_limit", params)
        assert any(">=" in e for e in errors)

    def test_unknown_action_type(self):
        """Unknown action type returns error."""
        errors = validate_action_params("unknown_action", {})
        assert any("Unknown action type" in e for e in errors)


class TestOutboxConnector:
    """Test OutboxConnector."""

    def test_write_action_creates_file(self, institution_id, valid_params):
        """Writing action creates outbox file."""
        action = LegacyWriteAction(
            action_id="test-action-001",
            action_type="increase_limit",
            params=valid_params,
            requested_by="user-123",
            institution_id=institution_id,
        )

        connector = OutboxConnector(institution_id)
        result = connector.write_action(action)

        assert result.success
        assert result.outbox_path is not None
        assert result.outbox_sha256 is not None
        assert len(result.outbox_sha256) == 64

        # Verify file exists
        inst_root = get_institution_root(institution_id)
        file_path = inst_root / result.outbox_path
        assert file_path.exists()

    def test_outbox_file_format_is_deterministic(self, institution_id, valid_params):
        """Outbox file is in deterministic JSON format."""
        action = LegacyWriteAction(
            action_id="test-action-001",
            action_type="increase_limit",
            params=valid_params,
            requested_by="user-123",
            institution_id=institution_id,
        )

        connector = OutboxConnector(institution_id)
        result = connector.write_action(action)

        inst_root = get_institution_root(institution_id)
        file_path = inst_root / result.outbox_path
        content = file_path.read_text()

        # Should be valid JSON
        data = json.loads(content)
        assert data["schema_version"] == "1.0"
        assert data["action_id"] == "test-action-001"
        assert data["action_type"] == "increase_limit"

        # Should be compact (no extra whitespace)
        assert "  " not in content  # no indentation
        assert ": " not in content  # no space after colon

    def test_dept_isolation_creates_separate_outbox(self, institution_id, dept_id, valid_params):
        """Department isolation creates separate outbox directory."""
        action = LegacyWriteAction(
            action_id="test-action-001",
            action_type="increase_limit",
            params=valid_params,
            requested_by="user-123",
            institution_id=institution_id,
            dept_id=dept_id,
        )

        connector = OutboxConnector(institution_id, dept_id)
        result = connector.write_action(action)

        assert result.success
        assert f"depts/{dept_id}" in result.outbox_path

    def test_list_actions_returns_action_ids(self, institution_id, valid_params):
        """List actions returns created action IDs."""
        connector = OutboxConnector(institution_id)

        # Create multiple actions
        for i in range(3):
            action = LegacyWriteAction(
                action_id=f"test-action-{i:03d}",
                action_type="increase_limit",
                params=valid_params,
                requested_by="user-123",
                institution_id=institution_id,
            )
            connector.write_action(action)

        action_ids = connector.list_actions()
        assert len(action_ids) == 3
        assert "test-action-000" in action_ids
        assert "test-action-001" in action_ids
        assert "test-action-002" in action_ids


class TestLegacyWriteRegistryAllowed:
    """Test write registry when governance gates allow."""

    def test_write_allowed_without_contracts(self, institution_id, valid_params):
        """Write is allowed when no governance contracts exist (no contract = allow)."""
        registry = LegacyWriteRegistry(institution_id)

        result = registry.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
            actor_roles=["admin"],
        )

        assert result.success
        assert result.action is not None
        assert result.action.status == ActionStatus.ENQUEUED.value
        assert result.outbox_path is not None
        assert result.outbox_sha256 is not None

    def test_write_allowed_creates_ledger_events(self, institution_id, valid_params):
        """Allowed write creates correct ledger events."""
        registry = LegacyWriteRegistry(institution_id)

        result = registry.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
            actor_roles=["admin"],
        )

        assert result.success

        # Check ledger events
        ledger = get_ledger_for_institution(institution_id)
        events = ledger.get_all_events()

        event_types = [e.event_type for e in events]
        assert LEGACY_WRITE_INTENT_CREATED in event_types
        assert LEGACY_WRITE_ALLOWED in event_types
        assert LEGACY_WRITE_ENQUEUED in event_types

    def test_write_allowed_with_mandate(self, institution_id, valid_params):
        """Write is allowed when mandate matches."""
        # Set up mandate that allows the action
        mandate_def = MandateDef(mandates=[
            Mandate(
                mandate_id="test-mandate-001",
                endpoint_sig=BRIDGE_ENDPOINT,
                phase="pre",
                allowed_roles=["admin"],
            ),
        ])
        set_mandates(None, mandate_def)

        registry = LegacyWriteRegistry(institution_id)
        result = registry.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
            actor_roles=["admin"],
        )

        assert result.success
        assert result.action.mandate_id == "test-mandate-001"


class TestLegacyWriteRegistryDenied:
    """Test write registry when governance gates deny."""

    def test_write_denied_by_autonomy_creates_deny_event(self, institution_id, valid_params):
        """Denied write by autonomy creates LEGACY_WRITE_DENIED event."""
        # Set up autonomy with low current level
        autonomy_def = AutonomyDef(
            current_level=1,  # Low level
            rules=[
                AutonomyRule(
                    rule_id="test-rule-001",
                    endpoint_sig=BRIDGE_ENDPOINT,
                    phase="pre",
                    required_level=3,  # Requires higher level
                ),
            ],
        )
        set_autonomy_for_dept(None, autonomy_def)

        registry = LegacyWriteRegistry(institution_id)
        result = registry.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
            actor_roles=["admin"],
        )

        assert not result.success
        assert result.denied_by == "AUTONOMY"

        # Check ledger has DENIED event
        ledger = get_ledger_for_institution(institution_id)
        events = ledger.get_all_events()

        event_types = [e.event_type for e in events]
        assert LEGACY_WRITE_INTENT_CREATED in event_types
        assert LEGACY_WRITE_DENIED in event_types
        assert LEGACY_WRITE_ALLOWED not in event_types
        assert LEGACY_WRITE_ENQUEUED not in event_types

    def test_write_denied_by_autonomy_insufficient_level(self, institution_id, valid_params):
        """Write is denied when autonomy level is insufficient."""
        # Set up autonomy with low current level
        autonomy_def = AutonomyDef(
            current_level=1,  # Low level
            rules=[
                AutonomyRule(
                    rule_id="test-rule-001",
                    endpoint_sig=BRIDGE_ENDPOINT,
                    phase="pre",
                    required_level=3,  # Requires higher level
                ),
            ],
        )
        set_autonomy_for_dept(None, autonomy_def)

        registry = LegacyWriteRegistry(institution_id)
        result = registry.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
            actor_roles=["admin"],
        )

        assert not result.success
        assert result.denied_by == "AUTONOMY"
        assert result.error_code == "LEGACY_WRITE_DENIED_AUTONOMY"

    def test_write_denied_by_policy_violation(self, institution_id):
        """Write is denied when policy is violated."""
        # Set up policy with numeric_max rule
        from engine.core.policy import validate_field_path
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="test-policy-001",
                rule_type="numeric_max",
                field_path="new_limit",
                field_path_tokens=validate_field_path("new_limit"),
                phase="pre",
                endpoint_sig=BRIDGE_ENDPOINT,
                value=10000,  # Max limit is 10000
                message="Limit cannot exceed 10000",
            ),
        ])
        set_policies(None, policy_def)

        registry = LegacyWriteRegistry(institution_id)
        result = registry.request_write(
            action_type="increase_limit",
            params={
                "customer_id": "CUST-123",
                "new_limit": 50000,  # Exceeds max
            },
            actor_id="user-123",
            actor_roles=["admin"],
        )

        assert not result.success
        assert result.denied_by == "POLICY"
        assert result.error_code == "LEGACY_WRITE_DENIED_POLICY"


class TestLegacyWriteRegistryValidation:
    """Test write registry input validation."""

    def test_unknown_action_type_rejected(self, institution_id):
        """Unknown action type is rejected."""
        registry = LegacyWriteRegistry(institution_id)
        result = registry.request_write(
            action_type="unknown_action",
            params={},
            actor_id="user-123",
        )

        assert not result.success
        assert result.error_code == "LEGACY_WRITE_ACTION_TYPE_UNKNOWN"

    def test_invalid_params_rejected(self, institution_id):
        """Invalid params are rejected."""
        registry = LegacyWriteRegistry(institution_id)
        result = registry.request_write(
            action_type="increase_limit",
            params={"customer_id": "CUST-123"},  # Missing new_limit
            actor_id="user-123",
        )

        assert not result.success
        assert result.error_code == "LEGACY_WRITE_PARAMS_INVALID"


class TestLegacyWriteRegistryIsolation:
    """Test institution/dept isolation."""

    def test_different_institutions_have_separate_outboxes(self, valid_params):
        """Different institutions have isolated outboxes."""
        inst1 = "test-inst-001"
        inst2 = "test-inst-002"

        registry1 = LegacyWriteRegistry(inst1)
        registry2 = LegacyWriteRegistry(inst2)

        # GAP 3: requires admin role in dev mode without approval rule
        result1 = registry1.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
            actor_roles=["admin"],
        )
        result2 = registry2.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-456",
            actor_roles=["admin"],
        )

        assert result1.success
        assert result2.success

        # Verify files are in different locations
        inst1_root = get_institution_root(inst1)
        inst2_root = get_institution_root(inst2)

        file1 = inst1_root / result1.outbox_path
        file2 = inst2_root / result2.outbox_path

        assert file1.exists()
        assert file2.exists()
        assert str(inst1_root) in str(file1)
        assert str(inst2_root) in str(file2)

    def test_different_depts_have_separate_outboxes(self, institution_id, valid_params):
        """Different departments have isolated outboxes."""
        registry_finance = LegacyWriteRegistry(institution_id, "finance")
        registry_support = LegacyWriteRegistry(institution_id, "support")

        # GAP 3: requires admin role in dev mode without approval rule
        result1 = registry_finance.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
            actor_roles=["admin"],
        )
        result2 = registry_support.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-456",
            actor_roles=["admin"],
        )

        assert result1.success
        assert result2.success

        # Verify files are in different dept directories
        assert "depts/finance" in result1.outbox_path
        assert "depts/support" in result2.outbox_path

    def test_action_not_visible_across_institutions(self, valid_params):
        """Actions from one institution are not visible in another."""
        inst1 = "test-inst-001"
        inst2 = "test-inst-002"

        registry1 = LegacyWriteRegistry(inst1)
        # GAP 3: requires admin role in dev mode without approval rule
        result = registry1.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
            actor_roles=["admin"],
        )

        assert result.success
        action_id = result.action.action_id

        # Should be visible in inst1
        assert registry1.get_action(action_id) is not None

        # Should NOT be visible in inst2
        registry2 = LegacyWriteRegistry(inst2)
        assert registry2.get_action(action_id) is None


class TestLegacyWriteRegistryListAndGet:
    """Test action listing and retrieval."""

    def test_list_actions_returns_all(self, institution_id, valid_params):
        """List actions returns all created actions."""
        registry = LegacyWriteRegistry(institution_id)

        # Create multiple actions
        for _ in range(3):
            registry.request_write(
                action_type="increase_limit",
                params=valid_params,
                actor_id="user-123",
            )

        actions = registry.list_actions()
        assert len(actions) == 3

    def test_list_actions_filter_by_status(self, institution_id, valid_params):
        """List actions can filter by status."""
        # Set up mandate to cause denial for some actions
        mandate_def = MandateDef(mandates=[
            Mandate(
                mandate_id="test-mandate-001",
                endpoint_sig=BRIDGE_ENDPOINT,
                phase="pre",
                allowed_roles=["admin"],
            ),
        ])
        set_mandates(None, mandate_def)

        registry = LegacyWriteRegistry(institution_id)

        # Create allowed action
        registry.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
            actor_roles=["admin"],
        )

        # Create denied action
        registry.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-456",
            actor_roles=["user"],  # Wrong role
        )

        enqueued = registry.list_actions(status=ActionStatus.ENQUEUED.value)
        denied = registry.list_actions(status=ActionStatus.DENIED.value)

        assert len(enqueued) == 1
        assert len(denied) == 1

    def test_get_action_by_id(self, institution_id, valid_params):
        """Get action by ID returns correct action."""
        registry = LegacyWriteRegistry(institution_id)
        result = registry.request_write(
            action_type="increase_limit",
            params=valid_params,
            actor_id="user-123",
        )

        action = registry.get_action(result.action.action_id)
        assert action is not None
        assert action.action_type == "increase_limit"
        assert action.params == valid_params

    def test_get_nonexistent_action_returns_none(self, institution_id):
        """Get nonexistent action returns None."""
        registry = LegacyWriteRegistry(institution_id)
        action = registry.get_action("nonexistent-action-id")
        assert action is None
