# Multi-Department Parity - Diagnostic Flow

**Data:** 2026-01-18
**Tipo:** Mapeamento diagnóstico para PROMPT 2.5.1

## Visão Geral

Este documento mapeia o fluxo atual de multi-department no engine, identificando como cada componente trata `dept_id`.

---

## 1. Department Selection (Routing)

### Path Pattern
```
/d/{dept_id}/...
```

### Implementação
**Arquivo:** `src/engine/core/dept_context.py:16`

```python
DEPT_PATH_PATTERN = re.compile(r"^/d/([^/]+)/")

def resolve_dept_from_path(path: str) -> Optional[str]:
    match = DEPT_PATH_PATTERN.match(path)
    if match:
        return match.group(1)
    return None
```

### Middleware de Routing
**Arquivo:** `src/engine/api/server.py:619-661`

```
Request /d/{dept}/...
       │
       ▼
dept_routing_middleware
       │
       ├─ resolve_dept_from_path(path)
       │
       ├─ If dept found:
       │    ├─ Check bundle mode == "multi"
       │    ├─ Validate dept exists in bundle_ctx.departments
       │    └─ set_request_dept(request, dept)
       │
       └─ Else: set_request_dept(request, None)
```

### Legacy Routes
- `/finance/expenses` → em multi-mode, alias para `dept_id="finance"`
- **Arquivo:** `src/engine/core/dept_context.py:69-102`

---

## 2. Bundle Loading por Department

### Detecção de Modo
**Arquivo:** `src/engine/loader/load_bundle.py:130-139`

```python
def _is_multi_dept_bundle(bundle_path: Path) -> bool:
    return (bundle_path / "departments").is_dir()
```

### Estrutura Multi-Dept
```
bundle/
├── bundle.manifest.json
├── contract_ledger.json
├── contracts.json           # Catálogo de depts
└── departments/
    ├── finance/
    │   ├── rbac.json
    │   ├── approvals.json
    │   ├── workflows.json
    │   ├── sod.json
    │   ├── invariants.json
    │   ├── openapi.yaml
    │   ├── policies.json    # opcional
    │   ├── mandates.json    # opcional
    │   └── autonomy.json    # opcional
    └── support/
        └── ... (mesmos artifacts)
```

### Artifacts Obrigatórios por Dept
**Arquivo:** `src/engine/loader/load_bundle.py:56-63`

```python
DEPT_REQUIRED_ARTIFACTS = [
    "rbac.json",
    "approvals.json",
    "workflows.json",
    "sod.json",
    "invariants.json",
    "openapi.yaml",
]
```

### Carregamento de Contracts per Dept
**Arquivo:** `src/engine/loader/load_bundle.py:221-335`

```
load_bundle()
     │
     ├─ _is_multi_dept_bundle() ?
     │
     ├─ YES → _load_multi_dept_bundle()
     │         │
     │         ├─ Validate contracts.json exists
     │         ├─ Parse contracts.json → contracts_catalog
     │         ├─ For each dept in departments/:
     │         │    ├─ _validate_dept_artifacts()
     │         │    └─ Load DeptContracts(rbac, approvals, sod, ...)
     │         └─ Return BundleContext(mode="multi", departments={...})
     │
     └─ NO → _load_single_dept_bundle()
              └─ Return BundleContext(mode="single", departments={})
```

### Policy Loading per Dept
**Arquivo:** `src/engine/loader/load_bundle.py:475-560`

```
_load_policies_multi_mode(bundle_path, bundle_ctx)
     │
     └─ For each dept_id in bundle_ctx.departments:
          ├─ Load policies.json → set_policies(dept_id, policy_def)
          └─ If not exists → set_policies(dept_id, None)  # allow all

_load_mandates_multi_mode(bundle_path, bundle_ctx)
     │
     └─ For each dept_id:
          └─ set_mandates(dept_id, mandate_def)

_load_autonomy_multi_mode(bundle_path, bundle_ctx)
     │
     └─ For each dept_id:
          └─ set_autonomy_for_dept(dept_id, autonomy_def)
```

---

## 3. State Store Namespacing

### Key Structure
**Arquivo:** `src/engine/core/state_store.py`

```python
# Internal cache key
_state_stores: Dict[Tuple[Optional[str], Optional[str]], StateStore] = {}
# Key: (institution_id, dept_id)
```

### File Namespacing
```python
def get_state_store_path_for_institution(
    institution_id: str,
    dept_id: Optional[str] = None,
) -> Path:
    # Pattern: state_store.{dept_id}.json
    # Example: /data/{institution_id}/state_store.finance.json
```

### Usage Flow
```
API Handler (create_expense_handler)
     │
     ├─ dept_id = get_request_dept(request)
     ├─ institution_id = get_request_institution_id(request)
     │
     └─ state_store = get_state_store(dept_id, institution_id=institution_id)
          │
          └─ Returns StateStore isolated by (institution_id, dept_id)
```

---

## 4. Ledger Namespacing

### Namespacing por Institution
**Arquivo:** `src/engine/core/ledger.py:23-38`

```python
def get_ledger_path_for_institution(institution_id: str) -> Path:
    # Returns: /data/{institution_id}/audit_ledger.jsonl
```

### Ledger Instance Cache
```python
_institution_ledgers: Dict[str, AuditLedger] = {}
# Key: institution_id (NOT dept_id)
```

### Step Name com Dept Prefix
**Arquivo:** `src/engine/core/dept_context.py:127-139`

```python
def get_ledger_step_name(base_step: str, dept_id: Optional[str]) -> str:
    if dept_id:
        return f"DEPT:{dept_id}:{base_step}"
    return base_step
```

### Exemplo de Evento
```json
{
  "event_type": "RBAC_DECISION",
  "tenant_id": "inst-001",
  "step": "DEPT:finance:RBAC:expense.create",
  "payload": { "permission": "expense.create", "decision": "allow" }
}
```

---

## 5. Gates/Contracts per Dept

### RBAC
**Arquivo:** `src/engine/api/finance.py:113-117`

```python
allowed = gate_rbac(permission, actor)
emit_rbac_decision(actor, permission, allowed, case_id, step,
                   dept_id=dept_id, institution_id=institution_id)
```

### Policy Evaluation
**Arquivo:** `src/engine/core/policy.py:374+`

```python
def evaluate_policies(
    phase: str,
    dept_id: Optional[str],  # ← per-dept lookup
    endpoint_sig: str,
    payload: Dict[str, Any],
) -> PolicyResult:
```

### Mandate Evaluation
**Arquivo:** `src/engine/core/mandates.py:568+`

```python
def evaluate_mandates(
    phase: str,
    dept_id: Optional[str],  # ← per-dept lookup
    endpoint_sig: str,
    actor: ActorContext,
    payload: Dict[str, Any],
) -> MandateResult:
```

### Autonomy Evaluation
**Arquivo:** `src/engine/core/autonomy.py:292+`

```python
def evaluate_autonomy(
    phase: str,
    dept_id: Optional[str],  # ← per-dept lookup
    endpoint_sig: str,
) -> AutonomyEvalResult:
```

---

## 6. Diagrama de Fluxo End-to-End

```
┌─────────────────────────────────────────────────────────────────┐
│                     POST /d/finance/finance/expenses            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  dept_routing_middleware                                        │
│  ├─ resolve_dept_from_path("/d/finance/...") → "finance"        │
│  ├─ validate dept in bundle_ctx.departments                     │
│  └─ set_request_dept(request, "finance")                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  institution_middleware                                         │
│  └─ set_request_institution_id(request, "inst-001")             │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  create_expense_dept (dept_finance.py)                          │
│  ├─ dept_id = get_request_dept(request) → "finance"             │
│  └─ create_expense_handler(request, actor, dept_id="finance")   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  create_expense_handler (finance.py)                            │
│  │                                                              │
│  ├─ gate_rbac(permission, actor)                                │
│  │    └─ emit_rbac_decision(..., dept_id="finance")             │
│  │         └─ step = "DEPT:finance:RBAC:expense.create"         │
│  │                                                              │
│  ├─ evaluate_policies(phase="pre", dept_id="finance", ...)      │
│  │    └─ Looks up policies for dept_id="finance"                │
│  │                                                              │
│  ├─ evaluate_mandates(phase="pre", dept_id="finance", ...)      │
│  │    └─ Looks up mandates for dept_id="finance"                │
│  │                                                              │
│  ├─ evaluate_autonomy(phase="pre", dept_id="finance", ...)      │
│  │    └─ Looks up autonomy for dept_id="finance"                │
│  │                                                              │
│  └─ get_state_store(dept_id="finance", institution_id="inst-001")│
│       └─ Returns StateStore for (inst-001, finance)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Testes Existentes

| Arquivo | Cobertura |
|---------|-----------|
| `test_multi_dept_loader.py` | Bundle loading, mode detection, artifact validation |
| `test_verify_bundle_multi_dept.py` | Hash verification for multi-dept |
| `test_pipeline_build_multi_dept.py` | Pipeline build with multi-dept |
| `test_pipeline_export_zip_multi_dept.py` | ZIP export with multi-dept |
| `test_ise_compile_release_multi_dept.py` | ISE release with multi-dept |
| `test_ise_compile_bundle_multi_dept.py` | ISE compile with multi-dept |

---

## Resumo do Estado Atual

| Componente | Suporte Multi-Dept | Namespacing |
|------------|-------------------|-------------|
| Routing | ✅ `/d/{dept}/...` | Path-based |
| Bundle Loading | ✅ `departments/` | Per-dept artifacts |
| RBAC | ✅ Per-dept rbac.json | Loaded per dept |
| Approvals | ✅ Per-dept approvals.json | Loaded per dept |
| Policies | ✅ Per-dept policies.json | `set_policies(dept_id, ...)` |
| Mandates | ✅ Per-dept mandates.json | `set_mandates(dept_id, ...)` |
| Autonomy | ✅ Per-dept autonomy.json | `set_autonomy_for_dept(dept_id, ...)` |
| State Store | ✅ Per-dept file | `(institution_id, dept_id)` |
| Ledger | ⚠️ Per-institution only | Step name prefix `DEPT:{dept}:` |
| SoD | ❓ Unclear per-dept | Needs verification |
| Invariants | ❓ Unclear per-dept | Needs verification |
