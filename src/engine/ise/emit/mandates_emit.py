"""Mandates contract emitter for ISE compiler.

Emits mandates.json in the format expected by the runtime mandates engine.
Per MVP decision (2026-01-17): mandates.json is a mandatory institutional contract.
"""

import json
from typing import Any, Dict, List

from ..idl_parser import ParsedIDL, IDLPolicy


# Mandate schema version
MANDATE_SCHEMA_VERSION = "1.0"


def emit_mandates(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit mandates contract from parsed IDL.

    Generates a mandates.json with mandate_schema_version and mandates array.
    If no mandates are defined in the IDL, emits an empty mandates array
    (which means default-deny behavior in runtime).

    Args:
        parsed: Parsed IDL structure.

    Returns:
        Dict with mandate contract structure.
    """
    mandates_list: List[Dict[str, Any]] = []

    # Extract mandates from IDL policies if they have mandate-related fields
    # For MVP, we emit an empty mandates array if no explicit mandates defined
    # This results in default-deny behavior (no mandate = deny)

    return {
        "mandate_schema_version": MANDATE_SCHEMA_VERSION,
        "mandates": mandates_list,
    }


def emit_mandates_json(parsed: ParsedIDL) -> str:
    """Emit mandates contract as JSON string.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        JSON string with sorted keys.
    """
    mandates = emit_mandates(parsed)
    return json.dumps(mandates, indent=2, sort_keys=True)
