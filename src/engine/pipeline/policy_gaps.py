"""Policy gaps helper utilities for pipeline."""

from typing import Any, Dict, List

from engine.nl.schemas.answers_v1 import Gap


def extract_policy_gaps(gaps: List[Gap]) -> List[Gap]:
    """Extract policy gaps from list of gaps.

    Policy gaps are identified by policy_ref starting with "GAP_POLICY_".

    Args:
        gaps: List of Gap objects.

    Returns:
        List of Gap objects that are policy gaps.
    """
    return [
        g for g in gaps
        if g.policy_ref and g.policy_ref.startswith("GAP_POLICY_")
    ]


def build_answers_template(gaps: List[Gap]) -> Dict[str, Any]:
    """Build answers_v1 template for filling gaps.

    Creates a template with null/empty placeholder values - does NOT invent values.
    Uses the same structure that answer_apply expects.

    Args:
        gaps: List of Gap objects to create template for.

    Returns:
        Dict following answers_v1 schema with placeholder values.
    """
    answers = []

    for gap in gaps:
        for question in gap.questions:
            answers.append({
                "question_id": question.question_id,
                "value": None,  # Placeholder - user must fill
            })

    return {
        "version": "1.0",
        "answers": sorted(answers, key=lambda x: x["question_id"]),
    }


def compute_policy_counts(
    gaps: List[Gap],
    runtime_policies_count: int = 0,
    dept_runtime_policies_count: int = 0,
) -> Dict[str, Any]:
    """Compute policy counts for trace.json.

    Args:
        gaps: List of Gap objects.
        runtime_policies_count: Count of runtime policies (single mode).
        dept_runtime_policies_count: Total count across all dept runtime policies.

    Returns:
        Dict with policy_count, policy_gap_count, has_policy_gaps.
    """
    policy_gaps = extract_policy_gaps(gaps)
    policy_gap_count = len(policy_gaps)

    return {
        "policy_count": runtime_policies_count + dept_runtime_policies_count,
        "policy_gap_count": policy_gap_count,
        "has_policy_gaps": policy_gap_count > 0,
    }
