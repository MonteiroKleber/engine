"""Admin EGE (Engine Governance Enforcement) API endpoints."""

from typing import Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from engine.core.admin_auth import require_admin_auth
from engine.core.ege import (
    check_drift,
    save_drift_state,
    load_drift_state,
    emit_ege_drift_checked,
    DriftState,
)
from engine.core.ege_proposals import (
    create_drift_resolution_proposal,
    decide_proposal,
    list_proposals,
    ProposalState,
)
from engine.core.ege_pins import (
    get_pin_status,
    create_pin_update_proposal,
    accept_pin_update_proposal,
    block_pin_update_proposal,
    PROPOSAL_TYPE_PIN_UPDATE,
)
from engine.core.errors import (
    EGE_STATE_UNAVAILABLE,
    EGE_NO_DRIFT_ACTIVE,
    EGE_PROPOSAL_NOT_FOUND,
    EGE_PROPOSAL_ALREADY_DECIDED,
    EGE_DECISION_INVALID,
    EGE_REGISTRY_UNAVAILABLE,
    EGE_PIN_PROPOSAL_NOT_FOUND,
    EGE_PIN_PROPOSAL_WRONG_TYPE,
    EGE_PIN_ALREADY_MATCHED,
    EGE_PIN_CONFIG_UNAVAILABLE,
    EGE_PIN_OBSERVED_UNAVAILABLE,
    INSTITUTION_HEADER_REQUIRED,
)


router = APIRouter(prefix="/admin/ege", tags=["admin-ege"])


# HTTP status code mapping for error codes
ERROR_CODE_TO_STATUS = {
    EGE_STATE_UNAVAILABLE: 500,
    EGE_REGISTRY_UNAVAILABLE: 500,
    EGE_NO_DRIFT_ACTIVE: 409,
    EGE_PROPOSAL_NOT_FOUND: 404,
    EGE_PROPOSAL_ALREADY_DECIDED: 409,
    EGE_DECISION_INVALID: 400,
    INSTITUTION_HEADER_REQUIRED: 400,
    # Pin proposal errors (8.1.1)
    EGE_PIN_PROPOSAL_NOT_FOUND: 404,
    EGE_PIN_PROPOSAL_WRONG_TYPE: 400,
    EGE_PIN_ALREADY_MATCHED: 409,
    EGE_PIN_CONFIG_UNAVAILABLE: 500,
    EGE_PIN_OBSERVED_UNAVAILABLE: 500,
}


class DriftStateResponse(BaseModel):
    """Response body for drift state."""

    schema_version: str
    status: str = Field(..., description="CLEAR, ACTIVE, or UNPINNED")
    checked_at: Optional[str]
    expected_bundle_manifest_sha256: Optional[str]
    expected_contract_ledger_sha256: Optional[str]
    observed_bundle_manifest_sha256: Optional[str]
    observed_contract_ledger_sha256: Optional[str]
    bundle_manifest_mismatch: bool
    contract_ledger_mismatch: bool


class DriftCheckResponse(BaseModel):
    """Response body for drift check."""

    status: str = Field(..., description="CLEAR, ACTIVE, or UNPINNED")
    state: DriftStateResponse


class ProposalResponse(BaseModel):
    """Response body for a proposal."""

    proposal_id: str
    status: str = Field(..., description="OPEN or DECIDED")
    created_at: str
    expected_bundle_manifest_sha256: Optional[str]
    expected_contract_ledger_sha256: Optional[str]
    observed_bundle_manifest_sha256: Optional[str]
    observed_contract_ledger_sha256: Optional[str]
    decision: Optional[str] = Field(None, description="accept or block")
    reason: Optional[str]
    decided_at: Optional[str]
    decider_actor_id: Optional[str]


class ProposalsListResponse(BaseModel):
    """Response body for proposals list."""

    items: List[ProposalResponse]


class DecideProposalRequest(BaseModel):
    """Request body for deciding a proposal."""

    decision: str = Field(..., description="accept or block")
    reason: Optional[str] = None


class PinProposeRequest(BaseModel):
    """Request body for creating a pin update proposal."""

    release_id: str = Field(..., description="Release ID")
    bundle_name: str = Field(..., description="Bundle name")


class PinStatusResponse(BaseModel):
    """Response body for pin status."""

    pinned: Dict[str, Optional[str]] = Field(
        ..., description="Pinned hashes from config"
    )
    observed: Dict[str, Optional[str]] = Field(
        ..., description="Observed hashes from current bundle"
    )
    drift_status: str = Field(
        ..., description="CLEAR, ACTIVE, or UNPINNED"
    )


class PinProposalResponse(BaseModel):
    """Response body for pin proposal operations."""

    proposal_id: str
    status: str = Field(..., description="OPEN or DECIDED")
    decision: Optional[str] = Field(None, description="accept or block")
    reason: Optional[str] = None


class BlockPinProposalRequest(BaseModel):
    """Request body for blocking a pin proposal."""

    reason: Optional[str] = None


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


def _drift_state_to_response(state: DriftState) -> DriftStateResponse:
    """Convert DriftState to response model."""
    return DriftStateResponse(
        schema_version=state.schema_version,
        status=state.status,
        checked_at=state.checked_at,
        expected_bundle_manifest_sha256=state.expected_bundle_manifest_sha256,
        expected_contract_ledger_sha256=state.expected_contract_ledger_sha256,
        observed_bundle_manifest_sha256=state.observed_bundle_manifest_sha256,
        observed_contract_ledger_sha256=state.observed_contract_ledger_sha256,
        bundle_manifest_mismatch=state.bundle_manifest_mismatch,
        contract_ledger_mismatch=state.contract_ledger_mismatch,
    )


def _proposal_to_response(proposal: ProposalState) -> ProposalResponse:
    """Convert ProposalState to response model."""
    return ProposalResponse(
        proposal_id=proposal.proposal_id,
        status=proposal.status,
        created_at=proposal.created_at,
        expected_bundle_manifest_sha256=proposal.expected_bundle_manifest_sha256,
        expected_contract_ledger_sha256=proposal.expected_contract_ledger_sha256,
        observed_bundle_manifest_sha256=proposal.observed_bundle_manifest_sha256,
        observed_contract_ledger_sha256=proposal.observed_contract_ledger_sha256,
        decision=proposal.decision,
        reason=proposal.reason,
        decided_at=proposal.decided_at,
        decider_actor_id=proposal.decider_actor_id,
    )


@router.post("/drift/check", response_model=DriftCheckResponse)
async def check_drift_endpoint(
    request: Request,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> DriftCheckResponse:
    """Check drift status for an institution.

    Computes hash comparison between pinned config and CURRENT bundle.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Returns:
        Drift check result with status (CLEAR, ACTIVE, or UNPINNED).
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    try:
        # Check drift
        state = check_drift(institution_id)

        # Save drift state
        save_drift_state(institution_id, state)

        # Emit ledger event
        emit_ege_drift_checked(institution_id, state)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": EGE_STATE_UNAVAILABLE,
                "message": f"Failed to check drift: {e}",
            },
        )

    return DriftCheckResponse(
        status=state.status,
        state=_drift_state_to_response(state),
    )


@router.post("/proposals", status_code=201, response_model=ProposalResponse)
async def create_proposal_endpoint(
    request: Request,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> ProposalResponse:
    """Create a drift resolution proposal.

    Loads current drift state (computes if missing) and creates a proposal
    if drift status is ACTIVE.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Returns:
        Created proposal.

    Raises:
        HTTPException: 409 if no active drift.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    # Load or compute drift state
    drift_state = load_drift_state(institution_id)
    if drift_state is None:
        drift_state = check_drift(institution_id)
        save_drift_state(institution_id, drift_state)
        emit_ege_drift_checked(institution_id, drift_state)

    # Create proposal
    proposal, error_code, error_message = create_drift_resolution_proposal(
        institution_id=institution_id,
        drift_state=drift_state,
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
    limit: int = 50,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> ProposalsListResponse:
    """List proposals for an institution.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        limit: Maximum number of proposals to return (default 50).

    Returns:
        List of proposals (most recent first).
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    proposals = list_proposals(institution_id, limit=limit)

    return ProposalsListResponse(
        items=[_proposal_to_response(p) for p in proposals],
    )


@router.post("/proposals/{proposal_id}/decide", response_model=ProposalResponse)
async def decide_proposal_endpoint(
    proposal_id: str,
    body: DecideProposalRequest,
    request: Request,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
) -> ProposalResponse:
    """Decide on a proposal.

    If decision is "accept":
    - Updates institution config with observed hashes (pins to current bundle)
    - Saves drift state as CLEAR

    If decision is "block":
    - Leaves drift state as ACTIVE (no changes)

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        proposal_id: Proposal UUID to decide.
        body: Decision details.

    Returns:
        Updated proposal.

    Raises:
        HTTPException: 404 if proposal not found, 409 if already decided, 400 if invalid decision.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    # Actor ID for audit trail
    actor_id = x_actor_id or "admin"

    # Decide proposal
    proposal, error_code, error_message = decide_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        decision=body.decision,
        reason=body.reason,
        decider_actor_id=actor_id,
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


# =============================================================================
# Pin Management Endpoints (8.1.1)
# =============================================================================


@router.get("/pins/status", response_model=PinStatusResponse)
async def get_pins_status_endpoint(
    request: Request,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> PinStatusResponse:
    """Get current pin status for an institution.

    Returns pinned hashes from config, observed hashes from current bundle,
    and drift status.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Returns:
        Pin status with pinned, observed, and drift_status.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    pin_status, error_code, error_message = get_pin_status(institution_id)

    if error_code:
        status_code = ERROR_CODE_TO_STATUS.get(error_code, 500)
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": error_code,
                "message": error_message,
            },
        )

    return PinStatusResponse(
        pinned=pin_status.pinned,
        observed=pin_status.observed,
        drift_status=pin_status.drift_status,
    )


@router.post("/pins/propose", status_code=201, response_model=PinProposalResponse)
async def create_pin_proposal_endpoint(
    body: PinProposeRequest,
    request: Request,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-Id"),
) -> PinProposalResponse:
    """Create a pin update proposal.

    Creates a proposal to update pinned hashes to match current observed hashes.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        body: Release ID and bundle name.

    Returns:
        Created proposal.

    Raises:
        HTTPException: 409 if already matched, 500 if config/observed unavailable.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    actor_id = x_actor_id or "admin"
    request_id = x_request_id

    proposal_id, error_code, error_message = create_pin_update_proposal(
        institution_id=institution_id,
        release_id=body.release_id,
        bundle_name=body.bundle_name,
        actor_id=actor_id,
        request_id=request_id,
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

    return PinProposalResponse(
        proposal_id=proposal_id,
        status="OPEN",
        decision=None,
        reason=None,
    )


@router.post(
    "/pins/proposals/{proposal_id}/accept",
    response_model=PinProposalResponse,
)
async def accept_pin_proposal_endpoint(
    proposal_id: str,
    request: Request,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-Id"),
) -> PinProposalResponse:
    """Accept a pin update proposal.

    Updates institution config with observed hashes from the proposal.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        proposal_id: Proposal UUID to accept.

    Returns:
        Updated proposal.

    Raises:
        HTTPException: 404 if proposal not found, 400 if wrong type, 409 if already decided.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    actor_id = x_actor_id or "admin"
    request_id = x_request_id

    success, error_code, error_message = accept_pin_update_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        actor_id=actor_id,
        request_id=request_id,
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

    return PinProposalResponse(
        proposal_id=proposal_id,
        status="DECIDED",
        decision="accept",
        reason=None,
    )


@router.post(
    "/pins/proposals/{proposal_id}/block",
    response_model=PinProposalResponse,
)
async def block_pin_proposal_endpoint(
    proposal_id: str,
    request: Request,
    body: Optional[BlockPinProposalRequest] = None,
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-Id"),
) -> PinProposalResponse:
    """Block a pin update proposal.

    Marks the proposal as blocked without updating config.

    Requires:
    - X-Admin-Key header (or X-Admin-Token for DEFAULT institution)
    - X-Institution-Id header

    Args:
        proposal_id: Proposal UUID to block.
        body: Optional reason for blocking.

    Returns:
        Updated proposal.

    Raises:
        HTTPException: 404 if proposal not found, 400 if wrong type, 409 if already decided.
    """
    institution_id = _require_institution_header(x_institution_id)

    # Authenticate admin for this institution
    require_admin_auth(request, institution_id)

    actor_id = x_actor_id or "admin"
    request_id = x_request_id
    reason = body.reason if body else None

    success, error_code, error_message = block_pin_update_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        actor_id=actor_id,
        request_id=request_id,
        reason=reason,
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

    return PinProposalResponse(
        proposal_id=proposal_id,
        status="DECIDED",
        decision="block",
        reason=reason,
    )