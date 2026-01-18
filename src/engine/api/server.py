"""FastAPI server with /health endpoint."""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from engine.core.runtime_state import runtime_state, RuntimeMode
from engine.core.logging import setup_logging, log_request, get_logger
from engine.core.request_context import set_request_id, get_request_id
from engine.core.security import (
    apply_security_headers,
    get_client_ip,
    parse_cors_origins,
    get_max_body_bytes,
)
from engine.core.rate_limit import get_rate_limiter, reset_rate_limiter
from engine.core.ledger import verify_ledger_file
from engine.loader.load_bundle import load_bundle, get_ledger_path
from engine.loader.safe_mode import enter_safe_mode
from engine.pipeline.cleanup import (
    cleanup_dev_runs,
    should_cleanup_on_boot,
    is_dry_run_on_boot,
)
from engine.core.dept_context import (
    resolve_dept_from_path,
    validate_dept,
    set_request_dept,
)
from engine.core.errors import (
    DEPT_MODE_REQUIRED,
    INSTITUTION_HEADER_REQUIRED,
    INSTITUTION_FROZEN,
    INSTITUTION_EMERGENCY_STOPPED,
    EGE_DRIFT_BLOCKED,
)
from engine.core.ledger import get_ledger
from engine.core.institution_context import (
    resolve_institution_id,
    validate_institution_exists,
    set_request_institution_id,
    DEFAULT_INSTITUTION_ID,
)
from engine.loader.load_bundle import get_bundle_context
from engine.api.finance import router as finance_router
from engine.api.dept_finance import router as dept_finance_router
from engine.api.approvals import router as approvals_router
from engine.api.nl import router as nl_router
from engine.api.ise import router as ise_router
from engine.api.pipeline import router as pipeline_router
from engine.api.contracts import router as contracts_router
from engine.api.admin_institutions import router as admin_institutions_router
from engine.api.admin_institution_config import router as admin_institution_config_router
from engine.api.admin_keys import router as admin_keys_router
from engine.api.admin_ege import router as admin_ege_router
from engine.core.institution_config import (
    get_cached_config,
    reset_config_cache,
)
from engine.core.ege import load_drift_state


# Paths subject to rate limiting
RATE_LIMITED_PATHS = {
    "/finance/expenses",
    "/pipeline/build",
    # /approvals/{id}/decide matched via startswith
}

# Legacy routes that should be blocked when allow_legacy_routes=false in multi-mode
LEGACY_FINANCE_ROUTES = {
    "/finance/expenses",
    "/finance/budgets",
}

# Default actor ID for ledger events when no actor context available (UUID zero)
DEFAULT_ACTOR_ID = "00000000-0000-0000-0000-000000000000"

# Paths that bypass freeze/emergency stop checks
FREEZE_BYPASS_PATHS = {"/health", "/docs", "/openapi.json"}


def _is_rate_limited_path(path: str) -> bool:
    """Check if path should be rate limited."""
    if path in RATE_LIMITED_PATHS:
        return True
    if path.startswith("/approvals/") and path.endswith("/decide"):
        return True
    return False


def _is_legacy_finance_route(path: str) -> bool:
    """Check if path is a legacy finance route."""
    for prefix in LEGACY_FINANCE_ROUTES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _should_bypass_freeze_check(path: str) -> bool:
    """Check if path should bypass freeze/emergency stop checks."""
    if path in FREEZE_BYPASS_PATHS:
        return True
    if path.startswith("/admin/"):
        return True
    return False


def _compute_endpoint_sig(method: str, path: str) -> str | None:
    """Compute canonical endpoint signature for freeze/emergency stop checks.

    Per spec:
    - POST /finance/expenses -> "POST /finance/expenses"
    - POST /approvals/{anything}/decide -> "POST /approvals/{approval_id}/decide"

    Returns None for paths that don't match known endpoints.
    """
    method = method.upper()

    # POST /finance/expenses
    if path == "/finance/expenses" and method == "POST":
        return "POST /finance/expenses"

    # POST /approvals/{approval_id}/decide
    if path.startswith("/approvals/") and path.endswith("/decide") and method == "POST":
        return "POST /approvals/{approval_id}/decide"

    return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup/shutdown."""
    # Setup logging
    setup_logging()
    logger = get_logger()
    logger.info("Starting Libervia Engine...")

    # Verify ledger integrity before accepting traffic
    ledger_path = get_ledger_path()
    if ledger_path.exists():
        logger.info("Verifying ledger integrity...", extra={"path": str(ledger_path)})
        verify_result = verify_ledger_file(ledger_path)

        if not verify_result.ok:
            logger.error(
                "LEDGER_VERIFY_FAILED",
                extra={
                    "event": "LEDGER_VERIFY_FAILED",
                    "code": verify_result.code,
                    "error_detail": verify_result.message,
                    "bad_line": verify_result.bad_line,
                },
            )
            enter_safe_mode(
                verify_result.code or "LEDGER_VERIFY_UNAVAILABLE",
                [verify_result.message or "Ledger verification failed"],
            )
        else:
            logger.info("Ledger verification passed")

    # Startup: load bundle
    load_bundle()
    logger.info("Bundle loaded, engine ready")

    # Cleanup dev-runs on boot if enabled
    if should_cleanup_on_boot():
        dry_run = is_dry_run_on_boot()
        logger.info(
            "DEV_RUNS_CLEANUP_ON_BOOT_START",
            extra={
                "event": "DEV_RUNS_CLEANUP_ON_BOOT_START",
                "dry_run": dry_run,
            },
        )
        try:
            result = cleanup_dev_runs(dry_run=dry_run)
            if result.success:
                logger.info(
                    "DEV_RUNS_CLEANUP_ON_BOOT_OK",
                    extra={
                        "event": "DEV_RUNS_CLEANUP_ON_BOOT_OK",
                        "dry_run": dry_run,
                        "deleted_count": len(result.deleted_run_ids),
                        "ttl_expired_count": result.ttl_expired_count,
                        "max_runs_exceeded_count": result.max_runs_exceeded_count,
                    },
                )
            else:
                logger.error(
                    "DEV_RUNS_CLEANUP_ON_BOOT_FAILED",
                    extra={
                        "event": "DEV_RUNS_CLEANUP_ON_BOOT_FAILED",
                        "error_code": result.error_code,
                        "error_message": result.error_message,
                    },
                )
        except Exception as e:
            logger.error(
                "DEV_RUNS_CLEANUP_ON_BOOT_EXCEPTION",
                extra={
                    "event": "DEV_RUNS_CLEANUP_ON_BOOT_EXCEPTION",
                    "error": str(e),
                },
            )
            # Do NOT enter SAFE_MODE - just log and continue

    yield

    # Shutdown
    logger.info("Shutting down Libervia Engine...")


app = FastAPI(title="Libervia Engine", version="8.1.1", lifespan=lifespan)

# Include routers
app.include_router(finance_router)
app.include_router(dept_finance_router)
app.include_router(approvals_router)
app.include_router(nl_router)
app.include_router(ise_router)
app.include_router(pipeline_router)
app.include_router(contracts_router)
app.include_router(admin_institutions_router)
app.include_router(admin_institution_config_router)
app.include_router(admin_keys_router)
app.include_router(admin_ege_router)

# Setup CORS if ENGINE_CORS_ORIGINS is set
cors_origins = parse_cors_origins()
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Actor-Id", "X-Actor-Roles", "X-Tenant-Id", "X-Institution-Id", "X-Request-Id"],
    )


# Exception handlers for standardized error envelope
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTPException with standard error envelope."""
    # Extract code from detail if it's a dict, otherwise use generic code
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        code = exc.detail["code"]
        message = exc.detail.get("message", str(exc.detail))
        # Build envelope, preserving extra fields like "violations"
        content = {"code": code, "message": message}
        for key, value in exc.detail.items():
            if key not in ("code", "message"):
                content[key] = value
    else:
        # Map status codes to standard codes
        status_to_code = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            413: "REQUEST_TOO_LARGE",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMIT_EXCEEDED",
            500: "INTERNAL_ERROR",
            503: "SERVICE_UNAVAILABLE",
        }
        code = status_to_code.get(exc.status_code, "ERROR")
        message = str(exc.detail) if exc.detail else "An error occurred"
        content = {"code": code, "message": message}

    return JSONResponse(
        status_code=exc.status_code,
        content=content
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with standard error envelope."""
    # Extract first error message
    errors = exc.errors()
    if errors:
        first_error = errors[0]
        loc = ".".join(str(l) for l in first_error.get("loc", []))
        msg = first_error.get("msg", "Validation error")
        message = f"{loc}: {msg}" if loc else msg
    else:
        message = "Validation error"

    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "message": message}
    )


def _is_valid_uuid(value: str) -> bool:
    """Check if string is a valid UUID."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    apply_security_headers(response)
    return response


@app.middleware("http")
async def body_size_middleware(request: Request, call_next):
    """Check body size for POST requests.

    Uses per-institution config if an institution header was provided,
    otherwise falls back to global default from ENGINE_MAX_BODY_BYTES.
    """
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)

                # Resolve institution ID directly from header
                # (can't rely on request.state as institution_middleware runs later)
                institution_id = request.headers.get("X-Institution-Id")
                if not institution_id:
                    institution_id = request.headers.get("X-Tenant-Id")

                if institution_id and institution_id != DEFAULT_INSTITUTION_ID:
                    # Use per-institution config
                    config = get_cached_config(institution_id)
                    max_size = config.limits.max_body_bytes
                else:
                    # No institution header - use global default
                    max_size = get_max_body_bytes()

                if size > max_size:
                    response = JSONResponse(
                        status_code=413,
                        content={
                            "code": "REQUEST_TOO_LARGE",
                            "message": "Request body too large"
                        }
                    )
                    apply_security_headers(response)
                    return response
            except (ValueError, TypeError):
                pass

    return await call_next(request)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to mutating endpoints.

    Uses per-institution rate limit if institution header provided.
    """
    if request.method == "POST" and _is_rate_limited_path(request.url.path):
        client_ip = get_client_ip(request)

        # Resolve institution ID directly from header
        # (can't rely on request.state as institution_middleware runs later)
        institution_id = request.headers.get("X-Institution-Id")
        if not institution_id:
            institution_id = request.headers.get("X-Tenant-Id")

        if institution_id and institution_id != DEFAULT_INSTITUTION_ID:
            config = get_cached_config(institution_id)
            limit_per_minute = config.limits.rate_limit_per_minute
        else:
            limit_per_minute = None  # Use default

        rate_limiter = get_rate_limiter()

        if not rate_limiter.check(client_ip, request.url.path, limit_per_minute):
            response = JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Rate limit exceeded"
                }
            )
            apply_security_headers(response)
            return response

    return await call_next(request)


@app.middleware("http")
async def legacy_routes_middleware(request: Request, call_next):
    """Enforce allow_legacy_routes flag.

    If false and route is legacy /finance/* while in multi-mode,
    return 409 DEPT_MODE_REQUIRED.
    """
    path = request.url.path

    # Only check legacy finance routes
    if not _is_legacy_finance_route(path):
        return await call_next(request)

    # Check if in multi-mode
    bundle_ctx = get_bundle_context()
    if bundle_ctx is None or bundle_ctx.mode != "multi":
        # Not in multi mode - legacy routes are allowed
        return await call_next(request)

    # In multi-mode - check institution config
    # Resolve institution ID directly from header
    institution_id = request.headers.get("X-Institution-Id")
    if not institution_id:
        institution_id = request.headers.get("X-Tenant-Id")
    if not institution_id:
        institution_id = DEFAULT_INSTITUTION_ID

    config = get_cached_config(institution_id)

    if not config.flags.allow_legacy_routes:
        response = JSONResponse(
            status_code=409,
            content={
                "code": DEPT_MODE_REQUIRED,
                "message": "Legacy routes are disabled; use department-specific routes",
            },
        )
        apply_security_headers(response)
        return response

    return await call_next(request)


@app.middleware("http")
async def freeze_emergency_stop_middleware(request: Request, call_next):
    """Enforce freeze_mode and emergency_stop config.

    - Skip /health, /admin/*, /docs, /openapi.json
    - Emergency stop check first: if enabled and endpoint_sig is blocked -> 503
    - Freeze check second: if freeze_mode true and method in POST/PUT/PATCH/DELETE -> 423
    - Emit ledger events on block decisions
    """
    path = request.url.path
    method = request.method.upper()

    # Skip paths that bypass freeze checks
    if _should_bypass_freeze_check(path):
        return await call_next(request)

    # Resolve institution ID directly from header
    institution_id = request.headers.get("X-Institution-Id")
    if not institution_id:
        institution_id = request.headers.get("X-Tenant-Id")
    if not institution_id:
        institution_id = DEFAULT_INSTITUTION_ID

    config = get_cached_config(institution_id)

    # Compute endpoint_sig for emergency stop check
    endpoint_sig = _compute_endpoint_sig(method, path)

    # Get actor info from headers (or use defaults)
    actor_id = request.headers.get("X-Actor-Id") or DEFAULT_ACTOR_ID
    actor_roles_header = request.headers.get("X-Actor-Roles") or ""
    actor_roles = [r.strip() for r in actor_roles_header.split(",") if r.strip()]

    # Emergency stop check (first)
    if config.emergency_stop.enabled and endpoint_sig:
        if endpoint_sig in config.emergency_stop.blocked_endpoints:
            # Emit ledger event for blocked request
            ledger = get_ledger()
            if ledger:
                ledger.append(
                    event_type="INSTITUTION_EMERGENCY_STOP_BLOCKED",
                    tenant_id=institution_id,
                    actor_id=actor_id,
                    actor_roles=actor_roles,
                    case_id=None,
                    step="ADMIN:emergency_stop.block",
                    payload={
                        "decision": "deny",
                        "institution_id": institution_id,
                        "endpoint_sig": endpoint_sig,
                        "reason": "emergency_stop",
                    },
                )

            response = JSONResponse(
                status_code=503,
                content={
                    "code": INSTITUTION_EMERGENCY_STOPPED,
                    "message": "Endpoint blocked by emergency stop",
                },
            )
            apply_security_headers(response)
            return response

    # Freeze mode check (second) - blocks POST/PUT/PATCH/DELETE
    if config.freeze_mode and method in ("POST", "PUT", "PATCH", "DELETE"):
        # Emit ledger event for frozen request
        ledger = get_ledger()
        if ledger:
            ledger.append(
                event_type="INSTITUTION_FREEZE_BLOCKED",
                tenant_id=institution_id,
                actor_id=actor_id,
                actor_roles=actor_roles,
                case_id=None,
                step="ADMIN:freeze.block",
                payload={
                    "decision": "deny",
                    "institution_id": institution_id,
                    "endpoint_sig": endpoint_sig,
                    "method": method,
                    "path": path,
                    "reason": "freeze_mode",
                },
            )

        response = JSONResponse(
            status_code=423,
            content={
                "code": INSTITUTION_FROZEN,
                "message": "Institution is frozen; mutating operations are blocked",
            },
        )
        apply_security_headers(response)
        return response

    return await call_next(request)


@app.middleware("http")
async def ege_drift_middleware(request: Request, call_next):
    """Enforce EGE drift blocking for write operations.

    - Skip paths: /health, /admin/*, /docs, /openapi.json
    - Only applies to POST, PUT, PATCH, DELETE methods
    - If drift status is ACTIVE and ege_enforce_drift is True -> 409
    - Emit ledger event on block
    """
    path = request.url.path
    method = request.method.upper()

    # Skip paths that bypass drift checks (same as freeze checks)
    if _should_bypass_freeze_check(path):
        return await call_next(request)

    # Only check write methods
    if method not in ("POST", "PUT", "PATCH", "DELETE"):
        return await call_next(request)

    # Resolve institution ID directly from header
    institution_id = request.headers.get("X-Institution-Id")
    if not institution_id:
        institution_id = request.headers.get("X-Tenant-Id")
    if not institution_id:
        institution_id = DEFAULT_INSTITUTION_ID

    config = get_cached_config(institution_id)

    # Check if EGE drift enforcement is enabled
    if not config.ege_enforce_drift:
        return await call_next(request)

    # Load drift state
    drift_state = load_drift_state(institution_id)

    # If no drift state file or status is not ACTIVE, allow
    if drift_state is None or drift_state.status != "ACTIVE":
        return await call_next(request)

    # Drift is ACTIVE and enforcement is on -> block
    # Get actor info from headers
    actor_id = request.headers.get("X-Actor-Id") or DEFAULT_ACTOR_ID
    actor_roles_header = request.headers.get("X-Actor-Roles") or ""
    actor_roles = [r.strip() for r in actor_roles_header.split(",") if r.strip()]

    # Emit ledger event
    ledger = get_ledger()
    if ledger:
        ledger.append(
            event_type="EGE_DRIFT_BLOCKED",
            tenant_id=institution_id,
            actor_id=actor_id,
            actor_roles=actor_roles,
            case_id=institution_id,
            step="EGE:drift.block",
            payload={
                "decision": "deny",
                "institution_id": institution_id,
                "method": method,
                "path": path,
                "drift_status": drift_state.status,
                "bundle_manifest_mismatch": drift_state.bundle_manifest_mismatch,
                "contract_ledger_mismatch": drift_state.contract_ledger_mismatch,
            },
        )

    response = JSONResponse(
        status_code=409,
        content={
            "code": EGE_DRIFT_BLOCKED,
            "message": "Institution drift is active; mutating operations are blocked until resolved",
        },
    )
    apply_security_headers(response)
    return response


@app.middleware("http")
async def dept_routing_middleware(request: Request, call_next):
    """Handle department routing for /d/{dept}/... paths."""
    path = request.url.path

    # Extract dept from path if present
    dept = resolve_dept_from_path(path)

    if dept is not None:
        # Path starts with /d/{dept}/ - validate dept
        bundle_ctx = get_bundle_context()

        if bundle_ctx is None or bundle_ctx.mode != "multi":
            # Not in multi mode - dept routes not allowed
            response = JSONResponse(
                status_code=409,
                content={
                    "code": DEPT_MODE_REQUIRED,
                    "message": "Department routing requires multi-department bundle",
                },
            )
            apply_security_headers(response)
            return response

        if dept not in bundle_ctx.departments:
            # Unknown department
            response = JSONResponse(
                status_code=400,
                content={
                    "code": "DEPT_UNKNOWN",
                    "message": f"Unknown department: {dept}",
                },
            )
            apply_security_headers(response)
            return response

        # Valid dept - set on request state
        set_request_dept(request, dept)
    else:
        # No dept in path - clear dept_id
        set_request_dept(request, None)

    return await call_next(request)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Handle X-Request-Id header: validate, generate if missing, propagate via contextvar."""
    request_id_header = request.headers.get("X-Request-Id")

    if request_id_header is not None:
        # Validate UUID format
        if not _is_valid_uuid(request_id_header):
            response = JSONResponse(
                status_code=400,
                content={
                    "code": "REQUEST_ID_INVALID",
                    "message": "Invalid X-Request-Id"
                }
            )
            apply_security_headers(response)
            return response
        request_id = request_id_header
    else:
        # Generate new UUID
        request_id = str(uuid.uuid4())

    # Set in context for logging and ledger
    set_request_id(request_id)

    # Process request
    response = await call_next(request)

    # Add X-Request-Id to response
    response.headers["X-Request-Id"] = request_id

    # Clear context after request
    set_request_id(None)

    return response


@app.middleware("http")
async def institution_middleware(request: Request, call_next):
    """Resolve institution from X-Institution-Id or X-Tenant-Id headers.

    Sets request.state.institution_id for downstream handlers.
    Skips admin endpoints which don't require institution context.

    Enforces require_institution_header_for_runtime flag:
    - If true, ONLY X-Institution-Id header is accepted (not X-Tenant-Id)
    - Missing X-Institution-Id -> 400 INSTITUTION_HEADER_REQUIRED
    """
    path = request.url.path

    # Skip institution resolution for admin and health endpoints
    if path.startswith("/admin/") or path == "/health":
        # Set default institution for consistency
        set_request_institution_id(request, DEFAULT_INSTITUTION_ID)
        return await call_next(request)

    try:
        # First, try to resolve without requiring header
        institution_id = resolve_institution_id(request, require_header=False)

        # Check if this institution's config requires header enforcement
        if institution_id != DEFAULT_INSTITUTION_ID:
            config = get_cached_config(institution_id)
            if config.flags.require_institution_header_for_runtime:
                # When require_institution_header_for_runtime is true,
                # ONLY X-Institution-Id is accepted (per spec)
                has_institution_id = request.headers.get("X-Institution-Id") is not None
                if not has_institution_id:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": INSTITUTION_HEADER_REQUIRED,
                            "message": "X-Institution-Id header is required",
                        },
                    )

        # Validate institution exists (skips validation for DEFAULT_INSTITUTION_ID)
        validate_institution_exists(institution_id)

        # Set on request state
        set_request_institution_id(request, institution_id)

    except HTTPException as exc:
        # Return error response with proper envelope
        response = JSONResponse(
            status_code=exc.status_code,
            content=exc.detail if isinstance(exc.detail, dict) else {"code": "ERROR", "message": str(exc.detail)},
        )
        apply_security_headers(response)
        return response

    return await call_next(request)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log HTTP requests."""
    response = await call_next(request)

    # Extract actor info from headers if present
    actor_id = request.headers.get("X-Actor-Id")
    tenant_id = request.headers.get("X-Tenant-Id")

    # Log request (skip health checks in production to reduce noise)
    if request.url.path != "/health":
        log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )

    return response


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint.

    Returns:
        - 200 with {"status": "ok", "mode": "ACTIVE"} when ACTIVE
        - 503 with {"status": "degraded", "mode": "SAFE_MODE", "reason_code": "...", "details": [...]} when SAFE_MODE
    """
    if runtime_state.mode == RuntimeMode.ACTIVE:
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "mode": "ACTIVE"
            }
        )
    else:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "mode": "SAFE_MODE",
                "reason_code": runtime_state.reason_code,
                "details": runtime_state.details
            }
        )
