"""Governed Autonomy - Runtime autonomy override via EGE-style proposals.

Implements autonomy governance workflow with:
- Append-only JSONL storage per institution/dept
- Proposal workflow: propose → decide → apply
- Runtime override: governed autonomy takes precedence over bundle
- Ledger event emission for all operations

Etapa 4.4: Policies + Autonomy Governance UI
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
from engine.core.autonomy import (
    AutonomyDef,
    AutonomyRule,
    parse_autonomy_data,
    get_autonomy_for_dept as get_bundle_autonomy,
    AutonomySchemaError,
    MIN_LEVEL,
    MAX_LEVEL,
)
from engine.core.errors import (
    AUTONOMY_PROPOSAL_NOT_FOUND,
    AUTONOMY_PROPOSAL_ALREADY_DECIDED,
    AUTONOMY_PROPOSAL_INVALID,
    AUTONOMY_NOT_FOUND_FOR_UPDATE,
    GOVERNED_AUTONOMY_UNAVAILABLE,
)


# Storage file names
PROPOSALS_FILE = "autonomy_proposals.jsonl"
AUTONOMY_FILE = "governed_autonomy.jsonl"
STATE_FILE = "governed_autonomy_state.json"

# Valid operations
VALID_OPERATIONS = frozenset({"update_level", "create_rule", "update_rule", "revoke_rule"})

# Valid decisions
VALID_DECISIONS = frozenset({"approve", "reject"})

# Ledger event types
AUTONOMY_PROPOSED = "AUTONOMY_PROPOSED"
AUTONOMY_GOV_APPROVED = "AUTONOMY_GOV_APPROVED"
AUTONOMY_GOV_REJECTED = "AUTONOMY_GOV_REJECTED"
AUTONOMY_GOV_APPLIED = "AUTONOMY_GOV_APPLIED"
AUTONOMY_GOV_REVOKED = "AUTONOMY_GOV_REVOKED"


@dataclass
class AutonomyProposalRecord:
    """A single autonomy proposal record (append-only log entry)."""

    seq: int  # Monotonic sequence number
    proposal_id: str  # UUID
    operation_type: str  # "create" or "decide"
    status: str  # "OPEN" or "DECIDED"
    created_at: str  # UTC ISO8601

    # Proposal details
    autonomy_operation: str  # "update_level", "create_rule", "update_rule", "revoke_rule"
    dept_id: Optional[str]  # None for single-mode
    rule_id: Optional[str]  # Target rule ID (None for update_level)
    autonomy_data: Optional[Dict[str, Any]]  # Autonomy data
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
    def from_dict(cls, data: Dict[str, Any]) -> "AutonomyProposalRecord":
        """Create from dictionary."""
        return cls(
            seq=data["seq"],
            proposal_id=data["proposal_id"],
            operation_type=data["operation_type"],
            status=data["status"],
            created_at=data["created_at"],
            autonomy_operation=data["autonomy_operation"],
            dept_id=data.get("dept_id"),
            rule_id=data.get("rule_id"),
            autonomy_data=data.get("autonomy_data"),
            reason=data.get("reason", ""),
            created_by=data.get("created_by", ""),
            decision=data.get("decision"),
            decision_reason=data.get("decision_reason"),
            decided_at=data.get("decided_at"),
            decided_by=data.get("decided_by"),
        )


@dataclass
class AutonomyProposalState:
    """Computed state of a single proposal (folded from records)."""

    proposal_id: str
    status: str  # "OPEN" or "DECIDED"
    created_at: str

    autonomy_operation: str
    dept_id: Optional[str]
    rule_id: Optional[str]
    autonomy_data: Optional[Dict[str, Any]]
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
class GovernedAutonomyRecord:
    """A governed autonomy record (append-only log entry)."""

    seq: int
    rule_id: Optional[str]
    action: str  # "update_level", "create_rule", "update_rule", "revoke_rule"
    dept_id: Optional[str]
    autonomy_data: Optional[Dict[str, Any]]
    applied_at: str
    applied_by: str
    proposal_id: str  # Source proposal

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GovernedAutonomyRecord":
        """Create from dictionary."""
        return cls(
            seq=data["seq"],
            rule_id=data.get("rule_id"),
            action=data["action"],
            dept_id=data.get("dept_id"),
            autonomy_data=data.get("autonomy_data"),
            applied_at=data["applied_at"],
            applied_by=data.get("applied_by", ""),
            proposal_id=data.get("proposal_id", ""),
        )


@dataclass
class GovernedAutonomyState:
    """Current state of governed autonomy for an institution/dept."""

    schema_version: str = "1.0"
    updated_at: Optional[str] = None
    current_level: Optional[int] = None  # None means use bundle default
    rules: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # rule_id -> rule_data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "current_level": self.current_level,
            "rules": self.rules,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GovernedAutonomyState":
        """Create from dictionary."""
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            updated_at=data.get("updated_at"),
            current_level=data.get("current_level"),
            rules=data.get("rules", {}),
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
    """Get governed autonomy directory path."""
    inst_root = get_institution_root(institution_id)
    if dept_id:
        return inst_root / "depts" / dept_id / "governed_autonomy"
    return inst_root / "governed_autonomy"


def _get_proposals_path(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get path to proposals file."""
    return _get_governed_dir(institution_id, dept_id) / PROPOSALS_FILE


def _get_autonomy_path(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get path to autonomy history file."""
    return _get_governed_dir(institution_id, dept_id) / AUTONOMY_FILE


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
    """Emit ledger event for governed autonomy operation."""
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
) -> List[AutonomyProposalRecord]:
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
                    records.append(AutonomyProposalRecord.from_dict(data))
                except (json.JSONDecodeError, KeyError):
                    continue
    return records


def load_proposal_state(
    institution_id: str, dept_id: Optional[str] = None
) -> Dict[str, AutonomyProposalState]:
    """Compute current proposal state by folding all records."""
    records = load_proposal_records(institution_id, dept_id)
    states: Dict[str, AutonomyProposalState] = {}

    for record in records:
        proposal_id = record.proposal_id

        if record.operation_type == "create":
            states[proposal_id] = AutonomyProposalState(
                proposal_id=proposal_id,
                status=record.status,
                created_at=record.created_at,
                autonomy_operation=record.autonomy_operation,
                dept_id=record.dept_id,
                rule_id=record.rule_id,
                autonomy_data=record.autonomy_data,
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
) -> GovernedAutonomyState:
    """Load current governed autonomy state."""
    state_path = _get_state_path(institution_id, dept_id)
    if not state_path.exists():
        return GovernedAutonomyState()

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return GovernedAutonomyState.from_dict(data)
    except (json.JSONDecodeError, IOError):
        return GovernedAutonomyState()


def _save_governed_state(
    institution_id: str,
    dept_id: Optional[str],
    state: GovernedAutonomyState,
) -> None:
    """Save governed autonomy state."""
    gov_dir = _get_governed_dir(institution_id, dept_id)
    gov_dir.mkdir(parents=True, exist_ok=True)
    state_path = _get_state_path(institution_id, dept_id)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, sort_keys=True)


def _validate_autonomy_level(level: Any) -> Tuple[bool, Optional[str]]:
    """Validate autonomy level.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not isinstance(level, int):
        return False, f"current_level must be an integer, got {type(level).__name__}"
    if level < MIN_LEVEL or level > MAX_LEVEL:
        return False, f"current_level must be in range {MIN_LEVEL}..{MAX_LEVEL}, got {level}"
    return True, None


def _validate_autonomy_rule(rule_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate autonomy rule data.

    Returns:
        Tuple of (is_valid, error_message).
    """
    # Wrap in autonomy.json format for validation
    wrapped = {
        "autonomy_schema_version": "1.0",
        "current_level": 0,
        "rules": [rule_data],
    }
    try:
        parse_autonomy_data(wrapped)
        return True, None
    except AutonomySchemaError as e:
        return False, e.message


def propose_autonomy_change(
    institution_id: str,
    operation: str,
    rule_id: Optional[str],
    autonomy_data: Dict[str, Any],
    reason: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[AutonomyProposalState], Optional[str], Optional[str]]:
    """Create an autonomy change proposal.

    Args:
        institution_id: Institution UUID.
        operation: "update_level", "create_rule", "update_rule", or "revoke_rule".
        rule_id: Target rule ID (required for rule operations, None for update_level).
        autonomy_data: Autonomy data (current_level for update_level, rule data for rule ops).
        reason: Reason for the proposal.
        actor_id: Actor creating the proposal.
        dept_id: Optional department ID.

    Returns:
        Tuple of (proposal_state, error_code, error_message).
    """
    # Validate operation
    if operation not in VALID_OPERATIONS:
        return None, AUTONOMY_PROPOSAL_INVALID, f"Invalid operation: {operation}. Must be one of: {sorted(VALID_OPERATIONS)}"

    # Validate based on operation type
    if operation == "update_level":
        if "current_level" not in autonomy_data:
            return None, AUTONOMY_PROPOSAL_INVALID, "autonomy_data must contain 'current_level' for update_level operation"
        is_valid, error_msg = _validate_autonomy_level(autonomy_data["current_level"])
        if not is_valid:
            return None, AUTONOMY_PROPOSAL_INVALID, f"Invalid autonomy data: {error_msg}"
        rule_id = None  # Ensure rule_id is None for level update

    elif operation in ("create_rule", "update_rule"):
        if not rule_id:
            return None, AUTONOMY_PROPOSAL_INVALID, f"rule_id is required for {operation} operation"
        if not autonomy_data:
            return None, AUTONOMY_PROPOSAL_INVALID, f"autonomy_data is required for {operation} operation"

        # Ensure rule_id matches
        if autonomy_data.get("rule_id") != rule_id:
            autonomy_data = dict(autonomy_data)
            autonomy_data["rule_id"] = rule_id

        # Validate rule schema
        is_valid, error_msg = _validate_autonomy_rule(autonomy_data)
        if not is_valid:
            return None, AUTONOMY_PROPOSAL_INVALID, f"Invalid autonomy rule: {error_msg}"

    elif operation == "revoke_rule":
        if not rule_id:
            return None, AUTONOMY_PROPOSAL_INVALID, "rule_id is required for revoke_rule operation"
        autonomy_data = None  # Clear data for revoke

    lock = _get_file_lock(institution_id, dept_id)

    with lock:
        # Load current state to check for conflicts
        governed_state = load_governed_state(institution_id, dept_id)

        if operation == "create_rule":
            # Check rule doesn't already exist
            if rule_id in governed_state.rules:
                return None, AUTONOMY_PROPOSAL_INVALID, f"Rule '{rule_id}' already exists in governed autonomy"

        if operation in ("update_rule", "revoke_rule"):
            # Check rule exists
            if rule_id not in governed_state.rules:
                # Also check bundle autonomy
                bundle_def = get_bundle_autonomy(dept_id)
                bundle_has_rule = False
                if bundle_def:
                    for r in bundle_def.rules:
                        if r.rule_id == rule_id:
                            bundle_has_rule = True
                            break

                if not bundle_has_rule:
                    return None, AUTONOMY_NOT_FOUND_FOR_UPDATE, f"Rule '{rule_id}' not found for {operation}"

        # Create proposal
        proposal_id = str(uuid.uuid4())
        now = _now_iso()
        proposals_path = _get_proposals_path(institution_id, dept_id)
        seq = _get_next_seq(proposals_path)

        record = AutonomyProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation_type="create",
            status="OPEN",
            created_at=now,
            autonomy_operation=operation,
            dept_id=dept_id,
            rule_id=rule_id,
            autonomy_data=autonomy_data,
            reason=reason,
            created_by=actor_id,
        )

        try:
            gov_dir = _get_governed_dir(institution_id, dept_id)
            gov_dir.mkdir(parents=True, exist_ok=True)
            with open(proposals_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        except OSError as e:
            return None, GOVERNED_AUTONOMY_UNAVAILABLE, f"Failed to write proposal: {e}"

    # Emit ledger event
    _emit_ledger_event(
        institution_id=institution_id,
        event_type=AUTONOMY_PROPOSED,
        case_id=proposal_id,
        step=f"GOVERNED_AUTONOMY:propose.{operation}",
        payload={
            "proposal_id": proposal_id,
            "operation": operation,
            "rule_id": rule_id,
            "autonomy_data": autonomy_data,
            "reason": reason,
        },
        actor_id=actor_id,
        dept_id=dept_id,
    )

    # Return proposal state
    state = AutonomyProposalState(
        proposal_id=proposal_id,
        status="OPEN",
        created_at=now,
        autonomy_operation=operation,
        dept_id=dept_id,
        rule_id=rule_id,
        autonomy_data=autonomy_data,
        reason=reason,
        created_by=actor_id,
    )

    return state, None, None


def decide_autonomy_proposal(
    institution_id: str,
    proposal_id: str,
    decision: str,
    reason: Optional[str],
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[AutonomyProposalState], Optional[str], Optional[str]]:
    """Decide on an autonomy proposal.

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
        return None, AUTONOMY_PROPOSAL_INVALID, f"Invalid decision: {decision}. Must be one of: {sorted(VALID_DECISIONS)}"

    lock = _get_file_lock(institution_id, dept_id)

    with lock:
        # Load current state
        states = load_proposal_state(institution_id, dept_id)

        if proposal_id not in states:
            return None, AUTONOMY_PROPOSAL_NOT_FOUND, f"Proposal '{proposal_id}' not found"

        proposal = states[proposal_id]

        if proposal.status == "DECIDED":
            return None, AUTONOMY_PROPOSAL_ALREADY_DECIDED, f"Proposal '{proposal_id}' is already decided"

        now = _now_iso()
        proposals_path = _get_proposals_path(institution_id, dept_id)
        seq = _get_next_seq(proposals_path)

        # Create decide record
        record = AutonomyProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation_type="decide",
            status="DECIDED",
            created_at=proposal.created_at,
            autonomy_operation=proposal.autonomy_operation,
            dept_id=proposal.dept_id,
            rule_id=proposal.rule_id,
            autonomy_data=proposal.autonomy_data,
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
            return None, GOVERNED_AUTONOMY_UNAVAILABLE, f"Failed to write decision: {e}"

        # Update proposal state
        proposal.status = "DECIDED"
        proposal.decision = decision
        proposal.decision_reason = reason
        proposal.decided_at = now
        proposal.decided_by = actor_id

    # Emit ledger event
    event_type = AUTONOMY_GOV_APPROVED if decision == "approve" else AUTONOMY_GOV_REJECTED
    _emit_ledger_event(
        institution_id=institution_id,
        event_type=event_type,
        case_id=proposal_id,
        step=f"GOVERNED_AUTONOMY:decide.{decision}",
        payload={
            "proposal_id": proposal_id,
            "decision": decision,
            "reason": reason,
            "rule_id": proposal.rule_id,
            "operation": proposal.autonomy_operation,
        },
        actor_id=actor_id,
        dept_id=dept_id,
    )

    # If approved, apply the change
    if decision == "approve":
        apply_result = apply_autonomy_change(institution_id, proposal_id, actor_id, dept_id)
        if apply_result[1]:
            # Apply failed - still return the decided proposal
            pass

    return proposal, None, None


def apply_autonomy_change(
    institution_id: str,
    proposal_id: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Apply an approved autonomy change.

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
            return False, AUTONOMY_PROPOSAL_NOT_FOUND, f"Proposal '{proposal_id}' not found"

        proposal = states[proposal_id]

        if proposal.status != "DECIDED" or proposal.decision != "approve":
            return False, AUTONOMY_PROPOSAL_INVALID, f"Proposal '{proposal_id}' is not approved"

        # Load current governed state
        governed_state = load_governed_state(institution_id, dept_id)
        now = _now_iso()

        # Apply the change
        operation = proposal.autonomy_operation
        rule_id = proposal.rule_id

        if operation == "update_level":
            governed_state.current_level = proposal.autonomy_data["current_level"]
        elif operation == "create_rule":
            governed_state.rules[rule_id] = proposal.autonomy_data
        elif operation == "update_rule":
            governed_state.rules[rule_id] = proposal.autonomy_data
        elif operation == "revoke_rule":
            governed_state.rules.pop(rule_id, None)

        governed_state.updated_at = now

        # Append to autonomy history
        autonomy_path = _get_autonomy_path(institution_id, dept_id)
        seq = _get_next_seq(autonomy_path)

        autonomy_record = GovernedAutonomyRecord(
            seq=seq,
            rule_id=rule_id,
            action=operation,
            dept_id=dept_id,
            autonomy_data=proposal.autonomy_data,
            applied_at=now,
            applied_by=actor_id,
            proposal_id=proposal_id,
        )

        try:
            gov_dir = _get_governed_dir(institution_id, dept_id)
            gov_dir.mkdir(parents=True, exist_ok=True)
            with open(autonomy_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(autonomy_record.to_dict(), sort_keys=True) + "\n")

            # Save state
            _save_governed_state(institution_id, dept_id, governed_state)
        except OSError as e:
            return False, GOVERNED_AUTONOMY_UNAVAILABLE, f"Failed to apply autonomy: {e}"

    # Emit ledger event
    event_type = AUTONOMY_GOV_REVOKED if operation == "revoke_rule" else AUTONOMY_GOV_APPLIED
    _emit_ledger_event(
        institution_id=institution_id,
        event_type=event_type,
        case_id=proposal_id,
        step=f"GOVERNED_AUTONOMY:apply.{operation}",
        payload={
            "proposal_id": proposal_id,
            "rule_id": rule_id,
            "operation": operation,
            "autonomy_data": proposal.autonomy_data,
        },
        actor_id=actor_id,
        dept_id=dept_id,
    )

    # Invalidate effective autonomy cache
    invalidate_effective_autonomy_cache(institution_id, dept_id)

    return True, None, None


# Effective autonomy cache
_effective_cache: Dict[str, Tuple[AutonomyDef, str]] = {}  # key -> (autonomy_def, updated_at)
_cache_lock = Lock()


def invalidate_effective_autonomy_cache(
    institution_id: str, dept_id: Optional[str] = None
) -> None:
    """Invalidate effective autonomy cache for institution/dept."""
    key = f"{institution_id}:{dept_id or '_single'}"
    with _cache_lock:
        _effective_cache.pop(key, None)


def invalidate_all_autonomy_cache() -> None:
    """Invalidate all effective autonomy cache (for testing)."""
    with _cache_lock:
        _effective_cache.clear()


def get_effective_autonomy(
    institution_id: str, dept_id: Optional[str] = None
) -> Optional[AutonomyDef]:
    """Get effective autonomy for institution/dept.

    Precedence:
    1. Governed autonomy (institutional override)
    2. Bundle autonomy (fallback)

    Governed rules override bundle rules by rule_id.
    Governed current_level overrides bundle current_level.
    Revoked rules are removed entirely.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        AutonomyDef with effective autonomy, or None if no autonomy exists.
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

    # Load governed autonomy state
    governed_state = load_governed_state(institution_id, dept_id)

    # Load bundle autonomy
    bundle_def = get_bundle_autonomy(dept_id)

    # If neither exists, return None
    if governed_state.current_level is None and not governed_state.rules and bundle_def is None:
        return None

    # Determine effective current_level
    if governed_state.current_level is not None:
        effective_level = governed_state.current_level
    elif bundle_def:
        effective_level = bundle_def.current_level
    else:
        effective_level = MAX_LEVEL  # Default allow-all

    # Build effective rules list
    effective_rules: Dict[str, AutonomyRule] = {}

    # First, add bundle rules
    if bundle_def:
        for rule in bundle_def.rules:
            effective_rules[rule.rule_id] = rule

    # Then, apply governed rules (override/create/revoke)
    for rule_id, rule_data in governed_state.rules.items():
        if rule_data is None:
            # Revoked - remove from effective
            effective_rules.pop(rule_id, None)
        else:
            # Create/update - parse and add
            wrapped = {
                "autonomy_schema_version": "1.0",
                "current_level": 0,
                "rules": [rule_data],
            }
            try:
                parsed = parse_autonomy_data(wrapped)
                if parsed.rules:
                    effective_rules[rule_id] = parsed.rules[0]
            except AutonomySchemaError:
                # Invalid governed rule - skip
                pass

    result = AutonomyDef(
        current_level=effective_level,
        rules=list(effective_rules.values()),
    )

    # Update cache
    with _cache_lock:
        _effective_cache[key] = (result, governed_state.updated_at)

    return result


def list_autonomy_proposals(
    institution_id: str,
    dept_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
) -> List[AutonomyProposalState]:
    """List autonomy proposals for institution.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        status_filter: Optional filter by status ("OPEN" or "DECIDED").
        limit: Maximum number of proposals to return.

    Returns:
        List of AutonomyProposalState (most recent first).
    """
    states = load_proposal_state(institution_id, dept_id)

    # Filter by status if specified
    proposals = list(states.values())
    if status_filter:
        proposals = [p for p in proposals if p.status == status_filter]

    # Sort by created_at descending
    proposals.sort(key=lambda p: p.created_at, reverse=True)

    return proposals[:limit]


def list_governed_autonomy(
    institution_id: str, dept_id: Optional[str] = None
) -> GovernedAutonomyState:
    """List current governed autonomy.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        GovernedAutonomyState with current_level and rules.
    """
    return load_governed_state(institution_id, dept_id)


def get_autonomy_proposal(
    institution_id: str,
    proposal_id: str,
    dept_id: Optional[str] = None,
) -> Optional[AutonomyProposalState]:
    """Get a specific autonomy proposal.

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID.
        dept_id: Optional department ID.

    Returns:
        AutonomyProposalState if found, None otherwise.
    """
    states = load_proposal_state(institution_id, dept_id)
    return states.get(proposal_id)


def reset_governed_autonomy_registry() -> None:
    """Reset file locks and cache (for testing)."""
    global _file_locks, _effective_cache
    with _global_lock:
        _file_locks.clear()
    with _cache_lock:
        _effective_cache.clear()
