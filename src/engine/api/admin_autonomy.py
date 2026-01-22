"""Admin Governed Autonomy API endpoints.

Provides endpoints for managing governed autonomy via EGE-style proposals:
- Create autonomy proposals (update_level/create_rule/update_rule/revoke_rule)
- Decide on proposals (approve/reject)
- List proposals and autonomy state

Etapa 4.4: Policies + Autonomy Governance UI
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from engine.core.admin_auth import require_admin_auth
from engine.core.governed_autonomy import (
    propose_autonomy_change,
    decide_autonomy_proposal,
    list_autonomy_proposals,
    list_governed_autonomy,
    get_effective_autonomy,
    get_autonomy_proposal,
    AutonomyProposalState,
)
from engine.core.autonomy import get_autonomy_for_dept as get_bundle_autonomy
from engine.core.errors import (
    AUTONOMY_PROPOSAL_NOT_FOUND,
    AUTONOMY_PROPOSAL_ALREADY_DECIDED,
    AUTONOMY_PROPOSAL_INVALID,
    AUTONOMY_NOT_FOUND_FOR_UPDATE,
    GOVERNED_AUTONOMY_UNAVAILABLE,
    INSTITUTION_HEADER_REQUIRED,
)


router = APIRouter(prefix="/admin/autonomy", tags=["admin-autonomy"])


# HTTP status code mapping for error codes
ERROR_CODE_TO_STATUS = {
    AUTONOMY_PROPOSAL_NOT_FOUND: 404,
    AUTONOMY_PROPOSAL_ALREADY_DECIDED: 409,
    AUTONOMY_PROPOSAL_INVALID: 400,
    AUTONOMY_NOT_FOUND_FOR_UPDATE: 404,
    GOVERNED_AUTONOMY_UNAVAILABLE: 500,
    INSTITUTION_HEADER_REQUIRED: 400,
}


class AutonomyProposalRequest(BaseModel):
    """Request body for creating an autonomy proposal."""

    operation: str = Field(..., description="update_level, create_rule, update_rule, or revoke_rule")
    rule_id: Optional[str] = Field(None, description="Target rule ID (required for rule operations)")
    autonomy_data: Dict[str, Any] = Field(..., description="Autonomy data (current_level or rule data)")
    reason: str = Field(..., description="Reason for the proposal")
    dept_id: Optional[str] = Field(None, description="Department ID (None for single-mode)")


class AutonomyProposalResponse(BaseModel):
    """Response body for an autonomy proposal."""

    proposal_id: str
    status: str = Field(..., description="OPEN or DECIDED")
    created_at: str
    autonomy_operation: str
    dept_id: Optional[str]
    rule_id: Optional[str]
    autonomy_data: Optional[Dict[str, Any]]
    reason: str
    created_by: str
    decision: Optional[str] = Field(None, description="approve or reject")
    decision_reason: Optional[str]
    decided_at: Optional[str]
    decided_by: Optional[str]


class ProposalsListResponse(BaseModel):
    """Response body for proposals list."""

    items: List[AutonomyProposalResponse]


class DecideProposalRequest(BaseModel):
    """Request body for deciding a proposal."""

    decision: str = Field(..., description="approve or reject")
    reason: Optional[str] = None


class GovernedAutonomyResponse(BaseModel):
    """Response body for governed autonomy."""

    current_level: Optional[int]
    rules: Dict[str, Dict[str, Any]]


class EffectiveAutonomyResponse(BaseModel):
    """Response body for effective autonomy."""

    current_level: int
    rules: List[Dict[str, Any]]
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


def _proposal_to_response(proposal: AutonomyProposalState) -> AutonomyProposalResponse:
    """Convert AutonomyProposalState to response model."""
    return AutonomyProposalResponse(
        proposal_id=proposal.proposal_id,
        status=proposal.status,
        created_at=proposal.created_at,
        autonomy_operation=proposal.autonomy_operation,
        dept_id=proposal.dept_id,
        rule_id=proposal.rule_id,
        autonomy_data=proposal.autonomy_data,
        reason=proposal.reason,
        created_by=proposal.created_by,
        decision=proposal.decision,
        decision_reason=proposal.decision_reason,
        decided_at=proposal.decided_at,
        decided_by=proposal.decided_by,
    )


@router.post("/proposals", status_code=201, response_model=AutonomyProposalResponse)
async def create_autonomy_proposal_endpoint(
    body: AutonomyProposalRequest,
    request: Request,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
) -> AutonomyProposalResponse:
    """Create an autonomy change proposal.

    Creates a proposal to update the autonomy level or manage rules.
    The proposal must be approved before it takes effect.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        body: Proposal details.

    Returns:
        Created proposal.

    Raises:
        HTTPException: 400 if invalid.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    actor_id = x_actor_id or "admin"

    proposal, error_code, error_message = propose_autonomy_change(
        institution_id=institution_id,
        operation=body.operation,
        rule_id=body.rule_id,
        autonomy_data=body.autonomy_data,
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
    """List autonomy proposals for an institution.

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

    proposals = list_autonomy_proposals(
        institution_id=institution_id,
        dept_id=dept_id,
        status_filter=status,
        limit=limit,
    )

    return ProposalsListResponse(
        items=[_proposal_to_response(p) for p in proposals],
    )


@router.get("/proposals/{proposal_id}", response_model=AutonomyProposalResponse)
async def get_proposal_endpoint(
    proposal_id: str,
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> AutonomyProposalResponse:
    """Get a specific autonomy proposal.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        proposal_id: Proposal UUID.
        dept_id: Department ID (must match proposal's dept_id).

    Returns:
        Proposal details.

    Raises:
        HTTPException: 404 if not found.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    proposal = get_autonomy_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        dept_id=dept_id,
    )

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail={
                "code": AUTONOMY_PROPOSAL_NOT_FOUND,
                "message": f"Proposal '{proposal_id}' not found",
            },
        )

    return _proposal_to_response(proposal)


@router.post("/proposals/{proposal_id}/decide", response_model=AutonomyProposalResponse)
async def decide_proposal_endpoint(
    proposal_id: str,
    body: DecideProposalRequest,
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
) -> AutonomyProposalResponse:
    """Decide on an autonomy proposal.

    If decision is "approve":
    - Applies the autonomy change immediately
    - Emits AUTONOMY_GOV_APPROVED and AUTONOMY_GOV_APPLIED/REVOKED events

    If decision is "reject":
    - No changes are made
    - Emits AUTONOMY_GOV_REJECTED event

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

    proposal, error_code, error_message = decide_autonomy_proposal(
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


@router.get("/governed", response_model=GovernedAutonomyResponse)
async def list_governed_autonomy_endpoint(
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> GovernedAutonomyResponse:
    """List current governed autonomy.

    Returns only autonomy settings that have been created/updated via the governance
    workflow (not bundle autonomy).

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        dept_id: Department ID (None for single-mode).

    Returns:
        Current governed autonomy state.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    state = list_governed_autonomy(
        institution_id=institution_id,
        dept_id=dept_id,
    )

    return GovernedAutonomyResponse(
        current_level=state.current_level,
        rules=state.rules,
    )


@router.get("/effective", response_model=EffectiveAutonomyResponse)
async def list_effective_autonomy_endpoint(
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> EffectiveAutonomyResponse:
    """List effective autonomy (governed + bundle).

    Returns the merged view of autonomy that will be used at runtime:
    - Governed current_level overrides bundle current_level
    - Governed rules override bundle rules by rule_id
    - Revoked rules are excluded

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        dept_id: Department ID (None for single-mode).

    Returns:
        Effective autonomy and source.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    effective_def = get_effective_autonomy(
        institution_id=institution_id,
        dept_id=dept_id,
    )

    if effective_def is None:
        return EffectiveAutonomyResponse(
            current_level=4,  # Default allow-all
            rules=[],
            source="none",
        )

    # Convert rules to dicts
    rules_list = []
    for rule in effective_def.rules:
        rule_dict = {
            "rule_id": rule.rule_id,
            "endpoint_sig": rule.endpoint_sig,
            "phase": rule.phase,
            "required_level": rule.required_level,
        }
        rules_list.append(rule_dict)

    # Determine source
    governed = list_governed_autonomy(institution_id, dept_id)
    bundle_def = get_bundle_autonomy(dept_id)

    has_governed = governed.current_level is not None or governed.rules

    if has_governed and bundle_def:
        source = "merged"
    elif has_governed:
        source = "governed"
    elif bundle_def:
        source = "bundle"
    else:
        source = "none"

    return EffectiveAutonomyResponse(
        current_level=effective_def.current_level,
        rules=rules_list,
        source=source,
    )
