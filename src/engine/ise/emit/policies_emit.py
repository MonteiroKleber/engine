"""Policies contract emitter for policies.json v1.1."""

import json
import re
from typing import Dict, Any, List

from engine.ise.idl_parser import IDLPolicy
from engine.ise.errors import ISE_POLICY_INVALID


# Allowed endpoint signatures (exact match only, no wildcards)
# Must match runtime core/policy.py ALLOWED_ENDPOINT_SIGS
ALLOWED_ENDPOINT_SIGS = frozenset({
    "POST /finance/expenses",
    "POST /approvals/{approval_id}/decide",
})

# Valid phases
ALLOWED_PHASES = frozenset({"pre", "post"})

# Valid rule types
ALLOWED_RULE_TYPES = frozenset({
    "numeric_max",
    "numeric_min",
    "string_max_len",
    "required_field",
    "enum_allowlist",
})

# Regex for valid field path tokens: only alphanumeric and underscore
_FIELD_TOKEN_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


class ISEPolicyValidationError(Exception):
    """Raised when policy validation fails during ISE compilation."""

    def __init__(self, code: str, message: str, details: List[Dict[str, Any]]):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


def validate_field_path(field_path: str) -> bool:
    """Validate field_path follows v1.1 rules.

    Rules:
    - Only characters [a-zA-Z0-9_.] allowed
    - Cannot start or end with '.'
    - Cannot have consecutive dots '..'
    - Each token must match [a-zA-Z0-9_]+

    Args:
        field_path: The field path to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not field_path:
        return False

    # Check for invalid characters (anything not alphanumeric, underscore, or dot)
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


def validate_policies_v11(policies: List[IDLPolicy]) -> None:
    """Validate policies against v1.1 schema rules.

    Raises ISEPolicyValidationError with details if validation fails.

    Args:
        policies: List of IDLPolicy objects to validate.

    Raises:
        ISEPolicyValidationError: If any policy is invalid.
    """
    errors: List[Dict[str, Any]] = []

    for policy in policies:
        # Validate endpoint_sig
        if policy.endpoint_sig not in ALLOWED_ENDPOINT_SIGS:
            errors.append({
                "policy_id": policy.policy_id,
                "field": "endpoint_sig",
                "code": "ENDPOINT_NOT_ALLOWED",
                "message": f"endpoint_sig '{policy.endpoint_sig}' not in allowed set: {sorted(ALLOWED_ENDPOINT_SIGS)}",
            })

        # Validate field_path
        if not validate_field_path(policy.field_path):
            errors.append({
                "policy_id": policy.policy_id,
                "field": "field_path",
                "code": "FIELD_PATH_INVALID",
                "message": f"field_path '{policy.field_path}' is invalid. Only [a-zA-Z0-9_.] allowed, no leading/trailing/consecutive dots.",
            })

        # Validate phase
        if policy.phase not in ALLOWED_PHASES:
            errors.append({
                "policy_id": policy.policy_id,
                "field": "phase",
                "code": "PHASE_INVALID",
                "message": f"phase '{policy.phase}' not in allowed set: {sorted(ALLOWED_PHASES)}",
            })

        # Validate rule_type
        if policy.rule_type not in ALLOWED_RULE_TYPES:
            errors.append({
                "policy_id": policy.policy_id,
                "field": "rule_type",
                "code": "RULE_TYPE_INVALID",
                "message": f"rule_type '{policy.rule_type}' not in allowed set: {sorted(ALLOWED_RULE_TYPES)}",
            })

    if errors:
        raise ISEPolicyValidationError(
            code=ISE_POLICY_INVALID,
            message=f"Policy validation failed with {len(errors)} error(s)",
            details=errors,
        )


def emit_policies_v11(policies: List[IDLPolicy]) -> Dict[str, Any]:
    """Emit policies.json v1.1 structure from IDLPolicy list.

    Args:
        policies: List of IDLPolicy objects.

    Returns:
        Dict with policy_schema_version "1.1" and policies array.
    """
    policies_list = []

    for policy in policies:
        policy_dict: Dict[str, Any] = {
            "policy_id": policy.policy_id,
            "phase": policy.phase,
            "endpoint_sig": policy.endpoint_sig,
            "rule_type": policy.rule_type,
            "field_path": policy.field_path,
        }

        # Include value if present
        if policy.value is not None:
            policy_dict["value"] = policy.value

        # Include message if present
        if policy.message:
            policy_dict["message"] = policy.message

        policies_list.append(policy_dict)

    return {
        "policy_schema_version": "1.1",
        "policies": policies_list,
    }


def emit_policies_json(policies: List[IDLPolicy]) -> str:
    """Emit policies.json v1.1 as JSON string.

    Validates policies before emitting.

    Args:
        policies: List of IDLPolicy objects.

    Returns:
        JSON string with sorted keys.

    Raises:
        ISEPolicyValidationError: If any policy is invalid.
    """
    # Validate first
    validate_policies_v11(policies)

    # Emit
    return json.dumps(emit_policies_v11(policies), indent=2, sort_keys=True)
