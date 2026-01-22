"""OpenAPI Overlay - Enrich FastAPI OpenAPI with OperationRegistry data.

This module provides OpenAPI schema enrichment:
- operationId from OperationSpec.operation_id
- responses from OperationSpec.errors
- Idempotency-Key header when idempotency=required
- Security schemes based on ENGINE_AUTH_MODE
- Tags derived from path prefix

The overlay approach modifies FastAPI's generated OpenAPI rather than
building a new schema from scratch.
"""

import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .operations import Operation, get_operations
from .actor_context import get_auth_mode, AuthMode


# Error code descriptions
ERROR_DESCRIPTIONS = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def _get_error_description(code: int) -> str:
    """Get description for an error code.

    Args:
        code: HTTP status code.

    Returns:
        Human-readable description.
    """
    return ERROR_DESCRIPTIONS.get(code, f"Error {code}")


def _derive_tag_from_path(path: str) -> str:
    """Derive tag from path prefix.

    Examples:
        /finance/expenses -> finance
        /support/tickets -> support
        /approvals/{id}/decide -> approvals
        /admin/institutions -> admin
        /d/{dept_id}/finance/expenses -> finance

    Args:
        path: Route path.

    Returns:
        Tag derived from first path segment.
    """
    # Remove /d/{dept_id}/ prefix if present
    if path.startswith("/d/{"):
        # Find the end of the dept_id param
        match = re.match(r"/d/\{[^}]+\}(/.+)", path)
        if match:
            path = match.group(1)

    # Get first segment
    parts = path.strip("/").split("/")
    if parts and parts[0]:
        return parts[0]
    return "default"


def _normalize_path_for_matching(path: str) -> str:
    """Normalize path for matching between registry and FastAPI.

    FastAPI may use different path param names. We normalize to compare.

    Args:
        path: Route path template.

    Returns:
        Normalized path for comparison.
    """
    # Replace all path params with generic {param}
    return re.sub(r"\{[^}]+\}", "{param}", path)


def _build_security_schemes() -> Dict[str, Any]:
    """Build OpenAPI security schemes based on auth mode.

    Returns:
        Dictionary of security scheme definitions.
    """
    return {
        "ActorIdHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Actor-Id",
            "description": "Actor UUID (required in dev mode)",
        },
        "ActorRolesHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Actor-Roles",
            "description": "Comma-separated list of roles (optional in dev mode)",
        },
        "ActorTokenHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Actor-Token",
            "description": "Authentication token (required in strict mode)",
        },
        "InstitutionHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Institution-Id",
            "description": "Institution UUID (required for multi-tenant operations)",
        },
    }


def _get_security_requirements() -> List[Dict[str, List]]:
    """Get security requirements based on current auth mode.

    Returns:
        List of security requirement objects.
    """
    auth_mode = get_auth_mode()
    if auth_mode == AuthMode.STRICT:
        return [{"ActorTokenHeader": [], "InstitutionHeader": []}]
    else:
        return [{"ActorIdHeader": [], "InstitutionHeader": []}]


def _enrich_operation_from_registry(
    path_item: Dict[str, Any],
    method: str,
    op: Operation,
) -> None:
    """Enrich an OpenAPI operation with registry data.

    Args:
        path_item: OpenAPI path item containing methods.
        method: HTTP method (lowercase).
        op: Operation from registry.
    """
    if method not in path_item:
        return

    operation = path_item[method]

    # Fix operationId - use exact value from registry
    operation["operationId"] = op.operation_id

    # Add/update tags
    operation["tags"] = [_derive_tag_from_path(op.path)]

    # Add responses from errors
    operation.setdefault("responses", {})
    for error_code in op.errors:
        code_str = str(error_code)
        if code_str not in operation["responses"]:
            operation["responses"][code_str] = {
                "description": _get_error_description(error_code),
            }

    # Add Idempotency-Key header if required
    if op.idempotency == "required":
        operation.setdefault("parameters", [])
        # Check if already present
        has_idempotency = any(
            p.get("name") == "Idempotency-Key" and p.get("in") == "header"
            for p in operation["parameters"]
        )
        if not has_idempotency:
            operation["parameters"].append({
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
                "description": "Unique request identifier for idempotency",
            })

    # Add security requirements
    operation["security"] = _get_security_requirements()


def _find_matching_path(
    openapi_paths: Dict[str, Any],
    registry_path: str,
) -> Optional[str]:
    """Find matching path in OpenAPI schema for a registry path.

    Args:
        openapi_paths: OpenAPI paths dictionary.
        registry_path: Path from registry.

    Returns:
        Matching path key from OpenAPI, or None if not found.
    """
    normalized_registry = _normalize_path_for_matching(registry_path)

    for openapi_path in openapi_paths:
        normalized_openapi = _normalize_path_for_matching(openapi_path)
        if normalized_openapi == normalized_registry:
            return openapi_path

    return None


def create_openapi_schema(
    app: FastAPI,
    dept_id: Optional[str] = None,
    filter_by_dept: bool = False,
) -> Dict[str, Any]:
    """Create OpenAPI schema with registry enrichment.

    Args:
        app: FastAPI application instance.
        dept_id: Optional department ID for registry lookup.
        filter_by_dept: If True, filter paths to only those for the dept.

    Returns:
        Enriched OpenAPI schema dictionary.
    """
    # Start with FastAPI's generated schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description=app.description,
    )

    # Add security schemes
    openapi_schema.setdefault("components", {})
    openapi_schema["components"]["securitySchemes"] = _build_security_schemes()

    # Get operations from registry
    ops_def = get_operations(dept_id)
    if ops_def:
        for op in ops_def.operations:
            # Try to find matching path in OpenAPI
            method = op.method.lower()

            # Check direct path match
            if op.path in openapi_schema.get("paths", {}):
                _enrich_operation_from_registry(
                    openapi_schema["paths"][op.path],
                    method,
                    op,
                )
            else:
                # Try normalized matching
                matching_path = _find_matching_path(
                    openapi_schema.get("paths", {}),
                    op.path,
                )
                if matching_path:
                    _enrich_operation_from_registry(
                        openapi_schema["paths"][matching_path],
                        method,
                        op,
                    )

            # Also check dept variant path
            dept_path = f"/d/{{dept_id}}{op.path}"
            if dept_path in openapi_schema.get("paths", {}):
                _enrich_operation_from_registry(
                    openapi_schema["paths"][dept_path],
                    method,
                    op,
                )
            else:
                matching_dept_path = _find_matching_path(
                    openapi_schema.get("paths", {}),
                    dept_path,
                )
                if matching_dept_path:
                    _enrich_operation_from_registry(
                        openapi_schema["paths"][matching_dept_path],
                        method,
                        op,
                    )

    # Filter by dept if requested
    if filter_by_dept and dept_id:
        filtered_paths = {}
        dept_prefix = f"/d/{dept_id}/"
        dept_param_prefix = "/d/{dept_id}/"

        for path, path_item in openapi_schema.get("paths", {}).items():
            # Include paths that:
            # 1. Start with /d/{dept_id}/ (parameterized)
            # 2. Or are base paths from the dept's registry
            if path.startswith(dept_param_prefix):
                filtered_paths[path] = path_item
            elif ops_def:
                # Check if this path is in the dept's registry
                for op in ops_def.operations:
                    matching = _find_matching_path({path: path_item}, op.path)
                    if matching:
                        filtered_paths[path] = path_item
                        break

        openapi_schema["paths"] = filtered_paths

    return openapi_schema


def setup_custom_openapi(app: FastAPI) -> None:
    """Setup custom OpenAPI generation for the app.

    This replaces FastAPI's default openapi() method with our
    enriched version.

    Args:
        app: FastAPI application instance.
    """

    def custom_openapi() -> Dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        app.openapi_schema = create_openapi_schema(app)
        return app.openapi_schema

    app.openapi = custom_openapi
