# Multi-Department Parity - Gaps Analysis

**Data:** 2026-01-18
**Tipo:** Análise de gaps para PROMPT 2.5.1
**Status:** ✅ IMPLEMENTADO (PROMPT 2.5.2)

---

## Resumo Executivo

O engine agora possui suporte completo para multi-department. Todos os gaps identificados foram resolvidos:

1. ✅ **Ledger com campo dept_id** - Eventos críticos incluem dept_id
2. ✅ **Bundle multi-pilot** criado com finance + support
3. ✅ **Testes E2E de isolamento** implementados
4. ✅ **SoD, Invariants, Approvals, RBAC** - Refatorados para per-dept lookup

---

## GAP-1: Ledger Namespacing por Department ✅ RESOLVIDO

### Solução Implementada
**Opção B** - Adicionado campo `dept_id` ao `LedgerEvent`.

```python
# src/engine/core/ledger.py
@dataclass
class LedgerEvent:
    # ... existing fields ...
    dept_id: Optional[str] = None  # Department ID for multi-dept isolation

def append(self, ..., dept_id: Optional[str] = None) -> Optional[LedgerEvent]:
    # dept_id is now included in all append calls from handlers
```

### Arquivos Modificados
- `src/engine/core/ledger.py` - Added dept_id field to LedgerEvent
- `src/engine/api/finance.py` - Pass dept_id to ledger.append()
- `src/engine/api/support.py` - Pass dept_id to ledger.append()

---

## GAP-2: Bundle multi-pilot ✅ RESOLVIDO

### Solução Implementada
Criado bundle completo em `bundles/multi-pilot/`:

```
bundles/multi-pilot/
├── bundle.manifest.json
├── contract_ledger.json
├── contracts.json
└── departments/
    ├── finance/
    │   ├── rbac.json
    │   ├── approvals.json
    │   ├── workflows.json
    │   ├── sod.json
    │   ├── invariants.json
    │   ├── openapi.yaml
    │   ├── mandates.json
    │   ├── autonomy.json
    │   └── policies.json
    └── support/
        ├── rbac.json
        ├── approvals.json
        ├── workflows.json
        ├── sod.json
        ├── invariants.json
        ├── openapi.yaml
        ├── mandates.json
        ├── autonomy.json
        └── policies.json
```

---

## GAP-3: Testes E2E de Isolamento ✅ RESOLVIDO

### Solução Implementada
Criado `tests/test_multi_dept_isolation.py` com cobertura completa:

```python
class TestFinanceVsSupportIsolation:
    """E2E: finance e support em paralelo, mesma instituição."""
    def test_expense_created_in_finance_not_visible_in_support(...)
    def test_ticket_created_in_support_not_visible_in_finance(...)

class TestMatrixTwoByTwo:
    """E2E: dois depts em duas instituições (matriz 2x2)."""
    def test_matrix_complete_isolation(...)

class TestLedgerDeptId:
    """Test that ledger events contain dept_id."""
    def test_ledger_event_contains_dept_id(...)

class TestDeptNotFoundReturns404:
    """Test anti-inference: 404 not 403."""
    def test_get_expense_wrong_dept_returns_404(...)
    def test_get_ticket_wrong_dept_returns_404(...)
```

### Resultados
- 6/6 testes passando
- Isolamento por (institution_id, dept_id) verificado
- Ledger events contêm dept_id para auditoria

---

## GAP-4: SoD e Invariants per Dept ✅ RESOLVIDO

### Solução Implementada

**SoD** - `src/engine/core/sod.py`:
```python
_sod_policies: Dict[Optional[str], SodPolicy] = {}  # Key: dept_id

def set_sod_policy(policy: Optional[SodPolicy], dept_id: Optional[str] = None):
    ...

def get_sod_policy(dept_id: Optional[str] = None) -> Optional[SodPolicy]:
    ...

def check_sod(case_id, step, actor, dept_id: Optional[str] = None):
    policy = get_sod_policy(dept_id)
    ...
```

**Invariants** - `src/engine/core/invariants.py`:
```python
_invariants_policies: Dict[Optional[str], InvariantsPolicy] = {}

def set_invariants_policy(policy, dept_id: Optional[str] = None):
    ...

def get_invariants_policy(dept_id: Optional[str] = None):
    ...

def validate_expense_invariants(payload, dept_id: Optional[str] = None):
    policy = get_invariants_policy(dept_id)
    ...
```

---

## GAP-5: Routing para Support Department ✅ RESOLVIDO

### Solução Implementada

Criados novos routers:

**api/support.py** - Core support handlers:
```python
async def create_ticket_handler(request, actor, dept_id: Optional[str] = None):
    ...

async def get_ticket_handler(request, ticket_id, actor, dept_id: Optional[str] = None):
    ...
```

**api/dept_support.py** - Department-namespaced routes:
```python
router = APIRouter(prefix="/d/{dept}/support", tags=["dept-support"])

@router.post("/tickets")
async def create_ticket_dept(dept: str, request: Request, actor: ...):
    dept_id = get_request_dept(request)
    return await create_ticket_handler(request, actor, dept_id=dept_id)

@router.get("/tickets/{ticket_id}")
async def get_ticket_dept(...):
    ...
```

### State Store Support
Added to `src/engine/core/state_store.py`:
```python
@dataclass
class TicketState:
    ticket_id: str
    subject: str
    status: str
    ...

class StateStore:
    def create_ticket(self, ticket_id, subject, description, ...):
        ...
    def get_ticket(self, ticket_id) -> Optional[TicketState]:
        ...
```

---

## GAP-6: Approvals per Dept ✅ RESOLVIDO

### Solução Implementada

**approvals.py**:
```python
_approvals_policies: Dict[Optional[str], ApprovalsPolicy] = {}

def set_approvals_policy(policy, dept_id: Optional[str] = None):
    if dept_id is None:
        # Single mode - set global
        ...
    else:
        # Multi mode - set per-department
        _approvals_policies[dept_id] = policy

def get_approvals_policy(dept_id: Optional[str] = None):
    if dept_id is not None and dept_id in _approvals_policies:
        return _approvals_policies[dept_id]
    return _approvals_policy  # Fallback to global
```

---

## GAP-7: RBAC per Dept ✅ RESOLVIDO

### Solução Implementada

**rbac.py** (novo per-dept):
```python
_rbac_policies: Dict[Optional[str], RBACPolicy] = {}

def set_rbac_policy(policy, dept_id: Optional[str] = None):
    ...

def get_rbac_policy(dept_id: Optional[str] = None):
    ...

def gate_rbac(permission, actor, dept_id: Optional[str] = None):
    policy = get_rbac_policy(dept_id)
    ...

def reset_all_rbac():
    """Clear all RBAC policies (for testing)."""
    ...
```

### Loader Support
**load_bundle.py** - Added `_load_rbac_multi_mode()`:
```python
def _load_rbac_multi_mode(bundle_path, bundle_ctx):
    for dept_id, dept_contracts in bundle_ctx.departments.items():
        rbac_path = dept_contracts.path / "rbac.json"
        if rbac_path.exists():
            rbac_policy = RBACPolicy(rbac_data)
            set_rbac_policy(rbac_policy, dept_id)
```

---

## Matriz de Gaps (Final)

| Gap | Status | Arquivos Modificados |
|-----|--------|---------------------|
| GAP-1: Ledger dept field | ✅ | ledger.py, finance.py, support.py |
| GAP-2: multi-pilot bundle | ✅ | bundles/multi-pilot/* |
| GAP-3: E2E isolation tests | ✅ | test_multi_dept_isolation.py |
| GAP-4: SoD/Invariants per dept | ✅ | sod.py, invariants.py, load_bundle.py |
| GAP-5: Support routing | ✅ | support.py, dept_support.py, server.py |
| GAP-6: Approvals per dept | ✅ | approvals.py, load_bundle.py |
| GAP-7: RBAC per dept | ✅ | rbac.py, load_bundle.py, dependencies.py |

---

## Decisões Tomadas

| ID | Decisão | Escolha |
|----|---------|---------|
| D-1 | Ledger: campo dept_id ou arquivo separado? | Campo dept_id (Opção B) |
| D-2 | Support endpoint | `POST /support/tickets` |
| D-3 | Per-dept contracts | Approvals, SoD, Invariants, RBAC, Mandates, Autonomy, Policies - todos per-dept |

---

## Arquivos Criados/Modificados

### Novos Arquivos
- `bundles/multi-pilot/` - Complete multi-dept bundle
- `src/engine/api/support.py` - Support API handlers
- `src/engine/api/dept_support.py` - Dept-namespaced support routes
- `tests/test_multi_dept_isolation.py` - E2E isolation tests

### Arquivos Modificados
- `src/engine/core/rbac.py` - Per-dept RBAC lookup
- `src/engine/core/approvals.py` - Per-dept approvals lookup
- `src/engine/core/sod.py` - Per-dept SoD lookup
- `src/engine/core/invariants.py` - Per-dept invariants lookup
- `src/engine/core/ledger.py` - Added dept_id field
- `src/engine/core/state_store.py` - Added TicketState
- `src/engine/core/errors.py` - Added TICKET_NOT_FOUND
- `src/engine/core/mandates.py` - Added POST /support/tickets to allowed endpoints
- `src/engine/core/autonomy.py` - Added POST /support/tickets to allowed endpoints
- `src/engine/loader/load_bundle.py` - Added multi-mode loading functions
- `src/engine/api/server.py` - Registered new routers
- `src/engine/api/finance.py` - Pass dept_id to all lookups
- `src/engine/api/dependencies.py` - require_permission now accepts dept_id

---

## Verificação

### Testes
```bash
pytest tests/test_multi_dept_isolation.py -v
# 6 passed
```

### Funcionalidade Verificada
- ✅ Expense em finance não visível em support
- ✅ Ticket em support não visível em finance
- ✅ Matriz 2x2 (2 inst × 2 dept) com isolamento completo
- ✅ Ledger events contêm dept_id
- ✅ Anti-inference: 404 (não 403) para itens em outro dept/inst
