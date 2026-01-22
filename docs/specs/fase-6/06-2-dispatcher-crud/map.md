# Mapeamento de Integração - Dispatcher v1 (CRUD)

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Objetivo:** Mapear pontos de integração para implementar o Dispatcher de create/read

---

## 1. State Store - Acesso Atual

### Arquivo Principal
- **`src/engine/core/state_store.py`**

### Path Resolution

```python
# Linha 70-111: Path namespacing por institution + dept
def get_state_store_path_for_institution(
    institution_id: str,
    dept_id: Optional[str] = None,
) -> Path:
    # Single mode: state_store.json
    # Multi mode: state_store.{dept_id}.json
```

### Helpers Existentes

| Função | Linha | Descrição |
|--------|-------|-----------|
| `get_state_store()` | 405 | Get store por (institution_id, dept_id) |
| `set_state_store()` | 431 | Set store (para testes) |
| `reset_all_state_stores()` | 460 | Limpa todos os stores |

### Formato de Dados

```python
# Linha 209-213: Schema interno do store
self._data: Dict[str, Any] = {
    "expenses": {},      # Dict[expense_id, ExpenseState.to_dict()]
    "approval_index": {},  # Dict[approval_id, expense_id]
    "tickets": {},       # Dict[ticket_id, TicketState.to_dict()]
}
```

### Dataclasses de Entidade

| Entidade | Linha | Campos |
|----------|-------|--------|
| `ExpenseState` | 123-149 | expense_id, status, approval_id, payload_sha256, payload_raw, created_at, updated_at |
| `TicketState` | 152-178 | ticket_id, subject, status, payload_raw, created_at, description, updated_at |

### Métodos CRUD no StateStore

| Método | Linha | Operação |
|--------|-------|----------|
| `create_expense()` | 240 | Create expense com approval_id |
| `get_expense()` | 275 | Read expense por ID |
| `get_expense_by_approval_id()` | 282 | Read expense por approval |
| `update_expense_status()` | 300 | Update status |
| `create_ticket()` | 322 | Create ticket |
| `get_ticket()` | 356 | Read ticket por ID |
| `update_ticket_status()` | 363 | Update status |

---

## 2. Finance Handler - Create/Read

### Arquivo: `src/engine/api/finance.py`

### Create Expense (`create_expense_handler` linha 92)

**Pipeline atual (ordem determinística):**

```python
# 1. Get institution_id (linha 108)
institution_id = get_request_institution_id(request)

# 2. RBAC Gate (linha 114-122)
allowed = gate_rbac(permission, actor, dept_id=dept_id)
emit_rbac_decision(...)
check_perm = require_permission(permission, dept_id=dept_id)
check_perm(actor)

# 3. Parse body (linha 125-130)
body_bytes = await request.body()
payload_dict = json.loads(body_bytes)

# 4. Policy Gate PRE (linha 133-162)
policy_result = evaluate_policies(phase="pre", ...)
emit_policy_decision(...)
if not policy_result.allow: raise HTTPException(403, POLICY_DENIED)

# 5. Mandates Gate PRE (linha 165-195)
mandate_result = evaluate_mandates(phase="pre", ...)
emit_mandate_decision(...)
if not mandate_result.allow: raise HTTPException(403, MANDATE_DENIED)

# 6. Autonomy Gate PRE (linha 198-227)
autonomy_result = evaluate_autonomy(phase="pre", ...)
emit_autonomy_evaluated(...)
if autonomy_result.decision == "deny": raise HTTPException(403, AUTONOMY_INSUFFICIENT)

# 7. Check approvals policy (linha 230-279)
policy = get_approvals_policy(dept_id)
if rule:
    expense_id = generate_expense_id()
    approval_id = generate_approval_id()
    state_store.create_expense(...)
    emit_approval_requested(...)
    return JSONResponse(202, pending_approval)

# 8. No approval - create directly (linha 282-289)
return JSONResponse(200, created)
```

### Read Expense (`get_expense_handler` linha 308)

**Pipeline atual:**

```python
# 1. Get institution_id (linha 326)
institution_id = get_request_institution_id(request)

# 2. RBAC Gate (linha 333-341)
allowed = gate_rbac(permission, actor, dept_id=dept_id)
emit_rbac_decision(...)
check_perm(actor)

# 3. Get state store (linha 344-352)
state_store = get_state_store(dept_id, institution_id=institution_id)
if not state_store: raise HTTPException(503, STATE_STORE_UNAVAILABLE)

# 4. Read entity (linha 354-363)
expense = state_store.get_expense(expense_id)
if not expense: raise HTTPException(404, EXPENSE_NOT_FOUND)  # Anti-inference

# 5. Return (linha 365-374)
return JSONResponse(200, expense_data)
```

---

## 3. Support Handler - Create/Read

### Arquivo: `src/engine/api/support.py`

### Create Ticket (`create_ticket_handler` linha 72)

**Pipeline (sem Policy gate, só Mandates + Autonomy):**

```python
# 1. Get institution_id (linha 88)
# 2. RBAC Gate (linha 94-102)
# 3. Parse body (linha 105-110)
# 4. Mandates Gate PRE (linha 113-145) - sem Policy!
# 5. Autonomy Gate PRE (linha 148-177)
# 6. Create ticket (linha 180-198)
state_store.create_ticket(...)
return JSONResponse(200, created)
```

**Observação:** Support não usa approvals flow nem Policy gate.

### Read Ticket (`get_ticket_handler` linha 210)

**Pipeline:**
```python
# 1. Get institution_id
# 2. RBAC Gate
# 3. Get state store
# 4. Read entity - 404 TICKET_NOT_FOUND se não existir
# 5. Return
```

---

## 4. Gates - Ordem e Semântica

### Módulos de Gates

| Gate | Arquivo | Função Principal | Evento Ledger |
|------|---------|------------------|---------------|
| RBAC | `core/rbac.py` | `gate_rbac()` | RBAC_DECISION |
| Policy | `core/policy.py` | `evaluate_policies()` | POLICY_PRE_DECISION |
| Mandates | `core/mandates.py` | `evaluate_mandates()` | MANDATE_EVALUATED |
| Autonomy | `core/autonomy.py` | `evaluate_autonomy()` | AUTONOMY_EVALUATED |

### Ordem de Execução (Finance Create)

```
1. RBAC (permission)
2. Policy PRE (endpoint_sig, payload)
3. Mandates PRE (endpoint_sig, actor, payload)
4. Autonomy PRE (endpoint_sig)
5. [Approvals se aplicável]
6. Persist
7. Ledger events
```

### Ordem de Execução (Support Create)

```
1. RBAC (permission)
2. Mandates PRE (endpoint_sig, actor, payload)
3. Autonomy PRE (endpoint_sig)
4. Persist
```

### Ordem de Execução (Read)

```
1. RBAC (permission)
2. Read from store
3. Return (ou 404)
```

### Semântica de Cada Gate

| Gate | Sem contrato | Com contrato, sem match | Com match |
|------|--------------|-------------------------|-----------|
| RBAC | deny | deny | allow se role tem permission |
| Policy | allow | allow | allow se todas rules passam |
| Mandates | allow | DENY | allow se mandate válido |
| Autonomy | allow | DENY | allow se level >= required |

---

## 5. Códigos de Erro Determinísticos

### Erros de Gates (403)

| Código | Módulo | Quando |
|--------|--------|--------|
| `POLICY_DENIED` | policy.py | Policy rule violation |
| `MANDATE_DENIED` | mandates.py | No mandate matches ou limit violation |
| `MANDATE_EXPIRED` | mandates.py | Mandate fora de validity window |
| `MANDATE_ROLE_MISMATCH` | mandates.py | Actor roles não match allowed_roles |
| `AUTONOMY_INSUFFICIENT` | autonomy.py | current_level < required_level |

### Erros de Read (404)

| Código | Handler | Quando |
|--------|---------|--------|
| `EXPENSE_NOT_FOUND` | finance.py | Expense não existe |
| `TICKET_NOT_FOUND` | support.py | Ticket não existe |

### Erros de Infraestrutura (503)

| Código | Quando |
|--------|--------|
| `STATE_STORE_UNAVAILABLE` | Store não inicializado |

---

## 6. OperationRegistry - Binds Disponíveis

### Lookup Functions (de 6.1)

```python
from engine.core.operations import (
    get_operation_by_endpoint_sig,
    get_operation_by_method_path,
)

# Lookup retorna Operation com:
# - operation_id
# - method, path, endpoint_sig
# - permission
# - scope (tenant/global)
# - idempotency (required/optional/none)
# - errors: List[int]
# - bind: {"kind": "create"|"read"|"action", "entity": "Expense"|"Ticket"}
```

### Binds Usados na Spec

| bind.kind | Entidade | Handlers Existentes |
|-----------|----------|---------------------|
| create | Expense | `create_expense_handler` |
| create | Ticket | `create_ticket_handler` |
| read | Expense | `get_expense_handler` |
| read | Ticket | `get_ticket_handler` |

---

## 7. Diagrama de Dependências (Dispatcher)

```
HTTP Request
    │
    ▼
[API Handler] ─────────────────────────────────────┐
    │                                               │
    ▼                                               │
[Get Operation from Registry] ◄─ operations.json   │
    │                                               │
    ▼                                               │
[Dispatcher.dispatch_create/read]                  │
    │                                               │
    ├──► [Gate: RBAC] ◄── rbac.json                │
    │        │                                      │
    │        ▼                                      │
    ├──► [Gate: Policy PRE] ◄── policies.json      │ (só create)
    │        │                                      │
    │        ▼                                      │
    ├──► [Gate: Mandates PRE] ◄── mandates.json    │ (só create)
    │        │                                      │
    │        ▼                                      │
    ├──► [Gate: Autonomy PRE] ◄── autonomy.json    │ (só create)
    │        │                                      │
    │        ▼                                      │
    ├──► [State Store] ◄── state_store.json        │
    │        │                                      │
    │        ▼                                      │
    └──► [Ledger Events] ◄── contract_ledger.jsonl │
            │                                       │
            ▼                                       │
       Response ◄───────────────────────────────────┘
```

---

## 8. Local para Dispatcher

### Recomendação: `src/engine/core/dispatcher.py`

Seguindo padrão existente de core modules:
- `src/engine/core/operations.py` (6.1)
- `src/engine/core/policy.py`
- `src/engine/core/mandates.py`
- `src/engine/core/autonomy.py`

### Assinatura Proposta

```python
@dataclass
class DispatchResult:
    status_code: int
    response_body: Dict[str, Any]
    error_code: Optional[str] = None
    step: Optional[str] = None

async def dispatch_create(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    request_body: Dict[str, Any],
    path_params: Dict[str, str],
) -> DispatchResult:
    ...

async def dispatch_read(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    path_params: Dict[str, str],
) -> DispatchResult:
    ...
```

---

## 9. Próximos Passos

1. **Criar `src/engine/core/dispatcher.py`** com dispatch_create e dispatch_read
2. **Reusar gates existentes** (não duplicar lógica)
3. **Reusar StateStore** (create_expense, create_ticket, get_expense, get_ticket)
4. **Adicionar bind dispatcher** baseado em Operation.bind.entity
5. **Criar testes unitários** chamando dispatcher diretamente
