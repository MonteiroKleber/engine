"""IDL route telemetry for ENGINE_API_MODE=idl|both.

Purpose:
Deterministic, per-institution telemetry for requests served by IDL router.
Records endpoint_sig, actor_id, timestamp for auditing and SRE observability.

Only records when ENGINE_API_MODE != legacy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engine.core.data_root import get_institution_root
from engine.core.idl_router import API_MODE_LEGACY, get_api_mode
from engine.core.institution_context import DEFAULT_INSTITUTION_ID


def _telemetry_path(institution_id: str):
    """Return <institution_root>/idl_telemetry.jsonl"""
    return get_institution_root(institution_id) / "idl_telemetry.jsonl"


def record_idl_invocation(
    *,
    institution_id: Optional[str],
    endpoint_sig: str,
    method: str,
    path: str,
    actor_id: Optional[str] = None,
    dept_id: Optional[str] = None,
) -> None:
    """Record an IDL route invocation (append-only JSONL).

    Records only when ENGINE_API_MODE != legacy.
    Does not record if institution_id is None or DEFAULT.

    Args:
        institution_id: Institution UUID.
        endpoint_sig: Canonical endpoint signature (e.g., "POST /reports").
        method: HTTP method.
        path: Request path.
        actor_id: Actor UUID (from resolved context).
        dept_id: Department ID (if multi-dept route).
    """
    if get_api_mode() == API_MODE_LEGACY:
        return
    if not institution_id or institution_id == DEFAULT_INSTITUTION_ID:
        return

    telemetry_path = _telemetry_path(institution_id)
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)

    event: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "route_mode": "idl",
        "endpoint_sig": endpoint_sig,
        "method": method.upper(),
        "path": path,
    }
    if actor_id:
        event["actor_id"] = actor_id
    if dept_id:
        event["dept_id"] = dept_id

    with open(telemetry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def get_idl_telemetry_status(institution_id: str) -> Dict[str, Any]:
    """Aggregate per-endpoint IDL usage for an institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Dict with:
        - total: Total invocation count
        - last_ts: Most recent timestamp
        - by_endpoint: List of {endpoint_sig, count, last_ts} sorted by count desc
    """
    telemetry_path = _telemetry_path(institution_id)
    if not telemetry_path.exists():
        return {
            "total": 0,
            "last_ts": None,
            "by_endpoint": [],
        }

    totals: Dict[str, Dict[str, Any]] = {}
    total_count = 0
    last_ts: Optional[str] = None

    with open(telemetry_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            endpoint_sig = event.get("endpoint_sig")
            ts = event.get("ts")
            if not endpoint_sig:
                continue
            total_count += 1
            if ts and (last_ts is None or ts > last_ts):
                last_ts = ts
            slot = totals.setdefault(endpoint_sig, {
                "endpoint_sig": endpoint_sig,
                "count": 0,
                "last_ts": None
            })
            slot["count"] += 1
            if ts and (slot["last_ts"] is None or ts > slot["last_ts"]):
                slot["last_ts"] = ts

    by_endpoint = sorted(totals.values(), key=lambda x: (-x["count"], x["endpoint_sig"]))
    return {
        "total": total_count,
        "last_ts": last_ts,
        "by_endpoint": by_endpoint,
    }


def clear_idl_telemetry(institution_id: str) -> None:
    """Best-effort clear of IDL telemetry file (test helper)."""
    try:
        telemetry_path = _telemetry_path(institution_id)
        if telemetry_path.exists():
            telemetry_path.unlink()
    except Exception:
        pass
