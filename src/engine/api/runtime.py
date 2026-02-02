"""Runtime API endpoints for agent job reporting.

Provides endpoints for external runtime (agent) to report job execution results.
Jobs are created via the outbox mechanism (legacy bridge write-mode).

This is a minimal, read-only reporting endpoint that:
- Does NOT execute anything
- Does NOT bypass approval gates
- Only accepts results for jobs that already exist in the outbox
- Writes evidence to filesystem (outbox-acks) and ledger

GAP 4: Agent Runtime observability - Fase 2.2

Example usage (curl):

    # Report a successful job execution
    curl -X POST http://localhost:8001/runtime/jobs/{job_id}/report \
        -H "Content-Type: application/json" \
        -H "X-Actor-Token: {agent_token}" \
        -H "X-Institution-Id: {institution_id}" \
        -d '{
            "status": "executed",
            "started_at": "2024-01-15T10:00:00Z",
            "finished_at": "2024-01-15T10:05:00Z",
            "exit_code": 0,
            "summary": "Job completed successfully",
            "artifacts": {
                "stdout_sha256": "abc123...",
                "stderr_sha256": "def456...",
                "result_sha256": "ghi789..."
            }
        }'

    # Response (first report):
    # {
    #     "success": true,
    #     "job_id": "{job_id}",
    #     "recorded": true,
    #     "message": "Job result recorded"
    # }

    # Response (subsequent report - idempotent):
    # {
    #     "success": true,
    #     "job_id": "{job_id}",
    #     "recorded": false,
    #     "message": "Job already reported (idempotent)"
    # }
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from engine.core.actor_context import ActorContext
from engine.core.actor_tokens import get_actor_tokens_registry
from engine.core.data_root import get_institution_root
from engine.core.institution_context import resolve_institution_id
from engine.core.ledger import get_ledger_for_institution
from engine.core.errors import (
    ACTOR_TOKEN_REQUIRED,
    ACTOR_TOKEN_INVALID,
)
from engine.legacy_bridge.connectors.outbox_connector import OutboxConnector
from engine.core.job_store import get_job_store, JobState


router = APIRouter(prefix="/runtime", tags=["runtime"])


# Event type for job reporting
RUNTIME_JOB_REPORTED = "RUNTIME_JOB_REPORTED"

# Directory for ack files (relative to institution root)
OUTBOX_ACKS_DIR = "legacy_bridge/outbox-acks"
# Directory for runtime result files written by the external agent (relative to institution root)
OUTBOX_RESULTS_DIR = "legacy_bridge/results"


# Request/Response models
class ArtifactsInfo(BaseModel):
    """SHA256 hashes of execution artifacts."""

    stdout_sha256: Optional[str] = Field(None, description="SHA256 of stdout output")
    stderr_sha256: Optional[str] = Field(None, description="SHA256 of stderr output")
    result_sha256: Optional[str] = Field(None, description="SHA256 of result payload")


class JobReportRequest(BaseModel):
    """Request body for reporting job execution result."""

    status: str = Field(..., description="Execution status: 'executed' or 'failed'")
    started_at: str = Field(..., description="ISO8601 timestamp when execution started")
    finished_at: str = Field(..., description="ISO8601 timestamp when execution finished")
    exit_code: int = Field(0, description="Process exit code (0 = success)")
    summary: str = Field("", description="Short summary (no secrets)", max_length=500)
    artifacts: Optional[ArtifactsInfo] = Field(None, description="SHA256 hashes of artifacts")


class JobReportResponse(BaseModel):
    """Response for job report endpoint."""

    success: bool = Field(..., description="Whether report was recorded")
    job_id: str = Field(..., description="Job ID that was reported")
    recorded: bool = Field(..., description="True if this was the first report")
    message: str = Field("", description="Additional info")


@dataclass
class AckResult:
    """Result of writing ack file."""

    success: bool
    ack_path: Optional[str] = None
    ack_sha256: Optional[str] = None
    already_exists: bool = False
    error: Optional[str] = None


def _get_acks_root(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get the outbox-acks root directory.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        Path to outbox-acks directory.
    """
    inst_root = get_institution_root(institution_id)
    if dept_id:
        return inst_root / "depts" / dept_id / OUTBOX_ACKS_DIR
    return inst_root / OUTBOX_ACKS_DIR


def _get_results_root(institution_id: str, dept_id: Optional[str] = None) -> Path:
    """Get the legacy-bridge results root directory.

    The agent runtime writes result payloads under:
    - var/institutions/{institution_id}/legacy_bridge/results/{job_id}.json
    - var/institutions/{institution_id}/depts/{dept_id}/legacy_bridge/results/{job_id}.json (multi-dept)
    """
    inst_root = get_institution_root(institution_id)
    if dept_id:
        return inst_root / "depts" / dept_id / OUTBOX_RESULTS_DIR
    return inst_root / OUTBOX_RESULTS_DIR


def _compute_json_sha256(value: Any) -> str:
    """Compute SHA256 over a deterministic JSON representation."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_result_json_from_legacy_results(
    institution_id: str,
    dept_id: Optional[str],
    job_id: str,
    expected_result_sha256: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Load result payload from legacy_bridge/results/{job_id}.json.

    This enables Console/UI to read `result_json` via `job.get` without needing
    direct filesystem access to the Engine data root.

    Verification strategy (best-effort, non-fatal):
    - If expected_result_sha256 is provided, accept if it matches:
      - top-level `result_sha256` field (if present), OR
      - SHA256 of deterministic JSON of the full file object, OR
      - SHA256 of deterministic JSON of the nested `result` object, OR
      - SHA256 of raw file bytes.
    - If verification fails or file missing, return None.
    """
    results_root = _get_results_root(institution_id, dept_id)
    result_path = results_root / f"{job_id}.json"
    if not result_path.exists():
        return None

    try:
        raw_bytes = result_path.read_bytes()
    except Exception:
        return None

    # If no expected hash, do not load (avoid unverified payload ingestion)
    if not expected_result_sha256:
        return None

    # Fast path: raw bytes hash
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    if raw_sha == expected_result_sha256:
        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            return None
        result = data.get("result")
        return result if isinstance(result, dict) else None

    # Parse JSON for additional verification methods
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        return None

    # Accept if file carries a declared result_sha256 matching expected
    if data.get("result_sha256") == expected_result_sha256:
        result = data.get("result")
        return result if isinstance(result, dict) else None

    # Deterministic JSON of full object
    try:
        if _compute_json_sha256(data) == expected_result_sha256:
            result = data.get("result")
            return result if isinstance(result, dict) else None
    except Exception:
        pass

    # Deterministic JSON of nested result object
    try:
        result_obj = data.get("result")
        if isinstance(result_obj, dict) and _compute_json_sha256(result_obj) == expected_result_sha256:
            return result_obj
    except Exception:
        pass

    return None


def _write_ack_file(
    institution_id: str,
    dept_id: Optional[str],
    job_id: str,
    report: JobReportRequest,
    actor_id: str,
) -> AckResult:
    """Write ack file to filesystem (idempotent).

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        job_id: Job/action ID.
        report: Report data.
        actor_id: Actor who reported.

    Returns:
        AckResult with path and hash.
    """
    acks_root = _get_acks_root(institution_id, dept_id)
    ack_path = acks_root / f"{job_id}.json"

    # Check if already acked (idempotency)
    if ack_path.exists():
        return AckResult(
            success=True,
            ack_path=str(ack_path.relative_to(get_institution_root(institution_id))),
            already_exists=True,
        )

    try:
        # Ensure directory exists
        acks_root.mkdir(parents=True, exist_ok=True)

        # Build ack data (deterministic)
        ack_data = {
            "schema_version": "1.0",
            "job_id": job_id,
            "reported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "reported_by": actor_id,
            "status": report.status,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "exit_code": report.exit_code,
            "summary": report.summary,
            "artifacts": report.artifacts.model_dump() if report.artifacts else None,
        }

        # Serialize deterministically
        content = json.dumps(ack_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        content_bytes = content.encode("utf-8")

        # Compute hash
        ack_sha256 = hashlib.sha256(content_bytes).hexdigest()

        # Write file
        ack_path.write_bytes(content_bytes)

        return AckResult(
            success=True,
            ack_path=str(ack_path.relative_to(get_institution_root(institution_id))),
            ack_sha256=ack_sha256,
            already_exists=False,
        )

    except Exception as e:
        return AckResult(success=False, error=str(e))


def _emit_job_reported_event(
    institution_id: str,
    dept_id: Optional[str],
    job_id: str,
    report: JobReportRequest,
    actor_id: str,
    ack_sha256: Optional[str],
    requester_user_id: Optional[str] = None,
    requester_user_name: Optional[str] = None,
) -> None:
    """Emit RUNTIME_JOB_REPORTED event to ledger.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        job_id: Job ID.
        report: Report data.
        actor_id: Actor who reported.
        ack_sha256: SHA256 of ack file.
        requester_user_id: Console user ID who initiated the request.
        requester_user_name: Console user name/email for display.
    """
    ledger = get_ledger_for_institution(institution_id)
    if not ledger:
        return

    payload: Dict[str, Any] = {
        "job_id": job_id,
        "status": report.status,
        "exit_code": report.exit_code,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "ack_sha256": ack_sha256,
    }

    # Include requester info if available
    if requester_user_id:
        payload["requester_user_id"] = requester_user_id
    if requester_user_name:
        payload["requester_user_name"] = requester_user_name

    if report.artifacts:
        payload["artifacts"] = report.artifacts.model_dump()

    ledger.append(
        event_type=RUNTIME_JOB_REPORTED,
        tenant_id=institution_id,
        actor_id=actor_id,
        actor_roles=["agent"],
        case_id=job_id,
        step=f"RUNTIME:job.{report.status}",
        payload=payload,
        dept_id=dept_id,
    )


def _verify_agent_token(
    request: Request,
    x_actor_token: Optional[str],
    institution_id: str,
) -> tuple[str, bool]:
    """Verify actor token and check is_agent flag.

    Args:
        request: FastAPI request.
        x_actor_token: Actor token from header.
        institution_id: Institution ID for context.

    Returns:
        Tuple of (actor_id, is_agent).

    Raises:
        HTTPException: 401 if token missing/invalid.
    """
    if not x_actor_token:
        raise HTTPException(
            status_code=401,
            detail={"code": ACTOR_TOKEN_REQUIRED, "message": "X-Actor-Token header required"},
        )

    registry = get_actor_tokens_registry()
    actor_id, roles, valid, error_code, is_agent = registry.verify_token(
        institution_id=institution_id,
        plaintext_token=x_actor_token,
    )

    if not valid:
        raise HTTPException(
            status_code=401,
            detail={"code": error_code or ACTOR_TOKEN_INVALID, "message": "Invalid actor token"},
        )

    return actor_id, is_agent


@router.post("/jobs/{job_id}/report", response_model=JobReportResponse)
async def report_job_result(
    request: Request,
    job_id: str,
    body: JobReportRequest,
    x_actor_token: Optional[str] = Header(None, alias="X-Actor-Token"),
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
    x_dept_id: Optional[str] = Header(None, alias="X-Dept-Id"),
) -> JobReportResponse:
    """Report job execution result.

    Records the result of a job execution by the runtime agent.
    The job must exist in the outbox (source of truth).

    This endpoint is idempotent: re-reporting the same job_id
    will not duplicate the ledger event or ack file.

    Requires:
    - X-Actor-Token: Agent's actor token (must be is_agent=true)
    - X-Institution-Id: Institution UUID

    Args:
        request: FastAPI request.
        job_id: Job/action ID from the outbox.
        body: Report data (status, timestamps, exit_code, artifacts).
        x_actor_token: Actor token header.
        x_institution_id: Institution ID header.
        x_dept_id: Optional department ID header.

    Returns:
        JobReportResponse with success status.

    Raises:
        HTTPException: 401 if auth fails.
        HTTPException: 403 if actor is not an agent.
        HTTPException: 404 if job not found in outbox.
    """
    # Resolve institution ID
    institution_id = resolve_institution_id(request, require_header=True)

    # Verify actor token
    actor_id, is_agent = _verify_agent_token(request, x_actor_token, institution_id)

    # Validate actor is an agent (required for runtime endpoints)
    if not is_agent:
        raise HTTPException(
            status_code=403,
            detail={"code": "AGENT_REQUIRED", "message": "Only agent tokens can report job results"},
        )

    # Validate status value
    if body.status not in ("executed", "failed"):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_STATUS", "message": "Status must be 'executed' or 'failed'"},
        )

    # Check job exists - JobStore is primary source of truth (Jobs First-Class)
    # Fall back to outbox check for backward compatibility with legacy bridge
    job_store = get_job_store(institution_id, x_dept_id)
    job = job_store.get_job(job_id)

    outbox = OutboxConnector(institution_id, x_dept_id)
    job_in_outbox = outbox.action_exists(job_id)

    if not job and not job_in_outbox:
        raise HTTPException(
            status_code=404,
            detail={"code": "JOB_NOT_FOUND", "message": f"Job {job_id} not found in JobStore or outbox"},
        )

    # Extract requester info for audit trail
    # Priority: JobStore (Jobs First-Class) > outbox file (legacy)
    requester_user_id: Optional[str] = None
    requester_user_name: Optional[str] = None

    if job:
        # Jobs First-Class: get requester from JobStore
        requester_user_id = job.requested_by
    elif job_in_outbox:
        # Legacy: try to read from outbox file
        job_file_path = outbox.outbox_root / f"{job_id}.json"
        try:
            job_data = json.loads(job_file_path.read_text(encoding="utf-8"))
            requester_user_id = job_data.get("requester_user_id") or job_data.get("requested_by")
            requester_user_name = job_data.get("requester_user_name")
        except Exception:
            pass  # Requester info is optional

    # Check if already acked (idempotency)
    acks_root = _get_acks_root(institution_id, x_dept_id)
    ack_path = acks_root / f"{job_id}.json"
    if ack_path.exists():
        return JobReportResponse(
            success=True,
            job_id=job_id,
            recorded=False,
            message="Job already reported (idempotent)",
        )

    # Write ack file
    ack_result = _write_ack_file(
        institution_id=institution_id,
        dept_id=x_dept_id,
        job_id=job_id,
        report=body,
        actor_id=actor_id,
    )

    if not ack_result.success:
        raise HTTPException(
            status_code=500,
            detail={"code": "ACK_WRITE_FAILED", "message": ack_result.error},
        )

    # Emit ledger event (only if this is the first report)
    if not ack_result.already_exists:
        _emit_job_reported_event(
            institution_id=institution_id,
            dept_id=x_dept_id,
            job_id=job_id,
            report=body,
            actor_id=actor_id,
            ack_sha256=ack_result.ack_sha256,
            requester_user_id=requester_user_id,
            requester_user_name=requester_user_name,
        )

        # Update JobStore if job exists there (Jobs First-Class integration)
        # Note: job and job_store already resolved above
        if job:
            new_state = JobState.EXECUTED.value if body.status == "executed" else JobState.FAILED.value
            expected_result_sha256 = body.artifacts.result_sha256 if body.artifacts else None
            result_json = _load_result_json_from_legacy_results(
                institution_id=institution_id,
                dept_id=x_dept_id,
                job_id=job_id,
                expected_result_sha256=expected_result_sha256,
            )
            job_store.update_job_state(
                job_id=job_id,
                state=new_state,
                executed_at=body.finished_at,
                result_json=result_json,
                result_summary=body.summary,
                exit_code=body.exit_code,
                artifacts=[
                    body.artifacts.stdout_sha256,
                    body.artifacts.stderr_sha256,
                    body.artifacts.result_sha256,
                ] if body.artifacts else [],
            )

    return JobReportResponse(
        success=True,
        job_id=job_id,
        recorded=not ack_result.already_exists,
        message="Job result recorded" if not ack_result.already_exists else "Already recorded",
    )
