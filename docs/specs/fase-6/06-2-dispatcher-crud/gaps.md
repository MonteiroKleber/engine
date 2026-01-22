# Gaps e Decisões - Dispatcher v1 (CRUD)

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Etapa:** 6.2 (Concluída)

---

## 1. Gaps Identificados (Resolvidos)

### ✅ Gap 1: Dispatcher Não Existe

**Problema:**
Não existe um módulo dispatcher que execute operações genéricas baseadas em `Operation` do OperationRegistry.

**Resolução:**
- Criado `src/engine/core/dispatcher.py`
- Implementado `dispatch_create()` e `dispatch_read()`
- Reutiliza gates existentes (RBAC, Policy, Mandates, Autonomy)

---

### ✅ Gap 2: Entity Binding Hardcoded

**Problema:**
Os handlers atuais sabem qual entidade persistir:
- `finance.py` → `ExpenseState`
- `support.py` → `TicketState`

**Resolução:**
- Implementado `ENTITY_CONFIG` em dispatcher.py
- Mapeamento por entity name (Expense, Ticket)
- Extensível para novos entity types

```python
ENTITY_CONFIG = {
    "Expense": {
        "create_method": "create_expense",
        "read_method": "get_expense",
        "id_param": "expense_id",
        "not_found_code": EXPENSE_NOT_FOUND,
    },
    "Ticket": {...},
}
```

---

### ✅ Gap 3: Approvals Flow no Finance

**Problema:**
O handler de `create_expense` tem lógica especial de approvals.

**Decisão Final:**
- Dispatcher NÃO implementa approvals flow nesta etapa
- Approvals continuam nos handlers legacy
- Dispatcher retorna 200 (created) simplificado

---

### ✅ Gap 4: Policy Gate Inconsistente

**Problema:**
- Finance usa Policy gate PRE
- Support NÃO usa Policy gate (só Mandates + Autonomy)

**Decisão Final:**
- Dispatcher executa TODOS os gates (RBAC, Policy, Mandates, Autonomy) para create
- Para read, apenas RBAC
- Se não houver policy/mandate/autonomy, gate retorna `allow=True`

---

### ✅ Gap 5: Ledger Events por Gate

**Problema:**
Cada gate emite seu próprio evento ao ledger.

**Decisão Final:**
- Dispatcher reutiliza funções de emit existentes
- `_emit_rbac_decision()` implementada localmente (mesmo padrão dos handlers)
- `emit_policy_decision()`, `emit_mandate_decision()`, `emit_autonomy_evaluated()` reusadas

---

### ✅ Gap 6: Error Codes já Definidos

**Problema:**
Os handlers usam códigos de erro específicos.

**Decisão Final:**
- Dispatcher usa mesmos error codes existentes
- `EXPENSE_NOT_FOUND`, `TICKET_NOT_FOUND` por entity type
- Mapeamento via `ENTITY_CONFIG[entity]["not_found_code"]`

---

### Gap 7: Idempotency não Enforçado

**Status:** Adiado para 6.4+

**Problema:**
O campo `Operation.idempotency` existe mas não é verificado.

**Decisão:** Idempotency enforcement adiado para etapa futura.

---

### ✅ Gap 8: Path Params não Extraídos

**Problema:**
Dispatcher precisa receber path params extraídos.

**Decisão Final:**
- Dispatcher recebe `path_params` já extraídos
- Valida presença do param correto baseado em `ENTITY_CONFIG[entity]["id_param"]`
- Retorna 400 `PATH_PARAM_MISSING` se ausente

---

## 2. Decisões Finais

| # | Decisão | Resultado | Status |
|---|---------|-----------|--------|
| D1 | Local do dispatcher | `src/engine/core/dispatcher.py` | ✅ |
| D2 | Gates para create | RBAC → Policy → Mandates → Autonomy (todos) | ✅ |
| D3 | Gates para read | RBAC apenas | ✅ |
| D4 | Approvals flow | Delegar para handler legacy | ✅ |
| D5 | Entity binding | Mapeamento hardcoded por entity name | ✅ |
| D6 | Error codes | Reusar existentes | ✅ |
| D7 | Idempotency | Adiado para 6.4+ | Adiado |
| D8 | Path params | Recebidos já extraídos | ✅ |
| D9 | Ledger events | Reusar funções de emit existentes | ✅ |

---

## 3. Patch Mínimo Proposto

### Arquivos a Criar

| Arquivo | Descrição |
|---------|-----------|
| `src/engine/core/dispatcher.py` | Dispatcher com dispatch_create, dispatch_read |
| `tests/test_dispatcher.py` | Testes unitários |

### Arquivos a Modificar

Nenhum. O dispatcher é standalone e não modifica handlers existentes (compatibilidade).

### Schema do Dispatcher

```python
# src/engine/core/dispatcher.py

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .actor_context import ActorContext
from .operations import Operation
from .rbac import gate_rbac
from .policy import evaluate_policies, emit_policy_decision
from .mandates import evaluate_mandates, emit_mandate_decision
from .autonomy import evaluate_autonomy, emit_autonomy_evaluated
from .state_store import get_state_store
from .errors import (
    POLICY_DENIED,
    MANDATE_DENIED,
    AUTONOMY_INSUFFICIENT,
    STATE_STORE_UNAVAILABLE,
    EXPENSE_NOT_FOUND,
    TICKET_NOT_FOUND,
)


@dataclass
class DispatchResult:
    """Result of dispatcher execution."""
    status_code: int
    response_body: Dict[str, Any]
    error_code: Optional[str] = None
    step: Optional[str] = None


# Entity handlers mapping
ENTITY_HANDLERS = {
    "Expense": {
        "create": "_create_expense",
        "read": "_read_expense",
        "not_found_code": EXPENSE_NOT_FOUND,
    },
    "Ticket": {
        "create": "_create_ticket",
        "read": "_read_ticket",
        "not_found_code": TICKET_NOT_FOUND,
    },
}


async def dispatch_create(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    request_body: Dict[str, Any],
    path_params: Dict[str, str],
) -> DispatchResult:
    """Execute a create operation via dispatcher.

    Pipeline:
    1. RBAC gate (permission)
    2. Policy PRE gate (endpoint_sig, payload)
    3. Mandates PRE gate (endpoint_sig, actor, payload)
    4. Autonomy PRE gate (endpoint_sig)
    5. Persist entity to state store
    6. Return result

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID (None for single mode).
        actor: Actor context with roles.
        operation: Operation from registry.
        request_body: Parsed request body.
        path_params: Extracted path parameters.

    Returns:
        DispatchResult with status and response.
    """
    # Implementation here...
    pass


async def dispatch_read(
    institution_id: str,
    dept_id: Optional[str],
    actor: ActorContext,
    operation: Operation,
    path_params: Dict[str, str],
) -> DispatchResult:
    """Execute a read operation via dispatcher.

    Pipeline:
    1. RBAC gate (permission)
    2. Read from state store
    3. Return entity or 404

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID (None for single mode).
        actor: Actor context with roles.
        operation: Operation from registry.
        path_params: Extracted path parameters (must contain entity ID).

    Returns:
        DispatchResult with status and response.
    """
    # Implementation here...
    pass
```

---

## 4. Critérios de Aceite (da Spec) - TODOS ATENDIDOS

- ✅ Módulo dispatcher com `dispatch_create()` e `dispatch_read()`
- ✅ Testes com `finance-pilot`: create/read expense via dispatcher
- ✅ Testes com `support`: create/read ticket via dispatcher
- ✅ Isolamento: (inst A, dept finance) não vaza para (inst A, dept support)
- ✅ Gates respeitados: sem permissão → 403

---

## 5. Riscos Mitigados

| Risco | Mitigação Implementada |
|-------|------------------------|
| Incompatibilidade com handlers legacy | Dispatcher é paralelo, handlers não modificados |
| Novos entity types | ENTITY_CONFIG extensível |
| Performance (múltiplos gates) | O(1) por gate, testado com 14 testes |
| Approvals não suportado | Documentado como out-of-scope, handlers legacy usados |

---

## 6. Próximos Passos (Fase 6.3+)

1. **6.3**: Workflow Executor
2. **6.4**: Dynamic Dispatcher + validação automática de endpoint_sig
3. **6.5**: Consolidar ALLOWED_ENDPOINT_SIGS usando registry
