"""Apply answers to resolve gaps in draft IDL."""

from typing import Dict, Any, List, Optional, Tuple, Union
from copy import deepcopy

from engine.nl.schemas.answers_v1 import AnswersV1, Answer, Gap, Question
from engine.nl.schemas.sir_v1 import SIRv1, RuntimePolicy
from engine.nl.canonical import canonical_dict
from engine.nl.gap_detector import (
    GAP_POLICY_ID_MISSING,
    GAP_POLICY_ENDPOINT_INVALID,
    GAP_POLICY_FIELD_PATH_INVALID,
    GAP_POLICY_PHASE_INVALID,
    GAP_POLICY_RULE_TYPE_INVALID,
    GAP_POLICY_VALUE_MISSING,
)


def apply_answers(
    draft: Dict[str, Any],
    gaps: List[Gap],
    answers: AnswersV1,
) -> Tuple[Dict[str, Any], List[Gap]]:
    """Apply answers to resolve gaps and update draft.

    Args:
        draft: Draft IDL dictionary.
        gaps: List of detected gaps.
        answers: User answers to gap questions.

    Returns:
        Tuple of (updated_draft, remaining_gaps).

    Raises:
        ValueError: If answer references unknown question.
    """
    updated_draft = deepcopy(draft)
    remaining_gaps = []

    # Build question index
    question_index: Dict[str, Tuple[Gap, Question]] = {}
    for gap in gaps:
        for question in gap.questions:
            question_index[question.question_id] = (gap, question)

    # Track which gaps have all questions answered
    gap_answers: Dict[str, Dict[str, Any]] = {}  # gap_key -> {step: value}

    # Process answers
    for answer in answers.answers:
        if answer.question_id not in question_index:
            raise ValueError(f"Question not found: {answer.question_id}")

        gap, question = question_index[answer.question_id]

        if gap.gap_key not in gap_answers:
            gap_answers[gap.gap_key] = {}

        gap_answers[gap.gap_key][question.step] = answer.value

    # Apply answers to draft
    for gap in gaps:
        if gap.gap_key in gap_answers:
            answers_for_gap = gap_answers[gap.gap_key]

            # Check if all required questions are answered
            all_answered = all(
                q.step in answers_for_gap
                for q in gap.questions
            )

            if all_answered:
                # Apply the answers to the draft
                _apply_gap_answers(updated_draft, gap, answers_for_gap)
            else:
                # Gap still has unanswered questions
                remaining_questions = [
                    q for q in gap.questions
                    if q.step not in answers_for_gap
                ]
                remaining_gaps.append(Gap(
                    gap_key=gap.gap_key,
                    gap_type=gap.gap_type,
                    severity=gap.severity,
                    description=gap.description,
                    policy_ref=gap.policy_ref,
                    questions=remaining_questions,
                ))
        else:
            # Gap not addressed at all
            remaining_gaps.append(gap)

    return canonical_dict(updated_draft), sorted(remaining_gaps, key=lambda g: g.gap_key)


def _apply_gap_answers(
    draft: Dict[str, Any],
    gap: Gap,
    answers: Dict[str, Any],
) -> None:
    """Apply answers for a specific gap to the draft.

    Args:
        draft: Draft to modify in place.
        gap: Gap being resolved.
        answers: Map of step -> value for this gap.
    """
    if gap.gap_type == "approval":
        _apply_approval_answers(draft, gap, answers)
    elif gap.gap_type == "sod":
        _apply_sod_answers(draft, gap, answers)
    elif gap.gap_type == "identity":
        _apply_identity_answers(draft, gap, answers)
    elif gap.gap_type == "auth":
        _apply_auth_answers(draft, gap, answers)
    elif gap.gap_type == "invariant":
        _apply_invariant_answers(draft, gap, answers)
    elif gap.gap_type == "runtime_policy":
        _apply_runtime_policy_answers(draft, gap, answers)


def _apply_approval_answers(
    draft: Dict[str, Any],
    gap: Gap,
    answers: Dict[str, Any],
) -> None:
    """Apply approval-related answers."""
    # Extract entity from gap_key (e.g., "gap-approval-expense" -> "expense")
    entity = gap.gap_key.replace("gap-approval-", "").replace("-quorum", "")

    needs_approval = answers.get("needs_approval", True)
    if not needs_approval:
        return

    approver_roles = answers.get("approver_roles", "manager")
    if isinstance(approver_roles, str):
        approver_roles = [approver_roles]

    quorum = answers.get("quorum", 1)

    # Ensure approvals section exists
    if "approvals" not in draft:
        draft["approvals"] = {
            "version": "1.0",
            "name": "approvals",
            "rules": [],
        }

    rules = draft["approvals"].get("rules", [])

    # Check if rule already exists
    existing_rule = None
    for rule in rules:
        if rule.get("rule_name", "").startswith(entity):
            existing_rule = rule
            break

    if existing_rule:
        existing_rule["approver_roles"] = sorted(approver_roles)
        existing_rule["quorum"] = quorum
    else:
        rules.append({
            "rule_name": f"{entity}.create",
            "trigger": {"api": f"POST /finance/{entity}s"},
            "approver_roles": sorted(approver_roles),
            "quorum": quorum,
        })

    draft["approvals"]["rules"] = sorted(rules, key=lambda r: r["rule_name"])


def _apply_sod_answers(
    draft: Dict[str, Any],
    gap: Gap,
    answers: Dict[str, Any],
) -> None:
    """Apply SoD-related answers."""
    entity = gap.gap_key.replace("gap-sod-", "")

    no_self_approval = answers.get("no_self_approval", True)
    if not no_self_approval:
        return

    # Ensure sod section exists
    if "sod" not in draft:
        draft["sod"] = {
            "version": "1.0",
            "name": "sod",
            "rules": [],
        }

    rules = draft["sod"].get("rules", [])

    # Check if rule already exists
    exists = any(
        entity in r.get("rule_name", "") or
        r.get("scope", {}).get("entity") == entity
        for r in rules
    )

    if not exists:
        rules.append({
            "rule_name": f"no_self_approval_{entity}",
            "constraint": "no_self_approval",
            "scope": {"entity": entity},
        })

    draft["sod"]["rules"] = sorted(rules, key=lambda r: r["rule_name"])


def _apply_identity_answers(
    draft: Dict[str, Any],
    gap: Gap,
    answers: Dict[str, Any],
) -> None:
    """Apply identity-related answers."""
    # Identity gaps typically define missing roles
    missing_roles_text = answers.get("missing_roles", "")

    if not missing_roles_text:
        return

    # Ensure rbac section exists
    if "rbac" not in draft:
        draft["rbac"] = {
            "version": "1.0",
            "name": "rbac",
            "roles": [],
        }

    # Parse the text answer (comma-separated role definitions)
    # Format: "role_name: permission1, permission2; role_name2: ..."
    # For now, just add the role with default permissions
    roles = draft["rbac"].get("roles", [])
    existing_names = set(r.get("name", "") for r in roles)

    # Simple parsing - assume it's just role names
    for role_name in missing_roles_text.split(","):
        role_name = role_name.strip().lower()
        if role_name and role_name not in existing_names:
            roles.append({
                "name": role_name,
                "permissions": ["resource.read"],  # Default permission
            })
            existing_names.add(role_name)

    draft["rbac"]["roles"] = sorted(roles, key=lambda r: r["name"])


def _apply_auth_answers(
    draft: Dict[str, Any],
    gap: Gap,
    answers: Dict[str, Any],
) -> None:
    """Apply authentication-related answers."""
    auth_method = answers.get("auth_method", "header")

    draft["auth"] = {
        "method": auth_method,
    }


def _apply_invariant_answers(
    draft: Dict[str, Any],
    gap: Gap,
    answers: Dict[str, Any],
) -> None:
    """Apply invariant-related answers."""
    entity = gap.gap_key.replace("gap-invariant-", "")

    amount_min = answers.get("amount_min", 0.01)
    amount_max = answers.get("amount_max", 1000000)

    # Ensure invariants section exists
    if "invariants" not in draft:
        draft["invariants"] = {
            "version": "1.0",
            "name": "invariants",
        }

    draft["invariants"][entity] = {
        "amount": {
            "min": amount_min,
            "max": amount_max,
        },
        "description": {
            "max_len": 280,
            "required": False,
        },
    }


def _parse_policy_index_from_gap_key(gap_key: str) -> Tuple[Optional[str], int]:
    """Parse policy index and optional dept_id from gap key.

    Gap keys are formatted as:
    - gap-policy-000-xxx (single mode)
    - gap-policy-dept-finance-000-xxx (multi mode)

    Returns:
        Tuple of (dept_id or None, policy_index).
    """
    # Remove the gap-policy- prefix
    rest = gap_key.replace("gap-policy-", "")

    # Check if it's multi-dept mode (has dept- prefix)
    if rest.startswith("dept-"):
        # Format: dept-{dept_id}-{index}-{suffix}
        parts = rest.split("-")
        # parts[0] = "dept", parts[1] = dept_id, parts[2] = index, parts[3+] = suffix
        if len(parts) >= 3:
            dept_id = parts[1]
            try:
                index = int(parts[2])
                return dept_id, index
            except ValueError:
                pass
        return None, 0
    else:
        # Format: {index}-{suffix}
        parts = rest.split("-")
        if parts:
            try:
                index = int(parts[0])
                return None, index
            except ValueError:
                pass
        return None, 0


def _apply_runtime_policy_answers(
    draft: Dict[str, Any],
    gap: Gap,
    answers: Dict[str, Any],
) -> None:
    """Apply runtime policy-related answers.

    Updates the draft's policies or dept_policies section with the answered values.
    Does NOT auto-fix - only applies the exact answer provided by the user.

    Args:
        draft: Draft to modify in place.
        gap: Gap being resolved.
        answers: Map of step -> value for this gap.
    """
    # Parse the gap key to find which policy to update
    dept_id, policy_index = _parse_policy_index_from_gap_key(gap.gap_key)

    # Get the policies list to update
    if dept_id:
        if "dept_policies" not in draft:
            draft["dept_policies"] = {}
        if dept_id not in draft["dept_policies"]:
            draft["dept_policies"][dept_id] = []
        policies = draft["dept_policies"][dept_id]
    else:
        if "policies" not in draft:
            draft["policies"] = []
        policies = draft["policies"]

    # Ensure the policy exists at the specified index
    while len(policies) <= policy_index:
        policies.append({
            "policy_id": "",
            "phase": "",
            "endpoint_sig": "",
            "rule_type": "",
            "field_path": "",
        })

    policy = policies[policy_index]

    # Apply answers based on gap type (policy_ref contains the gap code)
    if gap.policy_ref == GAP_POLICY_ID_MISSING:
        policy["policy_id"] = answers.get("policy_id", "")
    elif gap.policy_ref == GAP_POLICY_ENDPOINT_INVALID:
        policy["endpoint_sig"] = answers.get("endpoint_sig", "")
    elif gap.policy_ref == GAP_POLICY_PHASE_INVALID:
        policy["phase"] = answers.get("phase", "")
    elif gap.policy_ref == GAP_POLICY_RULE_TYPE_INVALID:
        policy["rule_type"] = answers.get("rule_type", "")
    elif gap.policy_ref == GAP_POLICY_FIELD_PATH_INVALID:
        policy["field_path"] = answers.get("field_path", "")
    elif gap.policy_ref == GAP_POLICY_VALUE_MISSING:
        value = answers.get("value")
        if value is not None:
            policy["value"] = value
