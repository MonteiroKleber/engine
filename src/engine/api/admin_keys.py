"""Admin Keys API - Per-institution admin key management."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from engine.core.admin_keys import get_admin_keys_registry, AdminKeyState
from engine.core.admin_auth import require_admin_auth
from engine.core.ledger import get_ledger_for_institution
from engine.core.errors import (
    ADMIN_KEY_NOT_FOUND,
    ADMIN_KEY_ALREADY_REVOKED,
    ADMIN_KEYS_REGISTRY_UNAVAILABLE,
)


router = APIRouter(prefix="/admin/institutions", tags=["admin-keys"])


class CreateAdminKeyRequest(BaseModel):
    """Request body for creating an admin key."""

    expires_at: Optional[str] = Field(
        None,
        description="Optional ISO 8601 timestamp for key expiry. If not set, key never expires.",
    )


class CreateAdminKeyResponse(BaseModel):
    """Response body for created admin key.

    IMPORTANT: The plaintext_secret is only returned at creation time.
    It is not stored and cannot be retrieved later.
    """

    key_id: str = Field(..., description="UUID of the created key")
    plaintext_secret: str = Field(
        ...,
        description="The plaintext secret. Store this securely - it cannot be retrieved later.",
    )
    expires_at: Optional[str] = Field(None, description="ISO 8601 expiry timestamp if set")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class AdminKeyInfo(BaseModel):
    """Admin key information (without secret)."""

    key_id: str = Field(..., description="UUID of the key")
    status: str = Field(..., description="Key status: active, revoked, or expired")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    expires_at: Optional[str] = Field(None, description="ISO 8601 expiry timestamp if set")
    last_used_at: Optional[str] = Field(None, description="ISO 8601 timestamp of last use")


class AdminKeysListResponse(BaseModel):
    """Response body for listing admin keys."""

    items: List[AdminKeyInfo] = Field(..., description="List of admin keys")


class RevokeAdminKeyResponse(BaseModel):
    """Response body for revoking an admin key."""

    key_id: str = Field(..., description="UUID of the revoked key")
    status: str = Field(..., description="New status: revoked")
    revoked_at: str = Field(..., description="ISO 8601 timestamp of revocation")


def _key_state_to_info(state: AdminKeyState) -> AdminKeyInfo:
    """Convert AdminKeyState to AdminKeyInfo response model."""
    return AdminKeyInfo(
        key_id=state.key_id,
        status=state.status,
        created_at=state.created_at,
        expires_at=state.expires_at,
        last_used_at=state.last_used_at,
    )


def _emit_key_event(
    institution_id: str,
    event_type: str,
    key_id: str,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit ledger event for key operation.

    Args:
        institution_id: Institution UUID.
        event_type: ADMIN_KEY_CREATED or ADMIN_KEY_REVOKED.
        key_id: Key UUID.
        extra_payload: Additional payload fields.
    """
    try:
        ledger = get_ledger_for_institution(institution_id)
        payload = {"key_id": key_id}
        if extra_payload:
            payload.update(extra_payload)

        ledger.append(
            event_type=event_type,
            tenant_id=institution_id,
            actor_id="ADMIN",
            actor_roles=["admin"],
            case_id="",
            step=f"ADMIN:key.{event_type.lower().replace('admin_key_', '')}",
            payload=payload,
        )
    except Exception:
        # Don't fail operation on ledger write errors
        pass


@router.post(
    "/{institution_id}/admin-keys",
    status_code=201,
    response_model=CreateAdminKeyResponse,
)
async def create_admin_key(
    institution_id: str,
    request: Request,
    body: CreateAdminKeyRequest,
) -> CreateAdminKeyResponse:
    """Create a new admin key for an institution.

    Requires admin authentication (X-Admin-Key or X-Admin-Token for DEFAULT).

    The plaintext_secret in the response is the ONLY time the secret is available.
    It is not stored and cannot be retrieved later. Store it securely.

    Args:
        institution_id: Institution UUID.
        request: FastAPI request (for auth headers).
        body: Request body with optional expires_at.

    Returns:
        Created key info including the plaintext secret.

    Raises:
        HTTPException: 401 if unauthorized, 500 if registry unavailable.
    """
    # Authenticate admin
    require_admin_auth(request, institution_id)

    try:
        registry = get_admin_keys_registry()
        key_id, plaintext_secret = registry.create_key(
            institution_id=institution_id,
            expires_at=body.expires_at,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": ADMIN_KEYS_REGISTRY_UNAVAILABLE,
                "message": f"Failed to create admin key: {e}",
            },
        )

    # Get created timestamp from registry
    states = registry.load_current_state(institution_id)
    created_at = states[key_id].created_at if key_id in states else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Emit ledger event
    _emit_key_event(
        institution_id=institution_id,
        event_type="ADMIN_KEY_CREATED",
        key_id=key_id,
        extra_payload={"expires_at": body.expires_at},
    )

    return CreateAdminKeyResponse(
        key_id=key_id,
        plaintext_secret=plaintext_secret,
        expires_at=body.expires_at,
        created_at=created_at,
    )


@router.get(
    "/{institution_id}/admin-keys",
    response_model=AdminKeysListResponse,
)
async def list_admin_keys(
    institution_id: str,
    request: Request,
) -> AdminKeysListResponse:
    """List all admin keys for an institution.

    Requires admin authentication (X-Admin-Key or X-Admin-Token for DEFAULT).

    Returns all keys including revoked and expired ones.
    Keys are returned in no particular order.

    Args:
        institution_id: Institution UUID.
        request: FastAPI request (for auth headers).

    Returns:
        List of admin keys with their current status.

    Raises:
        HTTPException: 401 if unauthorized, 500 if registry unavailable.
    """
    # Authenticate admin
    require_admin_auth(request, institution_id)

    try:
        registry = get_admin_keys_registry()
        keys = registry.list_keys(institution_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": ADMIN_KEYS_REGISTRY_UNAVAILABLE,
                "message": f"Failed to list admin keys: {e}",
            },
        )

    return AdminKeysListResponse(
        items=[_key_state_to_info(key) for key in keys],
    )


@router.post(
    "/{institution_id}/admin-keys/{key_id}/revoke",
    response_model=RevokeAdminKeyResponse,
)
async def revoke_admin_key(
    institution_id: str,
    key_id: str,
    request: Request,
) -> RevokeAdminKeyResponse:
    """Revoke an admin key.

    Requires admin authentication (X-Admin-Key or X-Admin-Token for DEFAULT).

    Revoked keys cannot be used for authentication and cannot be un-revoked.

    Args:
        institution_id: Institution UUID.
        key_id: Key UUID to revoke.
        request: FastAPI request (for auth headers).

    Returns:
        Revocation confirmation.

    Raises:
        HTTPException: 401 if unauthorized, 404 if key not found,
                      409 if key already revoked, 500 if registry unavailable.
    """
    # Authenticate admin
    require_admin_auth(request, institution_id)

    try:
        registry = get_admin_keys_registry()
        success, error_code = registry.revoke_key(institution_id, key_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": ADMIN_KEYS_REGISTRY_UNAVAILABLE,
                "message": f"Failed to revoke admin key: {e}",
            },
        )

    if not success:
        if error_code == "ADMIN_KEY_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail={
                    "code": ADMIN_KEY_NOT_FOUND,
                    "message": f"Admin key '{key_id}' not found",
                },
            )
        elif error_code == "ADMIN_KEY_ALREADY_REVOKED":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": ADMIN_KEY_ALREADY_REVOKED,
                    "message": f"Admin key '{key_id}' is already revoked",
                },
            )
        else:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": ADMIN_KEYS_REGISTRY_UNAVAILABLE,
                    "message": f"Failed to revoke admin key: {error_code}",
                },
            )

    revoked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Emit ledger event
    _emit_key_event(
        institution_id=institution_id,
        event_type="ADMIN_KEY_REVOKED",
        key_id=key_id,
        extra_payload={"revoked_at": revoked_at},
    )

    return RevokeAdminKeyResponse(
        key_id=key_id,
        status="revoked",
        revoked_at=revoked_at,
    )
