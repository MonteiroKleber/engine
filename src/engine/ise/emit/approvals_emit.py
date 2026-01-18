"""Approvals contract emitter."""

import json
from typing import Dict, Any, List

from engine.ise.idl_parser import ParsedIDL


def emit_approvals(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit approvals contract from parsed IDL.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        Approvals contract as dict.
    """
    rules = []

    # Collect approval requirements from usecases
    for uc in parsed.usecases:
        if not uc.has_approval:
            continue

        # Determine entity
        entity_type = parsed.entities[0].entity_type if parsed.entities else "resource"

        # Determine approver roles
        approver_roles = []
        if uc.approval_role:
            approver_roles.append(uc.approval_role)
        else:
            # Find roles with approve permission
            for actor in parsed.actors:
                for perm in actor.permissions:
                    if "approve" in perm.actions:
                        approver_roles.append(actor.role)
                        break

        if not approver_roles:
            approver_roles = ["manager"]

        rule_name = f"{entity_type}.create"

        # Check if rule already exists
        if any(r["rule_name"] == rule_name for r in rules):
            continue

        rules.append({
            "rule_name": rule_name,
            "trigger": {
                "api": f"POST /finance/{entity_type}s"
            },
            "approver_roles": sorted(set(approver_roles)),
            "quorum": 1,
        })

    return {
        "version": "1.0",
        "name": "approvals",
        "rules": sorted(rules, key=lambda r: r["rule_name"]),
    }


def emit_approvals_json(parsed: ParsedIDL) -> str:
    """Emit approvals contract as JSON string.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        JSON string with sorted keys.
    """
    return json.dumps(emit_approvals(parsed), indent=2, sort_keys=True)
