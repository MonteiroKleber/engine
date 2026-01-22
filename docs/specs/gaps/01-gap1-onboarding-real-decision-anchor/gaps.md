# GAP 1 — Âncora Real de Decisão — Análise de Gaps (v2)

**Status:** DRAFT
**Data:** 2026-01-21
**Baseado em:** spec.md v2 (contrato com requisitos atualizados)

---

## Mudanças na Spec v2

A spec foi atualizada com requisitos mais rigorosos para prova offline:

1. **Seeds DSL dentro do bundle** (não apenas no data root)
   - Single-dept: `source.idl` na raiz do bundle
   - Multi-dept: `departments/<dept_id>/source.idl` para cada dept

2. **Seeds no manifest** como contracts com `required=false`

3. **Hash multi-dept determinístico:**
   ```
   sha256("<dept_id>:<sha256(seed_bytes)>\n" concatenado, ordenado por dept_id)
   ```

4. **Novos campos no ledger:**
   - `source_idl_version` (ex: `idl.v1.2.2`)
   - `source_idl_by_dept` (mapa dept_id → sha256 do seed)

---

## 1. Mapeamento do Código Atual

### 1.1 Geração do Placeholder `source_idl_sha256`

**Arquivo:** [bundle_generator.py:100-110](src/engine/console/bundle_generator.py#L100-L110)
**Função:** `_update_contract_ledger()`

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
        ledger["source_idl_sha256"] = "0" * 64  # ← PROIBIDO pela spec v2
```

**Problema identificado:**
- Se o template não tiver `idl_hash`, gera `000...000` (64 zeros)
- Não existe nenhum arquivo DSL/IDL copiado para o bundle

---

### 1.2 Template Registry Atual

**Arquivo:** [templates_registry.py:14-57](src/engine/console/templates_registry.py#L14-L57)

```python
@dataclass
class BundleTemplate:
    id: str
    name: str
    description: str
    departments: List[str]
    path: str
    # ← FALTA: seed_dsl_paths: Dict[str, str]  # dept_id → path relativo ao seed
    # ← FALTA: seed_dsl_version: str  # ex: "idl.v1.2.2"

AVAILABLE_TEMPLATES: List[BundleTemplate] = [
    BundleTemplate(
        id="finance-pilot",
        name="Finance Pilot",
        departments=["finance"],
        path="bundles/finance-pilot",
        # ← FALTA: seed_dsl_paths={"finance": "seeds/finance.idl"}
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
- Não há campo para versão do IDL

---

### 1.3 Validação do Proof (source_idl_sha256)

**Arquivo:** [verify.py:360-376](src/engine/proof/verify.py#L360-L376)
**Função:** `verify_bundle_offline()` - Step 6

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
# ← NÃO VALIDA: vínculo com arquivo source.idl no bundle
# ← NÃO VALIDA: hash bate com arquivo existente
```

**Comportamento atual:**
- Exige presença de `source_idl_sha256`
- Valida formato (64-hex via `is_valid_sha256_hex()`)
- **NÃO valida** se hash corresponde ao `source.idl` dentro do bundle
- `000...000` passa a validação de formato (é hex válido)

**Nota:** A spec v2 diz "Não quebrar `verify_bundle_offline()`" — então o proof **não precisa** validar vínculo com arquivo. A garantia é que o hash é real no momento da geração.

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

## 2. Gaps Identificados (Spec v2)

### GAP-1A: Template Registry não declara seeds DSL

**Prioridade:** ALTA (core do modelo)
**Área:** Templates

**O que falta:**
- Campo `seed_dsl_paths: Dict[str, str]` no `BundleTemplate`
- Campo `seed_dsl_version: str` no `BundleTemplate`
- Mapeamento dept_id → path relativo do seed DSL (dentro do repo)

**Arquivos a modificar:**
```
src/engine/console/templates_registry.py
├── Adicionar campos seed_dsl_paths e seed_dsl_version ao BundleTemplate
├── Adicionar função get_seed_dsl_path(template_id, dept_id)
└── Atualizar AVAILABLE_TEMPLATES com seeds reais
```

**Estimativa:** ~25 linhas

---

### GAP-1B: Onboarding não inclui seed DSL dentro do bundle

**Prioridade:** ALTA (requisito novo da spec v2)
**Área:** Bundle Generator

**Requisito da spec v2:**
- Single-dept: adicionar `source.idl` na raiz do bundle gerado
- Multi-dept: adicionar `departments/<dept_id>/source.idl` para cada dept
- Esses arquivos devem entrar no `bundle.manifest.json` como contracts (`required=false`)

**O que falta:**
- Copiar seed DSL para dentro do bundle (path correto por tipo)
- Adicionar entry no manifest com `required: false`

**Arquivos a modificar:**
```
src/engine/console/bundle_generator.py
├── Adicionar função _copy_seed_dsl_to_bundle(template, bundle_path) -> Dict[str, str]
├── Chamar em generate_bundle_from_template() após copiar template
├── Atualizar manifest com entries de source.idl (required=false)
└── Criar estrutura departments/<dept>/ se multi-dept
```

**Path de destino dentro do bundle:**
```
# Single-dept (finance-pilot):
<bundle>/source.idl

# Multi-dept (multi-pilot):
<bundle>/departments/finance/source.idl
<bundle>/departments/support/source.idl
```

**Estimativa:** ~60 linhas

---

### GAP-1C: Onboarding não calcula hash real do seed (agregado para multi)

**Prioridade:** ALTA (core do modelo)
**Área:** Bundle Generator

**Requisito da spec v2:**
- Single-dept: `sha256(source.idl bytes)`
- Multi-dept: `sha256("<dept_id>:<sha256(seed_bytes)>\n" concatenado, ordenado por dept_id)`

**O que falta:**
- Implementar cálculo de hash agregado para multi-dept
- Setar `source_idl_sha256` com hash real
- Remover fallback `"0" * 64`
- Adicionar campos `source_idl_version` e `source_idl_by_dept` no ledger

**Arquivos a modificar:**
```
src/engine/console/bundle_generator.py
└── _update_contract_ledger():
    - Remover linhas 108-110 (fallback 0*64)
    - Receber parâmetro seed_hashes: Dict[str, str]
    - Calcular hash agregado se multi-dept
    - Setar ledger["source_idl_sha256"] = hash_real
    - Setar ledger["source_idl_version"] = template.seed_dsl_version
    - Setar ledger["source_idl_by_dept"] = seed_hashes (se multi)
```

**Exemplo de hash agregado (multi-dept):**
```python
# Entrada: {"finance": "abc123...", "support": "def456..."}
# Ordenado por dept_id → ["finance", "support"]
# String: "finance:abc123...\nsupport:def456...\n"
# Resultado: sha256(string.encode('utf-8')).hexdigest()
```

**Estimativa:** ~35 linhas

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
- OU atualizar templates para usar hash real do `examples/finance.idl`

**Localização recomendada:**
- `seeds/<dept>.idl` na raiz do repo (referenciado pelo template registry)

**Estimativa:** ~50 linhas de IDL por dept

---

### GAP-1E: Manifest não inclui source.idl como contract

**Prioridade:** ALTA (requisito novo da spec v2)
**Área:** Bundle Generator

**Requisito da spec v2:**
> "Esses arquivos devem entrar no `bundle.manifest.json` como contracts (required=false)."

**O que falta:**
- Após copiar seed para bundle, adicionar entry no manifest:
  ```json
  {
    "file": "source.idl",  // ou "departments/<dept>/source.idl"
    "sha256": "SHA256:<hash>",
    "required": false
  }
  ```

**Arquivos a modificar:**
```
src/engine/console/bundle_generator.py
└── _update_manifest_hashes() ou nova função
    - Adicionar entries de source.idl ao manifest.contracts[]
    - Recalcular hashes incluindo source.idl
```

**Estimativa:** ~20 linhas

---

### GAP-1F: Falha determinística se seed não existir

**Prioridade:** ALTA (requisito da spec v2)
**Área:** Bundle Generator

**Requisito da spec v2:**
> "Se seed não existir → falha determinística no onboarding."

**O que falta:**
- Validar existência de seed DSL antes de gerar bundle
- Retornar erro claro se seed não encontrado
- Novo código de erro: `SEED_DSL_NOT_FOUND`

**Arquivos a modificar:**
```
src/engine/console/bundle_generator.py
├── Validar seed_dsl_paths do template antes de copiar
└── Falhar com erro específico se arquivo não existir

src/engine/core/errors.py
└── Adicionar SEED_DSL_NOT_FOUND = "SEED_DSL_NOT_FOUND"
```

**Estimativa:** ~15 linhas

---

### GAP-1G: Testes automatizados

**Prioridade:** MÉDIA
**Área:** Testes

**O que falta:**
```
tests/test_onboarding_seed_dsl.py (NOVO)
├── test_single_dept_source_idl_in_bundle_root
├── test_multi_dept_source_idl_in_departments_dir
├── test_source_idl_in_manifest_required_false
├── test_source_idl_sha256_matches_single_dept_hash
├── test_source_idl_sha256_matches_multi_dept_aggregated_hash
├── test_source_idl_by_dept_in_ledger_for_multi
├── test_source_idl_version_in_ledger
├── test_no_placeholder_hash_generated
├── test_proof_passes_with_real_hash
└── test_fails_deterministically_if_seed_missing
```

**Estimativa:** ~150 linhas

---

## 3. Plano de Patch Mínimo (Spec v2)

### Fase 1: Preparar Seeds (pré-requisito)

| Item | Ação |
|------|------|
| 1 | Criar diretório `seeds/` na raiz do repo |
| 2 | Copiar/criar `seeds/finance.idl` |
| 3 | Criar `seeds/support.idl` (mínimo válido) |

### Fase 2: Template Registry

| Item | Arquivo | Mudança |
|------|---------|---------|
| 1 | `templates_registry.py` | Adicionar `seed_dsl_paths: Dict[str, str]` ao dataclass |
| 2 | `templates_registry.py` | Adicionar `seed_dsl_version: str` ao dataclass |
| 3 | `templates_registry.py` | Atualizar `AVAILABLE_TEMPLATES` com seeds |

### Fase 3: Bundle Generator

| Item | Arquivo | Mudança |
|------|---------|---------|
| 1 | `bundle_generator.py` | Criar `_copy_seed_dsl_to_bundle()` |
| 2 | `bundle_generator.py` | Atualizar manifest com entries source.idl (required=false) |
| 3 | `bundle_generator.py` | Implementar cálculo de hash agregado para multi-dept |
| 4 | `bundle_generator.py` | Adicionar campos `source_idl_version` e `source_idl_by_dept` no ledger |
| 5 | `bundle_generator.py` | Remover fallback `"0" * 64` |
| 6 | `bundle_generator.py` | Validar existência de seed e falhar se não existir |

### Fase 4: Error Codes

| Item | Arquivo | Mudança |
|------|---------|---------|
| 1 | `errors.py` | Adicionar `SEED_DSL_NOT_FOUND` |

### Fase 5: Testes

| Item | Arquivo | Conteúdo |
|------|---------|----------|
| 1 | `tests/test_onboarding_seed_dsl.py` | 10 testes cobrindo critérios de aceite |

---

## 4. Estrutura de Bundle Resultante

### Single-Dept (finance-pilot)

```
bundles/finance-pilot/
├── bundle.manifest.json       # inclui source.idl com required=false
├── contract_ledger.json       # source_idl_sha256 = hash real
├── source.idl                 # ← NOVO: seed DSL na raiz
└── contracts/
    └── *.json
```

**Ledger:**
```json
{
  "source_idl_sha256": "<sha256(source.idl bytes)>",
  "source_idl_version": "idl.v1.2.2"
}
```

### Multi-Dept (multi-pilot)

```
bundles/multi-pilot/
├── bundle.manifest.json       # inclui departments/*/source.idl
├── contract_ledger.json       # source_idl_sha256 = hash agregado
├── departments/
│   ├── finance/
│   │   └── source.idl         # ← NOVO: seed DSL do finance
│   └── support/
│       └── source.idl         # ← NOVO: seed DSL do support
└── contracts/
    └── *.json
```

**Ledger:**
```json
{
  "source_idl_sha256": "<sha256(aggregated string)>",
  "source_idl_version": "idl.v1.2.2",
  "source_idl_by_dept": {
    "finance": "<sha256(finance/source.idl)>",
    "support": "<sha256(support/source.idl)>"
  }
}
```

---

## 5. Critérios de Aceite (Spec v2)

| # | Critério | Como verificar |
|---|----------|----------------|
| 1 | Single-dept: `source.idl` presente na raiz do bundle | `ls <bundle>/source.idl` |
| 2 | Multi-dept: `departments/<dept>/source.idl` para cada dept | `ls <bundle>/departments/*/source.idl` |
| 3 | `source.idl` no manifest com `required=false` | Inspecionar `bundle.manifest.json` |
| 4 | `source_idl_sha256` é 64-hex real (não `000...`) | Inspecionar ledger |
| 5 | Hash single-dept = `sha256(source.idl)` | `sha256sum source.idl` vs ledger |
| 6 | Hash multi-dept = agregado determinístico | Calcular manualmente e comparar |
| 7 | `source_idl_by_dept` presente para multi | Inspecionar ledger |
| 8 | `engine.proof verify` PASS | `python -m engine.proof verify <bundle>` |
| 9 | Sem seed → falha determinística | Remover seed e tentar gerar |

---

## 6. Resumo de Arquivos

### A criar:
- `seeds/finance.idl` (seed para finance-pilot)
- `seeds/support.idl` (seed para multi-pilot)
- `tests/test_onboarding_seed_dsl.py`

### A modificar:
- `src/engine/console/templates_registry.py` (~25 linhas)
- `src/engine/console/bundle_generator.py` (~130 linhas)
- `src/engine/core/errors.py` (~2 linhas)

### Sem mudanças:
- `src/engine/proof/verify.py` (proof continua funcionando)
- Schema do manifest (campos extras são permitidos)

---

## 7. Estimativa Total

| Componente | Linhas |
|------------|--------|
| Templates Registry | ~25 |
| Bundle Generator | ~130 |
| Error Codes | ~2 |
| Seeds DSL | ~100 (conteúdo) |
| Testes | ~150 |
| **Total** | **~407 linhas** |
