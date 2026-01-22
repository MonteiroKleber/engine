"""Admin Governed Policies API endpoints.

Provides endpoints for managing governed policies via EGE-style proposals:
- Create policy proposals (create/update/revoke)
- Decide on proposals (approve/reject)
- List proposals and policies

Etapa 4.4: Policies + Autonomy Governance UI
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from engine.core.admin_auth import require_admin_auth
from engine.core.governed_policies import (
    propose_policy_change,
    decide_policy_proposal,
    list_policy_proposals,
    list_governed_policies,
    get_effective_policies,
    get_policy_proposal,
    PolicyProposalState,
)
from engine.core.policy import get_policies as get_bundle_policies
from engine.core.errors import (
    POLICY_PROPOSAL_NOT_FOUND,
    POLICY_PROPOSAL_ALREADY_DECIDED,
    POLICY_PROPOSAL_INVALID,
    POLICY_NOT_FOUND_FOR_UPDATE,
    POLICY_ALREADY_EXISTS,
    GOVERNED_POLICIES_UNAVAILABLE,
    INSTITUTION_HEADER_REQUIRED,
)


router = APIRouter(prefix="/admin/policies", tags=["admin-policies"])


# HTTP status code mapping for error codes
ERROR_CODE_TO_STATUS = {
    POLICY_PROPOSAL_NOT_FOUND: 404,
    POLICY_PROPOSAL_ALREADY_DECIDED: 409,
    POLICY_PROPOSAL_INVALID: 400,
    POLICY_NOT_FOUND_FOR_UPDATE: 404,
    POLICY_ALREADY_EXISTS: 409,
    GOVERNED_POLICIES_UNAVAILABLE: 500,
    INSTITUTION_HEADER_REQUIRED: 400,
}


class PolicyProposalRequest(BaseModel):
    """Request body for creating a policy proposal."""

    operation: str = Field(..., description="create, update, or revoke")
    policy_id: str = Field(..., description="Target policy ID")
    policy_data: Optional[Dict[str, Any]] = Field(
        None, description="Full policy data (required for create/update)"
    )
    reason: str = Field(..., description="Reason for the proposal")
    dept_id: Optional[str] = Field(None, description="Department ID (None for single-mode)")


class PolicyProposalResponse(BaseModel):
    """Response body for a policy proposal."""

    proposal_id: str
    status: str = Field(..., description="OPEN or DECIDED")
    created_at: str
    policy_operation: str
    dept_id: Optional[str]
    policy_id: str
    policy_data: Optional[Dict[str, Any]]
    reason: str
    created_by: str
    decision: Optional[str] = Field(None, description="approve or reject")
    decision_reason: Optional[str]
    decided_at: Optional[str]
    decided_by: Optional[str]


class ProposalsListResponse(BaseModel):
    """Response body for proposals list."""

    items: List[PolicyProposalResponse]


class DecideProposalRequest(BaseModel):
    """Request body for deciding a proposal."""

    decision: str = Field(..., description="approve or reject")
    reason: Optional[str] = None


class GovernedPoliciesResponse(BaseModel):
    """Response body for governed policies."""

    policies: Dict[str, Dict[str, Any]]


class EffectivePoliciesResponse(BaseModel):
    """Response body for effective policies."""

    policies: List[Dict[str, Any]]
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


def _proposal_to_response(proposal: PolicyProposalState) -> PolicyProposalResponse:
    """Convert PolicyProposalState to response model."""
    return PolicyProposalResponse(
        proposal_id=proposal.proposal_id,
        status=proposal.status,
        created_at=proposal.created_at,
        policy_operation=proposal.policy_operation,
        dept_id=proposal.dept_id,
        policy_id=proposal.policy_id,
        policy_data=proposal.policy_data,
        reason=proposal.reason,
        created_by=proposal.created_by,
        decision=proposal.decision,
        decision_reason=proposal.decision_reason,
        decided_at=proposal.decided_at,
        decided_by=proposal.decided_by,
    )


@router.post("/proposals", status_code=201, response_model=PolicyProposalResponse)
async def create_policy_proposal_endpoint(
    body: PolicyProposalRequest,
    request: Request,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
) -> PolicyProposalResponse:
    """Create a policy change proposal.

    Creates a proposal to create, update, or revoke a policy.
    The proposal must be approved before it takes effect.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        body: Proposal details.

    Returns:
        Created proposal.

    Raises:
        HTTPException: 400 if invalid, 409 if policy already exists (for create).
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    actor_id = x_actor_id or "admin"

    proposal, error_code, error_message = propose_policy_change(
        institution_id=institution_id,
        operation=body.operation,
        policy_id=body.policy_id,
        policy_data=body.policy_data,
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
    """List policy proposals for an institution.

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

    proposals = list_policy_proposals(
        institution_id=institution_id,
        dept_id=dept_id,
        status_filter=status,
        limit=limit,
    )

    return ProposalsListResponse(
        items=[_proposal_to_response(p) for p in proposals],
    )


@router.get("/proposals/{proposal_id}", response_model=PolicyProposalResponse)
async def get_proposal_endpoint(
    proposal_id: str,
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> PolicyProposalResponse:
    """Get a specific policy proposal.

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

    proposal = get_policy_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        dept_id=dept_id,
    )

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail={
                "code": POLICY_PROPOSAL_NOT_FOUND,
                "message": f"Proposal '{proposal_id}' not found",
            },
        )

    return _proposal_to_response(proposal)


@router.post("/proposals/{proposal_id}/decide", response_model=PolicyProposalResponse)
async def decide_proposal_endpoint(
    proposal_id: str,
    body: DecideProposalRequest,
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
) -> PolicyProposalResponse:
    """Decide on a policy proposal.

    If decision is "approve":
    - Applies the policy change immediately
    - Emits POLICY_APPROVED and POLICY_APPLIED/POLICY_REVOKED events

    If decision is "reject":
    - No changes are made
    - Emits POLICY_REJECTED event

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

    proposal, error_code, error_message = decide_policy_proposal(
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


@router.get("/governed", response_model=GovernedPoliciesResponse)
async def list_governed_policies_endpoint(
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> GovernedPoliciesResponse:
    """List current governed policies.

    Returns only policies that have been created/updated via the governance
    workflow (not bundle policies).

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        dept_id: Department ID (None for single-mode).

    Returns:
        Dictionary of policy_id -> policy_data.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    policies = list_governed_policies(
        institution_id=institution_id,
        dept_id=dept_id,
    )

    return GovernedPoliciesResponse(policies=policies)


@router.get("/effective", response_model=EffectivePoliciesResponse)
async def list_effective_policies_endpoint(
    request: Request,
    dept_id: Optional[str] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> EffectivePoliciesResponse:
    """List effective policies (governed + bundle).

    Returns the merged view of policies that will be used at runtime:
    - Governed policies override bundle policies by policy_id
    - Revoked policies are excluded

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        dept_id: Department ID (None for single-mode).

    Returns:
        List of effective policies and their source.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    effective_def = get_effective_policies(
        institution_id=institution_id,
        dept_id=dept_id,
    )

    if effective_def is None:
        return EffectivePoliciesResponse(policies=[], source="none")

    # Convert policies to dicts
    policies_list = []
    for policy in effective_def.policies:
        policy_dict = {
            "policy_id": policy.policy_id,
            "rule_type": policy.rule_type,
            "field_path": policy.field_path,
            "phase": policy.phase,
            "endpoint_sig": policy.endpoint_sig,
            "value": policy.value,
            "message": policy.message,
        }
        policies_list.append(policy_dict)

    # Determine source
    governed = list_governed_policies(institution_id, dept_id)
    bundle_def = get_bundle_policies(dept_id)

    if governed and bundle_def:
        source = "merged"
    elif governed:
        source = "governed"
    elif bundle_def:
        source = "bundle"
    else:
        source = "none"

    return EffectivePoliciesResponse(policies=policies_list, source=source)
