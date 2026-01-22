"""Dispatcher v2 - Generic operation execution via OperationRegistry.

This module provides deterministic execution of operations
based on Operation definitions from the OperationRegistry.

Pipeline for create (bind.kind=create):
1. RBAC gate (permission check)
2. Policy PRE gate (payload validation)
3. Mandates PRE gate (delegation check)
4. Autonomy PRE gate (level check)
5. Persist entity to state store
6. Emit ledger events
7. Return result

Pipeline for read (bind.kind=read):
1. RBAC gate (permission check)
2. Read from state store
3. Return entity or 404

Pipeline for approval_request (creating with approval):
1. All PRE gates (same as create)
2. Check if approval rule exists for endpoint_sig
3. If yes: persist entity + emit APPROVAL_REQUESTED, return 202
4. If no: persist entity normally, return 200

Pipeline for approval_decide (deciding on approval):
1. Validate decision ("approve"/"reject")
2. Find APPROVAL_REQUESTED event
3. Check if already decided
4. Check role can decide
5. SoD check (requester != decider)
6. If approve: POST gates + invariants
7. Update entity status
8. Emit APPROVAL_DECIDED + CASE_COMMITTED/REJECTED
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .actor_context import ActorContext
from .operations import Operation
from .rbac import gate_rbac
from .policy import evaluate_policies, emit_policy_decision, PolicyEvalResult
from .mandates import evaluate_mandates, emit_mandate_decision, MandateEvalResult
from .autonomy import evaluate_autonomy, emit_autonomy_evaluated, AutonomyEvalResult
from .ledger import get_ledger, get_ledger_for_institution
from .dept_context import get_ledger_step_name
from .errors import (
    POLICY_DENIED,
    MANDATE_DENIED,
    AUTONOMY_INSUFFICIENT,
    STATE_STORE_UNAVAILABLE,
    EXPENSE_NOT_FOUND,
    TICKET_NOT_FOUND,
    CASE_NOT_FOUND,
    SOD_VIOLATION,
    SOD_RULE_INVALID,
    INVARIANT_VIOLATION,
    INVARIANT_SCHEMA_INVALID,
)
from .approvals import (
    get_approvals_policy,
    generate_approval_id,
    emit_approval_requested,
    emit_approval_decided,
    compute_payload_sha256,
    get_approval_step_name,
    find_approval_requested,
    is_approval_decided,
    can_actor_decide,
    get_rule_name_from_step,
    ApprovalRule,
)
from .sod import check_sod
from .invariants import validate_expense_invariants
from .state_store import (
    get_state_store,
    STATUS_PENDING_APPROVAL,
    STATUS_COMMITTED,
    STATUS_REJECTED,
)


@dataclass
class DispatchResult:
    """Result of dispatcher execution."""

    status_code: int
    response_body: Dict[str, Any]
    error_code: Optional[str] = None
    step: Optional[str] = None


# Entity type to StateStore method mapping
# Maps bind.entity -> (create_method, read_method, id_param, not_found_code)
ENTITY_CONFIG = {
    "Expense": {
        "create_method": "create_expense",
        "read_method": "get_expense",
        "id_param": "expense_id",
        "not_found_code": EXPENSE_NOT_FOUND,
    },
    "Ticket": {
        "create_method": "create_ticket",
        "read_method": "get_ticket",
        "id_param": "ticket_id",
        "not_found_code": TICKET_NOT_FOUND,
    },
}


def _emit_rbac_decision(
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
    if institution_id:
        ledger = get_ledger_for_institution(institution_id)
    else:
        ledger = get_ledger()

    if ledger:
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


def _generate_entity_id() -> str:
    """Generate a new entity ID (UUID)."""
    return str(uuid.uuid4())


async def dispatch_create(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    request_body: Dict[str, Any],
    path_params: Optional[Dict[str, str]] = None,
) -> DispatchResult:
    """Execute a create operation via dispatcher.

    Pipeline:
    1. RBAC gate (permission)
    2. Policy PRE gate (endpoint_sig, payload)
    3. Mandates PRE gate (endpoint_sig, actor, payload)
    4. Autonomy PRE gate (endpoint_sig)
    5. Persist entity to state store
    6. Return result

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID (None for single mode).
        actor: Actor context with roles.
        operation: Operation from registry.
        request_body: Parsed request body.
        path_params: Extracted path parameters (optional for create).

    Returns:
        DispatchResult with status and response.
    """
    permission = operation.permission
    endpoint_sig = operation.endpoint_sig
    entity_type = operation.bind.get("entity") if operation.bind else None

    # Validate entity type is supported
    if not entity_type or entity_type not in ENTITY_CONFIG:
        return DispatchResult(
            status_code=500,
            response_body={
                "error": f"Unsupported entity type: {entity_type}",
            },
            error_code="ENTITY_TYPE_UNSUPPORTED",
            step="DISPATCHER:validate_entity",
        )

    config = ENTITY_CONFIG[entity_type]
    case_id = entity_type.lower()

    # 1. RBAC Gate
    rbac_allowed = gate_rbac(permission, actor, dept_id=dept_id)
    _emit_rbac_decision(
        actor=actor,
        permission=permission,
        allowed=rbac_allowed,
        case_id=case_id,
        step=f"RBAC:{permission}",
        dept_id=dept_id,
        institution_id=institution_id,
    )

    if not rbac_allowed:
        return DispatchResult(
            status_code=403,
            response_body={
                "code": "RBAC_DENIED",
                "message": f"Permission '{permission}' denied",
            },
            error_code="RBAC_DENIED",
            step=f"RBAC:{permission}",
        )

    # 2. Policy PRE Gate
    policy_result: PolicyEvalResult = evaluate_policies(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        payload=request_body,
        institution_id=institution_id,
    )

    emit_policy_decision(
        phase="pre",
        endpoint_sig=endpoint_sig,
        dept_id=dept_id,
        case_id=case_id,
        actor=actor,
        result=policy_result,
    )

    if not policy_result.allow:
        violation_messages = [v.message for v in policy_result.violations]
        return DispatchResult(
            status_code=403,
            response_body={
                "code": POLICY_DENIED,
                "message": "Policy denied",
                "violations": violation_messages,
            },
            error_code=POLICY_DENIED,
            step=f"POLICY_GATE:pre:{endpoint_sig}",
        )

    # 3. Mandates PRE Gate
    mandate_result: MandateEvalResult = evaluate_mandates(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        actor=actor,
        payload=request_body,
        institution_id=institution_id,
    )

    emit_mandate_decision(
        phase="pre",
        endpoint_sig=endpoint_sig,
        dept_id=dept_id,
        case_id=case_id,
        actor=actor,
        result=mandate_result,
    )

    if not mandate_result.allow:
        violation_messages = [v.message for v in mandate_result.violations]
        return DispatchResult(
            status_code=403,
            response_body={
                "code": MANDATE_DENIED,
                "message": "Mandate denied",
                "mandate_id": mandate_result.mandate_id,
                "violations": violation_messages,
            },
            error_code=MANDATE_DENIED,
            step=f"MANDATE_GATE:pre:{endpoint_sig}",
        )

    # 4. Autonomy PRE Gate
    autonomy_result: AutonomyEvalResult = evaluate_autonomy(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        institution_id=institution_id,
    )

    emit_autonomy_evaluated(
        tenant_id=actor.tenant_id,
        actor=actor,
        dept_id=dept_id,
        phase="pre",
        endpoint_sig=endpoint_sig,
        case_id=case_id,
        result=autonomy_result,
    )

    if autonomy_result.decision == "deny":
        return DispatchResult(
            status_code=403,
            response_body={
                "code": AUTONOMY_INSUFFICIENT,
                "message": "Autonomy level insufficient",
                "current_level": autonomy_result.current_level,
                "required_level": autonomy_result.required_level,
                "rule_id": autonomy_result.rule_id,
                "reason": autonomy_result.reason,
            },
            error_code=AUTONOMY_INSUFFICIENT,
            step=f"AXIOM_AUTONOMY:pre:{endpoint_sig}",
        )

    # 5. Get State Store
    state_store = get_state_store(dept_id, institution_id=institution_id)
    if not state_store:
        return DispatchResult(
            status_code=503,
            response_body={
                "code": STATE_STORE_UNAVAILABLE,
                "message": "State store not available",
            },
            error_code=STATE_STORE_UNAVAILABLE,
            step="DISPATCHER:state_store",
        )

    # 6. Persist Entity
    entity_id = _generate_entity_id()
    now = datetime.now(timezone.utc).isoformat()

    if entity_type == "Expense":
        # Expense requires approval_id - generate one
        import json
        import hashlib

        approval_id = str(uuid.uuid4())
        payload_bytes = json.dumps(request_body).encode("utf-8")
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()

        entity = state_store.create_expense(
            expense_id=entity_id,
            approval_id=approval_id,
            payload_sha256=payload_sha256,
            payload_raw=payload_bytes,
        )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.expense_id,
                "status": entity.status,
                "approval_id": entity.approval_id,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:create:{entity_type}",
        )

    elif entity_type == "Ticket":
        entity = state_store.create_ticket(
            ticket_id=entity_id,
            subject=request_body.get("subject", ""),
            description=request_body.get("description", ""),
            payload_raw=b"",  # Simplified for dispatcher
        )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.ticket_id,
                "status": entity.status,
                "subject": entity.subject,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:create:{entity_type}",
        )

    # Should not reach here due to earlier validation
    return DispatchResult(
        status_code=500,
        response_body={"error": "Unknown entity type"},
        error_code="ENTITY_TYPE_UNSUPPORTED",
    )


async def dispatch_read(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    path_params: Dict[str, str],
) -> DispatchResult:
    """Execute a read operation via dispatcher.

    Pipeline:
    1. RBAC gate (permission)
    2. Read from state store
    3. Return entity or 404

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID (None for single mode).
        actor: Actor context with roles.
        operation: Operation from registry.
        path_params: Extracted path parameters (must contain entity ID).

    Returns:
        DispatchResult with status and response.
    """
    permission = operation.permission
    entity_type = operation.bind.get("entity") if operation.bind else None

    # Validate entity type is supported
    if not entity_type or entity_type not in ENTITY_CONFIG:
        return DispatchResult(
            status_code=500,
            response_body={
                "error": f"Unsupported entity type: {entity_type}",
            },
            error_code="ENTITY_TYPE_UNSUPPORTED",
            step="DISPATCHER:validate_entity",
        )

    config = ENTITY_CONFIG[entity_type]
    id_param = config["id_param"]
    not_found_code = config["not_found_code"]

    # Extract entity ID from path_params
    entity_id = path_params.get(id_param)
    if not entity_id:
        return DispatchResult(
            status_code=400,
            response_body={
                "error": f"Missing required path parameter: {id_param}",
            },
            error_code="PATH_PARAM_MISSING",
            step="DISPATCHER:validate_params",
        )

    case_id = f"{entity_type.lower()}:{entity_id}"

    # 1. RBAC Gate
    rbac_allowed = gate_rbac(permission, actor, dept_id=dept_id)
    _emit_rbac_decision(
        actor=actor,
        permission=permission,
        allowed=rbac_allowed,
        case_id=case_id,
        step=f"RBAC:{permission}",
        dept_id=dept_id,
        institution_id=institution_id,
    )

    if not rbac_allowed:
        return DispatchResult(
            status_code=403,
            response_body={
                "code": "RBAC_DENIED",
                "message": f"Permission '{permission}' denied",
            },
            error_code="RBAC_DENIED",
            step=f"RBAC:{permission}",
        )

    # 2. Get State Store
    state_store = get_state_store(dept_id, institution_id=institution_id)
    if not state_store:
        return DispatchResult(
            status_code=503,
            response_body={
                "code": STATE_STORE_UNAVAILABLE,
                "message": "State store not available",
            },
            error_code=STATE_STORE_UNAVAILABLE,
            step="DISPATCHER:state_store",
        )

    # 3. Read Entity
    if entity_type == "Expense":
        entity = state_store.get_expense(entity_id)
        if not entity:
            return DispatchResult(
                status_code=404,
                response_body={
                    "code": not_found_code,
                    "message": "Expense not found",
                },
                error_code=not_found_code,
                step=f"DISPATCHER:read:{entity_type}",
            )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.expense_id,
                "status": entity.status,
                "approval_id": entity.approval_id,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:read:{entity_type}",
        )

    elif entity_type == "Ticket":
        entity = state_store.get_ticket(entity_id)
        if not entity:
            return DispatchResult(
                status_code=404,
                response_body={
                    "code": not_found_code,
                    "message": "Ticket not found",
                },
                error_code=not_found_code,
                step=f"DISPATCHER:read:{entity_type}",
            )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.ticket_id,
                "status": entity.status,
                "subject": entity.subject,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:read:{entity_type}",
        )

    # Should not reach here
    return DispatchResult(
        status_code=500,
        response_body={"error": "Unknown entity type"},
        error_code="ENTITY_TYPE_UNSUPPORTED",
    )


# =============================================================================
# Dispatcher v2: Approvals Support
# =============================================================================


def _emit_case_committed(
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


def _emit_case_rejected(
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


async def dispatch_approval_request(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    request_body: Dict[str, Any],
    path_params: Optional[Dict[str, str]] = None,
) -> DispatchResult:
    """Execute a create operation with approval support via dispatcher.

    Pipeline:
    1. RBAC gate (permission)
    2. Policy PRE gate (endpoint_sig, payload)
    3. Mandates PRE gate (endpoint_sig, actor, payload)
    4. Autonomy PRE gate (endpoint_sig)
    5. Check if approval rule exists for endpoint_sig
    6. Persist entity to state store
    7. If approval required: emit APPROVAL_REQUESTED, return 202
    8. If no approval: return 200

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID (None for single mode).
        actor: Actor context with roles.
        operation: Operation from registry.
        request_body: Parsed request body.
        path_params: Extracted path parameters (optional for create).

    Returns:
        DispatchResult with status 202 (pending_approval) or 200 (created).
    """
    import json
    import hashlib

    permission = operation.permission
    endpoint_sig = operation.endpoint_sig
    entity_type = operation.bind.get("entity") if operation.bind else None

    # Validate entity type is supported (only Expense supports approvals for now)
    if entity_type != "Expense":
        return DispatchResult(
            status_code=500,
            response_body={
                "error": f"Approval not supported for entity type: {entity_type}",
            },
            error_code="ENTITY_TYPE_UNSUPPORTED",
            step="DISPATCHER:validate_entity",
        )

    case_id = "expense"

    # 1. RBAC Gate
    rbac_allowed = gate_rbac(permission, actor, dept_id=dept_id)
    _emit_rbac_decision(
        actor=actor,
        permission=permission,
        allowed=rbac_allowed,
        case_id=case_id,
        step=f"RBAC:{permission}",
        dept_id=dept_id,
        institution_id=institution_id,
    )

    if not rbac_allowed:
        return DispatchResult(
            status_code=403,
            response_body={
                "code": "RBAC_DENIED",
                "message": f"Permission '{permission}' denied",
            },
            error_code="RBAC_DENIED",
            step=f"RBAC:{permission}",
        )

    # 2. Policy PRE Gate
    policy_result: PolicyEvalResult = evaluate_policies(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        payload=request_body,
        institution_id=institution_id,
    )

    emit_policy_decision(
        phase="pre",
        endpoint_sig=endpoint_sig,
        dept_id=dept_id,
        case_id=case_id,
        actor=actor,
        result=policy_result,
    )

    if not policy_result.allow:
        violation_messages = [v.message for v in policy_result.violations]
        return DispatchResult(
            status_code=403,
            response_body={
                "code": POLICY_DENIED,
                "message": "Policy denied",
                "violations": violation_messages,
            },
            error_code=POLICY_DENIED,
            step=f"POLICY_GATE:pre:{endpoint_sig}",
        )

    # 3. Mandates PRE Gate
    mandate_result: MandateEvalResult = evaluate_mandates(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        actor=actor,
        payload=request_body,
        institution_id=institution_id,
    )

    emit_mandate_decision(
        phase="pre",
        endpoint_sig=endpoint_sig,
        dept_id=dept_id,
        case_id=case_id,
        actor=actor,
        result=mandate_result,
    )

    if not mandate_result.allow:
        violation_messages = [v.message for v in mandate_result.violations]
        return DispatchResult(
            status_code=403,
            response_body={
                "code": MANDATE_DENIED,
                "message": "Mandate denied",
                "mandate_id": mandate_result.mandate_id,
                "violations": violation_messages,
            },
            error_code=MANDATE_DENIED,
            step=f"MANDATE_GATE:pre:{endpoint_sig}",
        )

    # 4. Autonomy PRE Gate
    autonomy_result: AutonomyEvalResult = evaluate_autonomy(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        institution_id=institution_id,
    )

    emit_autonomy_evaluated(
        tenant_id=actor.tenant_id,
        actor=actor,
        dept_id=dept_id,
        phase="pre",
        endpoint_sig=endpoint_sig,
        case_id=case_id,
        result=autonomy_result,
    )

    if autonomy_result.decision == "deny":
        return DispatchResult(
            status_code=403,
            response_body={
                "code": AUTONOMY_INSUFFICIENT,
                "message": "Autonomy level insufficient",
                "current_level": autonomy_result.current_level,
                "required_level": autonomy_result.required_level,
                "rule_id": autonomy_result.rule_id,
                "reason": autonomy_result.reason,
            },
            error_code=AUTONOMY_INSUFFICIENT,
            step=f"AXIOM_AUTONOMY:pre:{endpoint_sig}",
        )

    # 5. Get State Store
    state_store = get_state_store(dept_id, institution_id=institution_id)
    if not state_store:
        return DispatchResult(
            status_code=503,
            response_body={
                "code": STATE_STORE_UNAVAILABLE,
                "message": "State store not available",
            },
            error_code=STATE_STORE_UNAVAILABLE,
            step="DISPATCHER:state_store",
        )

    # 6. Check if approval rule exists for this endpoint
    policy = get_approvals_policy(dept_id)
    rule = policy.get_rule_for_api(endpoint_sig) if policy else None

    # 7. Generate IDs and persist
    entity_id = _generate_entity_id()
    approval_id = generate_approval_id()
    payload_bytes = json.dumps(request_body).encode("utf-8")
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()

    entity = state_store.create_expense(
        expense_id=entity_id,
        approval_id=approval_id,
        payload_sha256=payload_sha256,
        payload_raw=payload_bytes,
    )

    # 8. If approval required, emit APPROVAL_REQUESTED and return 202
    if rule:
        emit_approval_requested(
            approval_id=approval_id,
            rule=rule,
            actor=actor,
            payload_sha256=payload_sha256,
        )

        step = get_approval_step_name(rule.rule_name)
        step = get_ledger_step_name(step, dept_id)

        return DispatchResult(
            status_code=202,
            response_body={
                "status": "pending_approval",
                "expense_id": entity.expense_id,
                "approval_id": approval_id,
                "step": step,
            },
            step=step,
        )

    # No approval required - return 200 directly
    return DispatchResult(
        status_code=200,
        response_body={
            "id": entity.expense_id,
            "status": entity.status,
            "approval_id": entity.approval_id,
            "created_at": entity.created_at,
            "actor_id": actor.actor_id,
        },
        step="DISPATCHER:create:Expense",
    )


async def dispatch_approval_decide(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    approval_id: str,
    decision: str,
    reason: Optional[str] = None,
) -> DispatchResult:
    """Decide on an approval request via dispatcher.

    Pipeline:
    1. Validate decision ("approve"/"reject")
    2. Find APPROVAL_REQUESTED event
    3. Check if already decided
    4. Get rule from step
    5. Check role can decide
    6. SoD check (requester != decider)
    7. If approve:
       - Policy POST gate
       - Mandates POST gate
       - Autonomy POST gate
       - Invariants validation
    8. Update entity status (COMMITTED/REJECTED)
    9. Emit APPROVAL_DECIDED
    10. Emit CASE_COMMITTED or CASE_REJECTED

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID (None for single mode).
        actor: Actor context with roles.
        approval_id: The approval ID to decide on.
        decision: "approve" or "reject".
        reason: Optional reason string.

    Returns:
        DispatchResult with decision result.
    """
    # 1. Validate decision
    if decision not in ("approve", "reject"):
        return DispatchResult(
            status_code=400,
            response_body={
                "code": "APPROVAL_DECISION_INVALID",
                "message": "Decision must be 'approve' or 'reject'",
            },
            error_code="APPROVAL_DECISION_INVALID",
            step="DISPATCHER:validate_decision",
        )

    # 2. Find APPROVAL_REQUESTED event
    requested_event = find_approval_requested(approval_id)
    if not requested_event:
        return DispatchResult(
            status_code=404,
            response_body={
                "code": "APPROVAL_NOT_FOUND",
                "message": "Approval not found",
            },
            error_code="APPROVAL_NOT_FOUND",
            step="DISPATCHER:find_approval",
        )

    # 3. Check if already decided
    if is_approval_decided(approval_id):
        return DispatchResult(
            status_code=409,
            response_body={
                "code": "APPROVAL_ALREADY_DECIDED",
                "message": "Approval already decided",
            },
            error_code="APPROVAL_ALREADY_DECIDED",
            step="DISPATCHER:check_decided",
        )

    # 4. Get rule from step
    step = requested_event.step
    rule_name = get_rule_name_from_step(step)
    if not rule_name:
        return DispatchResult(
            status_code=500,
            response_body={
                "code": "APPROVAL_RULE_ERROR",
                "message": "Could not determine approval rule",
            },
            error_code="APPROVAL_RULE_ERROR",
            step="DISPATCHER:get_rule",
        )

    policy = get_approvals_policy(dept_id)
    if not policy:
        return DispatchResult(
            status_code=500,
            response_body={
                "code": "APPROVAL_POLICY_ERROR",
                "message": "Approvals policy not loaded",
            },
            error_code="APPROVAL_POLICY_ERROR",
            step="DISPATCHER:get_policy",
        )

    rule = policy.get_rule_by_name(rule_name)
    if not rule:
        return DispatchResult(
            status_code=500,
            response_body={
                "code": "APPROVAL_RULE_ERROR",
                "message": f"Approval rule '{rule_name}' not found",
            },
            error_code="APPROVAL_RULE_ERROR",
            step="DISPATCHER:get_rule",
        )

    # 5. Check role can decide
    if not can_actor_decide(actor, rule):
        return DispatchResult(
            status_code=403,
            response_body={
                "code": "APPROVAL_FORBIDDEN",
                "message": "Forbidden",
            },
            error_code="APPROVAL_FORBIDDEN",
            step="DISPATCHER:check_role",
        )

    # 6. SoD check
    sod_ok, sod_error_code, sod_message = check_sod(
        case_id=approval_id,
        step=step,
        actor=actor,
        dept_id=dept_id,
    )
    if not sod_ok:
        if sod_error_code == SOD_RULE_INVALID:
            return DispatchResult(
                status_code=500,
                response_body={
                    "code": sod_error_code,
                    "message": sod_message,
                },
                error_code=sod_error_code,
                step="DISPATCHER:sod_check",
            )
        else:
            # SOD_VIOLATION
            return DispatchResult(
                status_code=409,
                response_body={
                    "code": sod_error_code,
                    "message": sod_message,
                },
                error_code=sod_error_code,
                step="DISPATCHER:sod_check",
            )

    # Get state store and expense
    state_store = get_state_store(dept_id, institution_id=institution_id)
    if not state_store:
        return DispatchResult(
            status_code=503,
            response_body={
                "code": STATE_STORE_UNAVAILABLE,
                "message": "State store not available",
            },
            error_code=STATE_STORE_UNAVAILABLE,
            step="DISPATCHER:state_store",
        )

    expense = state_store.get_expense_by_approval_id(approval_id)
    if not expense:
        return DispatchResult(
            status_code=404,
            response_body={
                "code": CASE_NOT_FOUND,
                "message": "Case not found",
            },
            error_code=CASE_NOT_FOUND,
            step="DISPATCHER:find_expense",
        )

    expense_id = expense.expense_id

    # Handle reject
    if decision == "reject":
        state_store.update_expense_status(expense_id, STATUS_REJECTED)

        emit_approval_decided(
            approval_id=approval_id,
            rule=rule,
            actor=actor,
            decision=decision,
            reason=reason,
        )

        _emit_case_rejected(expense_id, actor, institution_id=institution_id)

        return DispatchResult(
            status_code=200,
            response_body={
                "status": "decided",
                "approval_id": approval_id,
                "expense_id": expense_id,
                "decision": decision,
                "case_status": STATUS_REJECTED,
            },
            step="DISPATCHER:decide:reject",
        )

    # Handle approve - run POST gates and invariants
    payload = state_store.get_expense_payload(expense_id)
    if payload is None:
        payload = {}

    # POST endpoint signature for gates
    post_endpoint_sig = "POST /approvals/{approval_id}/decide"
    context_payload = {
        **payload,
        "_approval_id": approval_id,
        "_decision": decision,
        "_expense_id": expense_id,
    }

    # 7a. Policy POST gate
    policy_result = evaluate_policies(
        phase="post",
        dept_id=dept_id,
        endpoint_sig=post_endpoint_sig,
        payload=context_payload,
        institution_id=institution_id,
    )

    emit_policy_decision(
        phase="post",
        endpoint_sig=post_endpoint_sig,
        dept_id=dept_id,
        case_id=approval_id,
        actor=actor,
        result=policy_result,
    )

    if not policy_result.allow:
        violation_messages = [v.message for v in policy_result.violations]
        return DispatchResult(
            status_code=403,
            response_body={
                "code": POLICY_DENIED,
                "message": "Policy denied",
                "violations": violation_messages,
            },
            error_code=POLICY_DENIED,
            step=f"POLICY_GATE:post:{post_endpoint_sig}",
        )

    # 7b. Mandates POST gate
    mandate_result = evaluate_mandates(
        phase="post",
        dept_id=dept_id,
        endpoint_sig=post_endpoint_sig,
        actor=actor,
        payload=context_payload,
        institution_id=institution_id,
    )

    emit_mandate_decision(
        phase="post",
        endpoint_sig=post_endpoint_sig,
        dept_id=dept_id,
        case_id=approval_id,
        actor=actor,
        result=mandate_result,
    )

    if not mandate_result.allow:
        violation_messages = [v.message for v in mandate_result.violations]
        return DispatchResult(
            status_code=403,
            response_body={
                "code": MANDATE_DENIED,
                "message": "Mandate denied",
                "mandate_id": mandate_result.mandate_id,
                "violations": violation_messages,
            },
            error_code=MANDATE_DENIED,
            step=f"MANDATE_GATE:post:{post_endpoint_sig}",
        )

    # 7c. Autonomy POST gate
    autonomy_result = evaluate_autonomy(
        phase="post",
        dept_id=dept_id,
        endpoint_sig=post_endpoint_sig,
        institution_id=institution_id,
    )

    emit_autonomy_evaluated(
        tenant_id=actor.tenant_id,
        actor=actor,
        dept_id=dept_id,
        phase="post",
        endpoint_sig=post_endpoint_sig,
        case_id=approval_id,
        result=autonomy_result,
    )

    if autonomy_result.decision == "deny":
        return DispatchResult(
            status_code=403,
            response_body={
                "code": AUTONOMY_INSUFFICIENT,
                "message": "Autonomy level insufficient",
                "current_level": autonomy_result.current_level,
                "required_level": autonomy_result.required_level,
                "rule_id": autonomy_result.rule_id,
                "reason": autonomy_result.reason,
            },
            error_code=AUTONOMY_INSUFFICIENT,
            step=f"AXIOM_AUTONOMY:post:{post_endpoint_sig}",
        )

    # 7d. Invariants validation
    inv_ok, inv_error_code, violations = validate_expense_invariants(payload, dept_id)
    if not inv_ok:
        if inv_error_code == INVARIANT_SCHEMA_INVALID:
            return DispatchResult(
                status_code=500,
                response_body={
                    "code": inv_error_code,
                    "message": "Invalid invariant schema",
                    "violations": violations,
                },
                error_code=inv_error_code,
                step="DISPATCHER:invariants",
            )
        else:
            # INVARIANT_VIOLATION
            return DispatchResult(
                status_code=422,
                response_body={
                    "code": inv_error_code,
                    "message": "Invariant violation",
                    "violations": violations,
                },
                error_code=inv_error_code,
                step="DISPATCHER:invariants",
            )

    # 8. Update status to COMMITTED
    state_store.update_expense_status(expense_id, STATUS_COMMITTED)

    # 9. Emit APPROVAL_DECIDED
    emit_approval_decided(
        approval_id=approval_id,
        rule=rule,
        actor=actor,
        decision=decision,
        reason=reason,
    )

    # 10. Emit CASE_COMMITTED
    _emit_case_committed(expense_id, actor, institution_id=institution_id)

    return DispatchResult(
        status_code=200,
        response_body={
            "status": "decided",
            "approval_id": approval_id,
            "expense_id": expense_id,
            "decision": decision,
            "case_status": STATUS_COMMITTED,
        },
        step="DISPATCHER:decide:approve",
    )
