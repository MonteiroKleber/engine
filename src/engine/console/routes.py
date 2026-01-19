"""AXIOM Console - Read-only operational dashboard routes.

Provides HTML pages for viewing platform status without mutation capabilities.
Uses Jinja2 templates and HTMX for minimal interactivity.

Etapa 3.1: Console mínimo (read-only)
Etapa 3.2: Institutional Explorer (contracts, proof)
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from engine.ise.release import verify_admin_token, get_bundles_root_for_institution
from engine.core.runtime_state import runtime_state
from engine.core.institutions import get_registry as get_institutions_registry
from engine.core.institution_config import get_effective_config
from engine.core.ege_pins import get_pin_status
from engine.core.governed_mandates import get_effective_mandates
from engine.core.ege_proposals import list_proposals as list_ege_proposals
from engine.pipeline.registry import get_registry as get_dev_runs_registry
from engine.loader.load_bundle import get_bundle_context, get_bundle_path
from engine.loader.verify_hashes import compute_sha256
from engine.proof import verify_bundle_offline, is_safe_path, ProofResult


# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(prefix="/console", tags=["console"])


def _require_admin_token(token: Optional[str]) -> None:
    """Verify admin token for console access.

    Args:
        token: Admin token from header or query param.

    Raises:
        HTTPException: 401 if token is invalid or missing.
    """
    if not verify_admin_token(token):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "CONSOLE_UNAUTHORIZED",
                "message": "Invalid or missing admin token. Pass X-Admin-Token header.",
            },
        )


def _get_institutions_list() -> List[Dict[str, Any]]:
    """Get list of institutions for selection."""
    try:
        registry = get_institutions_registry()
        institutions = registry.list_institutions(limit=100)
        return [
            {
                "id": inst.institution_id,
                "slug": inst.slug,
                "name": inst.display_name or inst.slug,
            }
            for inst in institutions
        ]
    except Exception:
        return []


def _get_departments_list() -> List[str]:
    """Get list of available departments from bundle context."""
    try:
        ctx = get_bundle_context()
        if ctx and ctx.dept_mode:
            # In multi-dept mode, return known departments
            return list(ctx.departments.keys()) if hasattr(ctx, 'departments') else []
        return []
    except Exception:
        return []


def _get_health_info() -> Dict[str, Any]:
    """Get runtime health information."""
    return {
        "status": "ok" if runtime_state.mode.value == "ACTIVE" else "degraded",
        "mode": runtime_state.mode.value,
        "reason_code": runtime_state.reason_code,
        "details": runtime_state.details,
    }


def _get_pin_status_info(institution_id: str) -> Dict[str, Any]:
    """Get pin status for an institution."""
    try:
        pin_status, error_code, _ = get_pin_status(institution_id)
        if error_code:
            return {
                "pinned": {},
                "observed": {},
                "drift_status": "UNKNOWN",
            }
        return {
            "pinned": pin_status.pinned,
            "observed": pin_status.observed,
            "drift_status": pin_status.drift_status,
        }
    except Exception:
        return {
            "pinned": {},
            "observed": {},
            "drift_status": "UNKNOWN",
        }


def _get_institution_config_info(institution_id: str) -> Dict[str, Any]:
    """Get institution configuration."""
    try:
        config = get_effective_config(institution_id)
        if config:
            return {
                "emergency_freeze": config.emergency_freeze,
                "safe_mode_enabled": config.safe_mode_enabled,
                "pinned_release_id": config.pinned_release_id,
                "pinned_bundle_manifest_sha256": config.pinned_bundle_manifest_sha256,
                "pinned_contract_ledger_sha256": config.pinned_contract_ledger_sha256,
            }
        return {}
    except Exception:
        return {}


def _get_effective_mandates_info(
    institution_id: str, dept_id: Optional[str]
) -> Dict[str, Any]:
    """Get effective mandates for institution/dept."""
    try:
        mandate_def = get_effective_mandates(institution_id, dept_id)
        if mandate_def:
            mandates = []
            for m in mandate_def.mandates:
                mandates.append({
                    "mandate_id": m.mandate_id,
                    "endpoint_sig": m.endpoint_sig,
                    "phase": m.phase,
                    "allowed_roles": m.allowed_roles,
                })
            # Determine source
            from engine.core.governed_mandates import list_governed_mandates
            from engine.core.mandates import get_mandates as get_bundle_mandates
            governed = list_governed_mandates(institution_id, dept_id)
            bundle_def = get_bundle_mandates(dept_id)
            if governed and bundle_def:
                source = "merged"
            elif governed:
                source = "governed"
            elif bundle_def:
                source = "bundle"
            else:
                source = "none"
            return {"mandates": mandates, "source": source}
        return {"mandates": [], "source": "none"}
    except Exception:
        return {"mandates": [], "source": "error"}


def _get_dev_runs_info(limit: int = 20) -> Dict[str, Any]:
    """Get recent dev runs for bundles page."""
    try:
        registry = get_dev_runs_registry()
        runs = registry.list_active_runs(limit=limit)
        return {
            "runs": [
                {
                    "run_id": r.run_id,
                    "bundle_name": r.bundle_name,
                    "created_at": r.created_at,
                    "deleted": r.deleted,
                }
                for r in runs
            ],
            "total": len(runs),
        }
    except Exception:
        return {"runs": [], "total": 0}


def _get_ege_proposals_info(institution_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent EGE proposals for bundles page."""
    try:
        proposals = list_ege_proposals(institution_id, limit=limit)
        return [
            {
                "proposal_id": p.proposal_id,
                "status": p.status,
                "created_at": p.created_at,
                "decision": p.decision,
            }
            for p in proposals
        ]
    except Exception:
        return []


def _get_legacy_assets_info(
    institution_id: str, dept_id: Optional[str]
) -> Dict[str, Any]:
    """Get legacy assets information.

    Note: Legacy bridge may not expose read-only endpoints yet.
    This is a placeholder that returns empty data.
    """
    # TODO: Integrate with legacy_bridge module when read-only endpoints are available
    return {
        "assets": [],
        "bridge_available": False,
        "bridge_config": None,
    }


# =============================================================================
# Etapa 3.2: Explorer Helpers
# =============================================================================


def _get_bundle_path_for_institution(institution_id: str) -> Optional[Path]:
    """Get resolved bundle path for institution.

    Tries to resolve CURRENT symlink for institution's bundles.
    Falls back to global bundle path if institution bundle not found.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to bundle directory, or None if not found.
    """
    try:
        bundles_root = get_bundles_root_for_institution(institution_id)
        current = bundles_root / "CURRENT"
        if current.exists() and current.is_symlink():
            return current.resolve()
    except Exception:
        pass

    # Fallback to global bundle path
    try:
        global_path = get_bundle_path()
        if global_path.exists():
            return global_path
    except Exception:
        pass

    return None


def _load_manifest(bundle_path: Path) -> Optional[Dict[str, Any]]:
    """Load bundle.manifest.json from bundle path.

    Args:
        bundle_path: Path to bundle directory.

    Returns:
        Parsed manifest dict, or None if not found/invalid.
    """
    manifest_path = bundle_path / "bundle.manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_contract_ledger(bundle_path: Path) -> Optional[Dict[str, Any]]:
    """Load contract_ledger.json from bundle path.

    Args:
        bundle_path: Path to bundle directory.

    Returns:
        Parsed ledger dict, or None if not found/invalid.
    """
    ledger_path = bundle_path / "contract_ledger.json"
    if not ledger_path.exists():
        return None
    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _get_contracts_info(bundle_path: Path) -> Dict[str, Any]:
    """Get contracts information from manifest.

    Args:
        bundle_path: Path to bundle directory.

    Returns:
        Dict with contracts list, manifest hash, and ledger info.
    """
    manifest = _load_manifest(bundle_path)
    ledger = _load_contract_ledger(bundle_path)

    if not manifest:
        return {
            "contracts": [],
            "manifest": None,
            "manifest_hash": None,
            "ledger": None,
            "ledger_hash": None,
            "source_idl_sha256": None,
            "bundle_name": None,
            "bundle_version": None,
        }

    # Compute manifest hash
    manifest_path = bundle_path / "bundle.manifest.json"
    manifest_hash = compute_sha256(manifest_path) if manifest_path.exists() else None

    # Compute ledger hash
    ledger_path = bundle_path / "contract_ledger.json"
    ledger_hash = compute_sha256(ledger_path) if ledger_path.exists() else None

    # Extract contracts from manifest
    contracts = []
    for c in manifest.get("contracts", []):
        contract_file = c.get("file", "")
        contract_sha256 = c.get("sha256", "")
        contracts.append({
            "file": contract_file,
            "sha256": contract_sha256,
            "required": c.get("required", True),
        })

    return {
        "contracts": contracts,
        "manifest": manifest,
        "manifest_hash": manifest_hash,
        "ledger": ledger,
        "ledger_hash": ledger_hash,
        "source_idl_sha256": ledger.get("source_idl_sha256") if ledger else None,
        "bundle_name": manifest.get("name"),
        "bundle_version": manifest.get("version"),
    }


def _read_contract_file(
    bundle_path: Path, file_path: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Read a contract file from bundle with safety checks.

    Args:
        bundle_path: Path to bundle directory.
        file_path: Relative path to contract file.

    Returns:
        Tuple of (content, computed_hash, error_message).
        On success: (content, hash, None)
        On failure: (None, None, error_message)
    """
    # Security: Check for path traversal
    if not is_safe_path(bundle_path, file_path):
        return None, None, "EXPLORER_PATH_TRAVERSAL"

    full_path = bundle_path / file_path

    if not full_path.exists():
        return None, None, "EXPLORER_FILE_NOT_FOUND"

    if not full_path.is_file():
        return None, None, "EXPLORER_NOT_A_FILE"

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        computed_hash = compute_sha256(full_path)
        return content, computed_hash, None
    except OSError as e:
        return None, None, f"EXPLORER_READ_ERROR: {e}"
    except UnicodeDecodeError:
        return None, None, "EXPLORER_BINARY_FILE"


# =============================================================================
# Static Files Route
# =============================================================================


@router.get("/static/{file_path:path}")
async def serve_static(file_path: str) -> FileResponse:
    """Serve static files (CSS, JS).

    Args:
        file_path: Path to static file.

    Returns:
        Static file response.

    Raises:
        HTTPException: 404 if file not found.
    """
    full_path = STATIC_DIR / file_path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    content_type = "text/plain"
    if file_path.endswith(".css"):
        content_type = "text/css"
    elif file_path.endswith(".js"):
        content_type = "application/javascript"

    return FileResponse(full_path, media_type=content_type)


# =============================================================================
# Page Routes
# =============================================================================


@router.get("/", response_class=HTMLResponse)
async def console_home(
    request: Request,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> HTMLResponse:
    """Console home page - institution/department selection.

    Args:
        request: FastAPI request.
        x_admin_token: Admin token from header.

    Returns:
        Rendered home page HTML.
    """
    _require_admin_token(x_admin_token)

    institutions = _get_institutions_list()
    departments = _get_departments_list()
    health = _get_health_info()

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "active_page": "home",
            "admin_token": x_admin_token or "",
            "institutions": institutions,
            "departments": departments,
            "runtime_mode": health["mode"],
            "institution_id": None,
            "dept_id": None,
        },
    )


@router.get("/status", response_class=HTMLResponse)
async def console_status(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> HTMLResponse:
    """Console status page - runtime status, drift, config.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered status page HTML.
    """
    _require_admin_token(x_admin_token)

    health = _get_health_info()
    pin_status = _get_pin_status_info(institution_id)
    config = _get_institution_config_info(institution_id)
    mandates = _get_effective_mandates_info(institution_id, dept_id)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    return templates.TemplateResponse(
        "status.html",
        {
            "request": request,
            "active_page": "status",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "health": health,
            "drift_status": pin_status["drift_status"],
            "pinned": pin_status["pinned"],
            "observed": pin_status["observed"],
            "config": config,
            "mandates": mandates,
        },
    )


@router.get("/bundles", response_class=HTMLResponse)
async def console_bundles(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> HTMLResponse:
    """Console bundles page - releases, pins, builds.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered bundles page HTML.
    """
    _require_admin_token(x_admin_token)

    pin_status = _get_pin_status_info(institution_id)
    dev_runs = _get_dev_runs_info(limit=20)
    proposals = _get_ege_proposals_info(institution_id, limit=10)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    return templates.TemplateResponse(
        "bundles.html",
        {
            "request": request,
            "active_page": "bundles",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "pinned": pin_status["pinned"],
            "observed": pin_status["observed"],
            "drift_status": pin_status["drift_status"],
            "runs": dev_runs["runs"],
            "total_runs": dev_runs["total"],
            "proposals": proposals,
        },
    )


@router.get("/legacy", response_class=HTMLResponse)
async def console_legacy(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> HTMLResponse:
    """Console legacy page - legacy assets read-only view.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered legacy page HTML.
    """
    _require_admin_token(x_admin_token)

    legacy_info = _get_legacy_assets_info(institution_id, dept_id)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    return templates.TemplateResponse(
        "legacy.html",
        {
            "request": request,
            "active_page": "legacy",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "assets": legacy_info["assets"],
            "bridge_available": legacy_info["bridge_available"],
            "bridge_config": legacy_info["bridge_config"],
        },
    )


# =============================================================================
# Partial Routes (for HTMX)
# =============================================================================


@router.get("/partials/status", response_class=HTMLResponse)
async def console_status_partial(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> HTMLResponse:
    """Partial status update for HTMX polling.

    Returns only the status card content for efficient updates.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Partial HTML for status update.
    """
    _require_admin_token(x_admin_token)

    health = _get_health_info()
    pin_status = _get_pin_status_info(institution_id)

    # Simple partial response - just data for client-side check
    # The full page handles display, this is for silent background updates
    return HTMLResponse(
        content=f"""
        <div id="status-data" data-mode="{health['mode']}" data-drift="{pin_status['drift_status']}">
            <!-- Status updated at {health.get('timestamp', 'now')} -->
        </div>
        """,
        status_code=200,
    )


# =============================================================================
# Etapa 3.2: Explorer Routes (Contracts, Proof)
# =============================================================================


@router.get("/contracts", response_class=HTMLResponse)
async def console_contracts(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> HTMLResponse:
    """Console contracts page - list contracts from manifest.

    Shows bundle.manifest.json, contract_ledger.json, and contracts list.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered contracts page HTML.
    """
    _require_admin_token(x_admin_token)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get bundle path for institution
    bundle_path = _get_bundle_path_for_institution(institution_id)

    if not bundle_path:
        return templates.TemplateResponse(
            "contracts.html",
            {
                "request": request,
                "active_page": "contracts",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "bundle_path": None,
                "error": "No bundle found for institution",
                "contracts": [],
                "manifest": None,
                "manifest_hash": None,
                "ledger": None,
                "ledger_hash": None,
                "source_idl_sha256": None,
                "bundle_name": None,
                "bundle_version": None,
            },
        )

    contracts_info = _get_contracts_info(bundle_path)

    return templates.TemplateResponse(
        "contracts.html",
        {
            "request": request,
            "active_page": "contracts",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "bundle_path": str(bundle_path),
            "error": None,
            **contracts_info,
        },
    )


@router.get("/contracts/{file_path:path}", response_class=HTMLResponse)
async def console_contract_detail(
    request: Request,
    file_path: str,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> HTMLResponse:
    """Console contract detail page - view contract content.

    Shows contract file content with computed hash for verification.

    Args:
        request: FastAPI request.
        file_path: Relative path to contract file within bundle.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered contract detail page HTML.

    Raises:
        HTTPException: 400 if path traversal detected, 404 if file not found.
    """
    _require_admin_token(x_admin_token)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get bundle path for institution
    bundle_path = _get_bundle_path_for_institution(institution_id)

    if not bundle_path:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "EXPLORER_BUNDLE_NOT_FOUND",
                "message": "No bundle found for institution",
            },
        )

    # Read contract file with safety checks
    content, computed_hash, error = _read_contract_file(bundle_path, file_path)

    if error:
        if error == "EXPLORER_PATH_TRAVERSAL":
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "EXPLORER_PATH_TRAVERSAL",
                    "message": "Path traversal detected - access denied",
                },
            )
        elif error == "EXPLORER_FILE_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "EXPLORER_FILE_NOT_FOUND",
                    "message": f"Contract file not found: {file_path}",
                },
            )
        else:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": error.split(":")[0] if ":" in error else error,
                    "message": error,
                },
            )

    # Get expected hash from manifest
    contracts_info = _get_contracts_info(bundle_path)
    expected_hash = None
    for c in contracts_info["contracts"]:
        if c["file"] == file_path:
            expected_hash = c["sha256"]
            break

    # Determine hash match status
    hash_match = None
    if expected_hash and computed_hash:
        hash_match = expected_hash.lower() == computed_hash.lower()

    # Determine file type for syntax highlighting hint
    file_ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""

    return templates.TemplateResponse(
        "contract_detail.html",
        {
            "request": request,
            "active_page": "contracts",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "file_path": file_path,
            "content": content,
            "computed_hash": computed_hash,
            "expected_hash": expected_hash,
            "hash_match": hash_match,
            "file_ext": file_ext,
            "bundle_path": str(bundle_path),
        },
    )


@router.get("/proof", response_class=HTMLResponse)
async def console_proof(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    show_json: bool = Query(False, description="Show raw JSON result"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> HTMLResponse:
    """Console proof page - run offline bundle verification.

    Executes verify_bundle_offline and displays PASS/FAIL result.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        show_json: Whether to show raw JSON result.
        x_admin_token: Admin token from header.

    Returns:
        Rendered proof page HTML.
    """
    _require_admin_token(x_admin_token)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get bundle path for institution
    bundle_path = _get_bundle_path_for_institution(institution_id)

    if not bundle_path:
        return templates.TemplateResponse(
            "proof.html",
            {
                "request": request,
                "active_page": "proof",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "bundle_path": None,
                "result": None,
                "error": "No bundle found for institution",
                "show_json": show_json,
                "result_json": None,
            },
        )

    # Run offline verification
    try:
        result = verify_bundle_offline(bundle_path)
        result_dict = result.to_dict()
    except Exception as e:
        return templates.TemplateResponse(
            "proof.html",
            {
                "request": request,
                "active_page": "proof",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "bundle_path": str(bundle_path),
                "result": None,
                "error": f"Verification error: {e}",
                "show_json": show_json,
                "result_json": None,
            },
        )

    return templates.TemplateResponse(
        "proof.html",
        {
            "request": request,
            "active_page": "proof",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "bundle_path": str(bundle_path),
            "result": result_dict,
            "error": None,
            "show_json": show_json,
            "result_json": json.dumps(result_dict, indent=2) if show_json else None,
        },
    )
