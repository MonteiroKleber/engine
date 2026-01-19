"""Governed Mandates - Runtime mandate override via EGE-style proposals.

Implements mandate governance workflow with:
- Append-only JSONL storage per institution/dept
- Proposal workflow: propose → decide → apply
- Runtime override: governed mandates take precedence over bundle
- Ledger event emission for all operations

Etapa 2.8: AXIOM MVP
"""

import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from engine.core.data_root import get_institution_root
from engine.core.ledger import get_ledger_for_institution
from engine.core.mandates import (
    MandateDef,
    Mandate,
    MandateLimit,
    parse_mandates_data,
    get_mandates as get_bundle_mandates,
    MandateSchemaError,
)
from engine.core.errors import (
    MANDATE_PROPOSAL_NOT_FOUND,
    MANDATE_PROPOSAL_ALREADY_DECIDED,
    MANDATE_PROPOSAL_INVALID,
    MANDATE_NOT_FOUND_FOR_UPDATE,
    MANDATE_ALREADY_EXISTS,
    GOVERNED_MANDATES_UNAVAILABLE,
)


# Storage file names
PROPOSALS_FILE = "mandate_proposals.jsonl"
MANDATES_FILE = "governed_mandates.jsonl"
STATE_FILE = "governed_mandates_state.json"

# Valid operations
VALID_OPERATIONS = frozenset({"create", "update", "revoke"})

# Valid decisions
VALID_DECISIONS = frozenset({"approve", "reject"})

# Ledger event types
MANDATE_PROPOSED = "MANDATE_PROPOSED"
MANDATE_APPROVED = "MANDATE_APPROVED"
MANDATE_REJECTED = "MANDATE_REJECTED"
MANDATE_APPLIED = "MANDATE_APPLIED"
MANDATE_REVOKED = "MANDATE_REVOKED"


@dataclass
class MandateProposalRecord:
    """A single mandate proposal record (append-only log entry)."""

    seq: int  # Monotonic sequence number
    proposal_id: str  # UUID
    operation_type: str  # "create" or "decide"
    status: str  # "OPEN" or "DECIDED"
    created_at: str  # UTC ISO8601

    # Proposal details
    mandate_operation: str  # "create", "update", or "revoke"
    dept_id: Optional[str]  # None for single-mode
    mandate_id: str  # Target mandate ID
    mandate_data: Optional[Dict[str, Any]]  # Full mandate data (for create/update)
    reason: str  # Reason for proposal

    # Creator
    created_by: str

    # Decision fields (only for "decide" operations)
    decision: Optional[str] = None  # "approve" or "reject"
    decision_reason: Optional[str] = None
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MandateProposalRecord":
        """Create from dictionary."""
        return cls(
            seq=data["seq"],
            proposal_id=data["proposal_id"],
            operation_type=data["operation_type"],
            status=data["status"],
            created_at=data["created_at"],
            mandate_operation=data["mandate_operation"],
            dept_id=data.get("dept_id"),
            mandate_id=data["mandate_id"],
            mandate_data=data.get("mandate_data"),
            reason=data.get("reason", ""),
            created_by=data.get("created_by", ""),
            decision=data.get("decision"),
            decision_reason=data.get("decision_reason"),
            decided_at=data.get("decided_at"),
            decided_by=data.get("decided_by"),
        )


@dataclass
class MandateProposalState:
    """Computed state of a single proposal (folded from records)."""

    proposal_id: str
    status: str  # "OPEN" or "DECIDED"
    created_at: str

    mandate_operation: str
    dept_id: Optional[str]
    mandate_id: str
    mandate_data: Optional[Dict[str, Any]]
    reason: str
    created_by: str

    # Decision (if decided)
    decision: Optional[str] = None
    decision_reason: Optional[str] = None
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class GovernedMandateRecord:
    """A governed mandate record (append-only log entry)."""

    seq: int
    mandate_id: str
    action: str  # "create", "update", "revoke"
    dept_id: Optional[str]
    mandate_data: Optional[Dict[str, Any]]  # None for revoke
    applied_at: str
    applied_by: str
    proposal_id: str  # Source proposal

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GovernedMandateRecord":
        """Create from dictionary."""
        return cls(
            seq=data["seq"],
            mandate_id=data["mandate_id"],
            action=data["action"],
            dept_id=data.get("dept_id"),
            mandate_data=data.get("mandate_data"),
            applied_at=data["applied_at"],
            applied_by=data.get("applied_by", ""),
            proposal_id=data.get("proposal_id", ""),
        )


@dataclass
class GovernedMandatesState:
    """Current state of governed mandates for an institution/dept."""

    schema_version: str = "1.0"
    updated_at: Optional[str] = None
    mandates: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # mandate_id -> mandate_data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "mandates": self.mandates,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GovernedMandatesState":
        """Create from dictionary."""
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            updated_at=data.get("updated_at"),
            mandates=data.get("mandates", {}),
        )


def _now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# File locks per institution
_file_locks: Dict[str, Lock] = {}
_global_lock = Lock()


def _get_file_lock(institution_id: str, dept_id: Optional[str] = None) -> Lock:
    """Get or create file lock for institution/dept."""
    key = f"{institution_id}:{dept_id or '_single'}"
    with _global_lock:
        if key not in _file_locks:
            _file_locks[key] = Lock()
        return _file_locks[key]


def _get_governed_dir(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get governed mandates directory path."""
    inst_root = get_institution_root(institution_id)
    if dept_id:
        return inst_root / "depts" / dept_id / "governed_mandates"
    return inst_root / "governed_mandates"


def _get_proposals_path(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get path to proposals file."""
    return _get_governed_dir(institution_id, dept_id) / PROPOSALS_FILE


def _get_mandates_path(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get path to mandates history file."""
    return _get_governed_dir(institution_id, dept_id) / MANDATES_FILE


def _get_state_path(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get path to state file."""
    return _get_governed_dir(institution_id, dept_id) / STATE_FILE


def _get_next_seq(path: Path) -> int:
    """Get next sequence number for a JSONL file."""
    if not path.exists():
        return 1
    try:
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count + 1
    except OSError:
        return 1


def _emit_ledger_event(
    institution_id: str,
    event_type: str,
    case_id: str,
    step: str,
    payload: Dict[str, Any],
    actor_id: str,
    dept_id: Optional[str] = None,
) -> None:
    """Emit ledger event for governed mandate operation."""
    try:
        ledger = get_ledger_for_institution(institution_id)
        ledger.append(
            event_type=event_type,
            tenant_id=institution_id,
            actor_id=actor_id,
            actor_roles=["admin"],
            case_id=case_id,
            step=step,
            payload=payload,
            dept_id=dept_id,
        )
    except Exception:
        # Don't fail on ledger write errors
        pass


def load_proposal_records(
    institution_id: str, dept_id: Optional[str] = None
) -> List[MandateProposalRecord]:
    """Load all proposal records."""
    proposals_path = _get_proposals_path(institution_id, dept_id)
    if not proposals_path.exists():
        return []

    records = []
    with open(proposals_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    records.append(MandateProposalRecord.from_dict(data))
                except (json.JSONDecodeError, KeyError):
                    continue
    return records


def load_proposal_state(
    institution_id: str, dept_id: Optional[str] = None
) -> Dict[str, MandateProposalState]:
    """Compute current proposal state by folding all records."""
    records = load_proposal_records(institution_id, dept_id)
    states: Dict[str, MandateProposalState] = {}

    for record in records:
        proposal_id = record.proposal_id

        if record.operation_type == "create":
            states[proposal_id] = MandateProposalState(
                proposal_id=proposal_id,
                status=record.status,
                created_at=record.created_at,
                mandate_operation=record.mandate_operation,
                dept_id=record.dept_id,
                mandate_id=record.mandate_id,
                mandate_data=record.mandate_data,
                reason=record.reason,
                created_by=record.created_by,
            )
        elif record.operation_type == "decide" and proposal_id in states:
            states[proposal_id].status = "DECIDED"
            states[proposal_id].decision = record.decision
            states[proposal_id].decision_reason = record.decision_reason
            states[proposal_id].decided_at = record.decided_at
            states[proposal_id].decided_by = record.decided_by

    return states


def load_governed_state(
    institution_id: str, dept_id: Optional[str] = None
) -> GovernedMandatesState:
    """Load current governed mandates state."""
    state_path = _get_state_path(institution_id, dept_id)
    if not state_path.exists():
        return GovernedMandatesState()

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return GovernedMandatesState.from_dict(data)
    except (json.JSONDecodeError, IOError):
        return GovernedMandatesState()


def _save_governed_state(
    institution_id: str,
    dept_id: Optional[str],
    state: GovernedMandatesState,
) -> None:
    """Save governed mandates state."""
    gov_dir = _get_governed_dir(institution_id, dept_id)
    gov_dir.mkdir(parents=True, exist_ok=True)
    state_path = _get_state_path(institution_id, dept_id)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, sort_keys=True)


def _validate_mandate_data(mandate_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate mandate data against schema.

    Returns:
        Tuple of (is_valid, error_message).
    """
    # Wrap in mandates.json format for validation
    wrapped = {
        "mandate_schema_version": "1.0",
        "mandates": [mandate_data],
    }
    try:
        parse_mandates_data(wrapped)
        return True, None
    except MandateSchemaError as e:
        return False, e.message


def propose_mandate_change(
    institution_id: str,
    operation: str,
    mandate_id: str,
    mandate_data: Optional[Dict[str, Any]],
    reason: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[MandateProposalState], Optional[str], Optional[str]]:
    """Create a mandate change proposal.

    Args:
        institution_id: Institution UUID.
        operation: "create", "update", or "revoke".
        mandate_id: Target mandate ID.
        mandate_data: Full mandate data (required for create/update, None for revoke).
        reason: Reason for the proposal.
        actor_id: Actor creating the proposal.
        dept_id: Optional department ID.

    Returns:
        Tuple of (proposal_state, error_code, error_message).
    """
    # Validate operation
    if operation not in VALID_OPERATIONS:
        return None, MANDATE_PROPOSAL_INVALID, f"Invalid operation: {operation}. Must be one of: {sorted(VALID_OPERATIONS)}"

    # Validate mandate_data for create/update
    if operation in ("create", "update"):
        if not mandate_data:
            return None, MANDATE_PROPOSAL_INVALID, f"mandate_data is required for {operation} operation"

        # Ensure mandate_id matches
        if mandate_data.get("mandate_id") != mandate_id:
            mandate_data = dict(mandate_data)
            mandate_data["mandate_id"] = mandate_id

        # Validate schema
        is_valid, error_msg = _validate_mandate_data(mandate_data)
        if not is_valid:
            return None, MANDATE_PROPOSAL_INVALID, f"Invalid mandate data: {error_msg}"

    # For revoke, mandate_data should be None
    if operation == "revoke":
        mandate_data = None

    lock = _get_file_lock(institution_id, dept_id)

    with lock:
        # Load current state to check for conflicts
        governed_state = load_governed_state(institution_id, dept_id)

        if operation == "create":
            # Check mandate doesn't already exist
            if mandate_id in governed_state.mandates:
                return None, MANDATE_ALREADY_EXISTS, f"Mandate '{mandate_id}' already exists in governed mandates"

        if operation in ("update", "revoke"):
            # Check mandate exists
            if mandate_id not in governed_state.mandates:
                # Also check bundle mandates
                bundle_def = get_bundle_mandates(dept_id)
                bundle_has_mandate = False
                if bundle_def:
                    for m in bundle_def.mandates:
                        if m.mandate_id == mandate_id:
                            bundle_has_mandate = True
                            break

                if not bundle_has_mandate:
                    return None, MANDATE_NOT_FOUND_FOR_UPDATE, f"Mandate '{mandate_id}' not found for {operation}"

        # Create proposal
        proposal_id = str(uuid.uuid4())
        now = _now_iso()
        proposals_path = _get_proposals_path(institution_id, dept_id)
        seq = _get_next_seq(proposals_path)

        record = MandateProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation_type="create",
            status="OPEN",
            created_at=now,
            mandate_operation=operation,
            dept_id=dept_id,
            mandate_id=mandate_id,
            mandate_data=mandate_data,
            reason=reason,
            created_by=actor_id,
        )

        try:
            gov_dir = _get_governed_dir(institution_id, dept_id)
            gov_dir.mkdir(parents=True, exist_ok=True)
            with open(proposals_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        except OSError as e:
            return None, GOVERNED_MANDATES_UNAVAILABLE, f"Failed to write proposal: {e}"

    # Emit ledger event
    _emit_ledger_event(
        institution_id=institution_id,
        event_type=MANDATE_PROPOSED,
        case_id=proposal_id,
        step=f"GOVERNED_MANDATE:propose.{operation}",
        payload={
            "proposal_id": proposal_id,
            "operation": operation,
            "mandate_id": mandate_id,
            "mandate_data": mandate_data,
            "reason": reason,
        },
        actor_id=actor_id,
        dept_id=dept_id,
    )

    # Return proposal state
    state = MandateProposalState(
        proposal_id=proposal_id,
        status="OPEN",
        created_at=now,
        mandate_operation=operation,
        dept_id=dept_id,
        mandate_id=mandate_id,
        mandate_data=mandate_data,
        reason=reason,
        created_by=actor_id,
    )

    return state, None, None


def decide_mandate_proposal(
    institution_id: str,
    proposal_id: str,
    decision: str,
    reason: Optional[str],
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[MandateProposalState], Optional[str], Optional[str]]:
    """Decide on a mandate proposal.

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID.
        decision: "approve" or "reject".
        reason: Optional reason for decision.
        actor_id: Actor making the decision.
        dept_id: Optional department ID.

    Returns:
        Tuple of (proposal_state, error_code, error_message).
    """
    # Validate decision
    if decision not in VALID_DECISIONS:
        return None, MANDATE_PROPOSAL_INVALID, f"Invalid decision: {decision}. Must be one of: {sorted(VALID_DECISIONS)}"

    lock = _get_file_lock(institution_id, dept_id)

    with lock:
        # Load current state
        states = load_proposal_state(institution_id, dept_id)

        if proposal_id not in states:
            return None, MANDATE_PROPOSAL_NOT_FOUND, f"Proposal '{proposal_id}' not found"

        proposal = states[proposal_id]

        if proposal.status == "DECIDED":
            return None, MANDATE_PROPOSAL_ALREADY_DECIDED, f"Proposal '{proposal_id}' is already decided"

        now = _now_iso()
        proposals_path = _get_proposals_path(institution_id, dept_id)
        seq = _get_next_seq(proposals_path)

        # Create decide record
        record = MandateProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation_type="decide",
            status="DECIDED",
            created_at=proposal.created_at,
            mandate_operation=proposal.mandate_operation,
            dept_id=proposal.dept_id,
            mandate_id=proposal.mandate_id,
            mandate_data=proposal.mandate_data,
            reason=proposal.reason,
            created_by=proposal.created_by,
            decision=decision,
            decision_reason=reason,
            decided_at=now,
            decided_by=actor_id,
        )

        try:
            with open(proposals_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        except OSError as e:
            return None, GOVERNED_MANDATES_UNAVAILABLE, f"Failed to write decision: {e}"

        # Update proposal state
        proposal.status = "DECIDED"
        proposal.decision = decision
        proposal.decision_reason = reason
        proposal.decided_at = now
        proposal.decided_by = actor_id

    # Emit ledger event
    event_type = MANDATE_APPROVED if decision == "approve" else MANDATE_REJECTED
    _emit_ledger_event(
        institution_id=institution_id,
        event_type=event_type,
        case_id=proposal_id,
        step=f"GOVERNED_MANDATE:decide.{decision}",
        payload={
            "proposal_id": proposal_id,
            "decision": decision,
            "reason": reason,
            "mandate_id": proposal.mandate_id,
            "operation": proposal.mandate_operation,
        },
        actor_id=actor_id,
        dept_id=dept_id,
    )

    # If approved, apply the change
    if decision == "approve":
        apply_result = apply_mandate_change(institution_id, proposal_id, actor_id, dept_id)
        if apply_result[1]:
            # Apply failed - still return the decided proposal
            pass

    return proposal, None, None


def apply_mandate_change(
    institution_id: str,
    proposal_id: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Apply an approved mandate change.

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID (must be approved).
        actor_id: Actor applying the change.
        dept_id: Optional department ID.

    Returns:
        Tuple of (success, error_code, error_message).
    """
    lock = _get_file_lock(institution_id, dept_id)

    with lock:
        # Load proposal
        states = load_proposal_state(institution_id, dept_id)

        if proposal_id not in states:
            return False, MANDATE_PROPOSAL_NOT_FOUND, f"Proposal '{proposal_id}' not found"

        proposal = states[proposal_id]

        if proposal.status != "DECIDED" or proposal.decision != "approve":
            return False, MANDATE_PROPOSAL_INVALID, f"Proposal '{proposal_id}' is not approved"

        # Load current governed state
        governed_state = load_governed_state(institution_id, dept_id)
        now = _now_iso()

        # Apply the change
        operation = proposal.mandate_operation
        mandate_id = proposal.mandate_id

        if operation == "create":
            governed_state.mandates[mandate_id] = proposal.mandate_data
        elif operation == "update":
            governed_state.mandates[mandate_id] = proposal.mandate_data
        elif operation == "revoke":
            governed_state.mandates.pop(mandate_id, None)

        governed_state.updated_at = now

        # Append to mandates history
        mandates_path = _get_mandates_path(institution_id, dept_id)
        seq = _get_next_seq(mandates_path)

        mandate_record = GovernedMandateRecord(
            seq=seq,
            mandate_id=mandate_id,
            action=operation,
            dept_id=dept_id,
            mandate_data=proposal.mandate_data,
            applied_at=now,
            applied_by=actor_id,
            proposal_id=proposal_id,
        )

        try:
            gov_dir = _get_governed_dir(institution_id, dept_id)
            gov_dir.mkdir(parents=True, exist_ok=True)
            with open(mandates_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(mandate_record.to_dict(), sort_keys=True) + "\n")

            # Save state
            _save_governed_state(institution_id, dept_id, governed_state)
        except OSError as e:
            return False, GOVERNED_MANDATES_UNAVAILABLE, f"Failed to apply mandate: {e}"

    # Emit ledger event
    event_type = MANDATE_REVOKED if operation == "revoke" else MANDATE_APPLIED
    _emit_ledger_event(
        institution_id=institution_id,
        event_type=event_type,
        case_id=proposal_id,
        step=f"GOVERNED_MANDATE:apply.{operation}",
        payload={
            "proposal_id": proposal_id,
            "mandate_id": mandate_id,
            "operation": operation,
            "mandate_data": proposal.mandate_data,
        },
        actor_id=actor_id,
        dept_id=dept_id,
    )

    # Invalidate effective mandates cache
    invalidate_effective_mandates_cache(institution_id, dept_id)

    return True, None, None


# Effective mandates cache
_effective_cache: Dict[str, Tuple[MandateDef, str]] = {}  # key -> (mandate_def, updated_at)
_cache_lock = Lock()


def invalidate_effective_mandates_cache(
    institution_id: str, dept_id: Optional[str] = None
) -> None:
    """Invalidate effective mandates cache for institution/dept."""
    key = f"{institution_id}:{dept_id or '_single'}"
    with _cache_lock:
        _effective_cache.pop(key, None)


def invalidate_all_mandates_cache() -> None:
    """Invalidate all effective mandates cache (for testing)."""
    with _cache_lock:
        _effective_cache.clear()


def get_effective_mandates(
    institution_id: str, dept_id: Optional[str] = None
) -> Optional[MandateDef]:
    """Get effective mandates for institution/dept.

    Precedence:
    1. Governed mandates (institutional override)
    2. Bundle mandates (fallback)

    Governed mandates override bundle mandates by mandate_id.
    Revoked mandates are removed entirely.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        MandateDef with effective mandates, or None if no mandates exist.
    """
    key = f"{institution_id}:{dept_id or '_single'}"

    # Check cache
    with _cache_lock:
        if key in _effective_cache:
            cached_def, cached_updated = _effective_cache[key]
            # Check if governed state has been updated
            governed_state = load_governed_state(institution_id, dept_id)
            if governed_state.updated_at == cached_updated:
                return cached_def

    # Load governed mandates state
    governed_state = load_governed_state(institution_id, dept_id)

    # Load bundle mandates
    bundle_def = get_bundle_mandates(dept_id)

    # If neither exists, return None
    if not governed_state.mandates and bundle_def is None:
        return None

    # Build effective mandates list
    effective_mandates: Dict[str, Mandate] = {}

    # First, add bundle mandates
    if bundle_def:
        for mandate in bundle_def.mandates:
            effective_mandates[mandate.mandate_id] = mandate

    # Then, apply governed mandates (override/create/revoke)
    for mandate_id, mandate_data in governed_state.mandates.items():
        if mandate_data is None:
            # Revoked - remove from effective
            effective_mandates.pop(mandate_id, None)
        else:
            # Create/update - parse and add
            wrapped = {
                "mandate_schema_version": "1.0",
                "mandates": [mandate_data],
            }
            try:
                parsed = parse_mandates_data(wrapped)
                if parsed.mandates:
                    effective_mandates[mandate_id] = parsed.mandates[0]
            except MandateSchemaError:
                # Invalid governed mandate - skip (should not happen if validation is correct)
                pass

    # If no effective mandates, return None (allow all)
    if not effective_mandates:
        # But if bundle_def was loaded, we should return empty MandateDef
        # to enforce "no execution outside mandate" semantics
        if bundle_def is not None or governed_state.mandates:
            result = MandateDef(mandates=[])
        else:
            result = None
    else:
        result = MandateDef(mandates=list(effective_mandates.values()))

    # Update cache
    with _cache_lock:
        _effective_cache[key] = (result, governed_state.updated_at)

    return result


def list_mandate_proposals(
    institution_id: str,
    dept_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
) -> List[MandateProposalState]:
    """List mandate proposals for institution.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        status_filter: Optional filter by status ("OPEN" or "DECIDED").
        limit: Maximum number of proposals to return.

    Returns:
        List of MandateProposalState (most recent first).
    """
    states = load_proposal_state(institution_id, dept_id)

    # Filter by status if specified
    proposals = list(states.values())
    if status_filter:
        proposals = [p for p in proposals if p.status == status_filter]

    # Sort by created_at descending
    proposals.sort(key=lambda p: p.created_at, reverse=True)

    return proposals[:limit]


def list_governed_mandates(
    institution_id: str, dept_id: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """List current governed mandates.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        Dictionary mapping mandate_id to mandate_data.
    """
    state = load_governed_state(institution_id, dept_id)
    return state.mandates


def reset_governed_mandates_registry() -> None:
    """Reset file locks and cache (for testing)."""
    global _file_locks, _effective_cache
    with _global_lock:
        _file_locks.clear()
    with _cache_lock:
        _effective_cache.clear()
