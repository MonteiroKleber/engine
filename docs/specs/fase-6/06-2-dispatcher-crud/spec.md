# Etapa 6.2 — Dispatcher v1 (CRUD: create/read)

**Status:** ✅ IMPLEMENTADO (2026-01-21)
**Pré-requisito:** Etapa 6.1 (OperationRegistry) ✅

## 1) Objetivo

Implementar um **Dispatcher determinístico** capaz de executar operações do `OperationRegistry` para os binds:

- `bind.kind=create`
- `bind.kind=read`

Sem rotas dinâmicas ainda (isso é 6.4). Nesta etapa, a execução deve ser validável via testes chamando o dispatcher diretamente.

## 2) Estado atual (realidade do código)

- Existem handlers fixos (ex.: finance/support) que executam CRUD usando:
  - state store namespaced
  - gates (RBAC/Policies/Mandates/Autonomy) e eventualmente approvals/SoD/workflows/invariants
  - ledger append-only
- Etapa 6.1 introduziu `operations.json` + `OperationRegistry` em runtime, mas ainda **não existe execução genérica** baseada em `OperationSpec`.

## 3) Decisões canônicas desta etapa

### 3.1 Compatibilidade

- **Não remover** rotas legacy existentes.
- Dispatcher é um motor interno novo. O wire-up HTTP (dynamic router) vem na etapa 6.4.

### 3.2 Escopo mínimo executável

- Suportar **apenas** `create` e `read`.
- Suportar **apenas** o modelo de storage atual (state store file-based), sem introduzir backend novo.
- Reusar os motores existentes de governança (não reimplementar gates).

## 4) Modelo canônico de entrada/saída (Dispatcher API)

### 4.1 Entrada mínima

O dispatcher recebe:

- `institution_id` (obrigatório)
- `dept_id` (opcional; `None` = single-dept)
- `actor_context` (já validado por `ENGINE_AUTH_MODE`)
- `operation` (resolvida via registry)
- `request_body` (dict) e `path_params` (dict)

### 4.2 Saída mínima

O dispatcher retorna:

- `status_code` (int)
- `response_body` (dict)
- `error_code` (opcional; determinístico)
- `step` (string; para rastreabilidade)

## 5) Semântica (create/read)

### 5.1 create (`bind.kind=create`)

Pipeline mínimo (ordem determinística):

1) Resolver store namespaced por `(institution_id, dept_id)`
2) Gates pré-execução (reuso):
   - RBAC (permission do `operation.permission`)
   - Policy pre (se aplicável)
   - Mandates pre (endpoint_sig)
   - Autonomy pre (endpoint_sig)
3) Persistir entidade no state store (schema "best effort" conforme modelo atual)
4) Emitir eventos no ledger (já existentes no fluxo legacy)
5) Retornar payload determinístico (id, status e/ou entity)

### 5.2 read (`bind.kind=read`)

Pipeline mínimo:

1) Resolver store namespaced por `(institution_id, dept_id)`
2) Gate RBAC (permission)
3) Ler do state store
4) Anti-inference:
   - se não existir, retornar 404 com código determinístico
5) Ledger event (read decision) se já existir padrão (não inventar evento novo; reutilizar padrão existente)

## 6) O que não pode mudar

- Não adicionar novos endpoints públicos nesta etapa.
- Não alterar semântica dos gates (apenas chamá-los).
- Não introduzir heurística para schema de entidades; usar o que já existe no runtime.

## 7) Critérios de aceite (Etapa 6.2)

- ✅ Há um módulo novo de dispatcher (nome claro) com:
  - ✅ `dispatch_create(...)`
  - ✅ `dispatch_read(...)`
- ✅ Testes provam que, para bundles templates existentes:
  - ✅ `finance-pilot`: `POST /finance/expenses` e `GET /finance/expenses/{id}` executam via dispatcher
  - ✅ `support`: create/read de ticket básico via dispatcher
- ✅ Testes provam isolamento:
  - ✅ `(institution A, dept finance)` não vaza para `(institution A, dept support)` nem `(institution B, dept finance)`
- ✅ Testes provam que os gates são respeitados:
  - ✅ sem permissão → 403 determinístico
  - ✅ sem mandate/autonomy (quando contrato exige) → 403 determinístico

## 8) Implementação Final

### Arquivos Criados

| Arquivo | Descrição |
|---------|-----------|
| `src/engine/core/dispatcher.py` | Dispatcher v1 com dispatch_create e dispatch_read |
| `tests/test_dispatcher.py` | 14 testes unitários |

### API Pública

```python
from engine.core.dispatcher import dispatch_create, dispatch_read, DispatchResult

# Create operation
result = await dispatch_create(
    institution_id="inst-001",
    dept_id="finance",
    actor=actor_context,
    operation=operation,  # from OperationRegistry
    request_body={"amount": 100},
)

# Read operation
result = await dispatch_read(
    institution_id="inst-001",
    dept_id="finance",
    actor=actor_context,
    operation=operation,
    path_params={"expense_id": "uuid-123"},
)

# DispatchResult
assert result.status_code == 200
assert result.response_body["id"] == "uuid-123"
assert result.error_code is None  # or deterministic error code
assert result.step == "DISPATCHER:create:Expense"
```

### Entidades Suportadas

| Entity | create | read | not_found_code |
|--------|--------|------|----------------|
| Expense | ✅ | ✅ | EXPENSE_NOT_FOUND |
| Ticket | ✅ | ✅ | TICKET_NOT_FOUND |

### Gates Executados (create)

1. **RBAC** - Valida `operation.permission` contra actor roles
2. **Policy PRE** - Valida payload contra regras de policy
3. **Mandates PRE** - Valida endpoint_sig + actor + payload
4. **Autonomy PRE** - Valida current_level >= required_level

### Gates Executados (read)

1. **RBAC** - Valida `operation.permission` contra actor roles

### Testes

```
tests/test_dispatcher.py::TestDispatchCreateExpense::test_create_expense_success PASSED
tests/test_dispatcher.py::TestDispatchCreateExpense::test_create_expense_rbac_denied PASSED
tests/test_dispatcher.py::TestDispatchCreateTicket::test_create_ticket_success PASSED
tests/test_dispatcher.py::TestDispatchReadExpense::test_read_expense_success PASSED
tests/test_dispatcher.py::TestDispatchReadExpense::test_read_expense_not_found PASSED
tests/test_dispatcher.py::TestDispatchReadTicket::test_read_ticket_not_found PASSED
tests/test_dispatcher.py::TestPolicyGateEnforcement::test_policy_denies_over_limit PASSED
tests/test_dispatcher.py::TestMandatesGateEnforcement::test_mandates_denies_no_matching_mandate PASSED
tests/test_dispatcher.py::TestAutonomyGateEnforcement::test_autonomy_denies_insufficient_level PASSED
tests/test_dispatcher.py::TestMultiTenantIsolation::test_isolation_between_institutions PASSED
tests/test_dispatcher.py::TestMultiTenantIsolation::test_isolation_between_departments PASSED
tests/test_dispatcher.py::TestMultiTenantIsolation::test_full_isolation_matrix PASSED
tests/test_dispatcher.py::TestEdgeCases::test_unsupported_entity_type PASSED
tests/test_dispatcher.py::TestEdgeCases::test_missing_path_param_for_read PASSED
```

## 9) Próximos Passos

1. **6.3**: Workflow Executor
2. **6.4**: Dynamic Dispatcher + validação automática de endpoint_sig
3. **6.5**: Consolidar ALLOWED_ENDPOINT_SIGS usando registry
