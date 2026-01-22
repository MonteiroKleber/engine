# Mapeamento de Integração - Dispatcher v2 (Workflows/Approvals)

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Objetivo:** Mapear pontos de integração para implementar dispatcher de approvals + commit/reject

---

## 1. Conceito de "Workflow" no Código Atual

### 1.1 Estado Atual: Workflows são Declarativos Apenas

O arquivo `workflows.json` existe nos bundles mas **não há engine de workflow implementado**:

```json
// bundles/finance-pilot/workflows.json
{
  "version": "1.0.0",
  "workflows": [
    {
      "name": "payment_approval",
      "steps": ["submit", "review", "approve", "execute"]
    }
  ]
}
```

**Realidade:** Não há código que leia ou execute workflows.json. O fluxo de estados é **hardcoded** no handler e no state store:

```python
# state_store.py linha 114-116
STATUS_PENDING_APPROVAL = "PENDING_APPROVAL"
STATUS_COMMITTED = "COMMITTED"
STATUS_REJECTED = "REJECTED"
```

### 1.2 Transições de Estado Hardcoded

| Transição | Onde Ocorre | Como |
|-----------|-------------|------|
| `None → PENDING_APPROVAL` | `finance.py:252` | `state_store.create_expense()` |
| `PENDING_APPROVAL → COMMITTED` | `api/approvals.py:475` | `state_store.update_expense_status(expense_id, STATUS_COMMITTED)` |
| `PENDING_APPROVAL → REJECTED` | `api/approvals.py:321` | `state_store.update_expense_status(expense_id, STATUS_REJECTED)` |

### 1.3 Métodos de Transição no StateStore

| Método | Linha | Operação |
|--------|-------|----------|
| `create_expense()` | 240-273 | Cria expense com status `PENDING_APPROVAL` |
| `update_expense_status()` | 300-318 | Atualiza status para qualquer valor |
| `create_ticket()` | 322-354 | Cria ticket com status `OPEN` |
| `update_ticket_status()` | 363-381 | Atualiza status para qualquer valor |

**Observação:** Não há validação de transição permitida. Qualquer status pode ser definido.

---

## 2. Approvals - Arquitetura Atual

### 2.1 Módulo Core: `src/engine/core/approvals.py`

| Estrutura | Linha | Descrição |
|-----------|-------|-----------|
| `ApprovalRule` | 12-18 | Dataclass: rule_name, trigger_api, approver_roles, quorum |
| `ApprovalsPolicy` | 21-56 | Carrega approvals.json, indexa por rule_name e trigger_api |
| `_approvals_policies` | 60 | Dict per-dept: `{dept_id: ApprovalsPolicy}` |

### 2.2 Funções Core de Approvals

| Função | Linha | Descrição |
|--------|-------|-----------|
| `set_approvals_policy()` | 63-73 | Define policy para dept_id |
| `get_approvals_policy()` | 76-85 | Obtém policy por dept_id |
| `generate_approval_id()` | 99-101 | Gera UUID para approval |
| `emit_approval_requested()` | 109-149 | Emite evento APPROVAL_REQUESTED ao ledger |
| `emit_approval_decided()` | 152-193 | Emite evento APPROVAL_DECIDED ao ledger |
| `find_approval_requested()` | 196-217 | Busca evento APPROVAL_REQUESTED por approval_id no ledger |
| `find_approval_decided()` | 220-241 | Busca evento APPROVAL_DECIDED por approval_id no ledger |
| `is_approval_decided()` | 244-246 | Verifica se approval já foi decidido |
| `can_actor_decide()` | 249-254 | Verifica se actor tem role necessária |
| `get_rule_name_from_step()` | 257-261 | Extrai rule_name do step (ex: `APPROVAL:expense.create` → `expense.create`) |

### 2.3 API Endpoint: `src/engine/api/approvals.py`

**Rota:** `POST /approvals/{approval_id}/decide`

**Pipeline do `decide_approval()` (linha 160-495):**

```
1. Validar decision ("approve" ou "reject")
2. Buscar APPROVAL_REQUESTED no ledger via find_approval_requested()
3. Verificar se já decidido via is_approval_decided()
4. Extrair rule_name do step
5. Obter ApprovalsPolicy e rule
6. Verificar can_actor_decide() (role check)
7. check_sod() - SoD constraint
8. Se legacy write → _handle_legacy_write_decision()
9. Se expense:
   a. Obter expense via state_store.get_expense_by_approval_id()
   b. Se reject:
      - update_expense_status(REJECTED)
      - emit_approval_decided()
      - emit_case_rejected()
   c. Se approve:
      - Rodar policy POST gate
      - Rodar mandate POST gate
      - Rodar autonomy POST gate
      - validate_expense_invariants()
      - update_expense_status(COMMITTED)
      - emit_approval_decided()
      - emit_case_committed()
```

### 2.4 Funções de Emit no API

| Função | Linha | Evento |
|--------|-------|--------|
| `emit_case_committed()` | 96-125 | `CASE_COMMITTED` |
| `emit_case_rejected()` | 128-157 | `CASE_REJECTED` |

---

## 3. SoD - Separation of Duties

### 3.1 Módulo: `src/engine/core/sod.py`

| Estrutura | Linha | Descrição |
|-----------|-------|-----------|
| `REQUESTER_NEQ_DECIDER` | 12 | Única constraint suportada |
| `SodRule` | 16-20 | Dataclass: rule_name, case_step, constraint |
| `SodPolicy` | 24-60 | Carrega sod.json, indexa por step |
| `_sod_policies` | 64 | Dict per-dept: `{dept_id: SodPolicy}` |

### 3.2 Funções SoD

| Função | Linha | Descrição |
|--------|-------|-----------|
| `set_sod_policy()` | 67-77 | Define policy para dept_id |
| `get_sod_policy()` | 80-89 | Obtém policy por dept_id |
| `find_approval_requested_for_step()` | 98-124 | Busca APPROVAL_REQUESTED por case_id + step |
| `check_sod()` | 127-176 | Verifica constraint REQUESTER_NEQ_DECIDER |

### 3.3 Contrato SoD

```json
// bundles/finance-pilot/sod.json
{
  "rules": [
    {
      "rule_name": "expense.create.requester_not_approver",
      "case_step": "APPROVAL:expense.create",
      "constraint": "REQUESTER_NEQ_DECIDER"
    }
  ]
}
```

### 3.4 Integração com Approvals

SoD é verificado em `api/approvals.py:258-280` **após** validar role e **antes** de processar decisão:

```python
sod_ok, sod_error_code, sod_message = check_sod(
    case_id=approval_id,
    step=step,
    actor=actor,
)
if not sod_ok:
    # 500 para SOD_RULE_INVALID
    # 409 para SOD_VIOLATION
```

---

## 4. Invariants

### 4.1 Módulo: `src/engine/core/invariants.py`

| Estrutura | Linha | Descrição |
|-----------|-------|-----------|
| `InvariantViolation` | 9-13 | Dataclass: field, message, value |
| `InvariantsPolicy` | 17-90 | Carrega invariants.json, valida expense |
| `_invariants_policies` | 94 | Dict per-dept: `{dept_id: InvariantsPolicy}` |

### 4.2 Funções Invariants

| Função | Linha | Descrição |
|--------|-------|-----------|
| `set_invariants_policy()` | 97-107 | Define policy para dept_id |
| `get_invariants_policy()` | 110-119 | Obtém policy por dept_id |
| `validate_expense_invariants()` | 128-146 | Valida payload contra schema |

### 4.3 Contrato Invariants

```json
// bundles/finance-pilot/invariants.json
{
  "expense": {
    "amount": { "min": 0.01, "max": 1000000000 },
    "description": { "max_len": 280, "required": false }
  }
}
```

### 4.4 Integração com Approvals

Invariants são validados em `api/approvals.py:451-472` **após** gates POST e **antes** de commit:

```python
inv_ok, inv_error_code, violations = validate_expense_invariants(payload)
if not inv_ok:
    # 500 para INVARIANT_SCHEMA_INVALID
    # 422 para INVARIANT_VIOLATION
```

---

## 5. State Store - Estruturas de Dados

### 5.1 Schema do State Store

```python
# state_store.py linha 209-213
self._data: Dict[str, Any] = {
    "expenses": {},        # Dict[expense_id, ExpenseState.to_dict()]
    "approval_index": {},  # Dict[approval_id, expense_id]
    "tickets": {},         # Dict[ticket_id, TicketState.to_dict()]
}
```

### 5.2 approval_index

O `approval_index` é um **índice reverso** para buscar expense por approval_id:

```python
# create_expense() linha 269-270
self._data["expenses"][expense_id] = expense.to_dict()
self._data["approval_index"][approval_id] = expense_id

# get_expense_by_approval_id() linha 282-287
def get_expense_by_approval_id(self, approval_id: str) -> Optional[ExpenseState]:
    expense_id = self._data["approval_index"].get(approval_id)
    if expense_id:
        return self.get_expense(expense_id)
    return None
```

### 5.3 ExpenseState

```python
@dataclass
class ExpenseState:
    expense_id: str
    status: str              # PENDING_APPROVAL, COMMITTED, REJECTED
    approval_id: str
    payload_sha256: str
    payload_raw: str         # base64 encoded
    created_at: str
    updated_at: Optional[str] = None
```

### 5.4 TicketState

```python
@dataclass
class TicketState:
    ticket_id: str
    subject: str
    status: str              # OPEN, CLOSED
    payload_raw: str         # base64 encoded
    created_at: str
    description: Optional[str] = None
    updated_at: Optional[str] = None
```

---

## 6. Eventos de Ledger

### 6.1 Fluxo de Eventos para Expense

```
1. RBAC_DECISION (allow/deny)
2. POLICY_PRE_DECISION
3. MANDATE_EVALUATED (pre)
4. AUTONOMY_EVALUATED (pre)
5. APPROVAL_REQUESTED (se approvals rule existe)
   ------- aguarda decisão -------
6. POLICY_POST_DECISION (se approve)
7. MANDATE_EVALUATED (post, se approve)
8. AUTONOMY_EVALUATED (post, se approve)
9. APPROVAL_DECIDED (approve/reject)
10. CASE_COMMITTED ou CASE_REJECTED
```

### 6.2 Estrutura dos Eventos

| Evento | case_id | step | Payload |
|--------|---------|------|---------|
| APPROVAL_REQUESTED | approval_id | `APPROVAL:{rule_name}` | decision=null, requested_by, required_roles, payload_sha256 |
| APPROVAL_DECIDED | approval_id | `APPROVAL:{rule_name}` | decision, decided_by, reason? |
| CASE_COMMITTED | expense_id | `CASE:expense.commit` | name |
| CASE_REJECTED | expense_id | `CASE:expense.reject` | name |

---

## 7. Códigos de Erro Relevantes

### 7.1 Approvals (definidos em api/approvals.py)

| Código | HTTP | Quando |
|--------|------|--------|
| `APPROVAL_DECISION_INVALID` | 400 | Decision não é "approve"/"reject" |
| `APPROVAL_NOT_FOUND` | 404 | Approval não existe no ledger |
| `APPROVAL_ALREADY_DECIDED` | 409 | Já foi decidido |
| `APPROVAL_RULE_ERROR` | 500 | Não conseguiu determinar rule |
| `APPROVAL_POLICY_ERROR` | 500 | ApprovalsPolicy não carregado |
| `APPROVAL_FORBIDDEN` | 403 | Actor não tem role de approver |

### 7.2 SoD (definidos em core/errors.py)

| Código | HTTP | Quando |
|--------|------|--------|
| `SOD_VIOLATION` | 409 | Requester == Decider |
| `SOD_RULE_INVALID` | 500 | Constraint desconhecido |

### 7.3 Invariants (definidos em core/errors.py)

| Código | HTTP | Quando |
|--------|------|--------|
| `INVARIANT_VIOLATION` | 422 | Payload não passa validação |
| `INVARIANT_SCHEMA_INVALID` | 500 | Schema de invariant inválido |

### 7.4 State Store (definidos em core/errors.py)

| Código | HTTP | Quando |
|--------|------|--------|
| `CASE_NOT_FOUND` | 404 | Expense não encontrado para approval_id |
| `STATE_STORE_UNAVAILABLE` | 503 | Store não inicializado |

---

## 8. Fluxo Atual: Finance Expense com Approval

```
POST /finance/expenses (analyst)
├─ RBAC gate: expense.create
├─ Policy PRE gate
├─ Mandates PRE gate
├─ Autonomy PRE gate
├─ get_approvals_policy(dept_id)
├─ rule = policy.get_rule_for_api("POST /finance/expenses")
├─ Se rule existe:
│   ├─ generate_expense_id()
│   ├─ generate_approval_id()
│   ├─ compute_payload_sha256()
│   ├─ state_store.create_expense(status=PENDING_APPROVAL)
│   ├─ emit_approval_requested()
│   └─ Return 202 { status: "pending_approval", approval_id }
│
POST /approvals/{approval_id}/decide (manager)
├─ Validar decision
├─ find_approval_requested(approval_id)
├─ is_approval_decided(approval_id)
├─ Extrair rule_name do step
├─ can_actor_decide(actor, rule)
├─ check_sod(case_id, step, actor)
├─ state_store.get_expense_by_approval_id(approval_id)
├─ Se reject:
│   ├─ update_expense_status(REJECTED)
│   ├─ emit_approval_decided(reject)
│   └─ emit_case_rejected()
├─ Se approve:
│   ├─ evaluate_policies(phase="post")
│   ├─ evaluate_mandates(phase="post")
│   ├─ evaluate_autonomy(phase="post")
│   ├─ validate_expense_invariants()
│   ├─ update_expense_status(COMMITTED)
│   ├─ emit_approval_decided(approve)
│   └─ emit_case_committed()
```

---

## 9. Mapeamento para Spec 6.3

### 9.1 bind.kind=transition (spec seção 4)

A spec espera:
- Resolver entidade no state store
- Gate RBAC
- Gates institucionais (policy, mandates, autonomy, SoD, workflow guard)
- Persistir entidade atualizada
- Ledger events

**Realidade:** Não existe conceito de "transition" como operação separada. Transições são implícitas em create/decide.

### 9.2 bind.kind=approval (spec seção 5)

A spec espera dois caminhos:
1. **Criar approval request:** 202 + `{ status: "pending_approval", approval_id, step }`
2. **Decidir approval:** 200 + `{ status: "decided", decision, case_status }`

**Realidade:**
- Criar approval está embutido no `create_expense_handler`
- Decidir approval está no endpoint `/approvals/{approval_id}/decide`

---

## 10. Implementação Realizada (2026-01-21)

### 10.1 Funções Implementadas no Dispatcher

**`dispatch_approval_request()` (dispatcher.py:620-774)**
- Pipeline completo: RBAC → Policy PRE → Mandates PRE → Autonomy PRE → Approval check → Persist
- Se approval rule existe para endpoint_sig: retorna 202 + emit APPROVAL_REQUESTED
- Se não existe: retorna 200 (create normal)

**`dispatch_approval_decide()` (dispatcher.py:777-1011)**
- Pipeline completo: Validate → Find → Check decided → Role check → SoD → POST gates → Invariants → Persist → Emit
- Reutiliza todas funções existentes de approvals.py, sod.py, invariants.py
- Emite APPROVAL_DECIDED + CASE_COMMITTED/CASE_REJECTED

### 10.2 Helpers Implementados

**`_emit_case_committed()` (dispatcher.py:553-584)**
- Emite evento CASE_COMMITTED ao ledger

**`_emit_case_rejected()` (dispatcher.py:587-618)**
- Emite evento CASE_REJECTED ao ledger

### 10.3 Testes Implementados (28 total)

| Categoria | Testes | Status |
|-----------|--------|--------|
| CRUD (v1) | 14 | ✅ Passando |
| Approval Request | 2 | ✅ Passando |
| Approval Decide | 7 | ✅ Passando |
| Full Flow | 2 | ✅ Passando |
| Multi-tenant | 2 | ✅ Passando |
| Invariants | 1 | ✅ Passando |

### 10.4 Gaps Resolvidos

| Gap | Status | Como |
|-----|--------|------|
| Dispatcher não conhece Approvals | ✅ | `dispatch_approval_request()` verifica approvals policy |
| Approval Decision via Dispatcher | ✅ | `dispatch_approval_decide()` extrai lógica reutilizável |
| SoD não integrado | ✅ | `check_sod()` chamado em dispatch_approval_decide |
| Invariants não validados | ✅ | `validate_expense_invariants()` chamado antes de commit |

### 10.5 Gaps Mantidos (out of scope)

| Gap | Decisão |
|-----|---------|
| Workflow Engine genérico | Adiado para Fase 7+ |
| Validação de transição | Manter hardcoded (funcional para MVP) |
| Quorum/distinct_actors | Usar approvals engine existente (já implementado) |
