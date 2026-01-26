"""Mandates contract emitter for ISE compiler.

Emits mandates.json in the format expected by the runtime mandates engine.
Per MVP decision (2026-01-17): mandates.json is a mandatory institutional contract.

IDL v1.1: mandates/autonomy are first-class. No silent defaults.
"""

import json
from typing import Any, Dict, List, Optional, Set

from ..idl_parser import ParsedIDL, IDLMandate, IDLMandateLimit


# Mandate schema version
MANDATE_SCHEMA_VERSION = "1.0"

POST_ONLY_ENDPOINT_SIGS: Set[str] = {
    "POST /approvals/{approval_id}/decide",
}


def _mandate_limit_to_dict(limit: IDLMandateLimit) -> Dict[str, Any]:
    """Convert IDLMandateLimit to runtime dict format."""
    result: Dict[str, Any] = {
        "rule_type": limit.rule_type,
        "field_path": limit.field_path,
    }
    if limit.value is not None:
        result["value"] = limit.value
    if limit.message:
        result["message"] = limit.message
    return result


def _mandate_to_dict(mandate: IDLMandate) -> Dict[str, Any]:
    """Convert IDLMandate to runtime dict format."""
    result: Dict[str, Any] = {
        "mandate_id": mandate.mandate_id,
        "endpoint_sig": mandate.endpoint_sig,
        "phase": mandate.phase,
        "allowed_roles": mandate.allowed_roles,
    }

    if mandate.limits:
        result["limits"] = [_mandate_limit_to_dict(l) for l in mandate.limits]

    if mandate.message:
        result["message"] = mandate.message

    return result


def emit_mandates(
    parsed: ParsedIDL,
    dept_id: Optional[str] = None,
    ir: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Emit mandates contract from parsed IDL.

    IDL v1.1 behavior:
    - If mandates are defined in IDL, emit exactly those mandates.
    - If IDL v1.1 has no mandates and multi-dept mode, check dept_mandates.
    - If mandates are not defined in IDL v1.1, emit empty list (valid format,
      represents explicit "deny all" by design - use gap detection to warn).

    IDL v1.0 (legacy) behavior:
    - Emit empty mandates array (default-deny, backward compatible).

    Args:
        parsed: Parsed IDL structure.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        Dict with mandate contract structure.
    """
    mandates_list: List[Dict[str, Any]] = []

    if parsed.idl_version == "1.1":
        # IDL v1.1: emit exactly what's defined
        if dept_id and dept_id in parsed.dept_mandates:
            for mandate in parsed.dept_mandates[dept_id]:
                mandates_list.append(_mandate_to_dict(mandate))
        elif parsed.mandates:
            for mandate in parsed.mandates:
                mandates_list.append(_mandate_to_dict(mandate))

    if not mandates_list and ir:
        # IRCS v1 canonical path (IDL DSL v1.2.2):
        # mandates/autonomy are not yet first-class in the DSL, but the runtime
        # requires mandates.json and treats empty list as explicit deny-all.
        # Canonical bridge: generate minimum mandates from operations + RBAC.

        # Build permission index: permission string -> allowed roles
        perm_to_roles: Dict[str, Set[str]] = {}
        for actor in parsed.actors:
            role = actor.role
            for perm in actor.permissions:
                for action in perm.actions:
                    perm_to_roles.setdefault(f"{perm.resource}.{action}", set()).add(role)

        operations = (ir.get("operations") or {}).get("api") or []
        for op in operations:
            method = op.get("method")
            path = op.get("path")
            op_id = op.get("id") or op.get("operation_id") or "op"
            permission = op.get("permission")
            if not method or not path:
                continue

            endpoint_sig = f"{method} {path}"
            phase = "post" if endpoint_sig in POST_ONLY_ENDPOINT_SIGS else "pre"
            allowed_roles = sorted(list(perm_to_roles.get(permission or "", set())))

            mandates_list.append(
                {
                    "mandate_id": f"{op_id}:{phase}",
                    "endpoint_sig": endpoint_sig,
                    "phase": phase,
                    "allowed_roles": allowed_roles,
                }
            )

    return {
        "mandate_schema_version": MANDATE_SCHEMA_VERSION,
        "mandates": mandates_list,
    }


def emit_mandates_json(
    parsed: ParsedIDL,
    dept_id: Optional[str] = None,
    ir: Optional[Dict[str, Any]] = None,
) -> str:
    """Emit mandates contract as JSON string.

    Args:
        parsed: Parsed IDL structure.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        JSON string with sorted keys.
    """
    mandates = emit_mandates(parsed, dept_id=dept_id, ir=ir)
    return json.dumps(mandates, indent=2, sort_keys=True)
