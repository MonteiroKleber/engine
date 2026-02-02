"""Finalize draft IDL to production-ready format."""

import re
from typing import Dict, Any, List, Optional, Tuple
from copy import deepcopy

from engine.nl.schemas.answers_v1 import Gap
from engine.nl.canonical import canonical_dict
from engine.nl.errors import NL_POLICY_INVALID


# =============================================================================
# Runtime Policy v1.1 Constants
# =============================================================================
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
    """Validate field_path follows v1.1 rules."""
    if not field_path:
        return False
    if not re.match(r"^[a-zA-Z0-9_.]+$", field_path):
        return False
    if field_path.startswith(".") or field_path.endswith("."):
        return False
    if ".." in field_path:
        return False
    for token in field_path.split("."):
        if not _FIELD_TOKEN_PATTERN.match(token):
            return False
    return True


class NLPolicyValidationError(Exception):
    """Raised when policy validation fails during NL finalization."""

    def __init__(self, code: str, message: str, details: List[Dict[str, Any]]):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


def finalize(
    draft: Dict[str, Any],
    remaining_gaps: List[Gap],
    allow_gaps: bool = False,
) -> Dict[str, Any]:
    """Finalize draft IDL to production format.

    Args:
        draft: Draft IDL dictionary.
        remaining_gaps: List of unresolved gaps.
        allow_gaps: If True, allow finalization with gaps (adds warnings).

    Returns:
        Final IDL dictionary.

    Raises:
        ValueError: If there are remaining required gaps and allow_gaps is False.
        NLPolicyValidationError: If runtime policies are invalid.
    """
    # Check for required gaps
    required_gaps = [g for g in remaining_gaps if g.severity == "required"]

    if required_gaps and not allow_gaps:
        gap_descriptions = [g.description for g in required_gaps]
        raise ValueError(
            f"Cannot finalize with {len(required_gaps)} required gaps: "
            f"{'; '.join(gap_descriptions)}"
        )

    # Start with a copy of the draft
    final = deepcopy(draft)

    # Remove draft-specific metadata
    final.pop("generated_from", None)

    # Ensure all required sections exist
    final = _ensure_required_sections(final)

    # Validate and clean each section
    final = _validate_rbac(final)
    final = _validate_approvals(final)
    final = _validate_sod(final)
    final = _validate_invariants(final)

    # Validate runtime policies - this raises NLPolicyValidationError on failure
    final = _validate_runtime_policies(final)

    # Add finalization metadata
    final["version"] = final.get("version", "1.0")
    final["name"] = final.get("name", "policy").replace("draft-", "")

    # Add warnings if there are remaining gaps
    if remaining_gaps:
        warnings = []
        for gap in remaining_gaps:
            warnings.append({
                "gap_key": gap.gap_key,
                "severity": gap.severity,
                "description": gap.description,
            })
        final["_warnings"] = sorted(warnings, key=lambda w: w["gap_key"])

    return canonical_dict(final)


def _ensure_required_sections(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all required sections exist with defaults."""
    if "rbac" not in draft:
        draft["rbac"] = {
            "version": "1.0",
            "name": "rbac",
            "roles": [],
        }

    return draft


def _validate_rbac(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean RBAC section."""
    rbac = draft.get("rbac", {})

    # Ensure roles is a list
    roles = rbac.get("roles", [])

    # Validate each role
    validated_roles = []
    for role in roles:
        if not role.get("name"):
            continue

        validated_roles.append({
            "name": role["name"].lower(),
            "permissions": sorted(role.get("permissions", [])),
        })

    # Sort and deduplicate
    seen = set()
    unique_roles = []
    for role in sorted(validated_roles, key=lambda r: r["name"]):
        if role["name"] not in seen:
            seen.add(role["name"])
            unique_roles.append(role)

    draft["rbac"] = {
        "version": rbac.get("version", "1.0"),
        "name": rbac.get("name", "rbac"),
        "roles": unique_roles,
    }

    return draft


def _validate_approvals(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean Approvals section."""
    if "approvals" not in draft:
        return draft

    approvals = draft["approvals"]
    rules = approvals.get("rules", [])

    # Validate each rule
    validated_rules = []
    for rule in rules:
        if not rule.get("rule_name"):
            continue

        validated_rule = {
            "rule_name": rule["rule_name"],
            "trigger": rule.get("trigger", {}),
            "approver_roles": sorted(rule.get("approver_roles", ["manager"])),
            "quorum": max(1, rule.get("quorum", 1)),
        }
        validated_rules.append(validated_rule)

    draft["approvals"] = {
        "version": approvals.get("version", "1.0"),
        "name": approvals.get("name", "approvals"),
        "rules": sorted(validated_rules, key=lambda r: r["rule_name"]),
    }

    return draft


def _validate_sod(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean SoD section."""
    if "sod" not in draft:
        return draft

    sod = draft["sod"]
    rules = sod.get("rules", [])

    # Validate each rule
    validated_rules = []
    for rule in rules:
        if not rule.get("rule_name"):
            continue

        validated_rule = {
            "rule_name": rule["rule_name"],
            "constraint": rule.get("constraint", "no_self_approval"),
        }
        if "scope" in rule:
            validated_rule["scope"] = rule["scope"]
        validated_rules.append(validated_rule)

    draft["sod"] = {
        "version": sod.get("version", "1.0"),
        "name": sod.get("name", "sod"),
        "rules": sorted(validated_rules, key=lambda r: r["rule_name"]),
    }

    return draft


def _validate_invariants(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean Invariants section."""
    if "invariants" not in draft:
        return draft

    invariants = draft["invariants"]

    # Keep version and name, validate entity schemas
    validated = {
        "version": invariants.get("version", "1.0"),
        "name": invariants.get("name", "invariants"),
    }

    for key, value in sorted(invariants.items()):
        if key in ("version", "name"):
            continue

        if isinstance(value, dict):
            validated[key] = _validate_entity_schema(value)

    draft["invariants"] = validated

    return draft


def _validate_entity_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an entity schema."""
    validated = {}

    for field, constraints in sorted(schema.items()):
        if not isinstance(constraints, dict):
            continue

        validated_constraints = {}
        for key, value in sorted(constraints.items()):
            if key in ("min", "max", "max_len", "required"):
                validated_constraints[key] = value

        if validated_constraints:
            validated[field] = validated_constraints

    return validated


def _validate_single_policy(policy: Dict[str, Any], index: int, dept_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Validate a single runtime policy dict.

    Returns list of validation error details.
    """
    errors = []
    policy_id = policy.get("policy_id", f"<unknown-{index}>")
    prefix = f"dept:{dept_id}:" if dept_id else ""

    # Validate policy_id
    if not policy.get("policy_id"):
        errors.append({
            "policy_id": policy_id,
            "field": "policy_id",
            "code": "POLICY_ID_MISSING",
            "message": f"{prefix}Policy #{index} is missing policy_id",
        })

    # Validate phase
    phase = policy.get("phase", "")
    if phase not in ALLOWED_PHASES:
        errors.append({
            "policy_id": policy_id,
            "field": "phase",
            "code": "PHASE_INVALID",
            "message": f"{prefix}phase '{phase}' not in allowed set: {sorted(ALLOWED_PHASES)}",
        })

    # Validate rule_type
    rule_type = policy.get("rule_type", "")
    if rule_type not in ALLOWED_RULE_TYPES:
        errors.append({
            "policy_id": policy_id,
            "field": "rule_type",
            "code": "RULE_TYPE_INVALID",
            "message": f"{prefix}rule_type '{rule_type}' not in allowed set: {sorted(ALLOWED_RULE_TYPES)}",
        })

    # Validate field_path
    field_path = policy.get("field_path", "")
    if not _validate_field_path(field_path):
        errors.append({
            "policy_id": policy_id,
            "field": "field_path",
            "code": "FIELD_PATH_INVALID",
            "message": f"{prefix}field_path '{field_path}' is invalid. Only [a-zA-Z0-9_.] allowed, no leading/trailing/consecutive dots.",
        })

    # Validate value for rules that require it
    rules_requiring_value = {"numeric_max", "numeric_min", "string_max_len", "enum_allowlist"}
    if rule_type in rules_requiring_value and policy.get("value") is None:
        errors.append({
            "policy_id": policy_id,
            "field": "value",
            "code": "VALUE_MISSING",
            "message": f"{prefix}rule_type '{rule_type}' requires a value",
        })

    return errors


def _validate_runtime_policies(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean runtime policies section.

    Raises NLPolicyValidationError if any policy is invalid.
    """
    errors: List[Dict[str, Any]] = []

    # Validate single-mode policies
    policies = draft.get("policies", [])
    validated_policies = []
    for i, policy in enumerate(policies):
        policy_errors = _validate_single_policy(policy, i)
        errors.extend(policy_errors)
        # Keep the policy as-is (no auto-fix)
        validated_policies.append(policy)

    if validated_policies:
        draft["policies"] = sorted(validated_policies, key=lambda p: p.get("policy_id", ""))

    # Validate multi-dept policies
    dept_policies = draft.get("dept_policies", {})
    validated_dept_policies: Dict[str, List[Dict[str, Any]]] = {}
    for dept_id, dept_policy_list in sorted(dept_policies.items()):
        validated_list = []
        for i, policy in enumerate(dept_policy_list):
            policy_errors = _validate_single_policy(policy, i, dept_id)
            errors.extend(policy_errors)
            # Keep the policy as-is (no auto-fix)
            validated_list.append(policy)
        validated_dept_policies[dept_id] = sorted(validated_list, key=lambda p: p.get("policy_id", ""))

    if validated_dept_policies:
        draft["dept_policies"] = dict(sorted(validated_dept_policies.items()))

    # Raise error if any validation failed
    if errors:
        raise NLPolicyValidationError(
            code=NL_POLICY_INVALID,
            message=f"Policy validation failed with {len(errors)} error(s)",
            details=errors,
        )

    return draft


def validate_final(idl: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate finalized IDL for completeness.

    Args:
        idl: Finalized IDL dictionary.

    Returns:
        Tuple of (is_valid, list of validation errors).
    """
    errors = []

    # Check version
    if "version" not in idl:
        errors.append("Missing 'version' field")

    # Check name
    if "name" not in idl:
        errors.append("Missing 'name' field")

    # Check RBAC
    rbac = idl.get("rbac", {})
    if not rbac.get("roles"):
        errors.append("RBAC has no roles defined")

    # Check for warnings
    if "_warnings" in idl:
        warnings = idl["_warnings"]
        required_warnings = [w for w in warnings if w.get("severity") == "required"]
        if required_warnings:
            for w in required_warnings:
                errors.append(f"Unresolved required gap: {w.get('description', w.get('gap_key'))}")

    return (len(errors) == 0, errors)
