"""Admin endpoints for actor token management.

Provides endpoints to:
- Create actor tokens (provisioning)
- Revoke actor tokens
- List actor tokens

Uses existing admin authentication (X-Admin-Key or X-Admin-Token).

GAP 2: Minimum Identity Not Spoofable
"""

from dataclasses import asdict
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from engine.core.actor_tokens import get_actor_tokens_registry, ActorTokenState
from engine.core.admin_auth import verify_admin_auth, require_admin_auth
from engine.core.institution_context import resolve_institution_id
from engine.core.ledger import get_ledger_for_institution
from engine.core.errors import (
    ACTOR_TOKEN_NOT_FOUND,
    ACTOR_TOKEN_REVOKED,
    ACTOR_TOKENS_REGISTRY_UNAVAILABLE,
)


router = APIRouter(prefix="/admin/institutions", tags=["admin-actors"])


# Request/Response models
class CreateActorTokenRequest(BaseModel):
    """Request to create an actor token."""

    actor_id: str = Field(..., description="UUID of the actor")
    roles: List[str] = Field(default_factory=list, description="Roles to assign")


class CreateActorTokenResponse(BaseModel):
    """Response with created actor token."""

    token: str = Field(..., description="Plaintext token (only shown once)")
    actor_id: str = Field(..., description="Actor UUID")
    roles: List[str] = Field(..., description="Assigned roles")
    message: str = Field(default="Token created successfully. Store it securely.")


class ActorTokenInfo(BaseModel):
    """Information about an actor token (without the plaintext token)."""

    token_sha256: str = Field(..., description="SHA256 hash of the token")
    actor_id: str = Field(..., description="Actor UUID")
    roles: List[str] = Field(..., description="Assigned roles")
    status: str = Field(..., description="active or revoked")
    created_at: str = Field(..., description="ISO 8601 timestamp")
    created_by: Optional[str] = Field(None, description="Admin key ID that created")


class ListActorsResponse(BaseModel):
    """Response with list of actor tokens."""

    actors: List[ActorTokenInfo] = Field(..., description="List of actor tokens")
    count: int = Field(..., description="Total count")


class RevokeActorTokenRequest(BaseModel):
    """Request to revoke an actor token."""

    token_sha256: str = Field(..., description="SHA256 hash of token to revoke")


class RevokeActorTokenResponse(BaseModel):
    """Response for token revocation."""

    success: bool
    message: str


def _emit_actor_event(
    institution_id: str,
    event_type: str,
    actor_id: str,
    token_sha256: str,
    admin_key_id: Optional[str],
    roles: Optional[List[str]] = None,
    decision: str = "allow",
    reason: Optional[str] = None,
) -> None:
    """Emit ledger event for actor token operations."""
    try:
        ledger = get_ledger_for_institution(institution_id)

        payload = {
            "decision": decision,
            "institution_id": institution_id,
            "target_actor_id": actor_id,
            "token_sha256": token_sha256,
            "admin_key_id": admin_key_id,
        }
        if roles is not None:
            payload["roles"] = roles
        if reason:
            payload["reason"] = reason

        step_map = {
            "ACTOR_TOKEN_CREATED": "ADMIN:actor.create",
            "ACTOR_TOKEN_REVOKED": "ADMIN:actor.revoke",
            "ACTOR_TOKEN_CREATE_FAILED": "ADMIN:actor.create.fail",
            "ACTOR_TOKEN_REVOKE_FAILED": "ADMIN:actor.revoke.fail",
        }
        step = step_map.get(event_type, "ADMIN:actor.unknown")

        ledger.append(
            event_type=event_type,
            tenant_id=institution_id,
            actor_id=admin_key_id or "system",
            actor_roles=["admin"],
            case_id=None,
            step=step,
            payload=payload,
        )
    except Exception:
        pass  # Don't fail request if ledger fails


@router.post("/{institution_id}/actors", response_model=CreateActorTokenResponse)
async def create_actor_token(
    institution_id: str,
    body: CreateActorTokenRequest,
    request: Request,
):
    """Create a new actor token for an institution.

    Requires admin authentication (X-Admin-Key or X-Admin-Token).

    Args:
        institution_id: Institution UUID.
        body: Request with actor_id and roles.
        request: FastAPI request object.

    Returns:
        CreateActorTokenResponse with the plaintext token (only shown once).
    """
    # Verify admin auth
    auth_result = require_admin_auth(request, institution_id)

    # Create token
    registry = get_actor_tokens_registry()
    plaintext_token, error_code = registry.create_token(
        institution_id=institution_id,
        actor_id=body.actor_id,
        roles=body.roles,
        created_by=auth_result.key_id,
    )

    if error_code:
        _emit_actor_event(
            institution_id=institution_id,
            event_type="ACTOR_TOKEN_CREATE_FAILED",
            actor_id=body.actor_id,
            token_sha256="",
            admin_key_id=auth_result.key_id,
            roles=body.roles,
            decision="deny",
            reason=error_code,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": error_code,
                "message": "Failed to create actor token",
            },
        )

    # Compute hash for event (token was just created)
    from engine.core.actor_tokens import _hash_token
    token_sha256 = _hash_token(plaintext_token)

    # Emit success event
    _emit_actor_event(
        institution_id=institution_id,
        event_type="ACTOR_TOKEN_CREATED",
        actor_id=body.actor_id,
        token_sha256=token_sha256,
        admin_key_id=auth_result.key_id,
        roles=body.roles,
    )

    return CreateActorTokenResponse(
        token=plaintext_token,
        actor_id=body.actor_id,
        roles=body.roles,
    )


@router.get("/{institution_id}/actors", response_model=ListActorsResponse)
async def list_actors(
    institution_id: str,
    request: Request,
):
    """List all actor tokens for an institution.

    Requires admin authentication (X-Admin-Key or X-Admin-Token).

    Args:
        institution_id: Institution UUID.
        request: FastAPI request object.

    Returns:
        ListActorsResponse with list of actor tokens.
    """
    # Verify admin auth
    require_admin_auth(request, institution_id)

    # Get actors
    registry = get_actor_tokens_registry()
    actors = registry.list_actors(institution_id)

    actor_infos = [
        ActorTokenInfo(
            token_sha256=a.token_sha256,
            actor_id=a.actor_id,
            roles=a.roles,
            status=a.status,
            created_at=a.created_at,
            created_by=a.created_by,
        )
        for a in actors
    ]

    return ListActorsResponse(
        actors=actor_infos,
        count=len(actor_infos),
    )


@router.post("/{institution_id}/actors/revoke", response_model=RevokeActorTokenResponse)
async def revoke_actor_token(
    institution_id: str,
    body: RevokeActorTokenRequest,
    request: Request,
):
    """Revoke an actor token.

    Requires admin authentication (X-Admin-Key or X-Admin-Token).

    Args:
        institution_id: Institution UUID.
        body: Request with token_sha256 to revoke.
        request: FastAPI request object.

    Returns:
        RevokeActorTokenResponse with success status.
    """
    # Verify admin auth
    auth_result = require_admin_auth(request, institution_id)

    # Revoke token
    registry = get_actor_tokens_registry()
    success, error_code = registry.revoke_token(
        institution_id=institution_id,
        token_sha256=body.token_sha256,
        revoked_by=auth_result.key_id,
    )

    if not success:
        _emit_actor_event(
            institution_id=institution_id,
            event_type="ACTOR_TOKEN_REVOKE_FAILED",
            actor_id="",
            token_sha256=body.token_sha256,
            admin_key_id=auth_result.key_id,
            decision="deny",
            reason=error_code,
        )

        error_messages = {
            ACTOR_TOKEN_NOT_FOUND: "Token not found",
            ACTOR_TOKEN_REVOKED: "Token already revoked",
            ACTOR_TOKENS_REGISTRY_UNAVAILABLE: "Registry unavailable",
        }

        raise HTTPException(
            status_code=404 if error_code == ACTOR_TOKEN_NOT_FOUND else 400,
            detail={
                "code": error_code,
                "message": error_messages.get(error_code, "Failed to revoke token"),
            },
        )

    # Emit success event
    _emit_actor_event(
        institution_id=institution_id,
        event_type="ACTOR_TOKEN_REVOKED",
        actor_id="",
        token_sha256=body.token_sha256,
        admin_key_id=auth_result.key_id,
    )

    return RevokeActorTokenResponse(
        success=True,
        message="Token revoked successfully",
    )


@router.get("/{institution_id}/actors/{actor_id}", response_model=ListActorsResponse)
async def get_actor_tokens(
    institution_id: str,
    actor_id: str,
    request: Request,
):
    """Get all tokens for a specific actor.

    Requires admin authentication (X-Admin-Key or X-Admin-Token).

    Args:
        institution_id: Institution UUID.
        actor_id: Actor UUID.
        request: FastAPI request object.

    Returns:
        ListActorsResponse with list of tokens for this actor.
    """
    # Verify admin auth
    require_admin_auth(request, institution_id)

    # Get actors
    registry = get_actor_tokens_registry()
    actors = registry.get_actor_by_id(institution_id, actor_id)

    actor_infos = [
        ActorTokenInfo(
            token_sha256=a.token_sha256,
            actor_id=a.actor_id,
            roles=a.roles,
            status=a.status,
            created_at=a.created_at,
            created_by=a.created_by,
        )
        for a in actors
    ]

    return ListActorsResponse(
        actors=actor_infos,
        count=len(actor_infos),
    )
