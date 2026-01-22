# 04-2 Onboarding + Templates - Gaps Analysis

**Status:** IMPLEMENTADO
**Data:** 2026-01-19

## Resumo

Onboarding de novas instituições com templates implementado via console UI.

## Estado Final

### 1. Criação/Listagem de Instituições

**APIs Admin Existentes** (`api/admin_institutions.py`)

| Método | Rota | Status | Descrição |
|--------|------|--------|-----------|
| POST | `/admin/institutions` | ✅ Existe | Cria instituição (slug, display_name) |
| GET | `/admin/institutions` | ✅ Existe | Lista instituições (paginado) |
| GET | `/admin/institutions/{id}` | ✅ Existe | Busca por UUID |
| GET | `/admin/institutions/by-slug/{slug}` | ✅ Existe | Busca por slug |

**Console Onboarding** (`console/routes.py`)
- `POST /console/onboarding/create-institution` - Cria instituição via wizard

### 2. Bundles por Instituição

**Estrutura de Diretórios**
```
bundles/                          # Templates globais
├── finance-pilot/                # Template single-dept
│   ├── bundle.manifest.json
│   ├── rbac.json, approvals.json, ...
│   └── contract_ledger.json
└── multi-pilot/                  # Template multi-dept
    ├── bundle.manifest.json
    ├── contracts.json
    └── departments/
        ├── finance/
        └── support/

var/institutions/{uuid}/          # Per-institution data
├── institution.json              # Metadata
├── config/
│   ├── ACTIVE.json               # Config atual
│   └── history.jsonl             # Histórico
└── bundles/                      # Bundles gerados
    ├── finance-pilot/            # Bundle copiado de template
    └── CURRENT -> finance-pilot  # Symlink para release ativo
```

### 3. Template Registry

**Módulo:** `console/templates_registry.py`

```python
AVAILABLE_TEMPLATES = [
    BundleTemplate(
        id="finance-pilot",
        name="Finance Pilot",
        description="Single-department bundle for finance operations...",
        departments=["finance"],
        path="bundles/finance-pilot",
    ),
    BundleTemplate(
        id="multi-pilot",
        name="Multi-Department Pilot",
        description="Multi-department bundle with finance and support...",
        departments=["finance", "support"],
        path="bundles/multi-pilot",
    ),
]
```

### 4. Bundle Generation

**Módulo:** `console/bundle_generator.py`

```python
from engine.console.bundle_generator import generate_bundle_from_template

result = generate_bundle_from_template(
    institution_id="...",
    template_id="finance-pilot",
)

if result.success:
    print(f"Bundle: {result.bundle_path}")
    print(f"Proof passed: {result.proof_result.passed}")
```

**Processo:**
1. Valida instituição e template existem
2. Copia template para `var/institutions/{uuid}/bundles/{template_id}/`
3. Remove `contract_ledger.json` do manifest (evita dependência circular)
4. Recalcula hashes dos contratos no manifest
5. Atualiza `contract_ledger.json` com:
   - `manifest_hash`: hash do manifest atualizado
   - `source_idl_sha256`: copiado de `idl_hash` (com normalização)
   - `created_at`: timestamp atual
   - `audit_trail`: evento de geração
6. Executa `verify_bundle_offline()` (proof obrigatório)
7. Se PASS: cria symlink `CURRENT -> {template_id}`
8. Se FAIL: bundle permanece mas symlink não é criado

### 5. Console Routes

| Rota | Método | Descrição |
|------|--------|-----------|
| `/console/onboarding` | GET | Wizard principal (4 steps) |
| `/console/onboarding/create-institution` | POST | Cria instituição |
| `/console/onboarding/generate-bundle` | POST | Gera bundle de template |
| `/console/onboarding/proof` | GET | Redirect para step 4 |

### 6. UI Wizard (onboarding.html)

**Step 1:** Create/Select Institution
- Lista instituições existentes
- Form para criar nova instituição (slug, display_name)

**Step 2:** Choose Template
- Radio buttons para selecionar template
- Descrição e departamentos de cada template

**Step 3:** (Processing - implícito)

**Step 4:** Proof Result
- Success banner se proof passou
- Error banner se proof falhou
- Detalhes do bundle verificado
- Link para console principal

---

## Gaps Fechados

### GAP-1: Rotas de onboarding no console ✅

**Implementado em:** `console/routes.py` (linhas 2910-3110)

### GAP-2: Template registry ✅

**Implementado em:** `console/templates_registry.py`

### GAP-3: Função para copiar template ✅

**Implementado em:** `console/bundle_generator.py`

### GAP-4: Templates HTML para wizard ✅

**Implementado em:** `console/templates/onboarding.html`

### GAP-5: Integração do proof com geração ✅

**Implementado em:** `generate_bundle_from_template()` executa proof automaticamente.

---

## Correções Adicionais

### Fix: Circular Hash Dependency

O manifest original incluía `contract_ledger.json` na lista de contratos, criando dependência circular:
- Manifest hasheava ledger
- Ledger armazenava manifest_hash
- Impossível manter ambos consistentes

**Solução:** `_update_manifest_hashes()` remove `contract_ledger.json` do manifest.
O ledger é verificado separadamente pelo proof system.

### Fix: normalize_hash for ledger_manifest_hash

A função `verify_bundle_offline()` não normalizava o `manifest_hash` do ledger antes de validar formato.

**Corrigido em:** `proof/verify.py` linha 300 - adicionado `normalize_hash()` call.

### Fix: source_idl_sha256 field

Templates usam `idl_hash` com prefixo `SHA256:`, mas proof espera `source_idl_sha256` sem prefixo.

**Solução:** `_update_contract_ledger()` copia e normaliza de `idl_hash` para `source_idl_sha256`.

---

## Testes

**Total:** 20 testes de onboarding (166 testes console total)

| Classe | Testes |
|--------|--------|
| TestOnboardingAuth | 2 |
| TestOnboardingWizardSteps | 2 |
| TestOnboardingCreateInstitution | 3 |
| TestOnboardingGenerateBundle | 3 |
| TestOnboardingProofResult | 1 |
| TestOnboardingProofRedirect | 1 |
| TestOnboardingNavLink | 1 |
| TestOnboardingTemplateRegistry | 3 |
| TestOnboardingBundleGenerator | 3 |
| TestOnboardingMutableRoutes | 1 |

---

## Definition of Done (da spec.md)

- [x] Um usuário consegue, via browser, criar uma instituição
- [x] Escolher template (finance, support/multi)
- [x] Gerar bundle piloto
- [x] Ver proof PASS

---

## Arquivos Modificados/Criados

| Arquivo | Ação |
|---------|------|
| `console/templates_registry.py` | Criado |
| `console/bundle_generator.py` | Criado |
| `console/routes.py` | Adicionado rotas onboarding |
| `console/templates/onboarding.html` | Criado |
| `console/templates/base.html` | Adicionado link Onboarding no nav |
| `core/errors.py` | Adicionado códigos de erro |
| `proof/verify.py` | Corrigido normalize_hash |
| `tests/test_console.py` | Adicionado 20 testes |
