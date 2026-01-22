"""Tests for Governed Autonomy (Etapa 4.4).

These tests verify:
1. Autonomy proposed does not change execution
2. After approval+apply, autonomy level/rules take effect
3. Revocation removes autonomy rules
4. Isolation: change in (A, finance) does not affect (A, support) or (B, finance)
"""

import json
import pytest
from pathlib import Path

from engine.core.actor_context import ActorContext
from engine.core.data_root import get_institution_root
from engine.core.ledger import reset_institution_ledgers, get_ledger_for_institution
from engine.core.autonomy import (
    evaluate_autonomy,
    set_autonomy_for_dept,
    reset_all_autonomy,
    AutonomyDef,
    AutonomyRule,
    parse_autonomy_data,
)
from engine.core.governed_autonomy import (
    propose_autonomy_change,
    decide_autonomy_proposal,
    apply_autonomy_change,
    get_effective_autonomy,
    list_autonomy_proposals,
    list_governed_autonomy,
    reset_governed_autonomy_registry,
    invalidate_all_autonomy_cache,
    load_governed_state,
    AUTONOMY_PROPOSED,
    AUTONOMY_GOV_APPROVED,
    AUTONOMY_GOV_REJECTED,
    AUTONOMY_GOV_APPLIED,
    AUTONOMY_GOV_REVOKED,
)
from engine.core.errors import (
    AUTONOMY_PROPOSAL_NOT_FOUND,
    AUTONOMY_PROPOSAL_ALREADY_DECIDED,
    AUTONOMY_PROPOSAL_INVALID,
    AUTONOMY_NOT_FOUND_FOR_UPDATE,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    reset_institution_ledgers()
    reset_all_autonomy()
    reset_governed_autonomy_registry()
    invalidate_all_autonomy_cache()
    yield
    reset_institution_ledgers()
    reset_all_autonomy()
    reset_governed_autonomy_registry()
    invalidate_all_autonomy_cache()


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
def sample_autonomy_level_data():
    """Sample autonomy data for level update."""
    return {
        "current_level": 3,
    }


@pytest.fixture
def sample_autonomy_rule_data():
    """Sample autonomy rule data."""
    return {
        "rule_id": "expense-rule-001",
        "endpoint_sig": "POST /finance/expenses",
        "phase": "pre",
        "required_level": 2,
    }


class TestProposalWorkflow:
    """Test proposal create/decide workflow."""

    def test_propose_update_level(self, institution_a, sample_autonomy_level_data):
        """Creating a level update proposal returns OPEN status."""
        proposal, error_code, error_msg = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data=sample_autonomy_level_data,
            reason="Update autonomy level to L3",
            actor_id="admin",
        )

        assert error_code is None
        assert error_msg is None
        assert proposal is not None
        assert proposal.status == "OPEN"
        assert proposal.autonomy_operation == "update_level"
        assert proposal.autonomy_data["current_level"] == 3

    def test_propose_create_rule(self, institution_a, sample_autonomy_rule_data):
        """Creating a rule creation proposal returns OPEN status."""
        proposal, error_code, error_msg = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id="expense-rule-001",
            autonomy_data=sample_autonomy_rule_data,
            reason="Add expense autonomy rule",
            actor_id="admin",
        )

        assert error_code is None
        assert error_msg is None
        assert proposal is not None
        assert proposal.status == "OPEN"
        assert proposal.autonomy_operation == "create_rule"
        assert proposal.rule_id == "expense-rule-001"

    def test_propose_invalid_operation(self, institution_a):
        """Invalid operation returns error."""
        proposal, error_code, error_msg = propose_autonomy_change(
            institution_id=institution_a,
            operation="invalid",
            rule_id=None,
            autonomy_data={},
            reason="Test",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == AUTONOMY_PROPOSAL_INVALID
        assert "Invalid operation" in error_msg

    def test_propose_create_rule_without_data(self, institution_a):
        """Create rule without autonomy_data returns error."""
        proposal, error_code, error_msg = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id="expense-rule-001",
            autonomy_data=None,
            reason="Test",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == AUTONOMY_PROPOSAL_INVALID
        assert "autonomy_data is required" in error_msg

    def test_propose_invalid_level(self, institution_a):
        """Invalid autonomy level returns error."""
        proposal, error_code, error_msg = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 10},  # Invalid level
            reason="Test",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == AUTONOMY_PROPOSAL_INVALID
        assert "Invalid autonomy data" in error_msg

    def test_decide_approve(self, institution_a, sample_autonomy_level_data):
        """Approving a proposal changes status to DECIDED."""
        # Create proposal
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data=sample_autonomy_level_data,
            reason="Test",
            actor_id="admin",
        )

        # Decide
        decided, error_code, error_msg = decide_autonomy_proposal(
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

    def test_decide_reject(self, institution_a, sample_autonomy_level_data):
        """Rejecting a proposal changes status to DECIDED."""
        # Create proposal
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data=sample_autonomy_level_data,
            reason="Test",
            actor_id="admin",
        )

        # Decide
        decided, error_code, error_msg = decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="reject",
            reason="Rejected for testing",
            actor_id="governance",
        )

        assert error_code is None
        assert decided.status == "DECIDED"
        assert decided.decision == "reject"

    def test_decide_already_decided(self, institution_a, sample_autonomy_level_data):
        """Deciding already decided proposal returns error."""
        # Create and decide
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data=sample_autonomy_level_data,
            reason="Test",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="First decision",
            actor_id="governance",
        )

        # Try to decide again
        decided, error_code, error_msg = decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="reject",
            reason="Second decision",
            actor_id="governance",
        )

        assert decided is None
        assert error_code == AUTONOMY_PROPOSAL_ALREADY_DECIDED

    def test_decide_not_found(self, institution_a):
        """Deciding non-existent proposal returns error."""
        decided, error_code, error_msg = decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id="nonexistent-proposal",
            decision="approve",
            reason="Test",
            actor_id="governance",
        )

        assert decided is None
        assert error_code == AUTONOMY_PROPOSAL_NOT_FOUND


class TestAutonomyNotAppliedUntilApproved:
    """Test that proposed autonomy doesn't affect runtime until approved."""

    def test_proposed_level_does_not_affect_runtime(
        self, institution_a, sample_autonomy_rule_data
    ):
        """A proposed level change should NOT affect evaluate_autonomy."""
        # Set bundle autonomy with level 2 and a rule requiring level 3
        bundle_data = {
            "autonomy_schema_version": "1.0",
            "current_level": 2,
            "rules": [
                {
                    "rule_id": "expense-rule-001",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 3,  # Requires L3
                }
            ],
        }
        bundle_def = parse_autonomy_data(bundle_data)
        set_autonomy_for_dept(None, bundle_def)

        # Should deny (level 2 < required 3)
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=None,  # Use bundle only
        )
        assert result.decision == "deny"

        # Create proposal to update level to 3 (not yet approved)
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 3},
            reason="Test",
            actor_id="admin",
        )

        # Still should deny (proposal not applied) - bundle still used
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=None,  # No governed autonomy yet
        )
        assert result.decision == "deny"

    def test_approved_level_affects_runtime(self, institution_a):
        """After approval+apply, autonomy level should affect evaluate_autonomy."""
        # First create a rule that requires level 2
        rule_data = {
            "rule_id": "expense-rule-001",
            "endpoint_sig": "POST /finance/expenses",
            "phase": "pre",
            "required_level": 2,
        }
        rule_proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id="expense-rule-001",
            autonomy_data=rule_data,
            reason="Create rule",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=rule_proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Set level to 1 (below required)
        level_proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 1},
            reason="Set low level",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=level_proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Should deny (level 1 < required 2)
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,
        )
        assert result.decision == "deny"

        # Update level to 2 (matches required)
        level_proposal2, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 2},
            reason="Raise level",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=level_proposal2.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Should allow (level 2 >= required 2)
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,
        )
        assert result.decision == "allow"


class TestRevocation:
    """Test revocation workflow."""

    def test_revoke_governed_rule(self, institution_a):
        """Revoking a governed rule removes it."""
        # Create and approve a rule
        rule_data = {
            "rule_id": "expense-rule-001",
            "endpoint_sig": "POST /finance/expenses",
            "phase": "pre",
            "required_level": 2,
        }
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id="expense-rule-001",
            autonomy_data=rule_data,
            reason="Create rule",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Also set level to 3 (above required)
        level_proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 3},
            reason="Set level",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=level_proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Verify rule is in effect (should allow)
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,
        )
        assert result.decision == "allow"
        assert result.rule_id == "expense-rule-001"

        # Revoke the rule
        revoke_proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="revoke_rule",
            rule_id="expense-rule-001",
            autonomy_data=None,
            reason="Revoke rule",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=revoke_proposal.proposal_id,
            decision="approve",
            reason="Approved revocation",
            actor_id="governance",
        )

        # Now rule should be revoked - no matching rule = deny per canonical semantics
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,
        )
        assert result.decision == "deny"
        assert result.rule_id is None


class TestIsolation:
    """Test isolation between institutions and departments."""

    def test_institution_isolation(self, institution_a, institution_b):
        """Autonomy in institution A does not affect institution B."""
        # Create rule for institution A
        rule_data = {
            "rule_id": "expense-rule-001",
            "endpoint_sig": "POST /finance/expenses",
            "phase": "pre",
            "required_level": 2,
        }
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id="expense-rule-001",
            autonomy_data=rule_data,
            reason="Create rule",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Set level to 3 for institution A
        level_proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 3},
            reason="Set level",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=level_proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Institution A should have the rule (allow)
        result_a = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,
        )
        assert result_a.decision == "allow"
        assert result_a.rule_id == "expense-rule-001"

        # Institution B should NOT have the rule (allow-all, no contract)
        result_b = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_b,
        )
        assert result_b.decision == "allow"
        assert result_b.rule_id is None  # No rule matched

    def test_department_isolation(self, institution_a):
        """Autonomy in dept finance does not affect dept support."""
        # Create rule for finance dept
        rule_data = {
            "rule_id": "expense-rule-001",
            "endpoint_sig": "POST /finance/expenses",
            "phase": "pre",
            "required_level": 2,
        }
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id="expense-rule-001",
            autonomy_data=rule_data,
            reason="Create rule",
            actor_id="admin",
            dept_id="finance",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
            dept_id="finance",
        )

        # Set level for finance
        level_proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 3},
            reason="Set level",
            actor_id="admin",
            dept_id="finance",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=level_proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
            dept_id="finance",
        )

        # Finance dept should have the rule
        result_finance = evaluate_autonomy(
            phase="pre",
            dept_id="finance",
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,
        )
        assert result_finance.decision == "allow"
        assert result_finance.rule_id == "expense-rule-001"

        # Support dept should NOT have the rule
        result_support = evaluate_autonomy(
            phase="pre",
            dept_id="support",
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,
        )
        assert result_support.decision == "allow"
        assert result_support.rule_id is None


class TestLedgerEvents:
    """Test ledger event emission."""

    def test_propose_emits_autonomy_proposed(self, institution_a, sample_autonomy_level_data):
        """Proposing emits AUTONOMY_PROPOSED event."""
        propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data=sample_autonomy_level_data,
            reason="Test",
            actor_id="admin",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()
        proposed_events = [e for e in events if e.event_type == AUTONOMY_PROPOSED]
        assert len(proposed_events) == 1
        assert proposed_events[0].payload["operation"] == "update_level"

    def test_approve_emits_autonomy_approved_and_applied(
        self, institution_a, sample_autonomy_level_data
    ):
        """Approving emits AUTONOMY_GOV_APPROVED and AUTONOMY_GOV_APPLIED events."""
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data=sample_autonomy_level_data,
            reason="Test",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()

        approved_events = [e for e in events if e.event_type == AUTONOMY_GOV_APPROVED]
        assert len(approved_events) == 1
        assert approved_events[0].payload["decision"] == "approve"

        applied_events = [e for e in events if e.event_type == AUTONOMY_GOV_APPLIED]
        assert len(applied_events) == 1
        assert applied_events[0].payload["operation"] == "update_level"

    def test_reject_emits_autonomy_rejected(self, institution_a, sample_autonomy_level_data):
        """Rejecting emits AUTONOMY_GOV_REJECTED event."""
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data=sample_autonomy_level_data,
            reason="Test",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="reject",
            reason="Rejected",
            actor_id="governance",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()

        rejected_events = [e for e in events if e.event_type == AUTONOMY_GOV_REJECTED]
        assert len(rejected_events) == 1
        assert rejected_events[0].payload["decision"] == "reject"

        # No AUTONOMY_GOV_APPLIED event
        applied_events = [e for e in events if e.event_type == AUTONOMY_GOV_APPLIED]
        assert len(applied_events) == 0

    def test_revoke_emits_autonomy_revoked(self, institution_a, sample_autonomy_rule_data):
        """Revoking emits AUTONOMY_GOV_REVOKED event."""
        # Create and approve
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id="expense-rule-001",
            autonomy_data=sample_autonomy_rule_data,
            reason="Create",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Revoke
        revoke_proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="revoke_rule",
            rule_id="expense-rule-001",
            autonomy_data=None,
            reason="Revoke",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=revoke_proposal.proposal_id,
            decision="approve",
            reason="Approved revocation",
            actor_id="governance",
        )

        ledger = get_ledger_for_institution(institution_a)
        events = ledger.get_all_events()

        revoked_events = [e for e in events if e.event_type == AUTONOMY_GOV_REVOKED]
        assert len(revoked_events) == 1
        assert revoked_events[0].payload["operation"] == "revoke_rule"


class TestBundleAutonomyOverride:
    """Test that governed autonomy overrides bundle autonomy."""

    def test_governed_overrides_bundle_level(self, institution_a):
        """Governed level overrides bundle level."""
        # Set bundle autonomy with level 1
        bundle_data = {
            "autonomy_schema_version": "1.0",
            "current_level": 1,
            "rules": [
                {
                    "rule_id": "expense-rule-001",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 2,  # Requires L2
                }
            ],
        }
        bundle_def = parse_autonomy_data(bundle_data)
        set_autonomy_for_dept(None, bundle_def)

        # Without governed override, should deny (level 1 < required 2)
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=None,  # Use bundle only
        )
        assert result.decision == "deny"

        # Create governed level override to 3
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 3},
            reason="Override bundle level",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # With governed override, should allow (governed level 3 >= required 2)
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,  # Use governed
        )
        assert result.decision == "allow"


class TestListFunctions:
    """Test list functions."""

    def test_list_proposals(self, institution_a, sample_autonomy_level_data):
        """List proposals returns all proposals."""
        # Create multiple proposals
        for i in range(3):
            propose_autonomy_change(
                institution_id=institution_a,
                operation="update_level",
                rule_id=None,
                autonomy_data={"current_level": i},
                reason=f"Test {i}",
                actor_id="admin",
            )

        proposals = list_autonomy_proposals(institution_a)
        assert len(proposals) == 3

    def test_list_proposals_filter_status(self, institution_a, sample_autonomy_level_data):
        """List proposals filters by status."""
        # Create and decide one
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 2},
            reason="Test",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Create another (still OPEN)
        propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 3},
            reason="Test 2",
            actor_id="admin",
        )

        # Filter by OPEN
        open_proposals = list_autonomy_proposals(institution_a, status_filter="OPEN")
        assert len(open_proposals) == 1

        # Filter by DECIDED
        decided_proposals = list_autonomy_proposals(institution_a, status_filter="DECIDED")
        assert len(decided_proposals) == 1

    def test_list_governed_autonomy(self, institution_a, sample_autonomy_rule_data):
        """List governed autonomy returns current state."""
        # Create and approve a rule
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id="expense-rule-001",
            autonomy_data=sample_autonomy_rule_data,
            reason="Test",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        state = list_governed_autonomy(institution_a)
        assert "expense-rule-001" in state.rules
        assert state.rules["expense-rule-001"]["rule_id"] == "expense-rule-001"


class TestUpdateOperation:
    """Test update operation."""

    def test_update_existing_rule(self, institution_a):
        """Updating an existing rule changes its properties."""
        # Create initial rule with required_level 2
        initial_data = {
            "rule_id": "expense-rule-001",
            "endpoint_sig": "POST /finance/expenses",
            "phase": "pre",
            "required_level": 2,
        }
        proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id="expense-rule-001",
            autonomy_data=initial_data,
            reason="Create",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Set level to 2
        level_proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": 2},
            reason="Set level",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=level_proposal.proposal_id,
            decision="approve",
            reason="Approved",
            actor_id="governance",
        )

        # Verify rule is in effect (should allow with level 2)
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,
        )
        assert result.decision == "allow"

        # Update rule to require level 3
        updated_data = {
            "rule_id": "expense-rule-001",
            "endpoint_sig": "POST /finance/expenses",
            "phase": "pre",
            "required_level": 3,
        }
        update_proposal, _, _ = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_rule",
            rule_id="expense-rule-001",
            autonomy_data=updated_data,
            reason="Update required level",
            actor_id="admin",
        )
        decide_autonomy_proposal(
            institution_id=institution_a,
            proposal_id=update_proposal.proposal_id,
            decision="approve",
            reason="Approved update",
            actor_id="governance",
        )

        # Now should deny (level 2 < updated required 3)
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            institution_id=institution_a,
        )
        assert result.decision == "deny"


class TestErrorCases:
    """Test error cases."""

    def test_update_nonexistent_rule(self, institution_a, sample_autonomy_rule_data):
        """Updating a non-existent rule returns error."""
        proposal, error_code, error_msg = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_rule",
            rule_id="nonexistent-rule",
            autonomy_data=sample_autonomy_rule_data,
            reason="Update",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == AUTONOMY_NOT_FOUND_FOR_UPDATE

    def test_revoke_nonexistent_rule(self, institution_a):
        """Revoking a non-existent rule returns error."""
        proposal, error_code, error_msg = propose_autonomy_change(
            institution_id=institution_a,
            operation="revoke_rule",
            rule_id="nonexistent-rule",
            autonomy_data=None,
            reason="Revoke",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == AUTONOMY_NOT_FOUND_FOR_UPDATE

    def test_create_rule_without_rule_id(self, institution_a, sample_autonomy_rule_data):
        """Creating a rule without rule_id returns error."""
        proposal, error_code, error_msg = propose_autonomy_change(
            institution_id=institution_a,
            operation="create_rule",
            rule_id=None,  # Missing rule_id
            autonomy_data=sample_autonomy_rule_data,
            reason="Create",
            actor_id="admin",
        )

        assert proposal is None
        assert error_code == AUTONOMY_PROPOSAL_INVALID


class TestAllAutonomyLevels:
    """Test all autonomy levels (L0-L4)."""

    @pytest.mark.parametrize("level", [0, 1, 2, 3, 4])
    def test_autonomy_level(self, institution_a, level):
        """Each autonomy level is valid and can be set."""
        proposal, error_code, error_msg = propose_autonomy_change(
            institution_id=institution_a,
            operation="update_level",
            rule_id=None,
            autonomy_data={"current_level": level},
            reason=f"Set level to L{level}",
            actor_id="admin",
        )

        assert error_code is None
        assert proposal is not None
        assert proposal.autonomy_data["current_level"] == level
