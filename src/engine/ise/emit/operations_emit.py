"""Operations contract emitter for ISE compiler.

Emits operations.json from IRCS v1 operations data.
The emitter works with data already in ParsedIDL or directly from IRCS.

Operations are sorted deterministically by (method, path, operation_id)
for consistent hashing.
"""

import json
from typing import Any, Dict, List, Optional

from engine.core.operations import OPERATIONS_SCHEMA_VERSION


def _normalize_state_name(state: Optional[str]) -> Optional[str]:
    if not state or not isinstance(state, str):
        return None
    return state.upper()


def _extract_guard_literal(guard: Any) -> Any:
    """Return bool/None when guard is a literal, else return original value."""
    if guard is True or guard is False or guard is None:
        return guard
    if isinstance(guard, dict) and "lit" in guard:
        return guard.get("lit")
    return guard


def _convert_workflow_effects(effects: Any) -> List[Dict[str, Any]]:
    """Convert IRCS workflow effects into dispatcher-supported effect dicts."""
    if not isinstance(effects, list):
        return []

    converted: List[Dict[str, Any]] = []
    for eff in effects:
        if not isinstance(eff, dict):
            continue
        kind = eff.get("kind")
        if kind == "set_state":
            value = _normalize_state_name(eff.get("value"))
            if value:
                converted.append({"type": "set_state", "value": value})
        elif kind == "set_field":
            field = eff.get("field")
            value = eff.get("value")
            if isinstance(value, dict) and "lit" in value:
                value = value.get("lit")
            if isinstance(field, str):
                converted.append({"type": "set_field", "field": field, "value": value})
        elif kind == "bump_version":
            field = eff.get("field")
            by = eff.get("by", 1)
            if field == "version" and by == 1:
                converted.append({"type": "bump_version", "value": 1})
    return converted


def _lookup_transition_def_from_ircs(
    ir: Dict[str, Any],
    workflow_name: Optional[str],
    transition_name: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not workflow_name or not transition_name:
        return None

    workflows = ir.get("workflows", [])
    if not isinstance(workflows, list):
        return None

    for wf in workflows:
        if not isinstance(wf, dict):
            continue
        if wf.get("name") != workflow_name:
            continue
        transitions = wf.get("transitions", [])
        if not isinstance(transitions, list):
            return None
        for tr in transitions:
            if not isinstance(tr, dict):
                continue
            if tr.get("name") != transition_name:
                continue
            return {
                "guard": _extract_guard_literal(tr.get("guard")),
                "from": _normalize_state_name(tr.get("from")),
                "to": _normalize_state_name(tr.get("to")),
                "effects": _convert_workflow_effects(tr.get("effects", [])),
                "approvals": tr.get("approvals"),
            }
    return None


def emit_operations_from_ircs(
    ir: Dict[str, Any],
    dept_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit operations contract from IRCS v1 data.

    Extracts operations from IRCS v1 operations.api section.

    Args:
        ir: IRCS v1 dict.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        Dict with operations contract structure.
    """
    operations_list: List[Dict[str, Any]] = []

    # Extract operations from IRCS
    operations_data = ir.get("operations", {})
    api_endpoints = operations_data.get("api", [])

    for endpoint in api_endpoints:
        operation_id = endpoint.get("id", "")
        method = endpoint.get("method", "GET").upper()
        path = endpoint.get("path", "")

        # Skip invalid operations
        if not operation_id or not path:
            continue

        # Validate path is absolute
        if not path.startswith("/"):
            continue

        # Build endpoint_sig in canonical format
        endpoint_sig = f"{method} {path}"

        # Extract permission
        permission = endpoint.get("permission", "")
        if not permission:
            # Derive from bind if available
            bind = endpoint.get("bind", {})
            entity = bind.get("entity", "").lower()
            kind = bind.get("kind", "read")
            if entity:
                permission = f"{entity}.{kind}"
            else:
                permission = operation_id.replace("_", ".")

        # Extract other fields
        scope = endpoint.get("scope", "tenant")
        idempotency = endpoint.get("idempotency", "none")
        errors = endpoint.get("errors", [400, 401, 403])
        bind = endpoint.get("bind")

        op_dict: Dict[str, Any] = {
            "operation_id": operation_id,
            "method": method,
            "path": path,
            "endpoint_sig": endpoint_sig,
            "permission": permission,
            "scope": scope,
            "idempotency": idempotency,
            "errors": errors,
        }

        if bind:
            # If this is a workflow transition, enrich bind with transition_def for runtime execution.
            if isinstance(bind, dict) and bind.get("kind") == "transition":
                workflow_name = bind.get("workflow")
                transition_name = bind.get("transition")
                transition_def = _lookup_transition_def_from_ircs(ir, workflow_name, transition_name)
                if transition_def:
                    bind = dict(bind)
                    bind["transition_def"] = transition_def
            op_dict["bind"] = bind

        operations_list.append(op_dict)

    # Sort deterministically by (method, path, operation_id)
    operations_list.sort(key=lambda op: (op["method"], op["path"], op["operation_id"]))

    result: Dict[str, Any] = {
        "operations_schema_version": OPERATIONS_SCHEMA_VERSION,
        "operations": operations_list,
    }

    if dept_id:
        result["dept_id"] = dept_id

    return result


def emit_operations_from_parsed(
    parsed: Any,  # ParsedIDL - using Any to avoid circular import
    dept_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit operations contract from ParsedIDL.

    Generates operations from usecases if no direct IRCS data.
    This is a fallback for legacy IDL sources.

    Args:
        parsed: ParsedIDL instance.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        Dict with operations contract structure.
    """
    operations_list: List[Dict[str, Any]] = []

    # Generate operations from usecases
    for usecase in parsed.usecases:
        main_flow = usecase.main_flow

        # Parse main_flow if it contains operation info
        # Format: "create: POST /finance/expenses" or similar
        if ": " in main_flow:
            parts = main_flow.split(": ", 1)
            kind = parts[0].lower()
            endpoint_info = parts[1]

            if " " in endpoint_info:
                method, path = endpoint_info.split(" ", 1)
                method = method.upper()

                # Validate
                if not path.startswith("/"):
                    continue

                operation_id = usecase.name
                endpoint_sig = f"{method} {path}"

                # Derive permission from path
                path_parts = path.strip("/").split("/")
                if len(path_parts) >= 2:
                    # /finance/expenses -> expense.create
                    resource = path_parts[1].rstrip("s")  # expenses -> expense
                    permission = f"{resource}.{kind}"
                else:
                    permission = operation_id.replace("_", ".")

                op_dict: Dict[str, Any] = {
                    "operation_id": operation_id,
                    "method": method,
                    "path": path,
                    "endpoint_sig": endpoint_sig,
                    "permission": permission,
                    "scope": "tenant",
                    "idempotency": "required" if kind == "create" else "none",
                    "errors": [400, 401, 403],
                }

                if kind in ("create", "read", "update", "delete"):
                    # Infer entity from path
                    entity_name = path_parts[1].rstrip("s").title() if len(path_parts) >= 2 else ""
                    if entity_name:
                        op_dict["bind"] = {"kind": kind, "entity": entity_name}

                operations_list.append(op_dict)

    # Sort deterministically
    operations_list.sort(key=lambda op: (op["method"], op["path"], op["operation_id"]))

    result: Dict[str, Any] = {
        "operations_schema_version": OPERATIONS_SCHEMA_VERSION,
        "operations": operations_list,
    }

    if dept_id:
        result["dept_id"] = dept_id

    return result


def emit_operations(
    ir_or_parsed: Any,
    dept_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit operations contract from IRCS v1 or ParsedIDL.

    Auto-detects input type and routes to appropriate emitter.

    Args:
        ir_or_parsed: IRCS v1 dict or ParsedIDL instance.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        Dict with operations contract structure.
    """
    # Check if this is IRCS v1 (has "ir_version" or "operations" dict with "api")
    if isinstance(ir_or_parsed, dict):
        if ir_or_parsed.get("ir_version") or (
            isinstance(ir_or_parsed.get("operations"), dict)
            and "api" in ir_or_parsed.get("operations", {})
        ):
            return emit_operations_from_ircs(ir_or_parsed, dept_id)

    # Assume ParsedIDL
    return emit_operations_from_parsed(ir_or_parsed, dept_id)


def emit_operations_json(
    ir_or_parsed: Any,
    dept_id: Optional[str] = None,
) -> str:
    """Emit operations contract as JSON string.

    Args:
        ir_or_parsed: IRCS v1 dict or ParsedIDL instance.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        JSON string with sorted keys for deterministic output.
    """
    operations = emit_operations(ir_or_parsed, dept_id)
    return json.dumps(operations, indent=2, sort_keys=True)
