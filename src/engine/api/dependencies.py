"""FastAPI dependencies for actor context and RBAC.

Supports two authentication modes via ENGINE_AUTH_MODE:
- dev: Accept X-Actor-Id and X-Actor-Roles headers (legacy)
- strict: Require X-Actor-Token, resolve actor/roles from registry

GAP 4: Adds X-On-Behalf-Of header support for agent delegation.
"""

from typing import Callable, Optional

from fastapi import Header, HTTPException, Request

from engine.core.runtime_state import runtime_state, RuntimeMode
from engine.core.actor_context import (
    ActorContext,
    parse_actor_context,
    get_auth_mode,
    AuthMode,
    DEFAULT_TENANT_ID,
    is_valid_uuid,
)
from engine.core.rbac import gate_rbac
from engine.core.errors import (
    ACTOR_TOKEN_REQUIRED,
    ACTOR_TOKEN_INVALID,
    ACTOR_TOKEN_REVOKED,
    UNVERIFIED_IDENTITY_USED,
    ON_BEHALF_OF_NOT_AGENT,
    ON_BEHALF_OF_INVALID,
)


def _emit_unverified_identity_event(
    actor_id: str,
    roles: list,
    tenant_id: str,
    institution_id: Optional[str],
) -> None:
    """Emit UNVERIFIED_IDENTITY_USED event in dev mode."""
    try:
        from engine.core.ledger import get_ledger, get_ledger_for_institution

        if institution_id:
            ledger = get_ledger_for_institution(institution_id)
        else:
            ledger = get_ledger()

        if ledger:
            ledger.append(
                event_type="UNVERIFIED_IDENTITY_USED",
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_roles=roles,
                case_id=None,
                step="AUTH:identity.unverified",
                payload={
                    "decision": "allow",
                    "auth_mode": "dev",
                    "source": "headers",
                    "warning": "Identity not verified - using header values",
                },
            )
    except Exception:
        pass  # Don't fail request if ledger fails


async def get_actor_context(
    request: Request,
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
    x_actor_roles: Optional[str] = Header(None, alias="X-Actor-Roles"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
    x_actor_token: Optional[str] = Header(None, alias="X-Actor-Token"),
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_on_behalf_of: Optional[str] = Header(None, alias="X-On-Behalf-Of"),
) -> ActorContext:
    """Dependency to extract and validate actor context.

    In dev mode (ENGINE_AUTH_MODE=dev):
        - Accepts X-Actor-Id and X-Actor-Roles headers (legacy behavior)
        - Emits UNVERIFIED_IDENTITY_USED event to ledger
        - identity_verified = False

    In strict mode (ENGINE_AUTH_MODE=strict):
        - Requires X-Actor-Token header
        - Resolves actor_id and roles from token registry
        - Ignores X-Actor-Id and X-Actor-Roles headers
        - identity_verified = True

    GAP 4 - X-On-Behalf-Of delegation:
        - Only accepted if actor is_agent=True (from registry)
        - In strict mode: actor must be verified agent
        - In dev mode: allowed but logged as unverified
        - Does NOT change permissions (gates use actor, not delegatee)

    Raises:
        HTTPException: 401 if actor is missing, invalid, or token verification fails.
        HTTPException: 403 if on_behalf_of used by non-agent.
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

    auth_mode = get_auth_mode()

    # Resolve institution_id for token verification
    institution_id = x_institution_id or x_tenant_id

    if auth_mode == AuthMode.STRICT:
        # STRICT MODE: Require token, resolve from registry
        context = await _resolve_actor_from_token(
            x_actor_token=x_actor_token,
            x_tenant_id=x_tenant_id,
            institution_id=institution_id,
        )
    else:
        # DEV MODE: Accept headers (legacy), emit warning event
        context = await _resolve_actor_from_headers(
            x_actor_id=x_actor_id,
            x_actor_roles=x_actor_roles,
            x_tenant_id=x_tenant_id,
            institution_id=institution_id,
        )

    # GAP 4: Handle on_behalf_of delegation
    if x_on_behalf_of:
        context = _validate_on_behalf_of(
            context=context,
            on_behalf_of=x_on_behalf_of,
            auth_mode=auth_mode,
            institution_id=institution_id,
        )

    return context


def _validate_on_behalf_of(
    context: ActorContext,
    on_behalf_of: str,
    auth_mode: AuthMode,
    institution_id: Optional[str],
) -> ActorContext:
    """Validate and apply on_behalf_of delegation.

    GAP 4: on_behalf_of is only allowed for agents.
    In strict mode: agent status from registry is authoritative.
    In dev mode: allow but log as unverified delegation.

    Args:
        context: The actor context to update.
        on_behalf_of: UUID of the actor being delegated for.
        auth_mode: Current authentication mode.
        institution_id: Institution ID for logging.

    Returns:
        Updated ActorContext with on_behalf_of set.

    Raises:
        HTTPException: 403 if actor is not an agent.
        HTTPException: 400 if on_behalf_of is not a valid UUID.
    """
    # Validate on_behalf_of is a valid UUID
    if not is_valid_uuid(on_behalf_of):
        raise HTTPException(
            status_code=400,
            detail={
                "code": ON_BEHALF_OF_INVALID,
                "message": "on_behalf_of must be a valid UUID",
            },
        )

    # In strict mode, only verified agents can delegate
    if auth_mode == AuthMode.STRICT:
        if not context.is_agent:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": ON_BEHALF_OF_NOT_AGENT,
                    "message": "Only agents can use on_behalf_of delegation",
                },
            )
    else:
        # In dev mode, allow but emit warning
        # Check if actor has 'agent' role as a hint (not authoritative)
        if not context.is_agent and "agent" not in context.roles:
            # Allow anyway in dev mode, but log
            _emit_unverified_delegation_event(
                agent_id=context.actor_id,
                on_behalf_of=on_behalf_of,
                tenant_id=context.tenant_id,
                institution_id=institution_id,
            )
        # In dev mode, allow delegation even without is_agent
        # but mark as unverified agent
        if "agent" in context.roles:
            context.is_agent = True

    # Set the delegation
    context.on_behalf_of = on_behalf_of
    return context


def _emit_unverified_delegation_event(
    agent_id: str,
    on_behalf_of: str,
    tenant_id: str,
    institution_id: Optional[str],
) -> None:
    """Emit UNVERIFIED_DELEGATION_USED event in dev mode."""
    try:
        from engine.core.ledger import get_ledger, get_ledger_for_institution

        if institution_id:
            ledger = get_ledger_for_institution(institution_id)
        else:
            ledger = get_ledger()

        if ledger:
            ledger.append(
                event_type="UNVERIFIED_DELEGATION_USED",
                tenant_id=tenant_id,
                actor_id=agent_id,
                actor_roles=[],
                case_id=None,
                step="AUTH:delegation.unverified",
                payload={
                    "decision": "allow",
                    "auth_mode": "dev",
                    "on_behalf_of": on_behalf_of,
                    "warning": "Delegation not verified - actor not registered as agent",
                },
            )
    except Exception:
        pass  # Don't fail request if ledger fails


async def _resolve_actor_from_token(
    x_actor_token: Optional[str],
    x_tenant_id: Optional[str],
    institution_id: Optional[str],
) -> ActorContext:
    """Resolve actor context from token (strict mode).

    Args:
        x_actor_token: Token from X-Actor-Token header.
        x_tenant_id: Tenant ID from X-Tenant-Id header.
        institution_id: Institution ID for token registry lookup.

    Returns:
        ActorContext with identity_verified=True.

    Raises:
        HTTPException: 401 if token is missing, invalid, or revoked.
    """
    # Token is required in strict mode
    if not x_actor_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": ACTOR_TOKEN_REQUIRED,
                "message": "Actor token required in strict mode. Use X-Actor-Token header.",
            },
        )

    # Institution ID is required for token lookup
    if not institution_id:
        raise HTTPException(
            status_code=401,
            detail={
                "code": ACTOR_TOKEN_REQUIRED,
                "message": "Institution ID required for token verification. Use X-Institution-Id header.",
            },
        )

    # Verify token against registry
    from engine.core.actor_tokens import get_actor_tokens_registry

    registry = get_actor_tokens_registry()
    actor_id, roles, valid, error_code, is_agent = registry.verify_token(
        institution_id=institution_id,
        plaintext_token=x_actor_token,
    )

    if not valid:
        error_messages = {
            ACTOR_TOKEN_INVALID: "Invalid actor token",
            ACTOR_TOKEN_REVOKED: "Actor token has been revoked",
        }
        raise HTTPException(
            status_code=401,
            detail={
                "code": error_code,
                "message": error_messages.get(error_code, "Token verification failed"),
            },
        )

    # Validate tenant_id if provided
    if x_tenant_id:
        if not is_valid_uuid(x_tenant_id):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "TENANT_INVALID",
                    "message": "Tenant is invalid",
                },
            )
        tenant_id = x_tenant_id
    else:
        tenant_id = DEFAULT_TENANT_ID

    return ActorContext(
        actor_id=actor_id,
        roles=roles or [],
        tenant_id=tenant_id,
        identity_verified=True,
        is_agent=is_agent,  # GAP 4: from registry
    )


async def _resolve_actor_from_headers(
    x_actor_id: Optional[str],
    x_actor_roles: Optional[str],
    x_tenant_id: Optional[str],
    institution_id: Optional[str],
) -> ActorContext:
    """Resolve actor context from headers (dev mode).

    Args:
        x_actor_id: Actor ID from X-Actor-Id header.
        x_actor_roles: Roles from X-Actor-Roles header.
        x_tenant_id: Tenant ID from X-Tenant-Id header.
        institution_id: Institution ID for ledger event.

    Returns:
        ActorContext with identity_verified=False.

    Raises:
        HTTPException: 401 if actor is missing or invalid.
    """
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

    # Mark as unverified
    context.identity_verified = False

    # Emit warning event (async, don't block)
    _emit_unverified_identity_event(
        actor_id=context.actor_id,
        roles=context.roles,
        tenant_id=context.tenant_id,
        institution_id=institution_id,
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
