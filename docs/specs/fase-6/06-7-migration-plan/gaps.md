# Gaps e Decisões - Migration Plan (Etapa 6.7)

**Data:** 2026-01-21
**Status:** ✅ IMPLEMENTADO
**Etapa:** 6.7

---

## 1. Gaps Identificados (TODOS RESOLVIDOS)

### Gap 1: Não Existe Módulo de Migration Check ✅

**Problema:**
Não existia um módulo dedicado para validar se um dept/bundle está pronto para operar em modo IDL.

**Solução Implementada:**
Criado `src/engine/core/migration_check.py` com:
```python
@dataclass
class MigrationCheckResult:
    ok: bool
    code: str  # MIGRATION_OK, MIGRATION_MISSING_OPERATIONS, MIGRATION_UNSUPPORTED_BIND_KIND
    message: str
    warnings: List[str]
    depts_migrated: List[str]
    depts_not_migrated: List[str]
    unsupported_binds: List[UnsupportedBind]

def run_migration_checks(departments: Optional[List[str]]) -> MigrationCheckResult
def get_migration_status(institution_id: str, departments: Optional[List[str]]) -> Dict[str, Any]
```

---

### Gap 2: operations.json Não É Validado Como Obrigatório em IDL Mode ✅

**Problema:**
Em `load_bundle.py`, quando `operations.json` não existe, o código define `set_operations(dept_id, None)` sem erro.

**Solução Implementada:**
Validação movida para `run_migration_checks()`:
- Verifica `get_operations(dept_id)` para cada dept
- Se `None`, marca dept como não migrado
- Em `ENGINE_API_MODE=idl`, isso causa `RuntimeError` no boot

---

### Gap 3: bind.kind Coverage Não É Validado no Boot ✅

**Problema:**
Não havia validação no boot para verificar se todos os `bind.kind` das operações são suportados.

**Solução Implementada:**
- `SUPPORTED_BIND_KINDS = {"create", "read", "approval_decide"}`
- `run_migration_checks()` valida cada operação
- Bind.kind não suportado marca dept como não migrado

---

### Gap 4: Console Não Mostra Status de Migração ✅

**Problema:**
O console status não exibia informações de migração.

**Solução Implementada:**
- Nova função `_get_migration_status_info()` em `routes.py`
- Nova seção "IDL Migration Status" em `status.html`
- Exibe: API Mode, Migration Complete, Depts Migrated, Not Migrated, Unsupported Binds, Warnings

---

### Gap 5: Não Há Fail Determinístico em IDL Mode ✅

**Problema:**
Spec exigia que `ENGINE_API_MODE=idl` falhasse deterministicamente se checks falhassem.

**Solução Implementada:**
Em `server.py`, após `run_preflight_checks()`:
```python
if api_mode == API_MODE_IDL:
    if not migration_result.ok:
        raise RuntimeError(
            f"Migration check failed: [{migration_result.code}] {migration_result.message}. "
            f"Depts not migrated: {migration_result.depts_not_migrated}"
        )
```

---

### Gap 6: Não Há Warnings Determinísticos em Both Mode ✅

**Problema:**
Spec exigia que `ENGINE_API_MODE=both` registrasse warnings determinísticos.

**Solução Implementada:**
Em `server.py`:
```python
else:  # both mode
    for warning in migration_result.warnings:
        logger.warning("MIGRATION_CHECK_WARNING", extra={"warning": warning})
```

---

## 2. Matriz de Resolução

| Gap | Solução | Arquivo(s) | Status |
|-----|---------|------------|--------|
| Gap 1 | Criar `migration_check.py` | `src/engine/core/migration_check.py` | ✅ |
| Gap 2 | Check em `run_migration_checks()` | `migration_check.py` | ✅ |
| Gap 3 | Check em `run_migration_checks()` | `migration_check.py` | ✅ |
| Gap 4 | `_get_migration_status_info()` + template | `routes.py`, `status.html` | ✅ |
| Gap 5 | `RuntimeError` no boot | `server.py` | ✅ |
| Gap 6 | `logger.warning()` no boot | `server.py` | ✅ |

---

## 3. Testes Implementados

**Arquivo:** `tests/test_migration_check.py` (22 testes)

- ✅ `test_supported_bind_kinds_matches_dispatcher`
- ✅ `test_ok_result`
- ✅ `test_failed_result_missing_ops`
- ✅ `test_failed_result_unsupported_bind`
- ✅ `test_to_dict`
- ✅ `test_single_mode_all_migrated`
- ✅ `test_single_mode_no_operations`
- ✅ `test_multi_mode_all_migrated`
- ✅ `test_multi_mode_partial_migration`
- ✅ `test_unsupported_bind_kind`
- ✅ `test_operation_without_bind`
- ✅ `test_all_supported_bind_kinds`
- ✅ `test_returns_dict_for_template`
- ✅ `test_single_mode_without_departments`
- ✅ `test_includes_warnings`
- ✅ `test_idl_mode_fails_without_operations`
- ✅ `test_idl_mode_fails_with_unsupported_bind`
- ✅ `test_both_mode_does_not_fail`
- ✅ `test_legacy_mode_not_checked`
- ✅ `test_migration_check_import`
- ✅ `test_idl_router_api_mode_constants`
- ✅ `test_migration_error_codes_exist`

---

## 4. Arquivos Modificados/Criados

| Arquivo | Modificação |
|---------|-------------|
| `src/engine/core/migration_check.py` | **NOVO** - MigrationCheckResult + run_migration_checks + get_migration_status |
| `src/engine/api/server.py` | Integração migration checks no boot |
| `src/engine/core/errors.py` | MIGRATION_* error codes |
| `src/engine/console/routes.py` | `_get_migration_status_info()` + chamada em `console_status()` |
| `src/engine/console/templates/status.html` | Seção "IDL Migration Status" |
| `tests/test_migration_check.py` | **NOVO** - 22 testes |
