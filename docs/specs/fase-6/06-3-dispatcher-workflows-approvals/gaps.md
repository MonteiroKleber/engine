# Gaps e Decisões - Dispatcher v2 (Approvals + Commit/Reject)

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Etapa:** 6.3 (Concluída)

---

## 1. Gaps Identificados e Status

### ✅ Gap 1: Dispatcher Não Suporta Approvals Flow

**Problema:**
O dispatcher v1 (6.2) executa `dispatch_create()` e `dispatch_read()` mas:
- Não verifica se operação requer approval
- Não integra com `get_approvals_policy()`
- Retorna sempre 200, nunca 202

**Resolução Implementada:**
- Criado `dispatch_approval_request()` em `dispatcher.py:620-774`
- Verifica approvals policy após gates PRE
- Se rule existe: retorna 202 + emite APPROVAL_REQUESTED
- Se não existe: retorna 200 (create normal)

---

### Adiado: Gap 2: Não Existe dispatch_transition()

**Problema:**
A spec original mencionava `bind.kind=transition` para workflow genérico.

**Decisão Final:**
- Adiado para Fase 7+
- Não existe workflow engine no código atual
- Transições permanecem implícitas via approvals (funcional para MVP)

---

### ✅ Gap 3: Não Existe dispatch_approval_decide()

**Problema:**
O endpoint `/approvals/{approval_id}/decide` tem 300+ linhas com toda lógica inline.

**Resolução Implementada:**
- Criado `dispatch_approval_decide()` em `dispatcher.py:777-1011`
- Extrai lógica de validação, SoD, gates POST, invariants
- Reutiliza funções existentes de `approvals.py`, `sod.py`, `invariants.py`
- Endpoint legacy `/approvals/{approval_id}/decide` mantido intacto

---

### Adiado: Gap 4: Workflow Engine Não Existe

**Problema:**
O arquivo `workflows.json` existe mas não há código que o interprete.

**Decisão Final:**
- NÃO implementar workflow engine nesta etapa
- Manter transições implícitas via approvals (já funcional)
- Workflow engine completo pode ser Fase 7+

---

### ✅ Gap 5: Approvals Policy Não Integrado com Dispatcher

**Problema:**
Approvals usa `trigger.api` como string literal.

**Resolução Implementada:**
- `dispatch_approval_request()` usa `operation.endpoint_sig` para lookup
- Formato é compatível: ambos usam `"METHOD /path"`

---

### Mantido: Gap 6: SoD Busca Eventos por Scan Linear

**Problema:**
`check_sod()` busca evento iterando todos eventos O(n).

**Decisão:**
- Manter comportamento atual (já funcional)
- Performance aceitável para MVP
- Otimização de índice pode ser Fase 7+

---

### Mantido: Gap 7: Invariants Só Valida Expense

**Problema:**
`InvariantsPolicy` só implementa validação para expense.

**Decisão:**
- Manter comportamento atual
- Tickets não têm invariants no finance-pilot bundle
- Extensão para outros entity types pode ser Fase 7+

---

### ✅ Gap 8: Dispatcher Não Emite Eventos de Approval

**Problema:**
Dispatcher v1 não emitia eventos de approval.

**Resolução Implementada:**
- `dispatch_approval_request()` usa `emit_approval_requested()` de `approvals.py`
- `dispatch_approval_decide()` usa `emit_approval_decided()` de `approvals.py`
- Helpers `_emit_case_committed()` e `_emit_case_rejected()` criados localmente

---

## 2. Decisões Finais

| # | Decisão | Resultado | Status |
|---|---------|-----------|--------|
| D1 | Criar `dispatch_approval_request()` | Implementado com verificação de approval rule | ✅ |
| D2 | Criar `dispatch_transition()` | Adiado (sem workflow engine) | Adiado |
| D3 | Criar `dispatch_approval_decide()` | Implementado com pipeline completo | ✅ |
| D4 | NÃO implementar workflow engine | Mantido, transições implícitas funcionam | ✅ |
| D5 | Manter SoD scan linear | Aceitável para MVP | ✅ |
| D6 | Manter invariants só para Expense | Escopo controlado | ✅ |
| D7 | Reutilizar funções de emit existentes | Implementado | ✅ |

---

## 3. Patch Implementado

### Arquivos Modificados

| Arquivo | Modificação |
|---------|-------------|
| `src/engine/core/dispatcher.py` | +450 linhas: dispatch_approval_request, dispatch_approval_decide, helpers |
| `tests/test_dispatcher.py` | +600 linhas: 14 novos testes de approvals |

### Arquivos NÃO Modificados (como planejado)

| Arquivo | Razão |
|---------|-------|
| `src/engine/core/approvals.py` | Reutilizado as-is |
| `src/engine/core/sod.py` | Reutilizado as-is |
| `src/engine/core/invariants.py` | Reutilizado as-is |
| `src/engine/api/approvals.py` | Endpoint legacy mantido |
| `src/engine/api/finance.py` | Handler legacy mantido |

---

## 4. Critérios de Aceite - TODOS ATENDIDOS

| Critério | Como Validado | Status |
|----------|---------------|--------|
| `dispatch_approval_request()` existe | `test_create_with_approval_returns_202` | ✅ |
| `dispatch_approval_decide()` existe | `test_manager_approve_returns_committed` | ✅ |
| Fluxo Finance completo via dispatcher | `test_finance_complete_flow_approve` | ✅ |
| Self-approve bloqueado | `test_self_approve_denied_by_sod` | ✅ |
| Manager approve → COMMITTED | `test_manager_approve_returns_committed` | ✅ |
| Manager reject → REJECTED | `test_manager_reject_returns_rejected` | ✅ |
| Isolamento 2 inst × 2 depts | `test_full_isolation_matrix_approvals` | ✅ |
| Invariants validados | `test_approve_with_invalid_amount_fails` | ✅ |

---

## 5. Riscos Mitigados

| Risco | Mitigação Implementada |
|-------|------------------------|
| Duplicar lógica de approvals.py | Reutilizado via import direto |
| Quebrar handlers legacy | Dispatcher é paralelo, handlers não modificados |
| Workflow engine incompleto | Não implementado, transições implícitas funcionam |
| Performance de SoD scan | Aceitável para MVP, não é gargalo |

---

## 6. Próximos Passos (Fase 6.4+)

1. **6.4**: Dynamic Router - expor operações via rotas dinâmicas
2. **6.5**: Validação automática de endpoint_sig
3. **7.x**: Workflow engine genérico (se necessário)
