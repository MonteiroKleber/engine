"""AXIOM Console - Read-only operational dashboard routes.

Provides HTML pages for viewing platform status without mutation capabilities.
Uses Jinja2 templates and HTMX for minimal interactivity.

Etapa 3.1: Console mínimo (read-only)
Etapa 3.2: Institutional Explorer (contracts, proof)
Etapa 3.3: Proof Console UX + Export
Etapa 4.1: Auth no Browser (Sessão/Cookie)
"""

import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Cookie, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from engine.ise.release import verify_admin_token, get_admin_token, get_bundles_root_for_institution
from engine.console.session import (
    COOKIE_NAME,
    COOKIE_PATH,
    create_session_cookie,
    verify_session_cookie,
    get_csrf_from_cookie,
    get_session_ttl_seconds,
    should_use_secure_cookie,
)
from engine.core.errors import CONSOLE_CSRF_INVALID
from engine.core.runtime_state import runtime_state
from engine.core.institutions import get_registry as get_institutions_registry
from engine.core.institution_config import get_effective_config
from engine.core.ege_pins import get_pin_status
from engine.core.governed_mandates import (
    get_effective_mandates,
    list_mandate_proposals,
    list_governed_mandates,
    load_proposal_state,
    propose_mandate_change,
    decide_mandate_proposal,
    MandateProposalState,
)
from engine.core.mandates import get_mandates as get_bundle_mandates
from engine.core.governed_policies import (
    get_effective_policies,
    list_policy_proposals,
    list_governed_policies,
    get_policy_proposal,
    propose_policy_change,
    decide_policy_proposal,
    PolicyProposalState,
)
from engine.core.policy import get_policies as get_bundle_policies
from engine.core.governed_autonomy import (
    get_effective_autonomy,
    list_autonomy_proposals,
    list_governed_autonomy,
    get_autonomy_proposal,
    propose_autonomy_change,
    decide_autonomy_proposal,
    AutonomyProposalState,
)
from engine.core.autonomy import get_autonomy_for_dept as get_bundle_autonomy
from engine.core.ege_proposals import list_proposals as list_ege_proposals, load_current_state as load_ege_proposal_state
from engine.core.ege import check_drift, load_drift_state
from engine.core.ege_rollback import (
    execute_governed_rollback,
    get_current_release_id,
    check_rollback_blocked,
    get_pinned_release_path,
    list_releases,
)
from engine.core.ege_pins import is_pin_update_proposal, get_pin_proposal_metadata
from engine.pipeline.registry import get_registry as get_dev_runs_registry
from engine.loader.load_bundle import get_bundle_context, get_bundle_path
from engine.loader.verify_hashes import compute_sha256
from engine.proof import verify_bundle_offline, is_safe_path, ProofResult
from engine.legacy_bridge import (
    LegacyBridgeRegistry,
    verify_asset as legacy_verify_asset,
    LegacyWriteRegistry,
    ACTION_SCHEMAS,
)
from engine.nl.extractors import get_extractor
from engine.nl.draft_generator import generate_draft
from engine.nl.gap_detector import detect_gaps, gaps_to_dict
from engine.nl.answer_apply import apply_answers
from engine.nl.finalizer import finalize, validate_final
from engine.nl.schemas.answers_v1 import AnswersV1, Answer, Gap
from engine.idl_dsl import parse_dsl, IDLSyntaxError, IDLSemanticError
from engine.agent_ops import (
    list_events_by_actor,
    list_denied_events,
    get_agent_registry,
    get_agent_by_actor_id,
    GATE_EVENT_TYPES,
)
from engine.agent_ops.agent_requests import get_agent_requests_registry
from engine.agent_ops.read_model import get_actor_stats, list_unique_actors


# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(prefix="/console", tags=["console"])


def _require_admin_token(token: Optional[str]) -> None:
    """Verify admin token for console access (legacy, header only).

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


def _is_html_request(request: Request) -> bool:
    """Check if request prefers HTML response.

    Args:
        request: FastAPI request.

    Returns:
        True if Accept header indicates HTML preference.
    """
    accept = request.headers.get("accept", "")
    return "text/html" in accept


def _require_console_auth(
    request: Request,
    x_admin_token: Optional[str] = None,
    session_cookie: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Verify console auth via header OR cookie.

    Supports dual authentication:
    - X-Admin-Token header (for curl/automation)
    - Session cookie (for browser)

    Args:
        request: FastAPI request.
        x_admin_token: Admin token from X-Admin-Token header.
        session_cookie: Session cookie value.

    Returns:
        Tuple of (is_authenticated, csrf_token).
        csrf_token is only set for cookie auth.

    Raises:
        HTTPException: 401/303 if not authenticated.
    """
    # Try header first (for curl/automation)
    if x_admin_token and verify_admin_token(x_admin_token):
        return True, None

    # Try cookie
    admin_token = get_admin_token()
    if session_cookie and admin_token:
        session_data = verify_session_cookie(session_cookie, admin_token)
        if session_data:
            return True, session_data.csrf_token

    # Not authenticated - determine response type
    if _is_html_request(request):
        # Redirect to login page using RedirectResponse
        from urllib.parse import quote
        next_url = quote(str(request.url), safe="")
        redirect_url = f"/console/login?next={next_url}"
        # Use a custom exception class that Starlette handles as redirect
        raise RedirectException(redirect_url)
    else:
        # Return JSON error
        raise HTTPException(
            status_code=401,
            detail={
                "code": "CONSOLE_UNAUTHORIZED",
                "message": "Invalid or missing authentication. Pass X-Admin-Token header or login via browser.",
            },
        )


class RedirectException(Exception):
    """Exception that triggers a redirect response."""

    def __init__(self, url: str, status_code: int = 303):
        self.url = url
        self.status_code = status_code
        super().__init__(f"Redirect to {url}")


def _require_csrf_token(
    request: Request,
    session_cookie: Optional[str],
    csrf_token: Optional[str],
) -> None:
    """Validate CSRF token for POST requests.

    CSRF is only required for cookie-based auth. Header auth (X-Admin-Token)
    is exempt since it already requires explicit token passing.

    Args:
        request: FastAPI request.
        session_cookie: Session cookie value.
        csrf_token: CSRF token from form.

    Raises:
        HTTPException: 403 if CSRF validation fails.
    """
    # If no session cookie, auth must be via header (CSRF not required)
    if not session_cookie:
        return

    # Get CSRF from session
    expected_csrf = get_csrf_from_cookie(session_cookie)
    if not expected_csrf:
        raise HTTPException(
            status_code=403,
            detail={
                "code": CONSOLE_CSRF_INVALID,
                "message": "Invalid session. Please login again.",
            },
        )

    # Validate CSRF token
    if not csrf_token or not secrets.compare_digest(expected_csrf, csrf_token):
        raise HTTPException(
            status_code=403,
            detail={
                "code": CONSOLE_CSRF_INVALID,
                "message": "Invalid or missing CSRF token.",
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


def _get_departments_for_institution(institution_id: str) -> List[str]:
    """Derive department IDs from the institution's active bundle manifest.

    This avoids relying on the global bundle context, since bundles are namespaced
    per institution.
    """
    bundle_path = _get_bundle_path_for_institution(institution_id)
    if not bundle_path:
        return []

    manifest_path = bundle_path / "bundle.manifest.json"
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        return []

    departments = set()
    for c in manifest.get("contracts", []):
        if not isinstance(c, dict):
            continue
        file_path = c.get("file") or ""
        if not isinstance(file_path, str):
            continue
        if file_path.startswith("departments/"):
            parts = file_path.split("/")
            if len(parts) >= 2 and parts[1]:
                departments.add(parts[1])

    return sorted(departments)


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
    """Get legacy assets information from LegacyBridgeRegistry.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        Dict with assets list and bridge status.
    """
    try:
        registry = LegacyBridgeRegistry(institution_id, dept_id)
        assets = registry.list_assets()
        return {
            "assets": assets,
            "bridge_available": True,
            "total_assets": len(assets),
        }
    except Exception:
        return {
            "assets": [],
            "bridge_available": False,
            "total_assets": 0,
        }


def _get_migration_status_info(
    institution_id: str, departments: Optional[List[str]]
) -> Dict[str, Any]:
    """Get IDL migration status for an institution.

    Args:
        institution_id: Institution UUID.
        departments: List of department IDs (or None for single-mode).

    Returns:
        Dict with migration status for template rendering.
    """
    try:
        from engine.core.migration_check import get_migration_status

        return get_migration_status(institution_id, departments)
    except Exception:
        return {
            "api_mode": "unknown",
            "depts_installed": departments or [],
            "depts_migrated": [],
            "depts_not_migrated": [],
            "unsupported_binds": [],
            "migration_complete": False,
            "check_code": "ERROR",
            "check_message": "Migration status unavailable",
            "warnings": [],
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


def _generate_proof_checks(result_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate list of verification checks for proof page.

    Args:
        result_dict: ProofResult as dictionary.

    Returns:
        List of check dicts with name, status, detail fields.
    """
    checks = []
    passed = result_dict.get("passed", False)
    error_code = result_dict.get("error_code")

    # Check 1: Manifest exists
    if error_code == "PROOF_MANIFEST_MISSING":
        checks.append({"name": "Manifest exists", "status": "fail", "detail": "bundle.manifest.json not found"})
    else:
        checks.append({"name": "Manifest exists", "status": "pass", "detail": None})

    # Check 2: Manifest valid JSON
    if error_code == "PROOF_MANIFEST_INVALID_JSON":
        checks.append({"name": "Manifest valid JSON", "status": "fail", "detail": "Invalid JSON format"})
    elif error_code == "PROOF_MANIFEST_MISSING":
        checks.append({"name": "Manifest valid JSON", "status": "skip", "detail": "Skipped (manifest missing)"})
    else:
        checks.append({"name": "Manifest valid JSON", "status": "pass", "detail": None})

    # Check 3: Manifest schema valid
    if error_code == "PROOF_MANIFEST_INVALID_SCHEMA":
        checks.append({"name": "Manifest schema valid", "status": "fail", "detail": "Missing required fields"})
    elif error_code in ("PROOF_MANIFEST_MISSING", "PROOF_MANIFEST_INVALID_JSON"):
        checks.append({"name": "Manifest schema valid", "status": "skip", "detail": "Skipped"})
    else:
        checks.append({"name": "Manifest schema valid", "status": "pass", "detail": None})

    # Check 4: Contracts hashes
    contracts_verified = result_dict.get("contracts_verified", 0)
    if error_code and error_code.startswith("PROOF_CONTRACT_"):
        detail = result_dict.get("details", {}).get("file", "Unknown file")
        checks.append({"name": "Contracts hashes", "status": "fail", "detail": f"Failed: {detail}"})
    elif error_code in ("PROOF_MANIFEST_MISSING", "PROOF_MANIFEST_INVALID_JSON", "PROOF_MANIFEST_INVALID_SCHEMA"):
        checks.append({"name": "Contracts hashes", "status": "skip", "detail": "Skipped"})
    else:
        checks.append({"name": "Contracts hashes", "status": "pass", "detail": f"{contracts_verified} verified"})

    # Check 5: Ledger exists
    if error_code == "PROOF_LEDGER_MISSING":
        checks.append({"name": "Ledger exists", "status": "fail", "detail": "contract_ledger.json not found"})
    elif error_code and (error_code.startswith("PROOF_MANIFEST_") or error_code.startswith("PROOF_CONTRACT_")):
        checks.append({"name": "Ledger exists", "status": "skip", "detail": "Skipped"})
    else:
        checks.append({"name": "Ledger exists", "status": "pass", "detail": None})

    # Check 6: Ledger manifest_hash
    if error_code == "PROOF_LEDGER_MANIFEST_HASH_MISMATCH":
        checks.append({"name": "Ledger manifest_hash", "status": "fail", "detail": "Hash mismatch"})
    elif error_code == "PROOF_LEDGER_MANIFEST_HASH_INVALID":
        checks.append({"name": "Ledger manifest_hash", "status": "fail", "detail": "Invalid format"})
    elif error_code and not passed:
        checks.append({"name": "Ledger manifest_hash", "status": "skip", "detail": "Skipped"})
    else:
        checks.append({"name": "Ledger manifest_hash", "status": "pass", "detail": None})

    # Check 7: Ledger contracts 1:1
    if error_code in ("PROOF_LEDGER_CONTRACT_MISSING", "PROOF_LEDGER_CONTRACT_EXTRA", "PROOF_LEDGER_CONTRACT_HASH_MISMATCH"):
        detail = result_dict.get("details", {}).get("file", "Unknown")
        checks.append({"name": "Ledger contracts 1:1", "status": "fail", "detail": f"Mismatch: {detail}"})
    elif error_code and not passed:
        checks.append({"name": "Ledger contracts 1:1", "status": "skip", "detail": "Skipped"})
    else:
        checks.append({"name": "Ledger contracts 1:1", "status": "pass", "detail": None})

    # Check 8: source_idl_sha256
    if error_code == "PROOF_SOURCE_IDL_MISSING":
        checks.append({"name": "source_idl_sha256", "status": "fail", "detail": "Not found in ledger"})
    elif error_code == "PROOF_SOURCE_IDL_INVALID_FORMAT":
        checks.append({"name": "source_idl_sha256", "status": "fail", "detail": "Invalid format"})
    elif error_code and not passed:
        checks.append({"name": "source_idl_sha256", "status": "skip", "detail": "Skipped"})
    else:
        checks.append({"name": "source_idl_sha256", "status": "pass", "detail": None})

    return checks


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
# Auth Routes (Etapa 4.1)
# =============================================================================


@router.get("/login", response_class=HTMLResponse)
async def console_login_page(
    request: Request,
    next: Optional[str] = Query("/console/", description="URL to redirect after login"),
    expired: Optional[str] = Query(None, description="Session expired flag"),
    console_session: Optional[str] = Cookie(None),
) -> Response:
    """Console login page.

    If already authenticated via cookie, redirects to next URL.

    Args:
        request: FastAPI request.
        next: URL to redirect after successful login.
        expired: If "1", shows session expired message.
        console_session: Session cookie.

    Returns:
        Login page HTML or redirect if already authenticated.
    """
    # Check if already authenticated via cookie
    admin_token = get_admin_token()
    if console_session and admin_token:
        session_data = verify_session_cookie(console_session, admin_token)
        if session_data:
            # Already authenticated - redirect to next
            return RedirectResponse(url=next or "/console/", status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
            "expired": expired == "1",
            "next": next or "/console/",
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def console_login_submit(
    request: Request,
    token: str = Form(..., description="Admin token"),
    next: str = Form("/console/", description="URL to redirect after login"),
) -> Response:
    """Process console login.

    Validates token and creates session cookie.

    Args:
        request: FastAPI request.
        token: Admin token from form.
        next: URL to redirect after login.

    Returns:
        Redirect on success, login page with error on failure.
    """
    # Validate token
    if not verify_admin_token(token):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid token. Please check and try again.",
                "expired": False,
                "next": next,
            },
            status_code=401,
        )

    # Create session cookie
    cookie_value, csrf_token = create_session_cookie(token)

    # Build redirect response with cookie
    response = RedirectResponse(url=next, status_code=303)

    # Set cookie attributes
    max_age = get_session_ttl_seconds()
    secure = should_use_secure_cookie()

    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        max_age=max_age,
        path=COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=secure,
    )

    return response


@router.get("/logout")
async def console_logout(
    request: Request,
    console_session: Optional[str] = Cookie(None),
) -> Response:
    """Console logout - clears session cookie.

    Args:
        request: FastAPI request.
        console_session: Session cookie (optional).

    Returns:
        Redirect to login page.
    """
    response = RedirectResponse(url="/console/login", status_code=303)

    # Clear cookie by setting max_age=0
    response.set_cookie(
        key=COOKIE_NAME,
        value="",
        max_age=0,
        path=COOKIE_PATH,
        httponly=True,
        samesite="strict",
    )

    return response


# =============================================================================
# Page Routes
# =============================================================================


@router.get("/", response_class=HTMLResponse)
async def console_home(
    request: Request,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console home page - institution/department selection.

    Supports dual auth: X-Admin-Token header OR session cookie.

    Args:
        request: FastAPI request.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Rendered home page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    institutions = _get_institutions_list()
    departments = _get_departments_list()
    health = _get_health_info()

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "active_page": "home",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institutions": institutions,
            "departments": departments,
            "runtime_mode": health["mode"],
            "institution_id": None,
            "dept_id": None,
        },
    )


@router.get("/partials/departments", response_class=HTMLResponse)
async def console_departments_partial(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Return <option> list for departments dropdown, derived from institution bundle."""
    _require_console_auth(request, x_admin_token, console_session)

    departments = _get_departments_for_institution(institution_id)
    options = ['<option value="">-- All Departments --</option>']
    for dept in departments:
        options.append(f'<option value="{dept}">{dept}</option>')

    return HTMLResponse(content="\n".join(options), status_code=200)


@router.get("/status", response_class=HTMLResponse)
async def console_status(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
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
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    health = _get_health_info()
    pin_status = _get_pin_status_info(institution_id)
    config = _get_institution_config_info(institution_id)
    mandates = _get_effective_mandates_info(institution_id, dept_id)

    # Get departments for migration status
    departments = _get_departments_for_institution(institution_id)
    migration = _get_migration_status_info(
        institution_id, departments if departments else None
    )

    # Legacy cutover telemetry (ENGINE_API_MODE=both): read-only status for transition planning.
    try:
        from engine.core.legacy_telemetry import get_legacy_cutover_status

        legacy_cutover = get_legacy_cutover_status(institution_id)
    except Exception:
        legacy_cutover = {"total": 0, "last_ts": None, "by_endpoint": []}

    # IDL telemetry (ENGINE_API_MODE=idl|both): endpoint usage for observability - Expansão 05
    try:
        from engine.core.idl_telemetry import get_idl_telemetry_status

        idl_telemetry = get_idl_telemetry_status(institution_id)
    except Exception:
        idl_telemetry = {"total": 0, "last_ts": None, "by_endpoint": []}

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
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "health": health,
            "drift_status": pin_status["drift_status"],
            "pinned": pin_status["pinned"],
            "observed": pin_status["observed"],
            "config": config,
            "mandates": mandates,
            "migration": migration,
            "legacy_cutover": legacy_cutover,
            "idl_telemetry": idl_telemetry,
        },
    )


@router.get("/bundles", response_class=HTMLResponse)
async def console_bundles(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
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
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

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
            "csrf_token": csrf_token or "",
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
    console_session: Optional[str] = Cookie(None),
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
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

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
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "assets": legacy_info["assets"],
            "bridge_available": legacy_info["bridge_available"],
            "total_assets": legacy_info.get("total_assets", 0),
        },
    )


@router.get("/legacy/{asset_id}", response_class=HTMLResponse)
async def console_legacy_detail(
    request: Request,
    asset_id: str,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    verify_result: Optional[str] = Query(None, description="Verify result from redirect"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console legacy asset detail page.

    Args:
        request: FastAPI request.
        asset_id: Asset identifier.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        verify_result: Optional verify result from POST redirect.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Rendered asset detail page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get asset from registry
    try:
        registry = LegacyBridgeRegistry(institution_id, dept_id)
        asset = registry.get_asset(asset_id)
        last_snapshot = registry.get_last_snapshot(asset_id) if asset else None
    except Exception:
        asset = None
        last_snapshot = None

    if not asset:
        raise HTTPException(
            status_code=404,
            detail={"code": "ASSET_NOT_FOUND", "message": f"Asset not found: {asset_id}"},
        )

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    return templates.TemplateResponse(
        "legacy_detail.html",
        {
            "request": request,
            "active_page": "legacy",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "asset": asset,
            "last_snapshot": last_snapshot,
            "verify_result": verify_result,
        },
    )


@router.post("/legacy/{asset_id}/verify")
async def console_legacy_verify(
    request: Request,
    asset_id: str,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Execute verify on a legacy asset (read-only on source).

    Args:
        request: FastAPI request.
        asset_id: Asset identifier.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        _csrf_token: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to asset detail page with verify result.
    """
    _require_console_auth(request, x_admin_token, console_session)
    _require_csrf_token(request, console_session, csrf_token_form)

    # Execute verify (read-only - does not modify source)
    try:
        result = legacy_verify_asset(
            institution_id=institution_id,
            asset_id=asset_id,
            dept_id=dept_id,
            actor_id="console",
        )
        verify_status = result.status
    except Exception as e:
        verify_status = f"ERROR:{str(e)[:50]}"

    # Build redirect URL
    redirect_url = f"/console/legacy/{asset_id}?institution_id={institution_id}&verify_result={verify_status}"
    if dept_id:
        redirect_url += f"&dept_id={dept_id}"

    return RedirectResponse(url=redirect_url, status_code=303)


# =============================================================================
# Etapa 4.3: Legacy Bridge Write-Mode (Governado)
# =============================================================================


@router.post("/bridge/write/{action}")
async def console_bridge_write(
    request: Request,
    action: str,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    params: str = Form(...),  # JSON string
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> JSONResponse:
    """Execute a governed write action on legacy system.

    This endpoint passes through governance gates (mandate/autonomy/policy)
    before writing an action to the outbox.

    Args:
        request: FastAPI request.
        action: Action type (e.g., "increase_limit").
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        params: JSON string with action parameters.
        csrf_token_form: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        JSON response with action details or error.
    """
    admin_token, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Validate CSRF
    if csrf_token_form != csrf_token:
        return JSONResponse(
            status_code=403,
            content={"error": "CONSOLE_CSRF_INVALID", "message": "Invalid CSRF token"},
        )

    # Parse params JSON
    try:
        params_dict = json.loads(params) if params else {}
    except json.JSONDecodeError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "LEGACY_WRITE_PARAMS_INVALID", "message": f"Invalid JSON: {e}"},
        )

    # Execute governed write
    registry = LegacyWriteRegistry(institution_id, dept_id)
    result = registry.request_write(
        action_type=action,
        params=params_dict,
        actor_id="console",  # In production, extract from session
        actor_roles=["admin"],
    )

    if result.success:
        return JSONResponse(
            status_code=201,
            content={
                "action_id": result.action.action_id if result.action else None,
                "action_type": action,
                "status": "enqueued",
                "outbox_path": result.outbox_path,
                "outbox_sha256": result.outbox_sha256,
            },
        )
    else:
        # Determine HTTP status based on error type
        if result.denied_by:
            status_code = 403  # Forbidden by governance
        elif result.error_code in ("LEGACY_WRITE_ACTION_TYPE_UNKNOWN", "LEGACY_WRITE_PARAMS_INVALID"):
            status_code = 400  # Bad request
        else:
            status_code = 500  # Server error

        return JSONResponse(
            status_code=status_code,
            content={
                "error": result.error_code,
                "message": result.error_message,
                "denied_by": result.denied_by,
                "action_id": result.action.action_id if result.action else None,
            },
        )


@router.get("/bridge/write/actions")
async def console_bridge_list_actions(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> JSONResponse:
    """List write actions for an institution.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        status: Filter by status (pending, enqueued, denied).
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        JSON response with list of actions.
    """
    _require_console_auth(request, x_admin_token, console_session)

    registry = LegacyWriteRegistry(institution_id, dept_id)
    actions = registry.list_actions(status=status)

    return JSONResponse(
        status_code=200,
        content={
            "actions": [a.to_dict() for a in actions],
            "total": len(actions),
        },
    )


@router.get("/bridge/write/actions/{action_id}")
async def console_bridge_get_action(
    request: Request,
    action_id: str,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> JSONResponse:
    """Get a specific write action by ID.

    Args:
        request: FastAPI request.
        action_id: Action UUID.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        JSON response with action details.
    """
    _require_console_auth(request, x_admin_token, console_session)

    registry = LegacyWriteRegistry(institution_id, dept_id)
    action = registry.get_action(action_id)

    if not action:
        return JSONResponse(
            status_code=404,
            content={"error": "LEGACY_WRITE_ACTION_NOT_FOUND", "message": f"Action not found: {action_id}"},
        )

    return JSONResponse(
        status_code=200,
        content={"action": action.to_dict()},
    )


@router.get("/bridge/write/schemas")
async def console_bridge_get_schemas(
    request: Request,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> JSONResponse:
    """Get available action schemas.

    Args:
        request: FastAPI request.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        JSON response with available action schemas.
    """
    _require_console_auth(request, x_admin_token, console_session)

    return JSONResponse(
        status_code=200,
        content={"schemas": ACTION_SCHEMAS},
    )


# =============================================================================
# Etapa 3.7: Intake Assistido
# =============================================================================


@router.get("/intake", response_class=HTMLResponse)
async def console_intake_page(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    mode: str = Query("nl", description="Mode: nl or dsl"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console intake page - assisted definition creation.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        mode: Input mode (nl for natural language, dsl for manual DSL).
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Rendered intake page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    return templates.TemplateResponse(
        "intake.html",
        {
            "request": request,
            "active_page": "intake",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "mode": mode,
            "draft": None,
            "gaps": None,
            "sir_json": None,
            "errors": None,
        },
    )


@router.post("/intake", response_class=HTMLResponse)
async def console_intake_process(
    request: Request,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    mode: str = Form("nl"),
    input_text: str = Form(...),
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Process intake input (NL or DSL) and generate draft.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        mode: Input mode (nl or dsl).
        input_text: Input text (NL description or DSL source).
        _csrf_token: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Rendered draft page HTML with gaps.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)
    _require_csrf_token(request, console_session, csrf_token_form)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    errors = []
    draft = None
    gaps = []
    sir_json = None
    ir_result = None

    if mode == "dsl":
        # DSL mode: parse DSL directly to IR
        try:
            ir_result = parse_dsl(input_text)
            # No draft/gaps for DSL mode - go directly to result
        except IDLSyntaxError as e:
            loc = e.location
            if loc:
                errors.append(f"DSL Syntax Error (line {loc.line}, col {loc.column}): {e.message}")
            else:
                errors.append(f"DSL Syntax Error: {e.message}")
        except IDLSemanticError as e:
            errors.append(f"DSL Semantic Error: {e.message}")
        except Exception as e:
            errors.append(f"DSL Parse Error: {str(e)}")
    else:
        # NL mode: extract -> draft -> gaps
        try:
            extractor = get_extractor()
            sir = extractor.extract(input_text)
            sir_json = json.dumps(sir.to_dict())

            draft = generate_draft(sir)
            gaps = detect_gaps(sir, draft)
        except Exception as e:
            errors.append(f"NL Processing Error: {str(e)}")

    # If DSL mode succeeded, show result directly
    if mode == "dsl" and ir_result and not errors:
        return templates.TemplateResponse(
            "intake_result.html",
            {
                "request": request,
                "active_page": "intake",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "mode": mode,
                "final_idl": ir_result,
                "final_idl_json": json.dumps(ir_result, indent=2, sort_keys=True),
                "is_valid": True,
                "validation_errors": [],
            },
        )

    # NL mode or errors: show draft page
    return templates.TemplateResponse(
        "intake_draft.html",
        {
            "request": request,
            "active_page": "intake",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "mode": mode,
            "draft": draft,
            "draft_json": json.dumps(draft, indent=2, sort_keys=True) if draft else None,
            "gaps": gaps,
            "gaps_json": json.dumps([g.to_dict() for g in gaps]) if gaps else "[]",
            "sir_json": sir_json,
            "errors": errors,
            "input_text": input_text,
        },
    )


@router.post("/intake/answer", response_class=HTMLResponse)
async def console_intake_answer(
    request: Request,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    sir_json: str = Form(...),
    draft_json: str = Form(...),
    gaps_json: str = Form(...),
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Process gap answers and update draft.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        sir_json: Serialized SIR.
        draft_json: Serialized draft.
        gaps_json: Serialized gaps.
        _csrf_token: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Rendered draft page with updated gaps.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)
    _require_csrf_token(request, console_session, csrf_token_form)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    errors = []

    try:
        # Parse state from form
        draft = json.loads(draft_json)
        gaps_data = json.loads(gaps_json)
        gaps = [Gap.from_dict(g) for g in gaps_data]

        # Collect answers from form data
        form_data = await request.form()
        answers_list = []
        for key, value in form_data.items():
            if key.startswith("answer_"):
                question_id = key[7:]  # Remove "answer_" prefix
                # Convert value based on type hints in question_id
                if value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                elif value.isdigit():
                    value = int(value)
                elif value.replace(".", "", 1).isdigit():
                    value = float(value)
                answers_list.append(Answer(question_id=question_id, value=value))

        if answers_list:
            answers = AnswersV1(answers=answers_list)
            updated_draft, remaining_gaps = apply_answers(draft, gaps, answers)
            draft = updated_draft
            gaps = remaining_gaps

    except Exception as e:
        errors.append(f"Answer Processing Error: {str(e)}")

    return templates.TemplateResponse(
        "intake_draft.html",
        {
            "request": request,
            "active_page": "intake",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "mode": "nl",
            "draft": draft,
            "draft_json": json.dumps(draft, indent=2, sort_keys=True) if draft else None,
            "gaps": gaps,
            "gaps_json": json.dumps([g.to_dict() for g in gaps]) if gaps else "[]",
            "sir_json": sir_json,
            "errors": errors,
            "input_text": "",
        },
    )


@router.post("/intake/finalize", response_class=HTMLResponse)
async def console_intake_finalize(
    request: Request,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    draft_json: str = Form(...),
    gaps_json: str = Form("[]"),
    allow_gaps: bool = Form(False),
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Finalize draft and produce final IDL.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        draft_json: Serialized draft.
        gaps_json: Serialized remaining gaps.
        allow_gaps: Allow finalization with gaps.
        _csrf_token: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Rendered result page with final IDL.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)
    _require_csrf_token(request, console_session, csrf_token_form)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    errors = []
    final_idl = None
    is_valid = False

    try:
        draft = json.loads(draft_json)
        gaps_data = json.loads(gaps_json)
        remaining_gaps = [Gap.from_dict(g) for g in gaps_data]

        final_idl = finalize(draft, remaining_gaps, allow_gaps=allow_gaps)
        is_valid, validation_errors = validate_final(final_idl)
        errors.extend(validation_errors)

    except ValueError as e:
        errors.append(str(e))
    except Exception as e:
        errors.append(f"Finalization Error: {str(e)}")

    if final_idl is None:
        # Failed to finalize - return to draft page
        try:
            draft = json.loads(draft_json)
            gaps_data = json.loads(gaps_json)
            gaps = [Gap.from_dict(g) for g in gaps_data]
        except Exception:
            draft = None
            gaps = []

        return templates.TemplateResponse(
            "intake_draft.html",
            {
                "request": request,
                "active_page": "intake",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "mode": "nl",
                "draft": draft,
                "draft_json": draft_json,
                "gaps": gaps,
                "gaps_json": gaps_json,
                "sir_json": "",
                "errors": errors,
                "input_text": "",
            },
        )

    return templates.TemplateResponse(
        "intake_result.html",
        {
            "request": request,
            "active_page": "intake",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "mode": "nl",
            "final_idl": final_idl,
            "final_idl_json": json.dumps(final_idl, indent=2, sort_keys=True),
            "is_valid": is_valid,
            "validation_errors": errors,
        },
    )


@router.get("/intake/export")
async def console_intake_export(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    format: str = Query("ir", description="Export format: ir or dsl"),
    idl_json: str = Query(..., description="IDL JSON to export"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> JSONResponse:
    """Export final IDL as downloadable JSON.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        format: Export format (ir or dsl).
        idl_json: IDL JSON to export.
        x_admin_token: Admin token from header.

    Returns:
        JSON response with Content-Disposition for download.
    """
    _require_console_auth(request, x_admin_token, console_session)

    if format == "dsl":
        # DSL export not implemented (IR→DSL reverse not available)
        return JSONResponse(
            status_code=501,
            content={
                "code": "DSL_EXPORT_NOT_IMPLEMENTED",
                "message": "DSL export is not yet implemented. Use IR format.",
            },
        )

    try:
        idl = json.loads(idl_json)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={
                "code": "INVALID_JSON",
                "message": "Invalid IDL JSON",
            },
        )

    # Generate filename
    name = idl.get("name", "policy")
    filename = f"{name}-{institution_id[:8]}.ir.json"

    return JSONResponse(
        content=idl,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
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
    console_session: Optional[str] = Cookie(None),
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
    _require_console_auth(request, x_admin_token, console_session)

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
    console_session: Optional[str] = Cookie(None),
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
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

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
                "csrf_token": csrf_token or "",
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
            "csrf_token": csrf_token or "",
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
    console_session: Optional[str] = Cookie(None),
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
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

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
            "csrf_token": csrf_token or "",
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
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console proof page - run offline bundle verification.

    Executes verify_bundle_offline and displays PASS/FAIL result with checks table.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        show_json: Whether to show raw JSON result.
        x_admin_token: Admin token from header.

    Returns:
        Rendered proof page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get institution config for pinned_release_id
    config = _get_institution_config_info(institution_id)
    pinned_release_id = config.get("pinned_release_id")

    # Get bundle path for institution
    bundle_path = _get_bundle_path_for_institution(institution_id)

    if not bundle_path:
        return templates.TemplateResponse(
            "proof.html",
            {
                "request": request,
                "active_page": "proof",
                "admin_token": x_admin_token or "",
                "csrf_token": csrf_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "bundle_path": None,
                "result": None,
                "checks": [],
                "pinned_release_id": pinned_release_id,
                "error": "No bundle found for institution",
                "show_json": show_json,
                "result_json": None,
            },
        )

    # Run offline verification
    try:
        result = verify_bundle_offline(bundle_path)
        result_dict = result.to_dict()
        checks = _generate_proof_checks(result_dict)
    except Exception as e:
        return templates.TemplateResponse(
            "proof.html",
            {
                "request": request,
                "active_page": "proof",
                "admin_token": x_admin_token or "",
                "csrf_token": csrf_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "bundle_path": str(bundle_path),
                "result": None,
                "checks": [],
                "pinned_release_id": pinned_release_id,
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
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "bundle_path": str(bundle_path),
            "result": result_dict,
            "checks": checks,
            "pinned_release_id": pinned_release_id,
            "error": None,
            "show_json": show_json,
            "result_json": json.dumps(result_dict, indent=2) if show_json else None,
        },
    )


@router.get("/proof.json")
async def console_proof_json(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> JSONResponse:
    """Export proof verification result as JSON (downloadable).

    Executes verify_bundle_offline and returns raw JSON result.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        JSON response with Content-Disposition for download.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Get bundle path for institution
    bundle_path = _get_bundle_path_for_institution(institution_id)

    if not bundle_path:
        return JSONResponse(
            content={
                "passed": False,
                "error_code": "BUNDLE_NOT_FOUND",
                "error_message": "No bundle found for institution",
                "institution_id": institution_id,
                "dept_id": dept_id,
            },
            headers={
                "Content-Disposition": f'attachment; filename="proof-{institution_id[:8]}.json"'
            },
        )

    # Run offline verification
    try:
        result = verify_bundle_offline(bundle_path)
        result_dict = result.to_dict()
    except Exception as e:
        return JSONResponse(
            content={
                "passed": False,
                "error_code": "VERIFICATION_ERROR",
                "error_message": str(e),
                "institution_id": institution_id,
                "dept_id": dept_id,
            },
            headers={
                "Content-Disposition": f'attachment; filename="proof-{institution_id[:8]}.json"'
            },
        )

    # Add metadata
    result_dict["institution_id"] = institution_id
    result_dict["dept_id"] = dept_id
    result_dict["bundle_path"] = str(bundle_path)

    return JSONResponse(
        content=result_dict,
        headers={
            "Content-Disposition": f'attachment; filename="proof-{institution_id[:8]}.json"'
        },
    )


# =============================================================================
# Etapa 3.4: Mandates Governance Routes
# =============================================================================


def _get_governed_mandates_info(
    institution_id: str, dept_id: Optional[str]
) -> List[Dict[str, Any]]:
    """Get governed mandates with proposal info for display."""
    governed = list_governed_mandates(institution_id, dept_id)
    result = []
    for mandate_id, mandate_data in governed.items():
        result.append({
            "mandate_id": mandate_id,
            "mandate_data": mandate_data,
        })
    return result


@router.get("/mandates", response_class=HTMLResponse)
async def console_mandates(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console mandates page - list effective mandates.

    Shows merged mandates (bundle + governed) with source indication.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered mandates page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get effective mandates
    mandates_info = _get_effective_mandates_info(institution_id, dept_id)

    # Get governed mandates for source identification
    governed = list_governed_mandates(institution_id, dept_id)
    governed_ids = set(governed.keys())

    # Get bundle mandates for comparison
    bundle_def = get_bundle_mandates(dept_id)
    bundle_ids = set()
    if bundle_def:
        bundle_ids = {m.mandate_id for m in bundle_def.mandates}

    # Mark source for each effective mandate
    effective_mandates = []
    for m in mandates_info.get("mandates", []):
        mandate_id = m["mandate_id"]
        source = "bundle"
        if mandate_id in governed_ids:
            source = "governed"
        effective_mandates.append({
            **m,
            "source": source,
        })

    return templates.TemplateResponse(
        "mandates.html",
        {
            "request": request,
            "active_page": "mandates",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "effective_mandates": effective_mandates,
            "source": mandates_info.get("source", "none"),
            "governed_mandates": _get_governed_mandates_info(institution_id, dept_id),
            "governed_count": len(governed_ids),
        },
    )


@router.get("/mandates/proposals", response_class=HTMLResponse)
async def console_mandates_proposals(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console mandates proposals page - list mandate change proposals.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        status_filter: Optional filter by status (OPEN, DECIDED).
        x_admin_token: Admin token from header.

    Returns:
        Rendered proposals list page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get proposals
    proposals = list_mandate_proposals(
        institution_id,
        dept_id,
        status_filter=status_filter,
        limit=50,
    )

    # Convert to dicts for template
    proposals_list = [p.to_dict() for p in proposals]

    return templates.TemplateResponse(
        "mandates_proposals.html",
        {
            "request": request,
            "active_page": "mandates",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "proposals": proposals_list,
            "status_filter": status_filter,
            "total_proposals": len(proposals_list),
        },
    )


@router.get("/mandates/proposals/new", response_class=HTMLResponse)
async def console_mandates_proposals_new(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console new mandate proposal page - form to create proposal.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered new proposal form page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    return templates.TemplateResponse(
        "mandates_proposal_new.html",
        {
            "request": request,
            "active_page": "mandates",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "error": None,
        },
    )


@router.post("/mandates/proposals")
async def console_mandates_proposals_create(
    request: Request,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    operation: str = Form(...),
    mandate_id: str = Form(...),
    mandate_data: str = Form(""),
    reason: str = Form(...),
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Create a new mandate proposal.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        operation: Operation type (create, update, revoke).
        mandate_id: Target mandate ID.
        mandate_data: JSON string of mandate data.
        reason: Reason for the proposal.
        _csrf_token: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to proposals list on success.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)
    _require_csrf_token(request, console_session, csrf_token_form)

    # Parse mandate_data JSON (only for create/update)
    parsed_mandate_data = None
    if operation in ("create", "update"):
        if not mandate_data.strip():
            # Return to form with error
            institutions = _get_institutions_list()
            institution_name = next(
                (i["name"] for i in institutions if i["id"] == institution_id),
                institution_id,
            )
            return templates.TemplateResponse(
                "mandates_proposal_new.html",
                {
                    "request": request,
                    "active_page": "mandates",
                    "admin_token": x_admin_token or "",
                    "csrf_token": csrf_token or "",
                    "institution_id": institution_id,
                    "institution_name": institution_name,
                    "dept_id": dept_id,
                    "error": "Mandate data is required for create/update operations",
                },
                status_code=400,
            )
        try:
            parsed_mandate_data = json.loads(mandate_data)
        except json.JSONDecodeError as e:
            # Return to form with error
            institutions = _get_institutions_list()
            institution_name = next(
                (i["name"] for i in institutions if i["id"] == institution_id),
                institution_id,
            )
            return templates.TemplateResponse(
                "mandates_proposal_new.html",
                {
                    "request": request,
                    "active_page": "mandates",
                    "admin_token": x_admin_token or "",
                    "csrf_token": csrf_token or "",
                    "institution_id": institution_id,
                    "institution_name": institution_name,
                    "dept_id": dept_id,
                    "error": f"Invalid JSON in mandate data: {e}",
                },
                status_code=400,
            )

    # Create proposal
    proposal, error_code, error_msg = propose_mandate_change(
        institution_id=institution_id,
        operation=operation,
        mandate_id=mandate_id,
        mandate_data=parsed_mandate_data,
        reason=reason,
        actor_id="CONSOLE",
        dept_id=dept_id or None,
    )

    if error_code:
        # Return to form with error
        institutions = _get_institutions_list()
        institution_name = next(
            (i["name"] for i in institutions if i["id"] == institution_id),
            institution_id,
        )
        return templates.TemplateResponse(
            "mandates_proposal_new.html",
            {
                "request": request,
                "active_page": "mandates",
                "admin_token": x_admin_token or "",
                "csrf_token": csrf_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "error": error_msg,
            },
            status_code=400,
        )

    # Redirect to proposals list
    redirect_url = f"/console/mandates/proposals?institution_id={institution_id}"
    if dept_id:
        redirect_url += f"&dept_id={dept_id}"
    redirect_url += "&success=proposal_created"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/mandates/proposals/{proposal_id}", response_class=HTMLResponse)
async def console_mandates_proposal_detail(
    request: Request,
    proposal_id: str,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console mandate proposal detail page - view and decide on proposal.

    Args:
        request: FastAPI request.
        proposal_id: Proposal UUID.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered proposal detail page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get proposal
    states = load_proposal_state(institution_id, dept_id)
    proposal = states.get(proposal_id)

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PROPOSAL_NOT_FOUND",
                "message": f"Proposal '{proposal_id}' not found",
            },
        )

    # Get current mandate for diff (if update/revoke)
    current_mandate = None
    if proposal.mandate_operation in ("update", "revoke"):
        # Check governed mandates first
        governed = list_governed_mandates(institution_id, dept_id)
        if proposal.mandate_id in governed:
            current_mandate = governed[proposal.mandate_id]
        else:
            # Check bundle mandates
            bundle_def = get_bundle_mandates(dept_id)
            if bundle_def:
                for m in bundle_def.mandates:
                    if m.mandate_id == proposal.mandate_id:
                        current_mandate = {
                            "mandate_id": m.mandate_id,
                            "endpoint_sig": m.endpoint_sig,
                            "phase": m.phase,
                            "allowed_roles": m.allowed_roles,
                            "limits": [l.__dict__ for l in m.limits] if m.limits else [],
                        }
                        break

    return templates.TemplateResponse(
        "mandates_proposal_detail.html",
        {
            "request": request,
            "active_page": "mandates",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "proposal": proposal.to_dict(),
            "current_mandate": current_mandate,
            "current_mandate_json": json.dumps(current_mandate, indent=2) if current_mandate else None,
            "proposed_mandate_json": json.dumps(proposal.mandate_data, indent=2) if proposal.mandate_data else None,
            "error": None,
        },
    )


@router.post("/mandates/proposals/{proposal_id}/decide")
async def console_mandates_proposal_decide(
    request: Request,
    proposal_id: str,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    decision: str = Form(...),
    decision_reason: str = Form(""),
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Decide on a mandate proposal (approve or reject).

    Args:
        request: FastAPI request.
        proposal_id: Proposal UUID.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        decision: Decision (approve or reject).
        decision_reason: Reason for the decision.
        _csrf_token: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to proposals list on success.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)
    _require_csrf_token(request, console_session, csrf_token_form)

    # Reject requires reason
    if decision == "reject" and not decision_reason.strip():
        # Get proposal for re-rendering
        states = load_proposal_state(institution_id, dept_id)
        proposal = states.get(proposal_id)
        if not proposal:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "PROPOSAL_NOT_FOUND",
                    "message": f"Proposal '{proposal_id}' not found",
                },
            )

        institutions = _get_institutions_list()
        institution_name = next(
            (i["name"] for i in institutions if i["id"] == institution_id),
            institution_id,
        )

        return templates.TemplateResponse(
            "mandates_proposal_detail.html",
            {
                "request": request,
                "active_page": "mandates",
                "admin_token": x_admin_token or "",
                "csrf_token": csrf_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "proposal": proposal.to_dict(),
                "current_mandate": None,
                "current_mandate_json": None,
                "proposed_mandate_json": json.dumps(proposal.mandate_data, indent=2) if proposal.mandate_data else None,
                "error": "Reason is required for rejection",
            },
            status_code=400,
        )

    # Decide on proposal
    result, error_code, error_msg = decide_mandate_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        decision=decision,
        reason=decision_reason if decision_reason.strip() else None,
        actor_id="CONSOLE",
        dept_id=dept_id or None,
    )

    if error_code:
        # Get proposal for re-rendering
        states = load_proposal_state(institution_id, dept_id)
        proposal = states.get(proposal_id)

        institutions = _get_institutions_list()
        institution_name = next(
            (i["name"] for i in institutions if i["id"] == institution_id),
            institution_id,
        )

        return templates.TemplateResponse(
            "mandates_proposal_detail.html",
            {
                "request": request,
                "active_page": "mandates",
                "admin_token": x_admin_token or "",
                "csrf_token": csrf_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "proposal": proposal.to_dict() if proposal else {},
                "current_mandate": None,
                "current_mandate_json": None,
                "proposed_mandate_json": json.dumps(proposal.mandate_data, indent=2) if proposal and proposal.mandate_data else None,
                "error": error_msg,
            },
            status_code=400,
        )

    # Redirect to proposals list with success message
    redirect_url = f"/console/mandates/proposals?institution_id={institution_id}"
    if dept_id:
        redirect_url += f"&dept_id={dept_id}"
    success_msg = "proposal_approved" if decision == "approve" else "proposal_rejected"
    redirect_url += f"&success={success_msg}"

    return RedirectResponse(url=redirect_url, status_code=303)


# =============================================================================
# Etapa 3.5: EGE Console Routes
# =============================================================================


def _get_ege_overview_info(institution_id: str) -> Dict[str, Any]:
    """Get EGE overview information for an institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Dict with drift_status, pin_status, proposals count, etc.
    """
    # Drift status
    drift_state = load_drift_state(institution_id)
    if not drift_state:
        drift_state = check_drift(institution_id)

    # Pin status
    pin_status_obj, _, _ = get_pin_status(institution_id)

    # Proposals
    proposals = list_ege_proposals(institution_id, limit=100)
    open_count = sum(1 for p in proposals if p.status == "OPEN")

    # Current release
    current_release = get_current_release_id(institution_id)

    # Config
    config = get_effective_config(institution_id)

    # Rollback check
    blocked, _, block_msg = check_rollback_blocked(institution_id)
    can_rollback = (
        config.pinned_release_id is not None
        and config.pinned_release_id != current_release
    )

    return {
        "drift_status": drift_state.status if drift_state else "UNKNOWN",
        "drift_checked_at": drift_state.checked_at if drift_state else None,
        "pin_status": pin_status_obj.to_dict() if pin_status_obj else {},
        "pinned_release_id": config.pinned_release_id,
        "open_proposals_count": open_count,
        "total_proposals_count": len(proposals),
        "current_release_id": current_release,
        "can_rollback": can_rollback,
        "rollback_blocked": blocked,
        "rollback_block_reason": block_msg,
    }


def _get_release_trace(
    institution_id: str,
    release_id: str,
) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
    """Load trace for a release.

    Args:
        institution_id: Institution UUID.
        release_id: Release ID (YYYYMMDD-HHMMSS).

    Returns:
        Tuple of (trace_dict, bundle_name, error_message).
    """
    bundles_root = get_bundles_root_for_institution(institution_id)
    release_dir = bundles_root / "releases" / release_id

    if not release_dir.exists():
        return None, None, "Release not found"

    # Find bundle
    try:
        for bundle_dir in release_dir.iterdir():
            if bundle_dir.is_dir():
                trace_path = bundle_dir / "trace.json"
                if trace_path.exists():
                    try:
                        with open(trace_path) as f:
                            trace = json.load(f)
                        return trace, bundle_dir.name, None
                    except Exception as e:
                        return None, bundle_dir.name, f"Failed to read trace: {e}"
                else:
                    return None, bundle_dir.name, "Trace not available for this release"
    except OSError:
        pass

    return None, None, "No bundle found in release"


@router.get("/ege", response_class=HTMLResponse)
async def console_ege(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console EGE overview page.

    Shows drift status, pin status, proposals summary, and rollback capability.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered EGE overview page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get EGE overview info
    ege_info = _get_ege_overview_info(institution_id)

    # Check for success/error messages in query params
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    rolled_back_to = request.query_params.get("rolled_back_to")

    return templates.TemplateResponse(
        "ege.html",
        {
            "request": request,
            "active_page": "ege",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            **ege_info,
            "success": success,
            "error": error,
            "rolled_back_to": rolled_back_to,
        },
    )


@router.get("/ege/proposals", response_class=HTMLResponse)
async def console_ege_proposals(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console EGE proposals list page.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        status_filter: Optional filter by status (OPEN, DECIDED).
        x_admin_token: Admin token from header.

    Returns:
        Rendered proposals list page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get proposals
    proposals = list_ege_proposals(institution_id, limit=50)

    # Filter by status if provided
    if status_filter:
        proposals = [p for p in proposals if p.status == status_filter]

    # Convert to dicts for template
    proposals_list = [p.to_dict() for p in proposals]

    return templates.TemplateResponse(
        "ege_proposals.html",
        {
            "request": request,
            "active_page": "ege",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "proposals": proposals_list,
            "status_filter": status_filter,
            "total_proposals": len(proposals_list),
        },
    )


@router.get("/ege/proposals/{proposal_id}", response_class=HTMLResponse)
async def console_ege_proposal_detail(
    request: Request,
    proposal_id: str,
    institution_id: str = Query(..., description="Institution UUID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console EGE proposal detail page.

    Args:
        request: FastAPI request.
        proposal_id: Proposal UUID.
        institution_id: Institution UUID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered proposal detail page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get proposal
    states = load_ege_proposal_state(institution_id)
    proposal = states.get(proposal_id)

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PROPOSAL_NOT_FOUND",
                "message": f"Proposal '{proposal_id}' not found",
            },
        )

    # Check if this is a PIN_UPDATE proposal
    is_pin = is_pin_update_proposal(institution_id, proposal_id)
    pin_metadata = None
    if is_pin:
        pin_metadata = get_pin_proposal_metadata(institution_id, proposal_id)

    return templates.TemplateResponse(
        "ege_proposal_detail.html",
        {
            "request": request,
            "active_page": "ege",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "proposal": proposal.to_dict(),
            "is_pin_proposal": is_pin,
            "pin_metadata": pin_metadata,
        },
    )


@router.get("/ege/releases", response_class=HTMLResponse)
async def console_ege_releases(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console EGE releases list page.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered releases list page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get releases
    releases = list_releases(institution_id, limit=20)

    # Get current and pinned
    current_release = get_current_release_id(institution_id)
    config = get_effective_config(institution_id)
    pinned_release = config.pinned_release_id

    return templates.TemplateResponse(
        "ege_releases.html",
        {
            "request": request,
            "active_page": "ege",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "releases": releases,
            "total_releases": len(releases),
            "current_release_id": current_release,
            "pinned_release_id": pinned_release,
        },
    )


@router.get("/ege/traces/{release_id}", response_class=HTMLResponse)
async def console_ege_trace(
    request: Request,
    release_id: str,
    institution_id: str = Query(..., description="Institution UUID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console EGE trace view page.

    Args:
        request: FastAPI request.
        release_id: Release ID (YYYYMMDD-HHMMSS).
        institution_id: Institution UUID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered trace view page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get trace
    trace, bundle_name, error = _get_release_trace(institution_id, release_id)

    return templates.TemplateResponse(
        "ege_trace.html",
        {
            "request": request,
            "active_page": "ege",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "release_id": release_id,
            "bundle_name": bundle_name,
            "has_trace": trace is not None,
            "trace": trace,
            "trace_unavailable_reason": error,
        },
    )


@router.get("/ege/rollback/confirm", response_class=HTMLResponse)
async def console_ege_rollback_confirm(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console EGE rollback confirmation page.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        x_admin_token: Admin token from header.

    Returns:
        Rendered rollback confirmation page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get current release info
    current_release = get_current_release_id(institution_id)

    # Get config for pinned info
    config = get_effective_config(institution_id)
    pinned_release_id = config.pinned_release_id

    # Get pinned release path to get bundle name
    pinned_path, err_code, err_msg = get_pinned_release_path(institution_id)
    target_bundle_path = str(pinned_path) if pinned_path else None

    # Check if will activate safe mode
    will_activate_safe_mode = pinned_path is None

    # Check if blocked
    blocked, _, block_reason = check_rollback_blocked(institution_id)

    return templates.TemplateResponse(
        "ege_rollback_confirm.html",
        {
            "request": request,
            "active_page": "ege",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "current_release_id": current_release,
            "pinned_release_id": pinned_release_id,
            "target_bundle_path": target_bundle_path,
            "will_activate_safe_mode": will_activate_safe_mode,
            "rollback_blocked": blocked,
            "block_reason": block_reason,
            "no_pinned_error": err_msg if not pinned_path else None,
        },
    )


@router.post("/ege/rollback")
async def console_ege_rollback(
    request: Request,
    institution_id: str = Form(...),
    confirm: str = Form(...),
    reason: str = Form(""),
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Execute governed rollback to pinned release.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        confirm: Must be "yes" to execute.
        reason: Optional reason for rollback.
        _csrf_token: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to EGE overview with success/error message.
    """
    _require_console_auth(request, x_admin_token, console_session)
    _require_csrf_token(request, console_session, csrf_token_form)

    # Verify confirmation
    if confirm != "yes":
        redirect_url = f"/console/ege?institution_id={institution_id}&error=not_confirmed"
        return RedirectResponse(url=redirect_url, status_code=303)

    # Get current release for the audit trail
    current_release = get_current_release_id(institution_id)

    # Execute governed rollback
    result = execute_governed_rollback(
        institution_id=institution_id,
        failed_release_id=current_release,
        reason=reason if reason.strip() else "Manual rollback via console",
    )

    # Build redirect URL
    redirect_url = f"/console/ege?institution_id={institution_id}"

    if result.success:
        redirect_url += f"&success=rollback_executed&rolled_back_to={result.rolled_back_to}"
    elif result.safe_mode_activated:
        redirect_url += "&error=safe_mode_activated"
    else:
        # URL encode the error message
        from urllib.parse import quote
        error_msg = quote(result.error_message or "Unknown error")
        redirect_url += f"&error=rollback_failed&message={error_msg}"

    return RedirectResponse(url=redirect_url, status_code=303)


# =============================================================================
# Onboarding Routes (Etapa 4.2)
# =============================================================================

from engine.console.templates_registry import list_templates, get_template
from engine.console.bundle_generator import (
    generate_bundle_from_template,
    get_institution_bundle_path,
    BundleGenerationResult,
)


@router.get("/onboarding")
async def console_onboarding(
    request: Request,
    step: int = Query(1, ge=1, le=4),
    institution_id: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Onboarding wizard for new institutions.

    Args:
        request: FastAPI request.
        step: Current wizard step (1-4).
        institution_id: Institution UUID (for steps 2+).
        error: Error message from previous action.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        HTML response with onboarding wizard.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    institutions = _get_institutions_list()
    available_templates = list_templates()

    # Get institution name if selected
    institution_name = None
    if institution_id:
        institution_name = next(
            (i["name"] for i in institutions if i["id"] == institution_id),
            institution_id,
        )

    # For step 4, run proof verification
    proof_result = None
    if step == 4 and institution_id:
        bundle_path = get_institution_bundle_path(institution_id)
        if bundle_path:
            proof_result = verify_bundle_offline(bundle_path)

    return templates.TemplateResponse(
        "onboarding.html",
        {
            "request": request,
            "step": step,
            "institutions": institutions,
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "departments": t.departments,
                }
                for t in available_templates
            ],
            "institution_id": institution_id,
            "institution_name": institution_name,
            "proof_result": proof_result.to_dict() if proof_result else None,
            "error": error,
            "csrf_token": csrf_token,
            "active_page": "onboarding",
        },
    )


@router.post("/onboarding/create-institution")
async def console_onboarding_create_institution(
    request: Request,
    slug: str = Form(...),
    display_name: Optional[str] = Form(None),
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Create a new institution for onboarding.

    Args:
        request: FastAPI request.
        slug: Unique institution slug.
        display_name: Optional display name.
        csrf_token_form: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to step 2 on success, or step 1 with error.
    """
    _require_console_auth(request, x_admin_token, console_session)
    _require_csrf_token(request, console_session, csrf_token_form)

    # Create institution via registry
    registry = get_institutions_registry()
    institution, error_code, error_msg = registry.create(
        slug=slug,
        display_name=display_name if display_name else None,
    )

    if not institution:
        from urllib.parse import quote
        error_text = quote(error_msg or error_code or "Failed to create institution")
        return RedirectResponse(
            url=f"/console/onboarding?step=1&error={error_text}",
            status_code=303,
        )

    # Success - redirect to step 2
    return RedirectResponse(
        url=f"/console/onboarding?step=2&institution_id={institution.institution_id}",
        status_code=303,
    )


@router.post("/onboarding/generate-bundle")
async def console_onboarding_generate_bundle(
    request: Request,
    institution_id: str = Form(...),
    template_id: str = Form(...),
    csrf_token_form: Optional[str] = Form(None, alias="_csrf_token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Generate bundle from template for institution.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        template_id: Template identifier.
        csrf_token_form: CSRF token from form.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to step 4 (proof result).
    """
    _require_console_auth(request, x_admin_token, console_session)
    _require_csrf_token(request, console_session, csrf_token_form)

    # Generate bundle from template
    result = generate_bundle_from_template(
        institution_id=institution_id,
        template_id=template_id,
        overwrite=True,  # Allow regeneration
    )

    if result.success:
        # Success - redirect to step 4 (proof result)
        return RedirectResponse(
            url=f"/console/onboarding?step=4&institution_id={institution_id}",
            status_code=303,
        )
    else:
        # Failed - redirect to step 2 with error
        from urllib.parse import quote
        error_text = quote(result.error_message or result.error_code or "Bundle generation failed")
        return RedirectResponse(
            url=f"/console/onboarding?step=2&institution_id={institution_id}&error={error_text}",
            status_code=303,
        )


@router.get("/onboarding/proof")
async def console_onboarding_proof(
    request: Request,
    institution_id: str = Query(...),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Show proof result for institution bundle.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to step 4 with proof result.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Just redirect to step 4
    return RedirectResponse(
        url=f"/console/onboarding?step=4&institution_id={institution_id}",
        status_code=303,
    )


# =============================================================================
# Etapa 4.4: Policies Governance Console Routes
# =============================================================================


@router.get("/policies", response_class=HTMLResponse)
async def console_policies(
    request: Request,
    institution_id: str = Query(...),
    dept_id: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Policies governance dashboard.

    Shows effective policies (bundle + governed) with source indicators.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        HTML page with policies list.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Get institutions for header dropdown
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Load effective policies
    effective_def = get_effective_policies(institution_id, dept_id)
    bundle_def = get_bundle_policies(dept_id)
    governed = list_governed_policies(institution_id, dept_id)

    # Build policies list with source info
    effective_policies = []
    if effective_def:
        governed_ids = set(governed.keys())
        for policy in effective_def.policies:
            source = "governed" if policy.policy_id in governed_ids else "bundle"
            effective_policies.append({
                "policy_id": policy.policy_id,
                "rule_type": policy.rule_type,
                "field_path": policy.field_path,
                "phase": policy.phase,
                "endpoint_sig": policy.endpoint_sig,
                "value": policy.value,
                "message": policy.message,
                "source": source,
            })

    # Determine overall source
    if governed and bundle_def:
        source = "merged"
    elif governed:
        source = "governed"
    elif bundle_def:
        source = "bundle"
    else:
        source = "none"

    # Build governed list
    governed_list = [
        {"policy_id": pid, "policy_data": pdata}
        for pid, pdata in governed.items()
    ]

    return templates.TemplateResponse(
        "policies.html",
        {
            "request": request,
            "active_page": "policies",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "institutions": institutions,
            "dept_id": dept_id,
            "effective_policies": effective_policies,
            "governed_policies": governed_list,
            "governed_count": len(governed),
            "source": source,
        },
    )


@router.get("/policies/proposals", response_class=HTMLResponse)
async def console_policies_proposals(
    request: Request,
    institution_id: str = Query(...),
    dept_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    success: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """List policy proposals.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        status: Optional status filter (OPEN or DECIDED).
        success: Optional success message key.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        HTML page with proposals list.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Get institutions for header dropdown
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Load proposals
    proposals = list_policy_proposals(
        institution_id=institution_id,
        dept_id=dept_id,
        status_filter=status,
        limit=100,
    )

    # Convert to dicts
    proposals_list = [p.to_dict() for p in proposals]

    # Determine success message
    success_message = None
    if success == "proposal_created":
        success_message = "Proposal created successfully"
    elif success == "proposal_approved":
        success_message = "Proposal approved and applied"
    elif success == "proposal_rejected":
        success_message = "Proposal rejected"

    return templates.TemplateResponse(
        "policies_proposals.html",
        {
            "request": request,
            "active_page": "policies",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "institutions": institutions,
            "dept_id": dept_id,
            "proposals": proposals_list,
            "status_filter": status,
            "success_message": success_message,
        },
    )


@router.get("/policies/proposals/new", response_class=HTMLResponse)
async def console_policies_proposal_new(
    request: Request,
    institution_id: str = Query(...),
    dept_id: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """New policy proposal form.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        HTML form for creating a proposal.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Get institutions for header dropdown
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get CSRF token
    csrf_token = get_csrf_from_cookie(console_session) if console_session else None

    return templates.TemplateResponse(
        "policies_proposal_new.html",
        {
            "request": request,
            "active_page": "policies",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "institutions": institutions,
            "dept_id": dept_id,
            "csrf_token": csrf_token,
            "error": None,
        },
    )


@router.post("/policies/proposals")
async def console_policies_proposal_create(
    request: Request,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    operation: str = Form(...),
    policy_id: str = Form(...),
    policy_data: Optional[str] = Form(None),
    reason: str = Form(...),
    csrf_token: str = Form(...),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Create a new policy proposal.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        operation: create, update, or revoke.
        policy_id: Target policy ID.
        policy_data: JSON policy data (for create/update).
        reason: Reason for proposal.
        csrf_token: CSRF token.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to proposals list on success, or form with error.
    """
    _require_console_auth(request, x_admin_token, console_session)
    _verify_csrf_token(csrf_token, console_session)

    # Parse policy data if provided
    parsed_policy_data = None
    if policy_data and operation in ("create", "update"):
        try:
            parsed_policy_data = json.loads(policy_data)
        except json.JSONDecodeError as e:
            # Return to form with error
            institutions = _get_institutions_list()
            institution_name = next(
                (i["name"] for i in institutions if i["id"] == institution_id),
                institution_id,
            )
            return templates.TemplateResponse(
                "policies_proposal_new.html",
                {
                    "request": request,
                    "active_page": "policies",
                    "admin_token": x_admin_token or "",
                    "institution_id": institution_id,
                    "institution_name": institution_name,
                    "institutions": institutions,
                    "dept_id": dept_id,
                    "csrf_token": get_csrf_from_cookie(console_session) if console_session else None,
                    "error": f"Invalid JSON: {e}",
                },
                status_code=400,
            )

    # Create proposal
    proposal, error_code, error_msg = propose_policy_change(
        institution_id=institution_id,
        operation=operation,
        policy_id=policy_id,
        policy_data=parsed_policy_data,
        reason=reason,
        actor_id="console",
        dept_id=dept_id if dept_id else None,
    )

    if error_code:
        # Return to form with error
        institutions = _get_institutions_list()
        institution_name = next(
            (i["name"] for i in institutions if i["id"] == institution_id),
            institution_id,
        )
        return templates.TemplateResponse(
            "policies_proposal_new.html",
            {
                "request": request,
                "active_page": "policies",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "institutions": institutions,
                "dept_id": dept_id,
                "csrf_token": get_csrf_from_cookie(console_session) if console_session else None,
                "error": error_msg,
            },
            status_code=400,
        )

    # Redirect to proposals list
    redirect_url = f"/console/policies/proposals?institution_id={institution_id}"
    if dept_id:
        redirect_url += f"&dept_id={dept_id}"
    redirect_url += "&success=proposal_created"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/policies/proposals/{proposal_id}", response_class=HTMLResponse)
async def console_policies_proposal_detail(
    request: Request,
    proposal_id: str,
    institution_id: str = Query(...),
    dept_id: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Policy proposal detail page.

    Args:
        request: FastAPI request.
        proposal_id: Proposal UUID.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        HTML page with proposal details and decide form.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Get institutions for header dropdown
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Load proposal
    proposal = get_policy_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        dept_id=dept_id,
    )

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "POLICY_PROPOSAL_NOT_FOUND",
                "message": f"Proposal '{proposal_id}' not found",
            },
        )

    # Get CSRF token
    csrf_token = get_csrf_from_cookie(console_session) if console_session else None

    return templates.TemplateResponse(
        "policies_proposal_detail.html",
        {
            "request": request,
            "active_page": "policies",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "institutions": institutions,
            "dept_id": dept_id,
            "proposal": proposal.to_dict(),
            "proposed_policy_json": json.dumps(proposal.policy_data, indent=2) if proposal.policy_data else None,
            "csrf_token": csrf_token,
            "error": None,
        },
    )


@router.post("/policies/proposals/{proposal_id}/decide")
async def console_policies_proposal_decide(
    request: Request,
    proposal_id: str,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    decision: str = Form(...),
    reason: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Decide on a policy proposal.

    Args:
        request: FastAPI request.
        proposal_id: Proposal UUID.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        decision: approve or reject.
        reason: Optional decision reason.
        csrf_token: CSRF token.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to proposals list.
    """
    _require_console_auth(request, x_admin_token, console_session)
    _verify_csrf_token(csrf_token, console_session)

    # Decide on proposal
    proposal, error_code, error_msg = decide_policy_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        decision=decision,
        reason=reason,
        actor_id="console",
        dept_id=dept_id if dept_id else None,
    )

    if error_code:
        # Return to detail page with error
        institutions = _get_institutions_list()
        institution_name = next(
            (i["name"] for i in institutions if i["id"] == institution_id),
            institution_id,
        )

        return templates.TemplateResponse(
            "policies_proposal_detail.html",
            {
                "request": request,
                "active_page": "policies",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "proposal": proposal.to_dict() if proposal else {},
                "proposed_policy_json": json.dumps(proposal.policy_data, indent=2) if proposal and proposal.policy_data else None,
                "csrf_token": get_csrf_from_cookie(console_session) if console_session else None,
                "error": error_msg,
            },
            status_code=400,
        )

    # Redirect to proposals list
    redirect_url = f"/console/policies/proposals?institution_id={institution_id}"
    if dept_id:
        redirect_url += f"&dept_id={dept_id}"
    success_msg = "proposal_approved" if decision == "approve" else "proposal_rejected"
    redirect_url += f"&success={success_msg}"

    return RedirectResponse(url=redirect_url, status_code=303)


# =============================================================================
# Etapa 4.4: Autonomy Governance Console Routes
# =============================================================================


@router.get("/autonomy", response_class=HTMLResponse)
async def console_autonomy(
    request: Request,
    institution_id: str = Query(...),
    dept_id: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Autonomy governance dashboard.

    Shows effective autonomy (bundle + governed) with source indicators.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        HTML page with autonomy settings.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Get institutions for header dropdown
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Load effective autonomy
    effective_def = get_effective_autonomy(institution_id, dept_id)
    bundle_def = get_bundle_autonomy(dept_id)
    governed = list_governed_autonomy(institution_id, dept_id)

    # Determine level source
    level_source = "governed" if governed.current_level is not None else "bundle"

    # Build rules list with source info
    effective_rules = []
    if effective_def:
        governed_rule_ids = set(governed.rules.keys())
        for rule in effective_def.rules:
            source = "governed" if rule.rule_id in governed_rule_ids else "bundle"
            effective_rules.append({
                "rule_id": rule.rule_id,
                "endpoint_sig": rule.endpoint_sig,
                "phase": rule.phase,
                "required_level": rule.required_level,
                "source": source,
            })

    # Determine overall source
    has_governed = governed.current_level is not None or governed.rules
    if has_governed and bundle_def:
        source = "merged"
    elif has_governed:
        source = "governed"
    elif bundle_def:
        source = "bundle"
    else:
        source = "none"

    return templates.TemplateResponse(
        "autonomy.html",
        {
            "request": request,
            "active_page": "autonomy",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "institutions": institutions,
            "dept_id": dept_id,
            "current_level": effective_def.current_level if effective_def else 4,
            "level_source": level_source,
            "bundle_level": bundle_def.current_level if bundle_def else None,
            "governed_level": governed.current_level,
            "effective_rules": effective_rules,
            "governed_rules_count": len(governed.rules),
            "source": source,
        },
    )


@router.get("/autonomy/proposals", response_class=HTMLResponse)
async def console_autonomy_proposals(
    request: Request,
    institution_id: str = Query(...),
    dept_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    success: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """List autonomy proposals.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        status: Optional status filter (OPEN or DECIDED).
        success: Optional success message key.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        HTML page with proposals list.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Get institutions for header dropdown
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Load proposals
    proposals = list_autonomy_proposals(
        institution_id=institution_id,
        dept_id=dept_id,
        status_filter=status,
        limit=100,
    )

    # Convert to dicts
    proposals_list = [p.to_dict() for p in proposals]

    # Determine success message
    success_message = None
    if success == "proposal_created":
        success_message = "Proposal created successfully"
    elif success == "proposal_approved":
        success_message = "Proposal approved and applied"
    elif success == "proposal_rejected":
        success_message = "Proposal rejected"

    return templates.TemplateResponse(
        "autonomy_proposals.html",
        {
            "request": request,
            "active_page": "autonomy",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "institutions": institutions,
            "dept_id": dept_id,
            "proposals": proposals_list,
            "status_filter": status,
            "success_message": success_message,
        },
    )


@router.get("/autonomy/proposals/new", response_class=HTMLResponse)
async def console_autonomy_proposal_new(
    request: Request,
    institution_id: str = Query(...),
    dept_id: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """New autonomy proposal form.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        HTML form for creating a proposal.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Get institutions for header dropdown
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Get current autonomy for context
    effective_def = get_effective_autonomy(institution_id, dept_id)
    current_level = effective_def.current_level if effective_def else 4

    # Get CSRF token
    csrf_token = get_csrf_from_cookie(console_session) if console_session else None

    return templates.TemplateResponse(
        "autonomy_proposal_new.html",
        {
            "request": request,
            "active_page": "autonomy",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "institutions": institutions,
            "dept_id": dept_id,
            "current_level": current_level,
            "csrf_token": csrf_token,
            "error": None,
        },
    )


@router.post("/autonomy/proposals")
async def console_autonomy_proposal_create(
    request: Request,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    operation: str = Form(...),
    rule_id: Optional[str] = Form(None),
    autonomy_data: str = Form(...),
    reason: str = Form(...),
    csrf_token: str = Form(...),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Create a new autonomy proposal.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        operation: update_level, create_rule, update_rule, or revoke_rule.
        rule_id: Target rule ID (for rule operations).
        autonomy_data: JSON autonomy data.
        reason: Reason for proposal.
        csrf_token: CSRF token.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to proposals list on success, or form with error.
    """
    _require_console_auth(request, x_admin_token, console_session)
    _verify_csrf_token(csrf_token, console_session)

    # Parse autonomy data
    try:
        parsed_autonomy_data = json.loads(autonomy_data)
    except json.JSONDecodeError as e:
        # Return to form with error
        institutions = _get_institutions_list()
        institution_name = next(
            (i["name"] for i in institutions if i["id"] == institution_id),
            institution_id,
        )
        effective_def = get_effective_autonomy(institution_id, dept_id)
        return templates.TemplateResponse(
            "autonomy_proposal_new.html",
            {
                "request": request,
                "active_page": "autonomy",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "institutions": institutions,
                "dept_id": dept_id,
                "current_level": effective_def.current_level if effective_def else 4,
                "csrf_token": get_csrf_from_cookie(console_session) if console_session else None,
                "error": f"Invalid JSON: {e}",
            },
            status_code=400,
        )

    # Create proposal
    proposal, error_code, error_msg = propose_autonomy_change(
        institution_id=institution_id,
        operation=operation,
        rule_id=rule_id if rule_id else None,
        autonomy_data=parsed_autonomy_data,
        reason=reason,
        actor_id="console",
        dept_id=dept_id if dept_id else None,
    )

    if error_code:
        # Return to form with error
        institutions = _get_institutions_list()
        institution_name = next(
            (i["name"] for i in institutions if i["id"] == institution_id),
            institution_id,
        )
        effective_def = get_effective_autonomy(institution_id, dept_id)
        return templates.TemplateResponse(
            "autonomy_proposal_new.html",
            {
                "request": request,
                "active_page": "autonomy",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "institutions": institutions,
                "dept_id": dept_id,
                "current_level": effective_def.current_level if effective_def else 4,
                "csrf_token": get_csrf_from_cookie(console_session) if console_session else None,
                "error": error_msg,
            },
            status_code=400,
        )

    # Redirect to proposals list
    redirect_url = f"/console/autonomy/proposals?institution_id={institution_id}"
    if dept_id:
        redirect_url += f"&dept_id={dept_id}"
    redirect_url += "&success=proposal_created"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/autonomy/proposals/{proposal_id}", response_class=HTMLResponse)
async def console_autonomy_proposal_detail(
    request: Request,
    proposal_id: str,
    institution_id: str = Query(...),
    dept_id: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Autonomy proposal detail page.

    Args:
        request: FastAPI request.
        proposal_id: Proposal UUID.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        HTML page with proposal details and decide form.
    """
    _require_console_auth(request, x_admin_token, console_session)

    # Get institutions for header dropdown
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    # Load proposal
    proposal = get_autonomy_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        dept_id=dept_id,
    )

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "AUTONOMY_PROPOSAL_NOT_FOUND",
                "message": f"Proposal '{proposal_id}' not found",
            },
        )

    # Get CSRF token
    csrf_token = get_csrf_from_cookie(console_session) if console_session else None

    return templates.TemplateResponse(
        "autonomy_proposal_detail.html",
        {
            "request": request,
            "active_page": "autonomy",
            "admin_token": x_admin_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "institutions": institutions,
            "dept_id": dept_id,
            "proposal": proposal.to_dict(),
            "proposed_autonomy_json": json.dumps(proposal.autonomy_data, indent=2) if proposal.autonomy_data else None,
            "csrf_token": csrf_token,
            "error": None,
        },
    )


@router.post("/autonomy/proposals/{proposal_id}/decide")
async def console_autonomy_proposal_decide(
    request: Request,
    proposal_id: str,
    institution_id: str = Form(...),
    dept_id: Optional[str] = Form(None),
    decision: str = Form(...),
    reason: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> RedirectResponse:
    """Decide on an autonomy proposal.

    Args:
        request: FastAPI request.
        proposal_id: Proposal UUID.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        decision: approve or reject.
        reason: Optional decision reason.
        csrf_token: CSRF token.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Redirect to proposals list.
    """
    _require_console_auth(request, x_admin_token, console_session)
    _verify_csrf_token(csrf_token, console_session)

    # Decide on proposal
    proposal, error_code, error_msg = decide_autonomy_proposal(
        institution_id=institution_id,
        proposal_id=proposal_id,
        decision=decision,
        reason=reason,
        actor_id="console",
        dept_id=dept_id if dept_id else None,
    )

    if error_code:
        # Return to detail page with error
        institutions = _get_institutions_list()
        institution_name = next(
            (i["name"] for i in institutions if i["id"] == institution_id),
            institution_id,
        )

        return templates.TemplateResponse(
            "autonomy_proposal_detail.html",
            {
                "request": request,
                "active_page": "autonomy",
                "admin_token": x_admin_token or "",
                "institution_id": institution_id,
                "institution_name": institution_name,
                "dept_id": dept_id,
                "proposal": proposal.to_dict() if proposal else {},
                "proposed_autonomy_json": json.dumps(proposal.autonomy_data, indent=2) if proposal and proposal.autonomy_data else None,
                "csrf_token": get_csrf_from_cookie(console_session) if console_session else None,
                "error": error_msg,
            },
            status_code=400,
        )

    # Redirect to proposals list
    redirect_url = f"/console/autonomy/proposals?institution_id={institution_id}"
    if dept_id:
        redirect_url += f"&dept_id={dept_id}"
    success_msg = "proposal_approved" if decision == "approve" else "proposal_rejected"
    redirect_url += f"&success={success_msg}"

    return RedirectResponse(url=redirect_url, status_code=303)


# ============================================================
# Agent Ops Routes (Etapa 4.6)
# ============================================================


@router.get("/agents", response_class=HTMLResponse)
async def console_agents(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console agents page - list of registered agents.

    Etapa 4.6: Agent Ops / Observability minima

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID to filter by.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Rendered agents list page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get agent registry
    agents = get_agent_registry(institution_id, dept_id)

    # Also get unique actors from ledger (for actors not in registry)
    ledger_actors = list_unique_actors(institution_id, dept_id)

    # Merge: registry agents + ledger-only actors
    registered_actor_ids = {a.actor_id for a in agents}
    agents_data = []

    for agent in agents:
        stats = get_actor_stats(institution_id, agent.actor_id, dept_id)
        agents_data.append({
            "actor_id": agent.actor_id,
            "name": agent.name,
            "roles": agent.roles,
            "dept_ids": agent.dept_ids,
            "registered": True,
            "total_events": stats["total_events"],
            "denied_count": stats["denied_count"],
            "last_active": stats["last_active"],
        })

    # Add ledger-only actors (not in registry)
    for actor_id in ledger_actors:
        if actor_id not in registered_actor_ids:
            stats = get_actor_stats(institution_id, actor_id, dept_id)
            agents_data.append({
                "actor_id": actor_id,
                "name": actor_id,  # Use actor_id as name
                "roles": [],
                "dept_ids": [],
                "registered": False,
                "total_events": stats["total_events"],
                "denied_count": stats["denied_count"],
                "last_active": stats["last_active"],
            })

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    return templates.TemplateResponse(
        "agents.html",
        {
            "request": request,
            "active_page": "agents",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "agents": agents_data,
        },
    )


@router.get("/agents/{actor_id}", response_class=HTMLResponse)
async def console_agent_detail(
    request: Request,
    actor_id: str,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    limit: int = Query(50, description="Max events to show"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console agent detail page - events and stats for an actor.

    Etapa 4.6: Agent Ops / Observability minima

    Args:
        request: FastAPI request.
        actor_id: Actor ID to view.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        limit: Max events to show.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Rendered agent detail page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Get agent from registry (if registered)
    agent = get_agent_by_actor_id(institution_id, actor_id)

    # Anti-inference: if actor doesn't exist in registry AND has no events, 404
    stats = get_actor_stats(institution_id, actor_id, dept_id)
    if agent is None and stats["total_events"] == 0:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": "Actor not found.",
            },
        )

    # Get recent events
    recent_events = list_events_by_actor(institution_id, actor_id, limit, dept_id)

    # Get denied events for this actor
    denied_events = list_denied_events(
        institution_id,
        gate=None,
        dept_id=dept_id,
        actor_id=actor_id,
        limit=limit,
    )

    # Build agent data
    agent_data = {
        "actor_id": actor_id,
        "name": agent.name if agent else actor_id,
        "description": agent.description if agent else "",
        "roles": agent.roles if agent else [],
        "dept_ids": agent.dept_ids if agent else [],
        "registered": agent is not None,
        "created_at": agent.created_at if agent else None,
        "created_by": agent.created_by if agent else None,
    }

    # Convert events to dicts for template
    recent_events_data = [
        {
            "timestamp": e.timestamp,
            "event_type": e.event_type,
            "step": e.step,
            "dept_id": e.dept_id,
            "case_id": e.case_id,
            "payload": e.payload,
        }
        for e in recent_events
    ]

    denied_events_data = [
        {
            "timestamp": e.timestamp,
            "event_type": e.event_type,
            "step": e.step,
            "dept_id": e.dept_id,
            "case_id": e.case_id,
            "reason": e.payload.get("reason") or e.payload.get("code") or "-",
            "payload": e.payload,
        }
        for e in denied_events
    ]

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    return templates.TemplateResponse(
        "agents_detail.html",
        {
            "request": request,
            "active_page": "agents",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "agent": agent_data,
            "stats": stats,
            "recent_events": recent_events_data,
            "denied_events": denied_events_data,
        },
    )


@router.get("/denied", response_class=HTMLResponse)
async def console_denied(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    gate: Optional[str] = Query(None, description="Filter by gate (rbac, policy, mandate, sod, autonomy)"),
    actor_id: Optional[str] = Query(None, description="Filter by actor ID"),
    limit: int = Query(100, description="Max events to show"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> HTMLResponse:
    """Console denied attempts page - blocked operations.

    Etapa 4.6: Agent Ops / Observability minima

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        gate: Optional gate filter.
        actor_id: Optional actor ID filter.
        limit: Max events to show.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        Rendered denied attempts page HTML.
    """
    _, csrf_token = _require_console_auth(request, x_admin_token, console_session)

    # Validate gate if provided
    available_gates = sorted(GATE_EVENT_TYPES.keys())
    if gate is not None and gate not in available_gates:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_GATE",
                "message": f"Invalid gate '{gate}'. Valid gates: {available_gates}",
            },
        )

    # Get denied events
    try:
        denied_events = list_denied_events(
            institution_id,
            gate=gate,
            dept_id=dept_id,
            actor_id=actor_id,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_GATE",
                "message": str(e),
            },
        )

    # Convert to template data
    denied_events_data = [
        {
            "timestamp": e.timestamp,
            "actor_id": e.actor_id,
            "event_type": e.event_type,
            "step": e.step,
            "dept_id": e.dept_id,
            "case_id": e.case_id,
            "reason": e.payload.get("reason") or e.payload.get("code") or "-",
            "payload": e.payload,
        }
        for e in denied_events
    ]

    # Get institution name
    institutions = _get_institutions_list()
    institution_name = next(
        (i["name"] for i in institutions if i["id"] == institution_id),
        institution_id,
    )

    return templates.TemplateResponse(
        "denied.html",
        {
            "request": request,
            "active_page": "denied",
            "admin_token": x_admin_token or "",
            "csrf_token": csrf_token or "",
            "institution_id": institution_id,
            "institution_name": institution_name,
            "dept_id": dept_id,
            "denied_events": denied_events_data,
            "filters": {
                "gate": gate,
                "actor_id": actor_id,
                "dept_id": dept_id,
            },
            "available_gates": available_gates,
        },
    )


# ============================================================================
# GAP 4: Agent Requests Endpoints
# ============================================================================


@router.get("/agent-requests", response_class=JSONResponse)
async def list_agent_requests(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    status: Optional[str] = Query(None, description="Filter by status (pending, resolved, expired)"),
    agent_id: Optional[str] = Query(None, description="Filter by agent actor ID"),
    limit: int = Query(100, description="Max results"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> JSONResponse:
    """List agent requests for an institution.

    GAP 4: Agents as governed actors - admin visibility into auto-solicitations.

    Args:
        request: FastAPI request.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        status: Optional status filter.
        agent_id: Optional agent ID filter.
        limit: Maximum results to return.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        JSON response with list of agent requests.
    """
    _, _ = _require_console_auth(request, x_admin_token, console_session)

    try:
        registry = get_agent_requests_registry(institution_id, dept_id)
        requests = registry.list_requests(status=status, agent_id=agent_id, limit=limit)

        return JSONResponse(
            content={
                "institution_id": institution_id,
                "dept_id": dept_id,
                "count": len(requests),
                "requests": [r.to_dict() for r in requests],
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "AGENT_REQUESTS_ERROR",
                "message": str(e),
            },
        )


@router.get("/agent-requests/{request_id}", response_class=JSONResponse)
async def get_agent_request(
    request: Request,
    request_id: str,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    console_session: Optional[str] = Cookie(None),
) -> JSONResponse:
    """Get a specific agent request by ID.

    GAP 4: Agents as governed actors - admin visibility.

    Args:
        request: FastAPI request.
        request_id: Request UUID.
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        x_admin_token: Admin token from header.
        console_session: Session cookie.

    Returns:
        JSON response with agent request details.
    """
    _, _ = _require_console_auth(request, x_admin_token, console_session)

    try:
        registry = get_agent_requests_registry(institution_id, dept_id)
        agent_request = registry.get_request(request_id)

        if not agent_request:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "AGENT_REQUEST_NOT_FOUND",
                    "message": f"Agent request not found: {request_id}",
                },
            )

        return JSONResponse(content=agent_request.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "AGENT_REQUESTS_ERROR",
                "message": str(e),
            },
        )
