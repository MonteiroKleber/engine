"""Pipeline API Router."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine.ise.release import verify_admin_token
from engine.ise import errors as ise_errors
from engine.pipeline.orchestrator import (
    run_pipeline,
    build_pipeline,
    PipelineResult,
    PIPELINE_TEXT_REQUIRED,
    PIPELINE_BUNDLE_NAME_REQUIRED,
    PIPELINE_ENGINE_SAFE_MODE,
    PIPELINE_VERIFY_FAILED,
    PIPELINE_DEPLOY_UNAVAILABLE,
)
from engine.pipeline.exporter import (
    export_bundle_zip,
    get_zip_path,
    PIPELINE_RUN_NOT_FOUND,
    PIPELINE_BUNDLE_NOT_FOUND,
    PIPELINE_EXPORT_FAILED,
    PIPELINE_DOWNLOAD_NOT_FOUND,
)
from engine.pipeline.registry import (
    get_registry,
    reset_registry,
    DEV_RUNS_REGISTRY_UNAVAILABLE,
)
from engine.pipeline.cleanup import (
    cleanup_dev_runs,
    DEV_RUNS_CLEANUP_FAILED,
)
from engine.pipeline.run_detail import (
    get_run_detail,
    DEV_RUN_NOT_FOUND,
    DEV_RUN_TRACE_NOT_FOUND,
    DEV_RUN_IDL_NOT_FOUND,
)
from engine.pipeline.diff import (
    diff_runs,
    RUN_DIFF_TOO_LARGE,
)


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class AnswerItem(BaseModel):
    """An answer to a gap question."""
    question_id: str
    value: Any


class PipelineDeployRequest(BaseModel):
    """Request for pipeline deploy."""
    text: str = Field(..., min_length=1, description="Natural language policy text")
    bundle_name: str = Field(..., min_length=1, description="Name for the bundle")
    target: str = Field(default="production", description="Deployment target")
    answers: Optional[List[AnswerItem]] = Field(
        None,
        description="Answers to gap questions (null if first run)",
    )


class PipelineDeployResponse(BaseModel):
    """Response from pipeline deploy."""
    status: str
    bundle_name: Optional[str] = None
    release_id: Optional[str] = None

    # Hashes for traceability
    hash_sir: Optional[str] = None
    hash_draft: Optional[str] = None
    hash_idl_final: Optional[str] = None
    bundle_hash: Optional[str] = None

    # NEEDS_ANSWERS data
    gaps: Optional[List[Dict[str, Any]]] = None
    sir: Optional[Dict[str, Any]] = None
    draft_idl: Optional[Dict[str, Any]] = None

    # Policy gaps specific data (subset of gaps that are policy-related)
    policy_gaps: Optional[List[Dict[str, Any]]] = None
    answers_template: Optional[Dict[str, Any]] = None

    # Error data
    error: Optional[Dict[str, Any]] = None


@router.post("/deploy", response_model=PipelineDeployResponse)
async def pipeline_deploy(
    request: PipelineDeployRequest,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> PipelineDeployResponse:
    """Execute full NL to Deploy pipeline.

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Pipeline stages:
    1. compile_sir - Extract SIR from natural language
    2. compile_draft - Generate draft IDL from SIR
    3. detect_gaps - Find missing information
    4. If gaps and no answers -> return NEEDS_ANSWERS
    5. If answers -> apply_answers, detect_gaps again
    6. If still gaps -> return NEEDS_ANSWERS
    7. finalize - Produce final IDL
    8. compile_release - Compile and deploy bundle
    9. Return DEPLOYED or ROLLED_BACK
    """
    # Auth check
    if not verify_admin_token(x_admin_token):
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": ise_errors.ISE_ADMIN_UNAUTHORIZED,
                "message": "Invalid or missing admin token",
            },
        )

    # Convert answers to dict list
    answers_list = None
    if request.answers is not None:
        answers_list = [
            {"question_id": a.question_id, "value": a.value}
            for a in request.answers
        ]

    # Run pipeline
    result = run_pipeline(
        text=request.text,
        bundle_name=request.bundle_name,
        target=request.target,
        answers=answers_list,
    )

    # Handle hard lock institutional errors with proper HTTP codes
    if result.error_code == PIPELINE_ENGINE_SAFE_MODE:
        raise HTTPException(
            status_code=503,
            detail={
                "code": result.error_code,
                "message": result.error_message,
            },
        )
    elif result.error_code == PIPELINE_VERIFY_FAILED:
        raise HTTPException(
            status_code=409,
            detail={
                "code": result.error_code,
                "message": result.error_message,
                "exit_code": result.exit_code,
            },
        )
    elif result.error_code == PIPELINE_DEPLOY_UNAVAILABLE:
        raise HTTPException(
            status_code=500,
            detail={
                "code": result.error_code,
                "message": result.error_message,
            },
        )

    # Convert result to response
    return PipelineDeployResponse(**result.to_dict())


class PipelineBuildRequest(BaseModel):
    """Request for pipeline build (sandbox, no deploy)."""
    text: str = Field(..., min_length=1, description="Natural language policy text")
    bundle_name: str = Field(..., min_length=1, description="Name for the bundle")
    answers: Optional[List[AnswerItem]] = Field(
        None,
        description="Answers to gap questions (null if first run)",
    )


class PipelineBuildResponse(BaseModel):
    """Response from pipeline build."""
    status: str
    bundle_name: Optional[str] = None
    run_id: Optional[str] = None
    bundle_path: Optional[str] = None

    # Hashes for traceability
    hash_sir: Optional[str] = None
    hash_draft: Optional[str] = None
    hash_idl_final: Optional[str] = None
    bundle_hash: Optional[str] = None

    # NEEDS_ANSWERS data
    gaps: Optional[List[Dict[str, Any]]] = None
    sir: Optional[Dict[str, Any]] = None
    draft_idl: Optional[Dict[str, Any]] = None

    # Policy gaps specific data (subset of gaps that are policy-related)
    policy_gaps: Optional[List[Dict[str, Any]]] = None
    answers_template: Optional[Dict[str, Any]] = None

    # Error data
    error: Optional[Dict[str, Any]] = None


@router.post("/build", response_model=PipelineBuildResponse)
async def pipeline_build(
    request: PipelineBuildRequest,
) -> PipelineBuildResponse:
    """Build bundle in sandbox (no deploy).

    This endpoint is PUBLIC - no admin token required.
    Builds bundle in bundles/dev-runs/<run_id>/<bundle_name>/.
    Does NOT call compile_release, deploy scripts, or subprocess.

    Pipeline stages:
    1. compile_sir - Extract SIR from natural language
    2. compile_draft - Generate draft IDL from SIR
    3. detect_gaps - Find missing information
    4. If gaps and no answers -> return NEEDS_ANSWERS
    5. If answers -> apply_answers, detect_gaps again
    6. If still gaps -> return NEEDS_ANSWERS
    7. finalize - Produce final IDL
    8. compile_bundle - Compile bundle to dev-runs sandbox
    9. Return BUILT with run_id and bundle_path
    """
    # Validate required fields (Pydantic handles min_length but be explicit)
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": PIPELINE_TEXT_REQUIRED,
                "message": "Text is required",
            },
        )

    if not request.bundle_name or not request.bundle_name.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": PIPELINE_BUNDLE_NAME_REQUIRED,
                "message": "Bundle name is required",
            },
        )

    # Convert answers to dict list
    answers_list = None
    if request.answers is not None:
        answers_list = [
            {"question_id": a.question_id, "value": a.value}
            for a in request.answers
        ]

    # Run build pipeline
    result = build_pipeline(
        text=request.text,
        bundle_name=request.bundle_name,
        answers=answers_list,
    )

    # Convert result to response
    return PipelineBuildResponse(**result.to_dict())


class PipelineExportRequest(BaseModel):
    """Request for bundle export."""
    run_id: str = Field(..., min_length=1, description="UUID of the build run")
    bundle_name: str = Field(..., min_length=1, description="Name of the bundle")


class PipelineExportResponse(BaseModel):
    """Response from bundle export."""
    status: str
    zip_path: Optional[str] = None
    zip_sha256: Optional[str] = None
    download_url: Optional[str] = None
    error: Optional[Dict[str, Any]] = None


@router.post("/build/export", response_model=PipelineExportResponse)
async def pipeline_export(
    request: PipelineExportRequest,
) -> PipelineExportResponse:
    """Export sandbox bundle to deterministic ZIP.

    This endpoint is PUBLIC - no admin token required.
    Creates ZIP at: bundles/dev-runs/<run_id>/exports/<bundle_name>.zip

    The ZIP is deterministic:
    - Paths are sorted alphabetically
    - Timestamp is fixed to 1980-01-01 00:00:00
    - Permissions are fixed to 0644
    - Uses ZIP_DEFLATED compression

    Returns download_url for subsequent GET request.
    """
    result = export_bundle_zip(
        run_id=request.run_id,
        bundle_name=request.bundle_name,
    )

    if not result.success:
        # Map error codes to HTTP status
        status_map = {
            PIPELINE_RUN_NOT_FOUND: 404,
            PIPELINE_BUNDLE_NOT_FOUND: 404,
            PIPELINE_EXPORT_FAILED: 500,
        }
        status_code = status_map.get(result.error_code, 500)

        raise HTTPException(
            status_code=status_code,
            detail={
                "code": result.error_code,
                "message": result.error_message,
            },
        )

    return PipelineExportResponse(**result.to_dict())


@router.get("/build/download")
async def pipeline_download(
    run_id: str = Query(..., min_length=1, description="UUID of the build run"),
    bundle_name: str = Query(..., min_length=1, description="Name of the bundle"),
) -> FileResponse:
    """Download exported ZIP file.

    This endpoint is PUBLIC - no admin token required.
    Returns the ZIP file with Content-Disposition attachment header.

    Must call POST /pipeline/build/export first to create the ZIP.
    """
    zip_path = get_zip_path(run_id=run_id, bundle_name=bundle_name)

    if zip_path is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": PIPELINE_DOWNLOAD_NOT_FOUND,
                "message": f"ZIP not found for run {run_id}, bundle {bundle_name}. Call /pipeline/build/export first.",
            },
        )

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"{bundle_name}.zip",
        headers={
            "Content-Disposition": f'attachment; filename="{bundle_name}.zip"',
        },
    )


class DevRunItem(BaseModel):
    """A dev run item."""
    run_id: str
    bundle_name: str
    created_at: str
    bundle_path: Optional[str] = None
    has_zip: bool = False
    zip_path: Optional[str] = None
    zip_sha256: Optional[str] = None
    deleted: bool = False
    deleted_at: Optional[str] = None


class PipelineRunsResponse(BaseModel):
    """Response from list runs."""
    runs: List[DevRunItem]
    total: int


@router.get("/build/runs", response_model=PipelineRunsResponse)
async def pipeline_list_runs(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum runs to return"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> PipelineRunsResponse:
    """List dev runs (admin only).

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.
    Returns non-deleted runs, newest first.
    """
    # Auth check
    if not verify_admin_token(x_admin_token):
        raise HTTPException(
            status_code=401,
            detail={
                "code": ise_errors.ISE_ADMIN_UNAUTHORIZED,
                "message": "Invalid or missing admin token",
            },
        )

    try:
        registry = get_registry()
        runs = registry.list_active_runs(limit=limit)

        return PipelineRunsResponse(
            runs=[DevRunItem(**r.to_dict()) for r in runs],
            total=len(runs),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": DEV_RUNS_REGISTRY_UNAVAILABLE,
                "message": f"Failed to read registry: {e}",
            },
        )


class PipelineCleanupRequest(BaseModel):
    """Request for cleanup."""
    dry_run: bool = Field(default=False, description="If true, simulate without deleting")


class PipelineCleanupResponse(BaseModel):
    """Response from cleanup."""
    success: bool
    dry_run: bool
    deleted_run_ids: List[str]
    deleted_paths: List[str]
    ttl_expired_count: int
    max_runs_exceeded_count: int
    error: Optional[Dict[str, Any]] = None


@router.post("/build/cleanup", response_model=PipelineCleanupResponse)
async def pipeline_cleanup(
    request: PipelineCleanupRequest,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> PipelineCleanupResponse:
    """Cleanup dev runs (admin only).

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Cleanup policy:
    1. Delete runs older than ENGINE_DEV_RUNS_TTL_HOURS (default 24)
    2. Delete oldest runs to stay under ENGINE_DEV_RUNS_MAX_RUNS (default 200)

    If dry_run=true, simulates deletion and returns what would be deleted.
    """
    # Auth check
    if not verify_admin_token(x_admin_token):
        raise HTTPException(
            status_code=401,
            detail={
                "code": ise_errors.ISE_ADMIN_UNAUTHORIZED,
                "message": "Invalid or missing admin token",
            },
        )

    result = cleanup_dev_runs(dry_run=request.dry_run)

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail={
                "code": result.error_code or DEV_RUNS_CLEANUP_FAILED,
                "message": result.error_message or "Cleanup failed",
            },
        )

    return PipelineCleanupResponse(**result.to_dict())


class TraceItem(BaseModel):
    """Trace information for a run."""
    run_id: str
    bundle_name: str
    sir_sha256: str
    draft_sha256: str
    final_idl_sha256: str
    bundle_manifest_sha256: str
    contract_ledger_sha256: str


class RunDetailResponse(BaseModel):
    """Response from run detail endpoint."""
    success: bool
    run_id: Optional[str] = None
    bundle_name: Optional[str] = None
    created_at: Optional[str] = None
    bundle_path: Optional[str] = None
    has_zip: bool = False
    zip_path: Optional[str] = None
    zip_sha256: Optional[str] = None
    deleted: bool = False
    deleted_at: Optional[str] = None
    trace: Optional[TraceItem] = None
    error: Optional[Dict[str, Any]] = None


@router.get("/build/runs/{run_id}", response_model=RunDetailResponse)
async def pipeline_run_detail(
    run_id: str,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> RunDetailResponse:
    """Get detailed information about a specific run (admin only).

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.
    Returns registry info combined with trace.json data.
    """
    # Auth check
    if not verify_admin_token(x_admin_token):
        raise HTTPException(
            status_code=401,
            detail={
                "code": ise_errors.ISE_ADMIN_UNAUTHORIZED,
                "message": "Invalid or missing admin token",
            },
        )

    result = get_run_detail(run_id=run_id)

    if not result.success:
        # Map error codes to HTTP status
        status_map = {
            DEV_RUN_NOT_FOUND: 404,
            DEV_RUN_TRACE_NOT_FOUND: 404,
        }
        status_code = status_map.get(result.error_code, 500)

        raise HTTPException(
            status_code=status_code,
            detail={
                "code": result.error_code,
                "message": result.error_message,
            },
        )

    # Convert to response
    response_data = result.to_dict()
    if result.trace:
        response_data["trace"] = TraceItem(**result.trace.to_dict())

    return RunDetailResponse(**response_data)


class RunDiffResponse(BaseModel):
    """Response from run diff endpoint."""
    success: bool
    run_a: Optional[str] = None
    run_b: Optional[str] = None
    diff: Optional[str] = None
    is_identical: bool = False
    size_a: int = 0
    size_b: int = 0
    error: Optional[Dict[str, Any]] = None


@router.get("/build/diff", response_model=RunDiffResponse)
async def pipeline_run_diff(
    run_a: str = Query(..., min_length=1, description="UUID of the first run"),
    run_b: str = Query(..., min_length=1, description="UUID of the second run"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> RunDiffResponse:
    """Generate unified diff between two runs' IDL files (admin only).

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.
    Returns unified diff of idl_final.idl files.

    Size limit: 256KB per IDL file.
    """
    # Auth check
    if not verify_admin_token(x_admin_token):
        raise HTTPException(
            status_code=401,
            detail={
                "code": ise_errors.ISE_ADMIN_UNAUTHORIZED,
                "message": "Invalid or missing admin token",
            },
        )

    result = diff_runs(run_a=run_a, run_b=run_b)

    if not result.success:
        # Map error codes to HTTP status
        status_map = {
            DEV_RUN_IDL_NOT_FOUND: 404,
            RUN_DIFF_TOO_LARGE: 413,
        }
        status_code = status_map.get(result.error_code, 500)

        raise HTTPException(
            status_code=status_code,
            detail={
                "code": result.error_code,
                "message": result.error_message,
            },
        )

    return RunDiffResponse(**result.to_dict())
