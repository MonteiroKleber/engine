# Multi-Institution Isolation Model

**Data:** 2026-01-18
**Versao:** 1.0
**Etapa:** 06 — Multi-instituicao e Admin Security

---

## 1. Visao Geral

Este documento descreve o modelo de isolamento multi-tenant do Libervia Engine, garantindo que cada instituicao tenha seus dados e configuracoes completamente segregados.

---

## 2. Header X-Institution-Id

### 2.1 Processamento

**Arquivo:** [server.py:701-755](../../../../src/engine/api/server.py)

```
Middleware: institution_middleware()
  1. Extrai headers X-Institution-Id e X-Tenant-Id (legacy)
  2. Valida formato UUID via resolve_institution_id()
  3. Valida existencia na registry via validate_institution_exists()
  4. Define request.state.institution_id para uso downstream
```

### 2.2 Resolucao de Headers

**Arquivo:** [institution_context.py:31-102](../../../../src/engine/core/institution_context.py)

| Cenario | Header Presente | Resultado |
|---------|-----------------|-----------|
| Nenhum header | - | DEFAULT_INSTITUTION_ID (se permitido) |
| X-Institution-Id | UUID valido | Usa valor |
| X-Tenant-Id (legacy) | UUID valido | Usa valor |
| Ambos iguais | UUID valido | Usa valor |
| Ambos diferentes | - | 409 INSTITUTION_HEADER_CONFLICT |
| UUID invalido | - | 400 INSTITUTION_ID_INVALID |
| Institution nao existe | UUID valido | 404 INSTITUTION_NOT_FOUND |

### 2.3 Flag require_institution_header_for_runtime

**Arquivo:** [institution_config.py:51-56](../../../../src/engine/core/institution_config.py)

Quando `config.flags.require_institution_header_for_runtime = true`:
- Requests sem header `X-Institution-Id` sao rejeitados com 400
- Nao usa DEFAULT_INSTITUTION_ID como fallback
- Codigo erro: `INSTITUTION_HEADER_REQUIRED`

**Testes:** [test_institution_config_require_header_flag.py](../../../../tests/test_institution_config_require_header_flag.py)

---

## 3. Segregacao de Paths em Disco

### 3.1 Estrutura de Diretorios

```
$ENGINE_DATA_ROOT/
  institutions/
    <institution_id>/
      audit_ledger.jsonl       # Ledger de auditoria
      state_store.json         # Estado do departamento (single mode)
      state_store.{dept}.json  # Estado por dept (multi mode)
      config/
        ACTIVE.json            # Configuracao ativa
        history.jsonl          # Historico de configs
      admin_keys.jsonl         # Chaves admin
      dev-runs/                # Execucoes de desenvolvimento
        dev_runs_registry.jsonl
      bundles/                 # Bundles customizados (opcional)
```

### 3.2 Funcoes de Resolucao de Path

| Componente | Funcao | Arquivo | ENV Override |
|------------|--------|---------|--------------|
| Institution Root | `get_institution_root()` | [data_root.py:23-33](../../../../src/engine/core/data_root.py) | - |
| Ledger | `get_ledger_path_for_institution()` | [ledger.py:23-38](../../../../src/engine/core/ledger.py) | ENGINE_LEDGER_PATH |
| State Store | `get_state_store_path_for_institution()` | [state_store.py:70-100](../../../../src/engine/core/state_store.py) | ENGINE_STATE_STORE_DIR |
| Config | `get_config_dir()` | [institution_config.py:173-182](../../../../src/engine/core/institution_config.py) | - |
| Admin Keys | `_get_keys_path()` | [admin_keys.py:148-158](../../../../src/engine/core/admin_keys.py) | - |
| Dev Runs | `get_dev_runs_dir_for_institution()` | [registry.py:49-59](../../../../src/engine/pipeline/registry.py) | - |

### 3.3 Semantica de ENV Override

**Arquivo:** [data_root.py:36-66](../../../../src/engine/core/data_root.py)

| ENV Value | Comportamento |
|-----------|---------------|
| None | Usa `institution_root/<default_rel>` |
| Absoluto (/path/to/...) | Usa path absoluto (ignora namespacing) |
| Relativo (path/to/...) | Usa `institution_root/<env_value>` |

### 3.4 AVISO: ENV Absoluto Quebra Isolamento

**IMPORTANTE:** Em ambiente multi-tenant, **NAO** defina ENV variables de path com valores absolutos,
pois isso faz todas as instituicoes compartilharem o mesmo storage:

```bash
# ERRADO (quebra isolamento):
ENGINE_STATE_STORE_DIR=/var/lib/engine/state
ENGINE_LEDGER_PATH=/var/log/engine/ledger.jsonl

# CORRETO (isolamento preservado):
# Nao definir (usa defaults por instituicao)
# OU usar path relativo:
ENGINE_STATE_STORE_DIR=custom_state
ENGINE_LEDGER_PATH=custom/audit.jsonl
```

Os testes em `test_cross_tenant_isolation.py` usam `monkeypatch.delenv()` para garantir
que ENVs nao interferem no isolamento.

---

## 4. Isolamento de Ledger

### 4.1 Paths por Instituicao

**Arquivo:** [ledger.py:23-38](../../../../src/engine/core/ledger.py)

```python
def get_ledger_path_for_institution(institution_id: str) -> Path:
    return resolve_namespaced_path(
        institution_id=institution_id,
        env_key="ENGINE_LEDGER_PATH",
        default_rel=DEFAULT_LEDGER_REL,  # "audit_ledger.jsonl"
    )
```

### 4.2 Instancias por Instituicao

**Arquivo:** [ledger.py](../../../../src/engine/core/ledger.py)

- Cache de instancias: `_institution_ledgers: Dict[str, AuditLedger]`
- Funcao: `get_ledger_for_institution(institution_id)` - retorna/cria ledger
- Funcao: `init_ledger_for_institution(institution_id)` - inicializa novo

### 4.3 Garantias

- Eventos de Institution A nunca sao escritos no arquivo de Institution B
- Cada institution tem seu proprio arquivo de ledger
- Eventos incluem `tenant_id` para rastreabilidade

**Testes:** [test_storage_namespacing_ledger.py](../../../../tests/test_storage_namespacing_ledger.py)

---

## 5. Isolamento de State Store

### 5.1 Paths por Instituicao

**Arquivo:** [state_store.py:70-100](../../../../src/engine/core/state_store.py)

```python
def get_state_store_path_for_institution(
    institution_id: str,
    dept_id: Optional[str] = None
) -> Path:
    # Returns: institution_root/state_store.json or
    #          institution_root/state_store.{dept_id}.json
```

### 5.2 Instancias por Instituicao

- Cache: `_institution_stores: Dict[Tuple[str, Optional[str]], StateStore]`
- Funcao: `get_state_store(dept_id=None, institution_id=None)`
- Duplo isolamento: por institution E por department

### 5.3 Uso nos Handlers de API

**Arquivos:**
- [finance.py:240](../../../../src/engine/api/finance.py) - `create_expense_handler`
- [finance.py:342](../../../../src/engine/api/finance.py) - `get_expense_handler`
- [approvals.py:246](../../../../src/engine/api/approvals.py) - `decide_approval`

Os handlers de API extraem `institution_id` do request via `get_request_institution_id(request)`
e passam para `get_state_store()`:

```python
institution_id = get_request_institution_id(request)
state_store = get_state_store(dept_id, institution_id=institution_id)
```

Isso garante que cada instituicao acessa apenas seu proprio state store.

### 5.4 Validacao de Dept ID

**Arquivo:** [state_store.py](../../../../src/engine/core/state_store.py)

```python
def validate_dept_id(dept_id: str):
    # Rejeita caracteres perigosos: /, ., espaco
    # Previne path traversal via dept_id
```

**Testes:** [test_state_store_dept_isolation.py:150-177](../../../../tests/test_state_store_dept_isolation.py)

---

## 6. Isolamento de Configuracao

### 6.1 Paths por Instituicao

**Arquivo:** [institution_config.py:173-206](../../../../src/engine/core/institution_config.py)

| Path | Funcao |
|------|--------|
| `institution_root/config/` | `get_config_dir()` |
| `institution_root/config/ACTIVE.json` | `get_active_config_path()` |
| `institution_root/config/history.jsonl` | `get_history_path()` |

### 6.2 Campos de Config v1.3

| Campo | Tipo | Default |
|-------|------|---------|
| `schema_version` | string | "1.3" |
| `freeze_mode` | bool | false |
| `emergency_stop.enabled` | bool | false |
| `emergency_stop.blocked_endpoints` | list | [] |
| `limits.rate_limit_per_minute` | int | 100 |
| `limits.max_body_bytes` | int | 262144 |
| `flags.require_institution_header_for_runtime` | bool | false |
| `flags.allow_legacy_routes` | bool | true |
| `ege_enforce_drift` | bool | true |

**Testes:** [test_institution_config_put_get.py](../../../../tests/test_institution_config_put_get.py)

---

## 7. Isolamento de Admin Keys

### 7.1 Paths por Instituicao

**Arquivo:** [admin_keys.py:148-158](../../../../src/engine/core/admin_keys.py)

```python
def _get_keys_path(self, institution_id: str) -> Path:
    return get_institution_root(institution_id) / "admin_keys.jsonl"
```

### 7.2 Garantias

- Chave de Institution A nao funciona para Institution B
- Cada institution tem seu proprio arquivo de chaves
- Verificacao inclui institution_id

**Testes:** [test_admin_keys_registry.py:246-254](../../../../tests/test_admin_keys_registry.py)

---

## 8. Aplicacao de Gates por Instituicao

### 8.1 Middlewares com Instituicao

| Middleware | Usa institution_id | Arquivo |
|------------|-------------------|---------|
| rate_limit_middleware | Sim (per-institution limit) | server.py:362-396 |
| body_size_middleware | Sim (per-institution limit) | server.py:320-359 |
| freeze_emergency_stop_middleware | Sim (per-institution config) | server.py:442-538 |
| ege_drift_middleware | Sim (per-institution drift state) | server.py:542-616 |

### 8.2 Eventos no Ledger

Todos os eventos incluem `tenant_id` (institution_id) para auditoria:

```json
{
  "event_type": "EXPENSE_CREATED",
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "actor_id": "user-123",
  ...
}
```

---

## 9. GAPs Identificados

| # | GAP | Severidade | Status |
|---|-----|------------|--------|
| 1 | Sem testes E2E cross-tenant API (expense de A nao visivel para B) | **CRITICO** | **RESOLVIDO** |
| 2 | Sem testes de path traversal via API | Alto | **RESOLVIDO** |
| 3 | Sem testes de inference cross-tenant (timing attacks) | Medio | **RESOLVIDO** |

### 9.1 Resolucao dos GAPs

**GAP 1: Cross-Tenant API Isolation** - RESOLVIDO

Testes adicionados em `test_cross_tenant_isolation.py`:
- `test_expense_created_in_a_not_visible_to_b` - Expense de A nao visivel para B
- `test_state_stores_are_separate_per_institution_at_core_level` - State stores separados
- `test_ledger_events_isolated_per_institution` - Eventos de ledger isolados
- `test_admin_key_from_a_rejected_for_b` - Admin key de A nao funciona para B
- `test_config_changes_only_affect_own_institution` - Config isolada por institution

**GAP 2: Path Traversal** - RESOLVIDO

Testes adicionados em `test_cross_tenant_isolation.py`:
- `test_invalid_dept_id_with_traversal_rejected` - Dept ID com `../` rejeitado
- `test_invalid_institution_id_format_rejected` - Institution ID nao-UUID rejeitado
- `test_valid_uuid_but_nonexistent_institution_rejected` - UUID valido mas inexistente rejeitado

**GAP 3: Inference Prevention** - RESOLVIDO

Teste adicionado em `test_cross_tenant_isolation.py`:
- `test_expense_not_found_returns_404_not_403` - Retorna 404 (nao 403) para evitar inference

---

## 10. Testes Existentes

| Teste | Arquivo | Cobertura |
|-------|---------|-----------|
| **Cross-tenant isolation E2E** | test_cross_tenant_isolation.py | **NOVO - 12 testes** |
| Ledger path isolation | test_storage_namespacing_ledger.py | Path + Data |
| State store path isolation | test_storage_namespacing_state_store.py | Path + Instance |
| Department isolation | test_state_store_dept_isolation.py | Path traversal prevention |
| Admin key isolation | test_admin_keys_registry.py:246-254 | Key per institution |
| Header validation | test_institution_context_headers.py | UUID, conflict |
| Header requirement | test_institution_config_require_header_flag.py | Flag enforcement |

---

## 11. Referencias

- [spec.md](spec.md) - Especificacao da Etapa 06
- [admin-auth.md](admin-auth.md) - Autenticacao administrativa
- [data_root.py](../../../../src/engine/core/data_root.py) - Resolucao de paths
- [institution_context.py](../../../../src/engine/core/institution_context.py) - Contexto de instituicao

---

**Status:** ESPECIFICACAO ATIVA (GAPs RESOLVIDOS, ISOLAMENTO E2E COMPROVADO)
**Data:** 2026-01-18
**Atualizado:** 2026-01-18 - Handlers corrigidos para passar institution_id ao state_store e ledger
**Atualizado:** 2026-01-18 - Testes E2E deterministicos (404 garantido para cross-tenant access)
