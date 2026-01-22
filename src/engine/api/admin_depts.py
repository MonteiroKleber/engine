"""Admin Depts API - Per-institution department activation management.

Implements Etapa 5.1 - Multi-Dept Activation Model.

Endpoints:
- GET /admin/institutions/{id}/depts - List installed, active, inactive depts
- POST /admin/institutions/{id}/depts/{dept_id}/activate - Activate a dept
- POST /admin/institutions/{id}/depts/{dept_id}/deactivate - Deactivate a dept
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.core.admin_auth import require_admin_auth
from engine.core.active_depts import (
    get_depts_summary,
    activate_dept,
    deactivate_dept,
    get_active_depts_state,
    invalidate_active_depts_cache,
)
from engine.core.errors import (
    DEPT_NOT_INSTALLED,
    DEPT_NOT_ACTIVE,
    DEPT_ALREADY_ACTIVE,
    DEPT_ALREADY_INACTIVE,
    CANNOT_DEACTIVATE_LAST_DEPT,
    ACTIVE_DEPTS_UNAVAILABLE,
)


router = APIRouter(prefix="/admin/institutions", tags=["admin-depts"])


class DeptsSummaryResponse(BaseModel):
    """Response body for listing departments."""

    installed: List[str] = Field(..., description="Departments available in the bundle")
    active: List[str] = Field(..., description="Departments currently active")
    inactive: List[str] = Field(..., description="Departments installed but not active")


class DeptActivateRequest(BaseModel):
    """Request body for activating a department."""

    pinned_contract_sha256: Optional[str] = Field(
        None,
        description="Optional SHA256 hash of contract to pin",
    )


class DeptDeactivateRequest(BaseModel):
    """Request body for deactivating a department."""

    reason: Optional[str] = Field(
        None,
        description="Optional reason for deactivation",
    )


class DeptActionResponse(BaseModel):
    """Response body for dept activation/deactivation."""

    dept_id: str = Field(..., description="Department ID")
    action: str = Field(..., description="Action performed: activated or deactivated")
    success: bool = Field(..., description="Whether action succeeded")


# Map error codes to HTTP status codes
ERROR_TO_HTTP = {
    DEPT_NOT_INSTALLED: 400,
    DEPT_NOT_ACTIVE: 404,
    DEPT_ALREADY_ACTIVE: 409,
    DEPT_ALREADY_INACTIVE: 409,
    CANNOT_DEACTIVATE_LAST_DEPT: 400,
    ACTIVE_DEPTS_UNAVAILABLE: 503,
}


@router.get(
    "/{institution_id}/depts",
    response_model=DeptsSummaryResponse,
    summary="List departments",
    description="List installed, active, and inactive departments for an institution.",
)
async def list_depts(
    institution_id: str,
    actor_id: str = require_admin_auth,
) -> DeptsSummaryResponse:
    """List departments for an institution.

    Returns:
    - installed: All departments available in the bundle
    - active: Departments that are currently active and accepting requests
    - inactive: Departments that are installed but not active

    If no active_depts.json exists, all installed depts are considered active.
    """
    summary = get_depts_summary(institution_id)
    return DeptsSummaryResponse(
        installed=summary["installed"],
        active=summary["active"],
        inactive=summary["inactive"],
    )


@router.post(
    "/{institution_id}/depts/{dept_id}/activate",
    response_model=DeptActionResponse,
    summary="Activate department",
    description="Activate a department for the institution. Emits DEPT_ACTIVATED event.",
)
async def activate_dept_endpoint(
    institution_id: str,
    dept_id: str,
    request: Optional[DeptActivateRequest] = None,
    actor_id: str = require_admin_auth,
) -> DeptActionResponse:
    """Activate a department.

    The department must be installed in the bundle but not yet active.
    On first activation, creates active_depts.json with all installed depts.
    """
    pin = request.pinned_contract_sha256 if request else None

    success, error_code, error_msg = activate_dept(
        institution_id=institution_id,
        dept_id=dept_id,
        actor_id=actor_id,
        pinned_contract_sha256=pin,
    )

    if not success:
        status_code = ERROR_TO_HTTP.get(error_code, 500)
        raise HTTPException(
            status_code=status_code,
            detail={"code": error_code, "message": error_msg},
        )

    # Invalidate cache
    invalidate_active_depts_cache(institution_id)

    return DeptActionResponse(
        dept_id=dept_id,
        action="activated",
        success=True,
    )


@router.post(
    "/{institution_id}/depts/{dept_id}/deactivate",
    response_model=DeptActionResponse,
    summary="Deactivate department",
    description="Deactivate a department for the institution. Emits DEPT_DEACTIVATED event.",
)
async def deactivate_dept_endpoint(
    institution_id: str,
    dept_id: str,
    request: Optional[DeptDeactivateRequest] = None,
    actor_id: str = require_admin_auth,
) -> DeptActionResponse:
    """Deactivate a department.

    The department must be currently active.
    Cannot deactivate the last active department.
    """
    reason = request.reason if request else None

    success, error_code, error_msg = deactivate_dept(
        institution_id=institution_id,
        dept_id=dept_id,
        actor_id=actor_id,
        reason=reason,
    )

    if not success:
        status_code = ERROR_TO_HTTP.get(error_code, 500)
        raise HTTPException(
            status_code=status_code,
            detail={"code": error_code, "message": error_msg},
        )

    # Invalidate cache
    invalidate_active_depts_cache(institution_id)

    return DeptActionResponse(
        dept_id=dept_id,
        action="deactivated",
        success=True,
    )
