"""Tests for Governed Policies (Etapa 4.4).

These tests verify:
1. Policy proposed does not change execution
2. After approval+apply, policy enforces constraints
3. Revocation removes the policy
4. Isolation: change in (A, finance) does not affect (A, support) or (B, finance)
"""

import json
import pytest
from pathlib import Path

from engine.core.actor_context import ActorContext
from engine.core.data_root import get_institution_root
from engine.core.ledger import reset_institution_ledgers, get_ledger_for_institution
from engine.core.policy import (
    evaluate_policies,
    set_policies,
    reset_all_policies,
    PolicyDef,
    PolicyRule,
    parse_policy_data,
)
from engine.core.governed_policies import (
    propose_policy_change,
    decide_policy_proposal,
    apply_policy_change,
    get_effective_policies,
    list_policy_proposals,
    list_governed_policies,
    reset_governed_policies_registry,
    invalidate_all_policies_cache,
    load_governed_state,
    POLICY_PROPOSED,
    POLICY_APPROVED,
    POLICY_REJECTED,
    POLICY_APPLIED,
    POLICY_REVOKED,
)
from engine.core.errors import (
    POLICY_PROPOSAL_NOT_FOUND,
    POLICY_PROPOSAL_ALREADY_DECIDED,
    POLICY_PROPOSAL_INVALID,
    POLICY_ALREADY_EXISTS,
    POLICY_NOT_FOUND_FOR_UPDATE,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    reset_institution_ledgers()
    reset_all_policies()
    reset_governed_policies_registry()
    invalidate_all_policies_cache()
    yield
    reset_institution_ledgers()
    reset_all_policies()
    reset_governed_policies_registry()
    invalidate_all_policies_cache()


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
def sample_policy_data():
    """Sample policy data for testing (numeric_max)."""
    return {
        "policy_id": "test-policy-001",
        "rule_type": "numeric_max",
        "field_path": "amount",
        "phase": "pre",
        "endpoint_sig": "POST /finance/expenses",
        "value": 5000,
        "message": "Amount exceeds maximum allowed",
    }


@pytest.fixture
def sample_required_field_policy():
    """Sample policy for required_field rule type."""
    return {
        "policy_id": "test-policy-required",
        "rule_type": "required_field",
        "field_path": "description",
        "phase": "pre",
        "endpoint_sig": "POST /finance/expenses",
        "value": True,
        "message": "Description is required",
    }


class TestProposalWorkflow:
    """Test proposal create/decide workflow."""

    def test_propose_create_policy(self, institution_a, sample_policy_data):
        """Creating a proposal returns OPEN status."""
        proposal, error_code, error_msg = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Add new policy for testing",
            actor_id="admin",
        )

        assert error_code is None
        assert error_msg is None
        assert proposal is not None
        assert proposal.status == "OPEN"
        assert proposal.policy_operation == "create"
        assert proposal.policy_id == "test-policy-001"

    def test_propose_invalid_operation(self, institution_a):
        """Invalid operation returns error."""
        proposal, error_code, error_msg = propose_policy_change(
            institution_id=institution_a,
            operation="invalid",
            policy_id="test-policy-001",
            policy_data={},
            reason="Test",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == POLICY_PROPOSAL_INVALID
        assert "Invalid operation" in error_msg

    def test_propose_create_without_data(self, institution_a):
        """Create without policy_data returns error."""
        proposal, error_code, error_msg = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=None,
            reason="Test",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == POLICY_PROPOSAL_INVALID
        assert "policy_data is required" in error_msg

    def test_propose_invalid_schema(self, institution_a):
        """Invalid policy schema returns error."""
        proposal, error_code, error_msg = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data={
                "policy_id": "test-policy-001",
                "rule_type": "invalid_rule_type",  # Invalid rule type
                "field_path": "amount",
                "phase": "pre",
                "endpoint_sig": "POST /finance/expenses",
                "value": 5000,
            },
            reason="Test",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == POLICY_PROPOSAL_INVALID
        assert "Invalid policy data" in error_msg

    def test_decide_approve(self, institution_a, sample_policy_data):
        """Approving a proposal changes status to DECIDED."""
        # Create proposal
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Test",
            actor_id="admin",
        )

        # Decide
        decided, error_code, error_msg = decide_policy_proposal(
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

    def test_decide_reject(self, institution_a, sample_policy_data):
        """Rejecting a proposal changes status to DECIDED."""
        # Create proposal
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Test",
            actor_id="admin",
        )

        # Decide
        decided, error_code, error_msg = decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="reject",
            reason="Rejected for testing",
            actor_id="governance",
        )

        assert error_code is None
        assert decided.status == "DECIDED"
        assert decided.decision == "reject"

    def test_decide_already_decided(self, institution_a, sample_policy_data):
        """Deciding already decided proposal returns error."""
        # Create and decide
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Test",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="First decision",
            actor_id="governance",
        )

        # Try to decide again
        decided, error_code, error_msg = decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="reject",
            reason="Second decision",
            actor_id="governance",
        )

        assert decided is None
        assert error_code == POLICY_PROPOSAL_ALREADY_DECIDED

    def test_decide_not_found(self, institution_a):
        """Deciding non-existent proposal returns error."""
        decided, error_code, error_msg = decide_policy_proposal(
            institution_id=institution_a,
            proposal_id="nonexistent-proposal",
            decision="approve",
            reason="Test",
            actor_id="governance",
        )

        assert decided is None
        assert error_code == POLICY_PROPOSAL_NOT_FOUND


class TestPolicyNotAppliedUntilApproved:
    """Test that proposed policies don't affect runtime until approved."""

    def test_proposed_policy_does_not_affect_runtime(
        self, institution_a, sample_policy_data, actor_manager
    ):
        """A proposed policy should NOT affect evaluate_policies."""
        # Initially no policies - allow all
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 10000},
            institution_id=institution_a,
        )
        assert result.decision == "allow"

        # Create proposal (not yet approved)
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,  # max 5000
            reason="Test",
            actor_id="admin",
        )

        # Still should allow (proposal not applied)
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 10000},
            institution_id=institution_a,
        )
        assert result.decision == "allow"

    def test_approved_policy_affects_runtime(
        self, institution_a, sample_policy_data, actor_manager
    ):
        """After approval+apply, policy should affect evaluate_policies."""
        # Create and approve policy (max 5000)
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Test",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Now policy should be in effect
        # Within limit - should allow
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 4000},
            institution_id=institution_a,
        )
        assert result.decision == "allow"

        # Exceeds limit - should deny
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 6000},
            institution_id=institution_a,
        )
        assert result.decision == "deny"
        assert result.policy_id == "test-policy-001"


class TestRevocation:
    """Test revocation workflow."""

    def test_revoke_governed_policy(
        self, institution_a, sample_policy_data, actor_manager
    ):
        """Revoking a governed policy removes its constraints."""
        # Create and approve policy (max 5000)
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Create",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Verify policy is in effect (6000 should be denied)
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 6000},
            institution_id=institution_a,
        )
        assert result.decision == "deny"

        # Revoke policy
        revoke_proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="revoke",
            policy_id="test-policy-001",
            policy_data=None,
            reason="Revoke",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=revoke_proposal.proposal_id,
            decision="approve",
            reason="Approved revocation",
            actor_id="governance",
        )

        # Now policy should be revoked - 6000 should be allowed
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 6000},
            institution_id=institution_a,
        )
        assert result.decision == "allow"


class TestIsolation:
    """Test isolation between institutions and departments."""

    def test_institution_isolation(
        self, institution_a, institution_b, sample_policy_data, actor_manager
    ):
        """Policy in institution A does not affect institution B."""
        # Create policy for institution A (max 5000)
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Create",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Institution A should enforce the policy (6000 denied)
        result_a = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 6000},
            institution_id=institution_a,
        )
        assert result_a.decision == "deny"
        assert result_a.policy_id == "test-policy-001"

        # Institution B should NOT have the policy (6000 allowed)
        result_b = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 6000},
            institution_id=institution_b,
        )
        assert result_b.decision == "allow"
        assert result_b.policy_id is None

    def test_department_isolation(
        self, institution_a, sample_policy_data, actor_manager
    ):
        """Policy in dept finance does not affect dept support."""
        # Create policy for finance dept
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Create",
            actor_id="admin",
            dept_id="finance",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
            dept_id="finance",
        )

        # Finance dept should have the policy (6000 denied)
        result_finance = evaluate_policies(
            phase="pre",
            dept_id="finance",
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 6000},
            institution_id=institution_a,
        )
        assert result_finance.decision == "deny"
        assert result_finance.policy_id == "test-policy-001"

        # Support dept should NOT have the policy (6000 allowed)
        result_support = evaluate_policies(
            phase="pre",
            dept_id="support",
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 6000},
            institution_id=institution_a,
        )
        assert result_support.decision == "allow"
        assert result_support.policy_id is None


class TestLedgerEvents:
    """Test ledger event emission."""

    def test_propose_emits_policy_proposed(self, institution_a, sample_policy_data):
        """Proposing emits POLICY_PROPOSED event."""
        propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Test",
            actor_id="admin",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()
        proposed_events = [e for e in events if e.event_type == POLICY_PROPOSED]
        assert len(proposed_events) == 1
        assert proposed_events[0].payload["operation"] == "create"
        assert proposed_events[0].payload["policy_id"] == "test-policy-001"

    def test_approve_emits_policy_approved_and_applied(
        self, institution_a, sample_policy_data
    ):
        """Approving emits POLICY_APPROVED and POLICY_APPLIED events."""
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Test",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()

        approved_events = [e for e in events if e.event_type == POLICY_APPROVED]
        assert len(approved_events) == 1
        assert approved_events[0].payload["decision"] == "approve"

        applied_events = [e for e in events if e.event_type == POLICY_APPLIED]
        assert len(applied_events) == 1
        assert applied_events[0].payload["operation"] == "create"

    def test_reject_emits_policy_rejected(self, institution_a, sample_policy_data):
        """Rejecting emits POLICY_REJECTED event."""
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Test",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="reject",
            reason="Rejected",
            actor_id="governance",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()

        rejected_events = [e for e in events if e.event_type == POLICY_REJECTED]
        assert len(rejected_events) == 1
        assert rejected_events[0].payload["decision"] == "reject"

        # No POLICY_APPLIED event
        applied_events = [e for e in events if e.event_type == POLICY_APPLIED]
        assert len(applied_events) == 0

    def test_revoke_emits_policy_revoked(self, institution_a, sample_policy_data):
        """Revoking emits POLICY_REVOKED event."""
        # Create and approve
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Create",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Revoke
        revoke_proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="revoke",
            policy_id="test-policy-001",
            policy_data=None,
            reason="Revoke",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=revoke_proposal.proposal_id,
            decision="approve",
            reason="Approved revocation",
            actor_id="governance",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()

        revoked_events = [e for e in events if e.event_type == POLICY_REVOKED]
        assert len(revoked_events) == 1
        assert revoked_events[0].payload["operation"] == "revoke"


class TestBundlePoliciesOverride:
    """Test that governed policies override bundle policies."""

    def test_governed_overrides_bundle(self, institution_a, actor_manager):
        """Governed policy overrides bundle policy with same ID."""
        # Set bundle policy with limit 5000
        bundle_data = {
            "policy_schema_version": "1.1",
            "policies": [
                {
                    "policy_id": "test-policy-001",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "value": 5000,  # Low limit
                    "message": "Bundle limit exceeded",
                }
            ],
        }
        bundle_def = parse_policy_data(bundle_data)
        set_policies(None, bundle_def)

        # Without governed override, 6000 should fail
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 6000},
            institution_id=None,  # Use bundle only
        )
        assert result.decision == "deny"

        # Create governed policy with higher limit 10000
        governed_data = {
            "policy_id": "test-policy-001",  # Same ID
            "rule_type": "numeric_max",
            "field_path": "amount",
            "phase": "pre",
            "endpoint_sig": "POST /finance/expenses",
            "value": 10000,  # Higher limit
            "message": "Governed limit exceeded",
        }
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=governed_data,
            reason="Override bundle limit",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # With governed override, 6000 should pass
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 6000},
            institution_id=institution_a,  # Use governed
        )
        assert result.decision == "allow"


class TestListFunctions:
    """Test list functions."""

    def test_list_proposals(self, institution_a, sample_policy_data):
        """List proposals returns all proposals."""
        # Create multiple proposals
        for i in range(3):
            propose_policy_change(
                institution_id=institution_a,
                operation="create",
                policy_id=f"test-policy-{i:03d}",
                policy_data={**sample_policy_data, "policy_id": f"test-policy-{i:03d}"},
                reason=f"Test {i}",
                actor_id="admin",
            )

        proposals = list_policy_proposals(institution_a)
        assert len(proposals) == 3

    def test_list_proposals_filter_status(self, institution_a, sample_policy_data):
        """List proposals filters by status."""
        # Create and decide one
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Test",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Create another (still OPEN)
        propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-002",
            policy_data={**sample_policy_data, "policy_id": "test-policy-002"},
            reason="Test 2",
            actor_id="admin",
        )

        # Filter by OPEN
        open_proposals = list_policy_proposals(institution_a, status_filter="OPEN")
        assert len(open_proposals) == 1
        assert open_proposals[0].policy_id == "test-policy-002"

        # Filter by DECIDED
        decided_proposals = list_policy_proposals(institution_a, status_filter="DECIDED")
        assert len(decided_proposals) == 1
        assert decided_proposals[0].policy_id == "test-policy-001"

    def test_list_governed_policies(self, institution_a, sample_policy_data):
        """List governed policies returns only applied policies."""
        # Create and approve
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Test",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        policies = list_governed_policies(institution_a)
        assert "test-policy-001" in policies
        assert policies["test-policy-001"]["policy_id"] == "test-policy-001"


class TestUpdateOperation:
    """Test update operation."""

    def test_update_existing_policy(self, institution_a, sample_policy_data, actor_manager):
        """Updating an existing policy changes its rules."""
        # Create initial policy with limit 5000
        initial_data = {**sample_policy_data, "value": 5000}
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=initial_data,
            reason="Create",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Verify initial limit (7000 should be denied)
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 7000},
            institution_id=institution_a,
        )
        assert result.decision == "deny"

        # Update policy with limit 10000
        updated_data = {**sample_policy_data, "value": 10000}
        update_proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="update",
            policy_id="test-policy-001",
            policy_data=updated_data,
            reason="Update limit",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=update_proposal.proposal_id,
            decision="approve",
            reason="Approved update",
            actor_id="governance",
        )

        # Verify updated limit (7000 should now be allowed)
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 7000},
            institution_id=institution_a,
        )
        assert result.decision == "allow"


class TestErrorCases:
    """Test error cases."""

    def test_create_duplicate_policy(self, institution_a, sample_policy_data):
        """Creating a policy that already exists returns error."""
        # Create and approve first policy
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Create",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Try to create same policy again
        proposal2, error_code, error_msg = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-001",
            policy_data=sample_policy_data,
            reason="Create again",
            actor_id="admin",
        )

        assert proposal2 is None
        assert error_code == POLICY_ALREADY_EXISTS

    def test_update_nonexistent_policy(self, institution_a, sample_policy_data):
        """Updating a non-existent policy returns error."""
        proposal, error_code, error_msg = propose_policy_change(
            institution_id=institution_a,
            operation="update",
            policy_id="nonexistent-policy",
            policy_data=sample_policy_data,
            reason="Update",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == POLICY_NOT_FOUND_FOR_UPDATE

    def test_revoke_nonexistent_policy(self, institution_a):
        """Revoking a non-existent policy returns error."""
        proposal, error_code, error_msg = propose_policy_change(
            institution_id=institution_a,
            operation="revoke",
            policy_id="nonexistent-policy",
            policy_data=None,
            reason="Revoke",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == POLICY_NOT_FOUND_FOR_UPDATE


class TestDifferentRuleTypes:
    """Test different policy rule types."""

    def test_required_field_policy(self, institution_a, sample_required_field_policy):
        """Required field policy enforces field presence."""
        # Create and approve required field policy
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-required",
            policy_data=sample_required_field_policy,
            reason="Test required field",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Without description - should deny
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 1000},
            institution_id=institution_a,
        )
        assert result.decision == "deny"
        assert result.policy_id == "test-policy-required"

        # With description - should allow
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 1000, "description": "Office supplies"},
            institution_id=institution_a,
        )
        assert result.decision == "allow"

    def test_numeric_min_policy(self, institution_a):
        """Numeric min policy enforces minimum value."""
        policy_data = {
            "policy_id": "test-policy-min",
            "rule_type": "numeric_min",
            "field_path": "amount",
            "phase": "pre",
            "endpoint_sig": "POST /finance/expenses",
            "value": 100,
            "message": "Amount must be at least 100",
        }

        # Create and approve
        proposal, _, _ = propose_policy_change(
            institution_id=institution_a,
            operation="create",
            policy_id="test-policy-min",
            policy_data=policy_data,
            reason="Test numeric min",
            actor_id="admin",
        )
        decide_policy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Below minimum - should deny
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 50},
            institution_id=institution_a,
        )
        assert result.decision == "deny"

        # At minimum - should allow
        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 100},
            institution_id=institution_a,
        )
        assert result.decision == "allow"
