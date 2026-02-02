"""Mandate Engine v1.0 - Autonomy with Revocation.

Mandates allow temporary delegation of authority with:
- Endpoint signature + phase matching
- Actor role validation
- ISO8601 UTC validity windows
- Limit enforcement using same rule_types as policy engine
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .ledger import get_ledger
from .actor_context import ActorContext
from .errors import (
    MANDATE_INVALID,
    MANDATE_DENIED,
    MANDATE_EXPIRED,
    MANDATE_ROLE_MISMATCH,
)


# Allowed phases
ALLOWED_PHASES = frozenset({"pre", "post"})

# Allowed rule_types (same as policy engine)
ALLOWED_RULE_TYPES = frozenset({
    "required_field",
    "numeric_max",
    "numeric_min",
    "string_max_len",
    "enum_allowlist",
})


class MandateSchemaError(Exception):
    """Raised when mandate schema validation fails."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class MandateLimit:
    """A single limit rule within a mandate."""

    rule_type: str  # numeric_max, numeric_min, string_max_len, required_field, enum_allowlist
    field_path: str  # dot notation e.g. "amount" or "payload.amount"
    field_path_tokens: List[str]  # pre-parsed tokens
    value: Any = None  # threshold value
    message: str = ""  # custom error message


@dataclass
class Mandate:
    """A single mandate definition."""

    mandate_id: str
    endpoint_sig: str  # e.g. "POST /finance/expenses"
    phase: str  # "pre" or "post"
    allowed_roles: List[str]  # roles that can invoke this mandate
    valid_from: Optional[datetime] = None  # ISO8601 UTC
    valid_until: Optional[datetime] = None  # ISO8601 UTC
    limits: List[MandateLimit] = field(default_factory=list)
    message: str = ""  # custom denial message


@dataclass
class MandateDef:
    """Mandate definition containing multiple mandates."""

    mandates: List[Mandate] = field(default_factory=list)


@dataclass
class MandateViolation:
    """Describes a mandate violation."""

    mandate_id: Optional[str]
    code: str  # MANDATE_DENIED, MANDATE_EXPIRED, MANDATE_ROLE_MISMATCH
    rule_type: Optional[str]
    field_path: Optional[str]
    message: str
    actual_value: Any = None
    threshold_value: Any = None


@dataclass
class MandateEvalResult:
    """Result of mandate evaluation."""

    allow: bool
    mandate_id: Optional[str] = None  # matched mandate ID, or None if no mandate matched
    violations: List[MandateViolation] = field(default_factory=list)


# Global mandates per department
# Key: dept_id (or "_single" for single-mode)
_mandates: Dict[str, MandateDef] = {}

SINGLE_MODE_KEY = "_single"


def set_mandates(dept_id: Optional[str], mandate_def: Optional[MandateDef]) -> None:
    """Set mandates for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.
        mandate_def: Mandate definition, or None to clear.
    """
    key = dept_id or SINGLE_MODE_KEY
    if mandate_def is None:
        _mandates.pop(key, None)
    else:
        _mandates[key] = mandate_def


def get_mandates(dept_id: Optional[str]) -> Optional[MandateDef]:
    """Get mandates for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.

    Returns:
        MandateDef if found, None otherwise.
    """
    key = dept_id or SINGLE_MODE_KEY
    return _mandates.get(key)


def clear_all_mandates() -> None:
    """Clear all mandates (for testing)."""
    _mandates.clear()


def _parse_iso8601_utc(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO8601 UTC timestamp.

    Args:
        value: ISO8601 string or None.

    Returns:
        datetime in UTC, or None if value is None.

    Raises:
        MandateSchemaError: If value is not valid ISO8601.
    """
    if value is None:
        return None

    try:
        # Handle various ISO8601 formats
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Ensure UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError) as e:
        raise MandateSchemaError(
            code=MANDATE_INVALID,
            message=f"Invalid ISO8601 timestamp: {value} - {e}",
        )


def _validate_field_path(field_path: str) -> List[str]:
    """Validate and parse a field path into tokens.

    Same rules as policy engine:
    - Only characters [a-zA-Z0-9_.] allowed
    - Cannot start or end with '.'
    - Cannot have consecutive dots '..'

    Args:
        field_path: The field path to validate.

    Returns:
        List of validated tokens.

    Raises:
        MandateSchemaError: If field_path is invalid.
    """
    import re

    if not field_path:
        raise MandateSchemaError(
            code=MANDATE_INVALID,
            message="field_path cannot be empty",
        )

    if not re.match(r"^[a-zA-Z0-9_.]+$", field_path):
        raise MandateSchemaError(
            code=MANDATE_INVALID,
            message=f"field_path '{field_path}' contains invalid characters",
        )

    if field_path.startswith(".") or field_path.endswith("."):
        raise MandateSchemaError(
            code=MANDATE_INVALID,
            message=f"field_path '{field_path}' cannot start or end with '.'",
        )

    if ".." in field_path:
        raise MandateSchemaError(
            code=MANDATE_INVALID,
            message=f"field_path '{field_path}' cannot contain consecutive dots",
        )

    return field_path.split(".")


def parse_mandates_data(data: Dict[str, Any]) -> MandateDef:
    """Parse mandates from dict.

    Schema v1.0:
    {
      "mandate_schema_version": "1.0",
      "mandates": [
        {
          "mandate_id": "string",
          "endpoint_sig": "POST /finance/expenses",
          "phase": "pre",
          "allowed_roles": ["role1", "role2"],
          "valid_from": "ISO8601",  // optional
          "valid_until": "ISO8601",  // optional
          "limits": [  // optional
            {
              "rule_type": "numeric_max",
              "field_path": "amount",
              "value": 1000,
              "message": "optional"
            }
          ],
          "message": "optional denial message"
        }
      ]
    }

    Args:
        data: Dict with mandates data.

    Returns:
        MandateDef with parsed mandates.

    Raises:
        MandateSchemaError: If schema validation fails.
    """
    schema_version = data.get("mandate_schema_version")
    if schema_version != "1.0":
        raise MandateSchemaError(
            code=MANDATE_INVALID,
            message=f"Unsupported mandate_schema_version: {schema_version}. Expected '1.0'.",
        )

    mandates: List[Mandate] = []
    mandates_list = data.get("mandates", [])

    for mandate_data in mandates_list:
        # Required fields
        mandate_id = mandate_data.get("mandate_id")
        if not mandate_id:
            raise MandateSchemaError(
                code=MANDATE_INVALID,
                message="mandate_id is required",
            )

        endpoint_sig = mandate_data.get("endpoint_sig")
        if not endpoint_sig:
            raise MandateSchemaError(
                code=MANDATE_INVALID,
                message=f"Mandate '{mandate_id}': endpoint_sig is required",
            )

        phase = mandate_data.get("phase")
        if not phase:
            raise MandateSchemaError(
                code=MANDATE_INVALID,
                message=f"Mandate '{mandate_id}': phase is required",
            )

        if phase not in ALLOWED_PHASES:
            raise MandateSchemaError(
                code=MANDATE_INVALID,
                message=f"Mandate '{mandate_id}': invalid phase '{phase}'. Must be 'pre' or 'post'.",
            )

        allowed_roles = mandate_data.get("allowed_roles", [])
        if not isinstance(allowed_roles, list):
            raise MandateSchemaError(
                code=MANDATE_INVALID,
                message=f"Mandate '{mandate_id}': allowed_roles must be a list",
            )

        # Optional fields
        valid_from = _parse_iso8601_utc(mandate_data.get("valid_from"))
        valid_until = _parse_iso8601_utc(mandate_data.get("valid_until"))
        message = mandate_data.get("message", "")

        # Parse limits
        limits: List[MandateLimit] = []
        limits_data = mandate_data.get("limits", [])
        for limit_data in limits_data:
            rule_type = limit_data.get("rule_type")
            if rule_type not in ALLOWED_RULE_TYPES:
                raise MandateSchemaError(
                    code=MANDATE_INVALID,
                    message=f"Mandate '{mandate_id}': invalid rule_type '{rule_type}'",
                )

            field_path = limit_data.get("field_path")
            field_path_tokens = _validate_field_path(field_path)

            limits.append(
                MandateLimit(
                    rule_type=rule_type,
                    field_path=field_path,
                    field_path_tokens=field_path_tokens,
                    value=limit_data.get("value"),
                    message=limit_data.get("message", ""),
                )
            )

        mandates.append(
            Mandate(
                mandate_id=mandate_id,
                endpoint_sig=endpoint_sig,
                phase=phase,
                allowed_roles=allowed_roles,
                valid_from=valid_from,
                valid_until=valid_until,
                limits=limits,
                message=message,
            )
        )

    return MandateDef(mandates=mandates)


def load_mandates_from_file(file_path: Path) -> Optional[MandateDef]:
    """Load mandates from a JSON file.

    Args:
        file_path: Path to mandates.json file.

    Returns:
        MandateDef if valid and exists, None if file doesn't exist.

    Raises:
        MandateSchemaError: If file exists but is invalid.
    """
    if not file_path.exists():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_mandates_data(data)
    except json.JSONDecodeError as e:
        raise MandateSchemaError(
            code=MANDATE_INVALID,
            message=f"Invalid JSON in mandates.json: {e}",
        )


def _get_field_value_by_tokens(
    payload: Dict[str, Any], tokens: List[str]
) -> Tuple[bool, Any]:
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


def _evaluate_limit(
    limit: MandateLimit, mandate_id: str, payload: Dict[str, Any]
) -> Tuple[bool, Optional[MandateViolation]]:
    """Evaluate a single limit rule.

    Same logic as policy engine's _evaluate_rule.

    Args:
        limit: The limit rule to evaluate.
        mandate_id: The parent mandate ID.
        payload: The request payload.

    Returns:
        Tuple of (pass: bool, violation: Optional[MandateViolation]).
    """
    found, value = _get_field_value_by_tokens(payload, limit.field_path_tokens)

    if limit.rule_type == "required_field":
        if not found or value is None:
            return False, MandateViolation(
                mandate_id=mandate_id,
                code=MANDATE_DENIED,
                rule_type=limit.rule_type,
                field_path=limit.field_path,
                message=limit.message or f"Required field '{limit.field_path}' is missing",
                actual_value=None,
                threshold_value=None,
            )
        return True, None

    if limit.rule_type == "numeric_max":
        if not found:
            return False, MandateViolation(
                mandate_id=mandate_id,
                code=MANDATE_DENIED,
                rule_type=limit.rule_type,
                field_path=limit.field_path,
                message=limit.message or f"Field '{limit.field_path}' is missing",
                actual_value=None,
                threshold_value=limit.value,
            )
        try:
            num_value = float(value)
            threshold = float(limit.value)
            if num_value > threshold:
                return False, MandateViolation(
                    mandate_id=mandate_id,
                    code=MANDATE_DENIED,
                    rule_type=limit.rule_type,
                    field_path=limit.field_path,
                    message=limit.message or f"Value {num_value} exceeds mandate limit {threshold}",
                    actual_value=num_value,
                    threshold_value=threshold,
                )
        except (TypeError, ValueError):
            return False, MandateViolation(
                mandate_id=mandate_id,
                code=MANDATE_DENIED,
                rule_type=limit.rule_type,
                field_path=limit.field_path,
                message=limit.message or f"Field '{limit.field_path}' is not a valid number",
                actual_value=value,
                threshold_value=limit.value,
            )
        return True, None

    if limit.rule_type == "numeric_min":
        if not found:
            return False, MandateViolation(
                mandate_id=mandate_id,
                code=MANDATE_DENIED,
                rule_type=limit.rule_type,
                field_path=limit.field_path,
                message=limit.message or f"Field '{limit.field_path}' is missing",
                actual_value=None,
                threshold_value=limit.value,
            )
        try:
            num_value = float(value)
            threshold = float(limit.value)
            if num_value < threshold:
                return False, MandateViolation(
                    mandate_id=mandate_id,
                    code=MANDATE_DENIED,
                    rule_type=limit.rule_type,
                    field_path=limit.field_path,
                    message=limit.message or f"Value {num_value} is below mandate minimum {threshold}",
                    actual_value=num_value,
                    threshold_value=threshold,
                )
        except (TypeError, ValueError):
            return False, MandateViolation(
                mandate_id=mandate_id,
                code=MANDATE_DENIED,
                rule_type=limit.rule_type,
                field_path=limit.field_path,
                message=limit.message or f"Field '{limit.field_path}' is not a valid number",
                actual_value=value,
                threshold_value=limit.value,
            )
        return True, None

    if limit.rule_type == "string_max_len":
        if not found:
            return False, MandateViolation(
                mandate_id=mandate_id,
                code=MANDATE_DENIED,
                rule_type=limit.rule_type,
                field_path=limit.field_path,
                message=limit.message or f"Field '{limit.field_path}' is missing",
                actual_value=None,
                threshold_value=limit.value,
            )
        if isinstance(value, str):
            threshold = int(limit.value)
            if len(value) > threshold:
                return False, MandateViolation(
                    mandate_id=mandate_id,
                    code=MANDATE_DENIED,
                    rule_type=limit.rule_type,
                    field_path=limit.field_path,
                    message=limit.message or f"String length {len(value)} exceeds mandate limit {threshold}",
                    actual_value=len(value),
                    threshold_value=threshold,
                )
        else:
            return False, MandateViolation(
                mandate_id=mandate_id,
                code=MANDATE_DENIED,
                rule_type=limit.rule_type,
                field_path=limit.field_path,
                message=limit.message or f"Field '{limit.field_path}' is not a string",
                actual_value=value,
                threshold_value=limit.value,
            )
        return True, None

    if limit.rule_type == "enum_allowlist":
        if not found:
            return False, MandateViolation(
                mandate_id=mandate_id,
                code=MANDATE_DENIED,
                rule_type=limit.rule_type,
                field_path=limit.field_path,
                message=limit.message or f"Field '{limit.field_path}' is missing",
                actual_value=None,
                threshold_value=limit.value,
            )
        allowed_values = limit.value if isinstance(limit.value, list) else []
        if value not in allowed_values:
            return False, MandateViolation(
                mandate_id=mandate_id,
                code=MANDATE_DENIED,
                rule_type=limit.rule_type,
                field_path=limit.field_path,
                message=limit.message or f"Value '{value}' not in mandate allowlist: {allowed_values}",
                actual_value=value,
                threshold_value=allowed_values,
            )
        return True, None

    # Unknown rule type - pass
    return True, None


def evaluate_mandates(
    phase: str,
    dept_id: Optional[str],
    endpoint_sig: str,
    actor: ActorContext,
    payload: Dict[str, Any],
    institution_id: Optional[str] = None,
) -> MandateEvalResult:
    """Evaluate mandates for a request.

    Logic (canonical semantics):
    1. If mandates.json does not exist: allow (no contract = allow)
    2. Find mandates matching endpoint_sig + phase
    3. If mandates.json exists but no mandate matches: DENY (MANDATE_DENIED)
       - "Nenhuma execução fora de mandato"
    4. If mandate matches:
       a. Check validity window (valid_from/valid_until)
       b. Check actor roles
       c. Evaluate limit rules
    5. Return allow=True if mandate grants access AND all limits pass

    Args:
        phase: "pre" or "post".
        dept_id: Department ID (None for single mode).
        endpoint_sig: Canonical endpoint signature.
        actor: Actor context.
        payload: The request payload.
        institution_id: Optional institution ID for governed mandates lookup.

    Returns:
        MandateEvalResult with allow status and any violations.
    """
    # If institution_id is provided, use governed mandates (override + bundle)
    if institution_id:
        from engine.core.governed_mandates import get_effective_mandates
        mandate_def = get_effective_mandates(institution_id, dept_id)
    else:
        mandate_def = get_mandates(dept_id)

    if mandate_def is None:
        # No mandates.json loaded - allow (no contract = allow)
        return MandateEvalResult(allow=True)

    now = datetime.now(timezone.utc)

    # Find matching mandates
    for mandate in mandate_def.mandates:
        # Check endpoint_sig and phase match
        if mandate.endpoint_sig != endpoint_sig:
            continue
        if mandate.phase != phase:
            continue

        # Found a matching mandate - evaluate it

        # 1. Check validity window
        if mandate.valid_from and now < mandate.valid_from:
            # Mandate not yet active
            return MandateEvalResult(
                allow=False,
                mandate_id=mandate.mandate_id,
                violations=[
                    MandateViolation(
                        mandate_id=mandate.mandate_id,
                        code=MANDATE_EXPIRED,
                        rule_type=None,
                        field_path=None,
                        message=mandate.message or f"Mandate '{mandate.mandate_id}' not yet active",
                    )
                ],
            )

        if mandate.valid_until and now > mandate.valid_until:
            # Mandate expired
            return MandateEvalResult(
                allow=False,
                mandate_id=mandate.mandate_id,
                violations=[
                    MandateViolation(
                        mandate_id=mandate.mandate_id,
                        code=MANDATE_EXPIRED,
                        rule_type=None,
                        field_path=None,
                        message=mandate.message or f"Mandate '{mandate.mandate_id}' has expired",
                    )
                ],
            )

        # 2. Check actor roles
        if mandate.allowed_roles:
            actor_roles_set = set(actor.roles)
            allowed_roles_set = set(mandate.allowed_roles)
            if not actor_roles_set.intersection(allowed_roles_set):
                return MandateEvalResult(
                    allow=False,
                    mandate_id=mandate.mandate_id,
                    violations=[
                        MandateViolation(
                            mandate_id=mandate.mandate_id,
                            code=MANDATE_ROLE_MISMATCH,
                            rule_type=None,
                            field_path=None,
                            message=mandate.message
                            or f"Actor roles {actor.roles} do not match mandate allowed_roles {mandate.allowed_roles}",
                        )
                    ],
                )

        # 3. Evaluate limits
        violations: List[MandateViolation] = []
        for limit in mandate.limits:
            passed, violation = _evaluate_limit(limit, mandate.mandate_id, payload)
            if not passed and violation:
                violations.append(violation)

        if violations:
            return MandateEvalResult(
                allow=False,
                mandate_id=mandate.mandate_id,
                violations=violations,
            )

        # All checks passed - mandate grants access
        return MandateEvalResult(
            allow=True,
            mandate_id=mandate.mandate_id,
        )

    # No matching mandate found - DENY per canonical semantics
    # "Nenhuma execução fora de mandato" - no execution outside of mandate
    return MandateEvalResult(
        allow=False,
        mandate_id=None,
        violations=[
            MandateViolation(
                mandate_id=None,
                code=MANDATE_DENIED,
                rule_type=None,
                field_path=None,
                message=f"No mandate applicable for ({endpoint_sig}, {phase})",
            )
        ],
    )


def emit_mandate_decision(
    phase: str,
    endpoint_sig: str,
    dept_id: Optional[str],
    case_id: str,
    actor: ActorContext,
    result: MandateEvalResult,
) -> None:
    """Emit MANDATE_EVALUATED event to ledger.

    Always emitted (for allow or deny), per spec:
    - name = MANDATE_GATE:<phase>:<endpoint_sig>
    - include mandate_id or null

    Args:
        phase: "pre" or "post".
        endpoint_sig: Canonical endpoint signature.
        dept_id: Department ID (None for single mode).
        case_id: Case identifier.
        actor: Actor context.
        result: Mandate evaluation result.
    """
    ledger = get_ledger()
    if not ledger:
        return

    event_type = "MANDATE_EVALUATED"
    step_name = f"MANDATE_GATE:{phase}:{endpoint_sig}"

    payload = {
        "dept_id": dept_id,
        "endpoint_sig": endpoint_sig,
        "phase": phase,
        "allow": result.allow,
        "mandate_id": result.mandate_id,
        "violations": [
            {
                "mandate_id": v.mandate_id,
                "code": v.code,
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
