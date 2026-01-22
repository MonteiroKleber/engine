# 05-1 Multi-Dept Activation Model — Gaps Analysis

**Status:** IMPLEMENTED
**Data:** 2026-01-20
**Baseado em:** spec.md, flow.md, implementação final

---

## 1. Resumo do Estado Atual

### O que existe (ATUALIZADO)

| Componente | Status | Localização |
|------------|--------|-------------|
| Bundle loader (single/multi mode) | ✅ Existe | `src/engine/loader/load_bundle.py` |
| Dept routing middleware | ✅ Existe + Validação | `src/engine/api/server.py:666-720` |
| Dept context (get/set) | ✅ Existe | `src/engine/core/dept_context.py` |
| Bundle CURRENT symlink | ✅ Existe | `var/institutions/{id}/bundles/CURRENT` |
| InstitutionConfig (pinned hashes) | ✅ Existe | `src/engine/core/institution_config.py` |
| Default dept config | ✅ Existe | `InstitutionConfig.defaults.default_dept` |
| Ledger append | ✅ Existe | `src/engine/core/ledger.py` |
| EGE drift detection | ✅ Existe | `src/engine/core/ege_pins.py` |
| **Active Depts Module** | ✅ NOVO | `src/engine/core/active_depts.py` |
| **Admin Depts API** | ✅ NOVO | `src/engine/api/admin_depts.py` |
| **Active Depts Tests** | ✅ NOVO | `tests/test_active_depts.py` |

### Gaps Fechados (IMPLEMENTADOS)

| Componente | Status | Arquivos |
|------------|--------|----------|
| `active_depts.json` storage | ✅ IMPLEMENTADO | `active_depts.py` |
| Active depts loader | ✅ IMPLEMENTADO | `active_depts.py` |
| Admin API para activate/deactivate | ✅ IMPLEMENTADO | `admin_depts.py` |
| Eventos DEPT_ACTIVATED/DEACTIVATED | ✅ IMPLEMENTADO | `active_depts.py` |
| Validação de dept ativo no middleware | ✅ IMPLEMENTADO | `server.py` |
| Códigos de erro | ✅ IMPLEMENTADO | `errors.py` |

### O que NÃO existe (ainda)

| Componente | Status | Impacto |
|------------|--------|---------|
| Console UI para gerenciar depts | ⏳ Opcional | Operador pode usar API diretamente |

---

## 2. Gaps Identificados → RESOLVIDOS

### GAP-1: Storage de Active Depts ✅ FECHADO

**Status:** IMPLEMENTADO
**Arquivos criados:**
- `src/engine/core/active_depts.py` (~400 linhas)

**Funcionalidades implementadas:**
- `get_active_depts(institution_id) → List[str]`
- `set_active_depts()` via `activate_dept()` e `deactivate_dept()`
- `is_dept_active(institution_id, dept_id) → bool`
- `is_dept_installed(institution_id, dept_id) → bool`
- `activate_dept(institution_id, dept_id, actor_id, pin)`
- `deactivate_dept(institution_id, dept_id, actor_id, reason)`
- `get_installed_depts(institution_id) → List[str]`
- `get_depts_summary(institution_id) → Dict`
- Cache: `get_cached_active_depts()`, `invalidate_active_depts_cache()`

---

### GAP-2: Validação no Middleware ✅ FECHADO

**Status:** IMPLEMENTADO
**Arquivos modificados:**
- `src/engine/api/server.py:666-720`

**Mudanças:**
- Adicionado import de `DEPT_NOT_ACTIVE` e `is_dept_active`
- Adicionado import de `get_request_institution_id`
- Middleware agora verifica `is_dept_active(institution_id, dept)`
- Retorna 403 com código `DEPT_NOT_ACTIVE` se dept não estiver ativo

---

### GAP-3: Eventos no Ledger ✅ FECHADO

**Status:** IMPLEMENTADO
**Arquivos:**
- `src/engine/core/active_depts.py`

**Eventos implementados:**
- `DEPT_ACTIVATED`: Emitido em `activate_dept()`
- `DEPT_DEACTIVATED`: Emitido em `deactivate_dept()`

---

### GAP-4: Admin API Endpoints ✅ FECHADO

**Status:** IMPLEMENTADO
**Arquivos criados:**
- `src/engine/api/admin_depts.py` (~180 linhas)

**Endpoints implementados:**
- `GET /admin/institutions/{id}/depts` - Lista depts (installed/active/inactive)
- `POST /admin/institutions/{id}/depts/{dept_id}/activate`
- `POST /admin/institutions/{id}/depts/{dept_id}/deactivate`

---

### GAP-5: Códigos de Erro ✅ FECHADO

**Status:** IMPLEMENTADO
**Arquivos modificados:**
- `src/engine/core/errors.py`

**Códigos adicionados:**
```python
# Active Depts errors (Etapa 5.1)
DEPT_NOT_INSTALLED = "DEPT_NOT_INSTALLED"
DEPT_NOT_ACTIVE = "DEPT_NOT_ACTIVE"
DEPT_ALREADY_ACTIVE = "DEPT_ALREADY_ACTIVE"
DEPT_ALREADY_INACTIVE = "DEPT_ALREADY_INACTIVE"
CANNOT_DEACTIVATE_LAST_DEPT = "CANNOT_DEACTIVATE_LAST_DEPT"
ACTIVE_DEPTS_UNAVAILABLE = "ACTIVE_DEPTS_UNAVAILABLE"
```

---

### GAP-6: Fallback para Backward Compatibility ✅ FECHADO

**Status:** IMPLEMENTADO
**Arquivos:**
- `src/engine/core/active_depts.py`

**Comportamento:**
- Se `active_depts.json` não existe e bundle é multi-mode: retorna todos depts do bundle
- Se `active_depts.json` não existe e bundle é single-mode: retorna `[defaults.default_dept]`
- Primeira operação de activate/deactivate cria o arquivo automaticamente

---

### GAP-7: Console UI ⏳ PENDENTE (BAIXA PRIORIDADE)

**Status:** Não implementado
**Motivo:** Pode ser feito via API primeiro, Console UI é opcional

---

## 3. Testes Implementados

### Testes Unitários (`tests/test_active_depts.py`)

| Teste | Status |
|-------|--------|
| `TestActiveDeptEntry::test_to_dict` | ✅ PASS |
| `TestActiveDeptEntry::test_from_dict` | ✅ PASS |
| `TestActiveDeptsState::test_to_dict_sorted` | ✅ PASS |
| `TestGetActiveDepts::test_no_file_returns_bundle_depts` | ✅ PASS |
| `TestGetActiveDepts::test_file_exists_uses_file` | ✅ PASS |
| `TestGetActiveDepts::test_is_dept_active` | ✅ PASS |
| `TestActivateDept::test_activate_creates_file_on_first_call` | ✅ PASS |
| `TestActivateDept::test_activate_dept_not_installed` | ✅ PASS |
| `TestActivateDept::test_activate_already_active` | ✅ PASS |
| `TestDeactivateDept::test_deactivate_removes_from_file` | ✅ PASS |
| `TestDeactivateDept::test_cannot_deactivate_last_dept` | ✅ PASS |
| `TestDeactivateDept::test_deactivate_not_active` | ✅ PASS |
| `TestDeptsSummary::test_summary_with_file` | ✅ PASS |
| `TestCache::test_cache_invalidation` | ✅ PASS |
| `TestMultiInstitutionIsolation::test_two_institutions_isolated` | ✅ PASS |

**Total: 15 testes, 15 passing**

---

## 4. Definition of Done ✅ COMPLETO

Baseado em `spec.md`:

- [x] Spec descreve formato e local do "mapa de depts ativos"
  - ✅ Implementado: `active_depts.json` em `var/institutions/{id}/`

- [x] Spec descreve precedência (pinned vs current vs template)
  - ✅ Implementado: Middleware valida: ativo → instalado → processa

- [x] Spec descreve eventos no ledger
  - ✅ Implementado: `DEPT_ACTIVATED`, `DEPT_DEACTIVATED`

- [x] Spec descreve erros determinísticos
  - ✅ Implementado: 6 códigos de erro novos em `errors.py`

---

## 5. Arquivos Criados/Modificados

### Novos arquivos
- `src/engine/core/active_depts.py` (~400 linhas)
- `src/engine/api/admin_depts.py` (~180 linhas)
- `tests/test_active_depts.py` (~580 linhas)

### Arquivos modificados
- `src/engine/core/errors.py` (+6 linhas)
- `src/engine/api/server.py` (+15 linhas)

### Total
- **~1,180 linhas** de código novo
- **15 testes** unitários

---

## 6. Como Usar

### Listar depts de uma instituição
```bash
curl -H "X-Admin-Token: TOKEN" \
  http://localhost:8000/admin/institutions/{id}/depts
```

### Ativar um dept
```bash
curl -X POST -H "X-Admin-Token: TOKEN" \
  http://localhost:8000/admin/institutions/{id}/depts/finance/activate
```

### Desativar um dept
```bash
curl -X POST -H "X-Admin-Token: TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Maintenance"}' \
  http://localhost:8000/admin/institutions/{id}/depts/finance/deactivate
```

### Verificar se requisição para dept inativo é bloqueada
```bash
# Se 'hr' está inativo:
curl http://localhost:8000/d/hr/expenses
# Retorna: 403 DEPT_NOT_ACTIVE
```
