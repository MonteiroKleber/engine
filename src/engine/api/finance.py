"""Finance API endpoints with RBAC protection and approvals."""

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from engine.core.actor_context import ActorContext
from engine.core.rbac import gate_rbac
from engine.core.ledger import get_ledger
from engine.core.approvals import (
    get_approvals_policy,
    generate_approval_id,
    emit_approval_requested,
    compute_payload_sha256,
    get_approval_step_name,
)
from engine.core.state_store import get_state_store
from engine.core.errors import STATE_STORE_UNAVAILABLE, POLICY_DENIED, MANDATE_DENIED, AUTONOMY_INSUFFICIENT
from engine.core.dept_context import (
    validate_legacy_finance_route,
    get_ledger_step_name,
)
from engine.core.policy import (
    evaluate_policies,
    emit_policy_decision,
)
from engine.core.mandates import (
    evaluate_mandates,
    emit_mandate_decision,
)
from engine.core.autonomy import (
    evaluate_autonomy,
    emit_autonomy_evaluated,
)
from .dependencies import get_actor_context, require_permission

router = APIRouter(prefix="/finance", tags=["finance"])


def emit_rbac_decision(
    actor: ActorContext,
    permission: str,
    allowed: bool,
    case_id: str,
    step: str,
    dept_id: Optional[str] = None,
) -> None:
    """Emit RBAC_DECISION event to ledger.

    Args:
        actor: Actor context with identity info.
        permission: Permission being checked.
        allowed: Whether permission was granted.
        case_id: Case identifier.
        step: Base step name.
        dept_id: Optional department ID for namespacing.
    """
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
        )


def generate_expense_id() -> str:
    """Generate a new expense ID (UUID)."""
    return str(uuid.uuid4())


async def create_expense_handler(
    request: Request,
    actor: ActorContext,
    dept_id: Optional[str] = None,
) -> JSONResponse:
    """Core handler for creating an expense.

    Args:
        request: FastAPI request object.
        actor: Actor context with identity info.
        dept_id: Optional department ID for namespacing.

    Returns:
        JSONResponse with 202 (pending_approval) or 200 (created).
    """
    permission = "expense.create"
    api_trigger = "POST /finance/expenses"

    # Check RBAC permission first
    allowed = gate_rbac(permission, actor)
    emit_rbac_decision(
        actor, permission, allowed, "expense", "RBAC:expense.create", dept_id=dept_id
    )

    # Enforce RBAC permission
    check_perm = require_permission(permission)
    check_perm(actor)

    # Pre-read body for policy evaluation (will be used later if needed)
    body_bytes = await request.body()
    try:
        import json
        payload_dict = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        payload_dict = {}

    # Run policy "pre" gate before approvals
    endpoint_sig = api_trigger  # "POST /finance/expenses"
    policy_result = evaluate_policies(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        payload=payload_dict,
    )

    # Emit policy decision to ledger (always, for allow or deny)
    expense_id_for_ledger = "expense"  # Placeholder before expense_id is generated
    emit_policy_decision(
        phase="pre",
        endpoint_sig=endpoint_sig,
        dept_id=dept_id,
        case_id=expense_id_for_ledger,
        actor=actor,
        result=policy_result,
    )

    # Enforce policy - if denied, return 403
    if not policy_result.allow:
        violation_messages = [v.message for v in policy_result.violations]
        raise HTTPException(
            status_code=403,
            detail={
                "code": POLICY_DENIED,
                "message": "Policy denied",
                "violations": violation_messages,
            },
        )

    # Run mandate "pre" gate before approvals
    mandate_result = evaluate_mandates(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        actor=actor,
        payload=payload_dict,
    )

    # Emit mandate decision to ledger (always, for allow or deny)
    emit_mandate_decision(
        phase="pre",
        endpoint_sig=endpoint_sig,
        dept_id=dept_id,
        case_id=expense_id_for_ledger,
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

    # Run autonomy "pre" gate before approvals
    autonomy_result = evaluate_autonomy(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
    )

    # Emit autonomy decision to ledger (always, for allow or deny)
    emit_autonomy_evaluated(
        tenant_id=actor.tenant_id,
        actor=actor,
        dept_id=dept_id,
        phase="pre",
        endpoint_sig=endpoint_sig,
        case_id=expense_id_for_ledger,
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

    # Check if approval is required for this API
    policy = get_approvals_policy()
    if policy:
        rule = policy.get_rule_for_api(api_trigger)
        if rule:
            # Generate IDs
            expense_id = generate_expense_id()
            approval_id = generate_approval_id()

            # Compute payload SHA256 (body_bytes already read above)
            payload_sha256 = compute_payload_sha256(body_bytes)

            # Save to state store (dept-aware in multi mode)
            state_store = get_state_store(dept_id)
            if not state_store:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": STATE_STORE_UNAVAILABLE,
                        "message": "State store not available",
                    },
                )

            state_store.create_expense(
                expense_id=expense_id,
                approval_id=approval_id,
                payload_sha256=payload_sha256,
                payload_raw=body_bytes,
            )

            # Emit APPROVAL_REQUESTED event
            emit_approval_requested(
                approval_id=approval_id,
                rule=rule,
                actor=actor,
                payload_sha256=payload_sha256,
            )

            step = get_approval_step_name(rule.rule_name)
            # Apply dept prefix to step if dept_id is set
            step = get_ledger_step_name(step, dept_id)

            return JSONResponse(
                status_code=202,
                content={
                    "status": "pending_approval",
                    "expense_id": expense_id,
                    "approval_id": approval_id,
                    "step": step,
                },
            )

    # No approval required - return created directly
    return JSONResponse(
        status_code=200,
        content={
            "id": "exp-001",
            "status": "created",
            "actor_id": actor.actor_id,
        },
    )


@router.post("/expenses")
async def create_expense(
    request: Request,
    actor: ActorContext = Depends(get_actor_context),
) -> JSONResponse:
    """Create an expense (requires expense.create permission).

    Legacy route - in multi-mode acts as alias for finance department.
    If approval rule exists for this endpoint, returns 202 with pending_approval.
    Otherwise, returns 200 with created status.
    """
    # Validate and get dept_id for legacy route
    dept_id = validate_legacy_finance_route()
    return await create_expense_handler(request, actor, dept_id=dept_id)


async def get_expense_handler(
    expense_id: str,
    actor: ActorContext,
    dept_id: Optional[str] = None,
) -> JSONResponse:
    """Core handler for getting an expense.

    Args:
        expense_id: Expense ID to retrieve.
        actor: Actor context with identity info.
        dept_id: Optional department ID for namespacing.

    Returns:
        JSONResponse with expense data.
    """
    permission = "expense.read"
    case_id = f"expense:{expense_id}"
    step = "RBAC:expense.read"

    # Check permission and emit decision
    allowed = gate_rbac(permission, actor)
    emit_rbac_decision(actor, permission, allowed, case_id, step, dept_id=dept_id)

    # Enforce permission
    check_perm = require_permission(permission)
    check_perm(actor)

    return JSONResponse(
        status_code=200,
        content={
            "id": expense_id,
            "status": "retrieved",
            "actor_id": actor.actor_id,
        },
    )


@router.get("/expenses/{expense_id}")
async def get_expense(
    expense_id: str,
    actor: ActorContext = Depends(get_actor_context),
) -> JSONResponse:
    """Get an expense by ID (requires expense.read permission).

    Legacy route - in multi-mode acts as alias for finance department.
    """
    # Validate and get dept_id for legacy route
    dept_id = validate_legacy_finance_route()
    return await get_expense_handler(expense_id, actor, dept_id=dept_id)
