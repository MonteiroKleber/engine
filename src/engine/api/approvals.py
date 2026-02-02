"""Approvals API endpoint.

Supports approvals for:
- Finance expenses (original use case)
- Legacy write actions (GAP 3: no self-approved)
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from engine.core.actor_context import ActorContext
from engine.core.ledger import get_ledger, get_ledger_for_institution
from engine.core.institution_context import get_request_institution_id, resolve_institution_id
from engine.core.institution_context import DEFAULT_INSTITUTION_ID
from engine.core.admin_auth import require_admin_auth
from engine.core.legacy_telemetry import record_legacy_invocation
from engine.core.approvals import (
    ApprovalRule,
    ApprovalTargetKind,
    find_approval_requested,
    find_approval_decided,
    is_approval_decided,
    can_actor_decide,
    emit_approval_decided,
    get_approvals_policy,
    get_rule_name_from_step,
    extract_target_from_event,
    get_job_ref_from_approval,
    get_entity_ref_from_approval,
    JobRef,
    EntityRef,
)
from engine.core.sod import check_sod, SOD_VIOLATION, SOD_RULE_INVALID
from engine.core.state_store import (
    get_state_store,
    STATUS_COMMITTED,
    STATUS_REJECTED,
)
from engine.core.invariants import validate_expense_invariants
from engine.core.errors import (
    CASE_NOT_FOUND,
    INVARIANT_VIOLATION,
    INVARIANT_SCHEMA_INVALID,
    STATE_STORE_UNAVAILABLE,
    POLICY_DENIED,
    MANDATE_DENIED,
    AUTONOMY_INSUFFICIENT,
    LEGACY_WRITE_ACTION_NOT_FOUND,
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
from .dependencies import get_actor_context

router = APIRouter(prefix="/approvals", tags=["approvals"])


class DecideRequest(BaseModel):
    """Request body for decide endpoint."""
    decision: str
    reason: Optional[str] = None


class PendingApprovalItem(BaseModel):
    """Item in pending approvals list."""
    approval_id: str
    created_at: str
    rule_name: Optional[str] = None
    case_id: str
    step: str
    requested_by: str
    requested_by_roles: List[str] = []
    dept_id: Optional[str] = None


class PendingApprovalsResponse(BaseModel):
    """Response for pending approvals list."""
    approvals: List[PendingApprovalItem]
    total: int


class ApprovalItemWithStatus(BaseModel):
    """Approval item with status information."""
    approval_id: str
    created_at: str
    rule_name: Optional[str] = None
    case_id: str
    step: str
    requested_by: str
    requested_by_roles: List[str] = []
    dept_id: Optional[str] = None
    status: str  # pending, approved, rejected
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    decision_reason: Optional[str] = None


class ApprovalsListResponse(BaseModel):
    """Response for approvals list with status filter."""
    approvals: List[ApprovalItemWithStatus]
    total: int


@router.get("", response_model=ApprovalsListResponse)
async def list_approvals(
    request: Request,
    status: Optional[str] = None,
    limit: int = 100,
) -> ApprovalsListResponse:
    """List approvals with optional status filter.

    Args:
        status: Filter by status (pending, approved, rejected, all). Default: all.
        limit: Maximum number of approvals to return.

    Returns:
        List of approval items with status.
    """
    institution_id = resolve_institution_id(request, require_header=True)
    require_admin_auth(request, institution_id)

    ledger = get_ledger_for_institution(institution_id)
    all_events = ledger.get_all_events()

    # Build approval data from events
    requested_events: Dict[str, Any] = {}  # approval_id -> request event
    decided_events: Dict[str, Any] = {}    # approval_id -> decide event

    for event in all_events:
        if event.event_type == "APPROVAL_REQUESTED":
            approval_id = event.case_id
            if approval_id:
                requested_events[approval_id] = event
        elif event.event_type == "APPROVAL_DECIDED":
            approval_id = event.case_id
            if approval_id:
                decided_events[approval_id] = event

    # Build approval items with status
    items: List[ApprovalItemWithStatus] = []
    for approval_id, req_event in requested_events.items():
        dec_event = decided_events.get(approval_id)

        if dec_event:
            # Decided - check decision
            decision = dec_event.data.get("decision", "approved") if dec_event.data else "approved"
            item_status = "approved" if decision == "approve" else "rejected"
        else:
            item_status = "pending"

        # Apply status filter
        if status and status != "all" and item_status != status:
            continue

        rule_name = get_rule_name_from_step(req_event.step) if req_event.step else None

        items.append(
            ApprovalItemWithStatus(
                approval_id=approval_id,
                created_at=req_event.timestamp or "",
                rule_name=rule_name,
                case_id=req_event.case_id,
                step=req_event.step or "",
                requested_by=req_event.actor_id or "",
                requested_by_roles=list(req_event.actor_roles) if req_event.actor_roles else [],
                dept_id=req_event.dept_id,
                status=item_status,
                decided_at=dec_event.timestamp if dec_event else None,
                decided_by=dec_event.actor_id if dec_event else None,
                decision_reason=dec_event.data.get("reason") if dec_event and dec_event.data else None,
            )
        )

    # Sort by created_at descending
    items.sort(key=lambda x: x.created_at, reverse=True)

    return ApprovalsListResponse(
        approvals=items[:limit],
        total=len(items),
    )


@router.get("/pending", response_model=PendingApprovalsResponse)
async def list_pending_approvals(
    request: Request,
    limit: int = 100,
) -> PendingApprovalsResponse:
    """List pending approvals for institution.

    Returns approvals that have been requested but not yet decided.
    Pending = APPROVAL_REQUESTED without corresponding APPROVAL_DECIDED.

    Requires:
    - `X-Institution-Id` header
    - Admin auth (`X-Admin-Key` or bootstrap `X-Admin-Token`)

    Example:
    ```bash
    curl http://localhost:8001/approvals/pending?limit=50 \\
        -H "X-Institution-Id: ${INSTITUTION_ID}" \\
        -H "X-Admin-Token: ${ENGINE_ISE_ADMIN_TOKEN}"
    ```

    Args:
        request: FastAPI request object.
        limit: Maximum number of approvals to return (default 100).

    Returns:
        List of pending approval items.
    """
    # Require admin auth + institution ID
    institution_id = resolve_institution_id(request, require_header=True)
    require_admin_auth(request, institution_id)

    # Get all events from ledger
    ledger = get_ledger_for_institution(institution_id)
    all_events = ledger.get_all_events()

    # Build sets of requested and decided approval IDs
    requested_events: Dict[str, Any] = {}  # approval_id -> event
    decided_ids: set = set()

    for event in all_events:
        if event.event_type == "APPROVAL_REQUESTED":
            # Extract approval_id from case_id (which is the approval_id for approval events)
            approval_id = event.case_id
            if approval_id:
                requested_events[approval_id] = event
        elif event.event_type == "APPROVAL_DECIDED":
            approval_id = event.case_id
            if approval_id:
                decided_ids.add(approval_id)

    # Find pending: requested but not decided
    pending_items: List[PendingApprovalItem] = []
    for approval_id, event in requested_events.items():
        if approval_id not in decided_ids:
            # Extract rule_name from step if possible
            rule_name = get_rule_name_from_step(event.step) if event.step else None

            pending_items.append(
                PendingApprovalItem(
                    approval_id=approval_id,
                    created_at=event.timestamp or "",
                    rule_name=rule_name,
                    case_id=event.case_id,
                    step=event.step or "",
                    requested_by=event.actor_id or "",
                    requested_by_roles=list(event.actor_roles) if event.actor_roles else [],
                    dept_id=event.dept_id,
                )
            )

    # Sort by created_at descending (most recent first)
    pending_items.sort(key=lambda x: x.created_at, reverse=True)

    # Apply limit
    limited_items = pending_items[:limit]

    return PendingApprovalsResponse(
        approvals=limited_items,
        total=len(pending_items),
    )


def _is_legacy_write_approval(rule_name: str) -> bool:
    """Check if approval is for a legacy write action.

    Legacy write rules have trigger_api like "POST /bridge/write/{action_type}".

    Args:
        rule_name: The approval rule name.

    Returns:
        True if this is a legacy write approval.
    """
    # Check if rule name contains legacy write indicators
    return rule_name.startswith("legacy.") or "bridge/write" in rule_name


def _get_legacy_write_registry(institution_id: str, dept_id: Optional[str] = None):
    """Get legacy write registry for institution.

    Lazy import to avoid circular dependency.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        LegacyWriteRegistry instance.
    """
    from engine.legacy_bridge.write_registry import LegacyWriteRegistry
    return LegacyWriteRegistry(institution_id, dept_id)


def emit_case_committed(
    expense_id: str,
    actor: ActorContext,
    institution_id: Optional[str] = None,
) -> None:
    """Emit CASE_COMMITTED event to ledger.

    Args:
        expense_id: The expense ID.
        actor: The actor context.
        institution_id: Optional institution ID for ledger namespacing.
    """
    # Use institution-specific ledger if institution_id provided
    if institution_id:
        ledger = get_ledger_for_institution(institution_id)
    else:
        ledger = get_ledger()

    if ledger:
        ledger.append(
            event_type="CASE_COMMITTED",
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_roles=actor.roles,
            case_id=expense_id,
            step="CASE:expense.commit",
            payload={
                "name": "CASE:expense.commit",
            },
        )


def emit_case_rejected(
    expense_id: str,
    actor: ActorContext,
    institution_id: Optional[str] = None,
) -> None:
    """Emit CASE_REJECTED event to ledger.

    Args:
        expense_id: The expense ID.
        actor: The actor context.
        institution_id: Optional institution ID for ledger namespacing.
    """
    # Use institution-specific ledger if institution_id provided
    if institution_id:
        ledger = get_ledger_for_institution(institution_id)
    else:
        ledger = get_ledger()

    if ledger:
        ledger.append(
            event_type="CASE_REJECTED",
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_roles=actor.roles,
            case_id=expense_id,
            step="CASE:expense.reject",
            payload={
                "name": "CASE:expense.reject",
            },
        )


@router.post("/{approval_id}/decide")
async def decide_approval(
    request: Request,
    approval_id: str,
    body: DecideRequest,
    actor: ActorContext = Depends(get_actor_context),
) -> Dict[str, Any]:
    """Decide on an approval request.

    Args:
        request: FastAPI request object.
        approval_id: The approval ID.
        body: Decision request with decision and optional reason.
        actor: The deciding actor context.

    Returns:
        Result of the decision.

    Raises:
        HTTPException: Various error codes for invalid states.
    """
    # Get institution_id from request context (set by middleware)
    institution_id = get_request_institution_id(request)
    institution_id_for_telemetry = (
        institution_id
        or request.headers.get("X-Institution-Id")
        or request.headers.get("X-Tenant-Id")
        or DEFAULT_INSTITUTION_ID
    )
    record_legacy_invocation(
        institution_id=institution_id_for_telemetry,
        endpoint_sig="POST /approvals/{approval_id}/decide",
        method="POST",
        path=str(request.url.path),
    )

    # Validate decision value
    if body.decision not in ("approve", "reject"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "APPROVAL_DECISION_INVALID",
                "message": "Decision must be 'approve' or 'reject'",
            },
        )

    # Use institution_id for ledger lookup (fall back to header if not set by middleware)
    lookup_institution_id = (
        institution_id
        or request.headers.get("X-Institution-Id")
        or request.headers.get("X-Tenant-Id")
    )

    # Check if approval exists (APPROVAL_REQUESTED event)
    requested_event = find_approval_requested(approval_id, lookup_institution_id)
    if not requested_event:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "APPROVAL_NOT_FOUND",
                "message": "Approval not found",
            },
        )

    # Check if already decided
    if is_approval_decided(approval_id, lookup_institution_id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APPROVAL_ALREADY_DECIDED",
                "message": "Approval already decided",
            },
        )

    # Get the rule from the step name
    step = requested_event.step
    rule_name = get_rule_name_from_step(step)
    if not rule_name:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "APPROVAL_RULE_ERROR",
                "message": "Could not determine approval rule",
            },
        )

    policy = get_approvals_policy()
    if not policy:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "APPROVAL_POLICY_ERROR",
                "message": "Approvals policy not loaded",
            },
        )

    rule = policy.get_rule_by_name(rule_name)
    # Bazari generic approvals (Expansão 03):
    # approvals.json may legitimately have no explicit rule for workflow transitions.
    # In that case, fall back to the generic approval index stored in the state store.
    state_store = get_state_store(institution_id=institution_id)
    if not state_store:
        raise HTTPException(
            status_code=503,
            detail={
                "code": STATE_STORE_UNAVAILABLE,
                "message": "State store not available",
            },
        )

    generic_approval = state_store.get_generic_approval(approval_id)
    if not rule and generic_approval:
        transition_def = generic_approval.get("transition_def", {})
        approvals_def = transition_def.get("approvals") or {}

        trigger_api = ""
        try:
            trigger_api = (requested_event.payload or {}).get("target", {}).get("api", "")  # type: ignore[union-attr]
        except Exception:
            trigger_api = ""

        rule = ApprovalRule(
            rule_name=rule_name,
            trigger_api=trigger_api or "POST /approvals/{approval_id}/decide",
            approver_roles=list(approvals_def.get("roles", [])),
            quorum=int(approvals_def.get("quorum", 1) or 1),
        )

    if not rule:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "APPROVAL_RULE_ERROR",
                "message": f"Approval rule '{rule_name}' not found",
            },
        )

    # Check if actor has required role
    if not can_actor_decide(actor, rule):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APPROVAL_FORBIDDEN",
                "message": "Forbidden",
            },
        )

    # Check SoD constraints
    sod_ok, sod_error_code, sod_message = check_sod(
        case_id=approval_id,
        step=step,
        actor=actor,
    )
    if not sod_ok:
        if sod_error_code == SOD_RULE_INVALID:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": sod_error_code,
                    "message": sod_message,
                },
            )
        else:
            # SOD_VIOLATION
            raise HTTPException(
                status_code=409,
                detail={
                    "code": sod_error_code,
                    "message": sod_message,
                },
            )

    # Check target kind from the APPROVAL_REQUESTED event payload
    target = extract_target_from_event(requested_event)

    # Handle job-based approvals (Jobs First-Class spec)
    if target and target.kind == ApprovalTargetKind.JOB:
        job_ref = get_job_ref_from_approval(approval_id, lookup_institution_id)
        if job_ref:
            return await _handle_job_approval_decision(
                request=request,
                approval_id=approval_id,
                rule=rule,
                actor=actor,
                decision=body.decision,
                reason=body.reason,
                institution_id=institution_id,
                job_ref=job_ref,
            )

    # Check if this is a legacy write approval (GAP 3)
    if _is_legacy_write_approval(rule_name):
        return await _handle_legacy_write_decision(
            request=request,
            approval_id=approval_id,
            rule=rule,
            actor=actor,
            decision=body.decision,
            reason=body.reason,
            institution_id=institution_id,
        )

    if generic_approval:
        return await _handle_generic_approval_decision(
            request=request,
            approval_id=approval_id,
            rule=rule,
            actor=actor,
            decision=body.decision,
            reason=body.reason,
            institution_id=institution_id,
            state_store=state_store,
            generic_approval=generic_approval,
        )

    # Original finance expense flow below
    expense = state_store.get_expense_by_approval_id(approval_id)
    if not expense:
        raise HTTPException(
            status_code=404,
            detail={
                "code": CASE_NOT_FOUND,
                "message": "Case not found",
            },
        )

    expense_id = expense.expense_id

    # Handle reject
    if body.decision == "reject":
        # Update status
        state_store.update_expense_status(expense_id, STATUS_REJECTED)

        # Emit APPROVAL_DECIDED
        emit_approval_decided(
            approval_id=approval_id,
            rule=rule,
            actor=actor,
            decision=body.decision,
            reason=body.reason,
        )

        # Emit CASE_REJECTED
        emit_case_rejected(expense_id, actor, institution_id=institution_id)

        return {
            "status": "decided",
            "approval_id": approval_id,
            "expense_id": expense_id,
            "decision": body.decision,
            "case_status": STATUS_REJECTED,
        }

    # Handle approve - must validate invariants first
    payload = state_store.get_expense_payload(expense_id)
    if payload is None:
        payload = {}

    # Run policy "post" gate before commit
    # Create context payload with approval decision info
    post_endpoint_sig = "POST /approvals/{approval_id}/decide"
    context_payload = {
        **payload,
        "_approval_id": approval_id,
        "_decision": body.decision,
        "_expense_id": expense_id,
    }
    policy_result = evaluate_policies(
        phase="post",
        dept_id=None,  # Use single mode for now; multi-mode would need dept context
        endpoint_sig=post_endpoint_sig,
        payload=context_payload,
    )

    # Emit policy decision to ledger (always)
    emit_policy_decision(
        phase="post",
        endpoint_sig=post_endpoint_sig,
        dept_id=None,
        case_id=approval_id,
        actor=actor,
        result=policy_result,
    )

    # Enforce policy - if denied, return 403 and do NOT commit
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

    # Run mandate "post" gate before commit
    mandate_result = evaluate_mandates(
        phase="post",
        dept_id=None,  # Use single mode for now; multi-mode would need dept context
        endpoint_sig=post_endpoint_sig,
        actor=actor,
        payload=context_payload,
        institution_id=institution_id,
    )

    # Emit mandate decision to ledger (always)
    emit_mandate_decision(
        phase="post",
        endpoint_sig=post_endpoint_sig,
        dept_id=None,
        case_id=approval_id,
        actor=actor,
        result=mandate_result,
    )

    # Enforce mandate - if denied, return 403 and do NOT commit
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

    # Run autonomy "post" gate before commit
    autonomy_result = evaluate_autonomy(
        phase="post",
        dept_id=None,  # Use single mode for now; multi-mode would need dept context
        endpoint_sig=post_endpoint_sig,
    )

    # Emit autonomy decision to ledger (always)
    emit_autonomy_evaluated(
        tenant_id=actor.tenant_id,
        actor=actor,
        dept_id=None,
        phase="post",
        endpoint_sig=post_endpoint_sig,
        case_id=approval_id,
        result=autonomy_result,
    )

    # Enforce autonomy - if denied, return 403 and do NOT commit
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

    # Validate invariants
    inv_ok, inv_error_code, violations = validate_expense_invariants(payload)
    if not inv_ok:
        if inv_error_code == INVARIANT_SCHEMA_INVALID:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": inv_error_code,
                    "message": "Invalid invariant schema",
                    "violations": violations,
                },
            )
        else:
            # INVARIANT_VIOLATION - do NOT emit APPROVAL_DECIDED or CASE_COMMITTED
            raise HTTPException(
                status_code=422,
                detail={
                    "code": inv_error_code,
                    "message": "Invariant violation",
                    "violations": violations,
                },
            )

    # Invariants passed - commit
    state_store.update_expense_status(expense_id, STATUS_COMMITTED)

    # Emit APPROVAL_DECIDED
    emit_approval_decided(
        approval_id=approval_id,
        rule=rule,
        actor=actor,
        decision=body.decision,
        reason=body.reason,
    )

    # Emit CASE_COMMITTED
    emit_case_committed(expense_id, actor, institution_id=institution_id)

    return {
        "status": "decided",
        "approval_id": approval_id,
        "expense_id": expense_id,
        "decision": body.decision,
        "case_status": STATUS_COMMITTED,
    }


async def _handle_job_approval_decision(
    request: Request,
    approval_id: str,
    rule: Any,
    actor: ActorContext,
    decision: str,
    reason: Optional[str],
    institution_id: Optional[str],
    job_ref: "JobRef",
) -> Dict[str, Any]:
    """Handle approval decision for job-based approval (Jobs First-Class spec).

    When approved, releases job.enqueue so the job can be executed by the runtime.

    Args:
        request: FastAPI request object.
        approval_id: The approval ID.
        rule: The approval rule.
        actor: The deciding actor.
        decision: "approve" or "reject".
        reason: Optional decision reason.
        institution_id: Institution ID.
        job_ref: Job reference with job_id and action.

    Returns:
        Decision result.

    Raises:
        HTTPException: Various error codes.
    """
    from engine.core.job_store import get_job_store, JobState

    if not institution_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INSTITUTION_REQUIRED",
                "message": "Institution ID required for job approval",
            },
        )

    # Get job store and find the job
    job_store = get_job_store(institution_id, dept_id=None)
    job = job_store.get_job(job_ref.job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": f"Job {job_ref.job_id} not found",
            },
        )

    # Check job state
    if job.state != JobState.PENDING_APPROVAL.value:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_STATE_INVALID",
                "message": f"Job is not pending approval (state: {job.state})",
            },
        )

    # SoD check: proposer cannot decide their own approval
    if actor.actor_id == job.requested_by:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APPROVAL_SOD_VIOLATION",
                "message": "Self-approval not allowed: proposer cannot decide their own job approval",
            },
        )

    # Emit APPROVAL_DECIDED event
    emit_approval_decided(
        approval_id=approval_id,
        rule=rule,
        actor=actor,
        decision=decision,
        reason=reason,
        institution_id=institution_id,
    )

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    if decision == "reject":
        # Update job state to rejected
        job_store.update_job_state(
            job_id=job.job_id,
            state=JobState.REJECTED.value,
        )

        return {
            "status": "decided",
            "approval_id": approval_id,
            "job_id": job.job_id,
            "job_type": job.job_type,
            "decision": decision,
            "job_state": JobState.REJECTED.value,
        }

    # Approve: update job state to approved, ready for enqueue
    job_store.update_job_state(
        job_id=job.job_id,
        state=JobState.APPROVED.value,
        approved_by=actor.actor_id,
    )

    # If action is "enqueue", automatically enqueue the job
    if job_ref.action == "enqueue":
        from engine.core.job_dispatcher import dispatch_job_enqueue
        from engine.core.operations import Operation

        # Create a minimal operation for dispatch
        operation = Operation(
            operation_id=f"job_enqueue_{job.job_type}",
            endpoint_sig=f"POST /jobs/{job.job_id}/enqueue",
            permission="job.enqueue",
            method="POST",
            path=f"/jobs/{job.job_id}/enqueue",
        )

        enqueue_result = await dispatch_job_enqueue(
            institution_id=institution_id,
            dept_id=None,
            actor=actor,
            operation=operation,
            path_params={"job_id": job.job_id},
        )

        if enqueue_result.error_code:
            raise HTTPException(
                status_code=enqueue_result.status_code,
                detail=enqueue_result.response_body,
            )

        return {
            "status": "decided",
            "approval_id": approval_id,
            "job_id": job.job_id,
            "job_type": job.job_type,
            "decision": decision,
            "job_state": JobState.ENQUEUED.value,
            "outbox_path": enqueue_result.response_body.get("outbox_path"),
        }

    # Just approve without auto-enqueue
    return {
        "status": "decided",
        "approval_id": approval_id,
        "job_id": job.job_id,
        "job_type": job.job_type,
        "decision": decision,
        "job_state": JobState.APPROVED.value,
    }


async def _handle_legacy_write_decision(
    request: Request,
    approval_id: str,
    rule: Any,
    actor: ActorContext,
    decision: str,
    reason: Optional[str],
    institution_id: Optional[str],
) -> Dict[str, Any]:
    """Handle approval decision for legacy write action.

    GAP 3: Legacy writes are handled via the write registry, which:
    - Completes the action if approved (writes to outbox)
    - Rejects the action if rejected
    - Tracks approved_by as the actual approver (not requester)

    Args:
        request: FastAPI request object.
        approval_id: The approval ID.
        rule: The approval rule.
        actor: The deciding actor.
        decision: "approve" or "reject".
        reason: Optional decision reason.
        institution_id: Institution ID.

    Returns:
        Decision result.

    Raises:
        HTTPException: Various error codes.
    """
    if not institution_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INSTITUTION_REQUIRED",
                "message": "Institution ID required for legacy write approval",
            },
        )

    # Get write registry for this institution
    # Note: dept_id would need to be extracted from the approval request payload
    # For now, use None (single-dept mode) - can be enhanced later
    registry = _get_legacy_write_registry(institution_id, dept_id=None)

    # Find action by approval_id
    action = registry.get_action_by_approval_id(approval_id)
    if not action:
        raise HTTPException(
            status_code=404,
            detail={
                "code": LEGACY_WRITE_ACTION_NOT_FOUND,
                "message": f"Legacy write action not found for approval: {approval_id}",
            },
        )

    # Emit APPROVAL_DECIDED event
    emit_approval_decided(
        approval_id=approval_id,
        rule=rule,
        actor=actor,
        decision=decision,
        reason=reason,
    )

    if decision == "reject":
        # Reject the action
        result = registry.reject_action(
            action_id=action.action_id,
            rejected_by=actor.actor_id,
            reason=reason,
            rejector_roles=actor.roles,
        )

        if not result.success and result.error_code not in ["LEGACY_WRITE_DENIED"]:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": result.error_code,
                    "message": result.error_message,
                },
            )

        return {
            "status": "decided",
            "approval_id": approval_id,
            "action_id": action.action_id,
            "decision": decision,
            "action_status": "denied",
        }

    else:
        # Approve and complete the action
        result = registry.complete_approved_action(
            action_id=action.action_id,
            approved_by=actor.actor_id,  # GAP 3: actual approver, not requester
            approver_roles=actor.roles,
        )

        if not result.success:
            raise HTTPException(
                status_code=403 if result.denied_by else 500,
                detail={
                    "code": result.error_code,
                    "message": result.error_message,
                    "denied_by": result.denied_by,
                },
            )

        return {
            "status": "decided",
            "approval_id": approval_id,
            "action_id": action.action_id,
            "decision": decision,
            "action_status": "enqueued",
            "outbox_path": result.outbox_path,
        }


async def _handle_generic_approval_decision(
    request: Request,
    approval_id: str,
    rule: Any,
    actor: ActorContext,
    decision: str,
    reason: Optional[str],
    institution_id: Optional[str],
    state_store: Any,
    generic_approval: Dict[str, Any],
) -> Dict[str, Any]:
    """Handle approval decision for generic workflow transition (Expansão 03).

    This handler processes approval decisions for workflow transitions that
    require approval. Uses generic entity access - no hardcoded entity_type checks.

    Args:
        request: FastAPI request object.
        approval_id: The approval ID.
        rule: The approval rule.
        actor: The deciding actor.
        decision: "approve" or "reject".
        reason: Optional decision reason.
        institution_id: Institution ID.
        state_store: State store instance.
        generic_approval: Approval index data with entity info.

    Returns:
        Decision result.

    Raises:
        HTTPException: Various error codes.
    """
    from datetime import datetime, timezone

    entity_type = generic_approval["entity_type"]
    entity_id = generic_approval["entity_id"]
    workflow = generic_approval["workflow"]
    transition = generic_approval["transition"]
    transition_def = generic_approval["transition_def"]
    proposer_id = generic_approval["proposer_id"]

    # SoD check: proposer cannot decide their own approval
    if actor.actor_id == proposer_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APPROVAL_SOD_VIOLATION",
                "message": "Self-approval not allowed: proposer cannot decide their own approval",
            },
        )

    # Verify entity exists (generic accessor)
    entity_data = state_store.get_entity(entity_type, entity_id)
    if entity_data is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ENTITY_NOT_FOUND",
                "message": f"Entity {entity_type}:{entity_id} not found",
            },
        )

    # Emit APPROVAL_DECIDED event
    emit_approval_decided(
        approval_id=approval_id,
        rule=rule,
        actor=actor,
        decision=decision,
        reason=reason,
    )

    now = datetime.now(timezone.utc).isoformat()

    if decision == "reject":
        # Update entity status to REJECTED (generic mutator)
        state_store.update_entity(entity_type, entity_id, {
            "status": "REJECTED",
            "updated_at": now,
        })

        # Emit CASE_REJECTED
        emit_case_rejected(entity_id, actor, institution_id=institution_id)

        return {
            "status": "decided",
            "approval_id": approval_id,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "decision": decision,
            "case_status": "REJECTED",
        }

    # Handle approve - build updates from transition effects
    updates: Dict[str, Any] = {"updated_at": now}

    to_state = transition_def.get("to")
    effects = transition_def.get("effects", [])

    # Apply to_state if specified
    if to_state:
        updates["status"] = to_state

    # Apply effects
    for effect in effects:
        effect_type = effect.get("type")
        if effect_type == "set_state":
            updates["status"] = effect.get("value")
        elif effect_type == "set_field":
            field_name = effect.get("field")
            field_value = effect.get("value")
            if field_name:
                updates[field_name] = field_value
        elif effect_type == "bump_version":
            current_version = entity_data.get("version", 0)
            updates["version"] = current_version + effect.get("value", 1)

    # Set applied_at if transitioning to APPLIED state
    if updates.get("status") == "APPLIED":
        updates["applied_at"] = now

    # Persist updates (generic mutator)
    state_store.update_entity(entity_type, entity_id, updates)

    # Emit CASE_COMMITTED
    emit_case_committed(entity_id, actor, institution_id=institution_id)

    return {
        "status": "decided",
        "approval_id": approval_id,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "workflow": workflow,
        "transition": transition,
        "decision": decision,
        "case_status": "COMMITTED",
    }
