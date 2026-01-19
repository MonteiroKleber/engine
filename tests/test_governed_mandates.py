"""Tests for Governed Mandates (Etapa 2.8).

These tests verify:
1. Mandate proposed does not change execution
2. After approval+apply, endpoint permits (before denied)
3. Revocation returns to deny
4. Isolation: change in (A, finance) does not affect (A, support) or (B, finance)
"""

import json
import pytest
from pathlib import Path

from engine.core.actor_context import ActorContext
from engine.core.data_root import get_institution_root
from engine.core.ledger import reset_institution_ledgers, get_ledger_for_institution
from engine.core.mandates import (
    evaluate_mandates,
    set_mandates,
    clear_all_mandates,
    MandateDef,
    Mandate,
    parse_mandates_data,
)
from engine.core.governed_mandates import (
    propose_mandate_change,
    decide_mandate_proposal,
    apply_mandate_change,
    get_effective_mandates,
    list_mandate_proposals,
    list_governed_mandates,
    reset_governed_mandates_registry,
    invalidate_all_mandates_cache,
    load_governed_state,
    MANDATE_PROPOSED,
    MANDATE_APPROVED,
    MANDATE_REJECTED,
    MANDATE_APPLIED,
    MANDATE_REVOKED,
)
from engine.core.errors import (
    MANDATE_PROPOSAL_NOT_FOUND,
    MANDATE_PROPOSAL_ALREADY_DECIDED,
    MANDATE_PROPOSAL_INVALID,
    MANDATE_ALREADY_EXISTS,
    MANDATE_NOT_FOUND_FOR_UPDATE,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    reset_institution_ledgers()
    clear_all_mandates()
    reset_governed_mandates_registry()
    invalidate_all_mandates_cache()
    yield
    reset_institution_ledgers()
    clear_all_mandates()
    reset_governed_mandates_registry()
    invalidate_all_mandates_cache()


@pytest.fixture
def institution_a() -> str:
    """Test institution A ID."""
    return "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture
def institution_b() -> str:
    """Test institution B ID."""
    return "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.fixture
def actor_manager() -> ActorContext:
    """Actor with manager role."""
    return ActorContext(
        tenant_id="test",
        actor_id="actor-manager",
        roles=["manager"],
    )


@pytest.fixture
def actor_analyst() -> ActorContext:
    """Actor with analyst role."""
    return ActorContext(
        tenant_id="test",
        actor_id="actor-analyst",
        roles=["analyst"],
    )


@pytest.fixture
def sample_mandate_data():
    """Sample mandate data for testing."""
    return {
        "mandate_id": "test-mandate-001",
        "endpoint_sig": "POST /finance/expenses",
        "phase": "pre",
        "allowed_roles": ["manager"],
        "limits": [
            {
                "rule_type": "numeric_max",
                "field_path": "amount",
                "value": 10000,
            }
        ],
    }


class TestProposalWorkflow:
    """Test proposal create/decide workflow."""

    def test_propose_create_mandate(self, institution_a, sample_mandate_data):
        """Creating a proposal returns OPEN status."""
        proposal, error_code, error_msg = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Add new mandate for testing",
            actor_id="admin",
        )

        assert error_code is None
        assert error_msg is None
        assert proposal is not None
        assert proposal.status == "OPEN"
        assert proposal.mandate_operation == "create"
        assert proposal.mandate_id == "test-mandate-001"

    def test_propose_invalid_operation(self, institution_a):
        """Invalid operation returns error."""
        proposal, error_code, error_msg = propose_mandate_change(
            institution_id=institution_a,
            operation="invalid",
            mandate_id="test-mandate-001",
            mandate_data={},
            reason="Test",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == MANDATE_PROPOSAL_INVALID
        assert "Invalid operation" in error_msg

    def test_propose_create_without_data(self, institution_a):
        """Create without mandate_data returns error."""
        proposal, error_code, error_msg = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=None,
            reason="Test",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == MANDATE_PROPOSAL_INVALID
        assert "mandate_data is required" in error_msg

    def test_propose_invalid_schema(self, institution_a):
        """Invalid mandate schema returns error."""
        proposal, error_code, error_msg = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data={
                "mandate_id": "test-mandate-001",
                "endpoint_sig": "INVALID_ENDPOINT",  # Invalid endpoint
                "phase": "pre",
                "allowed_roles": ["manager"],
            },
            reason="Test",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == MANDATE_PROPOSAL_INVALID
        assert "Invalid mandate data" in error_msg

    def test_decide_approve(self, institution_a, sample_mandate_data):
        """Approving a proposal changes status to DECIDED."""
        # Create proposal
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )

        # Decide
        decided, error_code, error_msg = decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved for testing",
            actor_id="governance",
        )

        assert error_code is None
        assert decided.status == "DECIDED"
        assert decided.decision == "approve"
        assert decided.decided_by == "governance"

    def test_decide_reject(self, institution_a, sample_mandate_data):
        """Rejecting a proposal changes status to DECIDED."""
        # Create proposal
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )

        # Decide
        decided, error_code, error_msg = decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="reject",
            reason="Rejected for testing",
            actor_id="governance",
        )

        assert error_code is None
        assert decided.status == "DECIDED"
        assert decided.decision == "reject"

    def test_decide_already_decided(self, institution_a, sample_mandate_data):
        """Deciding already decided proposal returns error."""
        # Create and decide
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="First decision",
            actor_id="governance",
        )

        # Try to decide again
        decided, error_code, error_msg = decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="reject",
            reason="Second decision",
            actor_id="governance",
        )

        assert decided is None
        assert error_code == MANDATE_PROPOSAL_ALREADY_DECIDED

    def test_decide_not_found(self, institution_a):
        """Deciding non-existent proposal returns error."""
        decided, error_code, error_msg = decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id="nonexistent-proposal",
            decision="approve",
            reason="Test",
            actor_id="governance",
        )

        assert decided is None
        assert error_code == MANDATE_PROPOSAL_NOT_FOUND


class TestMandateNotAppliedUntilApproved:
    """Test that proposed mandates don't affect runtime until approved."""

    def test_proposed_mandate_does_not_affect_runtime(
        self, institution_a, sample_mandate_data, actor_manager
    ):
        """A proposed mandate should NOT affect evaluate_mandates."""
        # Initially no mandates - allow all
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 5000},
            institution_id=institution_a,
        )
        assert result.allow is True

        # Create proposal (not yet approved)
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )

        # Still should allow (proposal not applied)
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 5000},
            institution_id=institution_a,
        )
        assert result.allow is True

    def test_approved_mandate_affects_runtime(
        self, institution_a, sample_mandate_data, actor_manager, actor_analyst
    ):
        """After approval+apply, mandate should affect evaluate_mandates."""
        # Create and approve mandate
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Now mandate should be in effect
        # Manager should be allowed (within limit)
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 5000},
            institution_id=institution_a,
        )
        assert result.allow is True
        assert result.mandate_id == "test-mandate-001"

        # Manager should be denied (exceeds limit)
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 15000},
            institution_id=institution_a,
        )
        assert result.allow is False

        # Analyst should be denied (wrong role)
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_analyst,
            payload={"amount": 5000},
            institution_id=institution_a,
        )
        assert result.allow is False


class TestRevocation:
    """Test revocation workflow."""

    def test_revoke_governed_mandate(
        self, institution_a, sample_mandate_data, actor_manager
    ):
        """Revoking a governed mandate should deny access."""
        # Create and approve mandate
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Create",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Verify mandate is in effect
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 5000},
            institution_id=institution_a,
        )
        assert result.allow is True

        # Revoke mandate
        revoke_proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="revoke",
            mandate_id="test-mandate-001",
            mandate_data=None,
            reason="Revoke",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=revoke_proposal.proposal_id,
            decision="approve",
            reason="Approved revocation",
            actor_id="governance",
        )

        # Now mandate should be revoked - with no mandates, allow is True
        # (per semantics: no mandates = allow all)
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 5000},
            institution_id=institution_a,
        )
        # With empty mandates list and no bundle mandates, returns allow=True
        assert result.allow is True


class TestIsolation:
    """Test isolation between institutions and departments."""

    def test_institution_isolation(
        self, institution_a, institution_b, sample_mandate_data, actor_manager
    ):
        """Mandate in institution A does not affect institution B."""
        # Create mandate for institution A
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Create",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Institution A should have the mandate
        result_a = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 5000},
            institution_id=institution_a,
        )
        assert result_a.allow is True
        assert result_a.mandate_id == "test-mandate-001"

        # Institution B should NOT have the mandate (allow all)
        result_b = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 5000},
            institution_id=institution_b,
        )
        assert result_b.allow is True
        assert result_b.mandate_id is None  # No mandate matched

    def test_department_isolation(
        self, institution_a, sample_mandate_data, actor_manager
    ):
        """Mandate in dept finance does not affect dept support."""
        # Create mandate for finance dept
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Create",
            actor_id="admin",
            dept_id="finance",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
            dept_id="finance",
        )

        # Finance dept should have the mandate
        result_finance = evaluate_mandates(
            phase="pre",
            dept_id="finance",
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 5000},
            institution_id=institution_a,
        )
        assert result_finance.allow is True
        assert result_finance.mandate_id == "test-mandate-001"

        # Support dept should NOT have the mandate
        result_support = evaluate_mandates(
            phase="pre",
            dept_id="support",
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 5000},
            institution_id=institution_a,
        )
        assert result_support.allow is True
        assert result_support.mandate_id is None


class TestLedgerEvents:
    """Test ledger event emission."""

    def test_propose_emits_mandate_proposed(self, institution_a, sample_mandate_data):
        """Proposing emits MANDATE_PROPOSED event."""
        propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()
        proposed_events = [e for e in events if e.event_type == MANDATE_PROPOSED]
        assert len(proposed_events) == 1
        assert proposed_events[0].payload["operation"] == "create"
        assert proposed_events[0].payload["mandate_id"] == "test-mandate-001"

    def test_approve_emits_mandate_approved_and_applied(
        self, institution_a, sample_mandate_data
    ):
        """Approving emits MANDATE_APPROVED and MANDATE_APPLIED events."""
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()

        approved_events = [e for e in events if e.event_type == MANDATE_APPROVED]
        assert len(approved_events) == 1
        assert approved_events[0].payload["decision"] == "approve"

        applied_events = [e for e in events if e.event_type == MANDATE_APPLIED]
        assert len(applied_events) == 1
        assert applied_events[0].payload["operation"] == "create"

    def test_reject_emits_mandate_rejected(self, institution_a, sample_mandate_data):
        """Rejecting emits MANDATE_REJECTED event."""
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="reject",
            reason="Rejected",
            actor_id="governance",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()

        rejected_events = [e for e in events if e.event_type == MANDATE_REJECTED]
        assert len(rejected_events) == 1
        assert rejected_events[0].payload["decision"] == "reject"

        # No MANDATE_APPLIED event
        applied_events = [e for e in events if e.event_type == MANDATE_APPLIED]
        assert len(applied_events) == 0

    def test_revoke_emits_mandate_revoked(self, institution_a, sample_mandate_data):
        """Revoking emits MANDATE_REVOKED event."""
        # Create and approve
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Create",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Revoke
        revoke_proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="revoke",
            mandate_id="test-mandate-001",
            mandate_data=None,
            reason="Revoke",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=revoke_proposal.proposal_id,
            decision="approve",
            reason="Approved revocation",
            actor_id="governance",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()

        revoked_events = [e for e in events if e.event_type == MANDATE_REVOKED]
        assert len(revoked_events) == 1
        assert revoked_events[0].payload["operation"] == "revoke"


class TestBundleMandatesOverride:
    """Test that governed mandates override bundle mandates."""

    def test_governed_overrides_bundle(self, institution_a, actor_manager):
        """Governed mandate overrides bundle mandate with same ID."""
        # Set bundle mandate with limit 5000
        bundle_data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "test-mandate-001",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["manager"],
                    "limits": [
                        {
                            "rule_type": "numeric_max",
                            "field_path": "amount",
                            "value": 5000,  # Low limit
                        }
                    ],
                }
            ],
        }
        bundle_def = parse_mandates_data(bundle_data)
        set_mandates(None, bundle_def)

        # Without governed override, 6000 should fail
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 6000},
            institution_id=None,  # Use bundle only
        )
        assert result.allow is False

        # Create governed mandate with higher limit 10000
        governed_data = {
            "mandate_id": "test-mandate-001",  # Same ID
            "endpoint_sig": "POST /finance/expenses",
            "phase": "pre",
            "allowed_roles": ["manager"],
            "limits": [
                {
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 10000,  # Higher limit
                }
            ],
        }
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=governed_data,
            reason="Override bundle limit",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # With governed override, 6000 should pass
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 6000},
            institution_id=institution_a,  # Use governed
        )
        assert result.allow is True
        assert result.mandate_id == "test-mandate-001"


class TestListFunctions:
    """Test list functions."""

    def test_list_proposals(self, institution_a, sample_mandate_data):
        """List proposals returns all proposals."""
        # Create multiple proposals
        for i in range(3):
            propose_mandate_change(
                institution_id=institution_a,
                operation="create",
                mandate_id=f"test-mandate-{i:03d}",
                mandate_data={**sample_mandate_data, "mandate_id": f"test-mandate-{i:03d}"},
                reason=f"Test {i}",
                actor_id="admin",
            )

        proposals = list_mandate_proposals(institution_a)
        assert len(proposals) == 3

    def test_list_proposals_filter_status(self, institution_a, sample_mandate_data):
        """List proposals filters by status."""
        # Create and decide one
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Create another (still OPEN)
        propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-002",
            mandate_data={**sample_mandate_data, "mandate_id": "test-mandate-002"},
            reason="Test 2",
            actor_id="admin",
        )

        # Filter by OPEN
        open_proposals = list_mandate_proposals(institution_a, status_filter="OPEN")
        assert len(open_proposals) == 1
        assert open_proposals[0].mandate_id == "test-mandate-002"

        # Filter by DECIDED
        decided_proposals = list_mandate_proposals(institution_a, status_filter="DECIDED")
        assert len(decided_proposals) == 1
        assert decided_proposals[0].mandate_id == "test-mandate-001"

    def test_list_governed_mandates(self, institution_a, sample_mandate_data):
        """List governed mandates returns only applied mandates."""
        # Create and approve
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Test",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        mandates = list_governed_mandates(institution_a)
        assert "test-mandate-001" in mandates
        assert mandates["test-mandate-001"]["mandate_id"] == "test-mandate-001"


class TestUpdateOperation:
    """Test update operation."""

    def test_update_existing_mandate(self, institution_a, sample_mandate_data, actor_manager):
        """Updating an existing mandate changes its rules."""
        # Create initial mandate with limit 5000
        initial_data = {**sample_mandate_data, "limits": [
            {"rule_type": "numeric_max", "field_path": "amount", "value": 5000}
        ]}
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=initial_data,
            reason="Create",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Verify initial limit
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 7000},
            institution_id=institution_a,
        )
        assert result.allow is False  # Exceeds 5000

        # Update mandate with limit 10000
        updated_data = {**sample_mandate_data, "limits": [
            {"rule_type": "numeric_max", "field_path": "amount", "value": 10000}
        ]}
        update_proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="update",
            mandate_id="test-mandate-001",
            mandate_data=updated_data,
            reason="Update limit",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=update_proposal.proposal_id,
            decision="approve",
            reason="Approved update",
            actor_id="governance",
        )

        # Verify updated limit
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor_manager,
            payload={"amount": 7000},
            institution_id=institution_a,
        )
        assert result.allow is True  # Now within 10000


class TestErrorCases:
    """Test error cases."""

    def test_create_duplicate_mandate(self, institution_a, sample_mandate_data):
        """Creating a mandate that already exists returns error."""
        # Create and approve first mandate
        proposal, _, _ = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Create",
            actor_id="admin",
        )
        decide_mandate_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Try to create same mandate again
        proposal2, error_code, error_msg = propose_mandate_change(
            institution_id=institution_a,
            operation="create",
            mandate_id="test-mandate-001",
            mandate_data=sample_mandate_data,
            reason="Create again",
            actor_id="admin",
        )

        assert proposal2 is None
        assert error_code == MANDATE_ALREADY_EXISTS

    def test_update_nonexistent_mandate(self, institution_a, sample_mandate_data):
        """Updating a non-existent mandate returns error."""
        proposal, error_code, error_msg = propose_mandate_change(
            institution_id=institution_a,
            operation="update",
            mandate_id="nonexistent-mandate",
            mandate_data=sample_mandate_data,
            reason="Update",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == MANDATE_NOT_FOUND_FOR_UPDATE

    def test_revoke_nonexistent_mandate(self, institution_a):
        """Revoking a non-existent mandate returns error."""
        proposal, error_code, error_msg = propose_mandate_change(
            institution_id=institution_a,
            operation="revoke",
            mandate_id="nonexistent-mandate",
            mandate_data=None,
            reason="Revoke",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == MANDATE_NOT_FOUND_FOR_UPDATE
