"""IDL Router - Dynamic route registration from OperationRegistry.

This module provides ENGINE_API_MODE-driven route registration:
- legacy (default): No IDL routes, only legacy handlers
- idl: Only IDL-driven routes (fails startup on collision)
- both: Legacy + IDL routes (skips colliding IDL routes with warning)

Routes are registered from OperationRegistry operations with two variants:
- Single-dept: Uses operation.path directly (e.g., /finance/expenses)
- Multi-dept: Also registers /d/{dept_id} + path variant (e.g., /d/{dept_id}/finance/expenses)
"""

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .operations import Operation, get_operations, get_operation_by_endpoint_sig
from .dispatcher import (
    dispatch_create,
    dispatch_read,
    dispatch_list,
    dispatch_delete,
    dispatch_approval_request,
    dispatch_approval_decide,
    dispatch_transition,
    DispatchResult,
)
from .approvals import get_approvals_policy
from .actor_context import ActorContext, DEFAULT_TENANT_ID
from .institution_context import get_request_institution_id
from .dept_context import get_request_dept
from .logging import get_logger
from .errors import RUNTIME_OPERATION_NOT_FOUND


# Valid API modes
API_MODE_LEGACY = "legacy"
API_MODE_IDL = "idl"
API_MODE_BOTH = "both"
VALID_API_MODES = frozenset({API_MODE_LEGACY, API_MODE_IDL, API_MODE_BOTH})


def get_api_mode() -> str:
    """Get API mode from ENGINE_API_MODE env var.

    Returns:
        One of: "legacy" (default), "idl", or "both".
    """
    mode = os.environ.get("ENGINE_API_MODE", API_MODE_LEGACY).lower()
    if mode not in VALID_API_MODES:
        return API_MODE_LEGACY
    return mode


def _normalize_path_for_collision(path: str) -> str:
    """Normalize path for collision detection.

    Replaces path parameters like {expense_id} with generic {param}
    so that /expenses/{expense_id} matches /expenses/{id}.

    Args:
        path: Route path template.

    Returns:
        Normalized path with generic parameter placeholders.
    """
    return re.sub(r"\{[^}]+\}", "{param}", path)


def _has_collision(app: FastAPI, method: str, path: str) -> bool:
    """Check if a route already exists in the app.

    Args:
        app: FastAPI application instance.
        method: HTTP method (GET, POST, etc.).
        path: Route path template.

    Returns:
        True if a matching route already exists.
    """
    normalized_path = _normalize_path_for_collision(path)
    method_upper = method.upper()

    for route in app.routes:
        if isinstance(route, APIRoute):
            route_path = _normalize_path_for_collision(route.path)
            if route_path == normalized_path and method_upper in route.methods:
                return True
    return False


def _get_registered_routes(app: FastAPI) -> Set[Tuple[str, str]]:
    """Get set of (method, normalized_path) tuples for all routes.

    Args:
        app: FastAPI application instance.

    Returns:
        Set of (method, normalized_path) tuples.
    """
    routes = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            normalized_path = _normalize_path_for_collision(route.path)
            for method in route.methods:
                routes.add((method.upper(), normalized_path))
    return routes


def _extract_path_params(request: Request) -> Dict[str, str]:
    """Extract path parameters from request.

    Args:
        request: FastAPI Request object.

    Returns:
        Dict of path parameter name -> value.
    """
    return dict(request.path_params)


async def _read_request_body(request: Request) -> Dict[str, Any]:
    """Read and parse JSON request body.

    Args:
        request: FastAPI Request object.

    Returns:
        Parsed JSON body as dict, or empty dict if no body.
    """
    body_bytes = await request.body()
    if not body_bytes:
        return {}
    try:
        return json.loads(body_bytes)
    except json.JSONDecodeError:
        return {}


def _create_idl_handler(
    operation: Operation,
    dept_from_path: bool = False,
    fixed_dept_id: Optional[str] = None,
) -> Callable:
    """Create a handler function for an IDL operation.

    IMPORTANT (Etapa 6.6): This handler does NOT capture the operation object
    in closure. Instead, it captures only the endpoint_sig and resolves the
    current operation from the registry at request time. This enables hot-swap
    of bundles without process restart.

    Args:
        operation: Operation definition from registry (used only to extract endpoint_sig).
        dept_from_path: If True, extract dept_id from path param {dept_id}.
        fixed_dept_id: If set, use this dept_id for registry lookup (single-dept mode).

    Returns:
        Async handler function for FastAPI route.
    """
    # Capture ONLY endpoint_sig for dynamic lookup - NOT the operation object
    # This is critical for hot-swap: after reload_active_runtime(), the handler
    # will resolve the NEW operation from the updated registry.
    endpoint_sig = operation.endpoint_sig
    captured_dept_id = fixed_dept_id  # For single-dept mode registry lookup

    async def idl_handler(request: Request) -> JSONResponse:
        """Generic IDL route handler with dynamic operation lookup."""
        # Resolve institution_id for auth + storage (prefer request context, then headers).
        institution_id = get_request_institution_id(request)
        if not institution_id:
            institution_id = request.headers.get("X-Institution-Id")
        if not institution_id:
            institution_id = request.headers.get("X-Tenant-Id")
        if not institution_id:
            institution_id = DEFAULT_TENANT_ID

        # Build actor context using the canonical dependency (respects ENGINE_AUTH_MODE).
        # Local import avoids import-time surprises and keeps auth logic centralized.
        from engine.api.dependencies import get_actor_context

        actor = await get_actor_context(
            request,
            x_actor_id=request.headers.get("X-Actor-Id"),
            x_actor_roles=request.headers.get("X-Actor-Roles"),
            x_tenant_id=request.headers.get("X-Tenant-Id"),
            x_actor_token=request.headers.get("X-Actor-Token"),
            x_institution_id=institution_id,
            x_on_behalf_of=request.headers.get("X-On-Behalf-Of"),
        )

        # Resolve dept_id for request context
        if dept_from_path:
            # Multi-dept route: /d/{dept_id}/...
            path_params = _extract_path_params(request)
            dept_id = path_params.get("dept_id")
        else:
            # Single-dept route: use request context dept or None
            dept_id = get_request_dept(request)

        # DYNAMIC LOOKUP (Etapa 6.6): Resolve operation from CURRENT registry state.
        # After hot-swap, the registry may have changed. We use the dept_id
        # that was used during route registration (captured_dept_id) to lookup
        # the operation, not the request's dept_id.
        lookup_dept = captured_dept_id if not dept_from_path else dept_id
        current_operation = get_operation_by_endpoint_sig(lookup_dept, endpoint_sig)

        if current_operation is None:
            # Operation was removed after hot-swap
            return JSONResponse(
                status_code=404,
                content={
                    "code": RUNTIME_OPERATION_NOT_FOUND,
                    "message": f"Operation {endpoint_sig} not found in current registry",
                },
            )

        # Get bind.kind from CURRENT operation (may have changed after hot-swap)
        bind_kind = current_operation.bind.get("kind") if current_operation.bind else None

        # Route to appropriate dispatcher based on bind.kind
        path_params = _extract_path_params(request)
        result: DispatchResult

        if bind_kind == "create":
            # Check if approval required for this endpoint
            policy = get_approvals_policy(dept_id)
            rule = policy.get_rule_for_api(current_operation.endpoint_sig) if policy else None

            if rule:
                # Approval required - use approval request dispatcher
                request_body = await _read_request_body(request)
                result = await dispatch_approval_request(
                    institution_id=institution_id,
                    dept_id=dept_id,
                    actor=actor,
                    operation=current_operation,
                    request_body=request_body,
                    path_params=path_params,
                )
            else:
                # No approval - use standard create dispatcher
                request_body = await _read_request_body(request)
                result = await dispatch_create(
                    institution_id=institution_id,
                    dept_id=dept_id,
                    actor=actor,
                    operation=current_operation,
                    request_body=request_body,
                    path_params=path_params,
                )

        elif bind_kind == "read":
            # DSL v1.2.2 does not have bind.kind=list.
            # Canonical behavior: treat read endpoints without path params as list.
            if path_params:
                result = await dispatch_read(
                    institution_id=institution_id,
                    dept_id=dept_id,
                    actor=actor,
                    operation=current_operation,
                    path_params=path_params,
                )
            else:
                result = await dispatch_list(
                    institution_id=institution_id,
                    dept_id=dept_id,
                    actor=actor,
                    operation=current_operation,
                )

        elif bind_kind == "delete":
            result = await dispatch_delete(
                institution_id=institution_id,
                dept_id=dept_id,
                actor=actor,
                operation=current_operation,
                path_params=path_params,
            )

        elif bind_kind in {"approval", "approval_decide"}:
            # Extract approval_id from path params
            approval_id = path_params.get("approval_id")
            if not approval_id:
                return JSONResponse(
                    status_code=400,
                    content={
                        "code": "PATH_PARAM_MISSING",
                        "message": "Missing required path parameter: approval_id",
                    },
                )

            # Read decision from body
            request_body = await _read_request_body(request)
            decision = request_body.get("decision")
            reason = request_body.get("reason")

            if not decision:
                return JSONResponse(
                    status_code=400,
                    content={
                        "code": "DECISION_REQUIRED",
                        "message": "Decision is required in request body",
                    },
                )

            result = await dispatch_approval_decide(
                institution_id=institution_id,
                dept_id=dept_id,
                actor=actor,
                approval_id=approval_id,
                decision=decision,
                reason=reason,
            )

        elif bind_kind == "transition":
            # Read optional request body (may contain transition params)
            request_body = await _read_request_body(request)

            result = await dispatch_transition(
                institution_id=institution_id,
                dept_id=dept_id,
                actor=actor,
                operation=current_operation,
                path_params=path_params,
                request_body=request_body,
            )

        else:
            # Unknown bind.kind
            return JSONResponse(
                status_code=501,
                content={
                    "code": "BIND_KIND_UNSUPPORTED",
                    "message": f"Unsupported bind.kind: {bind_kind}",
                },
            )

        # Record IDL telemetry (per-institution, append-only) - Expansão 05
        from engine.core.idl_telemetry import record_idl_invocation

        record_idl_invocation(
            institution_id=institution_id,
            endpoint_sig=endpoint_sig,
            method=current_operation.method,
            path=current_operation.path,
            actor_id=actor.actor_id if actor else None,
            dept_id=dept_id,
        )

        return JSONResponse(
            status_code=result.status_code,
            content=result.response_body,
        )

    return idl_handler


def register_idl_routes(app: FastAPI, departments: Optional[List[str]] = None) -> int:
    """Register IDL routes from OperationRegistry.

    Called during app startup (lifespan) after load_bundle().

    For each operation in the registry:
    - Registers the base path (e.g., /finance/expenses)
    - If multi-dept mode, also registers /d/{dept_id} + path variant

    Args:
        app: FastAPI application instance.
        departments: List of department IDs (for multi-dept mode).
                    If None, assumes single-dept mode.

    Returns:
        Number of routes registered.

    Raises:
        RuntimeError: In 'idl' mode if collision detected.
    """
    logger = get_logger()
    api_mode = get_api_mode()

    if api_mode == API_MODE_LEGACY:
        logger.info("ENGINE_API_MODE=legacy, skipping IDL route registration")
        return 0

    routes_registered = 0
    collisions_skipped = 0

    # Get all operations to register
    # In single-dept mode: dept_id=None
    # In multi-dept mode: iterate departments
    dept_ids = departments if departments else [None]

    # Track which operations we've already registered (to avoid duplicates)
    registered_ops: Set[Tuple[str, str]] = set()  # (method, normalized_path)

    for dept_id in dept_ids:
        ops_def = get_operations(dept_id)
        if ops_def is None:
            continue

        for op in ops_def.operations:
            # Register base path
            normalized = _normalize_path_for_collision(op.path)
            op_key = (op.method.upper(), normalized)

            if op_key not in registered_ops:
                if _has_collision(app, op.method, op.path):
                    if api_mode == API_MODE_IDL:
                        raise RuntimeError(
                            f"IDL route collision detected: {op.endpoint_sig}. "
                            "Cannot start in ENGINE_API_MODE=idl with colliding routes."
                        )
                    else:
                        # both mode - skip with warning
                        logger.warning(
                            "IDL_ROUTE_COLLISION_SKIPPED",
                            extra={
                                "event": "IDL_ROUTE_COLLISION_SKIPPED",
                                "endpoint_sig": op.endpoint_sig,
                                "path": op.path,
                                "method": op.method,
                            },
                        )
                        collisions_skipped += 1
                        continue

                # Register the route
                # Pass fixed_dept_id for single-dept registry lookup (Etapa 6.6)
                handler = _create_idl_handler(op, dept_from_path=False, fixed_dept_id=dept_id)
                app.add_api_route(
                    path=op.path,
                    endpoint=handler,
                    methods=[op.method],
                    name=f"idl_{op.operation_id}",
                    tags=["idl"],
                )
                registered_ops.add(op_key)
                routes_registered += 1

                logger.info(
                    "IDL_ROUTE_REGISTERED",
                    extra={
                        "event": "IDL_ROUTE_REGISTERED",
                        "endpoint_sig": op.endpoint_sig,
                        "path": op.path,
                        "method": op.method,
                        "operation_id": op.operation_id,
                    },
                )

            # Register multi-dept variant if we have departments
            if departments:
                dept_path = f"/d/{{dept_id}}{op.path}"
                dept_normalized = _normalize_path_for_collision(dept_path)
                dept_op_key = (op.method.upper(), dept_normalized)

                if dept_op_key not in registered_ops:
                    if _has_collision(app, op.method, dept_path):
                        if api_mode == API_MODE_IDL:
                            raise RuntimeError(
                                f"IDL route collision detected: {op.method} {dept_path}. "
                                "Cannot start in ENGINE_API_MODE=idl with colliding routes."
                            )
                        else:
                            logger.warning(
                                "IDL_ROUTE_COLLISION_SKIPPED",
                                extra={
                                    "event": "IDL_ROUTE_COLLISION_SKIPPED",
                                    "endpoint_sig": f"{op.method} {dept_path}",
                                    "path": dept_path,
                                    "method": op.method,
                                },
                            )
                            collisions_skipped += 1
                            continue

                    # Register multi-dept route
                    handler = _create_idl_handler(op, dept_from_path=True)
                    app.add_api_route(
                        path=dept_path,
                        endpoint=handler,
                        methods=[op.method],
                        name=f"idl_dept_{op.operation_id}",
                        tags=["idl-dept"],
                    )
                    registered_ops.add(dept_op_key)
                    routes_registered += 1

                    logger.info(
                        "IDL_ROUTE_REGISTERED",
                        extra={
                            "event": "IDL_ROUTE_REGISTERED",
                            "endpoint_sig": f"{op.method} {dept_path}",
                            "path": dept_path,
                            "method": op.method,
                            "operation_id": op.operation_id,
                            "dept_variant": True,
                        },
                    )

    logger.info(
        "IDL_ROUTES_REGISTRATION_COMPLETE",
        extra={
            "event": "IDL_ROUTES_REGISTRATION_COMPLETE",
            "api_mode": api_mode,
            "routes_registered": routes_registered,
            "collisions_skipped": collisions_skipped,
        },
    )

    return routes_registered
