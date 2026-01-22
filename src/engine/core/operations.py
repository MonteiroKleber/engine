"""OperationRegistry - Runtime registry for operation definitions.

Provides lookup of operations by endpoint_sig or (method, path).
Compatible with both single-dept and multi-dept bundles.

Legacy bundles without operations.json will have None/empty registry
and continue to operate normally.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# Schema version
OPERATIONS_SCHEMA_VERSION = "1.0"

# Valid HTTP methods
VALID_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})

# Path validation regex: must start with /, cannot contain ..
PATH_PATTERN = re.compile(r"^/[^.][^.]*$|^/[^.]*[^.]$|^/$|^/[^.]+$")


class OperationsSchemaError(Exception):
    """Raised when operations schema validation fails."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class Operation:
    """A single operation definition."""

    operation_id: str
    method: str  # GET, POST, PUT, PATCH, DELETE
    path: str  # e.g., "/finance/expenses"
    endpoint_sig: str  # e.g., "POST /finance/expenses"
    permission: str  # e.g., "expense.create"
    scope: str = "tenant"  # "tenant" or "global"
    idempotency: str = "none"  # "required", "optional", "none"
    errors: List[int] = field(default_factory=list)
    bind: Optional[Dict[str, Any]] = None  # {"kind": "create", "entity": "Expense"}


@dataclass
class OperationsDef:
    """Operations definition for a department."""

    dept_id: Optional[str]
    operations: List[Operation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        result: Dict[str, Any] = {
            "operations_schema_version": OPERATIONS_SCHEMA_VERSION,
            "operations": [
                {
                    "operation_id": op.operation_id,
                    "method": op.method,
                    "path": op.path,
                    "endpoint_sig": op.endpoint_sig,
                    "permission": op.permission,
                    "scope": op.scope,
                    "idempotency": op.idempotency,
                    "errors": op.errors,
                    **({"bind": op.bind} if op.bind else {}),
                }
                for op in self.operations
            ],
        }
        if self.dept_id:
            result["dept_id"] = self.dept_id
        return result


# Global registry per department
# Key: dept_id (or "_single" for single-mode)
_operations: Dict[str, OperationsDef] = {}

SINGLE_MODE_KEY = "_single"


def set_operations(dept_id: Optional[str], ops_def: Optional[OperationsDef]) -> None:
    """Set operations for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.
        ops_def: Operations definition, or None to clear.
    """
    key = dept_id or SINGLE_MODE_KEY
    if ops_def is None:
        _operations.pop(key, None)
    else:
        _operations[key] = ops_def


def get_operations(dept_id: Optional[str]) -> Optional[OperationsDef]:
    """Get operations for a department (or single mode).

    Args:
        dept_id: Department ID, or None for single mode.

    Returns:
        OperationsDef if found, None otherwise.
    """
    key = dept_id or SINGLE_MODE_KEY
    return _operations.get(key)


def get_operation_by_endpoint_sig(
    dept_id: Optional[str], endpoint_sig: str
) -> Optional[Operation]:
    """Lookup operation by endpoint_sig.

    Args:
        dept_id: Department ID, or None for single mode.
        endpoint_sig: Canonical endpoint signature (e.g., "POST /finance/expenses").

    Returns:
        Operation if found, None otherwise.
    """
    ops_def = get_operations(dept_id)
    if ops_def is None:
        return None
    for op in ops_def.operations:
        if op.endpoint_sig == endpoint_sig:
            return op
    return None


def get_operation_by_method_path(
    dept_id: Optional[str], method: str, path: str
) -> Optional[Operation]:
    """Lookup operation by method + path.

    Args:
        dept_id: Department ID, or None for single mode.
        method: HTTP method (e.g., "POST").
        path: Path template (e.g., "/finance/expenses").

    Returns:
        Operation if found, None otherwise.
    """
    ops_def = get_operations(dept_id)
    if ops_def is None:
        return None
    method_upper = method.upper()
    for op in ops_def.operations:
        if op.method == method_upper and op.path == path:
            return op
    return None


def reset_all_operations() -> None:
    """Clear all operations (for testing)."""
    _operations.clear()


def _validate_path(path: str, context: str) -> None:
    """Validate path is absolute and safe.

    Args:
        path: Path to validate.
        context: Context for error message.

    Raises:
        OperationsSchemaError: If path is invalid.
    """
    if not path:
        raise OperationsSchemaError(
            code="OPERATIONS_INVALID",
            message=f"{context}: path cannot be empty",
        )
    if not path.startswith("/"):
        raise OperationsSchemaError(
            code="OPERATIONS_INVALID",
            message=f"{context}: path must be absolute (start with /), got '{path}'",
        )
    if ".." in path:
        raise OperationsSchemaError(
            code="OPERATIONS_INVALID",
            message=f"{context}: path cannot contain '..', got '{path}'",
        )


def _validate_method(method: str, context: str) -> str:
    """Validate and normalize HTTP method.

    Args:
        method: HTTP method.
        context: Context for error message.

    Returns:
        Normalized (uppercase) method.

    Raises:
        OperationsSchemaError: If method is invalid.
    """
    method_upper = method.upper()
    if method_upper not in VALID_METHODS:
        raise OperationsSchemaError(
            code="OPERATIONS_INVALID",
            message=f"{context}: invalid method '{method}'. Must be one of {sorted(VALID_METHODS)}",
        )
    return method_upper


def parse_operations_data(
    data: Dict[str, Any], dept_id: Optional[str] = None
) -> OperationsDef:
    """Parse operations from dict.

    Schema v1.0:
    {
      "operations_schema_version": "1.0",
      "dept_id": "finance",  // optional
      "operations": [
        {
          "operation_id": "expense_create",
          "method": "POST",
          "path": "/finance/expenses",
          "endpoint_sig": "POST /finance/expenses",
          "permission": "expense.create",
          "scope": "tenant",
          "idempotency": "required",
          "errors": [400, 401, 403],
          "bind": { "kind": "create", "entity": "Expense" }
        }
      ]
    }

    Args:
        data: Dict with operations data.
        dept_id: Optional override for dept_id.

    Returns:
        OperationsDef with parsed operations.

    Raises:
        OperationsSchemaError: If schema validation fails.
    """
    schema_version = data.get("operations_schema_version")
    if schema_version != OPERATIONS_SCHEMA_VERSION:
        raise OperationsSchemaError(
            code="OPERATIONS_INVALID",
            message=f"Unsupported operations_schema_version: {schema_version}. Expected '{OPERATIONS_SCHEMA_VERSION}'.",
        )

    # Use dept_id from data or override
    effective_dept_id = dept_id or data.get("dept_id")

    operations: List[Operation] = []
    operations_list = data.get("operations", [])

    for i, op_data in enumerate(operations_list):
        context = f"Operation[{i}]"

        # Required fields
        operation_id = op_data.get("operation_id")
        if not operation_id:
            raise OperationsSchemaError(
                code="OPERATIONS_INVALID",
                message=f"{context}: operation_id is required",
            )
        context = f"Operation '{operation_id}'"

        method = op_data.get("method")
        if not method:
            raise OperationsSchemaError(
                code="OPERATIONS_INVALID",
                message=f"{context}: method is required",
            )
        method = _validate_method(method, context)

        path = op_data.get("path")
        if not path:
            raise OperationsSchemaError(
                code="OPERATIONS_INVALID",
                message=f"{context}: path is required",
            )
        _validate_path(path, context)

        endpoint_sig = op_data.get("endpoint_sig")
        if not endpoint_sig:
            raise OperationsSchemaError(
                code="OPERATIONS_INVALID",
                message=f"{context}: endpoint_sig is required",
            )

        # Validate endpoint_sig format matches method + path
        expected_sig = f"{method} {path}"
        if endpoint_sig != expected_sig:
            raise OperationsSchemaError(
                code="OPERATIONS_INVALID",
                message=f"{context}: endpoint_sig '{endpoint_sig}' doesn't match '{expected_sig}'",
            )

        permission = op_data.get("permission")
        if not permission:
            raise OperationsSchemaError(
                code="OPERATIONS_INVALID",
                message=f"{context}: permission is required",
            )

        # Optional fields with defaults
        scope = op_data.get("scope", "tenant")
        if scope not in ("tenant", "global"):
            raise OperationsSchemaError(
                code="OPERATIONS_INVALID",
                message=f"{context}: scope must be 'tenant' or 'global', got '{scope}'",
            )

        idempotency = op_data.get("idempotency", "none")
        if idempotency not in ("required", "optional", "none"):
            raise OperationsSchemaError(
                code="OPERATIONS_INVALID",
                message=f"{context}: idempotency must be 'required', 'optional', or 'none', got '{idempotency}'",
            )

        errors = op_data.get("errors", [])
        if not isinstance(errors, list):
            raise OperationsSchemaError(
                code="OPERATIONS_INVALID",
                message=f"{context}: errors must be a list",
            )

        bind = op_data.get("bind")

        operations.append(
            Operation(
                operation_id=operation_id,
                method=method,
                path=path,
                endpoint_sig=endpoint_sig,
                permission=permission,
                scope=scope,
                idempotency=idempotency,
                errors=errors,
                bind=bind,
            )
        )

    return OperationsDef(dept_id=effective_dept_id, operations=operations)


def load_operations_from_file(file_path: Path) -> Optional[OperationsDef]:
    """Load operations from a JSON file.

    Args:
        file_path: Path to operations.json file.

    Returns:
        OperationsDef if valid and exists, None if file doesn't exist.

    Raises:
        OperationsSchemaError: If file exists but is invalid.
    """
    if not file_path.exists():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_operations_data(data)
    except json.JSONDecodeError as e:
        raise OperationsSchemaError(
            code="OPERATIONS_INVALID",
            message=f"Invalid JSON in operations.json: {e}",
        )
