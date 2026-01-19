# AXIOM MVP - Gaps Analysis

**Data:** 2026-01-18
**Tipo:** Análise de gaps para PROMPT 2.8.1
**Status:** IMPLEMENTADO (PROMPT 2.8.2)

---

## Resumo Executivo

O engine possui infraestrutura reutilizável para implementar governed mandates:

1. **EGE Proposals** - `ege_proposals.py` tem padrão de proposals append-only
2. **Institution Config** - `institution_config.py` mostra como armazenar state governado
3. **Mandates Engine** - `mandates.py` tem parsing e avaliação funcionais
4. **Ledger Events** - Padrão de emissão já existe

**Abordagem implementada: Opção A (Override Governado)**
- Menor complexidade que rebuild de bundle
- Reutiliza padrões existentes
- Permite hot-reload de mandatos

---

## O Que Existe

### 1. Mandates Loading (`loader/load_bundle.py`)

```python
# Linha 503-526: Single-mode
def _load_mandates_single_mode(bundle_path: Path) -> bool:
    mandates_path = bundle_path / "mandates.json"
    if mandates_path.exists():
        mandate_def = load_mandates_from_file(mandates_path)
        set_mandates(None, mandate_def)

# Linha 529-559: Multi-mode
def _load_mandates_multi_mode(bundle_path: Path, bundle_ctx: BundleContext) -> bool:
    for dept_id, dept_contracts in bundle_ctx.departments.items():
        mandates_path = dept_contracts.path / "mandates.json"
        if mandates_path.exists():
            mandate_def = load_mandates_from_file(mandates_path)
            set_mandates(dept_id, mandate_def)
```

### 2. Mandates Engine (`core/mandates.py`)

```python
# Linha 109-145: Global storage
_mandates: Dict[str, MandateDef] = {}
SINGLE_MODE_KEY = "_single"

def set_mandates(dept_id: Optional[str], mandate_def: Optional[MandateDef]) -> None
def get_mandates(dept_id: Optional[str]) -> Optional[MandateDef]

# Linha 223-353: Schema parsing
def parse_mandates_data(data: Dict[str, Any]) -> MandateDef

# Linha 569-704: Evaluation (MODIFICADO - aceita institution_id)
def evaluate_mandates(phase, dept_id, endpoint_sig, actor, payload, institution_id=None) -> MandateEvalResult
```

### 3. EGE Proposals Pattern (`core/ege_proposals.py`)

```python
@dataclass
class ProposalRecord:
    seq: int
    proposal_id: str
    operation: str  # "create" or "decide"
    status: str  # "OPEN" or "DECIDED"
    created_at: str
    # ... fields for hashes
    decision: Optional[str]
    reason: Optional[str]

def create_drift_resolution_proposal(institution_id, drift_state) -> Tuple[...]
def decide_proposal(institution_id, proposal_id, decision, reason, actor_id) -> Tuple[...]
def load_current_state(institution_id) -> Dict[str, ProposalState]
```

### 4. Institution Config Pattern (`core/institution_config.py`)

```python
# Linha 84-104: Config dataclass com state governado
@dataclass
class InstitutionConfig:
    schema_version: str
    updated_at: Optional[str]
    updated_by: Optional[str]
    # ... flags, limits, etc.

# Funções de persistência
def save_active_config(institution_id, config_dict, actor_id)
def get_effective_config(institution_id) -> InstitutionConfig
```

### 5. Ledger Event Pattern (`core/ledger.py`)

```python
def append(
    event_type: str,
    tenant_id: str,
    actor_id: str,
    actor_roles: List[str],
    case_id: str,
    step: str,
    payload: Dict[str, Any],
) -> Optional[LedgerEvent]
```

---

## Gaps - Status de Implementação

### GAP-1: Módulo `governed_mandates.py`

**Status:** ✅ IMPLEMENTADO

**Implementado em:** `src/engine/core/governed_mandates.py`

```python
@dataclass
class MandateProposalRecord:
    seq: int
    proposal_id: str
    operation_type: str  # "create" or "decide"
    status: str  # "OPEN" or "DECIDED"
    mandate_operation: str  # "create", "update", "revoke"
    mandate_id: str
    mandate_data: Optional[Dict[str, Any]]
    ...

def propose_mandate_change(institution_id, operation, mandate_id, mandate_data, reason, actor_id, dept_id=None)
def decide_mandate_proposal(institution_id, proposal_id, decision, reason, actor_id, dept_id=None)
def apply_mandate_change(institution_id, proposal_id, actor_id, dept_id=None)
def get_effective_mandates(institution_id, dept_id=None) -> Optional[MandateDef]
```

### GAP-2: Storage Files

**Status:** ✅ IMPLEMENTADO

**Estrutura criada:**
```
<institution_root>/governed_mandates/
├── mandate_proposals.jsonl   # Append-only proposals
├── governed_mandates.jsonl   # Append-only mandate history
└── governed_mandates_state.json  # Current effective mandates

<institution_root>/depts/<dept_id>/governed_mandates/
├── mandate_proposals.jsonl
├── governed_mandates.jsonl
└── governed_mandates_state.json
```

### GAP-3: Ledger Event Types

**Status:** ✅ IMPLEMENTADO

**Definido em:** `src/engine/core/governed_mandates.py`

```python
MANDATE_PROPOSED = "MANDATE_PROPOSED"
MANDATE_APPROVED = "MANDATE_APPROVED"
MANDATE_REJECTED = "MANDATE_REJECTED"
MANDATE_APPLIED = "MANDATE_APPLIED"
MANDATE_REVOKED = "MANDATE_REVOKED"
```

### GAP-4: API Endpoints

**Status:** ✅ IMPLEMENTADO

**Implementado em:** `src/engine/api/admin_mandates.py`

```
POST /admin/mandates/proposals
    → create_mandate_proposal_endpoint

POST /admin/mandates/proposals/{proposal_id}/decide
    → decide_proposal_endpoint

GET /admin/mandates/proposals
    → list_proposals_endpoint

GET /admin/mandates/governed
    → list_governed_mandates_endpoint

GET /admin/mandates/effective
    → list_effective_mandates_endpoint
```

Todos os endpoints requerem:
- `X-Admin-Key` header (ou `X-Admin-Token` para DEFAULT institution)
- `X-Institution-Id` header

### GAP-5: Integration Point

**Status:** ✅ IMPLEMENTADO

**Modificado:** `src/engine/core/mandates.py`

```python
def evaluate_mandates(
    phase: str,
    dept_id: Optional[str],
    endpoint_sig: str,
    actor: ActorContext,
    payload: Dict[str, Any],
    institution_id: Optional[str] = None,  # NOVO PARÂMETRO
) -> MandateEvalResult:
    # If institution_id is provided, use governed mandates (override + bundle)
    if institution_id:
        from engine.core.governed_mandates import get_effective_mandates
        mandate_def = get_effective_mandates(institution_id, dept_id)
    else:
        mandate_def = get_mandates(dept_id)
```

**APIs atualizadas para passar institution_id:**
- `src/engine/api/finance.py`
- `src/engine/api/support.py`
- `src/engine/api/approvals.py`

### GAP-6: CLI Commands

**Status:** ⏳ NÃO IMPLEMENTADO (escopo reduzido para MVP)

Os endpoints API são suficientes para operação. CLI pode ser adicionado posteriormente se necessário.

### GAP-7: Error Codes

**Status:** ✅ IMPLEMENTADO

**Adicionado em:** `src/engine/core/errors.py`

```python
# Governed Mandates errors (Etapa 2.8)
MANDATE_PROPOSAL_NOT_FOUND = "MANDATE_PROPOSAL_NOT_FOUND"
MANDATE_PROPOSAL_ALREADY_DECIDED = "MANDATE_PROPOSAL_ALREADY_DECIDED"
MANDATE_PROPOSAL_INVALID = "MANDATE_PROPOSAL_INVALID"
MANDATE_NOT_FOUND_FOR_UPDATE = "MANDATE_NOT_FOUND_FOR_UPDATE"
MANDATE_ALREADY_EXISTS = "MANDATE_ALREADY_EXISTS"
GOVERNED_MANDATES_UNAVAILABLE = "GOVERNED_MANDATES_UNAVAILABLE"
```

---

## Matriz de Gaps - Status Final

| Gap | Descrição | Status |
|-----|-----------|--------|
| GAP-1 | Módulo governed_mandates | ✅ IMPLEMENTADO |
| GAP-2 | Storage files | ✅ IMPLEMENTADO |
| GAP-3 | Ledger event types | ✅ IMPLEMENTADO |
| GAP-4 | API endpoints | ✅ IMPLEMENTADO |
| GAP-5 | Integration point | ✅ IMPLEMENTADO |
| GAP-6 | CLI commands | ⏳ ADIADO (MVP completo sem CLI) |
| GAP-7 | Error codes | ✅ IMPLEMENTADO |

---

## Decisões Implementadas

| ID | Questão | Decisão |
|----|---------|---------|
| D-1 | Override vs Rebuild? | **A) Override governado** |
| D-2 | Scope inicial? | **A) Mandates only** |
| D-3 | Hot reload? | **A) Imediato** (cache invalidation) |
| D-4 | Auto-approve? | **A) Sempre requer aprovação** |
| D-5 | Multi-dept support? | **A) Desde o início** |

---

## Arquivos Criados/Modificados

### Criados

```
src/engine/core/governed_mandates.py     # Core logic (750+ lines)
src/engine/api/admin_mandates.py         # API endpoints (340+ lines)
tests/test_governed_mandates.py          # 25 tests
```

### Modificados

```
src/engine/core/errors.py                # +6 error codes
src/engine/api/server.py                 # +router registration
src/engine/core/mandates.py              # +institution_id parameter
src/engine/api/finance.py                # +institution_id in evaluate_mandates
src/engine/api/support.py                # +institution_id in evaluate_mandates
src/engine/api/approvals.py              # +institution_id in evaluate_mandates
```

---

## Notas de Design

### Por que Override Governado (Opção A)?

1. **Simplicidade**: Não requer rebuild de bundle
2. **Agilidade**: Mudança aplicada em segundos, não minutos
3. **Separação de concerns**: Bundle = contrato técnico, Governed = política
4. **Consistência**: Mesmo padrão de institution_config
5. **Rollback**: Simples - apenas remover override

### Por que não Rebuild (Opção B)?

1. **Lento**: Requer pipeline de build + deploy
2. **Acoplado**: Mistura governança com release técnica
3. **Complexo**: Precisa versionar bundles por mudança de mandato
4. **Overhead**: Cada mudança de mandato = novo bundle

### Integração com EGE

O governed mandates segue o mesmo padrão do EGE:
- Proposals append-only
- State folding
- Ledger events
- File locking per institution

Diferença:
- EGE governa **hashes de bundle** (drift)
- Governed Mandates governa **mandatos** (políticas de acesso)

### Precedência

```
Runtime Request
     ↓
┌─────────────────────┐
│ Governed Mandates   │  ← Prioridade
│ (institution state) │
└─────────────────────┘
     ↓ (merge por mandate_id)
┌─────────────────────┐
│ Bundle Mandates     │  ← Default
│ (mandates.json)     │
└─────────────────────┘
     ↓
evaluate_mandates()
     ↓
Allow / Deny
```

---

## Definition of Done (MVP)

- [x] Mandates podem ser propostos via API
- [x] Mandates podem ser aprovados/rejeitados via API
- [x] Mandates aprovados são aplicados e afetam runtime
- [x] Mandates podem ser revogados via API
- [x] Todos os eventos são registrados no ledger
- [x] Testes cobrem fluxo completo (25 tests)
- [ ] CLI funcional para operação offline (adiado)

---

## Testes Implementados

```
tests/test_governed_mandates.py (25 tests):

TestProposalWorkflow:
  - test_propose_create_mandate
  - test_propose_invalid_operation
  - test_propose_create_without_data
  - test_propose_invalid_schema
  - test_decide_approve
  - test_decide_reject
  - test_decide_already_decided
  - test_decide_not_found

TestMandateNotAppliedUntilApproved:
  - test_proposed_mandate_does_not_affect_runtime
  - test_approved_mandate_affects_runtime

TestRevocation:
  - test_revoke_governed_mandate

TestIsolation:
  - test_institution_isolation
  - test_department_isolation

TestLedgerEvents:
  - test_propose_emits_mandate_proposed
  - test_approve_emits_mandate_approved_and_applied
  - test_reject_emits_mandate_rejected
  - test_revoke_emits_mandate_revoked

TestBundleMandatesOverride:
  - test_governed_overrides_bundle

TestListFunctions:
  - test_list_proposals
  - test_list_proposals_filter_status
  - test_list_governed_mandates

TestUpdateOperation:
  - test_update_existing_mandate

TestErrorCases:
  - test_create_duplicate_mandate
  - test_update_nonexistent_mandate
  - test_revoke_nonexistent_mandate
```
