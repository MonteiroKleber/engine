"""Admin Institutions API endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from engine.ise.release import verify_admin_token
from engine.ise import errors as ise_errors
from engine.core.institutions import (
    get_registry,
    Institution,
    INSTITUTION_SLUG_INVALID,
    INSTITUTION_SLUG_TAKEN,
    INSTITUTION_NOT_FOUND,
    INSTITUTION_ID_INVALID,
    INSTITUTIONS_REGISTRY_UNAVAILABLE,
    INSTITUTION_META_UNAVAILABLE,
)


router = APIRouter(prefix="/admin", tags=["admin"])


# HTTP status code mapping for error codes
ERROR_CODE_TO_STATUS = {
    INSTITUTION_SLUG_INVALID: 400,
    INSTITUTION_SLUG_TAKEN: 409,
    INSTITUTION_NOT_FOUND: 404,
    INSTITUTION_ID_INVALID: 400,
    INSTITUTIONS_REGISTRY_UNAVAILABLE: 500,
    INSTITUTION_META_UNAVAILABLE: 500,
}


class CreateInstitutionRequest(BaseModel):
    """Request body for creating an institution."""

    slug: str = Field(..., min_length=3, max_length=63, description="Unique slug for the institution")
    display_name: Optional[str] = Field(None, description="Display name for the institution")


class InstitutionResponse(BaseModel):
    """Response body for institution data."""

    schema_version: str
    institution_id: str
    slug: str
    display_name: Optional[str]
    created_at: str


class InstitutionsListResponse(BaseModel):
    """Response body for listing institutions."""

    items: List[InstitutionResponse]
    next_cursor: Optional[str] = None


def _institution_to_response(inst: Institution) -> InstitutionResponse:
    """Convert Institution to response model."""
    return InstitutionResponse(
        schema_version="1.0",
        institution_id=inst.institution_id,
        slug=inst.slug,
        display_name=inst.display_name,
        created_at=inst.created_at,
    )


def _require_admin_token(token: Optional[str]) -> None:
    """Verify admin token, raise HTTPException if invalid."""
    if not verify_admin_token(token):
        raise HTTPException(
            status_code=401,
            detail={
                "code": ise_errors.ISE_ADMIN_UNAUTHORIZED,
                "message": "Invalid or missing admin token",
            },
        )


@router.post("/institutions", status_code=201, response_model=InstitutionResponse)
async def create_institution(
    request: CreateInstitutionRequest,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> InstitutionResponse:
    """Create a new institution.

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Args:
        request: Institution creation request with slug and optional display_name.
        x_admin_token: Admin token from header.

    Returns:
        Created institution data.

    Raises:
        HTTPException: 400 if slug invalid, 409 if slug taken, 401 if unauthorized.
    """
    _require_admin_token(x_admin_token)

    registry = get_registry()
    institution, error_code, error_message = registry.create(
        slug=request.slug,
        display_name=request.display_name,
    )

    if error_code:
        status_code = ERROR_CODE_TO_STATUS.get(error_code, 500)
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    return _institution_to_response(institution)


@router.get("/institutions/by-slug/{slug}", response_model=InstitutionResponse)
async def get_institution_by_slug(
    slug: str,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> InstitutionResponse:
    """Get institution by slug.

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Args:
        slug: Institution slug.
        x_admin_token: Admin token from header.

    Returns:
        Institution data.

    Raises:
        HTTPException: 404 if not found, 401 if unauthorized.
    """
    _require_admin_token(x_admin_token)

    registry = get_registry()
    institution, error_code, error_message = registry.get_by_slug(slug)

    if error_code:
        status_code = ERROR_CODE_TO_STATUS.get(error_code, 500)
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    return _institution_to_response(institution)


@router.get("/institutions/{institution_id}", response_model=InstitutionResponse)
async def get_institution_by_id(
    institution_id: str,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> InstitutionResponse:
    """Get institution by ID.

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Args:
        institution_id: Institution UUID.
        x_admin_token: Admin token from header.

    Returns:
        Institution data.

    Raises:
        HTTPException: 404 if not found, 400 if invalid ID, 401 if unauthorized.
    """
    _require_admin_token(x_admin_token)

    registry = get_registry()
    institution, error_code, error_message = registry.get_by_id(institution_id)

    if error_code:
        status_code = ERROR_CODE_TO_STATUS.get(error_code, 500)
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    return _institution_to_response(institution)


@router.get("/institutions", response_model=InstitutionsListResponse)
async def list_institutions(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum institutions to return"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> InstitutionsListResponse:
    """List institutions in creation order.

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Args:
        limit: Maximum number of institutions to return (1-200, default 50).
        x_admin_token: Admin token from header.

    Returns:
        List of institutions with next_cursor (always null in this phase).

    Raises:
        HTTPException: 401 if unauthorized.
    """
    _require_admin_token(x_admin_token)

    registry = get_registry()
    institutions = registry.list_institutions(limit=limit)

    return InstitutionsListResponse(
        items=[_institution_to_response(inst) for inst in institutions],
        next_cursor=None,
    )
