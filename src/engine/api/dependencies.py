"""FastAPI dependencies for actor context and RBAC."""

from typing import Callable, Optional

from fastapi import Header, HTTPException, Request

from engine.core.runtime_state import runtime_state, RuntimeMode
from engine.core.actor_context import ActorContext, parse_actor_context
from engine.core.rbac import gate_rbac


async def get_actor_context(
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
    x_actor_roles: Optional[str] = Header(None, alias="X-Actor-Roles"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
) -> ActorContext:
    """Dependency to extract and validate actor context from headers.

    Raises:
        HTTPException: 401 if actor is missing or invalid.
        HTTPException: 503 if runtime is in SAFE_MODE.
    """
    # Check runtime mode first
    if runtime_state.mode == RuntimeMode.SAFE_MODE:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SAFE_MODE",
                "message": "Service is in safe mode",
            },
        )

    context, error_code, error_message = parse_actor_context(
        x_actor_id, x_actor_roles, x_tenant_id
    )

    if context is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    return context


def require_permission(permission: str, dept_id: Optional[str] = None) -> Callable[[ActorContext], ActorContext]:
    """Create a dependency that checks for a specific permission.

    Args:
        permission: Permission required for the endpoint.
        dept_id: Optional department ID for per-dept RBAC lookup.

    Returns:
        Dependency function that validates the permission.
    """

    def check_permission(actor: ActorContext) -> ActorContext:
        if not gate_rbac(permission, actor, dept_id=dept_id):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "RBAC_FORBIDDEN",
                    "message": "Forbidden",
                },
            )
        return actor

    return check_permission
