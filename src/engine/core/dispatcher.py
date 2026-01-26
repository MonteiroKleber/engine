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
    CONTENT_REPORT_NOT_FOUND,
    CHAT_REPORT_NOT_FOUND,
    CHAT_BLOCK_NOT_FOUND,
    MODERATION_ACTION_NOT_FOUND,
    WORKFLOW_NOT_FOUND,
    WORKFLOW_TRANSITION_NOT_FOUND,
    WORKFLOW_TRANSITION_CONFLICT,
    WORKFLOW_EFFECT_INVALID,
    WORKFLOW_GUARD_UNSUPPORTED,
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
# Maps bind.entity -> (create_method, read_method, list_method, delete_method, id_param, not_found_code)
ENTITY_CONFIG = {
    "Expense": {
        "create_method": "create_expense",
        "read_method": "get_expense",
        "list_method": None,  # Not supported
        "delete_method": None,  # Not supported
        "id_param": "expense_id",
        "not_found_code": EXPENSE_NOT_FOUND,
    },
    "Ticket": {
        "create_method": "create_ticket",
        "read_method": "get_ticket",
        "list_method": None,  # Not supported
        "delete_method": None,  # Not supported
        "id_param": "ticket_id",
        "not_found_code": TICKET_NOT_FOUND,
    },
    # Bazari MVP entities
    "ContentReport": {
        "create_method": "create_content_report",
        "read_method": "get_content_report",
        "list_method": "list_content_reports",
        "delete_method": None,  # Not supported
        "id_param": "report_id",
        "not_found_code": CONTENT_REPORT_NOT_FOUND,
    },
    "ChatReport": {
        "create_method": "create_chat_report",
        "read_method": "get_chat_report",
        "list_method": "list_chat_reports",
        "delete_method": None,  # Not supported
        "id_param": "report_id",
        "not_found_code": CHAT_REPORT_NOT_FOUND,
    },
    "ChatBlock": {
        "create_method": "create_chat_block",
        "read_method": "get_chat_block",
        "list_method": "list_chat_blocks",
        "delete_method": "delete_chat_block",
        "id_param": "block_id",
        "not_found_code": CHAT_BLOCK_NOT_FOUND,
    },
    "ModerationAction": {
        "create_method": "create_moderation_action",
        "read_method": "get_moderation_action",
        "list_method": "list_moderation_actions",
        "delete_method": None,  # Not supported
        "id_param": "action_id",
        "not_found_code": MODERATION_ACTION_NOT_FOUND,
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

    elif entity_type == "ContentReport":
        entity = state_store.create_content_report(
            report_id=entity_id,
            content_type=request_body.get("content_type", ""),
            content_id=request_body.get("content_id", ""),
            reporter_id=actor.actor_id,
            reason=request_body.get("reason", ""),
            description=request_body.get("description", ""),
        )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.report_id,
                "content_type": entity.content_type,
                "content_id": entity.content_id,
                "reporter_id": entity.reporter_id,
                "reason": entity.reason,
                "status": entity.status,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:create:{entity_type}",
        )

    elif entity_type == "ChatReport":
        entity = state_store.create_chat_report(
            report_id=entity_id,
            message_id=request_body.get("message_id", ""),
            thread_id=request_body.get("thread_id", ""),
            reporter_id=actor.actor_id,
            reason=request_body.get("reason", ""),
            description=request_body.get("description", ""),
        )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.report_id,
                "message_id": entity.message_id,
                "thread_id": entity.thread_id,
                "reporter_id": entity.reporter_id,
                "reason": entity.reason,
                "status": entity.status,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:create:{entity_type}",
        )

    elif entity_type == "ChatBlock":
        entity = state_store.create_chat_block(
            block_id=entity_id,
            blocker_profile_id=actor.actor_id,
            blocked_profile_id=request_body.get("blocked_profile_id", ""),
        )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.block_id,
                "blocker_profile_id": entity.blocker_profile_id,
                "blocked_profile_id": entity.blocked_profile_id,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:create:{entity_type}",
        )

    elif entity_type == "ModerationAction":
        entity = state_store.create_moderation_action(
            action_id=entity_id,
            target_type=request_body.get("target_type", ""),
            target_id=request_body.get("target_id", ""),
            action_type=request_body.get("action_type", ""),
            proposed_by=actor.actor_id,
            report_id=request_body.get("report_id"),
            reason=request_body.get("reason"),
        )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.action_id,
                "target_type": entity.target_type,
                "target_id": entity.target_id,
                "action_type": entity.action_type,
                "proposed_by": entity.proposed_by,
                "report_id": entity.report_id,
                "status": entity.status,
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

    elif entity_type == "ContentReport":
        entity = state_store.get_content_report(entity_id)
        if not entity:
            return DispatchResult(
                status_code=404,
                response_body={
                    "code": not_found_code,
                    "message": "Content report not found",
                },
                error_code=not_found_code,
                step=f"DISPATCHER:read:{entity_type}",
            )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.report_id,
                "content_type": entity.content_type,
                "content_id": entity.content_id,
                "reporter_id": entity.reporter_id,
                "reason": entity.reason,
                "status": entity.status,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:read:{entity_type}",
        )

    elif entity_type == "ChatReport":
        entity = state_store.get_chat_report(entity_id)
        if not entity:
            return DispatchResult(
                status_code=404,
                response_body={
                    "code": not_found_code,
                    "message": "Chat report not found",
                },
                error_code=not_found_code,
                step=f"DISPATCHER:read:{entity_type}",
            )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.report_id,
                "message_id": entity.message_id,
                "thread_id": entity.thread_id,
                "reporter_id": entity.reporter_id,
                "reason": entity.reason,
                "status": entity.status,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:read:{entity_type}",
        )

    elif entity_type == "ChatBlock":
        entity = state_store.get_chat_block(entity_id)
        if not entity:
            return DispatchResult(
                status_code=404,
                response_body={
                    "code": not_found_code,
                    "message": "Chat block not found",
                },
                error_code=not_found_code,
                step=f"DISPATCHER:read:{entity_type}",
            )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.block_id,
                "blocker_profile_id": entity.blocker_profile_id,
                "blocked_profile_id": entity.blocked_profile_id,
                "created_at": entity.created_at,
                "actor_id": actor.actor_id,
            },
            step=f"DISPATCHER:read:{entity_type}",
        )

    elif entity_type == "ModerationAction":
        entity = state_store.get_moderation_action(entity_id)
        if not entity:
            return DispatchResult(
                status_code=404,
                response_body={
                    "code": not_found_code,
                    "message": "Moderation action not found",
                },
                error_code=not_found_code,
                step=f"DISPATCHER:read:{entity_type}",
            )

        return DispatchResult(
            status_code=200,
            response_body={
                "id": entity.action_id,
                "target_type": entity.target_type,
                "target_id": entity.target_id,
                "action_type": entity.action_type,
                "proposed_by": entity.proposed_by,
                "report_id": entity.report_id,
                "status": entity.status,
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


async def dispatch_list(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
) -> DispatchResult:
    """Execute a list operation via dispatcher.

    Pipeline:
    1. RBAC gate (permission)
    2. List from state store
    3. Return entities

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID (None for single mode).
        actor: Actor context with roles.
        operation: Operation from registry.

    Returns:
        DispatchResult with status and response containing list.
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
    list_method = config.get("list_method")

    # Check if list is supported for this entity
    if not list_method:
        return DispatchResult(
            status_code=501,
            response_body={
                "code": "LIST_NOT_SUPPORTED",
                "message": f"List not supported for entity type: {entity_type}",
            },
            error_code="LIST_NOT_SUPPORTED",
            step="DISPATCHER:validate_list",
        )

    case_id = f"{entity_type.lower()}:list"

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

    # 3. List Entities
    method = getattr(state_store, list_method)
    entities = method()

    # Convert entities to dict format
    items = []
    for entity in entities:
        items.append(entity.to_dict())

    return DispatchResult(
        status_code=200,
        response_body={
            "items": items,
            "count": len(items),
        },
        step=f"DISPATCHER:list:{entity_type}",
    )


async def dispatch_delete(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    path_params: Dict[str, str],
) -> DispatchResult:
    """Execute a delete operation via dispatcher.

    Pipeline:
    1. RBAC gate (permission)
    2. Delete from state store
    3. Return success or 404

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
    delete_method = config.get("delete_method")
    id_param = config["id_param"]
    not_found_code = config["not_found_code"]

    # Check if delete is supported for this entity
    if not delete_method:
        return DispatchResult(
            status_code=501,
            response_body={
                "code": "DELETE_NOT_SUPPORTED",
                "message": f"Delete not supported for entity type: {entity_type}",
            },
            error_code="DELETE_NOT_SUPPORTED",
            step="DISPATCHER:validate_delete",
        )

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

    # 3. Delete Entity
    method = getattr(state_store, delete_method)
    deleted = method(entity_id)

    if not deleted:
        return DispatchResult(
            status_code=404,
            response_body={
                "code": not_found_code,
                "message": f"{entity_type} not found",
            },
            error_code=not_found_code,
            step=f"DISPATCHER:delete:{entity_type}",
        )

    return DispatchResult(
        status_code=200,
        response_body={
            "deleted": True,
            "id": entity_id,
        },
        step=f"DISPATCHER:delete:{entity_type}",
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

    # If this approval_id is for a generic workflow transition (Expansão 03),
    # decide it using the generic approval index stored in the state store.
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

    generic_approval = state_store.get_generic_approval(approval_id)
    if generic_approval:
        entity_type = generic_approval.get("entity_type")
        entity_id = generic_approval.get("entity_id")
        transition_def = generic_approval.get("transition_def") or {}
        approvals_def = transition_def.get("approvals") or {}

        approver_roles = approvals_def.get("roles") or approvals_def.get("approver_roles") or []
        quorum = approvals_def.get("quorum", 1) or 1

        synthetic_rule = ApprovalRule(
            rule_name=rule_name,
            trigger_api="POST /approvals/{approval_id}/decide",
            approver_roles=list(approver_roles),
            quorum=int(quorum),
        )

        # Role gate
        if not can_actor_decide(actor, synthetic_rule):
            return DispatchResult(
                status_code=403,
                response_body={
                    "code": "APPROVAL_FORBIDDEN",
                    "message": "Forbidden",
                },
                error_code="APPROVAL_FORBIDDEN",
                step="DISPATCHER:check_role",
            )

        # SoD: requester != decider
        proposer_id = generic_approval.get("proposer_id")
        if proposer_id and proposer_id == actor.actor_id:
            return DispatchResult(
                status_code=409,
                response_body={
                    "code": "APPROVAL_SOD_VIOLATION",
                    "message": "SoD violation: proposer cannot decide",
                },
                error_code="APPROVAL_SOD_VIOLATION",
                step="DISPATCHER:sod_check",
            )

        # Load target entity data
        if not isinstance(entity_id, str) or not entity_id:
            return DispatchResult(
                status_code=404,
                response_body={
                    "code": CASE_NOT_FOUND,
                    "message": "Case not found",
                },
                error_code=CASE_NOT_FOUND,
                step="DISPATCHER:generic:find_entity",
            )

        if entity_type == "ModerationAction":
            entity_data = state_store._data["moderation_actions"].get(entity_id)
        elif entity_type == "ContentReport":
            entity_data = state_store._data["content_reports"].get(entity_id)
        elif entity_type == "ChatReport":
            entity_data = state_store._data["chat_reports"].get(entity_id)
        else:
            entity_data = None

        if not isinstance(entity_data, dict):
            return DispatchResult(
                status_code=404,
                response_body={
                    "code": CASE_NOT_FOUND,
                    "message": "Case not found",
                },
                error_code=CASE_NOT_FOUND,
                step="DISPATCHER:generic:find_entity",
            )

        now = datetime.now(timezone.utc).isoformat()

        # Decide
        if decision == "reject":
            updated_data = dict(entity_data)
            updated_data["status"] = STATUS_REJECTED
            updated_data.pop("approval_id", None)
            # keep deterministic versioning
            current_version = updated_data.get("version", 0)
            if not isinstance(current_version, int):
                current_version = 0
            updated_data["version"] = current_version + 1
            updated_data["updated_at"] = now
        else:
            effects = transition_def.get("effects") or []
            # On approval, materialize the transition "to" state even if the
            # transition_def has no explicit set_state effect.
            to_state = transition_def.get("to")
            base_data = dict(entity_data)
            if isinstance(to_state, str) and to_state:
                base_data["status"] = to_state

            success, error_msg, updated_data = _apply_effects(base_data, effects)
            if not success:
                return DispatchResult(
                    status_code=400,
                    response_body={
                        "code": WORKFLOW_EFFECT_INVALID,
                        "message": error_msg,
                    },
                    error_code=WORKFLOW_EFFECT_INVALID,
                    step="DISPATCHER:generic:effects",
                )
            updated_data.pop("approval_id", None)
            updated_data["updated_at"] = now

        # Persist
        if entity_type == "ModerationAction":
            state_store._data["moderation_actions"][entity_id] = updated_data
        elif entity_type == "ContentReport":
            state_store._data["content_reports"][entity_id] = updated_data
        elif entity_type == "ChatReport":
            state_store._data["chat_reports"][entity_id] = updated_data
        state_store._save()

        emit_approval_decided(
            approval_id=approval_id,
            rule=synthetic_rule,
            actor=actor,
            decision=decision,
            reason=reason,
        )

        return DispatchResult(
            status_code=200,
            response_body={
                "status": "decided",
                "approval_id": approval_id,
                "entity_id": entity_id,
                "decision": decision,
                "case_status": STATUS_COMMITTED if decision == "approve" else STATUS_REJECTED,
            },
            step="DISPATCHER:decide:generic",
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

    # Get expense (Finance path)
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


# =============================================================================
# Dispatcher v2: Transition Support (Expansão 02)
# =============================================================================


def _validate_guard(guard: Any) -> tuple[bool, Optional[str]]:
    """Validate transition guard.

    Only literal true/false is supported in this phase.

    Args:
        guard: Guard value from transition definition.

    Returns:
        Tuple of (is_valid, error_message).
        If guard is None or literal true, returns (True, None).
        If guard is literal false, returns (False, "Guard evaluated to false").
        If guard is not a literal bool, returns (False, error_message).
    """
    if guard is None:
        # No guard = always allowed
        return True, None

    if guard is True:
        return True, None

    if guard is False:
        return False, "Guard evaluated to false"

    # Any other value (expression, string, etc.) is unsupported
    return False, f"Guard expression not supported: {guard}"


def _is_literal_value(value: Any) -> bool:
    """Check if value is a supported literal (string, int, bool, or null)."""
    if value is None:
        return True
    if isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, float):
        # Allow float as well (int check won't catch floats)
        return True
    return False


def _apply_effects(
    entity_data: Dict[str, Any],
    effects: list,
) -> tuple[bool, Optional[str], Dict[str, Any]]:
    """Apply transition effects to entity data.

    Supported effects (subset):
    - set_state("<STATE>")
    - set_field("<field>", <literal>)
    - bump_version(1)

    Args:
        entity_data: Current entity data dict.
        effects: List of effect definitions.

    Returns:
        Tuple of (success, error_message, updated_data).
    """
    updated = dict(entity_data)

    for effect in effects:
        if not isinstance(effect, dict):
            return False, f"Invalid effect format: {effect}", entity_data

        effect_type = effect.get("type")

        if effect_type == "set_state":
            new_state = effect.get("value")
            if not isinstance(new_state, str):
                return False, f"set_state requires string value: {new_state}", entity_data
            updated["status"] = new_state

        elif effect_type == "set_field":
            field_name = effect.get("field")
            field_value = effect.get("value")

            if not isinstance(field_name, str):
                return False, f"set_field requires string field name: {field_name}", entity_data

            if not _is_literal_value(field_value):
                return False, f"set_field only supports literal values, got: {type(field_value).__name__}", entity_data

            # Check for unsupported dynamic values
            if isinstance(field_value, str) and field_value in ("now()", "__NOW__"):
                return False, f"Dynamic value '{field_value}' not supported in this phase", entity_data

            updated[field_name] = field_value

        elif effect_type == "bump_version":
            increment = effect.get("value", 1)
            if increment != 1:
                return False, f"bump_version only supports increment of 1, got: {increment}", entity_data
            current_version = updated.get("version", 0)
            if not isinstance(current_version, int):
                current_version = 0
            updated["version"] = current_version + 1

        else:
            return False, f"Unsupported effect type: {effect_type}", entity_data

    return True, None, updated


async def dispatch_transition(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    path_params: Dict[str, str],
    request_body: Optional[Dict[str, Any]] = None,
) -> DispatchResult:
    """Execute a transition operation via dispatcher.

    Pipeline:
    1. Validate entity type
    2. RBAC gate (permission)
    3. Load entity from state store (404 if not found)
    4. Validate workflow/transition exist in bind
    5. Validate guard (only true/false literal)
    6. Validate current state matches transition 'from' (if specified)
    7. Apply effects in order
    8. Persist updated entity
    9. Return result

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID (None for single mode).
        actor: Actor context with roles.
        operation: Operation from registry.
        path_params: Extracted path parameters (must contain entity ID).
        request_body: Optional request body (may contain transition params).

    Returns:
        DispatchResult with status and response.
    """
    permission = operation.permission
    endpoint_sig = operation.endpoint_sig
    bind = operation.bind or {}

    entity_type = bind.get("entity")
    workflow_name = bind.get("workflow")
    transition_name = bind.get("transition")

    # Validate entity type is supported
    if not entity_type or entity_type not in ENTITY_CONFIG:
        return DispatchResult(
            status_code=500,
            response_body={
                "code": "ENTITY_TYPE_UNSUPPORTED",
                "message": f"Unsupported entity type: {entity_type}",
            },
            error_code="ENTITY_TYPE_UNSUPPORTED",
            step="DISPATCHER:validate_entity",
        )

    # Validate workflow is specified
    if not workflow_name:
        return DispatchResult(
            status_code=400,
            response_body={
                "code": WORKFLOW_NOT_FOUND,
                "message": "Workflow not specified in operation bind",
            },
            error_code=WORKFLOW_NOT_FOUND,
            step="DISPATCHER:validate_workflow",
        )

    # Validate transition is specified
    if not transition_name:
        return DispatchResult(
            status_code=400,
            response_body={
                "code": WORKFLOW_TRANSITION_NOT_FOUND,
                "message": "Transition not specified in operation bind",
            },
            error_code=WORKFLOW_TRANSITION_NOT_FOUND,
            step="DISPATCHER:validate_transition",
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

    # 2. Policy PRE Gate
    payload = request_body or {}
    policy_result: PolicyEvalResult = evaluate_policies(
        phase="pre",
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
        payload=payload,
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
        payload=payload,
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

    # 6. Load Entity
    read_method = config.get("read_method")
    if not read_method:
        return DispatchResult(
            status_code=500,
            response_body={
                "code": "ENTITY_READ_UNSUPPORTED",
                "message": f"Read not supported for entity type: {entity_type}",
            },
            error_code="ENTITY_READ_UNSUPPORTED",
            step="DISPATCHER:validate_read",
        )

    entity = getattr(state_store, read_method)(entity_id)
    if not entity:
        return DispatchResult(
            status_code=404,
            response_body={
                "code": not_found_code,
                "message": f"{entity_type} not found",
            },
            error_code=not_found_code,
            step=f"DISPATCHER:transition:{entity_type}",
        )

    # 7. Get transition definition from bind
    transition_def = bind.get("transition_def", {})
    guard = transition_def.get("guard")
    from_state = transition_def.get("from")
    to_state = transition_def.get("to")
    effects = transition_def.get("effects", [])

    # 8. Validate guard
    guard_ok, guard_error = _validate_guard(guard)
    if guard_error and guard is not True and guard is not False and guard is not None:
        # Non-literal guard expression
        return DispatchResult(
            status_code=400,
            response_body={
                "code": WORKFLOW_GUARD_UNSUPPORTED,
                "message": guard_error,
            },
            error_code=WORKFLOW_GUARD_UNSUPPORTED,
            step=f"DISPATCHER:transition:{transition_name}:guard",
        )

    if not guard_ok:
        return DispatchResult(
            status_code=409,
            response_body={
                "code": WORKFLOW_TRANSITION_CONFLICT,
                "message": guard_error or "Guard condition not met",
            },
            error_code=WORKFLOW_TRANSITION_CONFLICT,
            step=f"DISPATCHER:transition:{transition_name}:guard",
        )

    # 9. Validate current state matches 'from' (if specified)
    entity_data = entity.to_dict()
    current_status = entity_data.get("status")

    if from_state and current_status != from_state:
        return DispatchResult(
            status_code=409,
            response_body={
                "code": WORKFLOW_TRANSITION_CONFLICT,
                "message": f"Current state '{current_status}' does not match expected 'from' state '{from_state}'",
                "current_state": current_status,
                "expected_from": from_state,
            },
            error_code=WORKFLOW_TRANSITION_CONFLICT,
            step=f"DISPATCHER:transition:{transition_name}:from_state",
        )

    # 10. Check if approval is required for this transition
    approvals_def = transition_def.get("approvals")
    if approvals_def:
        # Approval required - create pending approval instead of applying effects
        approval_id = generate_approval_id()
        now = datetime.now(timezone.utc).isoformat()

        # Update entity status to PENDING_APPROVAL and store approval_id
        entity_data["status"] = "PENDING_APPROVAL"
        entity_data["approval_id"] = approval_id
        entity_data["updated_at"] = now

        # Persist entity with pending status
        if entity_type == "ModerationAction":
            state_store._data["moderation_actions"][entity_id] = entity_data
        elif entity_type == "ContentReport":
            state_store._data["content_reports"][entity_id] = entity_data
        elif entity_type == "ChatReport":
            state_store._data["chat_reports"][entity_id] = entity_data
        else:
            return DispatchResult(
                status_code=500,
                response_body={
                    "code": "ENTITY_TYPE_UNSUPPORTED",
                    "message": f"Approval not supported for entity type: {entity_type}",
                },
                error_code="ENTITY_TYPE_UNSUPPORTED",
                step=f"DISPATCHER:transition:{transition_name}:approval",
            )

        # Index the approval for later lookup
        state_store.index_generic_approval(
            approval_id=approval_id,
            entity_type=entity_type,
            entity_id=entity_id,
            workflow=workflow_name,
            transition=transition_name,
            transition_def=transition_def,
            proposer_id=actor.actor_id,
        )
        state_store._save()

        # Create a synthetic ApprovalRule for emitting events
        approval_rule_name = f"{workflow_name}.{transition_name}"
        synthetic_rule = ApprovalRule(
            rule_name=approval_rule_name,
            trigger_api=endpoint_sig,
            approver_roles=approvals_def.get("approver_roles", []),
            quorum=approvals_def.get("quorum", 1),
        )

        # Emit APPROVAL_REQUESTED event
        emit_approval_requested(
            approval_id=approval_id,
            rule=synthetic_rule,
            actor=actor,
            payload_sha256="",  # No payload hash for transitions
        )

        # Return 202 with pending_approval
        return DispatchResult(
            status_code=202,
            response_body={
                "status": "pending_approval",
                "approval_id": approval_id,
                "id": entity_id,
                "workflow": workflow_name,
                "transition": transition_name,
                "previous_status": current_status,
            },
            step=f"DISPATCHER:transition:{workflow_name}:{transition_name}:approval_requested",
        )

    # 11. Build effects list
    # If to_state is specified in transition_def, add set_state effect
    all_effects = []
    if to_state:
        all_effects.append({"type": "set_state", "value": to_state})
    all_effects.extend(effects)

    # 11. Apply effects
    if all_effects:
        success, error_msg, updated_data = _apply_effects(entity_data, all_effects)
        if not success:
            return DispatchResult(
                status_code=400,
                response_body={
                    "code": WORKFLOW_EFFECT_INVALID,
                    "message": error_msg,
                },
                error_code=WORKFLOW_EFFECT_INVALID,
                step=f"DISPATCHER:transition:{transition_name}:effects",
            )
    else:
        updated_data = entity_data

    # 12. Persist updated entity
    # Use the appropriate update method based on entity type
    now = datetime.now(timezone.utc).isoformat()
    updated_data["updated_at"] = now

    # Update in state store raw data
    if entity_type == "ContentReport":
        state_store._data["content_reports"][entity_id] = updated_data
        state_store._save()
    elif entity_type == "ChatReport":
        state_store._data["chat_reports"][entity_id] = updated_data
        state_store._save()
    elif entity_type == "ModerationAction":
        state_store._data["moderation_actions"][entity_id] = updated_data
        state_store._save()
    elif entity_type == "Expense":
        state_store._data["expenses"][entity_id] = updated_data
        state_store._save()
    elif entity_type == "Ticket":
        state_store._data["tickets"][entity_id] = updated_data
        state_store._save()
    else:
        return DispatchResult(
            status_code=500,
            response_body={
                "code": "ENTITY_UPDATE_UNSUPPORTED",
                "message": f"Update not supported for entity type: {entity_type}",
            },
            error_code="ENTITY_UPDATE_UNSUPPORTED",
            step="DISPATCHER:transition:persist",
        )

    # 13. Return success
    return DispatchResult(
        status_code=200,
        response_body={
            "id": entity_id,
            "workflow": workflow_name,
            "transition": transition_name,
            "previous_status": current_status,
            "status": updated_data.get("status"),
            "updated_at": updated_data.get("updated_at"),
            "entity": updated_data,
        },
        step=f"DISPATCHER:transition:{workflow_name}:{transition_name}",
    )
