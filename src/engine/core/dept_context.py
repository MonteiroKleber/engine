"""Department context handling for multi-department bundles."""

import re
from typing import Optional

from fastapi import HTTPException, Request

from engine.core.errors import DEPT_UNKNOWN, DEPT_MODE_REQUIRED
from engine.loader.load_bundle import get_bundle_context


# Pattern to match /d/{dept}/ at the start of a path
DEPT_PATH_PATTERN = re.compile(r"^/d/([^/]+)/")


def resolve_dept_from_path(path: str) -> Optional[str]:
    """Extract department from path if present.

    Args:
        path: Request path (e.g., "/d/finance/finance/expenses")

    Returns:
        Department name if path matches /d/{dept}/..., None otherwise.
    """
    match = DEPT_PATH_PATTERN.match(path)
    if match:
        return match.group(1)
    return None


def validate_dept(dept: str) -> None:
    """Validate that department exists in multi-mode bundle.

    Args:
        dept: Department name to validate.

    Raises:
        HTTPException: 400 DEPT_UNKNOWN if dept doesn't exist.
        HTTPException: 409 DEPT_MODE_REQUIRED if not in multi mode.
    """
    bundle_ctx = get_bundle_context()

    if bundle_ctx is None:
        # No bundle loaded - shouldn't happen in normal operation
        raise HTTPException(
            status_code=503,
            detail={"code": "BUNDLE_NOT_LOADED", "message": "Bundle not loaded"},
        )

    if bundle_ctx.mode != "multi":
        raise HTTPException(
            status_code=409,
            detail={
                "code": DEPT_MODE_REQUIRED,
                "message": "Department routing requires multi-department bundle",
            },
        )

    if dept not in bundle_ctx.departments:
        raise HTTPException(
            status_code=400,
            detail={
                "code": DEPT_UNKNOWN,
                "message": f"Unknown department: {dept}",
            },
        )


def validate_legacy_finance_route() -> Optional[str]:
    """Validate legacy /finance/... route and return dept_id if applicable.

    In single mode: returns None (legacy behavior)
    In multi mode: returns "finance" if dept exists, raises 409 otherwise

    Returns:
        dept_id to use, or None for single mode

    Raises:
        HTTPException: 409 DEPT_MODE_REQUIRED if multi mode but no finance dept
    """
    bundle_ctx = get_bundle_context()

    if bundle_ctx is None:
        # No bundle loaded - shouldn't happen in normal operation
        return None

    if bundle_ctx.mode == "single":
        # Single mode: legacy behavior, no dept_id
        return None

    # Multi mode: legacy route is alias for finance dept
    if "finance" in bundle_ctx.departments:
        return "finance"

    # Multi mode but no finance dept - require explicit dept route
    raise HTTPException(
        status_code=409,
        detail={
            "code": DEPT_MODE_REQUIRED,
            "message": "Legacy /finance route requires 'finance' department in multi-mode bundle",
        },
    )


def set_request_dept(request: Request, dept: Optional[str]) -> None:
    """Set department ID on request state.

    Args:
        request: FastAPI request object.
        dept: Department ID or None.
    """
    request.state.dept_id = dept


def get_request_dept(request: Request) -> Optional[str]:
    """Get department ID from request state.

    Args:
        request: FastAPI request object.

    Returns:
        Department ID or None if not set.
    """
    return getattr(request.state, "dept_id", None)


def get_ledger_step_name(base_step: str, dept_id: Optional[str]) -> str:
    """Get ledger step name with optional dept prefix.

    Args:
        base_step: Base step name (e.g., "RBAC:expense.create")
        dept_id: Department ID or None

    Returns:
        Step name, prefixed with "DEPT:{dept}:" if dept_id is set
    """
    if dept_id:
        return f"DEPT:{dept_id}:{base_step}"
    return base_step
