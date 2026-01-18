"""Autonomy contract emitter for ISE compiler.

Emits autonomy.json in the format expected by the runtime autonomy engine.
Per MVP decision (2026-01-17): autonomy.json is a mandatory institutional contract.
"""

import json
from typing import Any, Dict, List

from ..idl_parser import ParsedIDL


# Autonomy schema version
AUTONOMY_SCHEMA_VERSION = "1.0"

# Default autonomy level for MVP (L0 = full human oversight required)
# This is the most restrictive default - requires explicit elevation
DEFAULT_CURRENT_LEVEL = 0


def emit_autonomy(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit autonomy contract from parsed IDL.

    Generates an autonomy.json with autonomy_schema_version, current_level, and rules.
    If no autonomy rules are defined in the IDL, emits with current_level=0 (L0)
    and empty rules array (which means all operations require human oversight).

    Args:
        parsed: Parsed IDL structure.

    Returns:
        Dict with autonomy contract structure.
    """
    rules_list: List[Dict[str, Any]] = []

    # Extract autonomy rules from IDL if defined
    # For MVP, we emit with L0 (most restrictive) if no explicit autonomy defined
    # This results in human oversight required for all operations

    return {
        "autonomy_schema_version": AUTONOMY_SCHEMA_VERSION,
        "current_level": DEFAULT_CURRENT_LEVEL,
        "rules": rules_list,
    }


def emit_autonomy_json(parsed: ParsedIDL) -> str:
    """Emit autonomy contract as JSON string.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        JSON string with sorted keys.
    """
    autonomy = emit_autonomy(parsed)
    return json.dumps(autonomy, indent=2, sort_keys=True)
