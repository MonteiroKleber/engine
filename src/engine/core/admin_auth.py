"""Unified admin authentication with per-institution keys and legacy fallback.

Implements:
- Per-institution admin key authentication via X-Admin-Key header
- Legacy X-Admin-Token support for DEFAULT institution only
- Ledger events for all authentication attempts
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from fastapi import HTTPException, Request

from engine.core.admin_keys import get_admin_keys_registry
from engine.core.institution_context import DEFAULT_INSTITUTION_ID
from engine.core.ledger import get_ledger_for_institution
from engine.core.errors import (
    ADMIN_KEY_REQUIRED,
    ADMIN_KEY_INVALID,
    ADMIN_KEY_REVOKED,
    ADMIN_KEY_EXPIRED,
)
from engine.ise.release import verify_admin_token as verify_legacy_token


@dataclass
class AdminAuthResult:
    """Result of admin authentication attempt."""

    valid: bool
    key_id: Optional[str] = None  # Key ID if authenticated via admin key
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    via_legacy_token: bool = False  # True if authenticated via X-Admin-Token


def verify_admin_auth(
    request: Request,
    institution_id: str,
) -> AdminAuthResult:
    """Verify admin authentication for an institution.

    Authentication methods (in priority order):
    1. X-Admin-Key header: Per-institution admin key (works for all institutions)
    2. X-Admin-Token header: Legacy token (ONLY for DEFAULT_INSTITUTION_ID)

    Args:
        request: FastAPI request object.
        institution_id: Institution UUID to authenticate against.

    Returns:
        AdminAuthResult with authentication status.
    """
    admin_key = request.headers.get("X-Admin-Key")
    admin_token = request.headers.get("X-Admin-Token")

    # Priority 1: X-Admin-Key header (per-institution key)
    if admin_key:
        return _verify_admin_key(institution_id, admin_key)

    # Priority 2: X-Admin-Token header (legacy, DEFAULT only)
    if admin_token:
        return _verify_legacy_admin_token(institution_id, admin_token)

    # No credentials provided
    return AdminAuthResult(
        valid=False,
        error_code=ADMIN_KEY_REQUIRED,
        error_message="Admin authentication required. Use X-Admin-Key header.",
    )


def _verify_admin_key(institution_id: str, admin_key: str) -> AdminAuthResult:
    """Verify per-institution admin key.

    Args:
        institution_id: Institution UUID.
        admin_key: Plaintext admin key from header.

    Returns:
        AdminAuthResult with verification status.
    """
    registry = get_admin_keys_registry()

    valid, key_id, error_code = registry.verify_key(institution_id, admin_key)

    if valid and key_id:
        # Mark key as used (for last_used_at tracking)
        registry.mark_used(institution_id, key_id)

        # Emit success event
        _emit_auth_event(
            institution_id=institution_id,
            event_type="ADMIN_KEY_USED",
            key_id=key_id,
            decision="allow",
            reason=None,
        )

        return AdminAuthResult(
            valid=True,
            key_id=key_id,
        )
    else:
        # Map error code to message
        error_messages = {
            "ADMIN_KEY_INVALID": "Invalid admin key",
            "ADMIN_KEY_REVOKED": "Admin key has been revoked",
            "ADMIN_KEY_EXPIRED": "Admin key has expired",
        }

        # Emit failure event
        _emit_auth_event(
            institution_id=institution_id,
            event_type="ADMIN_KEY_DENIED",
            key_id=key_id,
            decision="deny",
            reason=error_code,
        )

        return AdminAuthResult(
            valid=False,
            key_id=key_id,
            error_code=error_code,
            error_message=error_messages.get(error_code, "Admin key verification failed"),
        )


def _verify_legacy_admin_token(institution_id: str, admin_token: str) -> AdminAuthResult:
    """Verify legacy X-Admin-Token (DEFAULT institution only).

    Args:
        institution_id: Institution UUID.
        admin_token: Token from X-Admin-Token header.

    Returns:
        AdminAuthResult with verification status.
    """
    # Legacy token ONLY works for DEFAULT institution
    if institution_id != DEFAULT_INSTITUTION_ID:
        # Emit denial event
        _emit_auth_event(
            institution_id=institution_id,
            event_type="ADMIN_KEY_DENIED",
            key_id=None,
            decision="deny",
            reason="legacy_token_non_default",
        )

        return AdminAuthResult(
            valid=False,
            error_code=ADMIN_KEY_REQUIRED,
            error_message="X-Admin-Token is only valid for DEFAULT institution. Use X-Admin-Key for per-institution auth.",
        )

    # Verify against environment token
    if verify_legacy_token(admin_token):
        # Emit success event (no key_id for legacy auth)
        _emit_auth_event(
            institution_id=institution_id,
            event_type="ADMIN_KEY_USED",
            key_id=None,
            decision="allow",
            reason="legacy_token",
        )

        return AdminAuthResult(
            valid=True,
            via_legacy_token=True,
        )
    else:
        # Emit failure event
        _emit_auth_event(
            institution_id=institution_id,
            event_type="ADMIN_KEY_DENIED",
            key_id=None,
            decision="deny",
            reason="legacy_token_invalid",
        )

        return AdminAuthResult(
            valid=False,
            error_code=ADMIN_KEY_INVALID,
            error_message="Invalid admin token",
        )


def _emit_auth_event(
    institution_id: str,
    event_type: str,
    key_id: Optional[str],
    decision: str,
    reason: Optional[str],
) -> None:
    """Emit ledger event for authentication attempt.

    Args:
        institution_id: Institution UUID.
        event_type: ADMIN_KEY_USED or ADMIN_KEY_DENIED.
        key_id: Key ID if known.
        decision: "allow" or "deny".
        reason: Reason for the decision (for denials).
    """
    try:
        ledger = get_ledger_for_institution(institution_id)
        ledger.append(
            event_type=event_type,
            tenant_id=institution_id,
            actor_id="ADMIN",
            actor_roles=["admin"],
            case_id="",
            step=f"ADMIN:auth.{decision}",
            payload={
                "key_id": key_id,
                "decision": decision,
                "reason": reason,
            },
        )
    except Exception:
        # Don't fail auth on ledger write errors
        pass


def require_admin_auth(request: Request, institution_id: str) -> AdminAuthResult:
    """Require admin authentication, raising HTTPException on failure.

    Args:
        request: FastAPI request object.
        institution_id: Institution UUID to authenticate against.

    Returns:
        AdminAuthResult if authentication succeeds.

    Raises:
        HTTPException: 401 on authentication failure.
    """
    result = verify_admin_auth(request, institution_id)

    if not result.valid:
        raise HTTPException(
            status_code=401,
            detail={
                "code": result.error_code,
                "message": result.error_message,
            },
        )

    return result


def require_admin_auth_for_default(request: Request) -> AdminAuthResult:
    """Require admin authentication for DEFAULT institution.

    This is a convenience function for endpoints that don't have
    institution context (e.g., listing all institutions).

    Args:
        request: FastAPI request object.

    Returns:
        AdminAuthResult if authentication succeeds.

    Raises:
        HTTPException: 401 on authentication failure.
    """
    return require_admin_auth(request, DEFAULT_INSTITUTION_ID)
