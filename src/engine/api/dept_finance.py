"""Department-namespaced Finance API endpoints.

Routes under /d/{dept}/finance/... that delegate to shared finance handlers.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from engine.core.actor_context import ActorContext
from engine.core.dept_context import get_request_dept
from engine.core.institution_context import DEFAULT_INSTITUTION_ID, get_request_institution_id
from engine.core.legacy_telemetry import record_legacy_invocation
from .dependencies import get_actor_context
from .finance import create_expense_handler, get_expense_handler

router = APIRouter(prefix="/d/{dept}/finance", tags=["dept-finance"])


@router.post("/expenses")
async def create_expense_dept(
    dept: str,
    request: Request,
    actor: ActorContext = Depends(get_actor_context),
) -> JSONResponse:
    """Create an expense in a specific department.

    Department is validated by the dept_routing_middleware before this handler runs.
    """
    # dept_id is already validated and set on request.state by middleware
    dept_id = get_request_dept(request)
    record_legacy_invocation(
        institution_id=(
            get_request_institution_id(request)
            or request.headers.get("X-Institution-Id")
            or request.headers.get("X-Tenant-Id")
            or DEFAULT_INSTITUTION_ID
        ),
        endpoint_sig="POST /d/{dept}/finance/expenses",
        method="POST",
        path=str(request.url.path),
        dept_id=dept_id,
    )
    return await create_expense_handler(request, actor, dept_id=dept_id)


@router.get("/expenses/{expense_id}")
async def get_expense_dept(
    dept: str,
    expense_id: str,
    request: Request,
    actor: ActorContext = Depends(get_actor_context),
) -> JSONResponse:
    """Get an expense by ID from a specific department."""
    dept_id = get_request_dept(request)
    record_legacy_invocation(
        institution_id=(
            get_request_institution_id(request)
            or request.headers.get("X-Institution-Id")
            or request.headers.get("X-Tenant-Id")
            or DEFAULT_INSTITUTION_ID
        ),
        endpoint_sig="GET /d/{dept}/finance/expenses/{expense_id}",
        method="GET",
        path=str(request.url.path),
        dept_id=dept_id,
    )
    return await get_expense_handler(request, expense_id, actor, dept_id=dept_id)
