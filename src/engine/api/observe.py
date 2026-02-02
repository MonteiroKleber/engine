"""Read-only observability endpoints.

These endpoints provide lightweight visibility into ledger activity by actor_id.
They are intentionally read-only and require admin auth.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, Query, Request
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


class ObserveEventItem(BaseModel):
    seq: int
    occurred_at: str
    event_type: str
    gate: Optional[str] = None
    allowed: Optional[bool] = None
    code: Optional[str] = None
    reason: Optional[str] = None
    actor_id: str
    actor_roles: List[str] = Field(default_factory=list)
    case_id: Optional[str] = None
    dept_id: Optional[str] = None
    step: Optional[str] = None
    request_id: Optional[str] = None
    explanation: str = Field(default="", description="Human-readable explanation")
    # Requester tracking (for runtime jobs initiated by Console users)
    requester_user_id: Optional[str] = Field(None, description="Console user ID who initiated the request")
    requester_user_name: Optional[str] = Field(None, description="Console user name/email")
    # Full payload (security-redacted)
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload with sensitive keys redacted")


class ObserveActorDetailResponse(BaseModel):
    actor: ObserveActorItem
    recent_events: List[ObserveEventItem] = Field(default_factory=list)
    denied_events: List[ObserveEventItem] = Field(default_factory=list)


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


# Keys that should be redacted from payload for security
_SENSITIVE_KEYS = frozenset({
    "token",
    "secret",
    "admin_key",
    "password",
    "api_key",
    "plaintext_secret",
})

# Prefixes that indicate sensitive data
_SENSITIVE_PREFIXES = ("encrypted_",)


def _redact_sensitive(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive keys from payload for security.

    Removes values for keys matching:
    - Exact matches: token, secret, admin_key, password, api_key, plaintext_secret
    - Prefix matches: encrypted_*

    Args:
        payload: Original event payload.

    Returns:
        Copy of payload with sensitive values replaced by "[REDACTED]".
    """
    if not payload:
        return {}

    result = {}
    for key, value in payload.items():
        key_lower = key.lower()

        # Check exact matches
        if key_lower in _SENSITIVE_KEYS:
            result[key] = "[REDACTED]"
            continue

        # Check prefix matches
        if any(key_lower.startswith(prefix) for prefix in _SENSITIVE_PREFIXES):
            result[key] = "[REDACTED]"
            continue

        # Recursively redact nested dicts
        if isinstance(value, dict):
            result[key] = _redact_sensitive(value)
        else:
            result[key] = value

    return result


def _compute_explanation(event_type: str, allowed: Optional[bool], payload: Dict[str, Any]) -> str:
    """Compute deterministic human-readable explanation from event fields.

    Mapping is based only on event_type + allowed + payload fields.
    No heuristics or external lookups.

    Args:
        event_type: The event type string.
        allowed: Whether the action was allowed (True/False/None).
        payload: Event payload dict.

    Returns:
        Human-readable explanation string.
    """
    decision = payload.get("decision")

    # RBAC decisions
    if event_type == "RBAC_DECISION":
        if allowed is False or decision == "deny":
            return "Permissão negada pelo RBAC"
        if allowed is True or decision == "allow":
            return "Permissão concedida pelo RBAC"

    # Approval flow
    if event_type == "APPROVAL_REQUESTED":
        return "Aprovação solicitada"

    if event_type == "APPROVAL_DECIDED":
        if decision == "approve":
            return "Aprovação concedida"
        if decision == "reject":
            return "Aprovação rejeitada"

    # Actor token events
    if event_type == "ACTOR_TOKEN_CREATED":
        return "Token de ator criado"

    if event_type == "ACTOR_TOKEN_REVOKED":
        return "Token de ator revogado"

    # Fallback: "Evento: <EVENT_TYPE>"
    return f"Evento: {event_type}"


def _ledger_event_to_observe_item(event: Any) -> ObserveEventItem:
    """Convert a LedgerEvent to ObserveEventItem."""
    payload = event.payload or {}
    allowed = payload.get("allowed")
    code = payload.get("code")

    # Back-compat: older RBAC_DECISION events used payload.decision ("allow"/"deny")
    # and payload.permission, but did not include payload.allowed or payload.code.
    # Infer both so downstream tooling (portal) can count denials and translate.
    if event.event_type == "RBAC_DECISION" and allowed is None:
        decision = payload.get("decision")
        if decision in ("allow", "deny"):
            allowed = decision == "allow"
            if code is None:
                code = "RBAC_ALLOWED" if allowed else "RBAC_DENIED"

    # Compute explanation
    explanation = _compute_explanation(event.event_type, allowed, payload)

    return ObserveEventItem(
        seq=event.seq,
        occurred_at=event.timestamp or "",
        event_type=event.event_type,
        gate=payload.get("gate"),
        allowed=allowed,
        code=code,
        reason=payload.get("reason") or payload.get("message"),
        actor_id=event.actor_id,
        actor_roles=list(event.actor_roles) if event.actor_roles else [],
        case_id=event.case_id,
        dept_id=event.dept_id,
        step=event.step,
        request_id=event.request_id,
        explanation=explanation,
        requester_user_id=payload.get("requester_user_id"),
        requester_user_name=payload.get("requester_user_name"),
        payload=_redact_sensitive(payload),
    )


@router.get("/actors/{actor_id}", response_model=ObserveActorDetailResponse)
async def observe_actor_detail(
    actor_id: str,
    limit: int = 50,
    dept_id: Optional[str] = None,
    request: Request = None,
):
    """Get detailed information about a specific actor.

    Returns actor stats plus recent events and denied events.

    Requires:
    - `X-Institution-Id` (or legacy `X-Tenant-Id`)
    - Admin auth (`X-Admin-Key` or bootstrap `X-Admin-Token` where allowed)
    """
    if request is None:  # pragma: no cover
        raise RuntimeError("Request is required")

    institution_id = resolve_institution_id(request, require_header=True)
    require_admin_auth(request, institution_id)

    ledger = get_ledger_for_institution(institution_id)
    all_events = ledger.get_all_events()

    # Filter events for this actor (and optionally dept_id)
    actor_events = []
    for event in all_events:
        if event.actor_id != actor_id:
            continue
        if dept_id and event.dept_id != dept_id:
            continue
        actor_events.append(event)

    # Check actor token registry for roles and registered status
    registry = get_actor_tokens_registry()
    actor_roles: Set[str] = set()
    registered = False
    for actor in registry.list_actors(institution_id):
        if actor.actor_id == actor_id and actor.status == "active":
            registered = True
            actor_roles.update(actor.roles)

    # If no events and not registered, return 404
    if not actor_events and not registered:
        raise HTTPException(status_code=404, detail="Actor not found")

    # Compute stats
    total_events = len(actor_events)
    denied_count = sum(1 for e in actor_events if is_denied_event(e))
    dept_ids: Set[str] = set()
    last_active: Optional[str] = None

    for event in actor_events:
        if event.dept_id:
            dept_ids.add(event.dept_id)
        ts = event.timestamp
        if ts and (last_active is None or ts > last_active):
            last_active = ts

    # Build actor item
    actor_item = ObserveActorItem(
        actor_id=actor_id,
        name=actor_id,
        registered=registered,
        roles=sorted(actor_roles),
        dept_ids=sorted(dept_ids),
        total_events=total_events,
        denied_count=denied_count,
        last_active=last_active,
    )

    # Recent events (most recent first, limited)
    sorted_events = sorted(actor_events, key=lambda e: e.timestamp or "", reverse=True)
    recent_events = [_ledger_event_to_observe_item(e) for e in sorted_events[:limit]]

    # Denied events (most recent first, limited)
    denied_events_list = [e for e in sorted_events if is_denied_event(e)]
    denied_events = [_ledger_event_to_observe_item(e) for e in denied_events_list[:limit]]

    return ObserveActorDetailResponse(
        actor=actor_item,
        recent_events=recent_events,
        denied_events=denied_events,
    )


class ObserveLedgerEventsResponse(BaseModel):
    """Response for ledger events query."""

    events: List[ObserveEventItem] = Field(default_factory=list)
    total: int = Field(description="Total events matching filters (before limit)")
    filtered_by: Dict[str, Any] = Field(default_factory=dict)


@router.get("/ledger/events", response_model=ObserveLedgerEventsResponse)
async def observe_ledger_events(
    request: Request,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    actor_id: Optional[str] = Query(None, description="Filter by actor ID"),
    days: int = Query(15, ge=1, le=90, description="Events from last N days"),
    limit: int = Query(200, ge=1, le=1000, description="Max events to return"),
    offset: int = Query(0, ge=0, description="Skip first N events (for pagination)"),
):
    """Query ledger events with filters and pagination.

    Read-only endpoint for observability. Returns events filtered by type,
    actor, and time window. Results are sorted by timestamp descending
    (most recent first).

    Pagination: use offset + limit to navigate pages.
    Example: offset=0, limit=50 returns first 50; offset=50, limit=50 returns next 50.

    Requires:
    - `X-Institution-Id` (or legacy `X-Tenant-Id`)
    - Admin auth (`X-Admin-Key` or bootstrap `X-Admin-Token` where allowed)
    """
    institution_id = resolve_institution_id(request, require_header=True)
    require_admin_auth(request, institution_id)

    ledger = get_ledger_for_institution(institution_id)
    all_events = ledger.get_all_events()

    # Compute cutoff timestamp
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")

    # Filter events
    filtered = []
    for event in all_events:
        # Time filter
        ts = event.timestamp or ""
        if ts and ts < cutoff_iso:
            continue

        # Event type filter
        if event_type and event.event_type != event_type:
            continue

        # Actor filter
        if actor_id and event.actor_id != actor_id:
            continue

        filtered.append(event)

    total = len(filtered)

    # Sort by timestamp desc (most recent first), then apply offset + limit
    filtered.sort(key=lambda e: e.timestamp or "", reverse=True)
    paginated = filtered[offset : offset + limit]

    # Convert to response items
    events = [_ledger_event_to_observe_item(e) for e in paginated]

    return ObserveLedgerEventsResponse(
        events=events,
        total=total,
        filtered_by={
            "event_type": event_type,
            "actor_id": actor_id,
            "days": days,
            "limit": limit,
            "offset": offset,
        },
    )
