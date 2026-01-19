# Etapa 2.4: Rollback Automatizado e Governado — Gaps & Decisões

**Data:** 2026-01-18
**Status:** ✅ IMPLEMENTADO

---

## 1. Status de Implementação

| Gap | Status | Resolução |
|-----|--------|-----------|
| Gap 1: Rollback para pinned | ✅ Fechado | `execute_governed_rollback()` usa `pinned_release_id` |
| Gap 2: Eventos de rollback | ✅ Fechado | `EGE_ROLLBACK_STARTED/COMPLETED/FAILED` |
| Gap 3: Status "rolled_back" | ✅ Fechado | `_handle_deploy_failure()` executa rollback real |
| Gap 4: SAFE_MODE no startup | ⏳ Parcial | SAFE_MODE ativado se no pinned release; drift check no startup não implementado |
| Gap 5: Recovery check | ⏳ Pendente | Não implementado (nice-to-have) |
| Gap 6: Cross-device check | ⏳ Pendente | Documentado apenas (nice-to-have) |
| Gap 7: pinned_release_id | ✅ Fechado | Adicionado ao config v1.4 |
| Gap 8: Multi-tenant script | ⏳ Parcial | rollback via Python; bash script não alterado |

---

## 2. Arquivos Criados

```
src/engine/core/ege_rollback.py        # ~220 LOC - Rollback module
tests/test_ege_rollback.py             # ~520 LOC - 18 testes
```

---

## 3. Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/engine/core/errors.py` | Adicionados 5 códigos EGE_ROLLBACK_* |
| `src/engine/core/institution_config.py` | Adicionado `pinned_release_id` (schema v1.4) |
| `src/engine/core/ege_pins.py` | Stores `pinned_release_id` on accept |
| `src/engine/ise/release.py` | `_handle_deploy_failure()` com governed rollback |
| `tests/test_institution_config_defaults.py` | Atualizado para v1.4 |
| `tests/test_institution_config_put_get.py` | Atualizado para v1.4 |

---

## 4. Códigos de Erro Implementados

| Código | Descrição |
|--------|-----------|
| `EGE_ROLLBACK_NO_PINNED_RELEASE` | Nenhuma release pinada configurada |
| `EGE_ROLLBACK_PINNED_RELEASE_MISSING` | Release pinada não encontrada no filesystem |
| `EGE_ROLLBACK_SYMLINK_FAILED` | Falha ao atualizar CURRENT symlink |
| `EGE_ROLLBACK_BLOCKED_FROZEN` | Rollback bloqueado: instituição congelada |
| `EGE_ROLLBACK_BLOCKED_EMERGENCY` | Rollback bloqueado: emergency stop ativo |

---

## 5. Eventos de Auditoria Implementados

| Evento | Payload |
|--------|---------|
| `EGE_ROLLBACK_STARTED` | `failed_release_id`, `reason`, `timestamp` |
| `EGE_ROLLBACK_COMPLETED` | `rolled_back_to`, `pinned_path`, `failed_release_id`, `reason`, `timestamp` |
| `EGE_ROLLBACK_FAILED` | `error_code`, `error_message`, `failed_release_id`, `safe_mode_activated`, `timestamp` |

---

## 6. Testes Implementados

### 6.1 Cobertura

| Categoria | Testes | Status |
|-----------|--------|--------|
| `get_pinned_release_path()` | 3 | ✅ |
| `check_rollback_blocked()` | 3 | ✅ |
| `execute_governed_rollback()` | 4 | ✅ |
| `get_current_release_id()` | 2 | ✅ |
| Integration with release.py | 3 | ✅ |
| pinned_release_id in config | 3 | ✅ |
| **Total** | **18** | ✅ |

### 6.2 Execução

```bash
cd /home/bazari/engine
PYTHONPATH=src python -m pytest tests/test_ege_rollback.py -v
# Resultado: 18 passed
```

---

## 7. Decisões Implementadas

| # | Decisão | Implementação |
|---|---------|---------------|
| Q1 | Rollback para PINNED (não PREVIOUS) | ✅ `get_pinned_release_path()` usa `pinned_release_id` |
| Q2 | Eventos via Python (não bash) | ✅ `ege_rollback.py` emite eventos no ledger |
| Q3 | SAFE_MODE se no pinned | ✅ `execute_governed_rollback()` ativa SAFE_MODE |

---

## 8. Definition of Done - ATINGIDO

- [x] Um deploy falho nunca deixa o runtime apontando para uma release inválida
  - **Implementado:** `_handle_deploy_failure()` executa rollback para pinned release
  - **Se não há pinned:** ativa SAFE_MODE

- [x] Rollback é automático e deixa trilha de auditoria
  - **Implementado:** Eventos `EGE_ROLLBACK_STARTED/COMPLETED/FAILED`
  - **Automático:** Via `execute_governed_rollback()`

- [x] Testes automatizados cobrem o cenário de falha e retorno ao estado consistente
  - **Implementado:** 18 testes em `test_ege_rollback.py`
  - **Cenários:** pinned existe → rollback ok; no pinned → SAFE_MODE

---

## 9. Métricas Finais

| Métrica | Valor |
|---------|-------|
| Linhas de código (ege_rollback.py) | ~220 LOC |
| Linhas de código (testes) | ~520 LOC |
| Testes adicionados | 18 |
| Códigos de erro | 5 |
| Eventos de auditoria | 3 |
| Arquivos criados | 2 |
| Arquivos modificados | 6 |

---

## 10. Itens Pendentes (Nice-to-have)

| Item | Descrição | Prioridade |
|------|-----------|------------|
| Drift check on startup | Verificar drift no boot e ativar SAFE_MODE | Média |
| Recovery check | Detectar releases órfãs em releases/ | Baixa |
| Cross-device check | Validar que STAGING e releases estão no mesmo FS | Baixa |
| Multi-tenant bash script | Parametrizar deploy_engine_prod.sh | Média |
