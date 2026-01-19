"""Admin Governed Mandates API endpoints.

Provides endpoints for managing governed mandates via EGE-style proposals:
- Create mandate proposals (create/update/revoke)
- Decide on proposals (approve/reject)
- List proposals and mandates

Etapa 2.8: AXIOM MVP
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from engine.core.admin_auth import require_admin_auth
from engine.core.governed_mandates import (
    propose_mandate_change,
    decide_mandate_proposal,
    list_mandate_proposals,
    list_governed_mandates,
    get_effective_mandates,
    MandateProposalState,
)
from engine.core.errors import (
    MANDATE_PROPOSAL_NOT_FOUND,
    MANDATE_PROPOSAL_ALREADY_DECIDED,
    MANDATE_PROPOSAL_INVALID,
    MANDATE_NOT_FOUND_FOR_UPDATE,
    MANDATE_ALREADY_EXISTS,
    GOVERNED_MANDATES_UNAVAILABLE,
    INSTITUTION_HEADER_REQUIRED,
)


router = APIRouter(prefix="/admin/mandates", tags=["admin-mandates"])


# HTTP status code mapping for error codes
ERROR_CODE_TO_STATUS = {
    MANDATE_PROPOSAL_NOT_FOUND: 404,
    MANDATE_PROPOSAL_ALREADY_DECIDED: 409,
    MANDATE_PROPOSAL_INVALID: 400,
    MANDATE_NOT_FOUND_FOR_UPDATE: 404,
    MANDATE_ALREADY_EXISTS: 409,
    GOVERNED_MANDATES_UNAVAILABLE: 500,
    INSTITUTION_HEADER_REQUIRED: 400,
}


class MandateProposalRequest(BaseModel):
    """Request body for creating a mandate proposal."""

    operation: str = Field(..., description="create, update, or revoke")
    mandate_id: str = Field(..., description="Target mandate ID")
    mandate_data: Optional[Dict[str, Any]] = Field(
        None, description="Full mandate data (required for create/update)"
    )
    reason: str = Field(..., description="Reason for the proposal")
    dept_id: Optional[str] = Field(None, description="Department ID (None for single-mode)")


class MandateProposalResponse(BaseModel):
    """Response body for a mandate proposal."""

    proposal_id: str
    status: str = Field(..., description="OPEN or DECIDED")
    created_at: str
    mandate_operation: str
    dept_id: Optional[str]
    mandate_id: str
    mandate_data: Optional[Dict[str, Any]]
    reason: str
    created_by: str
    decision: Optional[str] = Field(None, description="approve or reject")
    decision_reason: Optional[str]
    decided_at: Optional[str]
    decided_by: Optional[str]


class ProposalsListResponse(BaseModel):
    """Response body for proposals list."""

    items: List[MandateProposalResponse]


class DecideProposalRequest(BaseModel):
    """Request body for deciding a proposal."""

    decision: str = Field(..., description="approve or reject")
    reason: Optional[str] = None


class GovernedMandatesResponse(BaseModel):
    """Response body for governed mandates."""

    mandates: Dict[str, Dict[str, Any]]


class EffectiveMandatesResponse(BaseModel):
    """Response body for effective mandates."""

    mandates: List[Dict[str, Any]]
    source: str = Field(..., description="governed, bundle, or merged")


def _require_institution_header(institution_id: Optional[str]) -> str:
    """Require X-Institution-Id header.

    Args:
        institution_id: Institution ID from header.

    Returns:
        Validated institution ID.

    Raises:
        HTTPException: 400 if missing.
    """
    if not institution_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": INSTITUTION_HEADER_REQUIRED,
                "message": "X-Institution-Id header is required",
            },
        )
    return institution_id


def _proposal_to_response(proposal: MandateProposalState) -> MandateProposalResponse:
    """Convert MandateProposalState to response model."""
    return MandateProposalResponse(
        proposal_id=proposal.proposal_id,
        status=proposal.status,
        created_at=proposal.created_at,
        mandate_operation=proposal.mandate_operation,
        dept_id=proposal.dept_id,
        mandate_id=proposal.mandate_id,
        mandate_data=proposal.mandate_data,
        reason=proposal.reason,
        created_by=proposal.created_by,
        decision=proposal.decision,
        decision_reason=proposal.decision_reason,
        decided_at=proposal.decided_at,
        decided_by=proposal.decided_by,
    )


@router.post("/proposals", status_code=201, response_model=MandateProposalResponse)
async def create_mandate_proposal_endpoint(
    body: MandateProposalRequest,
    request: Request,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
) -> MandateProposalResponse:
    """Create a mandate change proposal.

    Creates a proposal to create, update, or revoke a mandate.
    The proposal must be approved before it takes effect.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        body: Proposal details.

    Returns:
        Created proposal.

    Raises:
        HTTPException: 400 if invalid, 409 if mandate already exists (for create).
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    actor_id = x_actor_id or "admin"

    proposal, error_code, error_message = propose_mandate_change(
        institution_id=institution_id,
        operation=body.operation,
        mandate_id=body.mandate_id,
        mandate_data=body.mandate_data,
        reason=body.reason,
        actor_id=actor_id,
        dept_id=body.dept_id,
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

    return _proposal_to_response(proposal)


@router.get("/proposals", response_model=ProposalsListResponse)
async def list_proposals_endpoint(
    request: Request,
    status: Optional[str] = None,
    dept_id: Optional[str] = None,
    limit: int = 50,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> ProposalsListResponse:
    """List mandate proposals for an institution.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        status: Filter by status (OPEN or DECIDED).
        dept_id: Filter by department ID.
        limit: Maximum number of proposals to return (default 50).

    Returns:
        List of proposals (most recent first).
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    proposals = list_mandate_proposals(
        institution_id=institution_id,
        dept_id=dept_id,
        status_filter=status,
        limit=limit,
    )

    return ProposalsListResponse(
        items=[_proposal_to_response(p) for p in proposals],
    )


@router.post("/proposals/{proposal_id}/decide", response_model=MandateProposalResponse)
async def decide_proposal_endpoint(
    proposal_id: str,
    body: DecideProposalRequest,
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
) -> MandateProposalResponse:
    """Decide on a mandate proposal.

    If decision is "approve":
    - Applies the mandate change immediately
    - Emits MANDATE_APPROVED and MANDATE_APPLIED/MANDATE_REVOKED events

    If decision is "reject":
    - No changes are made
    - Emits MANDATE_REJECTED event

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        proposal_id: Proposal UUID to decide.
        body: Decision details.
        dept_id: Department ID (must match proposal's dept_id).

    Returns:
        Updated proposal.

    Raises:
        HTTPException: 404 if not found, 409 if already decided, 400 if invalid.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    actor_id = x_actor_id or "admin"

    proposal, error_code, error_message = decide_mandate_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        decision=body.decision,
        reason=body.reason,
        actor_id=actor_id,
        dept_id=dept_id,
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

    return _proposal_to_response(proposal)


@router.get("/governed", response_model=GovernedMandatesResponse)
async def list_governed_mandates_endpoint(
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> GovernedMandatesResponse:
    """List current governed mandates.

    Returns only mandates that have been created/updated via the governance
    workflow (not bundle mandates).

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        dept_id: Department ID (None for single-mode).

    Returns:
        Dictionary of mandate_id -> mandate_data.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    mandates = list_governed_mandates(
        institution_id=institution_id,
        dept_id=dept_id,
    )

    return GovernedMandatesResponse(mandates=mandates)


@router.get("/effective", response_model=EffectiveMandatesResponse)
async def list_effective_mandates_endpoint(
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> EffectiveMandatesResponse:
    """List effective mandates (governed + bundle).

    Returns the merged view of mandates that will be used at runtime:
    - Governed mandates override bundle mandates by mandate_id
    - Revoked mandates are excluded

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        dept_id: Department ID (None for single-mode).

    Returns:
        List of effective mandates and their source.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    effective_def = get_effective_mandates(
        institution_id=institution_id,
        dept_id=dept_id,
    )

    if effective_def is None:
        return EffectiveMandatesResponse(mandates=[], source="none")

    # Convert mandates to dicts
    mandates_list = []
    for mandate in effective_def.mandates:
        mandate_dict = {
            "mandate_id": mandate.mandate_id,
            "endpoint_sig": mandate.endpoint_sig,
            "phase": mandate.phase,
            "allowed_roles": mandate.allowed_roles,
            "valid_from": mandate.valid_from.isoformat() if mandate.valid_from else None,
            "valid_until": mandate.valid_until.isoformat() if mandate.valid_until else None,
            "limits": [
                {
                    "rule_type": limit.rule_type,
                    "field_path": limit.field_path,
                    "value": limit.value,
                    "message": limit.message,
                }
                for limit in mandate.limits
            ],
            "message": mandate.message,
        }
        mandates_list.append(mandate_dict)

    # Determine source
    governed = list_governed_mandates(institution_id, dept_id)
    from engine.core.mandates import get_mandates as get_bundle_mandates
    bundle_def = get_bundle_mandates(dept_id)

    if governed and bundle_def:
        source = "merged"
    elif governed:
        source = "governed"
    elif bundle_def:
        source = "bundle"
    else:
        source = "none"

    return EffectiveMandatesResponse(mandates=mandates_list, source=source)
