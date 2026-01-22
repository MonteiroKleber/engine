# 04-4 Governança UI (Policies + Autonomy) - Gaps Analysis

**Status:** IMPLEMENTAÇÃO COMPLETA
**Data:** 2026-01-20
**Revisado:** Implementação finalizada com testes e documentação

---

## Resumo

Governança operacional para **policies** e **autonomy** seguindo o padrão de governed_mandates:
- Proposal workflow: propose → decide → apply
- Diff antes/depois
- Trilha no ledger
- Override governado (instituição) > bundle

---

## Estado Final (IMPLEMENTADO)

### 1. Core Modules

#### `src/engine/core/governed_policies.py` (NEW)

**Status:** ✅ IMPLEMENTADO

**Estruturas de dados:**
```python
@dataclass
class PolicyProposalRecord:
    seq: int
    proposal_id: str
    policy_operation: str  # "create", "update", "revoke"
    policy_id: str
    dept_id: Optional[str]
    policy_data: Optional[Dict[str, Any]]
    reason: str
    created_by: str
    created_at: str
    decision: Optional[str]  # "approve" or "reject"
    decision_reason: Optional[str]
    decided_at: Optional[str]
    decided_by: Optional[str]

@dataclass
class PolicyProposalState:
    proposal_id: str
    status: str  # "OPEN" or "DECIDED"
    created_at: str
    policy_operation: str
    dept_id: Optional[str]
    policy_id: str
    policy_data: Optional[Dict[str, Any]]
    reason: str
    created_by: str
    decision: Optional[str]
    decision_reason: Optional[str]
    decided_at: Optional[str]
    decided_by: Optional[str]

@dataclass
class GovernedPolicyRecord:
    seq: int
    policy_id: str
    dept_id: Optional[str]
    operation: str  # "create", "update", "revoke"
    policy_data: Optional[Dict[str, Any]]
    applied_at: str
    applied_by: str
    proposal_id: str

@dataclass
class GovernedPoliciesState:
    schema_version: str
    updated_at: str
    policies: Dict[str, Dict[str, Any]]
```

**Funções principais:**
| Função | Status | Descrição |
|--------|--------|-----------|
| `propose_policy_change()` | ✅ | Cria proposal (emite POLICY_PROPOSED) |
| `decide_policy_proposal()` | ✅ | Aprova/rejeita (emite POLICY_APPROVED/REJECTED) |
| `apply_policy_change()` | ✅ | Aplica alteração (emite POLICY_APPLIED/REVOKED) |
| `get_effective_policies()` | ✅ | Retorna bundle + governed merged |
| `list_policy_proposals()` | ✅ | Lista proposals com filtros |
| `list_governed_policies()` | ✅ | Lista policies governadas |
| `get_policy_proposal()` | ✅ | Busca proposal específica |

**Eventos de Ledger:**
- ✅ `POLICY_PROPOSED`
- ✅ `POLICY_APPROVED`
- ✅ `POLICY_REJECTED`
- ✅ `POLICY_APPLIED`
- ✅ `POLICY_REVOKED`

---

#### `src/engine/core/governed_autonomy.py` (NEW)

**Status:** ✅ IMPLEMENTADO

**Estruturas de dados:**
```python
@dataclass
class AutonomyProposalRecord:
    seq: int
    proposal_id: str
    autonomy_operation: str  # "update_level", "create_rule", "update_rule", "revoke_rule"
    dept_id: Optional[str]
    rule_id: Optional[str]
    autonomy_data: Optional[Dict[str, Any]]
    reason: str
    created_by: str
    created_at: str
    decision: Optional[str]
    decision_reason: Optional[str]
    decided_at: Optional[str]
    decided_by: Optional[str]

@dataclass
class AutonomyProposalState:
    # (similar structure)

@dataclass
class GovernedAutonomyRecord:
    seq: int
    operation: str
    dept_id: Optional[str]
    rule_id: Optional[str]
    autonomy_data: Optional[Dict[str, Any]]
    applied_at: str
    applied_by: str
    proposal_id: str

@dataclass
class GovernedAutonomyState:
    schema_version: str
    updated_at: str
    current_level: Optional[int]
    rules: Dict[str, Dict[str, Any]]
```

**Funções principais:**
| Função | Status | Descrição |
|--------|--------|-----------|
| `propose_autonomy_change()` | ✅ | Cria proposal |
| `decide_autonomy_proposal()` | ✅ | Aprova/rejeita |
| `apply_autonomy_change()` | ✅ | Aplica alteração |
| `get_effective_autonomy()` | ✅ | Retorna bundle + governed merged |
| `list_autonomy_proposals()` | ✅ | Lista proposals |
| `list_governed_autonomy()` | ✅ | Lista autonomy governada |
| `get_autonomy_proposal()` | ✅ | Busca proposal específica |

**Eventos de Ledger:**
- ✅ `AUTONOMY_PROPOSED`
- ✅ `AUTONOMY_GOV_APPROVED`
- ✅ `AUTONOMY_GOV_REJECTED`
- ✅ `AUTONOMY_GOV_APPLIED`
- ✅ `AUTONOMY_GOV_REVOKED`

---

### 2. Runtime Integration

**Status:** ✅ IMPLEMENTADO

#### `src/engine/core/policy.py`
```python
def evaluate_policies(phase, dept_id, endpoint_sig, payload, institution_id=None):
    # Se institution_id fornecido, buscar governed policies
    if institution_id:
        from engine.core.governed_policies import get_effective_policies
        policy_def = get_effective_policies(institution_id, dept_id)
    else:
        policy_def = get_policies(dept_id)
    # ... resto da avaliação
```

#### `src/engine/core/autonomy.py`
```python
def evaluate_autonomy(phase, dept_id, endpoint_sig, institution_id=None):
    # Se institution_id fornecido, buscar governed autonomy
    if institution_id:
        from engine.core.governed_autonomy import get_effective_autonomy
        autonomy_def = get_effective_autonomy(institution_id, dept_id)
    else:
        autonomy_def = get_autonomy_for_dept(dept_id)
    # ... resto da avaliação
```

---

### 3. Admin API Endpoints

**Status:** ✅ IMPLEMENTADO

#### `src/engine/api/admin_policies.py` (NEW)

| Endpoint | Método | Status |
|----------|--------|--------|
| `/admin/policies/proposals` | POST | ✅ |
| `/admin/policies/proposals` | GET | ✅ |
| `/admin/policies/proposals/{id}` | GET | ✅ |
| `/admin/policies/proposals/{id}/decide` | POST | ✅ |
| `/admin/policies/governed` | GET | ✅ |
| `/admin/policies/effective` | GET | ✅ |

#### `src/engine/api/admin_autonomy.py` (NEW)

| Endpoint | Método | Status |
|----------|--------|--------|
| `/admin/autonomy/proposals` | POST | ✅ |
| `/admin/autonomy/proposals` | GET | ✅ |
| `/admin/autonomy/proposals/{id}` | GET | ✅ |
| `/admin/autonomy/proposals/{id}/decide` | POST | ✅ |
| `/admin/autonomy/governed` | GET | ✅ |
| `/admin/autonomy/effective` | GET | ✅ |

---

### 4. Console UI

**Status:** ✅ IMPLEMENTADO

#### Routes (`src/engine/console/routes.py`)

| Rota | Método | Status |
|------|--------|--------|
| `/policies` | GET | ✅ |
| `/policies/proposals` | GET | ✅ |
| `/policies/proposals/new` | GET/POST | ✅ |
| `/policies/proposals/{id}` | GET | ✅ |
| `/policies/proposals/{id}/decide` | POST | ✅ |
| `/autonomy` | GET | ✅ |
| `/autonomy/proposals` | GET | ✅ |
| `/autonomy/proposals/new` | GET/POST | ✅ |
| `/autonomy/proposals/{id}` | GET | ✅ |
| `/autonomy/proposals/{id}/decide` | POST | ✅ |

#### Templates (`src/engine/console/templates/`)

| Template | Status |
|----------|--------|
| `policies.html` | ✅ |
| `policies_proposals.html` | ✅ |
| `policies_proposal_new.html` | ✅ |
| `policies_proposal_detail.html` | ✅ |
| `autonomy.html` | ✅ |
| `autonomy_proposals.html` | ✅ |
| `autonomy_proposal_new.html` | ✅ |
| `autonomy_proposal_detail.html` | ✅ |

---

### 5. Storage por Instituição

**Status:** ✅ IMPLEMENTADO

```
var/institutions/{uuid}/governed_policies/
├── policy_proposals.jsonl        # Append-only proposals
├── governed_policies.jsonl       # Append-only applied changes
└── governed_policies_state.json  # Estado efetivo atual

var/institutions/{uuid}/governed_autonomy/
├── autonomy_proposals.jsonl      # Append-only proposals
├── governed_autonomy.jsonl       # Append-only applied changes
└── governed_autonomy_state.json  # Estado efetivo atual

var/institutions/{uuid}/depts/{dept_id}/governed_policies/
└── (mesma estrutura)

var/institutions/{uuid}/depts/{dept_id}/governed_autonomy/
└── (mesma estrutura)
```

---

### 6. Testes

**Status:** ✅ IMPLEMENTADO

#### `tests/test_governed_policies.py` (NEW)

| Classe de Testes | Status |
|------------------|--------|
| `TestProposalWorkflow` | ✅ |
| `TestPolicyNotAppliedUntilApproved` | ✅ |
| `TestRevocation` | ✅ |
| `TestIsolation` | ✅ |
| `TestLedgerEvents` | ✅ |
| `TestBundlePoliciesOverride` | ✅ |
| `TestListFunctions` | ✅ |
| `TestUpdateOperation` | ✅ |
| `TestErrorCases` | ✅ |
| `TestDifferentRuleTypes` | ✅ |

#### `tests/test_governed_autonomy.py` (NEW)

| Classe de Testes | Status |
|------------------|--------|
| `TestProposalWorkflow` | ✅ |
| `TestAutonomyNotAppliedUntilApproved` | ✅ |
| `TestRevocation` | ✅ |
| `TestIsolation` | ✅ |
| `TestLedgerEvents` | ✅ |
| `TestBundleAutonomyOverride` | ✅ |
| `TestListFunctions` | ✅ |
| `TestUpdateOperation` | ✅ |
| `TestErrorCases` | ✅ |
| `TestAllAutonomyLevels` | ✅ |

---

### 7. Error Codes

**Status:** ✅ IMPLEMENTADO em `src/engine/core/errors.py`

```python
# Governed Policies errors (Etapa 4.4)
POLICY_PROPOSAL_NOT_FOUND = "POLICY_PROPOSAL_NOT_FOUND"
POLICY_PROPOSAL_ALREADY_DECIDED = "POLICY_PROPOSAL_ALREADY_DECIDED"
POLICY_PROPOSAL_INVALID = "POLICY_PROPOSAL_INVALID"
POLICY_NOT_FOUND_FOR_UPDATE = "POLICY_NOT_FOUND_FOR_UPDATE"
POLICY_ALREADY_EXISTS = "POLICY_ALREADY_EXISTS"
GOVERNED_POLICIES_UNAVAILABLE = "GOVERNED_POLICIES_UNAVAILABLE"

# Governed Autonomy errors (Etapa 4.4)
AUTONOMY_PROPOSAL_NOT_FOUND = "AUTONOMY_PROPOSAL_NOT_FOUND"
AUTONOMY_PROPOSAL_ALREADY_DECIDED = "AUTONOMY_PROPOSAL_ALREADY_DECIDED"
AUTONOMY_PROPOSAL_INVALID = "AUTONOMY_PROPOSAL_INVALID"
AUTONOMY_NOT_FOUND_FOR_UPDATE = "AUTONOMY_NOT_FOUND_FOR_UPDATE"
GOVERNED_AUTONOMY_UNAVAILABLE = "GOVERNED_AUTONOMY_UNAVAILABLE"
```

---

## Definition of Done

- [x] Policies e autonomy podem ser governadas sem rebuild, com prova e isolamento
- [x] Proposta não altera execução até apply
- [x] Apply muda decisão do gate
- [x] Isolamento por institution/dept

---

## Arquivos Implementados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `src/engine/core/governed_policies.py` | NEW | Core module (~700 linhas) |
| `src/engine/core/governed_autonomy.py` | NEW | Core module (~700 linhas) |
| `src/engine/core/policy.py` | MODIFIED | Adicionado `institution_id` parameter |
| `src/engine/core/autonomy.py` | MODIFIED | Adicionado `institution_id` parameter |
| `src/engine/core/errors.py` | MODIFIED | Adicionados 11 error codes |
| `src/engine/api/admin_policies.py` | NEW | API endpoints (~450 linhas) |
| `src/engine/api/admin_autonomy.py` | NEW | API endpoints (~460 linhas) |
| `src/engine/api/server.py` | MODIFIED | Registrados novos routers |
| `src/engine/console/routes.py` | MODIFIED | Adicionadas rotas console (~600 linhas) |
| `src/engine/console/templates/policies.html` | NEW | Template lista efetiva |
| `src/engine/console/templates/policies_proposals.html` | NEW | Template lista proposals |
| `src/engine/console/templates/policies_proposal_new.html` | NEW | Template form criar |
| `src/engine/console/templates/policies_proposal_detail.html` | NEW | Template detalhe |
| `src/engine/console/templates/autonomy.html` | NEW | Template lista efetiva |
| `src/engine/console/templates/autonomy_proposals.html` | NEW | Template lista proposals |
| `src/engine/console/templates/autonomy_proposal_new.html` | NEW | Template form criar |
| `src/engine/console/templates/autonomy_proposal_detail.html` | NEW | Template detalhe |
| `tests/test_governed_policies.py` | NEW | Testes (~600 linhas) |
| `tests/test_governed_autonomy.py` | NEW | Testes (~600 linhas) |

---

## Semântica Implementada

### Policies
- **Operações:** `create`, `update`, `revoke`
- **Rule types:** `numeric_max`, `numeric_min`, `string_max_len`, `required_field`, `enum_allowlist`
- **Precedência:** governed > bundle (por policy_id)
- **Revogação:** Marca como revogada (excluded do effective)

### Autonomy
- **Operações:** `update_level`, `create_rule`, `update_rule`, `revoke_rule`
- **Níveis:** L0-L4 (0=full oversight, 4=full autonomy)
- **Precedência:** governed > bundle
- **Revogação:** Marca rule como revogada

### Workflow
1. `propose_*()` → Cria proposal OPEN, emite *_PROPOSED
2. `decide_*()` → Aprova/rejeita, emite *_APPROVED/*_REJECTED
3. Se approve → Chama `apply_*()` automaticamente
4. `apply_*()` → Aplica mudança, emite *_APPLIED ou *_REVOKED
5. `get_effective_*()` → Retorna merged (governed > bundle)
