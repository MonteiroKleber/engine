# Expansão 05 — Gaps: IDL Telemetry Implementation

Data: 2026-01-25

## 1. Gap Identificado

**IDL endpoint telemetry não existe.**

O `legacy_telemetry.py` registra invocações de rotas legacy apenas quando `ENGINE_API_MODE=both`. Não há equivalente para registrar invocações atendidas pelo **IDL router** quando `ENGINE_API_MODE=idl`.

---

## 2. Proposta de Patch Mínimo

### 2.1 Novo Módulo: `src/engine/core/idl_telemetry.py`

Seguir o padrão de `legacy_telemetry.py`:

```python
"""IDL route telemetry for ENGINE_API_MODE=idl.

Purpose:
Deterministic, per-institution telemetry for requests served by IDL router.
Records endpoint_sig, actor_id, timestamp for auditing and SRE planning.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from engine.core.data_root import get_institution_root
from engine.core.idl_router import API_MODE_LEGACY, get_api_mode
from engine.loader.load_bundle import get_bundle_context


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
    status_code: int = 200,
) -> None:
    """Record an IDL route invocation (append-only JSONL).

    Records only when ENGINE_API_MODE != legacy.
    """
    if get_api_mode() == API_MODE_LEGACY:
        return
    if not institution_id:
        return

    telemetry_path = _telemetry_path(institution_id)
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)

    event: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "route_mode": "idl",
        "endpoint_sig": endpoint_sig,
        "method": method.upper(),
        "path": path,
        "status_code": status_code,
    }
    if actor_id:
        event["actor_id"] = actor_id
    if dept_id:
        event["dept_id"] = dept_id

    # Include bundle info if available
    bundle_ctx = get_bundle_context()
    if bundle_ctx and bundle_ctx.manifest:
        manifest = bundle_ctx.manifest
        event["bundle_name"] = manifest.get("bundle_name")
        event["bundle_version"] = manifest.get("version")

    with open(telemetry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def get_idl_telemetry_status(institution_id: str) -> Dict[str, Any]:
    """Aggregate per-endpoint IDL usage for an institution."""
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
```

### 2.2 Hook no IDL Router

Modificar `src/engine/core/idl_router.py` para chamar `record_idl_invocation()` após dispatch bem-sucedido.

Localização: [idl_router.py:343-346](src/engine/core/idl_router.py#L343)

Antes:
```python
        return JSONResponse(
            status_code=result.status_code,
            content=result.response_body,
        )
```

Depois:
```python
        # Record IDL telemetry (per-institution, append-only)
        from engine.core.idl_telemetry import record_idl_invocation
        record_idl_invocation(
            institution_id=institution_id,
            endpoint_sig=endpoint_sig,
            method=current_operation.method,
            path=current_operation.path,
            actor_id=actor.actor_id if actor else None,
            dept_id=dept_id,
            status_code=result.status_code,
        )

        return JSONResponse(
            status_code=result.status_code,
            content=result.response_body,
        )
```

### 2.3 Console Status Page

Modificar `src/engine/console/routes.py` para incluir `idl_telemetry` no template context.

Localização: [routes.py:996-1032](src/engine/console/routes.py#L996)

Adicionar após `legacy_cutover`:
```python
    # IDL telemetry (ENGINE_API_MODE=idl): endpoint usage for observability
    try:
        from engine.core.idl_telemetry import get_idl_telemetry_status
        idl_telemetry = get_idl_telemetry_status(institution_id)
    except Exception:
        idl_telemetry = {"total": 0, "last_ts": None, "by_endpoint": []}
```

E adicionar ao template context:
```python
    return templates.TemplateResponse(
        "status.html",
        {
            ...
            "idl_telemetry": idl_telemetry,  # NEW
        },
    )
```

### 2.4 Template status.html

Adicionar novo card após "Legacy Cutover Telemetry":

```html
<!-- IDL Telemetry (Expansão 05) -->
<div class="card">
    <h3 class="card-title">IDL Endpoint Telemetry</h3>
    <div class="info-row">
        <span class="info-label">Total IDL Invocations</span>
        <span class="info-value">{{ idl_telemetry.total }}</span>
    </div>
    <div class="info-row">
        <span class="info-label">Last Seen</span>
        <span class="info-value mono">{{ idl_telemetry.last_ts or "-" }}</span>
    </div>
    {% if idl_telemetry.by_endpoint %}
    <table style="margin-top: 0.75rem;">
        <thead>
            <tr>
                <th>Endpoint</th>
                <th>Count</th>
                <th>Last Seen</th>
            </tr>
        </thead>
        <tbody>
            {% for row in idl_telemetry.by_endpoint[:20] %}
            <tr>
                <td class="mono">{{ row.endpoint_sig }}</td>
                <td>{{ row.count }}</td>
                <td class="mono">{{ row.last_ts or "-" }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% if idl_telemetry.by_endpoint|length > 20 %}
    <div style="margin-top: 0.5rem; color: var(--text-secondary);">
        Showing top 20 of {{ idl_telemetry.by_endpoint|length }} endpoints.
    </div>
    {% endif %}
    {% else %}
    <div class="empty-state">No IDL telemetry recorded (only records in ENGINE_API_MODE=idl or both)</div>
    {% endif %}
</div>
```

---

## 3. Event Schema (idl_telemetry.jsonl)

```json
{
  "ts": "2026-01-25T12:00:00Z",
  "route_mode": "idl",
  "endpoint_sig": "POST /reports",
  "method": "POST",
  "path": "/reports",
  "status_code": 200,
  "actor_id": "uuid-...",
  "dept_id": "...",
  "bundle_name": "bazari-phase1",
  "bundle_version": "1.0.0"
}
```

---

## 4. Allowlist para Implementação

Arquivos a modificar/criar:

| File | Action |
|------|--------|
| `src/engine/core/idl_telemetry.py` | CREATE |
| `src/engine/core/idl_router.py` | EDIT (add hook) |
| `src/engine/console/routes.py` | EDIT (add idl_telemetry to status) |
| `src/engine/console/templates/status.html` | EDIT (add card) |
| `tests/test_bazari_idl_telemetry_e2e.py` | CREATE |

---

## 5. Hard Gates

1. `PYTHONPATH=src python3 -m pytest tests/test_bazari_idl_telemetry_e2e.py -v` PASS
2. `PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v` PASS
3. `git status --porcelain | rg -n '^(\?\?| M ) (tmp/|var/)' && exit 1 || true` clean

---

## 6. Notas

- Telemetry é **append-only** e **determinística** (sem side-effects).
- Registra apenas quando `ENGINE_API_MODE != legacy` (ou seja, `idl` ou `both`).
- Não requer mudança de auth/dispatcher/router dinâmico.
- Pattern idêntico ao `legacy_telemetry.py` para consistência.
