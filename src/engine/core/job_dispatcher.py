"""Job Dispatcher - Handlers for job-based operations.

Implements dispatch functions for job.request, job.enqueue, and job.get bind.kinds.
All job types are defined in the IDL bundle - no hardcoded product logic here.

Jobs First-Class Spec: docs/specs/core-generico/02-jobs-first-class.md
Dispatcher v3 Spec: docs/specs/core-generico/05-dispatcher-v3.md
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from engine.core.actor_context import ActorContext
from engine.core.approvals import (
    get_approvals_policy,
    emit_approval_requested_generic,
    ApprovalTarget,
    ApprovalTargetKind,
    JobRef,
)
from engine.core.errors import (
    POLICY_DENIED,
    MANDATE_DENIED,
    AUTONOMY_INSUFFICIENT,
)
from engine.core.job_store import Job, JobState, get_job_store
from engine.core.ledger import get_ledger_for_institution
from engine.core.mandates import evaluate_mandates, emit_mandate_decision, MandateEvalResult
from engine.core.policy import evaluate_policies, emit_policy_decision, PolicyEvalResult
from engine.core.autonomy import evaluate_autonomy, emit_autonomy_evaluated, AutonomyEvalResult
from engine.core.data_root import get_institution_root
from engine.core.rbac import gate_rbac
from engine.core.operations import Operation
from engine.legacy_bridge.connectors.outbox_connector import OutboxConnector


# Ledger event types for jobs
JOB_REQUESTED = "JOB_REQUESTED"
JOB_ENQUEUED = "JOB_ENQUEUED"
JOB_APPROVAL_REQUESTED = "JOB_APPROVAL_REQUESTED"


@dataclass
class JobDispatchResult:
    """Result of a job dispatch operation."""

    status_code: int
    response_body: Dict[str, Any]
    error_code: Optional[str] = None
    step: Optional[str] = None


def _compute_params_sha256(params: Dict[str, Any]) -> str:
    """Compute SHA256 hash of params for audit trail."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _try_load_result_json_from_legacy_results(
    institution_id: str,
    dept_id: Optional[str],
    job_id: str,
    expected_result_sha256: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Best-effort: load result payload from legacy_bridge/results/{job_id}.json.

    This is a compatibility bridge for UI rendering. It allows `job.get` to return
    `result_json` even if older runtime reports did not persist it into JobStore.
    """
    if not expected_result_sha256:
        return None

    inst_root = get_institution_root(institution_id)
    if dept_id:
        result_path = inst_root / "depts" / dept_id / "legacy_bridge" / "results" / f"{job_id}.json"
    else:
        result_path = inst_root / "legacy_bridge" / "results" / f"{job_id}.json"

    if not result_path.exists():
        return None

    try:
        raw_bytes = result_path.read_bytes()
        raw_sha = hashlib.sha256(raw_bytes).hexdigest()
        data = json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        return None

    if raw_sha != expected_result_sha256 and data.get("result_sha256") != expected_result_sha256:
        return None

    result = data.get("result")
    return result if isinstance(result, dict) else None


def _emit_rbac_decision(
    actor: ActorContext,
    permission: str,
    allowed: bool,
    case_id: str,
    step: str,
    dept_id: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> None:
    """Emit RBAC_DECISION event to ledger."""
    ledger = get_ledger_for_institution(institution_id)
    if not ledger:
        return

    ledger.append(
        event_type="RBAC_DECISION",
        tenant_id=institution_id or "",
        actor_id=actor.actor_id,
        actor_roles=actor.roles,
        case_id=case_id,
        step=step,
        dept_id=dept_id,
        payload={
            "decision": "allow" if allowed else "deny",
            "permission": permission,
            "allowed": allowed,
            "code": "RBAC_ALLOWED" if allowed else "RBAC_DENIED",
        },
    )


def _emit_job_requested(
    job: Job,
    actor: ActorContext,
    institution_id: str,
    dept_id: Optional[str],
    endpoint_sig: str,
) -> None:
    """Emit JOB_REQUESTED event to ledger."""
    ledger = get_ledger_for_institution(institution_id)
    if not ledger:
        return

    ledger.append(
        event_type=JOB_REQUESTED,
        tenant_id=institution_id,
        actor_id=actor.actor_id,
        actor_roles=actor.roles,
        case_id=job.job_id,
        step=f"JOB:request:{job.job_type}",
        dept_id=dept_id,
        payload={
            "job_id": job.job_id,
            "job_type": job.job_type,
            "endpoint_sig": endpoint_sig,
            "params_sha256": job.params_sha256,
            "state": job.state,
            "approval_id": job.approval_id,
        },
    )


def _emit_job_enqueued(
    job: Job,
    actor: ActorContext,
    institution_id: str,
    dept_id: Optional[str],
    outbox_path: str,
    outbox_sha256: str,
) -> None:
    """Emit JOB_ENQUEUED event to ledger."""
    ledger = get_ledger_for_institution(institution_id)
    if not ledger:
        return

    ledger.append(
        event_type=JOB_ENQUEUED,
        tenant_id=institution_id,
        actor_id=actor.actor_id,
        actor_roles=actor.roles,
        case_id=job.job_id,
        step=f"JOB:enqueue:{job.job_type}",
        dept_id=dept_id,
        payload={
            "job_id": job.job_id,
            "job_type": job.job_type,
            "outbox_path": outbox_path,
            "outbox_sha256": outbox_sha256,
        },
    )


async def dispatch_job_request(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    request_body: Dict[str, Any],
    path_params: Optional[Dict[str, str]] = None,
) -> JobDispatchResult:
    """Create a job request.

    Pipeline:
    1. RBAC gate (permission from operation)
    2. Policy PRE gate (endpoint_sig, payload)
    3. Mandates PRE gate (endpoint_sig, actor, payload)
    4. Autonomy PRE gate (endpoint_sig)
    5. Check if approval rule exists for endpoint_sig
    6. Create job in JobStore
    7. If approval required: mark pending_approval, return 202
    8. If safe: mark requested (ready for enqueue), return 201

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID (None for single mode).
        actor: Actor context with roles.
        operation: Operation from registry.
        request_body: Parsed request body (job params).
        path_params: Extracted path parameters.

    Returns:
        JobDispatchResult with created job info.
    """
    permission = operation.permission
    endpoint_sig = operation.endpoint_sig

    # Extract job_type from operation bind or endpoint
    # Format: POST /personal/files/list -> job_type = "files.list" (from operation_id or bind)
    bind = operation.bind or {}
    job_type = bind.get("job_type") or operation.operation_id or endpoint_sig

    params = request_body
    params_sha256 = _compute_params_sha256(params)
    case_id = f"job:{job_type}"

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
        return JobDispatchResult(
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
        payload=params,
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
        return JobDispatchResult(
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
        payload=params,
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
        return JobDispatchResult(
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
        tenant_id=institution_id,
        actor=actor,
        dept_id=dept_id,
        phase="pre",
        endpoint_sig=endpoint_sig,
        case_id=case_id,
        result=autonomy_result,
    )

    if autonomy_result.decision != "allow":
        return JobDispatchResult(
            status_code=403,
            response_body={
                "code": AUTONOMY_INSUFFICIENT,
                "message": "Autonomy limit exceeded",
                "reason": autonomy_result.reason,
            },
            error_code=AUTONOMY_INSUFFICIENT,
            step=f"AUTONOMY_GATE:pre:{endpoint_sig}",
        )

    # 5. Check if approval rule exists for endpoint_sig
    policy = get_approvals_policy(dept_id)
    rule = policy.get_rule_for_api(endpoint_sig) if policy else None
    requires_approval = rule is not None

    # 6. Create job in JobStore
    job_store = get_job_store(institution_id, dept_id)

    import uuid as uuid_module
    approval_id = str(uuid_module.uuid4()) if requires_approval else None

    initial_state = JobState.PENDING_APPROVAL.value if requires_approval else JobState.REQUESTED.value

    job = job_store.create_job(
        job_type=job_type,
        params=params,
        requested_by=actor.actor_id,
        params_sha256=params_sha256,
        approval_id=approval_id,
        mandate_id=mandate_result.mandate_id,
        initial_state=initial_state,
    )

    # Emit JOB_REQUESTED event
    _emit_job_requested(
        job=job,
        actor=actor,
        institution_id=institution_id,
        dept_id=dept_id,
        endpoint_sig=endpoint_sig,
    )

    # 7. If approval required, emit APPROVAL_REQUESTED and return 202
    if requires_approval:
        # Emit APPROVAL_REQUESTED with generic job_ref target
        job_ref = JobRef(job_id=job.job_id, action="enqueue")
        target = ApprovalTarget(kind=ApprovalTargetKind.JOB, ref=job_ref)

        emit_approval_requested_generic(
            approval_id=approval_id,
            rule_name=rule.rule_name if rule else f"job.{job_type}",
            target=target,
            actor=actor,
            approver_roles=rule.approver_roles if rule else [],
            payload_sha256=params_sha256,
            tenant_id=institution_id,
        )

        return JobDispatchResult(
            status_code=202,
            response_body={
                "status": "pending_approval",
                "job_id": job.job_id,
                "job_type": job_type,
                "approval_id": approval_id,
                "message": "Job requires approval before execution",
            },
            step=f"JOB:pending_approval:{job_type}",
        )

    # 8. Safe job - return 201 (ready for enqueue)
    return JobDispatchResult(
        status_code=201,
        response_body={
            "status": "requested",
            "job_id": job.job_id,
            "job_type": job_type,
            "message": "Job created, ready for enqueue",
        },
        step=f"JOB:requested:{job_type}",
    )


async def dispatch_job_enqueue(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    path_params: Dict[str, str],
    request_body: Optional[Dict[str, Any]] = None,
) -> JobDispatchResult:
    """Enqueue a job to the outbox for runtime execution.

    Writes the job payload to the outbox directory. The runtime agent
    polls the outbox and executes jobs.

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID.
        actor: Actor context.
        operation: Operation from registry.
        path_params: Must contain job_id.
        request_body: Optional additional params.

    Returns:
        JobDispatchResult.
    """
    job_id = path_params.get("job_id")
    if not job_id:
        return JobDispatchResult(
            status_code=400,
            response_body={
                "code": "PATH_PARAM_MISSING",
                "message": "Missing required path parameter: job_id",
            },
            error_code="PATH_PARAM_MISSING",
            step="JOB:enqueue:validate",
        )

    job_store = get_job_store(institution_id, dept_id)
    job = job_store.get_job(job_id)

    if not job:
        return JobDispatchResult(
            status_code=404,
            response_body={
                "code": "JOB_NOT_FOUND",
                "message": f"Job {job_id} not found",
            },
            error_code="JOB_NOT_FOUND",
            step="JOB:enqueue:lookup",
        )

    # Check job state - must be requested or approved
    if job.state not in (JobState.REQUESTED.value, JobState.APPROVED.value):
        return JobDispatchResult(
            status_code=409,
            response_body={
                "code": "JOB_STATE_INVALID",
                "message": f"Job cannot be enqueued in state '{job.state}'",
                "current_state": job.state,
            },
            error_code="JOB_STATE_INVALID",
            step="JOB:enqueue:validate_state",
        )

    # Write to outbox
    outbox = OutboxConnector(institution_id, dept_id)

    # Create outbox payload
    outbox_data = job.to_outbox_dict()
    outbox_json = json.dumps(outbox_data, sort_keys=True, separators=(",", ":"))
    outbox_sha256 = hashlib.sha256(outbox_json.encode("utf-8")).hexdigest()

    # Write file
    outbox_dir = outbox.outbox_root
    outbox_dir.mkdir(parents=True, exist_ok=True)
    outbox_file = outbox_dir / f"{job_id}.json"
    outbox_file.write_text(outbox_json, encoding="utf-8")

    outbox_path = str(outbox_file.relative_to(outbox_dir.parent.parent))

    # Update job state
    now = datetime.now(timezone.utc).isoformat()
    job_store.update_job_state(
        job_id=job_id,
        state=JobState.ENQUEUED.value,
        enqueued_at=now,
    )

    # Emit JOB_ENQUEUED event
    _emit_job_enqueued(
        job=job,
        actor=actor,
        institution_id=institution_id,
        dept_id=dept_id,
        outbox_path=outbox_path,
        outbox_sha256=outbox_sha256,
    )

    return JobDispatchResult(
        status_code=200,
        response_body={
            "status": "enqueued",
            "job_id": job_id,
            "job_type": job.job_type,
            "outbox_path": outbox_path,
            "outbox_sha256": outbox_sha256,
        },
        step=f"JOB:enqueued:{job.job_type}",
    )


async def dispatch_job_get(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    path_params: Dict[str, str],
) -> JobDispatchResult:
    """Get job status and result.

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID.
        actor: Actor context.
        operation: Operation from registry.
        path_params: Must contain job_id.

    Returns:
        JobDispatchResult with job details.
    """
    permission = operation.permission

    # RBAC gate
    rbac_allowed = gate_rbac(permission, actor, dept_id=dept_id)
    if not rbac_allowed:
        return JobDispatchResult(
            status_code=403,
            response_body={
                "code": "RBAC_DENIED",
                "message": f"Permission '{permission}' denied",
            },
            error_code="RBAC_DENIED",
            step=f"RBAC:{permission}",
        )

    job_id = path_params.get("job_id")
    if not job_id:
        return JobDispatchResult(
            status_code=400,
            response_body={
                "code": "PATH_PARAM_MISSING",
                "message": "Missing required path parameter: job_id",
            },
            error_code="PATH_PARAM_MISSING",
            step="JOB:get:validate",
        )

    job_store = get_job_store(institution_id, dept_id)
    job = job_store.get_job(job_id)

    if not job:
        return JobDispatchResult(
            status_code=404,
            response_body={
                "code": "JOB_NOT_FOUND",
                "message": f"Job {job_id} not found",
            },
            error_code="JOB_NOT_FOUND",
            step="JOB:get:lookup",
        )

    # Backfill result_json from legacy results file if missing (compat).
    # New runtime reports persist result_json via runtime.py, but older jobs may not.
    if job.result_json is None:
        expected_result_sha256: Optional[str] = None
        if job.artifacts and len(job.artifacts) >= 3:
            expected_result_sha256 = job.artifacts[2]

        loaded = _try_load_result_json_from_legacy_results(
            institution_id=institution_id,
            dept_id=dept_id,
            job_id=job.job_id,
            expected_result_sha256=expected_result_sha256,
        )
        if loaded is not None:
            job_store.update_job_state(job_id=job.job_id, state=job.state, result_json=loaded)
            job = job_store.get_job(job.job_id) or job

    return JobDispatchResult(
        status_code=200,
        response_body={
            "job_id": job.job_id,
            "job_type": job.job_type,
            "state": job.state,
            "params": job.params,
            "requested_by": job.requested_by,
            "approval_id": job.approval_id,
            "approved_by": job.approved_by,
            "result_json": job.result_json,
            "result_summary": job.result_summary,
            "exit_code": job.exit_code,
            "artifacts": job.artifacts,
            "created_at": job.created_at,
            "enqueued_at": job.enqueued_at,
            "executed_at": job.executed_at,
            "version": job.version,
        },
        step=f"JOB:get:{job.job_type}",
    )


async def dispatch_job_approval_decide(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    approval_id: str,
    decision: str,
    reason: Optional[str] = None,
) -> JobDispatchResult:
    """Handle approval decision for a job.

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID.
        actor: Actor context (must have approval permission).
        approval_id: Approval UUID.
        decision: "approve" or "reject".
        reason: Optional reason text.

    Returns:
        JobDispatchResult.
    """
    job_store = get_job_store(institution_id, dept_id)
    job = job_store.get_job_by_approval_id(approval_id)

    if not job:
        return JobDispatchResult(
            status_code=404,
            response_body={
                "code": "APPROVAL_NOT_FOUND",
                "message": f"No job found with approval_id {approval_id}",
            },
            error_code="APPROVAL_NOT_FOUND",
            step="JOB:approval:lookup",
        )

    if job.state != JobState.PENDING_APPROVAL.value:
        return JobDispatchResult(
            status_code=409,
            response_body={
                "code": "APPROVAL_STATE_INVALID",
                "message": f"Job is not pending approval (state: {job.state})",
            },
            error_code="APPROVAL_STATE_INVALID",
            step="JOB:approval:validate_state",
        )

    # SoD check: proposer cannot decide their own approval
    if actor.actor_id == job.requested_by:
        return JobDispatchResult(
            status_code=403,
            response_body={
                "code": "APPROVAL_SOD_VIOLATION",
                "message": "Self-approval not allowed: proposer cannot decide their own job approval",
            },
            error_code="APPROVAL_SOD_VIOLATION",
            step="JOB:approval:sod",
        )

    now = datetime.now(timezone.utc).isoformat()

    if decision == "approve":
        new_state = JobState.APPROVED.value
        job_store.update_job_state(
            job_id=job.job_id,
            state=new_state,
            approved_by=actor.actor_id,
        )
    else:
        new_state = JobState.REJECTED.value
        job_store.update_job_state(
            job_id=job.job_id,
            state=new_state,
        )

    # Emit APPROVAL_DECIDED event
    ledger = get_ledger_for_institution(institution_id)
    if ledger:
        ledger.append(
            event_type="APPROVAL_DECIDED",
            tenant_id=institution_id,
            actor_id=actor.actor_id,
            actor_roles=actor.roles,
            case_id=job.job_id,
            step=f"JOB:approval:decide:{job.job_type}",
            dept_id=dept_id,
            payload={
                "approval_id": approval_id,
                "job_id": job.job_id,
                "job_type": job.job_type,
                "decision": decision,
                "reason": reason,
                "decided_by": actor.actor_id,
            },
        )

    return JobDispatchResult(
        status_code=200,
        response_body={
            "status": "decided",
            "approval_id": approval_id,
            "job_id": job.job_id,
            "decision": decision,
            "new_state": new_state,
        },
        step=f"JOB:approval:{decision}:{job.job_type}",
    )
