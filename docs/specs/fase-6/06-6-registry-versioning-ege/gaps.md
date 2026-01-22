# Gaps e Decisões - Registry Versioning + EGE (Etapa 6.6)

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Etapa:** 6.6

---

## 1. Gaps Identificados (RESOLVIDOS)

### Gap 1: Sem Mecanismo de Reload em Runtime ✅

**Problema:**
O bundle era carregado **uma única vez** no startup via `load_bundle()` (server.py:189).

**Solução Implementada:**
- Criado módulo `src/engine/core/runtime_reload.py` com `reload_active_runtime()`
- Chamado automaticamente após `accept_pin_update_proposal()` e `execute_governed_rollback()`
- Atualiza `_operations` em memória sem restart

---

### Gap 2: IDL Handler Captura Operation em Closure ✅

**Problema:**
O handler IDL capturava `operation` em closure, ignorando atualizações do registry.

**Solução Implementada:**
- Handler modificado em `src/engine/core/idl_router.py:173-299`
- Agora captura apenas `endpoint_sig` e faz lookup dinâmico via `get_operation_by_endpoint_sig()`
- Cada request resolve a operação atual do registry

---

### Gap 3: Rotas FastAPI São Imutáveis Após Registro ✅

**Limitação Aceita (por design):**
- FastAPI não permite remover rotas após registro
- Rotas existentes continuam válidas, mas handlers resolvem dinamicamente
- **Novas rotas** (novos paths/methods) requerem restart
- Operações removidas retornam 404 com código `RUNTIME_OPERATION_NOT_FOUND`

---

### Gap 4: Sem ActiveRuntimeSnapshot ✅

**Problema:**
Não existia estrutura para expor estado do runtime.

**Solução Implementada:**
```python
@dataclass
class ActiveRuntimeSnapshot:
    institution_id: str
    active_release_id: Optional[str]
    bundle_path: str
    manifest_hash: str
    operations_hash: Optional[str]
    loaded_at: str
    reload_reason: Optional[str]  # "boot", "pin_applied", "rollback"
```

- Armazenado em `_active_snapshots` por instituição
- Preenchido no boot via `reload_on_boot()`
- Atualizado em cada hot-swap

---

### Gap 5: Sem Evento RUNTIME_RELOADED ✅

**Problema:**
Spec 6.6 requeria evento determinístico no ledger.

**Solução Implementada:**
- Evento `RUNTIME_RELOADED` emitido em cada hot-swap (não no boot)
- Payload inclui:
  - `active_release_id`
  - `manifest_hash`
  - `operations_hash`
  - `bundle_path`
  - `reason`
  - `loaded_at`

---

### Gap 6: OpenAPI Cache Não Invalida Automaticamente ✅

**Problema:**
`app.openapi_schema` permanecia cacheado após atualização do registry.

**Solução Implementada:**
- `reload_active_runtime()` executa `app.openapi_schema = None`
- Próximo request gera novo schema do registry atualizado

---

### Gap 7: Concorrência Durante Reload ✅

**Decisão:**
Aceitar janela de inconsistência (operação é atômica e rápida).
- Updates do registry são ~ms
- Requests em voo podem ver estado parcial momentaneamente
- Lock de leitura considerado over-engineering para MVP

---

## 2. Decisões Finais

| # | Decisão | Implementação |
|---|---------|---------------|
| D1 | Onde chamar reload | Após `accept_pin_update_proposal()` e `execute_governed_rollback()` |
| D2 | Handler lookup | Lookup dinâmico via `get_operation_by_endpoint_sig()` |
| D3 | Rotas FastAPI | Mantidas; handlers resolvem dinamicamente |
| D4 | ActiveRuntimeSnapshot | Dataclass em `runtime_reload.py` |
| D5 | Evento RUNTIME_RELOADED | Emitido no ledger após hot-swap |
| D6 | OpenAPI invalidation | `app.openapi_schema = None` no reload |
| D7 | Concorrência | Aceitar janela de inconsistência |

---

## 3. Arquivos Modificados

| Arquivo | Modificação |
|---------|-------------|
| `src/engine/core/runtime_reload.py` | **NOVO** - ActiveRuntimeSnapshot + reload_active_runtime + reload_on_boot |
| `src/engine/core/idl_router.py` | Handler com lookup dinâmico (linhas 173-299) |
| `src/engine/core/ege_pins.py` | Chamar reload após accept (linha ~557) |
| `src/engine/core/ege_rollback.py` | Chamar reload após rollback (linha ~333) |
| `src/engine/core/errors.py` | Adicionado RUNTIME_* error codes |
| `src/engine/api/server.py` | Integração com `reload_on_boot()` |
| `tests/test_runtime_reload.py` | **NOVO** - 19 testes |

---

## 4. Testes

```bash
pytest tests/test_runtime_reload.py -v
# 19 passed
```

Cobertura:
- ActiveRuntimeSnapshot CRUD
- create_snapshot_from_bundle()
- reload_active_runtime() com bundle swap
- OpenAPI cache invalidation
- Dynamic lookup integration
- RUNTIME_RELOADED event emission
- Multi-dept bundle reload
- Bundle swap e rollback scenarios

---

## 5. Riscos Mitigados

| Risco | Status |
|-------|--------|
| Performance de lookup dinâmico | Mitigado - O(n) com n pequeno |
| Rotas órfãs após reload | Aceito - retorna 404 |
| Concorrência durante reload | Aceito - janela mínima |
| Circular import | Resolvido - imports dinâmicos |

---

## 6. Limitações Documentadas

1. **Novas rotas requerem restart**: Se um novo bundle adicionar rotas com novos paths/methods, elas só ficam disponíveis após restart do processo.

2. **Operações removidas retornam 404**: Se uma operação for removida do bundle, a rota ainda existe mas retorna 404 com `RUNTIME_OPERATION_NOT_FOUND`.

3. **Reload é por bundle**: O reload atualiza todo o operations registry, não operações individuais.
