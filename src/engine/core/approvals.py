"""Approvals - MVP approval workflow with ledger integration.

Supports generic approval targets (Jobs First-Class spec):
- entity_ref: {entity_type, entity_id, transition?}
- job_ref: {job_id, action? (enqueue)}

The approval system is target-agnostic - no hardcoded entity_type checks.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from .ledger import get_ledger, get_ledger_for_institution, LedgerEvent
from .actor_context import ActorContext


class ApprovalTargetKind(str, Enum):
    """Approval target kinds."""
    JOB = "job"
    ENTITY = "entity"
    LEGACY_API = "legacy_api"  # Backward compatibility for API-triggered approvals


@dataclass
class JobRef:
    """Reference to a job for approval."""
    job_id: str
    action: str = "enqueue"  # Action to take when approved

    def to_dict(self) -> Dict[str, Any]:
        return {"job_id": self.job_id, "action": self.action}


@dataclass
class EntityRef:
    """Reference to an entity for approval."""
    entity_type: str
    entity_id: str
    transition: Optional[str] = None
    workflow: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"entity_type": self.entity_type, "entity_id": self.entity_id}
        if self.transition:
            result["transition"] = self.transition
        if self.workflow:
            result["workflow"] = self.workflow
        return result


@dataclass
class ApprovalTarget:
    """Generic approval target supporting job_ref or entity_ref."""
    kind: ApprovalTargetKind
    ref: Union[JobRef, EntityRef, Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        if isinstance(self.ref, (JobRef, EntityRef)):
            return {"kind": self.kind.value, "ref": self.ref.to_dict()}
        return {"kind": self.kind.value, "ref": self.ref}


@dataclass
class ApprovalRule:
    """Approval rule definition."""
    rule_name: str
    trigger_api: str
    approver_roles: List[str]
    quorum: int = 1


class ApprovalsPolicy:
    """Approvals policy loaded from approvals.json."""

    def __init__(self, approvals_data: Dict[str, Any]) -> None:
        """Initialize approvals policy from contract data."""
        self._rules: Dict[str, ApprovalRule] = {}
        self._api_rules: Dict[str, ApprovalRule] = {}
        self._load_rules(approvals_data)

    def _load_rules(self, approvals_data: Dict[str, Any]) -> None:
        """Load rules from approvals data."""
        rules = approvals_data.get("rules", [])
        for rule in rules:
            rule_name = rule.get("rule_name")
            trigger = rule.get("trigger", {})
            trigger_api = trigger.get("api", "")
            approver_roles = rule.get("approver_roles", [])
            quorum = rule.get("quorum", 1)

            if rule_name and trigger_api:
                approval_rule = ApprovalRule(
                    rule_name=rule_name,
                    trigger_api=trigger_api,
                    approver_roles=approver_roles,
                    quorum=quorum,
                )
                self._rules[rule_name] = approval_rule
                self._api_rules[trigger_api] = approval_rule

    def get_rule_for_api(self, api: str) -> Optional[ApprovalRule]:
        """Get approval rule for an API endpoint."""
        return self._api_rules.get(api)

    def get_rule_by_name(self, rule_name: str) -> Optional[ApprovalRule]:
        """Get approval rule by name."""
        return self._rules.get(rule_name)


# Per-department approvals policies (key: dept_id, None for single mode)
_approvals_policies: Dict[Optional[str], ApprovalsPolicy] = {}


def set_approvals_policy(policy: Optional[ApprovalsPolicy], dept_id: Optional[str] = None) -> None:
    """Set approvals policy for a department (or single mode).

    Args:
        policy: ApprovalsPolicy instance, or None to clear.
        dept_id: Department ID, or None for single mode.
    """
    if policy is None:
        _approvals_policies.pop(dept_id, None)
    else:
        _approvals_policies[dept_id] = policy


def get_approvals_policy(dept_id: Optional[str] = None) -> Optional[ApprovalsPolicy]:
    """Get approvals policy for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.

    Returns:
        ApprovalsPolicy if set, None otherwise.
    """
    return _approvals_policies.get(dept_id)


def reset_all_approvals() -> None:
    """Reset all approvals policies (for testing)."""
    global _approvals_policies
    _approvals_policies = {}


def compute_payload_sha256(payload_bytes: bytes) -> str:
    """Compute SHA-256 hash of payload bytes."""
    return hashlib.sha256(payload_bytes).hexdigest()


def generate_approval_id() -> str:
    """Generate a new approval ID (UUID)."""
    return str(uuid.uuid4())


def get_approval_step_name(rule_name: str) -> str:
    """Get the step name for an approval rule."""
    return f"APPROVAL:{rule_name}"


def emit_approval_requested(
    approval_id: str,
    rule: ApprovalRule,
    actor: ActorContext,
    payload_sha256: str,
) -> Optional[LedgerEvent]:
    """Emit APPROVAL_REQUESTED event to ledger.

    Args:
        approval_id: The approval ID (case_id).
        rule: The approval rule.
        actor: The requesting actor.
        payload_sha256: SHA256 of the request payload.

    Returns:
        The created event, or None if failed.
    """
    ledger = get_ledger()
    if not ledger:
        return None

    step = get_approval_step_name(rule.rule_name)

    return ledger.append(
        event_type="APPROVAL_REQUESTED",
        tenant_id=actor.tenant_id,
        actor_id=actor.actor_id,
        actor_roles=actor.roles,
        case_id=approval_id,
        step=step,
        payload={
            "decision": None,
            "name": step,
            "target": {
                "api": rule.trigger_api,
            },
            "payload_sha256": payload_sha256,
            "requested_by": actor.actor_id,
            "required_roles": rule.approver_roles,
        },
    )


def emit_approval_requested_generic(
    approval_id: str,
    rule_name: str,
    target: ApprovalTarget,
    actor: ActorContext,
    approver_roles: List[str],
    payload_sha256: str = "",
    tenant_id: Optional[str] = None,
) -> Optional[LedgerEvent]:
    """Emit APPROVAL_REQUESTED event with generic target (Jobs First-Class spec).

    This is the preferred function for new approvals. It supports:
    - job_ref: {job_id, action} - for job-based approvals
    - entity_ref: {entity_type, entity_id, transition} - for entity transitions

    Args:
        approval_id: The approval ID (case_id).
        rule_name: The approval rule name (e.g., "FileOperationFlow.Approve").
        target: ApprovalTarget with kind and ref.
        actor: The requesting actor.
        approver_roles: List of roles that can decide.
        payload_sha256: SHA256 of the request payload (optional).
        tenant_id: Override tenant_id (defaults to actor.tenant_id).

    Returns:
        The created event, or None if failed.
    """
    from .ledger import get_ledger_for_institution

    effective_tenant_id = tenant_id or actor.tenant_id
    ledger = get_ledger_for_institution(effective_tenant_id)
    if not ledger:
        # Fall back to default ledger
        ledger = get_ledger()
    if not ledger:
        return None

    step = get_approval_step_name(rule_name)

    return ledger.append(
        event_type="APPROVAL_REQUESTED",
        tenant_id=effective_tenant_id,
        actor_id=actor.actor_id,
        actor_roles=actor.roles,
        case_id=approval_id,
        step=step,
        payload={
            "decision": None,
            "name": step,
            "target_kind": target.kind.value,
            "target_ref": target.to_dict()["ref"],
            "payload_sha256": payload_sha256,
            "requested_by": actor.actor_id,
            "required_roles": approver_roles,
        },
    )


def emit_approval_decided(
    approval_id: str,
    rule: ApprovalRule,
    actor: ActorContext,
    decision: str,
    reason: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> Optional[LedgerEvent]:
    """Emit APPROVAL_DECIDED event to ledger.

    Args:
        approval_id: The approval ID (case_id).
        rule: The approval rule.
        actor: The deciding actor.
        decision: "approve" or "reject".
        reason: Optional reason string.
        institution_id: Optional institution ID for institution-specific ledger.

    Returns:
        The created event, or None if failed.
    """
    if institution_id:
        ledger = get_ledger_for_institution(institution_id)
    else:
        ledger = get_ledger()
    if not ledger:
        return None

    step = get_approval_step_name(rule.rule_name)

    payload: Dict[str, Any] = {
        "decision": decision,
        "name": step,
        "decided_by": actor.actor_id,
    }
    if reason:
        payload["reason"] = reason

    return ledger.append(
        event_type="APPROVAL_DECIDED",
        tenant_id=actor.tenant_id,
        actor_id=actor.actor_id,
        actor_roles=actor.roles,
        case_id=approval_id,
        step=step,
        payload=payload,
    )


def find_approval_requested(
    approval_id: str, institution_id: Optional[str] = None
) -> Optional[LedgerEvent]:
    """Find APPROVAL_REQUESTED event for an approval_id.

    Args:
        approval_id: The approval ID to search for.
        institution_id: Optional institution ID for institution-specific ledger.

    Returns:
        The APPROVAL_REQUESTED event if found, None otherwise.
    """
    if institution_id:
        ledger = get_ledger_for_institution(institution_id)
    else:
        ledger = get_ledger()
    if not ledger:
        return None

    events = ledger.get_all_events()
    for event in events:
        if (
            event.case_id == approval_id
            and event.event_type == "APPROVAL_REQUESTED"
        ):
            return event

    return None


def find_approval_decided(
    approval_id: str, institution_id: Optional[str] = None
) -> Optional[LedgerEvent]:
    """Find APPROVAL_DECIDED event for an approval_id.

    Args:
        approval_id: The approval ID to search for.
        institution_id: Optional institution ID for institution-specific ledger.

    Returns:
        The APPROVAL_DECIDED event if found, None otherwise.
    """
    if institution_id:
        ledger = get_ledger_for_institution(institution_id)
    else:
        ledger = get_ledger()
    if not ledger:
        return None

    events = ledger.get_all_events()
    for event in events:
        if (
            event.case_id == approval_id
            and event.event_type == "APPROVAL_DECIDED"
        ):
            return event

    return None


def is_approval_decided(
    approval_id: str, institution_id: Optional[str] = None
) -> bool:
    """Check if an approval has already been decided."""
    return find_approval_decided(approval_id, institution_id) is not None


def can_actor_decide(actor: ActorContext, rule: ApprovalRule) -> bool:
    """Check if actor has required role to decide on approval."""
    for role in actor.roles:
        if role in rule.approver_roles:
            return True
    return False


def get_rule_name_from_step(step: str) -> Optional[str]:
    """Extract rule name from step (e.g., 'APPROVAL:expense.create' -> 'expense.create')."""
    if step.startswith("APPROVAL:"):
        return step[9:]
    return None


def extract_target_from_event(event: LedgerEvent) -> Optional[ApprovalTarget]:
    """Extract ApprovalTarget from APPROVAL_REQUESTED event payload.

    Supports both new generic format (target_kind/target_ref) and legacy format (api).

    Args:
        event: APPROVAL_REQUESTED ledger event.

    Returns:
        ApprovalTarget if extractable, None otherwise.
    """
    if event.event_type != "APPROVAL_REQUESTED":
        return None

    payload = event.payload or {}

    # New generic format
    target_kind = payload.get("target_kind")
    target_ref = payload.get("target_ref")

    if target_kind and target_ref:
        kind = ApprovalTargetKind(target_kind)
        if kind == ApprovalTargetKind.JOB:
            ref = JobRef(
                job_id=target_ref.get("job_id", ""),
                action=target_ref.get("action", "enqueue"),
            )
        elif kind == ApprovalTargetKind.ENTITY:
            ref = EntityRef(
                entity_type=target_ref.get("entity_type", ""),
                entity_id=target_ref.get("entity_id", ""),
                transition=target_ref.get("transition"),
                workflow=target_ref.get("workflow"),
            )
        else:
            ref = target_ref  # Legacy or unknown
        return ApprovalTarget(kind=kind, ref=ref)

    # Legacy format (api-based)
    target = payload.get("target", {})
    if target.get("api"):
        return ApprovalTarget(
            kind=ApprovalTargetKind.LEGACY_API,
            ref={"api": target["api"]},
        )

    return None


def is_job_approval(event: LedgerEvent) -> bool:
    """Check if approval event is for a job."""
    target = extract_target_from_event(event)
    return target is not None and target.kind == ApprovalTargetKind.JOB


def is_entity_approval(event: LedgerEvent) -> bool:
    """Check if approval event is for an entity transition."""
    target = extract_target_from_event(event)
    return target is not None and target.kind == ApprovalTargetKind.ENTITY


def get_job_ref_from_approval(
    approval_id: str, institution_id: Optional[str] = None
) -> Optional[JobRef]:
    """Get JobRef from a pending job approval.

    Args:
        approval_id: The approval ID.
        institution_id: Optional institution ID for institution-specific ledger.

    Returns:
        JobRef if this is a job approval, None otherwise.
    """
    event = find_approval_requested(approval_id, institution_id)
    if not event:
        return None

    target = extract_target_from_event(event)
    if target and target.kind == ApprovalTargetKind.JOB:
        if isinstance(target.ref, JobRef):
            return target.ref
        # Handle dict case
        return JobRef(
            job_id=target.ref.get("job_id", ""),
            action=target.ref.get("action", "enqueue"),
        )
    return None


def get_entity_ref_from_approval(
    approval_id: str, institution_id: Optional[str] = None
) -> Optional[EntityRef]:
    """Get EntityRef from a pending entity approval.

    Args:
        approval_id: The approval ID.
        institution_id: Optional institution ID for institution-specific ledger.

    Returns:
        EntityRef if this is an entity approval, None otherwise.
    """
    event = find_approval_requested(approval_id, institution_id)
    if not event:
        return None

    target = extract_target_from_event(event)
    if target and target.kind == ApprovalTargetKind.ENTITY:
        if isinstance(target.ref, EntityRef):
            return target.ref
        # Handle dict case
        return EntityRef(
            entity_type=target.ref.get("entity_type", ""),
            entity_id=target.ref.get("entity_id", ""),
            transition=target.ref.get("transition"),
            workflow=target.ref.get("workflow"),
        )
    return None
