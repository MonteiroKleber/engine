# Mapeamento - Registry Versioning + EGE (Etapa 6.6)

**Data:** 2026-01-21
**Status:** MAPEADO (diagnóstico completo)
**Etapa:** 6.6 (Pré-implementação)

---

## 1. Objetivo da Etapa

Amarrar EGE (pins/rollback/drift) ao runtime IDL-driven (router/dispatcher/openapi), para que:
- A API exposta reflita a versão ativa (release) por instituição
- O OpenAPI reflita a versão ativa
- Atualizar/pinar/rollback seja governado e resulte em hot-swap seguro, sem restart "duro"

---

## 2. Como o "Release Ativo" é Definido por Instituição

### 2.1 CURRENT Symlink

**Arquivo:** `src/engine/ise/release.py:42-57`

```python
def get_bundles_root_for_institution(institution_id: str) -> Path:
    """Get production bundles root path for a specific institution."""
    env_value = os.environ.get(ENV_PROD_BUNDLES_ROOT)
    return resolve_namespaced_path(institution_id, env_value, DEFAULT_BUNDLES_REL_PATH)
```

**Estrutura de diretórios:**
```
{institution_root}/bundles/
├── releases/
│   ├── 20260121-142530/     # Release ID (YYYYMMDD-HHMMSS)
│   │   └── finance-pilot/   # Bundle name
│   └── 20260120-093000/
├── STAGING/                  # Bundle being deployed
└── CURRENT -> releases/20260121-142530/finance-pilot  # Symlink ativo
```

**Evidência:** `src/engine/core/ege_pins.py:101-143`
- `get_observed_hashes()` lê CURRENT symlink
- Resolve para bundle ativo e computa hashes

### 2.2 Pinned Release ID

**Arquivo:** `src/engine/core/institution_config.py:125`

```python
@dataclass
class InstitutionConfig:
    pinned_release_id: Optional[str] = None
    pinned_bundle_manifest_sha256: Optional[str] = None
    pinned_contract_ledger_sha256: Optional[str] = None
```

O release ativo é determinado por:
1. **CURRENT symlink** - aponta para o bundle em disco
2. **pinned_release_id** - release considerado "seguro" para rollback
3. **pinned_bundle_manifest_sha256** - hash para drift detection

### 2.3 Fluxo de Determinação

| Fonte | Uso | Arquivo |
|-------|-----|---------|
| CURRENT symlink | Bundle carregado em runtime | ege_pins.py:118-128 |
| pinned_release_id | Rollback target | ege_rollback.py:121 |
| pinned_bundle_manifest_sha256 | Drift detection | ege.py |
| ENGINE_BUNDLE_PATH | Override para dev/test | load_bundle.py:112-121 |

---

## 3. Onde EGE Aplica Pin e Rollback

### 3.1 Pin Application

**Arquivo:** `src/engine/core/ege_pins.py:441-554`

```python
def accept_pin_update_proposal(
    institution_id: str,
    proposal_id: str,
    actor_id: str = "SYSTEM",
) -> Tuple[Optional[Dict], Optional[str], Optional[str]]:
    """Accept a PIN_UPDATE proposal, updating pinned hashes in config."""

    # ... validation ...

    # Update institution config with observed hashes and release_id
    config_dict["pinned_bundle_manifest_sha256"] = proposal.observed_bundle_manifest_sha256
    config_dict["pinned_contract_ledger_sha256"] = proposal.observed_contract_ledger_sha256
    if metadata and metadata.get("release_id"):
        config_dict["pinned_release_id"] = metadata["release_id"]

    save_active_config(institution_id, config_dict, actor_id)
    invalidate_config_cache(institution_id)
```

**Pontos de chamada:**
1. `POST /admin/ege/{institution_id}/pin-proposals/{proposal_id}/accept` - admin_ege.py:536
2. `auto_propose_and_accept_pin()` após deploy bem-sucedido - orchestrator.py:508

### 3.2 Rollback Application

**Arquivo:** `src/engine/core/ege_rollback.py:196-339`

```python
def execute_governed_rollback(
    institution_id: str,
    failed_release_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> RollbackResult:
    """Execute governed rollback to pinned release."""

    # 1. Get pinned release path
    pinned_path, error_code, error_message = get_pinned_release_path(institution_id)

    # 2. If no pinned release - activate SAFE_MODE
    if pinned_path is None:
        runtime_state.set_safe_mode(...)
        return RollbackResult(safe_mode_activated=True)

    # 3. Atomic symlink update
    os.symlink(pinned_path, temp_path)
    os.replace(temp_path, current_link)  # CURRENT -> pinned_path
```

**Ponto de chamada:**
- `_handle_deploy_failure()` em `src/engine/ise/release.py:177-184`

### 3.3 Eventos Emitidos

| Evento | Quando | Arquivo |
|--------|--------|---------|
| `EGE_PIN_PROPOSAL_CREATED` | Criação de proposta | ege_pins.py:329-344 |
| `EGE_PIN_PROPOSAL_ACCEPTED` | Aceite de pin | ege_pins.py:532-548 |
| `EGE_PIN_AUTO_ACCEPTED` | Auto-aceite após deploy | ege_pins.py:706-718 |
| `EGE_ROLLBACK_STARTED` | Início de rollback | ege_rollback.py:220-228 |
| `EGE_ROLLBACK_COMPLETED` | Rollback bem-sucedido | ege_rollback.py:323-332 |
| `EGE_ROLLBACK_FAILED` | Falha no rollback | ege_rollback.py:260-270 |

---

## 4. Como `load_bundle()` Escolhe o Bundle Ativo

### 4.1 Mecanismo Atual

**Arquivo:** `src/engine/loader/load_bundle.py:112-121`

```python
def get_bundle_path() -> Path:
    """Get the bundle path from ENV or default."""
    env_path = os.environ.get("ENGINE_BUNDLE_PATH")
    if env_path:
        return Path(env_path)
    return Path(DEFAULT_BUNDLE_PATH)  # "bundles/finance-pilot"
```

**Chamada no startup:** `src/engine/api/server.py:189`
```python
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ...
    load_bundle()  # <-- Carrega bundle do ENGINE_BUNDLE_PATH
    logger.info("Bundle loaded, engine ready")
```

### 4.2 O que `load_bundle()` Popula

| Global | Módulo | Setter |
|--------|--------|--------|
| `_bundle_context` | load_bundle.py:98 | `_set_bundle_context()` |
| `_operations` | operations.py:84 | `set_operations()` |
| `_rbac` | rbac.py | `set_rbac_policy()` |
| `_approvals` | approvals.py | `set_approvals_policy()` |
| `_sod` | sod.py | `set_sod_policy()` |
| `_invariants` | invariants.py | `set_invariants_policy()` |

### 4.3 Limitação Atual

`load_bundle()` é chamado **uma vez no startup**. Não há mecanismo para:
- Recarregar bundle em runtime
- Detectar mudança de CURRENT symlink
- Hot-swap após pin/rollback

---

## 5. Como o Dynamic Router 6.4 Resolve OperationSpec

### 5.1 Registro de Rotas (Startup)

**Arquivo:** `src/engine/core/idl_router.py:302-450`

```python
def register_idl_routes(app: FastAPI, departments: Optional[List[str]] = None) -> int:
    """Register IDL routes from OperationRegistry."""

    for dept_id in dept_ids:
        ops_def = get_operations(dept_id)  # <-- Lê do _operations global
        for op in ops_def.operations:
            handler = _create_idl_handler(op, dept_from_path=False)
            app.add_api_route(
                path=op.path,
                endpoint=handler,
                methods=[op.method],
                name=f"idl_{op.operation_id}",
            )
```

**Chamada:** `src/engine/api/server.py:221`
```python
routes_count = register_idl_routes(app, departments=departments)
```

### 5.2 Lookup em Runtime (por Request)

**Arquivo:** `src/engine/core/idl_router.py:173-299`

```python
def _create_idl_handler(operation: Operation, dept_from_path: bool = False) -> Callable:
    """Create a handler function for an IDL operation."""
    bind_kind = operation.bind.get("kind") if operation.bind else None

    async def idl_handler(request: Request) -> JSONResponse:
        # O handler usa o 'operation' capturado em closure
        # NÃO faz lookup dinâmico do registry
        ...
```

### 5.3 Cache vs Lookup

| Aspecto | Comportamento Atual |
|---------|---------------------|
| Rotas registradas | Uma vez no startup (server.py:221) |
| Operation em handler | Capturada em closure (imutável) |
| Lookup dinâmico | **NÃO EXISTE** - handler usa operation fixa |
| Invalidação | **NÃO EXISTE** - requer restart |

**GAP CRÍTICO:** O handler IDL captura `operation` em closure durante o registro.
Se o registry mudar, o handler continua usando a operation antiga.

---

## 6. Como `/openapi.json` é Gerado (6.5)

### 6.1 Mecanismo de Geração

**Arquivo:** `src/engine/core/openapi_overlay.py:317-333`

```python
def setup_custom_openapi(app: FastAPI) -> None:
    """Setup custom OpenAPI generation for the app."""

    def custom_openapi() -> Dict[str, Any]:
        if app.openapi_schema:  # <-- Cache
            return app.openapi_schema
        app.openapi_schema = create_openapi_schema(app)  # <-- Gera e cacheia
        return app.openapi_schema

    app.openapi = custom_openapi
```

### 6.2 Dependência de Estado em Memória

**Arquivo:** `src/engine/core/openapi_overlay.py:245-247`

```python
def create_openapi_schema(app, dept_id=None, filter_by_dept=False):
    # ...
    ops_def = get_operations(dept_id)  # <-- Lê do _operations global
    if ops_def:
        for op in ops_def.operations:
            _enrich_operation_from_registry(...)
```

### 6.3 Cache e Invalidação

| Aspecto | Comportamento |
|---------|---------------|
| Cache | `app.openapi_schema` (set once) |
| Invalidação manual | `app.openapi_schema = None` |
| Auto-invalidação | **NÃO EXISTE** |
| Depende de | `_operations` global (memory) |

**GAP:** Para refletir novo bundle:
1. Atualizar `_operations` (via `set_operations`)
2. Invalidar `app.openapi_schema = None`
3. Próximo request gera novo schema

---

## 7. Pontos de Integração para Hot-Swap

### 7.1 Candidato: `accept_pin_update_proposal()`

**Arquivo:** `src/engine/core/ege_pins.py:510-521`

```python
# Update institution config with observed hashes and release_id
config_dict["pinned_bundle_manifest_sha256"] = proposal.observed_bundle_manifest_sha256
config_dict["pinned_contract_ledger_sha256"] = proposal.observed_contract_ledger_sha256
if metadata and metadata.get("release_id"):
    config_dict["pinned_release_id"] = metadata["release_id"]

save_active_config(institution_id, config_dict, actor_id)
invalidate_config_cache(institution_id)
# <-- AQUI: Ponto para chamar reload_active_runtime()
```

### 7.2 Candidato: `execute_governed_rollback()`

**Arquivo:** `src/engine/core/ege_rollback.py:296-300`

```python
# Atomic symlink update
os.symlink(pinned_path, temp_path)
os.replace(temp_path, current_link)
# <-- AQUI: Ponto para chamar reload_active_runtime()
```

### 7.3 Comparação de Pontos

| Ponto | Trigger | Prós | Contras |
|-------|---------|------|---------|
| `accept_pin_update_proposal` | Pin aceito | Governado, com audit | Não cobre rollback manual |
| `execute_governed_rollback` | Deploy falhou | Cobre rollback automático | Pode não ter bundle novo |
| Novo endpoint `/admin/reload` | Manual | Flexível | Não governado |

### 7.4 Proposta: Menor Ponto de Integração

**Criar função `reload_active_runtime(institution_id)`** que:
1. Relê bundle do CURRENT symlink
2. Atualiza `_operations` via `set_operations()`
3. Invalida `app.openapi_schema = None`
4. Emite evento `RUNTIME_RELOADED` no ledger

**Chamar em:**
1. Após `accept_pin_update_proposal()` linha 521
2. Após `execute_governed_rollback()` sucesso, linha 333

---

## 8. Estado Global a Considerar

| Global | Módulo | Reload Necessário? |
|--------|--------|-------------------|
| `_bundle_context` | load_bundle.py:98 | ✅ Sim |
| `_operations` | operations.py:84 | ✅ Sim (crítico para router) |
| `_rbac` | rbac.py | ⚠️ Possível (depende de mudança) |
| `_approvals` | approvals.py | ⚠️ Possível |
| `_sod` | sod.py | ⚠️ Possível |
| `_invariants` | invariants.py | ⚠️ Possível |
| `app.routes` | FastAPI | ⚠️ Complexo (rotas já registradas) |
| `app.openapi_schema` | FastAPI | ✅ Sim (fácil: = None) |

---

## 9. Resumo do Mapeamento

| Item | Status | Localização |
|------|--------|-------------|
| CURRENT symlink por instituição | ✅ Existe | release.py, ege_pins.py |
| pinned_release_id em config | ✅ Existe | institution_config.py:125 |
| EGE pin application | ✅ Existe | ege_pins.py:441-554 |
| EGE rollback application | ✅ Existe | ege_rollback.py:196-339 |
| load_bundle() no startup | ✅ Existe | server.py:189 |
| _operations global | ✅ Existe | operations.py:84 |
| IDL router registration | ✅ Existe | idl_router.py:302 |
| OpenAPI cache | ✅ Existe | openapi_overlay.py:328 |
| Reload em runtime | ❌ NÃO EXISTE | - |
| Hot-swap após pin | ❌ NÃO EXISTE | - |
| RUNTIME_RELOADED event | ❌ NÃO EXISTE | - |

---

## 10. Arquivos Relevantes

| Arquivo | Função |
|---------|--------|
| `src/engine/ise/release.py` | CURRENT symlink, bundles root |
| `src/engine/core/ege_pins.py` | Pin proposals, accept/block |
| `src/engine/core/ege_rollback.py` | Governed rollback |
| `src/engine/core/institution_config.py` | pinned_release_id, hashes |
| `src/engine/loader/load_bundle.py` | Bundle loading, BundleContext |
| `src/engine/core/operations.py` | OperationRegistry |
| `src/engine/core/idl_router.py` | Dynamic route registration |
| `src/engine/core/openapi_overlay.py` | OpenAPI generation |
| `src/engine/api/server.py` | Lifespan, startup |
