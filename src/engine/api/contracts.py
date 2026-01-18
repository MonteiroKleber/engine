"""Interdepartmental contracts API endpoints."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from engine.core.actor_context import ActorContext
from engine.core.dept_context import get_request_dept
from engine.core.institution_context import get_request_institution_id, DEFAULT_INSTITUTION_ID
from engine.core.institution_config import get_cached_config
from engine.core.ledger import get_ledger, LedgerEvent
from engine.core.contracts import (
    find_contract,
    validate_consumer,
    validate_provider,
    compute_payload_sha256,
    generate_case_id,
)
from engine.core.errors import (
    CONTRACT_NOT_FOUND,
    CONTRACT_PROVIDER_MISMATCH,
    CONTRACT_CONSUMER_FORBIDDEN,
    CONTRACT_CASE_ID_REQUIRED,
    CONTRACT_DECISION_INVALID,
)
from .dependencies import get_actor_context

router = APIRouter(prefix="/d/{dept}/contracts", tags=["contracts"])


class InvokeRequest(BaseModel):
    """Request body for contract invoke."""

    case_id: Optional[str] = Field(default=None, description="Optional case ID")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Request payload")


class DecideRequest(BaseModel):
    """Request body for contract decide."""

    case_id: str = Field(..., description="Case ID (required)")
    decision: str = Field(..., description="Decision: allow or deny")
    reason: Optional[str] = Field(default=None, description="Optional reason")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Optional details")


VALID_DECISIONS = {"allow", "deny"}


def _check_contracts_enabled(request: Request) -> None:
    """Check if contracts stub is enabled for this institution.

    Args:
        request: FastAPI request.

    Raises:
        HTTPException: 404 if contracts stub is disabled.
    """
    institution_id = get_request_institution_id(request) or DEFAULT_INSTITUTION_ID
    config = get_cached_config(institution_id)

    if not config.flags.enable_contracts_stub:
        raise HTTPException(
            status_code=404,
            detail={
                "code": CONTRACT_NOT_FOUND,
                "message": "Contracts feature is not enabled for this institution",
            },
        )


def _find_invoke_event(
    ledger, case_id: str, contract_id: str
) -> Optional[Dict[str, Any]]:
    """Find the CONTRACT_INVOKED event for a case.

    Args:
        ledger: Ledger instance.
        case_id: Case ID to search.
        contract_id: Contract ID.

    Returns:
        Details dict from the invoke event, or None if not found.
    """
    if ledger is None:
        return None

    events = ledger.get_all_events()
    # Search in reverse to find the most recent
    for event in reversed(events):
        if (
            event.event_type == "CONTRACT_INVOKED"
            and event.case_id == case_id
            and event.payload.get("contract_id") == contract_id
        ):
            return event.payload
    return None


@router.post("/{contract_id}/invoke")
async def invoke_contract(
    dept: str,
    contract_id: str,
    request: Request,
    body: InvokeRequest,
    actor: ActorContext = Depends(get_actor_context),
) -> JSONResponse:
    """Invoke an interdepartmental contract as consumer.

    The consumer dept is extracted from the route /d/{dept}/...
    Emits CONTRACT_INVOKED event to ledger.
    """
    # Check if contracts are enabled for this institution
    _check_contracts_enabled(request)

    # Get consumer dept from request state (set by middleware)
    consumer_dept = get_request_dept(request)
    if consumer_dept is None:
        consumer_dept = dept

    # Find contract
    contract = find_contract(contract_id)
    if contract is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": CONTRACT_NOT_FOUND,
                "message": f"Contract not found: {contract_id}",
            },
        )

    # Validate consumer is authorized
    if not validate_consumer(contract, consumer_dept):
        raise HTTPException(
            status_code=403,
            detail={
                "code": CONTRACT_CONSUMER_FORBIDDEN,
                "message": f"Department '{consumer_dept}' is not authorized to invoke contract '{contract_id}'",
            },
        )

    # Resolve case_id
    case_id = body.case_id if body.case_id else generate_case_id()

    # Compute payload hash
    payload_sha256 = compute_payload_sha256(body.payload)

    # Emit CONTRACT_INVOKED event
    ledger = get_ledger()
    if ledger:
        ledger.append(
            event_type="CONTRACT_INVOKED",
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_roles=actor.roles,
            case_id=case_id,
            step=f"CONTRACT:{contract_id}",
            payload={
                "contract_id": contract_id,
                "origin_dept": consumer_dept,
                "target_dept": contract.provider_dept,
                "payload_sha256": payload_sha256,
                "request_payload_present": True,
                "dependency_id": None,
                "status": "pending",
                "decision": "allow",  # Placeholder per spec
            },
        )

    return JSONResponse(
        status_code=202,
        content={
            "status": "pending",
            "case_id": case_id,
            "contract_id": contract_id,
            "provider_dept": contract.provider_dept,
            "consumer_dept": consumer_dept,
            "payload_sha256": payload_sha256,
        },
    )


@router.post("/{contract_id}/decide")
async def decide_contract(
    dept: str,
    contract_id: str,
    request: Request,
    body: DecideRequest,
    actor: ActorContext = Depends(get_actor_context),
) -> JSONResponse:
    """Decide on an interdepartmental contract as provider.

    The provider dept is extracted from the route /d/{dept}/...
    Emits CONTRACT_DECIDED event to ledger.
    """
    # Check if contracts are enabled for this institution
    _check_contracts_enabled(request)

    # Get provider dept from request state (set by middleware)
    provider_dept = get_request_dept(request)
    if provider_dept is None:
        provider_dept = dept

    # Find contract
    contract = find_contract(contract_id)
    if contract is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": CONTRACT_NOT_FOUND,
                "message": f"Contract not found: {contract_id}",
            },
        )

    # Validate provider matches
    if not validate_provider(contract, provider_dept):
        raise HTTPException(
            status_code=409,
            detail={
                "code": CONTRACT_PROVIDER_MISMATCH,
                "message": f"Department '{provider_dept}' is not the provider of contract '{contract_id}' (expected: '{contract.provider_dept}')",
            },
        )

    # Validate case_id is present
    if not body.case_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": CONTRACT_CASE_ID_REQUIRED,
                "message": "case_id is required for decide",
            },
        )

    # Validate decision
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": CONTRACT_DECISION_INVALID,
                "message": f"Invalid decision: '{body.decision}'. Must be 'allow' or 'deny'",
            },
        )

    # Try to find the original invoke event to get origin_dept
    ledger = get_ledger()
    origin_dept = None
    payload_sha256 = None

    if ledger:
        invoke_payload = _find_invoke_event(ledger, body.case_id, contract_id)
        if invoke_payload:
            origin_dept = invoke_payload.get("origin_dept")
            payload_sha256 = invoke_payload.get("payload_sha256")

    # Emit CONTRACT_DECIDED event
    if ledger:
        ledger.append(
            event_type="CONTRACT_DECIDED",
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_roles=actor.roles,
            case_id=body.case_id,
            step=f"CONTRACT:{contract_id}",
            payload={
                "contract_id": contract_id,
                "origin_dept": origin_dept,
                "target_dept": provider_dept,
                "decision": body.decision,
                "reason": body.reason,
                "decider_actor_id": actor.actor_id,
                "payload_sha256": payload_sha256,
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "decided",
            "case_id": body.case_id,
            "contract_id": contract_id,
            "decision": body.decision,
        },
    )
