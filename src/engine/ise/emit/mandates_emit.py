"""Mandates contract emitter for ISE compiler.

Emits mandates.json in the format expected by the runtime mandates engine.
Per MVP decision (2026-01-17): mandates.json is a mandatory institutional contract.

IDL v1.1: mandates/autonomy are first-class. No silent defaults.
"""

import json
from typing import Any, Dict, List, Optional

from ..idl_parser import ParsedIDL, IDLMandate, IDLMandateLimit


# Mandate schema version
MANDATE_SCHEMA_VERSION = "1.0"


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
            # Multi-dept mode: use dept-specific mandates
            for mandate in parsed.dept_mandates[dept_id]:
                mandates_list.append(_mandate_to_dict(mandate))
        elif parsed.mandates:
            # Single mode: use global mandates
            for mandate in parsed.mandates:
                mandates_list.append(_mandate_to_dict(mandate))
        # else: emit empty list (explicit deny-all by design)
    # else: v1.0 legacy - emit empty list (backward compatible)

    return {
        "mandate_schema_version": MANDATE_SCHEMA_VERSION,
        "mandates": mandates_list,
    }


def emit_mandates_json(
    parsed: ParsedIDL,
    dept_id: Optional[str] = None,
) -> str:
    """Emit mandates contract as JSON string.

    Args:
        parsed: Parsed IDL structure.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        JSON string with sorted keys.
    """
    mandates = emit_mandates(parsed, dept_id)
    return json.dumps(mandates, indent=2, sort_keys=True)
