"""Operations contract emitter for ISE compiler.

Emits operations.json from IRCS v1 operations data.
The emitter works with data already in ParsedIDL or directly from IRCS.

Operations are sorted deterministically by (method, path, operation_id)
for consistent hashing.
"""

import json
from typing import Any, Dict, List, Optional

from engine.core.operations import OPERATIONS_SCHEMA_VERSION


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
