"""Separation of Duties (SoD) enforcement - MVP."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .errors import SOD_VIOLATION, SOD_RULE_INVALID
from .ledger import get_ledger, LedgerEvent
from .actor_context import ActorContext


# Supported constraints
REQUESTER_NEQ_DECIDER = "REQUESTER_NEQ_DECIDER"
VALID_CONSTRAINTS = {REQUESTER_NEQ_DECIDER}


@dataclass
class SodRule:
    """SoD rule definition."""
    rule_name: str
    case_step: str
    constraint: str


class SodPolicy:
    """SoD policy loaded from sod.json."""

    def __init__(self, sod_data: Dict[str, Any]) -> None:
        """Initialize SoD policy from contract data."""
        self._rules: List[SodRule] = []
        self._step_rules: Dict[str, List[SodRule]] = {}
        self._load_rules(sod_data)

    def _load_rules(self, sod_data: Dict[str, Any]) -> None:
        """Load rules from SoD data."""
        rules = sod_data.get("rules", [])
        for rule in rules:
            rule_name = rule.get("rule_name", "")
            case_step = rule.get("case_step", "")
            constraint = rule.get("constraint", "")

            if rule_name and case_step and constraint:
                sod_rule = SodRule(
                    rule_name=rule_name,
                    case_step=case_step,
                    constraint=constraint,
                )
                self._rules.append(sod_rule)

                # Index by step
                if case_step not in self._step_rules:
                    self._step_rules[case_step] = []
                self._step_rules[case_step].append(sod_rule)

    def get_rules_for_step(self, step: str) -> List[SodRule]:
        """Get all SoD rules for a given step."""
        return self._step_rules.get(step, [])

    def all_rules(self) -> List[SodRule]:
        """Get all SoD rules."""
        return self._rules


# Per-department SoD policies (key: dept_id, None for single mode)
_sod_policies: Dict[Optional[str], SodPolicy] = {}


def set_sod_policy(policy: Optional[SodPolicy], dept_id: Optional[str] = None) -> None:
    """Set SoD policy for a department (or single mode).

    Args:
        policy: SodPolicy instance, or None to clear.
        dept_id: Department ID, or None for single mode.
    """
    if policy is None:
        _sod_policies.pop(dept_id, None)
    else:
        _sod_policies[dept_id] = policy


def get_sod_policy(dept_id: Optional[str] = None) -> Optional[SodPolicy]:
    """Get SoD policy for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.

    Returns:
        SodPolicy if set, None otherwise.
    """
    return _sod_policies.get(dept_id)


def reset_all_sod() -> None:
    """Reset all SoD policies (for testing)."""
    global _sod_policies
    _sod_policies = {}


def find_approval_requested_for_step(
    case_id: str,
    step: str,
) -> Optional[LedgerEvent]:
    """Find APPROVAL_REQUESTED event for case_id and step.

    Args:
        case_id: The case ID (approval_id).
        step: The step name (e.g., 'APPROVAL:expense.create').

    Returns:
        The APPROVAL_REQUESTED event if found, None otherwise.
    """
    ledger = get_ledger()
    if not ledger:
        return None

    events = ledger.get_all_events()
    for event in events:
        if (
            event.case_id == case_id
            and event.step == step
            and event.event_type == "APPROVAL_REQUESTED"
        ):
            return event

    return None


def check_sod(
    case_id: str,
    step: str,
    actor: ActorContext,
    dept_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check SoD constraints for a decision.

    Args:
        case_id: The case ID (approval_id).
        step: The step name.
        actor: The actor attempting to decide.
        dept_id: Department ID, or None for single mode.

    Returns:
        Tuple of (ok, error_code, message).
        - ok=True means no SoD violation.
        - ok=False means violation, with error_code and message.
    """
    policy = get_sod_policy(dept_id)
    if not policy:
        # No SoD policy - allow
        return (True, None, None)

    rules = policy.get_rules_for_step(step)
    if not rules:
        # No rules for this step - allow
        return (True, None, None)

    for rule in rules:
        if rule.constraint not in VALID_CONSTRAINTS:
            return (
                False,
                SOD_RULE_INVALID,
                f"Unknown constraint: {rule.constraint}",
            )

        if rule.constraint == REQUESTER_NEQ_DECIDER:
            # Find the APPROVAL_REQUESTED event
            requested_event = find_approval_requested_for_step(case_id, step)
            if requested_event:
                requested_by = requested_event.payload.get("requested_by")
                if requested_by and requested_by == actor.actor_id:
                    return (
                        False,
                        SOD_VIOLATION,
                        "Separation of duties violation",
                    )

    return (True, None, None)
