# Mapeamento - Dynamic Router (Etapa 6.4)

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Etapa:** 6.4 (Concluída)

---

## 1. Objetivo da Etapa

Publicar no FastAPI rotas HTTP reais baseadas no `OperationRegistry`, de forma que:
- O engine exponha endpoints definidos no contrato (`operations.json`)
- Cada request seja roteada para o **dispatcher** (não para handlers hardcoded)
- Rotas legacy continuem funcionando (compatibilidade)

---

## 2. Arquitetura FastAPI Atual

### 2.1 Criação do App

**Arquivo:** `src/engine/api/server.py:257`

```python
app = FastAPI(title="Libervia Engine", version="8.1.1", lifespan=lifespan)
```

### 2.2 Inclusão de Routers Legacy

**Arquivo:** `src/engine/api/server.py:259-278`

```python
# Include routers
app.include_router(finance_router)         # prefix="/finance"
app.include_router(dept_finance_router)    # prefix="/d/{dept}/finance"
app.include_router(support_router)         # prefix="/support"
app.include_router(dept_support_router)    # prefix="/d/{dept}/support"
app.include_router(approvals_router)       # prefix="/approvals"
app.include_router(nl_router)              # prefix="/nl"
app.include_router(ise_router)             # prefix="/ise"
app.include_router(pipeline_router)        # prefix="/pipeline"
app.include_router(contracts_router)       # prefix="/d/{dept}/contracts"
app.include_router(admin_institutions_router)        # prefix="/admin"
app.include_router(admin_institution_config_router)  # prefix="/admin"
app.include_router(admin_keys_router)                # prefix="/admin/institutions"
app.include_router(admin_ege_router)                 # prefix="/admin/ege"
app.include_router(admin_mandates_router)            # prefix="/admin/mandates"
app.include_router(admin_policies_router)            # prefix="/admin/policies"
app.include_router(admin_autonomy_router)            # prefix="/admin/autonomy"
app.include_router(admin_depts_router)               # prefix="/admin/institutions"
app.include_router(admin_actors_router)              # prefix="/admin/institutions"
app.include_router(console_router)                   # prefix="/console"
```

### 2.3 Rotas Legacy por Prefixo

| Prefixo | Router | Rotas Principais |
|---------|--------|------------------|
| `/finance` | finance_router | `POST /expenses`, `GET /expenses/{id}` |
| `/d/{dept}/finance` | dept_finance_router | `POST /expenses`, `GET /expenses/{id}` |
| `/support` | support_router | `POST /tickets` |
| `/d/{dept}/support` | dept_support_router | `POST /tickets` |
| `/approvals` | approvals_router | `POST /{id}/decide` |
| `/admin/*` | admin_* | Gestão institucional |
| `/console/*` | console_router | UI de visualização |

---

## 3. Lifespan e load_bundle()

### 3.1 Localização

**Arquivo:** `src/engine/api/server.py:154-255`

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup/shutdown."""
    setup_logging()

    # Verify ledger integrity
    ledger_path = get_ledger_path()
    if ledger_path.exists():
        verify_result = verify_ledger_file(ledger_path)
        # ... handle verification ...

    # Startup: load bundle
    load_bundle()  # <-- OperationRegistry é populado aqui
    logger.info("Bundle loaded, engine ready")

    # Run preflight checks
    preflight_result = run_preflight_checks()
    # ...

    yield  # <-- App está pronto, rotas podem ser acessadas

    # Shutdown
    logger.info("Shutting down Libervia Engine...")
```

### 3.2 Sequência de Inicialização

1. `setup_logging()` - Configura logging
2. `verify_ledger_file()` - Verifica integridade do ledger
3. **`load_bundle()`** - Carrega bundle e popula OperationRegistry
4. `run_preflight_checks()` - Validações de segurança
5. `cleanup_dev_runs()` - Limpeza opcional
6. `yield` - App pronto para receber requests

### 3.3 Ponto de Integração para Rotas Dinâmicas

**Após `load_bundle()` e antes de `yield`** é o ponto ideal para registrar rotas dinâmicas:

```python
# Proposta de integração (linha ~188)
load_bundle()
logger.info("Bundle loaded, engine ready")

# NOVO: Registrar rotas IDL se ENGINE_API_MODE != "legacy"
api_mode = os.environ.get("ENGINE_API_MODE", "legacy")
if api_mode in ("idl", "both"):
    register_idl_routes(app)  # <-- Função a ser criada
```

---

## 4. OperationRegistry

### 4.1 Módulo

**Arquivo:** `src/engine/core/operations.py`

### 4.2 Estruturas de Dados

```python
@dataclass
class Operation:
    operation_id: str      # e.g., "expense_create"
    method: str            # GET, POST, PUT, PATCH, DELETE
    path: str              # e.g., "/finance/expenses"
    endpoint_sig: str      # e.g., "POST /finance/expenses"
    permission: str        # e.g., "expense.create"
    scope: str             # "tenant" or "global"
    idempotency: str       # "required", "optional", "none"
    errors: List[int]
    bind: Optional[Dict]   # {"kind": "create", "entity": "Expense"}

@dataclass
class OperationsDef:
    dept_id: Optional[str]
    operations: List[Operation]
```

### 4.3 Funções de Acesso

| Função | Descrição |
|--------|-----------|
| `get_operations(dept_id)` | Retorna OperationsDef para dept |
| `get_operation_by_endpoint_sig(dept_id, sig)` | Lookup por "POST /path" |
| `get_operation_by_method_path(dept_id, method, path)` | Lookup por método+path |
| `set_operations(dept_id, ops_def)` | Define operações para dept |
| `reset_all_operations()` | Limpa registry (para testes) |

### 4.4 Carregamento

**Em `load_bundle()`:** `src/engine/loader/load_bundle.py:952-959`

```python
# 7. Load operations registry (optional - bundles without operations.json work in legacy mode)
reset_all_operations()
if bundle_ctx.mode == "single":
    if not _load_operations_single_mode(bundle_path):
        return None
else:
    if not _load_operations_multi_mode(bundle_path, bundle_ctx):
        return None
```

### 4.5 Arquivos de Operações

| Modo | Arquivo |
|------|---------|
| Single | `{bundle}/operations.json` |
| Multi | `{bundle}/departments/{dept}/operations.json` |

---

## 5. Rotas Candidatas a Colisão

### 5.1 Rotas Legacy Finance

| Rota Legacy | endpoint_sig IDL |
|-------------|------------------|
| `POST /finance/expenses` | `POST /finance/expenses` |
| `GET /finance/expenses/{expense_id}` | `GET /finance/expenses/{expense_id}` |

### 5.2 Rotas Legacy Support

| Rota Legacy | endpoint_sig IDL |
|-------------|------------------|
| `POST /support/tickets` | `POST /support/tickets` |

### 5.3 Rotas Legacy Approvals

| Rota Legacy | endpoint_sig IDL |
|-------------|------------------|
| `POST /approvals/{approval_id}/decide` | `POST /approvals/{approval_id}/decide` |

---

## 6. Modos de Operação Propostos

### 6.1 ENGINE_API_MODE

| Valor | Comportamento |
|-------|---------------|
| `legacy` (default) | Apenas rotas existentes (finance_router, etc.) |
| `idl` | Apenas rotas geradas do OperationRegistry |
| `both` | Rotas legacy + rotas IDL |

### 6.2 Estratégia de Colisão

**Modo `idl`:**
- Se rota IDL colide com legacy no mesmo método/path: **bloquear startup**
- Registrar no log qual colisão foi detectada

**Modo `both`:**
- Se colisão detectada: **log warning**, mas continuar
- FastAPI usa ordem de registro: primeira rota vence
- IDL routes devem ser registradas APÓS legacy para não sobrescrever

---

## 7. Middlewares Existentes

### 7.1 Ordem de Execução (inversa à inclusão)

1. `logging_middleware` - Log de requests
2. `institution_middleware` - Resolve X-Institution-Id
3. `request_id_middleware` - Gerencia X-Request-Id
4. `dept_routing_middleware` - Resolve /d/{dept}/
5. `ege_drift_middleware` - Bloqueia se drift ativo
6. `freeze_emergency_stop_middleware` - Bloqueia se frozen
7. `legacy_routes_middleware` - Bloqueia legacy se `allow_legacy_routes=false`
8. `rate_limit_middleware` - Rate limiting
9. `body_size_middleware` - Limite de body size
10. `security_headers_middleware` - Headers de segurança

### 7.2 Impacto nas Rotas IDL

Todos os middlewares continuam funcionando para rotas IDL porque:
- São registrados no `app` global
- Executam antes de qualquer handler

---

## 8. Handler Wrapper Proposto

### 8.1 Função `idl_route_handler`

```python
async def idl_route_handler(
    request: Request,
    operation: Operation,
) -> JSONResponse:
    """Generic handler for IDL-driven routes."""

    # 1. Extract institution_id from header
    institution_id = get_request_institution_id(request)

    # 2. Infer dept_id from path or operation scope
    dept_id = infer_dept_id(request, operation)

    # 3. Build ActorContext from headers
    actor = build_actor_context(request)

    # 4. Route to correct dispatcher based on bind.kind
    bind_kind = operation.bind.get("kind") if operation.bind else None

    if bind_kind == "create":
        # Check if approval required
        policy = get_approvals_policy(dept_id)
        rule = policy.get_rule_for_api(operation.endpoint_sig) if policy else None
        if rule:
            return await dispatch_approval_request(...)
        else:
            return await dispatch_create(...)

    elif bind_kind == "read":
        return await dispatch_read(...)

    elif bind_kind == "approval_decide":
        return await dispatch_approval_decide(...)

    else:
        raise HTTPException(status_code=501, detail="Unknown bind.kind")
```

### 8.2 Registro de Rotas

```python
def register_idl_routes(app: FastAPI) -> None:
    """Register routes from OperationRegistry."""

    # Get all departments
    bundle_ctx = get_bundle_context()
    if bundle_ctx is None:
        return

    depts = list(bundle_ctx.departments.keys()) if bundle_ctx.mode == "multi" else [None]

    for dept_id in depts:
        ops_def = get_operations(dept_id)
        if ops_def is None:
            continue

        for op in ops_def.operations:
            # Check for collision with legacy routes
            if _has_collision(app, op.method, op.path):
                api_mode = os.environ.get("ENGINE_API_MODE", "legacy")
                if api_mode == "idl":
                    raise RuntimeError(f"Route collision: {op.endpoint_sig}")
                else:
                    logger.warning(f"Route collision (skipping IDL): {op.endpoint_sig}")
                    continue

            # Create handler closure
            handler = _create_handler(op)

            # Register route
            app.add_api_route(
                path=op.path,
                endpoint=handler,
                methods=[op.method],
                name=op.operation_id,
            )
```

---

## 9. Verificação de Colisões

### 9.1 Função `_has_collision`

```python
def _has_collision(app: FastAPI, method: str, path: str) -> bool:
    """Check if route already exists in app."""
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            if route.path == path and method in route.methods:
                return True
    return False
```

### 9.2 Colisões Esperadas

| endpoint_sig | Rota Legacy | Colide? |
|--------------|-------------|---------|
| `POST /finance/expenses` | finance_router | ✅ SIM |
| `GET /finance/expenses/{expense_id}` | finance_router | ✅ SIM |
| `POST /approvals/{approval_id}/decide` | approvals_router | ✅ SIM |
| `POST /support/tickets` | support_router | ✅ SIM |

---

## 10. Arquivos a Modificar

| Arquivo | Modificação |
|---------|-------------|
| `src/engine/api/server.py` | Adicionar `register_idl_routes()` no lifespan |
| `src/engine/core/idl_router.py` | **NOVO** - Handler wrapper e registro de rotas |
| `tests/test_idl_router.py` | **NOVO** - Testes para rotas IDL |

---

## 11. Dependências

### 11.1 Módulos Necessários

- `engine.core.operations` - OperationRegistry (✅ existe)
- `engine.core.dispatcher` - dispatch_create, dispatch_read, dispatch_approval_* (✅ existe)
- `engine.core.approvals` - get_approvals_policy (✅ existe)
- `engine.loader.load_bundle` - get_bundle_context (✅ existe)

### 11.2 Variável de Ambiente

- `ENGINE_API_MODE` - **NOVA** - Controla modo de operação

---

## 12. Resumo do Mapeamento

| Item | Status | Localização |
|------|--------|-------------|
| FastAPI app criado | ✅ Mapeado | server.py:257 |
| Routers legacy incluídos | ✅ Mapeado | server.py:259-278 |
| lifespan com load_bundle() | ✅ Mapeado | server.py:186 |
| OperationRegistry disponível | ✅ Mapeado | operations.py |
| Ponto de integração | ✅ Implementado | server.py:189-207 |
| Colisões de rota | ✅ Tratadas | idl_router.py |
| Middlewares | ✅ Compatíveis | Funcionam para rotas IDL |

---

## 13. Implementação Realizada (2026-01-21)

| Componente | Arquivo | Status |
|------------|---------|--------|
| IDL Router | `src/engine/core/idl_router.py` | ✅ Criado |
| Lifespan integration | `src/engine/api/server.py:189-207` | ✅ Modificado |
| Testes | `tests/test_idl_router.py` | ✅ Criado (21 testes) |

### 13.1 Funções Implementadas

```python
# src/engine/core/idl_router.py

def get_api_mode() -> str
def register_idl_routes(app, departments) -> int
def _normalize_path_for_collision(path) -> str
def _has_collision(app, method, path) -> bool
def _create_idl_handler(operation, dept_from_path) -> Callable
def _build_actor_context_from_request(request) -> ActorContext
```

### 13.2 Multi-dept Support

Para bundles multi-dept, cada operação gera 2 rotas:
- Base: `/finance/expenses`
- Dept variant: `/d/{dept_id}/finance/expenses`
