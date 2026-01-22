# GAP 1 — Âncora Real de Decisão — Análise de Gaps

**Status:** DRAFT
**Data:** 2026-01-21
**Baseado em:** spec.md (contrato), mapeamento do código atual

---

## 1. Mapeamento do Código Atual

### 1.1 Geração do Placeholder `source_idl_sha256`

**Arquivo:** `src/engine/console/bundle_generator.py`
**Função:** `_update_contract_ledger()`
**Linhas:** 100-110

```python
# Ensure source_idl_sha256 exists (proof verification requires it)
# Some templates use idl_hash with SHA256: prefix
if "source_idl_sha256" not in ledger:
    idl_hash = ledger.get("idl_hash", "")
    if idl_hash.upper().startswith("SHA256:"):
        ledger["source_idl_sha256"] = idl_hash[7:]  # Remove prefix
    elif idl_hash:
        ledger["source_idl_sha256"] = idl_hash
    else:
        # Generate placeholder if missing (64-char hex)
        ledger["source_idl_sha256"] = "0" * 64  # ← PROBLEMA: placeholder inválido
```

**Problema identificado:**
- Se o template não tiver `idl_hash`, gera `000...000` (64 zeros)
- Não existe nenhum arquivo DSL/IDL referenciado ou copiado

---

### 1.2 Template Registry Atual

**Arquivo:** `src/engine/console/templates_registry.py`
**Linhas:** 14-57

```python
@dataclass
class BundleTemplate:
    id: str
    name: str
    description: str
    departments: List[str]
    path: str
    # ← FALTA: seed_dsl_paths: Dict[str, str]  # dept_id → path relativo ao seed

AVAILABLE_TEMPLATES: List[BundleTemplate] = [
    BundleTemplate(
        id="finance-pilot",
        name="Finance Pilot",
        departments=["finance"],
        path="bundles/finance-pilot",
        # ← FALTA: seed_dsl_paths={"finance": "examples/finance.idl"}
    ),
    BundleTemplate(
        id="multi-pilot",
        name="Multi-Department Pilot",
        departments=["finance", "support"],
        path="bundles/multi-pilot",
        # ← FALTA: seed_dsl_paths={"finance": "...", "support": "..."}
    ),
]
```

**Problema identificado:**
- `BundleTemplate` não declara seeds DSL por departamento
- Não há mapeamento dept → arquivo DSL

---

### 1.3 Validação do Proof (source_idl_sha256)

**Arquivo:** `src/engine/proof/verify.py`
**Função:** `verify_bundle_offline()`
**Linhas:** 360-376 (Step 6)

```python
# ================================================================
# Step 6: Validate source_idl_sha256
# ================================================================
source_idl_sha256 = ledger.get("source_idl_sha256")

if not source_idl_sha256:
    return _fail(
        PROOF_SOURCE_IDL_MISSING,
        "source_idl_sha256 not found in contract_ledger.json",
    )

if not is_valid_sha256_hex(source_idl_sha256):
    return _fail(
        PROOF_SOURCE_IDL_INVALID_FORMAT,
        f"Invalid source_idl_sha256 format: {source_idl_sha256}",
    )
# ← NÃO VALIDA: vínculo com arquivo DSL real
# ← NÃO VALIDA: hash bate com arquivo existente
```

**Comportamento atual:**
- Exige presença de `source_idl_sha256`
- Valida formato (64-hex via `is_valid_sha256_hex()`)
- **NÃO valida** se hash corresponde a um arquivo DSL real
- `000...000` passa a validação de formato (é hex válido)

---

### 1.4 Estado dos Templates Atuais

| Template | Tem `idl_hash` no ledger? | Tem arquivo DSL? |
|----------|---------------------------|------------------|
| `finance-pilot` | ✅ SIM: `SHA256:abe451b...` | ❌ NÃO dentro do bundle |
| `multi-pilot` | ? (precisa verificar) | ❌ NÃO dentro do bundle |

**Arquivo DSL existente no repo:**
- `examples/finance.idl` (5193 bytes)
- SHA256: `9ef76983753ab85c6b6435ce8583279bd2738f55137e2474d682d976d9a3274c`
- **NOTA:** Hash não bate com `idl_hash` do finance-pilot (`abe451b...`)

---

## 2. Gaps Identificados

### GAP-1A: Template Registry não declara seeds DSL

**Prioridade:** ALTA (core do modelo)
**Área:** Templates

**O que falta:**
- Campo `seed_dsl_paths: Dict[str, str]` no `BundleTemplate`
- Mapeamento dept_id → path relativo do seed DSL

**Arquivos a modificar:**
```
src/engine/console/templates_registry.py
├── Adicionar campo seed_dsl_paths ao BundleTemplate
└── Atualizar AVAILABLE_TEMPLATES com seeds reais
```

**Estimativa:** ~20 linhas

---

### GAP-1B: Onboarding não copia seed DSL

**Prioridade:** ALTA (core do modelo)
**Área:** Bundle Generator

**O que falta:**
- Copiar seed DSL para `institutions/<id>/depts/<dept>/idl/seed.idl`
- Criar diretório `depts/<dept>/idl/` se não existir

**Arquivos a modificar:**
```
src/engine/console/bundle_generator.py
├── Adicionar função _copy_seed_dsls()
├── Chamar em generate_bundle_from_template() após copiar template
└── Criar estrutura de diretórios por dept
```

**Path canônico de destino:**
```
ENGINE_DATA_ROOT/institutions/<institution_id>/depts/<dept_id>/idl/seed.idl
```

**Estimativa:** ~40 linhas

---

### GAP-1C: Onboarding não calcula hash real do seed

**Prioridade:** ALTA (core do modelo)
**Área:** Bundle Generator

**O que falta:**
- Calcular `SHA256(UTF-8 bytes)` do seed DSL copiado
- Setar `source_idl_sha256` com hash real
- Remover fallback `"0" * 64`

**Arquivos a modificar:**
```
src/engine/console/bundle_generator.py
└── _update_contract_ledger():
    - Remover linhas 108-110 (fallback 0*64)
    - Receber parâmetro seed_hash
    - Setar ledger["source_idl_sha256"] = seed_hash
```

**Estimativa:** ~15 linhas

---

### GAP-1D: Seeds DSL não existem para todos os templates

**Prioridade:** ALTA (pré-requisito)
**Área:** Conteúdo/Assets

**Estado atual:**
- `examples/finance.idl` existe (5193 bytes)
- **Não existe** seed para `support` (multi-pilot)
- Hash do `finance.idl` atual não bate com `idl_hash` do template

**O que falta:**
- Criar `examples/support.idl` (ou usar placeholder mínimo)
- OU atualizar `finance.idl` para gerar hash que bate com template
- Decidir: seed no repo (`examples/`) ou dentro do bundle (`bundles/<id>/seed/`)

**Opções de localização:**
1. **`examples/<dept>.idl`** - Seeds compartilhados por templates
2. **`bundles/<template>/seeds/<dept>.idl`** - Seeds por template

**Recomendação:** Opção 1 (seeds em `examples/`) + mapeamento no registry

**Estimativa:** ~50 linhas de IDL por dept

---

### GAP-1E: Testes automatizados

**Prioridade:** MÉDIA
**Área:** Testes

**O que falta:**
```
tests/test_onboarding_seed_dsl.py (NOVO)
├── test_seed_dsl_copied_to_institution
├── test_source_idl_sha256_matches_seed_hash
├── test_proof_passes_with_real_hash
├── test_no_placeholder_hash_generated
└── test_multi_dept_each_has_own_seed
```

**Estimativa:** ~100 linhas

---

## 3. Plano de Patch Mínimo

### Fase 1: Preparar Seeds (pré-requisito)

| Item | Ação |
|------|------|
| 1 | Verificar/atualizar `examples/finance.idl` |
| 2 | Criar `examples/support.idl` (mínimo válido) |
| 3 | Documentar formato esperado do seed |

### Fase 2: Template Registry

| Item | Arquivo | Mudança |
|------|---------|---------|
| 1 | `templates_registry.py` | Adicionar `seed_dsl_paths: Dict[str, str]` ao dataclass |
| 2 | `templates_registry.py` | Adicionar função `get_seed_dsl_path(template_id, dept_id)` |
| 3 | `templates_registry.py` | Atualizar `AVAILABLE_TEMPLATES` com seeds |

### Fase 3: Bundle Generator

| Item | Arquivo | Mudança |
|------|---------|---------|
| 1 | `bundle_generator.py` | Criar `_copy_seed_dsl(src, dst) -> str` (retorna hash) |
| 2 | `bundle_generator.py` | Chamar copy para cada dept em `generate_bundle_from_template()` |
| 3 | `bundle_generator.py` | Passar hash para `_update_contract_ledger()` |
| 4 | `bundle_generator.py` | Remover fallback `"0" * 64` |

### Fase 4: Testes

| Item | Arquivo | Conteúdo |
|------|---------|----------|
| 1 | `tests/test_onboarding_seed_dsl.py` | 5 testes cobrindo critérios de aceite |

---

## 4. Validações Necessárias

### Prova Offline (sem mudanças)

A spec diz: "Não quebrar `engine.proof.verify_bundle_offline()` nem a ABI do manifest."

O proof atual **continua funcionando** porque:
1. Apenas valida formato de `source_idl_sha256` (64-hex)
2. Não valida vínculo com arquivo
3. Hash real passa a mesma validação que placeholder passava

### ABI do Manifest (sem mudanças)

O `contract_ledger.json` mantém estrutura:
```json
{
  "source_idl_sha256": "<64-hex-real>"  // antes era "0...0" ou hash do template
}
```

Nenhum campo novo obrigatório, apenas valor diferente.

---

## 5. Critérios de Aceite (do spec.md)

| # | Critério | Como verificar |
|---|----------|----------------|
| 1 | `source_idl_sha256` não é `000...` | Gerar bundle e inspecionar ledger |
| 2 | Seed DSL existe em `institutions/<id>/depts/<dept>/idl/seed.idl` | Verificar path após onboarding |
| 3 | Hash no ledger = SHA256(seed) | `sha256sum seed.idl` vs ledger |
| 4 | `engine.proof verify` PASS | Executar proof no bundle gerado |
| 5 | Testes automatizados | `pytest tests/test_onboarding_seed_dsl.py` |

---

## 6. Resumo de Arquivos

### A criar:
- `examples/support.idl` (seed para multi-pilot)
- `tests/test_onboarding_seed_dsl.py`

### A modificar:
- `src/engine/console/templates_registry.py` (~20 linhas)
- `src/engine/console/bundle_generator.py` (~55 linhas)

### Sem mudanças:
- `src/engine/proof/verify.py` (proof continua funcionando)
- `bundles/*/bundle.manifest.json` (ABI mantida)

---

## 7. Estimativa Total

| Componente | Linhas |
|------------|--------|
| Templates Registry | ~20 |
| Bundle Generator | ~55 |
| Seeds DSL | ~100 (conteúdo) |
| Testes | ~100 |
| **Total** | **~275 linhas** |
