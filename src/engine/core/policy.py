"""Policy Engine MVP - pre/post enforcement with ledger events."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .ledger import get_ledger
from .actor_context import ActorContext
from .errors import POLICY_ENDPOINT_UNKNOWN, POLICY_PATH_INVALID, POLICY_INVALID


# Allowed endpoint signatures (exact match only, no wildcards)
ALLOWED_ENDPOINT_SIGS = frozenset({
    "POST /finance/expenses",
    "POST /approvals/{approval_id}/decide",
})

# Regex for valid field path tokens: only alphanumeric and underscore
_FIELD_TOKEN_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


class PolicySchemaError(Exception):
    """Raised when policy schema validation fails."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_endpoint_sig(endpoint_sig: str) -> None:
    """Validate that endpoint_sig is in the allowed set.

    Args:
        endpoint_sig: The endpoint signature to validate.

    Raises:
        PolicySchemaError: If endpoint_sig is not allowed.
    """
    if endpoint_sig not in ALLOWED_ENDPOINT_SIGS:
        raise PolicySchemaError(
            code=POLICY_ENDPOINT_UNKNOWN,
            message=f"Unknown endpoint_sig: '{endpoint_sig}'. "
            f"Allowed values: {sorted(ALLOWED_ENDPOINT_SIGS)}",
        )


def validate_field_path(field_path: str) -> List[str]:
    """Validate and parse a field path into tokens.

    Rules:
    - Only characters [a-zA-Z0-9_.] allowed
    - Cannot start or end with '.'
    - Cannot have consecutive dots '..'
    - Each token must match [a-zA-Z0-9_]+

    Args:
        field_path: The field path to validate (e.g., "amount" or "payload.amount").

    Returns:
        List of validated tokens.

    Raises:
        PolicySchemaError: If field_path is invalid.
    """
    if not field_path:
        raise PolicySchemaError(
            code=POLICY_PATH_INVALID,
            message="field_path cannot be empty",
        )

    # Check for invalid characters (anything not alphanumeric, underscore, or dot)
    if not re.match(r"^[a-zA-Z0-9_.]+$", field_path):
        raise PolicySchemaError(
            code=POLICY_PATH_INVALID,
            message=f"field_path '{field_path}' contains invalid characters. "
            "Only [a-zA-Z0-9_.] allowed.",
        )

    # Check for leading/trailing dots
    if field_path.startswith(".") or field_path.endswith("."):
        raise PolicySchemaError(
            code=POLICY_PATH_INVALID,
            message=f"field_path '{field_path}' cannot start or end with '.'",
        )

    # Check for consecutive dots
    if ".." in field_path:
        raise PolicySchemaError(
            code=POLICY_PATH_INVALID,
            message=f"field_path '{field_path}' cannot contain consecutive dots '..'",
        )

    # Split and validate each token
    tokens = field_path.split(".")
    for token in tokens:
        if not _FIELD_TOKEN_PATTERN.match(token):
            raise PolicySchemaError(
                code=POLICY_PATH_INVALID,
                message=f"field_path token '{token}' is invalid. "
                "Only [a-zA-Z0-9_] allowed in tokens.",
            )

    return tokens


@dataclass
class PolicyRule:
    """A single policy rule definition."""

    policy_id: str
    rule_type: str  # numeric_max, numeric_min, string_max_len, required_field, enum_allowlist
    field_path: str  # dot notation e.g. "amount" or "payload.amount"
    field_path_tokens: List[str]  # pre-validated tokens from field_path
    phase: str  # "pre" or "post"
    endpoint_sig: str  # e.g. "POST /finance/expenses" (exact match, no wildcards)
    value: Any = None  # threshold value for comparison rules
    message: str = ""  # custom error message


@dataclass
class PolicyDef:
    """Policy definition containing multiple rules."""

    policies: List[PolicyRule] = field(default_factory=list)


@dataclass
class PolicyViolation:
    """Describes a policy violation."""

    policy_id: str
    rule_type: str
    field_path: str
    message: str
    actual_value: Any = None
    threshold_value: Any = None


@dataclass
class PolicyEvalResult:
    """Result of policy evaluation."""

    allow: bool
    violations: List[PolicyViolation] = field(default_factory=list)
    matched_policies: List[str] = field(default_factory=list)


# Global policies per department
# Key: dept_id (or "_single" for single-mode)
_policies: Dict[str, PolicyDef] = {}

SINGLE_MODE_KEY = "_single"


def set_policies(dept_id: Optional[str], policy_def: Optional[PolicyDef]) -> None:
    """Set policies for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.
        policy_def: Policy definition, or None to clear.
    """
    key = dept_id or SINGLE_MODE_KEY
    if policy_def is None:
        _policies.pop(key, None)
    else:
        _policies[key] = policy_def


def get_policies(dept_id: Optional[str]) -> Optional[PolicyDef]:
    """Get policies for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.

    Returns:
        PolicyDef if found, None otherwise.
    """
    key = dept_id or SINGLE_MODE_KEY
    return _policies.get(key)


def clear_all_policies() -> None:
    """Clear all policies (for testing)."""
    _policies.clear()


def _get_field_value_by_tokens(payload: Dict[str, Any], tokens: List[str]) -> Tuple[bool, Any]:
    """Get a value from nested dict using pre-validated tokens.

    Args:
        payload: The payload dict.
        tokens: Pre-validated list of path tokens.

    Returns:
        Tuple of (found: bool, value: Any).
    """
    current = payload
    for token in tokens:
        if not isinstance(current, dict):
            return False, None
        if token not in current:
            return False, None
        current = current[token]
    return True, current


def _evaluate_rule(
    rule: PolicyRule, payload: Dict[str, Any]
) -> Tuple[bool, Optional[PolicyViolation]]:
    """Evaluate a single policy rule.

    For v1.1 hardening: field missing = violation (deny) for all rule types
    to prevent bypass attacks.

    Args:
        rule: The policy rule to evaluate.
        payload: The request payload.

    Returns:
        Tuple of (pass: bool, violation: Optional[PolicyViolation]).
    """
    found, value = _get_field_value_by_tokens(payload, rule.field_path_tokens)

    if rule.rule_type == "required_field":
        if not found or value is None:
            return False, PolicyViolation(
                policy_id=rule.policy_id,
                rule_type=rule.rule_type,
                field_path=rule.field_path,
                message=rule.message or f"Required field '{rule.field_path}' is missing",
                actual_value=None,
                threshold_value=None,
            )
        return True, None

    if rule.rule_type == "numeric_max":
        # v1.1: field missing = violation (deny)
        if not found:
            return False, PolicyViolation(
                policy_id=rule.policy_id,
                rule_type=rule.rule_type,
                field_path=rule.field_path,
                message=rule.message or f"Field '{rule.field_path}' is missing",
                actual_value=None,
                threshold_value=rule.value,
            )
        try:
            num_value = float(value)
            threshold = float(rule.value)
            if num_value > threshold:
                return False, PolicyViolation(
                    policy_id=rule.policy_id,
                    rule_type=rule.rule_type,
                    field_path=rule.field_path,
                    message=rule.message
                    or f"Value {num_value} exceeds maximum {threshold}",
                    actual_value=num_value,
                    threshold_value=threshold,
                )
        except (TypeError, ValueError):
            # Non-numeric value - violation
            return False, PolicyViolation(
                policy_id=rule.policy_id,
                rule_type=rule.rule_type,
                field_path=rule.field_path,
                message=rule.message or f"Field '{rule.field_path}' is not a valid number",
                actual_value=value,
                threshold_value=rule.value,
            )
        return True, None

    if rule.rule_type == "numeric_min":
        # v1.1: field missing = violation (deny)
        if not found:
            return False, PolicyViolation(
                policy_id=rule.policy_id,
                rule_type=rule.rule_type,
                field_path=rule.field_path,
                message=rule.message or f"Field '{rule.field_path}' is missing",
                actual_value=None,
                threshold_value=rule.value,
            )
        try:
            num_value = float(value)
            threshold = float(rule.value)
            if num_value < threshold:
                return False, PolicyViolation(
                    policy_id=rule.policy_id,
                    rule_type=rule.rule_type,
                    field_path=rule.field_path,
                    message=rule.message
                    or f"Value {num_value} is below minimum {threshold}",
                    actual_value=num_value,
                    threshold_value=threshold,
                )
        except (TypeError, ValueError):
            # Non-numeric value - violation
            return False, PolicyViolation(
                policy_id=rule.policy_id,
                rule_type=rule.rule_type,
                field_path=rule.field_path,
                message=rule.message or f"Field '{rule.field_path}' is not a valid number",
                actual_value=value,
                threshold_value=rule.value,
            )
        return True, None

    if rule.rule_type == "string_max_len":
        # v1.1: field missing = violation (deny)
        if not found:
            return False, PolicyViolation(
                policy_id=rule.policy_id,
                rule_type=rule.rule_type,
                field_path=rule.field_path,
                message=rule.message or f"Field '{rule.field_path}' is missing",
                actual_value=None,
                threshold_value=rule.value,
            )
        if isinstance(value, str):
            threshold = int(rule.value)
            if len(value) > threshold:
                return False, PolicyViolation(
                    policy_id=rule.policy_id,
                    rule_type=rule.rule_type,
                    field_path=rule.field_path,
                    message=rule.message
                    or f"String length {len(value)} exceeds maximum {threshold}",
                    actual_value=len(value),
                    threshold_value=threshold,
                )
        else:
            # Not a string - violation
            return False, PolicyViolation(
                policy_id=rule.policy_id,
                rule_type=rule.rule_type,
                field_path=rule.field_path,
                message=rule.message or f"Field '{rule.field_path}' is not a string",
                actual_value=value,
                threshold_value=rule.value,
            )
        return True, None

    if rule.rule_type == "enum_allowlist":
        # v1.1: field missing = violation (deny)
        if not found:
            return False, PolicyViolation(
                policy_id=rule.policy_id,
                rule_type=rule.rule_type,
                field_path=rule.field_path,
                message=rule.message or f"Field '{rule.field_path}' is missing",
                actual_value=None,
                threshold_value=rule.value,
            )
        allowed_values = rule.value if isinstance(rule.value, list) else []
        if value not in allowed_values:
            return False, PolicyViolation(
                policy_id=rule.policy_id,
                rule_type=rule.rule_type,
                field_path=rule.field_path,
                message=rule.message
                or f"Value '{value}' not in allowed list: {allowed_values}",
                actual_value=value,
                threshold_value=allowed_values,
            )
        return True, None

    # Unknown rule type - pass
    return True, None


def evaluate_policies(
    phase: str,
    dept_id: Optional[str],
    endpoint_sig: str,
    payload: Dict[str, Any],
    institution_id: Optional[str] = None,
) -> PolicyEvalResult:
    """Evaluate all applicable policies for a request.

    v1.1: endpoint matching is exact only (no wildcards).

    Args:
        phase: "pre" or "post".
        dept_id: Department ID (None for single mode).
        endpoint_sig: Canonical endpoint signature e.g. "POST /finance/expenses".
        payload: The request payload.
        institution_id: Optional institution ID for governed policies lookup.

    Returns:
        PolicyEvalResult with allow status and any violations.
    """
    # If institution_id is provided, use governed policies (override + bundle)
    if institution_id:
        from engine.core.governed_policies import get_effective_policies
        policy_def = get_effective_policies(institution_id, dept_id)
    else:
        policy_def = get_policies(dept_id)

    if policy_def is None:
        # No policies defined - allow by default
        return PolicyEvalResult(allow=True)

    violations: List[PolicyViolation] = []
    matched_policies: List[str] = []

    for rule in policy_def.policies:
        # Check phase and endpoint match (exact match only)
        if rule.phase != phase:
            continue
        if rule.endpoint_sig != endpoint_sig:
            continue

        matched_policies.append(rule.policy_id)

        # Evaluate rule
        passed, violation = _evaluate_rule(rule, payload)
        if not passed and violation:
            violations.append(violation)

    return PolicyEvalResult(
        allow=len(violations) == 0,
        violations=violations,
        matched_policies=matched_policies,
    )


def emit_policy_decision(
    phase: str,
    endpoint_sig: str,
    dept_id: Optional[str],
    case_id: str,
    actor: ActorContext,
    result: PolicyEvalResult,
) -> None:
    """Emit POLICY_PRE_DECISION or POLICY_POST_DECISION event to ledger.

    Args:
        phase: "pre" or "post".
        endpoint_sig: Canonical endpoint signature.
        dept_id: Department ID (None for single mode).
        case_id: Case identifier (expense_id, approval_id, etc.).
        actor: Actor context.
        result: Policy evaluation result.
    """
    ledger = get_ledger()
    if not ledger:
        return

    event_type = f"POLICY_{phase.upper()}_DECISION"
    step_name = f"POLICY_GATE:{phase}:{endpoint_sig}"

    payload = {
        "dept_id": dept_id,
        "endpoint_sig": endpoint_sig,
        "allow": result.allow,
        "matched_policies": result.matched_policies,
        "violations": [
            {
                "policy_id": v.policy_id,
                "rule_type": v.rule_type,
                "field_path": v.field_path,
                "message": v.message,
                "actual_value": v.actual_value,
                "threshold_value": v.threshold_value,
            }
            for v in result.violations
        ],
    }

    ledger.append(
        event_type=event_type,
        tenant_id=actor.tenant_id,
        actor_id=actor.actor_id,
        actor_roles=actor.roles,
        case_id=case_id,
        step=step_name,
        payload=payload,
    )


def load_policies_from_json(policies_json: str) -> Optional[PolicyDef]:
    """Load policies from JSON string.

    Args:
        policies_json: JSON string containing policies.

    Returns:
        PolicyDef if valid, None if invalid.
    """
    try:
        data = json.loads(policies_json)
        return parse_policies_data(data)
    except (json.JSONDecodeError, KeyError, TypeError, PolicySchemaError):
        return None


def parse_policies_data(data: Dict[str, Any]) -> PolicyDef:
    """Parse policies from dict with v1.1 schema support.

    Schema v1.1:
    - policy_schema_version: "1.1"
    - policies[].endpoint_sig: exact endpoint signature (required)

    Backward compat (schema version absent):
    - policies[].endpoint_pattern must exactly match an allowed endpoint_sig
    - No wildcards or patterns allowed

    Args:
        data: Dict with "policies" key containing list of policy rules.

    Returns:
        PolicyDef with parsed rules.

    Raises:
        PolicySchemaError: If schema validation fails.
        KeyError, TypeError: If data is malformed.
    """
    schema_version = data.get("policy_schema_version")
    is_v11 = schema_version == "1.1"

    rules: List[PolicyRule] = []
    policies_list = data.get("policies", [])

    for policy in policies_list:
        policy_id = policy["policy_id"]
        rule_type = policy["rule_type"]
        field_path = policy["field_path"]
        phase = policy.get("phase", "pre")
        value = policy.get("value")
        message = policy.get("message", "")

        # Validate field_path
        field_path_tokens = validate_field_path(field_path)

        # Determine endpoint_sig based on schema version
        if is_v11:
            # v1.1: require endpoint_sig, reject endpoint_pattern
            if "endpoint_pattern" in policy:
                raise PolicySchemaError(
                    code=POLICY_INVALID,
                    message=f"Policy '{policy_id}': endpoint_pattern not allowed in v1.1 schema. "
                    "Use endpoint_sig instead.",
                )
            endpoint_sig = policy.get("endpoint_sig")
            if not endpoint_sig:
                raise PolicySchemaError(
                    code=POLICY_INVALID,
                    message=f"Policy '{policy_id}': endpoint_sig is required in v1.1 schema.",
                )
        else:
            # Legacy (no version): accept endpoint_pattern but only if it's an exact match
            # to an allowed endpoint_sig (no wildcards)
            endpoint_pattern = policy.get("endpoint_pattern")
            if endpoint_pattern is None:
                raise PolicySchemaError(
                    code=POLICY_INVALID,
                    message=f"Policy '{policy_id}': endpoint_pattern is required "
                    "(legacy schema without version).",
                )
            # endpoint_pattern must be exactly an allowed endpoint_sig
            endpoint_sig = endpoint_pattern

        # Validate endpoint_sig is allowed
        validate_endpoint_sig(endpoint_sig)

        rules.append(
            PolicyRule(
                policy_id=policy_id,
                rule_type=rule_type,
                field_path=field_path,
                field_path_tokens=field_path_tokens,
                phase=phase,
                endpoint_sig=endpoint_sig,
                value=value,
                message=message,
            )
        )

    return PolicyDef(policies=rules)


def load_policies_from_file(file_path: Path) -> Optional[PolicyDef]:
    """Load policies from a JSON file.

    Args:
        file_path: Path to policies.json file.

    Returns:
        PolicyDef if valid and exists, None otherwise.
    """
    if not file_path.exists():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_policies_data(data)
    except (json.JSONDecodeError, KeyError, TypeError, PolicySchemaError):
        return None
