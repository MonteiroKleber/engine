# Mapeamento - Migration Plan (Etapa 6.7)

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Etapa:** 6.7

---

## 1. Objetivo da Etapa

Definir e implementar o plano mínimo para migrar de um runtime com rotas legacy (handlers fixos) para um runtime IDL-driven, sem "big bang" e sem quebrar instalações em produção.

---

## 2. Onde ENGINE_API_MODE é Lido/Aplicado (6.4)

### 2.1 Definição e Leitura

**Arquivo:** `src/engine/core/idl_router.py:45-54`

```python
def get_api_mode() -> str:
    """Get API mode from ENGINE_API_MODE env var.

    Returns:
        One of: "legacy" (default), "idl", or "both".
    """
    mode = os.environ.get("ENGINE_API_MODE", API_MODE_LEGACY).lower()
    if mode not in VALID_API_MODES:
        return API_MODE_LEGACY
    return mode
```

**Constantes:**
```python
API_MODE_LEGACY = "legacy"
API_MODE_IDL = "idl"
API_MODE_BOTH = "both"
VALID_API_MODES = frozenset({API_MODE_LEGACY, API_MODE_IDL, API_MODE_BOTH})
```

### 2.2 Pontos de Uso no Boot

| Local | Arquivo:Linha | Comportamento |
|-------|---------------|---------------|
| Registro de rotas IDL | server.py:234-261 | Pula se legacy, registra se idl/both |
| Logging no startup | idl_router.py:361 | Loga "skipping" se legacy |
| Collision handling | idl_router.py:387-391 | RuntimeError se idl + collision |
| Collision handling | idl_router.py:392-404 | Warning + skip se both + collision |

### 2.3 Fluxo de Aplicação no Boot

```
lifespan(app)
    |
    v
load_bundle()
    |
    v
reload_on_boot()  # Etapa 6.6
    |
    v
run_preflight_checks()  # <-- AQUI: Ponto para migration checks
    |
    v
api_mode = get_api_mode()
    |
    +-- if api_mode != "legacy":
    |       |
    |       v
    |   register_idl_routes(app, departments)
    |       |
    |       +-- RuntimeError se idl + collision
    |       +-- Warning + skip se both + collision
    |
    v
yield (server running)
```

---

## 3. Onde Seria o Lugar Correto para Migration Checks no Boot

### 3.1 Candidato: Após load_bundle(), Antes de register_idl_routes()

**Arquivo:** `src/engine/api/server.py` (entre linhas 212 e 234)

**Justificativa:**
1. `load_bundle()` já carregou o bundle e populou `_operations` (se existir)
2. `run_preflight_checks()` já rodou validações de segurança
3. Antes de `register_idl_routes()` garante que checks rodem antes de registrar rotas

**Proposta de integração:**

```python
# server.py (após run_preflight_checks, antes de register_idl_routes)

# NEW: Run migration checks (Etapa 6.7)
api_mode = get_api_mode()
if api_mode != API_MODE_LEGACY:
    from engine.core.migration_check import run_migration_checks
    migration_result = run_migration_checks(departments=departments)

    if api_mode == API_MODE_IDL:
        # idl mode: fail if migration incomplete
        if not migration_result.ok:
            raise RuntimeError(
                f"Migration check failed: [{migration_result.code}] {migration_result.message}"
            )
    else:
        # both mode: log warnings
        for warning in migration_result.warnings:
            logger.warning("MIGRATION_CHECK_WARNING", extra={"warning": warning})
```

### 3.2 Alternativa: Dentro de run_preflight_checks()

**Arquivo:** `src/engine/core/preflight.py` (adicionar check_migration())

**Prós:**
- Mantém todos os checks de startup em um lugar
- Segue padrão existente de PreflightResult

**Contras:**
- Precisa passar `api_mode` como parâmetro
- Lógica de fail vs warning é diferente dos outros checks

### 3.3 Decisão Proposta

**Opção escolhida: Candidato 3.1** (integrar diretamente no server.py)

**Razão:** O comportamento de fail vs warning é específico do api_mode, que é diferente da lógica de preflight (que sempre falha ou passa).

---

## 4. Como o Console Status Coleta Informações Hoje

### 4.1 Endpoint Principal

**Arquivo:** `src/engine/console/routes.py:937-986`

```python
@router.get("/status", response_class=HTMLResponse)
async def console_status(
    request: Request,
    institution_id: str = Query(..., description="Institution UUID"),
    dept_id: Optional[str] = Query(None, description="Department ID"),
    ...
) -> HTMLResponse:
    health = _get_health_info()
    pin_status = _get_pin_status_info(institution_id)
    config = _get_institution_config_info(institution_id)
    mandates = _get_effective_mandates_info(institution_id, dept_id)

    return templates.TemplateResponse("status.html", {...})
```

### 4.2 Funções de Coleta de Dados

| Função | Arquivo:Linha | Dados Coletados |
|--------|---------------|-----------------|
| `_get_health_info()` | routes.py:313-320 | status, mode, reason_code, details |
| `_get_pin_status_info()` | routes.py:323-343 | pinned, observed, drift_status |
| `_get_institution_config_info()` | routes.py:~350 | config flags, freeze, limits |
| `_get_effective_mandates_info()` | routes.py:~400 | mandates per dept |

### 4.3 Template status.html

**Arquivo:** `src/engine/console/templates/status.html`

**Seções atuais:**
1. Runtime Status (mode, reason_code)
2. Drift Status (pinned, observed)
3. Institution Configuration (freeze, safe_mode, limits)
4. Mandates (per dept)

### 4.4 Onde Injetar "migrated vs not migrated"

**Proposta: Nova função `_get_migration_status_info()`**

```python
def _get_migration_status_info(institution_id: str) -> Dict[str, Any]:
    """Get migration status for an institution."""
    from engine.core.migration_check import get_migration_status

    return {
        "api_mode": get_api_mode(),
        "depts_installed": [...],
        "depts_migrated": [...],
        "depts_not_migrated": [...],
        "unsupported_binds": [...],  # bind.kind não suportados
    }
```

**Integração no template:**
```html
<!-- Migration Status (NEW) -->
<div class="card">
    <h3 class="card-title">IDL Migration Status</h3>
    <div class="info-row">
        <span class="info-label">API Mode</span>
        <span class="info-value">{{ migration.api_mode }}</span>
    </div>
    <div class="info-row">
        <span class="info-label">Depts Migrated</span>
        <span class="info-value">{{ migration.depts_migrated|length }} / {{ migration.depts_installed|length }}</span>
    </div>
</div>
```

---

## 5. Bind Kinds Suportados pelo Dispatcher

### 5.1 Handlers no IDL Router

**Arquivo:** `src/engine/core/idl_router.py:247-320`

| bind.kind | Dispatcher | Status |
|-----------|------------|--------|
| `create` | `dispatch_create()` | ✅ Suportado |
| `read` | `dispatch_read()` | ✅ Suportado |
| `approval_decide` | `dispatch_approval_decide()` | ✅ Suportado |
| (outros) | N/A | ❌ Retorna 501 |

**Código para bind.kind não suportado:**
```python
else:
    # Unknown bind.kind
    return JSONResponse(
        status_code=501,
        content={
            "code": "BIND_KIND_UNSUPPORTED",
            "message": f"Unsupported bind.kind: {bind_kind}",
        },
    )
```

### 5.2 Critério de "Dept Migrado"

Segundo spec 3.2, um dept é "migrado" quando:
1. `operations.json` existe e valida ✅
2. Para as operações declaradas, o dispatcher cobre os binds necessários ✅
3. As rotas idl estão ativas (registradas sem colisão) ✅

---

## 6. Estado Atual de Carregamento de operations.json

### 6.1 Single Mode

**Arquivo:** `src/engine/loader/load_bundle.py:627-654`

```python
def _load_operations_single_mode(bundle_path: Path) -> bool:
    operations_path = bundle_path / "operations.json"
    if operations_path.exists():
        # Carrega e valida
        ops_def = load_operations_from_file(operations_path)
        set_operations(None, ops_def)
    else:
        # No operations.json - legacy mode
        set_operations(None, None)  # <-- NENHUM ERRO!
    return True
```

### 6.2 Multi Mode

**Arquivo:** `src/engine/loader/load_bundle.py:657-685`

```python
def _load_operations_multi_mode(bundle_path: Path, bundle_ctx: BundleContext) -> bool:
    for dept_id, dept_contracts in bundle_ctx.departments.items():
        operations_path = dept_contracts.path / "operations.json"
        if operations_path.exists():
            ops_def = load_operations_from_file(operations_path)
            set_operations(dept_id, ops_def)
        else:
            # No operations.json for this dept - legacy mode
            set_operations(dept_id, None)  # <-- NENHUM ERRO!
    return True
```

### 6.3 GAP: Não há Validação de Obrigatoriedade

Atualmente, `operations.json` é **opcional**. Isso é correto para `ENGINE_API_MODE=legacy|both`, mas **incorreto** para `ENGINE_API_MODE=idl` onde deveria falhar.

---

## 7. Fluxo de Boot Completo (Relevante para Migration)

```
lifespan(app) [server.py:157]
    |
    ├── setup_logging()
    ├── verify_ledger_file()
    |
    ├── load_bundle() [server.py:189]
    |       |
    |       ├── _load_operations_single_mode() ou _load_operations_multi_mode()
    |       |       (popula _operations, SEM ERRO se não existir)
    |       |
    |       └── set_operations(dept_id, ops_def ou None)
    |
    ├── reload_on_boot() [server.py:194]  # Etapa 6.6
    |
    ├── run_preflight_checks() [server.py:216]
    |       |
    |       ├── check_path_isolation()
    |       ├── check_console_session_secret()
    |       └── check_prod_mode_requirements()
    |       (NÃO inclui migration check!)
    |
    ├── [AQUI: Migration checks devem entrar]
    |
    ├── api_mode = get_api_mode() [server.py:236]
    |
    └── if api_mode != "legacy":
            register_idl_routes(app, departments) [server.py:243]
                |
                ├── get_operations(dept_id)
                |       (pode retornar None se não existir)
                |
                ├── Para cada op: add_api_route()
                |
                └── RuntimeError se collision em idl mode
```

---

## 8. Arquivos Relevantes

| Arquivo | Função |
|---------|--------|
| `src/engine/core/idl_router.py` | get_api_mode(), register_idl_routes() |
| `src/engine/api/server.py` | lifespan(), integração de boot |
| `src/engine/core/preflight.py` | run_preflight_checks(), padrão de checks |
| `src/engine/loader/load_bundle.py` | _load_operations_*_mode() |
| `src/engine/core/operations.py` | get_operations(), set_operations() |
| `src/engine/console/routes.py` | console_status(), _get_*_info() |
| `src/engine/console/templates/status.html` | Template do status |
| `src/engine/core/dispatcher.py` | dispatch_create/read/approval_decide |

---

## 9. Resumo do Mapeamento (PÓS-IMPLEMENTAÇÃO)

| Item | Status | Localização |
|------|--------|-------------|
| ENGINE_API_MODE leitura | ✅ Existe | idl_router.py:45-54 |
| ENGINE_API_MODE aplicação | ✅ Existe | server.py:240-310 |
| Preflight checks pattern | ✅ Existe | preflight.py:199-229 |
| Console status collection | ✅ Existe | routes.py:985-1020 |
| Migration check module | ✅ IMPLEMENTADO | migration_check.py |
| Validação obrigatória ops.json | ✅ IMPLEMENTADO | migration_check.py:run_migration_checks() |
| Validação bind.kind coverage | ✅ IMPLEMENTADO | migration_check.py:SUPPORTED_BIND_KINDS |
| Console migrated vs not | ✅ IMPLEMENTADO | routes.py:_get_migration_status_info() |
| Fail determinístico em idl | ✅ IMPLEMENTADO | server.py (RuntimeError) |
| Warnings determinísticos em both | ✅ IMPLEMENTADO | server.py (logger.warning) |
