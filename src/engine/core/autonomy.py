"""AXIOM Autonomy Levels v1.0 - Graduated Autonomy Gate.

Autonomy levels L0..L4 control what actions the engine can take:
- L0: Full human oversight required
- L1: Minimal autonomy
- L2: Moderate autonomy
- L3: High autonomy
- L4: Full autonomy (allow-all)

Each rule specifies a required_level for an (endpoint_sig, phase) pair.
The current_level (from autonomy.json or default) must be >= required_level.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ledger import get_ledger
from .actor_context import ActorContext
from .errors import (
    AUTONOMY_INVALID,
    AUTONOMY_INSUFFICIENT,
    AUTONOMY_ENDPOINT_UNKNOWN,
    AUTONOMY_LEVEL_INVALID,
)


# Allowed endpoint signatures (same as policy engine and mandates)
ALLOWED_ENDPOINT_SIGS = frozenset({
    "POST /finance/expenses",
    "POST /approvals/{approval_id}/decide",
    "POST /support/tickets",
    # Bazari Phase 1 (control-plane CRUD)
    "POST /reports",
    "GET /reports/{report_id}",
    "GET /reports/my",
    "GET /moderation/reports",
    "POST /chat/reports",
    "POST /chat/blocks",
    "DELETE /chat/blocks/{block_id}",
    "POST /moderation/actions",
    "GET /moderation/actions/{action_id}",
    "GET /moderation/actions",
    # Bazari MVP (workflows / transitions)
    "POST /moderation/reports/{report_id}/triage",
    "POST /moderation/actions/{action_id}/apply",
    "POST /moderation/actions/{action_id}/submit",
})

# Allowed phases
ALLOWED_PHASES = frozenset({"pre", "post"})

# Valid autonomy levels
MIN_LEVEL = 0
MAX_LEVEL = 4

# Default values when autonomy.json is missing (allow-all behavior)
DEFAULT_CURRENT_LEVEL = 4
DEFAULT_REQUIRED_LEVEL = 0


class AutonomySchemaError(Exception):
    """Raised when autonomy schema validation fails."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class AutonomyRule:
    """A single autonomy rule definition."""

    rule_id: str
    endpoint_sig: str  # e.g. "POST /finance/expenses"
    phase: str  # "pre" or "post"
    required_level: int  # 0..4


@dataclass
class AutonomyDef:
    """Autonomy definition for a department."""

    current_level: int = DEFAULT_CURRENT_LEVEL
    rules: List[AutonomyRule] = field(default_factory=list)


@dataclass
class AutonomyEvalResult:
    """Result of autonomy evaluation."""

    decision: str  # "allow" or "deny"
    current_level: int
    required_level: int
    rule_id: Optional[str] = None
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API/logging."""
        return {
            "decision": self.decision,
            "current_level": self.current_level,
            "required_level": self.required_level,
            "rule_id": self.rule_id,
            "reason": self.reason,
        }


# Global autonomy store per department
# Key: dept_id (or "_single" for single-mode)
_autonomy: Dict[str, AutonomyDef] = {}

SINGLE_MODE_KEY = "_single"


def set_autonomy_for_dept(dept_id: Optional[str], autonomy_def: Optional[AutonomyDef]) -> None:
    """Set autonomy definition for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.
        autonomy_def: Autonomy definition, or None to clear.
    """
    key = dept_id or SINGLE_MODE_KEY
    if autonomy_def is None:
        _autonomy.pop(key, None)
    else:
        _autonomy[key] = autonomy_def


def get_autonomy_for_dept(dept_id: Optional[str]) -> Optional[AutonomyDef]:
    """Get autonomy definition for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.

    Returns:
        AutonomyDef if found, None otherwise.
    """
    key = dept_id or SINGLE_MODE_KEY
    return _autonomy.get(key)


def reset_all_autonomy() -> None:
    """Clear all autonomy definitions (for testing)."""
    _autonomy.clear()


def _validate_level(level: Any, field_name: str, context: str) -> int:
    """Validate that a level is an integer in range 0..4.

    Args:
        level: The level value to validate.
        field_name: Name of the field (for error messages).
        context: Context string (for error messages).

    Returns:
        The validated level as int.

    Raises:
        AutonomySchemaError: If level is invalid.
    """
    if not isinstance(level, int):
        raise AutonomySchemaError(
            code=AUTONOMY_LEVEL_INVALID,
            message=f"{context}: {field_name} must be an integer, got {type(level).__name__}",
        )
    if level < MIN_LEVEL or level > MAX_LEVEL:
        raise AutonomySchemaError(
            code=AUTONOMY_LEVEL_INVALID,
            message=f"{context}: {field_name} must be in range {MIN_LEVEL}..{MAX_LEVEL}, got {level}",
        )
    return level


def parse_autonomy_data(data: Dict[str, Any]) -> AutonomyDef:
    """Parse autonomy definition from dict.

    Schema v1.0:
    {
      "autonomy_schema_version": "1.0",
      "current_level": 3,  // optional, defaults to 4
      "rules": [  // optional, defaults to []
        {
          "rule_id": "string",
          "endpoint_sig": "POST /finance/expenses",
          "phase": "pre",
          "required_level": 2
        }
      ]
    }

    Args:
        data: Dict with autonomy data.

    Returns:
        AutonomyDef with parsed rules.

    Raises:
        AutonomySchemaError: If schema validation fails.
    """
    schema_version = data.get("autonomy_schema_version")
    if schema_version != "1.0":
        raise AutonomySchemaError(
            code=AUTONOMY_INVALID,
            message=f"Unsupported autonomy_schema_version: {schema_version}. Expected '1.0'.",
        )

    # Parse current_level (optional, defaults to 4)
    current_level = data.get("current_level", DEFAULT_CURRENT_LEVEL)
    current_level = _validate_level(current_level, "current_level", "Autonomy definition")

    # Parse rules (optional)
    rules: List[AutonomyRule] = []
    rules_list = data.get("rules", [])

    if not isinstance(rules_list, list):
        raise AutonomySchemaError(
            code=AUTONOMY_INVALID,
            message="'rules' must be a list",
        )

    for idx, rule_data in enumerate(rules_list):
        context = f"Rule {idx}"

        # Required fields
        rule_id = rule_data.get("rule_id")
        if not rule_id:
            raise AutonomySchemaError(
                code=AUTONOMY_INVALID,
                message=f"{context}: rule_id is required",
            )
        context = f"Rule '{rule_id}'"

        endpoint_sig = rule_data.get("endpoint_sig")
        if not endpoint_sig:
            raise AutonomySchemaError(
                code=AUTONOMY_INVALID,
                message=f"{context}: endpoint_sig is required",
            )

        if endpoint_sig not in ALLOWED_ENDPOINT_SIGS:
            raise AutonomySchemaError(
                code=AUTONOMY_ENDPOINT_UNKNOWN,
                message=f"{context}: unknown endpoint_sig '{endpoint_sig}'",
            )

        phase = rule_data.get("phase")
        if not phase:
            raise AutonomySchemaError(
                code=AUTONOMY_INVALID,
                message=f"{context}: phase is required",
            )

        if phase not in ALLOWED_PHASES:
            raise AutonomySchemaError(
                code=AUTONOMY_INVALID,
                message=f"{context}: invalid phase '{phase}'. Must be 'pre' or 'post'.",
            )

        required_level = rule_data.get("required_level")
        if required_level is None:
            raise AutonomySchemaError(
                code=AUTONOMY_INVALID,
                message=f"{context}: required_level is required",
            )
        required_level = _validate_level(required_level, "required_level", context)

        rules.append(
            AutonomyRule(
                rule_id=rule_id,
                endpoint_sig=endpoint_sig,
                phase=phase,
                required_level=required_level,
            )
        )

    return AutonomyDef(current_level=current_level, rules=rules)


def load_autonomy_from_file(file_path: Path) -> Optional[AutonomyDef]:
    """Load autonomy definition from a JSON file.

    Args:
        file_path: Path to autonomy.json file.

    Returns:
        AutonomyDef if valid and exists, None if file doesn't exist.

    Raises:
        AutonomySchemaError: If file exists but is invalid.
    """
    if not file_path.exists():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_autonomy_data(data)
    except json.JSONDecodeError as e:
        raise AutonomySchemaError(
            code=AUTONOMY_INVALID,
            message=f"Invalid JSON in autonomy.json: {e}",
        )


def evaluate_autonomy(
    phase: str,
    dept_id: Optional[str],
    endpoint_sig: str,
    institution_id: Optional[str] = None,
) -> AutonomyEvalResult:
    """Evaluate autonomy for a request.

    Logic (canonical semantics):
    1. If autonomy.json does not exist: allow (no contract = allow)
    2. Find first rule matching (phase, endpoint_sig)
    3. If autonomy.json exists but no rule matches: DENY (AUTONOMY_INSUFFICIENT)
       - Canonical semantics: no rule = no permission
    4. Decision is "allow" if current_level >= required_level, else "deny"

    Args:
        phase: "pre" or "post".
        dept_id: Department ID (None for single mode).
        endpoint_sig: Canonical endpoint signature.
        institution_id: Optional institution ID for governed autonomy lookup.

    Returns:
        AutonomyEvalResult with decision and details.
    """
    # If institution_id is provided, use governed autonomy (override + bundle)
    if institution_id:
        from engine.core.governed_autonomy import get_effective_autonomy
        autonomy_def = get_effective_autonomy(institution_id, dept_id)
    else:
        autonomy_def = get_autonomy_for_dept(dept_id)

    if autonomy_def is None:
        # No autonomy.json loaded - allow (no contract = allow)
        return AutonomyEvalResult(
            decision="allow",
            current_level=DEFAULT_CURRENT_LEVEL,
            required_level=DEFAULT_REQUIRED_LEVEL,
            rule_id=None,
            reason="No autonomy contract loaded (allow-all)",
        )

    current_level = autonomy_def.current_level

    # Find first matching rule (by phase + endpoint_sig)
    for rule in autonomy_def.rules:
        if rule.phase == phase and rule.endpoint_sig == endpoint_sig:
            # Found matching rule
            if current_level >= rule.required_level:
                return AutonomyEvalResult(
                    decision="allow",
                    current_level=current_level,
                    required_level=rule.required_level,
                    rule_id=rule.rule_id,
                    reason=None,
                )
            else:
                return AutonomyEvalResult(
                    decision="deny",
                    current_level=current_level,
                    required_level=rule.required_level,
                    rule_id=rule.rule_id,
                    reason=f"Autonomy level {current_level} is below required level {rule.required_level}",
                )

    # No matching rule - DENY per canonical semantics
    # If autonomy.json exists but no rule matches → deny (AUTONOMY_INSUFFICIENT)
    return AutonomyEvalResult(
        decision="deny",
        current_level=current_level,
        required_level=MAX_LEVEL + 1,  # Impossible to satisfy
        rule_id=None,
        reason=f"No autonomy rule applicable for ({endpoint_sig}, {phase})",
    )


def emit_autonomy_evaluated(
    tenant_id: str,
    actor: ActorContext,
    dept_id: Optional[str],
    phase: str,
    endpoint_sig: str,
    case_id: str,
    result: AutonomyEvalResult,
) -> None:
    """Emit AUTONOMY_EVALUATED event to ledger.

    Always emitted (for allow or deny), per spec:
    - event_type = AUTONOMY_EVALUATED
    - step/name = AXIOM_AUTONOMY:<phase>:<endpoint_sig>

    Args:
        tenant_id: Tenant identifier.
        actor: Actor context.
        dept_id: Department ID (None for single mode).
        phase: "pre" or "post".
        endpoint_sig: Canonical endpoint signature.
        case_id: Case identifier.
        result: Autonomy evaluation result.
    """
    ledger = get_ledger()
    if not ledger:
        return

    event_type = "AUTONOMY_EVALUATED"
    step_name = f"AXIOM_AUTONOMY:{phase}:{endpoint_sig}"

    payload = {
        "name": step_name,
        "dept_id": dept_id,
        "phase": phase,
        "endpoint_sig": endpoint_sig,
        "decision": result.decision,
        "current_level": result.current_level,
        "required_level": result.required_level,
        "rule_id": result.rule_id,
        "reason": result.reason,
    }

    ledger.append(
        event_type=event_type,
        tenant_id=tenant_id,
        actor_id=actor.actor_id,
        actor_roles=actor.roles,
        case_id=case_id,
        step=step_name,
        payload=payload,
    )
