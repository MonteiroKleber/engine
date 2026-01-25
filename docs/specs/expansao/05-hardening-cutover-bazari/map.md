# Expansão 05 — Map: Existing Infrastructure

Data: 2026-01-25

## 1. Logging / request_id Middlewares

### 1.1 Request Context

| File | Symbol | Description |
|------|--------|-------------|
| [request_context.py](src/engine/core/request_context.py) | `_request_id_var: ContextVar` | ContextVar for request_id propagation |
| [request_context.py:9](src/engine/core/request_context.py#L9) | `set_request_id()` | Sets request_id in context |
| [request_context.py:14](src/engine/core/request_context.py#L14) | `get_request_id()` | Gets request_id from context |

### 1.2 Request ID Middleware

| File | Symbol | Description |
|------|--------|-------------|
| [server.py:925](src/engine/api/server.py#L925) | `request_id_middleware()` | HTTP middleware: validates/generates X-Request-Id, sets contextvar |

Flow:
```
Request → request_id_middleware() → set_request_id() → ...handler... → response with X-Request-Id header → set_request_id(None)
```

### 1.3 Structured Logging

| File | Symbol | Description |
|------|--------|-------------|
| [logging.py](src/engine/core/logging.py) | `JSONFormatter` | JSON log formatter with request_id |
| [logging.py:25](src/engine/core/logging.py#L25) | `log_entry["request_id"]` | Auto-includes request_id from context |
| [logging.py:85](src/engine/core/logging.py#L85) | `log_request()` | Helper to log HTTP requests |

---

## 2. Ledger Append-Only per Institution

### 2.1 Path Resolution

| File | Symbol | Description |
|------|--------|-------------|
| [data_root.py:23](src/engine/core/data_root.py#L23) | `get_institution_root()` | Returns `<data_root>/institutions/<institution_id>/` |
| [data_root.py:36](src/engine/core/data_root.py#L36) | `resolve_namespaced_path()` | Resolves ENV or default rel path under institution root |
| [ledger.py:23](src/engine/core/ledger.py#L23) | `get_ledger_path_for_institution()` | Returns `<institution_root>/audit_ledger.jsonl` |

### 2.2 Ledger Classes

| File | Symbol | Description |
|------|--------|-------------|
| [ledger.py:42](src/engine/core/ledger.py#L42) | `LedgerEvent` | Dataclass: event_type, tenant_id, actor_id, request_id, etc. |
| [ledger.py:169](src/engine/core/ledger.py#L169) | `AuditLedger` | Append-only JSONL with hash-chain |
| [ledger.py:229](src/engine/core/ledger.py#L229) | `AuditLedger.append()` | Appends event with auto-hash, request_id from contextvar |

### 2.3 Per-Institution Instances

| File | Symbol | Description |
|------|--------|-------------|
| [ledger.py:413](src/engine/core/ledger.py#L413) | `_institution_ledgers: Dict` | Cache of per-institution AuditLedger instances |
| [ledger.py:428](src/engine/core/ledger.py#L428) | `get_ledger_for_institution()` | Gets/creates ledger for institution_id |

### 2.4 Ledger Event Fields

```python
@dataclass
class LedgerEvent:
    event_type: str
    tenant_id: str
    actor_id: str
    actor_roles: List[str]
    case_id: str
    step: str
    payload: Dict[str, Any]
    bundle_manifest_sha256: str
    contract_ledger_sha256: str
    engine_version: str
    seq: int
    prev_hash: str
    hash: str
    timestamp: str
    request_id: Optional[str]
    dept_id: Optional[str]
```

---

## 3. Console Status Page

### 3.1 Route

| File | Symbol | Description |
|------|--------|-------------|
| [routes.py:966](src/engine/console/routes.py#L966) | `GET /console/status` | Console status page endpoint |

### 3.2 Template

| File | Description |
|------|-------------|
| [status.html](src/engine/console/templates/status.html) | Status page template with cards |

### 3.3 Existing Cards in status.html

| Card | Lines | Description |
|------|-------|-------------|
| Runtime Status | 8-32 | ACTIVE/SAFE_MODE badge |
| Drift Status | 35-61 | CLEAR/DRIFT badge, pinned/observed hashes |
| IDL Migration Status | 64-123 | API mode, depts migrated, unsupported binds |
| Legacy Cutover Telemetry | 125-163 | Total invocations, by_endpoint table |
| Institution Config | 165-206 | Emergency freeze, safe mode, pinned release |
| Effective Mandates | 208-238 | Table of mandates |

### 3.4 Legacy Telemetry Pattern (Reference Implementation)

| File | Symbol | Description |
|------|--------|-------------|
| [legacy_telemetry.py:19](src/engine/core/legacy_telemetry.py#L19) | `_telemetry_path()` | Returns `<institution_root>/legacy_telemetry.jsonl` |
| [legacy_telemetry.py:23](src/engine/core/legacy_telemetry.py#L23) | `record_legacy_invocation()` | Appends event to JSONL (only when API_MODE=both) |
| [legacy_telemetry.py:57](src/engine/core/legacy_telemetry.py#L57) | `get_legacy_cutover_status()` | Aggregates by endpoint_sig with count and last_ts |

Event schema:
```json
{
  "ts": "2026-01-25T12:00:00Z",
  "route_mode": "legacy",
  "endpoint_sig": "POST /finance/expenses",
  "method": "POST",
  "path": "/finance/expenses",
  "dept_id": "..."  // optional
}
```

---

## 4. IDL Router Integration Points

### 4.1 IDL Handler

| File | Symbol | Description |
|------|--------|-------------|
| [idl_router.py:157](src/engine/core/idl_router.py#L157) | `_create_idl_handler()` | Factory for IDL route handlers |
| [idl_router.py:343](src/engine/core/idl_router.py#L343) | Return `JSONResponse(...)` | Final response point (ideal hook for telemetry) |

### 4.2 Dispatcher Results

All dispatchers return `DispatchResult`:

| File | Symbol | Description |
|------|--------|-------------|
| [dispatcher.py](src/engine/core/dispatcher.py) | `DispatchResult` | status_code, response_body, events |

### 4.3 Available Context in IDL Handler

At the point of return (line 343-346), these values are available:
- `institution_id` (from middleware)
- `actor` (ActorContext with actor_id, roles)
- `endpoint_sig` (from operation)
- `current_operation.method` / `current_operation.path`
- `dept_id` (from path or context)
- `result.status_code`

### 4.4 Bundle Context

| File | Symbol | Description |
|------|--------|-------------|
| [load_bundle.py:87](src/engine/loader/load_bundle.py#L87) | `BundleContext` | mode, path, manifest, departments |
| [load_bundle.py:101](src/engine/loader/load_bundle.py#L101) | `get_bundle_context()` | Returns current bundle context |

`manifest` contains:
- `bundle_name`
- `version`
- `bundle_manifest_sha256` (computed hash)

---

## 5. Summary

| Capability | Exists | Module |
|------------|--------|--------|
| request_id propagation | YES | `request_context.py` |
| Structured JSON logging | YES | `logging.py` |
| Per-institution ledger | YES | `ledger.py` |
| Institution path resolution | YES | `data_root.py` |
| Console Status page | YES | `routes.py` + `status.html` |
| Legacy telemetry (API_MODE=both) | YES | `legacy_telemetry.py` |
| **IDL telemetry (API_MODE=idl)** | **NO** | Needs implementation |
