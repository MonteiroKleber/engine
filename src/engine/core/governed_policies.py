"""Governed Policies - Runtime policy override via EGE-style proposals.

Implements policy governance workflow with:
- Append-only JSONL storage per institution/dept
- Proposal workflow: propose → decide → apply
- Runtime override: governed policies take precedence over bundle
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
from engine.core.policy import (
    PolicyDef,
    PolicyRule,
    parse_policies_data,
    get_policies as get_bundle_policies,
    PolicySchemaError,
)
from engine.core.errors import (
    POLICY_PROPOSAL_NOT_FOUND,
    POLICY_PROPOSAL_ALREADY_DECIDED,
    POLICY_PROPOSAL_INVALID,
    POLICY_NOT_FOUND_FOR_UPDATE,
    POLICY_ALREADY_EXISTS,
    GOVERNED_POLICIES_UNAVAILABLE,
)


# Storage file names
PROPOSALS_FILE = "policy_proposals.jsonl"
POLICIES_FILE = "governed_policies.jsonl"
STATE_FILE = "governed_policies_state.json"

# Valid operations
VALID_OPERATIONS = frozenset({"create", "update", "revoke"})

# Valid decisions
VALID_DECISIONS = frozenset({"approve", "reject"})

# Ledger event types
POLICY_PROPOSED = "POLICY_PROPOSED"
POLICY_APPROVED = "POLICY_APPROVED"
POLICY_REJECTED = "POLICY_REJECTED"
POLICY_APPLIED = "POLICY_APPLIED"
POLICY_REVOKED = "POLICY_REVOKED"


@dataclass
class PolicyProposalRecord:
    """A single policy proposal record (append-only log entry)."""

    seq: int  # Monotonic sequence number
    proposal_id: str  # UUID
    operation_type: str  # "create" or "decide"
    status: str  # "OPEN" or "DECIDED"
    created_at: str  # UTC ISO8601

    # Proposal details
    policy_operation: str  # "create", "update", or "revoke"
    dept_id: Optional[str]  # None for single-mode
    policy_id: str  # Target policy ID
    policy_data: Optional[Dict[str, Any]]  # Full policy data (for create/update)
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
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyProposalRecord":
        """Create from dictionary."""
        return cls(
            seq=data["seq"],
            proposal_id=data["proposal_id"],
            operation_type=data["operation_type"],
            status=data["status"],
            created_at=data["created_at"],
            policy_operation=data["policy_operation"],
            dept_id=data.get("dept_id"),
            policy_id=data["policy_id"],
            policy_data=data.get("policy_data"),
            reason=data.get("reason", ""),
            created_by=data.get("created_by", ""),
            decision=data.get("decision"),
            decision_reason=data.get("decision_reason"),
            decided_at=data.get("decided_at"),
            decided_by=data.get("decided_by"),
        )


@dataclass
class PolicyProposalState:
    """Computed state of a single proposal (folded from records)."""

    proposal_id: str
    status: str  # "OPEN" or "DECIDED"
    created_at: str

    policy_operation: str
    dept_id: Optional[str]
    policy_id: str
    policy_data: Optional[Dict[str, Any]]
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
class GovernedPolicyRecord:
    """A governed policy record (append-only log entry)."""

    seq: int
    policy_id: str
    action: str  # "create", "update", "revoke"
    dept_id: Optional[str]
    policy_data: Optional[Dict[str, Any]]  # None for revoke
    applied_at: str
    applied_by: str
    proposal_id: str  # Source proposal

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GovernedPolicyRecord":
        """Create from dictionary."""
        return cls(
            seq=data["seq"],
            policy_id=data["policy_id"],
            action=data["action"],
            dept_id=data.get("dept_id"),
            policy_data=data.get("policy_data"),
            applied_at=data["applied_at"],
            applied_by=data.get("applied_by", ""),
            proposal_id=data.get("proposal_id", ""),
        )


@dataclass
class GovernedPoliciesState:
    """Current state of governed policies for an institution/dept."""

    schema_version: str = "1.0"
    updated_at: Optional[str] = None
    policies: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # policy_id -> policy_data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "policies": self.policies,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GovernedPoliciesState":
        """Create from dictionary."""
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            updated_at=data.get("updated_at"),
            policies=data.get("policies", {}),
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
    """Get governed policies directory path."""
    inst_root = get_institution_root(institution_id)
    if dept_id:
        return inst_root / "depts" / dept_id / "governed_policies"
    return inst_root / "governed_policies"


def _get_proposals_path(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get path to proposals file."""
    return _get_governed_dir(institution_id, dept_id) / PROPOSALS_FILE


def _get_policies_path(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get path to policies history file."""
    return _get_governed_dir(institution_id, dept_id) / POLICIES_FILE


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
    """Emit ledger event for governed policy operation."""
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
) -> List[PolicyProposalRecord]:
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
                    records.append(PolicyProposalRecord.from_dict(data))
                except (json.JSONDecodeError, KeyError):
                    continue
    return records


def load_proposal_state(
    institution_id: str, dept_id: Optional[str] = None
) -> Dict[str, PolicyProposalState]:
    """Compute current proposal state by folding all records."""
    records = load_proposal_records(institution_id, dept_id)
    states: Dict[str, PolicyProposalState] = {}

    for record in records:
        proposal_id = record.proposal_id

        if record.operation_type == "create":
            states[proposal_id] = PolicyProposalState(
                proposal_id=proposal_id,
                status=record.status,
                created_at=record.created_at,
                policy_operation=record.policy_operation,
                dept_id=record.dept_id,
                policy_id=record.policy_id,
                policy_data=record.policy_data,
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
) -> GovernedPoliciesState:
    """Load current governed policies state."""
    state_path = _get_state_path(institution_id, dept_id)
    if not state_path.exists():
        return GovernedPoliciesState()

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return GovernedPoliciesState.from_dict(data)
    except (json.JSONDecodeError, IOError):
        return GovernedPoliciesState()


def _save_governed_state(
    institution_id: str,
    dept_id: Optional[str],
    state: GovernedPoliciesState,
) -> None:
    """Save governed policies state."""
    gov_dir = _get_governed_dir(institution_id, dept_id)
    gov_dir.mkdir(parents=True, exist_ok=True)
    state_path = _get_state_path(institution_id, dept_id)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, sort_keys=True)


def _validate_policy_data(policy_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate policy data against schema.

    Returns:
        Tuple of (is_valid, error_message).
    """
    # Wrap in policies.json format for validation
    wrapped = {
        "policy_schema_version": "1.1",
        "policies": [policy_data],
    }
    try:
        parse_policies_data(wrapped)
        return True, None
    except PolicySchemaError as e:
        return False, e.message


def propose_policy_change(
    institution_id: str,
    operation: str,
    policy_id: str,
    policy_data: Optional[Dict[str, Any]],
    reason: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[PolicyProposalState], Optional[str], Optional[str]]:
    """Create a policy change proposal.

    Args:
        institution_id: Institution UUID.
        operation: "create", "update", or "revoke".
        policy_id: Target policy ID.
        policy_data: Full policy data (required for create/update, None for revoke).
        reason: Reason for the proposal.
        actor_id: Actor creating the proposal.
        dept_id: Optional department ID.

    Returns:
        Tuple of (proposal_state, error_code, error_message).
    """
    # Validate operation
    if operation not in VALID_OPERATIONS:
        return None, POLICY_PROPOSAL_INVALID, f"Invalid operation: {operation}. Must be one of: {sorted(VALID_OPERATIONS)}"

    # Validate policy_data for create/update
    if operation in ("create", "update"):
        if not policy_data:
            return None, POLICY_PROPOSAL_INVALID, f"policy_data is required for {operation} operation"

        # Ensure policy_id matches
        if policy_data.get("policy_id") != policy_id:
            policy_data = dict(policy_data)
            policy_data["policy_id"] = policy_id

        # Validate schema
        is_valid, error_msg = _validate_policy_data(policy_data)
        if not is_valid:
            return None, POLICY_PROPOSAL_INVALID, f"Invalid policy data: {error_msg}"

    # For revoke, policy_data should be None
    if operation == "revoke":
        policy_data = None

    lock = _get_file_lock(institution_id, dept_id)

    with lock:
        # Load current state to check for conflicts
        governed_state = load_governed_state(institution_id, dept_id)

        if operation == "create":
            # Check policy doesn't already exist
            if policy_id in governed_state.policies:
                return None, POLICY_ALREADY_EXISTS, f"Policy '{policy_id}' already exists in governed policies"

        if operation in ("update", "revoke"):
            # Check policy exists
            if policy_id not in governed_state.policies:
                # Also check bundle policies
                bundle_def = get_bundle_policies(dept_id)
                bundle_has_policy = False
                if bundle_def:
                    for p in bundle_def.policies:
                        if p.policy_id == policy_id:
                            bundle_has_policy = True
                            break

                if not bundle_has_policy:
                    return None, POLICY_NOT_FOUND_FOR_UPDATE, f"Policy '{policy_id}' not found for {operation}"

        # Create proposal
        proposal_id = str(uuid.uuid4())
        now = _now_iso()
        proposals_path = _get_proposals_path(institution_id, dept_id)
        seq = _get_next_seq(proposals_path)

        record = PolicyProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation_type="create",
            status="OPEN",
            created_at=now,
            policy_operation=operation,
            dept_id=dept_id,
            policy_id=policy_id,
            policy_data=policy_data,
            reason=reason,
            created_by=actor_id,
        )

        try:
            gov_dir = _get_governed_dir(institution_id, dept_id)
            gov_dir.mkdir(parents=True, exist_ok=True)
            with open(proposals_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        except OSError as e:
            return None, GOVERNED_POLICIES_UNAVAILABLE, f"Failed to write proposal: {e}"

    # Emit ledger event
    _emit_ledger_event(
        institution_id=institution_id,
        event_type=POLICY_PROPOSED,
        case_id=proposal_id,
        step=f"GOVERNED_POLICY:propose.{operation}",
        payload={
            "proposal_id": proposal_id,
            "operation": operation,
            "policy_id": policy_id,
            "policy_data": policy_data,
            "reason": reason,
        },
        actor_id=actor_id,
        dept_id=dept_id,
    )

    # Return proposal state
    state = PolicyProposalState(
        proposal_id=proposal_id,
        status="OPEN",
        created_at=now,
        policy_operation=operation,
        dept_id=dept_id,
        policy_id=policy_id,
        policy_data=policy_data,
        reason=reason,
        created_by=actor_id,
    )

    return state, None, None


def decide_policy_proposal(
    institution_id: str,
    proposal_id: str,
    decision: str,
    reason: Optional[str],
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[PolicyProposalState], Optional[str], Optional[str]]:
    """Decide on a policy proposal.

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
        return None, POLICY_PROPOSAL_INVALID, f"Invalid decision: {decision}. Must be one of: {sorted(VALID_DECISIONS)}"

    lock = _get_file_lock(institution_id, dept_id)

    with lock:
        # Load current state
        states = load_proposal_state(institution_id, dept_id)

        if proposal_id not in states:
            return None, POLICY_PROPOSAL_NOT_FOUND, f"Proposal '{proposal_id}' not found"

        proposal = states[proposal_id]

        if proposal.status == "DECIDED":
            return None, POLICY_PROPOSAL_ALREADY_DECIDED, f"Proposal '{proposal_id}' is already decided"

        now = _now_iso()
        proposals_path = _get_proposals_path(institution_id, dept_id)
        seq = _get_next_seq(proposals_path)

        # Create decide record
        record = PolicyProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation_type="decide",
            status="DECIDED",
            created_at=proposal.created_at,
            policy_operation=proposal.policy_operation,
            dept_id=proposal.dept_id,
            policy_id=proposal.policy_id,
            policy_data=proposal.policy_data,
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
            return None, GOVERNED_POLICIES_UNAVAILABLE, f"Failed to write decision: {e}"

        # Update proposal state
        proposal.status = "DECIDED"
        proposal.decision = decision
        proposal.decision_reason = reason
        proposal.decided_at = now
        proposal.decided_by = actor_id

    # Emit ledger event
    event_type = POLICY_APPROVED if decision == "approve" else POLICY_REJECTED
    _emit_ledger_event(
        institution_id=institution_id,
        event_type=event_type,
        case_id=proposal_id,
        step=f"GOVERNED_POLICY:decide.{decision}",
        payload={
            "proposal_id": proposal_id,
            "decision": decision,
            "reason": reason,
            "policy_id": proposal.policy_id,
            "operation": proposal.policy_operation,
        },
        actor_id=actor_id,
        dept_id=dept_id,
    )

    # If approved, apply the change
    if decision == "approve":
        apply_result = apply_policy_change(institution_id, proposal_id, actor_id, dept_id)
        if apply_result[1]:
            # Apply failed - still return the decided proposal
            pass

    return proposal, None, None


def apply_policy_change(
    institution_id: str,
    proposal_id: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Apply an approved policy change.

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
            return False, POLICY_PROPOSAL_NOT_FOUND, f"Proposal '{proposal_id}' not found"

        proposal = states[proposal_id]

        if proposal.status != "DECIDED" or proposal.decision != "approve":
            return False, POLICY_PROPOSAL_INVALID, f"Proposal '{proposal_id}' is not approved"

        # Load current governed state
        governed_state = load_governed_state(institution_id, dept_id)
        now = _now_iso()

        # Apply the change
        operation = proposal.policy_operation
        policy_id = proposal.policy_id

        if operation == "create":
            governed_state.policies[policy_id] = proposal.policy_data
        elif operation == "update":
            governed_state.policies[policy_id] = proposal.policy_data
        elif operation == "revoke":
            governed_state.policies.pop(policy_id, None)

        governed_state.updated_at = now

        # Append to policies history
        policies_path = _get_policies_path(institution_id, dept_id)
        seq = _get_next_seq(policies_path)

        policy_record = GovernedPolicyRecord(
            seq=seq,
            policy_id=policy_id,
            action=operation,
            dept_id=dept_id,
            policy_data=proposal.policy_data,
            applied_at=now,
            applied_by=actor_id,
            proposal_id=proposal_id,
        )

        try:
            gov_dir = _get_governed_dir(institution_id, dept_id)
            gov_dir.mkdir(parents=True, exist_ok=True)
            with open(policies_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(policy_record.to_dict(), sort_keys=True) + "\n")

            # Save state
            _save_governed_state(institution_id, dept_id, governed_state)
        except OSError as e:
            return False, GOVERNED_POLICIES_UNAVAILABLE, f"Failed to apply policy: {e}"

    # Emit ledger event
    event_type = POLICY_REVOKED if operation == "revoke" else POLICY_APPLIED
    _emit_ledger_event(
        institution_id=institution_id,
        event_type=event_type,
        case_id=proposal_id,
        step=f"GOVERNED_POLICY:apply.{operation}",
        payload={
            "proposal_id": proposal_id,
            "policy_id": policy_id,
            "operation": operation,
            "policy_data": proposal.policy_data,
        },
        actor_id=actor_id,
        dept_id=dept_id,
    )

    # Invalidate effective policies cache
    invalidate_effective_policies_cache(institution_id, dept_id)

    return True, None, None


# Effective policies cache
_effective_cache: Dict[str, Tuple[PolicyDef, str]] = {}  # key -> (policy_def, updated_at)
_cache_lock = Lock()


def invalidate_effective_policies_cache(
    institution_id: str, dept_id: Optional[str] = None
) -> None:
    """Invalidate effective policies cache for institution/dept."""
    key = f"{institution_id}:{dept_id or '_single'}"
    with _cache_lock:
        _effective_cache.pop(key, None)


def invalidate_all_policies_cache() -> None:
    """Invalidate all effective policies cache (for testing)."""
    with _cache_lock:
        _effective_cache.clear()


def get_effective_policies(
    institution_id: str, dept_id: Optional[str] = None
) -> Optional[PolicyDef]:
    """Get effective policies for institution/dept.

    Precedence:
    1. Governed policies (institutional override)
    2. Bundle policies (fallback)

    Governed policies override bundle policies by policy_id.
    Revoked policies are removed entirely.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        PolicyDef with effective policies, or None if no policies exist.
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

    # Load governed policies state
    governed_state = load_governed_state(institution_id, dept_id)

    # Load bundle policies
    bundle_def = get_bundle_policies(dept_id)

    # If neither exists, return None
    if not governed_state.policies and bundle_def is None:
        return None

    # Build effective policies list
    effective_policies: Dict[str, PolicyRule] = {}

    # First, add bundle policies
    if bundle_def:
        for policy in bundle_def.policies:
            effective_policies[policy.policy_id] = policy

    # Then, apply governed policies (override/create/revoke)
    for policy_id, policy_data in governed_state.policies.items():
        if policy_data is None:
            # Revoked - remove from effective
            effective_policies.pop(policy_id, None)
        else:
            # Create/update - parse and add
            wrapped = {
                "policy_schema_version": "1.1",
                "policies": [policy_data],
            }
            try:
                parsed = parse_policies_data(wrapped)
                if parsed.policies:
                    effective_policies[policy_id] = parsed.policies[0]
            except PolicySchemaError:
                # Invalid governed policy - skip (should not happen if validation is correct)
                pass

    # If no effective policies, return None (allow all)
    if not effective_policies:
        # But if bundle_def was loaded, we should return empty PolicyDef
        if bundle_def is not None or governed_state.policies:
            result = PolicyDef(policies=[])
        else:
            result = None
    else:
        result = PolicyDef(policies=list(effective_policies.values()))

    # Update cache
    with _cache_lock:
        _effective_cache[key] = (result, governed_state.updated_at)

    return result


def list_policy_proposals(
    institution_id: str,
    dept_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
) -> List[PolicyProposalState]:
    """List policy proposals for institution.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        status_filter: Optional filter by status ("OPEN" or "DECIDED").
        limit: Maximum number of proposals to return.

    Returns:
        List of PolicyProposalState (most recent first).
    """
    states = load_proposal_state(institution_id, dept_id)

    # Filter by status if specified
    proposals = list(states.values())
    if status_filter:
        proposals = [p for p in proposals if p.status == status_filter]

    # Sort by created_at descending
    proposals.sort(key=lambda p: p.created_at, reverse=True)

    return proposals[:limit]


def list_governed_policies(
    institution_id: str, dept_id: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """List current governed policies.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        Dictionary mapping policy_id to policy_data.
    """
    state = load_governed_state(institution_id, dept_id)
    return state.policies


def get_policy_proposal(
    institution_id: str,
    proposal_id: str,
    dept_id: Optional[str] = None,
) -> Optional[PolicyProposalState]:
    """Get a specific policy proposal.

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID.
        dept_id: Optional department ID.

    Returns:
        PolicyProposalState if found, None otherwise.
    """
    states = load_proposal_state(institution_id, dept_id)
    return states.get(proposal_id)


def reset_governed_policies_registry() -> None:
    """Reset file locks and cache (for testing)."""
    global _file_locks, _effective_cache
    with _global_lock:
        _file_locks.clear()
    with _cache_lock:
        _effective_cache.clear()
