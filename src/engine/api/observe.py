"""Read-only observability endpoints.

These endpoints provide lightweight visibility into ledger activity by actor_id.
They are intentionally read-only and require admin auth.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from engine.agent_ops.read_model import is_denied_event
from engine.core.actor_tokens import get_actor_tokens_registry
from engine.core.admin_auth import require_admin_auth
from engine.core.institution_context import resolve_institution_id
from engine.core.ledger import get_ledger_for_institution


router = APIRouter(prefix="/v1/observe", tags=["observe"])


class ObserveActorItem(BaseModel):
    actor_id: str
    name: str
    registered: bool
    roles: List[str] = Field(default_factory=list)
    dept_ids: List[str] = Field(default_factory=list)
    total_events: int
    denied_count: int
    last_active: Optional[str] = None


class ObserveActorsResponse(BaseModel):
    items: List[ObserveActorItem]
    next_cursor: Optional[str] = None


@router.get("/actors", response_model=ObserveActorsResponse)
async def observe_actors(limit: int = 50, request: Request = None):
    """List actors observed in the institution ledger with basic stats.

    Requires:
    - `X-Institution-Id` (or legacy `X-Tenant-Id`)
    - Admin auth (`X-Admin-Key` or bootstrap `X-Admin-Token` where allowed)
    """
    if request is None:  # pragma: no cover (FastAPI always provides Request)
        raise RuntimeError("Request is required")

    institution_id = resolve_institution_id(request, require_header=True)
    require_admin_auth(request, institution_id)

    ledger = get_ledger_for_institution(institution_id)
    events = ledger.get_all_events()

    # Aggregate per-actor stats from the ledger (single pass, deterministic).
    stats_by_actor: Dict[str, Dict[str, Any]] = {}
    for event in events:
        actor_id = event.actor_id
        if not actor_id:
            continue

        stats = stats_by_actor.get(actor_id)
        if stats is None:
            stats = {
                "total_events": 0,
                "denied_count": 0,
                "last_active": None,  # ISO string
                "dept_ids": set(),  # type: Set[str]
            }
            stats_by_actor[actor_id] = stats

        stats["total_events"] += 1
        if is_denied_event(event):
            stats["denied_count"] += 1

        if event.dept_id:
            stats["dept_ids"].add(event.dept_id)

        # `timestamp` is already ISO (LedgerEvent), keep most recent.
        # Compare as string works because ISO 8601 sorts lexicographically.
        ts = event.timestamp
        if ts and (stats["last_active"] is None or ts > stats["last_active"]):
            stats["last_active"] = ts

    # Join with actor token registry (if any) to show roles + registered flag.
    registry = get_actor_tokens_registry()
    registry_actor_roles: Dict[str, Set[str]] = {}
    for actor in registry.list_actors(institution_id):
        if actor.status != "active":
            continue
        registry_actor_roles.setdefault(actor.actor_id, set()).update(actor.roles)

    # Sort by last_active desc, then actor_id for determinism.
    actor_ids = list(stats_by_actor.keys())
    actor_ids.sort(
        key=lambda a: (
            stats_by_actor[a]["last_active"] is not None,
            stats_by_actor[a]["last_active"] or "",
            a,
        ),
        reverse=True,
    )

    items: List[ObserveActorItem] = []
    for actor_id in actor_ids[: max(0, int(limit))]:
        stats = stats_by_actor[actor_id]
        roles = sorted(registry_actor_roles.get(actor_id, set()))
        items.append(
            ObserveActorItem(
                actor_id=actor_id,
                name=actor_id,
                registered=actor_id in registry_actor_roles,
                roles=roles,
                dept_ids=sorted(stats["dept_ids"]),
                total_events=stats["total_events"],
                denied_count=stats["denied_count"],
                last_active=stats["last_active"],
            )
        )

    return ObserveActorsResponse(items=items, next_cursor=None)

