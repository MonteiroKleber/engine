"""Department-namespaced Support API endpoints.

Routes under /d/{dept}/support/... that delegate to shared support handlers.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from engine.core.actor_context import ActorContext
from engine.core.dept_context import get_request_dept
from .dependencies import get_actor_context
from .support import create_ticket_handler, get_ticket_handler

router = APIRouter(prefix="/d/{dept}/support", tags=["dept-support"])


@router.post("/tickets")
async def create_ticket_dept(
    dept: str,
    request: Request,
    actor: ActorContext = Depends(get_actor_context),
) -> JSONResponse:
    """Create a support ticket in a specific department.

    Department is validated by the dept_routing_middleware before this handler runs.
    """
    # dept_id is already validated and set on request.state by middleware
    dept_id = get_request_dept(request)
    return await create_ticket_handler(request, actor, dept_id=dept_id)


@router.get("/tickets/{ticket_id}")
async def get_ticket_dept(
    dept: str,
    ticket_id: str,
    request: Request,
    actor: ActorContext = Depends(get_actor_context),
) -> JSONResponse:
    """Get a support ticket by ID from a specific department."""
    dept_id = get_request_dept(request)
    return await get_ticket_handler(request, ticket_id, actor, dept_id=dept_id)
