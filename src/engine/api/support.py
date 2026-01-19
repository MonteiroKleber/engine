"""Support API endpoints with RBAC protection."""

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from engine.core.actor_context import ActorContext
from engine.core.rbac import gate_rbac
from engine.core.ledger import get_ledger, get_ledger_for_institution
from engine.core.state_store import get_state_store
from engine.core.errors import STATE_STORE_UNAVAILABLE, MANDATE_DENIED, AUTONOMY_INSUFFICIENT, TICKET_NOT_FOUND
from engine.core.institution_context import get_request_institution_id
from engine.core.dept_context import get_ledger_step_name
from engine.core.mandates import evaluate_mandates, emit_mandate_decision
from engine.core.autonomy import evaluate_autonomy, emit_autonomy_evaluated
from .dependencies import get_actor_context, require_permission

router = APIRouter(prefix="/support", tags=["support"])


def emit_rbac_decision(
    actor: ActorContext,
    permission: str,
    allowed: bool,
    case_id: str,
    step: str,
    dept_id: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> None:
    """Emit RBAC_DECISION event to ledger.

    Args:
        actor: Actor context with identity info.
        permission: Permission being checked.
        allowed: Whether permission was granted.
        case_id: Case identifier.
        step: Base step name.
        dept_id: Optional department ID for namespacing.
        institution_id: Optional institution ID for ledger namespacing.
    """
    # Use institution-specific ledger if institution_id provided
    if institution_id:
        ledger = get_ledger_for_institution(institution_id)
    else:
        ledger = get_ledger()

    if ledger:
        # Apply dept prefix to step name if dept_id is set
        ledger_step = get_ledger_step_name(step, dept_id)
        ledger.append(
            event_type="RBAC_DECISION",
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_roles=actor.roles,
            case_id=case_id,
            step=ledger_step,
            payload={
                "permission": permission,
                "decision": "allow" if allowed else "deny",
            },
            dept_id=dept_id,
        )


def generate_ticket_id() -> str:
    """Generate a new ticket ID (UUID)."""
    return str(uuid.uuid4())


async def create_ticket_handler(
    request: Request,
    actor: ActorContext,
    dept_id: Optional[str] = None,
) -> JSONResponse:
    """Core handler for creating a support ticket.

    Args:
        request: FastAPI request object.
        actor: Actor context with identity info.
        dept_id: Optional department ID for namespacing.

    Returns:
        JSONResponse with 200 (created).
    """
    # Get institution_id from request context (set by middleware)
    institution_id = get_request_institution_id(request)

    permission = "ticket.create"
    api_trigger = "POST /support/tickets"

    # Check RBAC permission first (use dept_id for per-dept RBAC lookup)
    allowed = gate_rbac(permission, actor, dept_id=dept_id)
    emit_rbac_decision(
        actor, permission, allowed, "ticket", "RBAC:ticket.create",
        dept_id=dept_id, institution_id=institution_id
    )

    # Enforce RBAC permission (use dept_id for per-dept RBAC lookup)
    check_perm = require_permission(permission, dept_id=dept_id)
    check_perm(actor)

    # Pre-read body for mandate/autonomy evaluation
    body_bytes = await request.body()
    try:
        import json
        payload_dict = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        payload_dict = {}

    # Run mandate "pre" gate
    endpoint_sig = api_trigger
    mandate_result = evaluate_mandates(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        actor=actor,
        payload=payload_dict,
        institution_id=institution_id,
    )

    # Emit mandate decision to ledger
    ticket_id_for_ledger = "ticket"
    emit_mandate_decision(
        phase="pre",
        endpoint_sig=endpoint_sig,
        dept_id=dept_id,
        case_id=ticket_id_for_ledger,
        actor=actor,
        result=mandate_result,
    )

    # Enforce mandate - if denied, return 403
    if not mandate_result.allow:
        violation_messages = [v.message for v in mandate_result.violations]
        raise HTTPException(
            status_code=403,
            detail={
                "code": MANDATE_DENIED,
                "message": "Mandate denied",
                "mandate_id": mandate_result.mandate_id,
                "violations": violation_messages,
            },
        )

    # Run autonomy "pre" gate
    autonomy_result = evaluate_autonomy(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
    )

    # Emit autonomy decision to ledger
    emit_autonomy_evaluated(
        tenant_id=actor.tenant_id,
        actor=actor,
        dept_id=dept_id,
        phase="pre",
        endpoint_sig=endpoint_sig,
        case_id=ticket_id_for_ledger,
        result=autonomy_result,
    )

    # Enforce autonomy - if denied, return 403
    if autonomy_result.decision == "deny":
        raise HTTPException(
            status_code=403,
            detail={
                "code": AUTONOMY_INSUFFICIENT,
                "message": "Autonomy level insufficient",
                "current_level": autonomy_result.current_level,
                "required_level": autonomy_result.required_level,
                "rule_id": autonomy_result.rule_id,
                "reason": autonomy_result.reason,
            },
        )

    # Generate ticket ID and save to state store
    ticket_id = generate_ticket_id()

    state_store = get_state_store(dept_id, institution_id=institution_id)
    if not state_store:
        raise HTTPException(
            status_code=503,
            detail={
                "code": STATE_STORE_UNAVAILABLE,
                "message": "State store not available",
            },
        )

    # Store ticket in state store
    state_store.create_ticket(
        ticket_id=ticket_id,
        subject=payload_dict.get("subject", ""),
        description=payload_dict.get("description", ""),
        payload_raw=body_bytes,
    )

    return JSONResponse(
        status_code=200,
        content={
            "id": ticket_id,
            "status": "created",
            "actor_id": actor.actor_id,
        },
    )


async def get_ticket_handler(
    request: Request,
    ticket_id: str,
    actor: ActorContext,
    dept_id: Optional[str] = None,
) -> JSONResponse:
    """Core handler for getting a support ticket.

    Args:
        request: FastAPI request object.
        ticket_id: Ticket ID to retrieve.
        actor: Actor context with identity info.
        dept_id: Optional department ID for namespacing.

    Returns:
        JSONResponse with ticket data, or 404 if not found.
    """
    # Get institution_id from request context (set by middleware)
    institution_id = get_request_institution_id(request)

    permission = "ticket.read"
    case_id = f"ticket:{ticket_id}"
    step = "RBAC:ticket.read"

    # Check permission and emit decision (use dept_id for per-dept RBAC lookup)
    allowed = gate_rbac(permission, actor, dept_id=dept_id)
    emit_rbac_decision(
        actor, permission, allowed, case_id, step,
        dept_id=dept_id, institution_id=institution_id
    )

    # Enforce permission (use dept_id for per-dept RBAC lookup)
    check_perm = require_permission(permission, dept_id=dept_id)
    check_perm(actor)

    # Look up ticket in institution-specific state store
    state_store = get_state_store(dept_id, institution_id=institution_id)
    if not state_store:
        raise HTTPException(
            status_code=503,
            detail={
                "code": STATE_STORE_UNAVAILABLE,
                "message": "State store not available",
            },
        )

    ticket = state_store.get_ticket(ticket_id)
    if not ticket:
        # Return 404 (not 403) for anti-inference - don't reveal existence
        raise HTTPException(
            status_code=404,
            detail={
                "code": TICKET_NOT_FOUND,
                "message": "Ticket not found",
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "id": ticket.ticket_id,
            "subject": ticket.subject,
            "status": ticket.status,
            "created_at": ticket.created_at,
            "actor_id": actor.actor_id,
        },
    )
