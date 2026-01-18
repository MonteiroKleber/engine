"""Approvals - MVP approval workflow with ledger integration."""

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .ledger import get_ledger, LedgerEvent
from .actor_context import ActorContext


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


# Global approvals policy
_approvals_policy: Optional[ApprovalsPolicy] = None


def set_approvals_policy(policy: Optional[ApprovalsPolicy]) -> None:
    """Set the global approvals policy."""
    global _approvals_policy
    _approvals_policy = policy


def get_approvals_policy() -> Optional[ApprovalsPolicy]:
    """Get the global approvals policy."""
    return _approvals_policy


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


def emit_approval_decided(
    approval_id: str,
    rule: ApprovalRule,
    actor: ActorContext,
    decision: str,
    reason: Optional[str] = None,
) -> Optional[LedgerEvent]:
    """Emit APPROVAL_DECIDED event to ledger.

    Args:
        approval_id: The approval ID (case_id).
        rule: The approval rule.
        actor: The deciding actor.
        decision: "approve" or "reject".
        reason: Optional reason string.

    Returns:
        The created event, or None if failed.
    """
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


def find_approval_requested(approval_id: str) -> Optional[LedgerEvent]:
    """Find APPROVAL_REQUESTED event for an approval_id.

    Args:
        approval_id: The approval ID to search for.

    Returns:
        The APPROVAL_REQUESTED event if found, None otherwise.
    """
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


def find_approval_decided(approval_id: str) -> Optional[LedgerEvent]:
    """Find APPROVAL_DECIDED event for an approval_id.

    Args:
        approval_id: The approval ID to search for.

    Returns:
        The APPROVAL_DECIDED event if found, None otherwise.
    """
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


def is_approval_decided(approval_id: str) -> bool:
    """Check if an approval has already been decided."""
    return find_approval_decided(approval_id) is not None


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
