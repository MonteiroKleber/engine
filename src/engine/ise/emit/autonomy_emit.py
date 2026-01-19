"""Autonomy contract emitter for ISE compiler.

Emits autonomy.json in the format expected by the runtime autonomy engine.
Per MVP decision (2026-01-17): autonomy.json is a mandatory institutional contract.

IDL v1.1: mandates/autonomy are first-class. No silent defaults.
"""

import json
from typing import Any, Dict, List, Optional

from ..idl_parser import ParsedIDL, IDLAutonomy, IDLAutonomyRule


# Autonomy schema version
AUTONOMY_SCHEMA_VERSION = "1.0"

# Default autonomy level for IDL v1.0 legacy (L0 = full human oversight required)
# This is the most restrictive default - requires explicit elevation
DEFAULT_CURRENT_LEVEL_V10 = 0


def _autonomy_rule_to_dict(rule: IDLAutonomyRule) -> Dict[str, Any]:
    """Convert IDLAutonomyRule to runtime dict format."""
    return {
        "rule_id": rule.rule_id,
        "endpoint_sig": rule.endpoint_sig,
        "phase": rule.phase,
        "required_level": rule.required_level,
    }


def emit_autonomy(
    parsed: ParsedIDL,
    dept_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit autonomy contract from parsed IDL.

    IDL v1.1 behavior:
    - If autonomy is defined in IDL, emit exactly that autonomy config.
    - If IDL v1.1 has no autonomy and multi-dept mode, check dept_autonomy.
    - If autonomy is not defined in IDL v1.1, emit with current_level=0 and empty
      rules (valid format, represents "require human oversight for all" by design
      - use gap detection to warn).

    IDL v1.0 (legacy) behavior:
    - Emit with current_level=0 and empty rules array (most restrictive, backward
      compatible).

    Args:
        parsed: Parsed IDL structure.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        Dict with autonomy contract structure.
    """
    current_level = DEFAULT_CURRENT_LEVEL_V10
    rules_list: List[Dict[str, Any]] = []

    if parsed.idl_version == "1.1":
        # IDL v1.1: emit exactly what's defined
        autonomy: Optional[IDLAutonomy] = None

        if dept_id and dept_id in parsed.dept_autonomy:
            # Multi-dept mode: use dept-specific autonomy
            autonomy = parsed.dept_autonomy[dept_id]
        elif parsed.autonomy:
            # Single mode: use global autonomy
            autonomy = parsed.autonomy

        if autonomy:
            current_level = autonomy.current_level
            rules_list = [_autonomy_rule_to_dict(r) for r in autonomy.rules]
        # else: emit defaults (L0, empty rules) - explicit "require oversight for all"
    # else: v1.0 legacy - emit defaults (backward compatible)

    return {
        "autonomy_schema_version": AUTONOMY_SCHEMA_VERSION,
        "current_level": current_level,
        "rules": rules_list,
    }


def emit_autonomy_json(
    parsed: ParsedIDL,
    dept_id: Optional[str] = None,
) -> str:
    """Emit autonomy contract as JSON string.

    Args:
        parsed: Parsed IDL structure.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        JSON string with sorted keys.
    """
    autonomy = emit_autonomy(parsed, dept_id)
    return json.dumps(autonomy, indent=2, sort_keys=True)
