"""EGE Proposals Registry with append-only JSONL storage.

Implements drift resolution proposal workflow with:
- Append-only JSONL storage per institution
- Monotonic sequence numbers
- Folding state computation
- Ledger event emission
"""

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from engine.core.data_root import get_institution_root
from engine.core.ege import DriftState, check_drift, save_drift_state, load_drift_state
from engine.core.institution_config import (
    get_effective_config,
    save_active_config,
    invalidate_config_cache,
    HASH_PREFIX,
)
from engine.core.ledger import get_ledger_for_institution
from engine.core.errors import (
    EGE_NO_DRIFT_ACTIVE,
    EGE_PROPOSAL_NOT_FOUND,
    EGE_PROPOSAL_ALREADY_DECIDED,
    EGE_DECISION_INVALID,
    EGE_REGISTRY_UNAVAILABLE,
)


# Proposals file name
PROPOSALS_FILE = "ege_proposals.jsonl"

# Valid decision values
VALID_DECISIONS = {"accept", "block"}


@dataclass
class ProposalRecord:
    """A single proposal record (append-only log entry)."""

    seq: int  # Monotonic sequence number (per institution)
    proposal_id: str  # UUID of the proposal
    operation: str  # "create" or "decide"
    status: str  # "OPEN" or "DECIDED"
    created_at: str  # UTC ISO8601

    # From drift state at creation time
    expected_bundle_manifest_sha256: Optional[str] = None
    expected_contract_ledger_sha256: Optional[str] = None
    observed_bundle_manifest_sha256: Optional[str] = None
    observed_contract_ledger_sha256: Optional[str] = None

    # Decision fields (only for "decide" operations)
    decision: Optional[str] = None  # "accept" or "block"
    reason: Optional[str] = None
    decided_at: Optional[str] = None
    decider_actor_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProposalRecord":
        """Create from dictionary."""
        return cls(
            seq=data["seq"],
            proposal_id=data["proposal_id"],
            operation=data["operation"],
            status=data["status"],
            created_at=data["created_at"],
            expected_bundle_manifest_sha256=data.get("expected_bundle_manifest_sha256"),
            expected_contract_ledger_sha256=data.get("expected_contract_ledger_sha256"),
            observed_bundle_manifest_sha256=data.get("observed_bundle_manifest_sha256"),
            observed_contract_ledger_sha256=data.get("observed_contract_ledger_sha256"),
            decision=data.get("decision"),
            reason=data.get("reason"),
            decided_at=data.get("decided_at"),
            decider_actor_id=data.get("decider_actor_id"),
        )


@dataclass
class ProposalState:
    """Computed state of a single proposal (folded from records)."""

    proposal_id: str
    status: str  # "OPEN" or "DECIDED"
    created_at: str

    # From drift state
    expected_bundle_manifest_sha256: Optional[str] = None
    expected_contract_ledger_sha256: Optional[str] = None
    observed_bundle_manifest_sha256: Optional[str] = None
    observed_contract_ledger_sha256: Optional[str] = None

    # Decision (if decided)
    decision: Optional[str] = None
    reason: Optional[str] = None
    decided_at: Optional[str] = None
    decider_actor_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


def _get_proposals_path(institution_id: str) -> Path:
    """Get path to proposals file for institution."""
    return get_institution_root(institution_id) / PROPOSALS_FILE


def _now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# File locks per institution
_file_locks: Dict[str, Lock] = {}
_global_lock = Lock()


def _get_file_lock(institution_id: str) -> Lock:
    """Get or create file lock for institution."""
    with _global_lock:
        if institution_id not in _file_locks:
            _file_locks[institution_id] = Lock()
        return _file_locks[institution_id]


def _get_next_seq(institution_id: str) -> int:
    """Get next sequence number for proposals file."""
    proposals_path = _get_proposals_path(institution_id)

    if not proposals_path.exists():
        return 1

    try:
        count = 0
        with open(proposals_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count + 1
    except OSError:
        return 1


def load_records(institution_id: str) -> List[ProposalRecord]:
    """Load all records from institution's proposals file.

    Args:
        institution_id: Institution UUID.

    Returns:
        List of all ProposalRecord entries (chronological order).
    """
    proposals_path = _get_proposals_path(institution_id)

    if not proposals_path.exists():
        return []

    records = []
    with open(proposals_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    records.append(ProposalRecord.from_dict(data))
                except (json.JSONDecodeError, KeyError):
                    # Skip malformed records
                    continue

    return records


def load_current_state(institution_id: str) -> Dict[str, ProposalState]:
    """Compute current state by folding all records.

    Args:
        institution_id: Institution UUID.

    Returns:
        Dictionary mapping proposal_id to current ProposalState.
    """
    records = load_records(institution_id)

    states: Dict[str, ProposalState] = {}

    for record in records:
        proposal_id = record.proposal_id

        if record.operation == "create":
            states[proposal_id] = ProposalState(
                proposal_id=proposal_id,
                status=record.status,
                created_at=record.created_at,
                expected_bundle_manifest_sha256=record.expected_bundle_manifest_sha256,
                expected_contract_ledger_sha256=record.expected_contract_ledger_sha256,
                observed_bundle_manifest_sha256=record.observed_bundle_manifest_sha256,
                observed_contract_ledger_sha256=record.observed_contract_ledger_sha256,
            )
        elif record.operation == "decide" and proposal_id in states:
            states[proposal_id].status = "DECIDED"
            states[proposal_id].decision = record.decision
            states[proposal_id].reason = record.reason
            states[proposal_id].decided_at = record.decided_at
            states[proposal_id].decider_actor_id = record.decider_actor_id

    return states


def append_record(institution_id: str, record: ProposalRecord) -> None:
    """Append a record to the institution's proposals file.

    Args:
        institution_id: Institution UUID.
        record: ProposalRecord to append.
    """
    lock = _get_file_lock(institution_id)

    with lock:
        proposals_path = _get_proposals_path(institution_id)

        # Ensure directory exists
        proposals_path.parent.mkdir(parents=True, exist_ok=True)

        with open(proposals_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")


def _emit_proposal_event(
    institution_id: str,
    event_type: str,
    proposal_id: str,
    payload: Dict[str, Any],
) -> None:
    """Emit ledger event for proposal operation.

    Args:
        institution_id: Institution UUID.
        event_type: EGE_PROPOSAL_CREATED or EGE_PROPOSAL_DECIDED.
        proposal_id: Proposal UUID.
        payload: Event payload.
    """
    try:
        ledger = get_ledger_for_institution(institution_id)
        step = "EGE:proposal.create" if event_type == "EGE_PROPOSAL_CREATED" else "EGE:proposal.decide"

        ledger.append(
            event_type=event_type,
            tenant_id=institution_id,
            actor_id=payload.get("decider_actor_id", "SYSTEM"),
            actor_roles=["admin"],
            case_id=proposal_id,
            step=step,
            payload=payload,
        )
    except Exception:
        # Don't fail on ledger write errors
        pass


def create_drift_resolution_proposal(
    institution_id: str,
    drift_state: DriftState,
) -> Tuple[Optional[ProposalState], Optional[str], Optional[str]]:
    """Create a drift resolution proposal.

    Args:
        institution_id: Institution UUID.
        drift_state: Current drift state (must be ACTIVE).

    Returns:
        Tuple of (ProposalState, error_code, error_message).
        On success: (ProposalState, None, None)
        On failure: (None, error_code, error_message)
    """
    # Only allow if drift is ACTIVE
    if drift_state.status != "ACTIVE":
        return None, EGE_NO_DRIFT_ACTIVE, "Cannot create proposal: drift status is not ACTIVE"

    lock = _get_file_lock(institution_id)

    with lock:
        proposal_id = str(uuid.uuid4())
        seq = _get_next_seq(institution_id)
        now = _now_iso()

        record = ProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation="create",
            status="OPEN",
            created_at=now,
            expected_bundle_manifest_sha256=drift_state.expected_bundle_manifest_sha256,
            expected_contract_ledger_sha256=drift_state.expected_contract_ledger_sha256,
            observed_bundle_manifest_sha256=drift_state.observed_bundle_manifest_sha256,
            observed_contract_ledger_sha256=drift_state.observed_contract_ledger_sha256,
        )

        try:
            proposals_path = _get_proposals_path(institution_id)
            proposals_path.parent.mkdir(parents=True, exist_ok=True)

            with open(proposals_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except OSError as e:
            return None, EGE_REGISTRY_UNAVAILABLE, f"Failed to write proposal: {e}"

    # Emit ledger event
    _emit_proposal_event(
        institution_id=institution_id,
        event_type="EGE_PROPOSAL_CREATED",
        proposal_id=proposal_id,
        payload={
            "proposal_id": proposal_id,
            "status": "OPEN",
            "expected_bundle_manifest_sha256": drift_state.expected_bundle_manifest_sha256,
            "expected_contract_ledger_sha256": drift_state.expected_contract_ledger_sha256,
            "observed_bundle_manifest_sha256": drift_state.observed_bundle_manifest_sha256,
            "observed_contract_ledger_sha256": drift_state.observed_contract_ledger_sha256,
        },
    )

    # Return proposal state
    state = ProposalState(
        proposal_id=proposal_id,
        status="OPEN",
        created_at=now,
        expected_bundle_manifest_sha256=drift_state.expected_bundle_manifest_sha256,
        expected_contract_ledger_sha256=drift_state.expected_contract_ledger_sha256,
        observed_bundle_manifest_sha256=drift_state.observed_bundle_manifest_sha256,
        observed_contract_ledger_sha256=drift_state.observed_contract_ledger_sha256,
    )

    return state, None, None


def decide_proposal(
    institution_id: str,
    proposal_id: str,
    decision: str,
    reason: Optional[str],
    decider_actor_id: str,
) -> Tuple[Optional[ProposalState], Optional[str], Optional[str]]:
    """Decide on a proposal.

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID.
        decision: "accept" or "block".
        reason: Optional reason for decision.
        decider_actor_id: Actor making the decision.

    Returns:
        Tuple of (ProposalState, error_code, error_message).
        On success: (ProposalState, None, None)
        On failure: (None, error_code, error_message)

    Effects:
    - If accept: updates institution config with observed hashes, saves drift state as CLEAR.
    - If block: leaves drift state as ACTIVE.
    """
    # Validate decision
    if decision not in VALID_DECISIONS:
        return None, EGE_DECISION_INVALID, f"Decision must be one of: {sorted(VALID_DECISIONS)}"

    lock = _get_file_lock(institution_id)

    with lock:
        # Load current state
        states = load_current_state(institution_id)

        if proposal_id not in states:
            return None, EGE_PROPOSAL_NOT_FOUND, f"Proposal '{proposal_id}' not found"

        proposal = states[proposal_id]

        if proposal.status == "DECIDED":
            return None, EGE_PROPOSAL_ALREADY_DECIDED, f"Proposal '{proposal_id}' is already decided"

        now = _now_iso()
        seq = _get_next_seq(institution_id)

        # Create decide record
        record = ProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation="decide",
            status="DECIDED",
            created_at=proposal.created_at,
            expected_bundle_manifest_sha256=proposal.expected_bundle_manifest_sha256,
            expected_contract_ledger_sha256=proposal.expected_contract_ledger_sha256,
            observed_bundle_manifest_sha256=proposal.observed_bundle_manifest_sha256,
            observed_contract_ledger_sha256=proposal.observed_contract_ledger_sha256,
            decision=decision,
            reason=reason,
            decided_at=now,
            decider_actor_id=decider_actor_id,
        )

        try:
            proposals_path = _get_proposals_path(institution_id)
            with open(proposals_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except OSError as e:
            return None, EGE_REGISTRY_UNAVAILABLE, f"Failed to write decision: {e}"

        # Update proposal state
        proposal.status = "DECIDED"
        proposal.decision = decision
        proposal.reason = reason
        proposal.decided_at = now
        proposal.decider_actor_id = decider_actor_id

    # Handle decision effects
    if decision == "accept":
        _handle_accept_decision(institution_id, proposal, decider_actor_id)
    # If block: leave drift state as ACTIVE (no changes needed)

    # Emit ledger event
    _emit_proposal_event(
        institution_id=institution_id,
        event_type="EGE_PROPOSAL_DECIDED",
        proposal_id=proposal_id,
        payload={
            "proposal_id": proposal_id,
            "decision": decision,
            "reason": reason,
            "decider_actor_id": decider_actor_id,
        },
    )

    return proposal, None, None


def _handle_accept_decision(
    institution_id: str,
    proposal: ProposalState,
    actor_id: str,
) -> None:
    """Handle accept decision: update config and drift state.

    Args:
        institution_id: Institution UUID.
        proposal: Proposal that was accepted.
        actor_id: Actor who accepted.
    """
    # Get current config and update pinned hashes to observed values
    config = get_effective_config(institution_id)

    config_dict = config.to_dict()
    config_dict["pinned_bundle_manifest_sha256"] = proposal.observed_bundle_manifest_sha256
    config_dict["pinned_contract_ledger_sha256"] = proposal.observed_contract_ledger_sha256

    # Save updated config
    save_active_config(institution_id, config_dict, actor_id)
    invalidate_config_cache(institution_id)

    # Update drift state to CLEAR
    drift_state = load_drift_state(institution_id)
    if drift_state:
        drift_state.status = "CLEAR"
        drift_state.bundle_manifest_mismatch = False
        drift_state.contract_ledger_mismatch = False
        drift_state.expected_bundle_manifest_sha256 = proposal.observed_bundle_manifest_sha256
        drift_state.expected_contract_ledger_sha256 = proposal.observed_contract_ledger_sha256
        drift_state.checked_at = _now_iso()
        save_drift_state(institution_id, drift_state)


def list_proposals(
    institution_id: str,
    limit: int = 50,
) -> List[ProposalState]:
    """List proposals for institution.

    Args:
        institution_id: Institution UUID.
        limit: Maximum number of proposals to return.

    Returns:
        List of ProposalState (most recent first).
    """
    states = load_current_state(institution_id)

    # Sort by created_at descending
    proposals = sorted(
        states.values(),
        key=lambda p: p.created_at,
        reverse=True,
    )

    return proposals[:limit]


def reset_proposals_registry() -> None:
    """Reset file locks (for testing)."""
    global _file_locks
    with _global_lock:
        _file_locks.clear()
