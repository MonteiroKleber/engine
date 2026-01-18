"""Gap Detection for Draft IDL."""

import re
from typing import Dict, Any, List, Optional

from engine.nl.schemas.sir_v1 import SIRv1, RuntimePolicy
from engine.nl.schemas.answers_v1 import Gap, Question, generate_question_id


# =============================================================================
# Runtime Policy v1.1 Constants (must match ISE emit/policies_emit.py)
# =============================================================================
ALLOWED_ENDPOINT_SIGS = frozenset({
    "POST /finance/expenses",
    "POST /approvals/{approval_id}/decide",
})

ALLOWED_PHASES = frozenset({"pre", "post"})

ALLOWED_RULE_TYPES = frozenset({
    "numeric_max",
    "numeric_min",
    "string_max_len",
    "required_field",
    "enum_allowlist",
})

# Field path validation pattern
_FIELD_TOKEN_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def _validate_field_path(field_path: str) -> bool:
    """Validate field_path follows v1.1 rules.

    Rules:
    - Only characters [a-zA-Z0-9_.] allowed
    - Cannot start or end with '.'
    - Cannot have consecutive dots '..'
    - Each token must match [a-zA-Z0-9_]+
    """
    if not field_path:
        return False

    # Check for invalid characters
    if not re.match(r"^[a-zA-Z0-9_.]+$", field_path):
        return False

    # Check for leading/trailing dots
    if field_path.startswith(".") or field_path.endswith("."):
        return False

    # Check for consecutive dots
    if ".." in field_path:
        return False

    # Split and validate each token
    tokens = field_path.split(".")
    for token in tokens:
        if not _FIELD_TOKEN_PATTERN.match(token):
            return False

    return True


# Gap codes for runtime policy validation
GAP_POLICY_ID_MISSING = "GAP_POLICY_ID_MISSING"
GAP_POLICY_ENDPOINT_INVALID = "GAP_POLICY_ENDPOINT_INVALID"
GAP_POLICY_FIELD_PATH_INVALID = "GAP_POLICY_FIELD_PATH_INVALID"
GAP_POLICY_PHASE_INVALID = "GAP_POLICY_PHASE_INVALID"
GAP_POLICY_RULE_TYPE_INVALID = "GAP_POLICY_RULE_TYPE_INVALID"
GAP_POLICY_VALUE_MISSING = "GAP_POLICY_VALUE_MISSING"


def detect_gaps(sir: SIRv1, draft: Dict[str, Any]) -> List[Gap]:
    """Detect gaps in the draft IDL that need clarification.

    Args:
        sir: Structured Intermediate Representation.
        draft: Draft IDL dictionary.

    Returns:
        List of detected gaps.
    """
    gaps = []

    # Check for approval gaps
    gaps.extend(_detect_approval_gaps(sir, draft))

    # Check for SoD gaps
    gaps.extend(_detect_sod_gaps(sir, draft))

    # Check for identity/auth gaps
    gaps.extend(_detect_identity_gaps(sir, draft))

    # Check for invariant gaps
    gaps.extend(_detect_invariant_gaps(sir, draft))

    # Check for runtime policy gaps (validates extracted policies)
    gaps.extend(_detect_runtime_policy_gaps(sir, draft))

    # Sort gaps by gap_key for determinism
    return sorted(gaps, key=lambda g: g.gap_key)


def _detect_approval_gaps(sir: SIRv1, draft: Dict[str, Any]) -> List[Gap]:
    """Detect gaps in approval configuration."""
    gaps = []

    approvals = draft.get("approvals", {})
    rules = approvals.get("rules", [])

    # Get entities from SIR
    entities = [e.entity_type for e in sir.extraction.entities]
    if not entities:
        entities = ["resource"]

    for entity in entities:
        # Check if entity has approval rule
        has_rule = any(r.get("rule_name", "").startswith(entity) for r in rules)

        if not has_rule:
            # No approval rule defined
            gap_key = f"gap-approval-{entity}"
            policy_key = f"policy-approval-{entity}"

            questions = [
                Question(
                    question_id=generate_question_id(gap_key, policy_key, "needs_approval"),
                    gap_key=gap_key,
                    policy_key=policy_key,
                    step="needs_approval",
                    question_text=f"Does {entity} creation require approval?",
                    question_type="boolean",
                    default_value=True,
                ),
                Question(
                    question_id=generate_question_id(gap_key, policy_key, "approver_roles"),
                    gap_key=gap_key,
                    policy_key=policy_key,
                    step="approver_roles",
                    question_text=f"Which roles can approve {entity}?",
                    question_type="choice",
                    options=["manager", "admin", "supervisor", "director"],
                    default_value="manager",
                ),
                Question(
                    question_id=generate_question_id(gap_key, policy_key, "quorum"),
                    gap_key=gap_key,
                    policy_key=policy_key,
                    step="quorum",
                    question_text=f"How many approvals are required for {entity}?",
                    question_type="number",
                    default_value=1,
                ),
            ]

            gaps.append(Gap(
                gap_key=gap_key,
                gap_type="approval",
                severity="required",
                description=f"Approval requirements for {entity} not specified",
                policy_ref=policy_key,
                questions=questions,
            ))
        else:
            # Check if quorum is specified
            for rule in rules:
                if rule.get("rule_name", "").startswith(entity):
                    if "quorum" not in rule or rule.get("quorum", 0) < 1:
                        gap_key = f"gap-approval-quorum-{entity}"
                        policy_key = rule.get("rule_name", f"policy-approval-{entity}")

                        gaps.append(Gap(
                            gap_key=gap_key,
                            gap_type="approval",
                            severity="recommended",
                            description=f"Approval quorum for {entity} not specified",
                            policy_ref=policy_key,
                            questions=[
                                Question(
                                    question_id=generate_question_id(gap_key, policy_key, "quorum"),
                                    gap_key=gap_key,
                                    policy_key=policy_key,
                                    step="quorum",
                                    question_text=f"How many approvals are required for {entity}?",
                                    question_type="number",
                                    default_value=1,
                                ),
                            ],
                        ))

    return gaps


def _detect_sod_gaps(sir: SIRv1, draft: Dict[str, Any]) -> List[Gap]:
    """Detect gaps in SoD configuration."""
    gaps = []

    sod = draft.get("sod", {})
    rules = sod.get("rules", [])

    # Check if SoD was mentioned in policies
    has_sod_policy = any(
        p.policy_type == "sod" for p in sir.extraction.policies
    )

    # Get entities
    entities = [e.entity_type for e in sir.extraction.entities]
    if not entities:
        entities = ["resource"]

    for entity in entities:
        # Check if entity has SoD rule
        has_rule = any(
            entity in r.get("rule_name", "") or
            r.get("scope", {}).get("entity") == entity
            for r in rules
        )

        if not has_rule:
            gap_key = f"gap-sod-{entity}"
            policy_key = f"policy-sod-{entity}"

            questions = [
                Question(
                    question_id=generate_question_id(gap_key, policy_key, "no_self_approval"),
                    gap_key=gap_key,
                    policy_key=policy_key,
                    step="no_self_approval",
                    question_text=f"Should self-approval be blocked for {entity}?",
                    question_type="boolean",
                    default_value=True,
                ),
            ]

            gaps.append(Gap(
                gap_key=gap_key,
                gap_type="sod",
                severity="recommended" if not has_sod_policy else "required",
                description=f"Segregation of duties for {entity} not specified",
                policy_ref=policy_key,
                questions=questions,
            ))

    return gaps


def _detect_identity_gaps(sir: SIRv1, draft: Dict[str, Any]) -> List[Gap]:
    """Detect gaps in identity/authentication configuration."""
    gaps = []

    rbac = draft.get("rbac", {})
    roles = rbac.get("roles", [])

    # Check if there are actors without roles in RBAC
    actor_roles = set()
    for actor in sir.extraction.actors:
        actor_roles.update(actor.roles)

    rbac_roles = set(r.get("name", "") for r in roles)

    missing_roles = actor_roles - rbac_roles
    if missing_roles:
        gap_key = "gap-identity-roles"
        policy_key = "policy-rbac"

        questions = [
            Question(
                question_id=generate_question_id(gap_key, policy_key, "missing_roles"),
                gap_key=gap_key,
                policy_key=policy_key,
                step="missing_roles",
                question_text=f"Define permissions for roles: {', '.join(sorted(missing_roles))}",
                question_type="text",
            ),
        ]

        gaps.append(Gap(
            gap_key=gap_key,
            gap_type="identity",
            severity="required",
            description=f"Roles {sorted(missing_roles)} not defined in RBAC",
            policy_ref=policy_key,
            questions=questions,
        ))

    # Check if authentication method is specified
    if not draft.get("auth"):
        gap_key = "gap-auth-method"
        policy_key = "policy-auth"

        questions = [
            Question(
                question_id=generate_question_id(gap_key, policy_key, "auth_method"),
                gap_key=gap_key,
                policy_key=policy_key,
                step="auth_method",
                question_text="What authentication method should be used?",
                question_type="choice",
                options=["header", "jwt", "oauth2", "api_key"],
                default_value="header",
            ),
        ]

        gaps.append(Gap(
            gap_key=gap_key,
            gap_type="auth",
            severity="optional",
            description="Authentication method not specified",
            policy_ref=policy_key,
            questions=questions,
        ))

    return gaps


def _detect_invariant_gaps(sir: SIRv1, draft: Dict[str, Any]) -> List[Gap]:
    """Detect gaps in invariant configuration."""
    gaps = []

    invariants = draft.get("invariants", {})

    # Get entities
    entities = [e.entity_type for e in sir.extraction.entities]
    if not entities:
        entities = ["resource"]

    for entity in entities:
        if entity not in invariants:
            # Check if invariant was mentioned in policies
            has_invariant_policy = any(
                p.policy_type == "invariant" and
                any(e.entity_key in p.entity_refs for e in sir.extraction.entities if e.entity_type == entity)
                for p in sir.extraction.policies
            )

            if has_invariant_policy:
                gap_key = f"gap-invariant-{entity}"
                policy_key = f"policy-invariant-{entity}"

                questions = [
                    Question(
                        question_id=generate_question_id(gap_key, policy_key, "amount_min"),
                        gap_key=gap_key,
                        policy_key=policy_key,
                        step="amount_min",
                        question_text=f"What is the minimum amount for {entity}?",
                        question_type="number",
                        default_value=0.01,
                    ),
                    Question(
                        question_id=generate_question_id(gap_key, policy_key, "amount_max"),
                        gap_key=gap_key,
                        policy_key=policy_key,
                        step="amount_max",
                        question_text=f"What is the maximum amount for {entity}?",
                        question_type="number",
                        default_value=1000000,
                    ),
                ]

                gaps.append(Gap(
                    gap_key=gap_key,
                    gap_type="invariant",
                    severity="recommended",
                    description=f"Invariants for {entity} not fully specified",
                    policy_ref=policy_key,
                    questions=questions,
                ))

    return gaps


def _validate_single_runtime_policy(
    policy: RuntimePolicy,
    policy_index: int,
    dept_id: Optional[str] = None,
) -> List[Gap]:
    """Validate a single runtime policy and return gaps for any issues.

    Does NOT auto-fix. Creates gaps requiring user answers.

    Args:
        policy: The runtime policy to validate.
        policy_index: Index of policy for gap key generation.
        dept_id: Optional dept ID for multi-dept mode.

    Returns:
        List of gaps for this policy.
    """
    gaps = []
    prefix = f"dept-{dept_id}-" if dept_id else ""
    base_gap_key = f"gap-policy-{prefix}{policy_index:03d}"

    # Check policy_id is present
    if not policy.policy_id or not policy.policy_id.strip():
        gap_key = f"{base_gap_key}-id"
        gaps.append(Gap(
            gap_key=gap_key,
            gap_type="runtime_policy",
            severity="required",
            description=f"Policy #{policy_index} is missing policy_id",
            policy_ref=GAP_POLICY_ID_MISSING,
            questions=[
                Question(
                    question_id=generate_question_id(gap_key, GAP_POLICY_ID_MISSING, "policy_id"),
                    gap_key=gap_key,
                    policy_key=GAP_POLICY_ID_MISSING,
                    step="policy_id",
                    question_text=f"What is the policy ID for policy #{policy_index}?",
                    question_type="text",
                ),
            ],
        ))

    # Check endpoint_sig is valid
    if policy.endpoint_sig not in ALLOWED_ENDPOINT_SIGS:
        gap_key = f"{base_gap_key}-endpoint"
        gaps.append(Gap(
            gap_key=gap_key,
            gap_type="runtime_policy",
            severity="required",
            description=f"Policy '{policy.policy_id}' has invalid endpoint_sig: '{policy.endpoint_sig}'",
            policy_ref=GAP_POLICY_ENDPOINT_INVALID,
            questions=[
                Question(
                    question_id=generate_question_id(gap_key, GAP_POLICY_ENDPOINT_INVALID, "endpoint_sig"),
                    gap_key=gap_key,
                    policy_key=GAP_POLICY_ENDPOINT_INVALID,
                    step="endpoint_sig",
                    question_text=f"Select valid endpoint for policy '{policy.policy_id}'",
                    question_type="choice",
                    options=sorted(ALLOWED_ENDPOINT_SIGS),
                ),
            ],
        ))

    # Check phase is valid
    if policy.phase not in ALLOWED_PHASES:
        gap_key = f"{base_gap_key}-phase"
        gaps.append(Gap(
            gap_key=gap_key,
            gap_type="runtime_policy",
            severity="required",
            description=f"Policy '{policy.policy_id}' has invalid phase: '{policy.phase}'",
            policy_ref=GAP_POLICY_PHASE_INVALID,
            questions=[
                Question(
                    question_id=generate_question_id(gap_key, GAP_POLICY_PHASE_INVALID, "phase"),
                    gap_key=gap_key,
                    policy_key=GAP_POLICY_PHASE_INVALID,
                    step="phase",
                    question_text=f"Select valid phase for policy '{policy.policy_id}'",
                    question_type="choice",
                    options=sorted(ALLOWED_PHASES),
                ),
            ],
        ))

    # Check rule_type is valid
    if policy.rule_type not in ALLOWED_RULE_TYPES:
        gap_key = f"{base_gap_key}-rule-type"
        gaps.append(Gap(
            gap_key=gap_key,
            gap_type="runtime_policy",
            severity="required",
            description=f"Policy '{policy.policy_id}' has invalid rule_type: '{policy.rule_type}'",
            policy_ref=GAP_POLICY_RULE_TYPE_INVALID,
            questions=[
                Question(
                    question_id=generate_question_id(gap_key, GAP_POLICY_RULE_TYPE_INVALID, "rule_type"),
                    gap_key=gap_key,
                    policy_key=GAP_POLICY_RULE_TYPE_INVALID,
                    step="rule_type",
                    question_text=f"Select valid rule_type for policy '{policy.policy_id}'",
                    question_type="choice",
                    options=sorted(ALLOWED_RULE_TYPES),
                ),
            ],
        ))

    # Check field_path is valid
    if not _validate_field_path(policy.field_path):
        gap_key = f"{base_gap_key}-field-path"
        gaps.append(Gap(
            gap_key=gap_key,
            gap_type="runtime_policy",
            severity="required",
            description=f"Policy '{policy.policy_id}' has invalid field_path: '{policy.field_path}'",
            policy_ref=GAP_POLICY_FIELD_PATH_INVALID,
            questions=[
                Question(
                    question_id=generate_question_id(gap_key, GAP_POLICY_FIELD_PATH_INVALID, "field_path"),
                    gap_key=gap_key,
                    policy_key=GAP_POLICY_FIELD_PATH_INVALID,
                    step="field_path",
                    question_text=f"Enter valid field_path for policy '{policy.policy_id}' (e.g., 'amount', 'payload.amount')",
                    question_type="text",
                ),
            ],
        ))

    # Check value is present for rules that require it
    rules_requiring_value = {"numeric_max", "numeric_min", "string_max_len", "enum_allowlist"}
    if policy.rule_type in rules_requiring_value and policy.value is None:
        gap_key = f"{base_gap_key}-value"
        question_type = "number" if policy.rule_type != "enum_allowlist" else "text"
        gaps.append(Gap(
            gap_key=gap_key,
            gap_type="runtime_policy",
            severity="required",
            description=f"Policy '{policy.policy_id}' with rule_type '{policy.rule_type}' requires a value",
            policy_ref=GAP_POLICY_VALUE_MISSING,
            questions=[
                Question(
                    question_id=generate_question_id(gap_key, GAP_POLICY_VALUE_MISSING, "value"),
                    gap_key=gap_key,
                    policy_key=GAP_POLICY_VALUE_MISSING,
                    step="value",
                    question_text=f"Enter value for policy '{policy.policy_id}' ({policy.rule_type})",
                    question_type=question_type,
                ),
            ],
        ))

    return gaps


def _detect_runtime_policy_gaps(sir: SIRv1, draft: Dict[str, Any]) -> List[Gap]:
    """Detect gaps in runtime policy validation.

    Validates extracted runtime policies against v1.1 schema rules.
    Does NOT auto-fix - creates gaps requiring user answers.

    Args:
        sir: Structured Intermediate Representation.
        draft: Draft IDL dictionary.

    Returns:
        List of gaps for invalid policies.
    """
    gaps = []

    # Validate single-mode runtime policies
    for i, policy in enumerate(sir.extraction.runtime_policies):
        gaps.extend(_validate_single_runtime_policy(policy, i))

    # Validate multi-dept runtime policies
    for dept_id, policies in sorted(sir.extraction.dept_runtime_policies.items()):
        for i, policy in enumerate(policies):
            gaps.extend(_validate_single_runtime_policy(policy, i, dept_id))

    return gaps


def gaps_to_dict(gaps: List[Gap]) -> Dict[str, Any]:
    """Convert gaps list to dictionary format.

    Args:
        gaps: List of Gap objects.

    Returns:
        Dictionary with gaps array.
    """
    return {
        "version": "1.0",
        "gaps": sorted([g.to_dict() for g in gaps], key=lambda x: x["gap_key"]),
    }
