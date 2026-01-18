"""Tests for EGE proposals registry (core/ege_proposals.py)."""

import json
import pytest
from pathlib import Path

from engine.core.ege import DriftState, save_drift_state, load_drift_state
from engine.core.ege_proposals import (
    create_drift_resolution_proposal,
    decide_proposal,
    list_proposals,
    load_records,
    load_current_state,
    reset_proposals_registry,
    ProposalRecord,
    ProposalState,
    PROPOSALS_FILE,
)
from engine.core.institution_config import (
    save_active_config,
    get_effective_config,
    reset_config_cache,
    invalidate_config_cache,
)
from engine.core.errors import (
    EGE_NO_DRIFT_ACTIVE,
    EGE_PROPOSAL_NOT_FOUND,
    EGE_PROPOSAL_ALREADY_DECIDED,
    EGE_DECISION_INVALID,
)
from engine.core.ledger import AuditLedger, set_ledger, get_ledger, get_ledger_for_institution


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))

    # Set up ledger
    ledger_path = tmp_path / "audit_ledger.jsonl"
    ledger = AuditLedger(ledger_path)
    set_ledger(ledger)

    reset_config_cache()
    reset_proposals_registry()

    yield

    reset_config_cache()
    reset_proposals_registry()
    set_ledger(None)


@pytest.fixture
def institution_id():
    """Test institution ID."""
    return "test-inst-proposals-001"


@pytest.fixture
def active_drift_state():
    """Create an active drift state."""
    return DriftState(
        status="ACTIVE",
        checked_at="2024-01-01T00:00:00Z",
        expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
        expected_contract_ledger_sha256="SHA256:" + "b" * 64,
        observed_bundle_manifest_sha256="SHA256:" + "c" * 64,
        observed_contract_ledger_sha256="SHA256:" + "d" * 64,
        bundle_manifest_mismatch=True,
        contract_ledger_mismatch=True,
    )


@pytest.fixture
def clear_drift_state():
    """Create a clear drift state."""
    return DriftState(
        status="CLEAR",
        checked_at="2024-01-01T00:00:00Z",
    )


class TestCreateProposal:
    """Test create_drift_resolution_proposal function."""

    def test_create_proposal_success(self, institution_id, active_drift_state):
        """Create proposal when drift is ACTIVE."""
        proposal, error_code, error_msg = create_drift_resolution_proposal(
            institution_id, active_drift_state
        )

        assert error_code is None
        assert proposal is not None
        assert proposal.status == "OPEN"
        assert proposal.proposal_id is not None
        assert proposal.expected_bundle_manifest_sha256 == active_drift_state.expected_bundle_manifest_sha256
        assert proposal.observed_bundle_manifest_sha256 == active_drift_state.observed_bundle_manifest_sha256

    def test_create_proposal_fails_when_clear(self, institution_id, clear_drift_state):
        """Cannot create proposal when drift is CLEAR."""
        proposal, error_code, error_msg = create_drift_resolution_proposal(
            institution_id, clear_drift_state
        )

        assert proposal is None
        assert error_code == EGE_NO_DRIFT_ACTIVE

    def test_create_proposal_fails_when_unpinned(self, institution_id):
        """Cannot create proposal when drift is UNPINNED."""
        unpinned_state = DriftState(status="UNPINNED")

        proposal, error_code, error_msg = create_drift_resolution_proposal(
            institution_id, unpinned_state
        )

        assert proposal is None
        assert error_code == EGE_NO_DRIFT_ACTIVE

    def test_create_proposal_writes_record(self, institution_id, active_drift_state, tmp_path, monkeypatch):
        """Creating proposal writes to JSONL file."""
        data_root = tmp_path / "data"
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(data_root))

        create_drift_resolution_proposal(institution_id, active_drift_state)

        proposals_path = data_root / "institutions" / institution_id / PROPOSALS_FILE
        assert proposals_path.exists()

        records = load_records(institution_id)
        assert len(records) == 1
        assert records[0].operation == "create"
        assert records[0].status == "OPEN"

    def test_create_proposal_emits_ledger_event(self, institution_id, active_drift_state):
        """Creating proposal emits EGE_PROPOSAL_CREATED event."""
        create_drift_resolution_proposal(institution_id, active_drift_state)

        ledger = get_ledger_for_institution(institution_id)
        if not ledger._path.exists():
            events = []
        else:
            with open(ledger._path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

        created_events = [e for e in events if e.get("event_type") == "EGE_PROPOSAL_CREATED"]
        assert len(created_events) >= 1
        event = created_events[-1]
        assert event["step"] == "EGE:proposal.create"


class TestDecideProposal:
    """Test decide_proposal function."""

    def test_decide_proposal_accept(self, institution_id, active_drift_state):
        """Accept proposal updates config and clears drift."""
        # Save initial drift state
        save_drift_state(institution_id, active_drift_state)

        # Create proposal
        proposal, _, _ = create_drift_resolution_proposal(institution_id, active_drift_state)
        assert proposal is not None

        # Accept proposal
        decided, error_code, error_msg = decide_proposal(
            institution_id,
            proposal.proposal_id,
            "accept",
            "Approved by test",
            "test-actor",
        )

        assert error_code is None
        assert decided is not None
        assert decided.status == "DECIDED"
        assert decided.decision == "accept"
        assert decided.decider_actor_id == "test-actor"

        # Check config was updated
        invalidate_config_cache(institution_id)
        config = get_effective_config(institution_id)
        assert config.pinned_bundle_manifest_sha256 == active_drift_state.observed_bundle_manifest_sha256
        assert config.pinned_contract_ledger_sha256 == active_drift_state.observed_contract_ledger_sha256

        # Check drift state was cleared
        drift = load_drift_state(institution_id)
        assert drift.status == "CLEAR"

    def test_decide_proposal_block(self, institution_id, active_drift_state):
        """Block proposal leaves drift as ACTIVE."""
        # Save initial drift state
        save_drift_state(institution_id, active_drift_state)

        # Create proposal
        proposal, _, _ = create_drift_resolution_proposal(institution_id, active_drift_state)
        assert proposal is not None

        # Block proposal
        decided, error_code, error_msg = decide_proposal(
            institution_id,
            proposal.proposal_id,
            "block",
            "Blocked by test",
            "test-actor",
        )

        assert error_code is None
        assert decided is not None
        assert decided.status == "DECIDED"
        assert decided.decision == "block"

        # Check drift state is still ACTIVE
        drift = load_drift_state(institution_id)
        assert drift.status == "ACTIVE"

    def test_decide_proposal_not_found(self, institution_id):
        """Deciding nonexistent proposal fails."""
        decided, error_code, error_msg = decide_proposal(
            institution_id,
            "nonexistent-proposal-id",
            "accept",
            None,
            "test-actor",
        )

        assert decided is None
        assert error_code == EGE_PROPOSAL_NOT_FOUND

    def test_decide_proposal_already_decided(self, institution_id, active_drift_state):
        """Cannot decide already decided proposal."""
        save_drift_state(institution_id, active_drift_state)

        proposal, _, _ = create_drift_resolution_proposal(institution_id, active_drift_state)
        assert proposal is not None

        # First decision
        decide_proposal(institution_id, proposal.proposal_id, "accept", None, "actor1")

        # Second decision should fail
        decided, error_code, error_msg = decide_proposal(
            institution_id,
            proposal.proposal_id,
            "block",
            None,
            "actor2",
        )

        assert decided is None
        assert error_code == EGE_PROPOSAL_ALREADY_DECIDED

    def test_decide_proposal_invalid_decision(self, institution_id, active_drift_state):
        """Invalid decision value fails."""
        save_drift_state(institution_id, active_drift_state)

        proposal, _, _ = create_drift_resolution_proposal(institution_id, active_drift_state)
        assert proposal is not None

        decided, error_code, error_msg = decide_proposal(
            institution_id,
            proposal.proposal_id,
            "invalid-decision",
            None,
            "test-actor",
        )

        assert decided is None
        assert error_code == EGE_DECISION_INVALID

    def test_decide_proposal_emits_ledger_event(self, institution_id, active_drift_state):
        """Deciding proposal emits EGE_PROPOSAL_DECIDED event."""
        save_drift_state(institution_id, active_drift_state)

        proposal, _, _ = create_drift_resolution_proposal(institution_id, active_drift_state)
        decide_proposal(institution_id, proposal.proposal_id, "accept", "Test reason", "test-actor")

        ledger = get_ledger_for_institution(institution_id)
        if not ledger._path.exists():
            events = []
        else:
            with open(ledger._path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

        decided_events = [e for e in events if e.get("event_type") == "EGE_PROPOSAL_DECIDED"]
        assert len(decided_events) >= 1
        event = decided_events[-1]
        assert event["step"] == "EGE:proposal.decide"
        assert event["payload"]["decision"] == "accept"
        assert event["payload"]["reason"] == "Test reason"


class TestListProposals:
    """Test list_proposals function."""

    def test_list_empty(self, institution_id):
        """List returns empty for new institution."""
        proposals = list_proposals(institution_id)

        assert proposals == []

    def test_list_returns_proposals(self, institution_id, active_drift_state):
        """List returns created proposals."""
        save_drift_state(institution_id, active_drift_state)

        create_drift_resolution_proposal(institution_id, active_drift_state)
        create_drift_resolution_proposal(institution_id, active_drift_state)

        proposals = list_proposals(institution_id)

        assert len(proposals) == 2
        assert all(p.status == "OPEN" for p in proposals)

    def test_list_respects_limit(self, institution_id, active_drift_state):
        """List respects limit parameter."""
        save_drift_state(institution_id, active_drift_state)

        for _ in range(5):
            create_drift_resolution_proposal(institution_id, active_drift_state)

        proposals = list_proposals(institution_id, limit=3)

        assert len(proposals) == 3

    def test_list_includes_decided(self, institution_id, active_drift_state):
        """List includes decided proposals."""
        save_drift_state(institution_id, active_drift_state)

        proposal, _, _ = create_drift_resolution_proposal(institution_id, active_drift_state)
        decide_proposal(institution_id, proposal.proposal_id, "accept", None, "actor")

        proposals = list_proposals(institution_id)

        assert len(proposals) == 1
        assert proposals[0].status == "DECIDED"
        assert proposals[0].decision == "accept"


class TestLoadCurrentState:
    """Test load_current_state folding."""

    def test_folds_create_and_decide(self, institution_id, active_drift_state):
        """State correctly folds create and decide operations."""
        save_drift_state(institution_id, active_drift_state)

        proposal, _, _ = create_drift_resolution_proposal(institution_id, active_drift_state)
        decide_proposal(institution_id, proposal.proposal_id, "block", "Reason", "actor")

        states = load_current_state(institution_id)

        assert len(states) == 1
        assert proposal.proposal_id in states
        assert states[proposal.proposal_id].status == "DECIDED"
        assert states[proposal.proposal_id].decision == "block"
        assert states[proposal.proposal_id].reason == "Reason"

    def test_multiple_proposals_separate_states(self, institution_id, active_drift_state):
        """Multiple proposals have separate states."""
        save_drift_state(institution_id, active_drift_state)

        proposal1, _, _ = create_drift_resolution_proposal(institution_id, active_drift_state)
        proposal2, _, _ = create_drift_resolution_proposal(institution_id, active_drift_state)

        decide_proposal(institution_id, proposal1.proposal_id, "accept", None, "actor")

        states = load_current_state(institution_id)

        assert len(states) == 2
        assert states[proposal1.proposal_id].status == "DECIDED"
        assert states[proposal2.proposal_id].status == "OPEN"
