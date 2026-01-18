"""Invariants contract emitter."""

import json
from typing import Dict, Any

from engine.ise.idl_parser import ParsedIDL


def emit_invariants(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit invariants contract from parsed IDL.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        Invariants contract as dict.
    """
    invariants = {
        "version": "1.0",
        "name": "invariants",
    }

    for entity in parsed.entities:
        entity_type = entity.entity_type
        schema = {}

        # Build schema from fields
        for field in entity.fields:
            constraints = {}

            if field.field_type == "number":
                constraints["min"] = 0.01
                constraints["max"] = 1000000000

                # Check for modifiers
                for mod in field.modifiers:
                    if mod.startswith("min:"):
                        try:
                            constraints["min"] = float(mod.split(":")[1])
                        except ValueError:
                            pass
                    elif mod.startswith("max:"):
                        try:
                            constraints["max"] = float(mod.split(":")[1])
                        except ValueError:
                            pass

            elif field.field_type == "string":
                constraints["max_len"] = 280
                constraints["required"] = field.required

            if constraints:
                schema[field.name] = constraints

        # Default schema if no fields
        if not schema:
            schema = {
                "amount": {
                    "min": 0.01,
                    "max": 1000000000,
                },
                "description": {
                    "max_len": 280,
                    "required": False,
                },
            }

        invariants[entity_type] = schema

    return invariants


def emit_invariants_json(parsed: ParsedIDL) -> str:
    """Emit invariants contract as JSON string.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        JSON string with sorted keys.
    """
    return json.dumps(emit_invariants(parsed), indent=2, sort_keys=True)
