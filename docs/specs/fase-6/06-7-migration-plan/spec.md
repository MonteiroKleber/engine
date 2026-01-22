# Etapa 6.7 — Migration Plan (legacy → idl sem quebra)

**Status:** ✅ IMPLEMENTADO
**Pré-requisitos:** 6.1–6.6 ✅
**Data de implementação:** 2026-01-21

## 1) Objetivo

Definir e implementar o plano mínimo para migrar de um runtime com rotas legacy (handlers fixos) para um runtime IDL-driven,
sem "big bang" e sem quebrar instalações em produção.

## 2) Estado atual (realidade do código)

- `ENGINE_API_MODE=legacy|idl|both` já existe (6.4).
- `OperationRegistry` + dispatcher já suportam create/read/approvals (6.1–6.3).
- OpenAPI e hot-reload governado estão alinhados (6.5–6.6).

~~Ainda faltam:~~
~~- política explícita de migração por instituição/dept~~
~~- checklists e bloqueios para evitar "switch" incompleto (ex.: dept sem operations.json)~~
~~- observabilidade clara do modo efetivo por instituição (status)~~

**Implementado:**
- ✅ Migration check module (`src/engine/core/migration_check.py`)
- ✅ Integração no boot com fail/warn determinístico
- ✅ Console status mostra migration status (read-only)
- ✅ 22 testes cobrindo todos os cenários

## 3) Decisões canônicas desta etapa

### 3.1 Semântica do modo de API

Manter `ENGINE_API_MODE` como modo "global do processo", mas introduzir **regras de segurança**:

- `ENGINE_API_MODE=idl` só pode subir se:
  - existir `operations.json` para todos os depts carregados ✅
  - dispatcher suportar todos os `bind.kind` usados pelas operações presentes (nesta fase: create/read/approval_decide) ✅
  - não houver colisões fatais de rota (já tratado na 6.4) ✅
- `ENGINE_API_MODE=both` é o modo recomendado para migração:
  - rotas legacy continuam ✅
  - rotas idl aparecem quando não colidem (ou colidem mas são ignoradas com warning) ✅

### 3.2 Critério de "dept migrado"

Um dept é considerado "migrado" quando:

- `operations.json` existe e valida ✅
- para as operações declaradas, o dispatcher cobre os binds necessários (create/read/approval_decide) ✅
- as rotas idl estão ativas (ou seja, registradas sem colisão) ✅

### 3.3 Comunicação no produto (console/status)

O console operacional mostra (read-only) por instituição: ✅

- `ENGINE_API_MODE` atual
- depts instalados vs depts migrados
- lista de operações não suportadas (se houver)
- warnings (em modo `both`)

## 4) Mudanças implementadas

### 4.1 Módulo `migration_check.py`

**Arquivo:** `src/engine/core/migration_check.py`

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

**Bind kinds suportados:** `create`, `read`, `approval_decide`

### 4.2 Integração no boot (`server.py`)

Localização: Entre `run_preflight_checks()` e `register_idl_routes()` (linhas ~240-300)

```python
if api_mode != API_MODE_LEGACY:
    migration_result = run_migration_checks(departments)

    if api_mode == API_MODE_IDL:
        if not migration_result.ok:
            raise RuntimeError(...)  # Hard fail
    else:
        # both mode: log warnings
        for warning in migration_result.warnings:
            logger.warning("MIGRATION_CHECK_WARNING", ...)
```

### 4.3 Console status

**Arquivo:** `src/engine/console/routes.py`

Nova função: `_get_migration_status_info(institution_id, departments)`

**Arquivo:** `src/engine/console/templates/status.html`

Nova seção: "IDL Migration Status" com:
- API Mode (badge colorido)
- Migration Complete (YES/NO)
- Depts Migrated (X / Y)
- Not Migrated (lista)
- Unsupported Binds (contagem)
- Warnings (em modo both)

### 4.4 Error codes

**Arquivo:** `src/engine/core/errors.py`

```python
MIGRATION_CHECK_FAILED = "MIGRATION_CHECK_FAILED"
MIGRATION_MISSING_OPERATIONS = "MIGRATION_MISSING_OPERATIONS"
MIGRATION_UNSUPPORTED_BIND_KIND = "MIGRATION_UNSUPPORTED_BIND_KIND"
```

## 5) Critérios de aceite (Etapa 6.7) ✅

- ✅ Em `ENGINE_API_MODE=idl`, o engine falha deterministicamente se:
  - bundle não tem `operations.json`
  - existir operação com `bind.kind` não suportado pelo dispatcher
- ✅ Em `ENGINE_API_MODE=both`, o engine sobe e:
  - registra warnings determinísticos sobre depts/ops não migrados
  - console status mostra "migrated vs not migrated"
- ✅ Testes cobrem:
  - fail em idl quando ops ausentes
  - warning em both
  - report estruturado do migration check

## 6) Testes

**Arquivo:** `tests/test_migration_check.py`

```bash
pytest tests/test_migration_check.py -v
# 22 passed
```

**Cobertura:**
- MigrationCheckResult dataclass
- run_migration_checks() single-mode e multi-mode
- Missing operations.json detection
- Unsupported bind.kind detection
- get_migration_status() for console
- Boot integration scenarios
- Error codes validation

## 7) Arquivos modificados/criados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `src/engine/core/migration_check.py` | NOVO | Módulo de migration checks |
| `src/engine/api/server.py` | MODIFICADO | Integração no boot |
| `src/engine/core/errors.py` | MODIFICADO | Error codes |
| `src/engine/console/routes.py` | MODIFICADO | `_get_migration_status_info()` |
| `src/engine/console/templates/status.html` | MODIFICADO | Seção Migration Status |
| `tests/test_migration_check.py` | NOVO | 22 testes |
