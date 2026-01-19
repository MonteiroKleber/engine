# Multi-Tenant Hardening - Gaps Analysis

**Data:** 2026-01-18
**Tipo:** Análise de gaps para PROMPT 2.6.1
**Status:** ✅ IMPLEMENTADO (PROMPT 2.6.2)

---

## Resumo Executivo

Todos os gaps críticos foram resolvidos. O engine agora detecta e bloqueia configurações perigosas no startup quando multi-tenant está ativo.

1. ✅ **GAP-1: Ledger path absoluto** - Bloqueado via preflight check
2. ✅ **GAP-2: State store dir absoluto** - Bloqueado via preflight check
3. ✅ **GAP-3: Preflight check** - Implementado em `server.py` lifespan
4. ✅ **GAP-4: Validação automática** - Preflight valida quando `require_institution_header_for_runtime=true`
5. ⏭️ **GAP-5: SAFE_MODE** - Decisão: usar HARD FAIL ao invés de SAFE_MODE (mais seguro)

---

## GAP-1: Ledger Path Absoluto Não Bloqueado ✅ RESOLVIDO

### Solução Implementada
**Opção A escolhida:** Bloquear paths absolutos quando multi-tenant está ativo (fail startup).

```python
# src/engine/core/preflight.py
CRITICAL_PATH_ENVS = {
    "ENGINE_LEDGER_PATH": PATH_MISCONFIG_ABSOLUTE_LEDGER,
    "ENGINE_STATE_STORE_DIR": PATH_MISCONFIG_ABSOLUTE_STATE_STORE,
}

def check_path_isolation(require_multi_tenant: bool = False) -> PreflightResult:
    if not require_multi_tenant:
        return PreflightResult(ok=True)

    for env_name, error_code in CRITICAL_PATH_ENVS.items():
        env_value = os.environ.get(env_name)
        if env_value is not None and Path(env_value).is_absolute():
            return PreflightResult(
                ok=False,
                code=error_code,
                message=f"{env_name} cannot be absolute in multi-tenant mode",
            )
    return PreflightResult(ok=True)
```

### Arquivos Modificados
- `src/engine/core/preflight.py` - Novo módulo de preflight checks
- `src/engine/core/errors.py` - Novos códigos de erro

---

## GAP-2: State Store Dir Absoluto Não Bloqueado ✅ RESOLVIDO

### Solução Implementada
Mesma solução que GAP-1. Ambas variáveis são verificadas no preflight.

---

## GAP-3: Falta de Preflight Check para Misconfig ✅ RESOLVIDO

### Solução Implementada
Preflight check integrado no lifespan do servidor:

```python
# src/engine/api/server.py (lifespan)
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ... logging setup ...
    # ... ledger integrity check ...
    # ... bundle loading ...

    # Run preflight checks for multi-tenant path isolation
    preflight_result = run_preflight_checks()
    if not preflight_result.ok:
        logger.error(
            "PREFLIGHT_CHECK_FAILED",
            extra={
                "event": "PREFLIGHT_CHECK_FAILED",
                "code": preflight_result.code,
                "message": preflight_result.message,
                "details": preflight_result.details,
            },
        )
        # Hard fail - do not start the server
        raise RuntimeError(
            f"Preflight check failed: [{preflight_result.code}] {preflight_result.message}"
        )

    yield
```

### Arquivos Modificados
- `src/engine/api/server.py` - Integração do preflight no lifespan

---

## GAP-4: require_institution_header Não Valida Paths ✅ RESOLVIDO

### Solução Implementada
O preflight check automaticamente detecta quando `require_institution_header_for_runtime=true` está ativo em qualquer instituição:

```python
# src/engine/core/preflight.py
def is_multi_tenant_mode_active() -> bool:
    """Check if any institution has require_institution_header_for_runtime=true."""
    registry = get_registry()
    institutions = registry.list_institutions(limit=1000)
    for inst in institutions:
        config = get_effective_config(inst.institution_id)
        if config.flags.require_institution_header_for_runtime:
            return True
    return False

def run_preflight_checks() -> PreflightResult:
    multi_tenant_active = is_multi_tenant_mode_active()
    return check_path_isolation(require_multi_tenant=multi_tenant_active)
```

---

## GAP-5: SAFE_MODE Não Ativado por Misconfig de Path ⏭️ SUBSTITUÍDO

### Decisão
Em vez de SAFE_MODE, optamos por **HARD FAIL** no startup. Justificativa:
- Path misconfig é configuração errada, não erro de runtime
- Melhor falhar rápido do que operar em modo degradado com risco de vazamento
- Admin precisa corrigir configuração antes de iniciar

---

## Matriz de Gaps (Final)

| Gap | Descrição | Status | Arquivos Modificados |
|-----|-----------|--------|---------------------|
| GAP-1 | Ledger path absoluto | ✅ | preflight.py, errors.py |
| GAP-2 | State store dir absoluto | ✅ | preflight.py, errors.py |
| GAP-3 | Falta preflight check | ✅ | server.py, preflight.py |
| GAP-4 | require_institution_header incompleto | ✅ | preflight.py |
| GAP-5 | SAFE_MODE não ativado | ⏭️ | Substituído por HARD FAIL |

---

## Decisões Tomadas

| ID | Questão | Decisão |
|----|---------|---------|
| D-1 | Como tratar path absoluto detectado? | **Opção A: Fail startup** |
| D-2 | Quais ENVs são "críticos"? | `ENGINE_LEDGER_PATH`, `ENGINE_STATE_STORE_DIR` |
| D-3 | Permitir override via flag? | **Opção A: Nunca** (em multi-tenant) |

---

## Arquivos Criados/Modificados

### Novos Arquivos
- `src/engine/core/preflight.py` - Módulo de preflight checks
- `tests/test_path_misconfig.py` - Testes de detecção de misconfig (20 testes)

### Arquivos Modificados
- `src/engine/core/errors.py` - Novos códigos:
  - `PATH_MISCONFIG_ABSOLUTE_LEDGER`
  - `PATH_MISCONFIG_ABSOLUTE_STATE_STORE`
- `src/engine/api/server.py` - Integração do preflight no lifespan

---

## Verificação

### Testes
```bash
pytest tests/test_path_misconfig.py -v
# 20 passed
```

### Cenários Cobertos
- ✅ `check_path_isolation` permite qualquer path quando `require_multi_tenant=False`
- ✅ `check_path_isolation` permite paths relativos em multi-tenant
- ✅ `check_path_isolation` permite paths não definidos em multi-tenant
- ✅ `check_path_isolation` rejeita `ENGINE_LEDGER_PATH` absoluto em multi-tenant
- ✅ `check_path_isolation` rejeita `ENGINE_STATE_STORE_DIR` absoluto em multi-tenant
- ✅ `is_multi_tenant_mode_active` retorna False sem instituições
- ✅ `is_multi_tenant_mode_active` retorna False com instituições sem flag
- ✅ `is_multi_tenant_mode_active` retorna True com uma instituição com flag
- ✅ `run_preflight_checks` passa sem multi-tenant
- ✅ `run_preflight_checks` falha com path absoluto em multi-tenant
- ✅ Single-tenant permite paths absolutos (backward compatible)
- ✅ Se UMA instituição é strict, paths absolutos são bloqueados para TODAS

---

## Comportamento Final

### Multi-Tenant Ativo
Quando `require_institution_header_for_runtime=true` em qualquer instituição:
```
ENGINE_LEDGER_PATH=/var/audit.jsonl
→ RuntimeError: Preflight check failed: [PATH_MISCONFIG_ABSOLUTE_LEDGER] ...
```

### Single-Tenant/Dev
Quando nenhuma instituição tem `require_institution_header_for_runtime=true`:
```
ENGINE_LEDGER_PATH=/var/audit.jsonl
→ OK (backward compatible)
```
