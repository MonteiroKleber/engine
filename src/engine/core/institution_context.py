"""Institution context resolution from request headers."""

import uuid
from typing import Optional

from fastapi import HTTPException, Request

from engine.core.errors import (
    INSTITUTION_HEADER_REQUIRED,
    INSTITUTION_HEADER_CONFLICT,
    INSTITUTION_HEADER_INVALID,
    INSTITUTION_NOT_FOUND,
    INSTITUTION_CONTEXT_UNAVAILABLE,
)
from engine.core.institutions import get_registry


# Default institution ID (for backward compatibility)
DEFAULT_INSTITUTION_ID = "00000000-0000-0000-0000-000000000000"


def _is_valid_uuid(value: str) -> bool:
    """Check if string is a valid UUID."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def resolve_institution_id(request: Request, require_header: bool = False) -> str:
    """Resolve institution ID from request headers.

    Reads headers:
    - X-Institution-Id (canonical)
    - X-Tenant-Id (legacy alias)

    Rules:
    - If both present and differ -> HTTPException 409 INSTITUTION_HEADER_CONFLICT
    - If any present but invalid UUID -> HTTPException 400 INSTITUTION_HEADER_INVALID
    - If none present:
      - if require_header True -> HTTPException 400 INSTITUTION_HEADER_REQUIRED
      - else -> return DEFAULT_INSTITUTION_ID

    Args:
        request: FastAPI request object.
        require_header: If True, require header to be present.

    Returns:
        Institution ID string.

    Raises:
        HTTPException: On validation errors.
    """
    institution_id_header = request.headers.get("X-Institution-Id")
    tenant_id_header = request.headers.get("X-Tenant-Id")

    # Validate UUID format if present
    if institution_id_header is not None and not _is_valid_uuid(institution_id_header):
        raise HTTPException(
            status_code=400,
            detail={
                "code": INSTITUTION_HEADER_INVALID,
                "message": "Invalid X-Institution-Id header format",
            },
        )

    if tenant_id_header is not None and not _is_valid_uuid(tenant_id_header):
        raise HTTPException(
            status_code=400,
            detail={
                "code": INSTITUTION_HEADER_INVALID,
                "message": "Invalid X-Tenant-Id header format",
            },
        )

    # Check for conflict
    if institution_id_header is not None and tenant_id_header is not None:
        if institution_id_header != tenant_id_header:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": INSTITUTION_HEADER_CONFLICT,
                    "message": "X-Institution-Id and X-Tenant-Id headers conflict",
                },
            )

    # Determine institution_id
    institution_id = institution_id_header or tenant_id_header

    if institution_id is None:
        if require_header:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": INSTITUTION_HEADER_REQUIRED,
                    "message": "X-Institution-Id header is required",
                },
            )
        return DEFAULT_INSTITUTION_ID

    return institution_id


def validate_institution_exists(institution_id: str) -> None:
    """Validate that institution exists in registry.

    Args:
        institution_id: Institution UUID to validate.

    Raises:
        HTTPException: 404 if not found, 500 if registry unavailable.
    """
    # Default institution is always valid (backward compatibility)
    if institution_id == DEFAULT_INSTITUTION_ID:
        return

    try:
        registry = get_registry()
        institution, error_code, error_message = registry.get_by_id(institution_id)

        if error_code == INSTITUTION_NOT_FOUND:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": INSTITUTION_NOT_FOUND,
                    "message": f"Institution '{institution_id}' not found",
                },
            )
        elif error_code is not None:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": INSTITUTION_CONTEXT_UNAVAILABLE,
                    "message": "Failed to validate institution",
                },
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={
                "code": INSTITUTION_CONTEXT_UNAVAILABLE,
                "message": "Institution registry unavailable",
            },
        )


def set_request_institution_id(request: Request, institution_id: str) -> None:
    """Set institution ID on request state.

    Args:
        request: FastAPI request object.
        institution_id: Institution ID to set.
    """
    request.state.institution_id = institution_id


def get_request_institution_id(request: Request) -> Optional[str]:
    """Get institution ID from request state.

    Args:
        request: FastAPI request object.

    Returns:
        Institution ID if set, None otherwise.
    """
    return getattr(request.state, "institution_id", None)
