"""Legacy route telemetry for ENGINE_API_MODE=both.

Purpose:
In transition mode (both), IDL and legacy routes may overlap. This module provides
deterministic, per-institution telemetry for requests that were served by legacy
routers, so we can plan the legacy cutover.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from engine.core.data_root import get_institution_root
from engine.core.idl_router import API_MODE_BOTH, get_api_mode


def _telemetry_path(institution_id: str):
    return get_institution_root(institution_id) / "legacy_telemetry.jsonl"


def record_legacy_invocation(
    *,
    institution_id: Optional[str],
    endpoint_sig: str,
    method: str,
    path: str,
    dept_id: Optional[str] = None,
) -> None:
    """Record a legacy route invocation (append-only JSONL).

    Records only when ENGINE_API_MODE=both.
    """
    if get_api_mode() != API_MODE_BOTH:
        return
    if not institution_id:
        return

    telemetry_path = _telemetry_path(institution_id)
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)

    event: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "route_mode": "legacy",
        "endpoint_sig": endpoint_sig,
        "method": method.upper(),
        "path": path,
    }
    if dept_id:
        event["dept_id"] = dept_id

    with open(telemetry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def get_legacy_cutover_status(institution_id: str) -> Dict[str, Any]:
    """Aggregate per-endpoint legacy usage for an institution."""
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
            slot = totals.setdefault(endpoint_sig, {"endpoint_sig": endpoint_sig, "count": 0, "last_ts": None})
            slot["count"] += 1
            if ts and (slot["last_ts"] is None or ts > slot["last_ts"]):
                slot["last_ts"] = ts

    by_endpoint = sorted(totals.values(), key=lambda x: (-x["count"], x["endpoint_sig"]))
    return {
        "total": total_count,
        "last_ts": last_ts,
        "by_endpoint": by_endpoint,
    }


def clear_legacy_telemetry(institution_id: str) -> None:
    """Best-effort clear of legacy telemetry file (test helper)."""
    try:
        telemetry_path = _telemetry_path(institution_id)
        if telemetry_path.exists():
            telemetry_path.unlink()
    except Exception:
        pass

