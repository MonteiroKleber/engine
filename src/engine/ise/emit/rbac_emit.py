"""RBAC contract emitter."""

import json
from typing import Dict, Any

from engine.ise.idl_parser import ParsedIDL


def emit_rbac(parsed: ParsedIDL) -> Dict[str, Any]:
    """Emit RBAC contract from parsed IDL.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        RBAC contract as dict.
    """
    roles = []

    for actor in parsed.actors:
        # Build permissions list
        permissions = []
        for perm in actor.permissions:
            for action in sorted(perm.actions):
                permissions.append(f"{perm.resource}.{action}")

        # If no permissions defined, add defaults based on role type
        if not permissions:
            for entity in parsed.entities:
                entity_type = entity.entity_type
                if actor.role in ("manager", "admin", "supervisor", "director"):
                    permissions.extend([
                        f"{entity_type}.create",
                        f"{entity_type}.read",
                        f"{entity_type}.approve",
                    ])
                elif actor.role in ("analyst", "employee", "user"):
                    permissions.extend([
                        f"{entity_type}.create",
                        f"{entity_type}.read",
                    ])
                elif actor.role in ("viewer", "auditor"):
                    permissions.append(f"{entity_type}.read")

        roles.append({
            "name": actor.role,
            "permissions": sorted(set(permissions)),
        })

    return {
        "version": "1.0",
        "name": "rbac",
        "roles": sorted(roles, key=lambda r: r["name"]),
    }


def emit_rbac_json(parsed: ParsedIDL) -> str:
    """Emit RBAC contract as JSON string.

    Args:
        parsed: Parsed IDL structure.

    Returns:
        JSON string with sorted keys.
    """
    return json.dumps(emit_rbac(parsed), indent=2, sort_keys=True)
