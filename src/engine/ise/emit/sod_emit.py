"""SoD (Segregation of Duties) contract emitter."""

import json
from typing import Dict, Any, List

from engine.ise.idl_parser import ParsedIDL


def emit_sod(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit SoD contract from parsed IDL.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        SoD contract as dict.
    """
    rules = []

    # Collect SoD requirements from usecases
    for uc in parsed.usecases:
        if not uc.has_sod:
            continue

        # Determine entity
        entity_type = parsed.entities[0].entity_type if parsed.entities else "resource"

        rule_name = f"no_self_approval_{entity_type}"

        # Check if rule already exists
        if any(r["rule_name"] == rule_name for r in rules):
            continue

        rules.append({
            "rule_name": rule_name,
            "constraint": "no_self_approval",
            "scope": {
                "entity": entity_type,
            },
        })

    return {
        "version": "1.0",
        "name": "sod",
        "rules": sorted(rules, key=lambda r: r["rule_name"]),
    }


def emit_sod_json(parsed: ParsedIDL) -> str:
    """Emit SoD contract as JSON string.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        JSON string with sorted keys.
    """
    return json.dumps(emit_sod(parsed), indent=2, sort_keys=True)
