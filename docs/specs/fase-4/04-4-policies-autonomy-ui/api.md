# 04-4 Governança UI (Policies + Autonomy) - API Specification

**Status:** IMPLEMENTAÇÃO COMPLETA
**Data:** 2026-01-20
**Revisado:** Implementação finalizada - Etapa 4.4

---

## Admin API Endpoints (FastAPI)

Seguir padrão de `src/engine/api/admin_mandates.py`.

### Policies Admin API

**Router:** `/admin/policies` (criar em `src/engine/api/admin_policies.py`)

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/admin/policies/proposals` | POST | Criar proposal |
| `/admin/policies/proposals` | GET | Listar proposals |
| `/admin/policies/proposals/{id}/decide` | POST | Decidir proposal |
| `/admin/policies/governed` | GET | Listar governed policies |
| `/admin/policies/effective` | GET | Listar policies efetivas |

**Headers requeridos:**
- `X-Admin-Key` ou `X-Admin-Token`
- `X-Institution-Id`
- `X-Actor-Id` (opcional, default "admin")

### Autonomy Admin API

**Router:** `/admin/autonomy` (criar em `src/engine/api/admin_autonomy.py`)

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/admin/autonomy/proposals` | POST | Criar proposal |
| `/admin/autonomy/proposals` | GET | Listar proposals |
| `/admin/autonomy/proposals/{id}/decide` | POST | Decidir proposal |
| `/admin/autonomy/governed` | GET | Listar governed autonomy |
| `/admin/autonomy/effective` | GET | Listar autonomy efetiva |

---

## Console Routes - Policies

### GET /console/policies

Lista efetiva de policies (bundle vs governado).

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |

**Response 200:**
```json
{
  "institution_id": "uuid",
  "dept_id": "dept-001",
  "source": "governed",  // "bundle" | "governed" | "merged"
  "policies": [
    {
      "policy_id": "max-limit-50k",
      "rule_type": "numeric_max",
      "field_path": "amount",
      "phase": "pre",
      "endpoint_sig": "POST /operations/*",
      "value": 50000,
      "message": "Valor máximo excedido",
      "source": "governed"  // indica origem
    }
  ],
  "bundle_count": 5,
  "governed_count": 2,
  "effective_count": 6
}
```

---

### GET /console/policies/proposals

Lista proposals de policies.

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |
| status | string | No | Filter: pending, approved, rejected, applied |

**Response 200:**
```json
{
  "proposals": [
    {
      "proposal_id": "uuid",
      "operation": "add",
      "policy_id": "max-limit-100k",
      "status": "pending",
      "proposed_by": "user-123",
      "proposed_at": "2026-01-19T10:00:00Z",
      "reason": "Aumentar limite para clientes premium"
    }
  ],
  "total": 1
}
```

---

### GET /console/policies/proposals/new

Formulário para criar nova proposal (HTML).

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |

**Response 200:** HTML (policies_proposal_new.html)

---

### POST /console/policies/proposals

Cria nova proposal de policy.

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |
| operation | string | Yes | add, update, remove |
| policy_id | string | Yes | Policy ID |
| policy_data | string | No | JSON string (required for add/update) |
| reason | string | Yes | Justificativa |

**policy_data schema (for add/update):**
```json
{
  "rule_type": "numeric_max",
  "field_path": "amount",
  "phase": "pre",
  "endpoint_sig": "POST /operations/*",
  "value": 100000,
  "message": "Valor máximo excedido"
}
```

**Response 201:**
```json
{
  "proposal_id": "uuid",
  "status": "pending",
  "message": "Proposal created successfully"
}
```

**Response 400:**
```json
{
  "error": "POLICY_PROPOSAL_INVALID_SCHEMA",
  "message": "Invalid policy data: missing required field 'rule_type'"
}
```

---

### GET /console/policies/proposals/{proposal_id}

Detalhes de uma proposal com diff.

**Path Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| proposal_id | string | Yes | Proposal UUID |

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |

**Response 200:**
```json
{
  "proposal": {
    "proposal_id": "uuid",
    "operation": "update",
    "policy_id": "max-limit-50k",
    "policy_data": {
      "rule_type": "numeric_max",
      "field_path": "amount",
      "phase": "pre",
      "endpoint_sig": "POST /operations/*",
      "value": 100000
    },
    "status": "approved",
    "proposed_by": "user-123",
    "proposed_at": "2026-01-19T10:00:00Z",
    "reason": "Aumentar limite",
    "decided_by": "admin-456",
    "decided_at": "2026-01-19T11:00:00Z",
    "decision_reason": "Aprovado conforme política interna"
  },
  "diff": {
    "before": {
      "value": 50000
    },
    "after": {
      "value": 100000
    }
  },
  "can_decide": false,
  "can_apply": true
}
```

---

### POST /console/policies/proposals/{proposal_id}/decide

Aprova ou rejeita uma proposal.

**Path Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| proposal_id | string | Yes | Proposal UUID |

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |
| decision | string | Yes | approve, reject |
| reason | string | Yes | Justificativa |

**Response 200:**
```json
{
  "proposal_id": "uuid",
  "status": "approved",
  "message": "Proposal approved successfully"
}
```

**Response 400:**
```json
{
  "error": "POLICY_PROPOSAL_ALREADY_DECIDED",
  "message": "Proposal already decided"
}
```

---

### POST /console/policies/proposals/{proposal_id}/apply

Aplica uma proposal aprovada.

**Path Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| proposal_id | string | Yes | Proposal UUID |

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |

**Response 200:**
```json
{
  "proposal_id": "uuid",
  "status": "applied",
  "message": "Policy change applied successfully",
  "effective_from": "2026-01-19T12:00:00Z"
}
```

**Response 400:**
```json
{
  "error": "POLICY_PROPOSAL_NOT_APPROVED",
  "message": "Proposal must be approved before apply"
}
```

---

## Console Routes - Autonomy

### GET /console/autonomy

Lista efetiva de autonomy (bundle vs governado).

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |

**Response 200:**
```json
{
  "institution_id": "uuid",
  "dept_id": "dept-001",
  "source": "governed",
  "current_level": 3,
  "current_level_source": "governed",
  "rules": [
    {
      "rule_id": "restrict-high-value",
      "endpoint_sig": "POST /operations/high-value",
      "phase": "pre",
      "required_level": 4,
      "source": "bundle"
    }
  ],
  "bundle_level": 4,
  "governed_level": 3
}
```

---

### GET /console/autonomy/proposals

Lista proposals de autonomy.

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |
| status | string | No | Filter: pending, approved, rejected, applied |

**Response 200:**
```json
{
  "proposals": [
    {
      "proposal_id": "uuid",
      "operation": "set_level",
      "rule_id": null,
      "autonomy_data": {
        "current_level": 2
      },
      "status": "pending",
      "proposed_by": "user-123",
      "proposed_at": "2026-01-19T10:00:00Z",
      "reason": "Reduzir autonomia para revisão obrigatória"
    }
  ],
  "total": 1
}
```

---

### GET /console/autonomy/proposals/new

Formulário para criar nova proposal (HTML).

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |

**Response 200:** HTML (autonomy_proposal_new.html)

---

### POST /console/autonomy/proposals

Cria nova proposal de autonomy.

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |
| operation | string | Yes | set_level, add_rule, update_rule, remove_rule |
| rule_id | string | No | Rule ID (required for rule operations) |
| autonomy_data | string | Yes | JSON string |
| reason | string | Yes | Justificativa |

**autonomy_data schema (for set_level):**
```json
{
  "current_level": 2
}
```

**autonomy_data schema (for add_rule/update_rule):**
```json
{
  "endpoint_sig": "POST /operations/critical",
  "phase": "pre",
  "required_level": 4
}
```

**Response 201:**
```json
{
  "proposal_id": "uuid",
  "status": "pending",
  "message": "Proposal created successfully"
}
```

---

### GET /console/autonomy/proposals/{proposal_id}

Detalhes de uma proposal com diff.

**Path Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| proposal_id | string | Yes | Proposal UUID |

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |

**Response 200:**
```json
{
  "proposal": {
    "proposal_id": "uuid",
    "operation": "set_level",
    "rule_id": null,
    "autonomy_data": {
      "current_level": 2
    },
    "status": "approved",
    "proposed_by": "user-123",
    "proposed_at": "2026-01-19T10:00:00Z",
    "reason": "Reduzir autonomia",
    "decided_by": "admin-456",
    "decided_at": "2026-01-19T11:00:00Z",
    "decision_reason": "Aprovado"
  },
  "diff": {
    "before": {
      "current_level": 4
    },
    "after": {
      "current_level": 2
    }
  },
  "can_decide": false,
  "can_apply": true
}
```

---

### POST /console/autonomy/proposals/{proposal_id}/decide

Aprova ou rejeita uma proposal.

**Path Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| proposal_id | string | Yes | Proposal UUID |

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |
| decision | string | Yes | approve, reject |
| reason | string | Yes | Justificativa |

**Response 200:**
```json
{
  "proposal_id": "uuid",
  "status": "approved",
  "message": "Proposal approved successfully"
}
```

---

### POST /console/autonomy/proposals/{proposal_id}/apply

Aplica uma proposal aprovada.

**Path Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| proposal_id | string | Yes | Proposal UUID |

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| institution_id | string | Yes | Institution UUID |
| dept_id | string | No | Department ID |

**Response 200:**
```json
{
  "proposal_id": "uuid",
  "status": "applied",
  "message": "Autonomy change applied successfully",
  "effective_from": "2026-01-19T12:00:00Z"
}
```

---

## Ledger Events

### Policy Events

| Event Type | Payload |
|------------|---------|
| POLICY_PROPOSED | `{proposal_id, operation, policy_id, reason, proposed_by}` |
| POLICY_APPROVED | `{proposal_id, policy_id, decided_by, reason}` |
| POLICY_REJECTED | `{proposal_id, policy_id, decided_by, reason}` |
| POLICY_APPLIED | `{proposal_id, policy_id, applied_by, diff_sha256}` |
| POLICY_REVOKED | `{proposal_id, policy_id, revoked_by, reason}` |

### Autonomy Events

| Event Type | Payload |
|------------|---------|
| AUTONOMY_PROPOSED | `{proposal_id, operation, rule_id, reason, proposed_by}` |
| AUTONOMY_APPROVED | `{proposal_id, rule_id, decided_by, reason}` |
| AUTONOMY_REJECTED | `{proposal_id, rule_id, decided_by, reason}` |
| AUTONOMY_APPLIED | `{proposal_id, rule_id, applied_by, diff_sha256}` |
| AUTONOMY_REVOKED | `{proposal_id, rule_id, revoked_by, reason}` |

---

## Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| POLICY_PROPOSAL_INVALID_SCHEMA | 400 | Policy data fails schema validation |
| POLICY_PROPOSAL_NOT_FOUND | 404 | Proposal not found |
| POLICY_PROPOSAL_ALREADY_DECIDED | 400 | Proposal already approved/rejected |
| POLICY_PROPOSAL_NOT_APPROVED | 400 | Cannot apply non-approved proposal |
| POLICY_NOT_FOUND | 404 | Policy ID not found |
| AUTONOMY_PROPOSAL_INVALID_SCHEMA | 400 | Autonomy data fails schema validation |
| AUTONOMY_PROPOSAL_NOT_FOUND | 404 | Proposal not found |
| AUTONOMY_PROPOSAL_ALREADY_DECIDED | 400 | Proposal already approved/rejected |
| AUTONOMY_PROPOSAL_NOT_APPROVED | 400 | Cannot apply non-approved proposal |
| AUTONOMY_RULE_NOT_FOUND | 404 | Rule ID not found |
| AUTONOMY_INVALID_LEVEL | 400 | Level must be 0-4 |

---

## Core Module APIs

### governed_policies.py

```python
def propose_policy_change(
    institution_id: str,
    operation: str,  # "add" | "update" | "remove"
    policy_id: str,
    policy_data: Optional[Dict[str, Any]],
    reason: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[PolicyProposalState], Optional[str], Optional[str]]:
    """Create a policy change proposal.

    Returns:
        (proposal_state, None, None) on success
        (None, error_code, error_message) on failure
    """

def decide_policy_proposal(
    institution_id: str,
    proposal_id: str,
    decision: str,  # "approve" | "reject"
    reason: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[PolicyProposalState], Optional[str], Optional[str]]:
    """Approve or reject a policy proposal."""

def apply_policy_change(
    institution_id: str,
    proposal_id: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Apply an approved policy proposal."""

def get_effective_policies(
    institution_id: str,
    dept_id: Optional[str] = None,
) -> Optional[PolicyDef]:
    """Get merged bundle + governed policies (governed has precedence)."""

def list_policy_proposals(
    institution_id: str,
    dept_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[PolicyProposalState]:
    """List policy proposals, optionally filtered by status."""

def get_policy_proposal(
    institution_id: str,
    proposal_id: str,
    dept_id: Optional[str] = None,
) -> Optional[PolicyProposalState]:
    """Get a specific policy proposal."""
```

### governed_autonomy.py

```python
def propose_autonomy_change(
    institution_id: str,
    operation: str,  # "set_level" | "add_rule" | "update_rule" | "remove_rule"
    rule_id: Optional[str],
    autonomy_data: Dict[str, Any],
    reason: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[AutonomyProposalState], Optional[str], Optional[str]]:
    """Create an autonomy change proposal."""

def decide_autonomy_proposal(
    institution_id: str,
    proposal_id: str,
    decision: str,  # "approve" | "reject"
    reason: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[Optional[AutonomyProposalState], Optional[str], Optional[str]]:
    """Approve or reject an autonomy proposal."""

def apply_autonomy_change(
    institution_id: str,
    proposal_id: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Apply an approved autonomy proposal."""

def get_effective_autonomy(
    institution_id: str,
    dept_id: Optional[str] = None,
) -> Optional[AutonomyDef]:
    """Get merged bundle + governed autonomy (governed has precedence)."""

def list_autonomy_proposals(
    institution_id: str,
    dept_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[AutonomyProposalState]:
    """List autonomy proposals, optionally filtered by status."""

def get_autonomy_proposal(
    institution_id: str,
    proposal_id: str,
    dept_id: Optional[str] = None,
) -> Optional[AutonomyProposalState]:
    """Get a specific autonomy proposal."""
```

---

## Templates

| Template | Description |
|----------|-------------|
| policies.html | Lista efetiva de policies com indicação de fonte |
| policies_proposals.html | Lista de proposals de policies |
| policies_proposal_new.html | Formulário para criar proposal de policy |
| policies_proposal_detail.html | Detalhes da proposal com diff visual |
| autonomy.html | Estado efetivo de autonomy com indicação de fonte |
| autonomy_proposals.html | Lista de proposals de autonomy |
| autonomy_proposal_new.html | Formulário para criar proposal de autonomy |
| autonomy_proposal_detail.html | Detalhes da proposal com diff visual |

---

## Estrutura de Storage

Seguir padrão de `governed_mandates`:

```
var/institutions/{institution_id}/governed_policies/
├── policy_proposals.jsonl          # Append-only proposals
├── governed_policies.jsonl         # Append-only applied changes
└── governed_policies_state.json    # Estado efetivo atual

var/institutions/{institution_id}/governed_autonomy/
├── autonomy_proposals.jsonl        # Append-only proposals
├── governed_autonomy.jsonl         # Append-only applied changes
└── governed_autonomy_state.json    # Estado efetivo atual

var/institutions/{institution_id}/depts/{dept_id}/governed_policies/
└── (mesma estrutura por departamento)

var/institutions/{institution_id}/depts/{dept_id}/governed_autonomy/
└── (mesma estrutura por departamento)
```

---

## Operações Suportadas

### Policies
| Operação | Descrição |
|----------|-----------|
| `create` | Criar nova policy rule (por policy_id) |
| `update` | Atualizar policy rule existente |
| `revoke` | Remover policy rule |

### Autonomy
| Operação | Descrição |
|----------|-----------|
| `update_level` | Alterar `current_level` (0-4) |
| `create_rule` | Criar nova autonomy rule (por rule_id) |
| `update_rule` | Atualizar autonomy rule existente |
| `revoke_rule` | Remover autonomy rule |

---

## Validação de Schema

### Policies (reusar `parse_policies_data()`)
```python
# Schema v1.1 - campos obrigatórios
{
  "policy_id": "string",
  "rule_type": "numeric_max|numeric_min|string_max_len|required_field|enum_allowlist",
  "field_path": "string (dot notation)",
  "phase": "pre|post",
  "endpoint_sig": "POST /finance/expenses|POST /approvals/{approval_id}/decide"
}
```

### Autonomy (reusar `parse_autonomy_data()`)
```python
# Schema v1.0 - campos obrigatórios
{
  "rule_id": "string",
  "endpoint_sig": "POST /finance/expenses|POST /approvals/{approval_id}/decide|POST /support/tickets",
  "phase": "pre|post",
  "required_level": 0  # 0-4
}

# Para update_level
{
  "current_level": 0  # 0-4
}
```

---

## Implementação (COMPLETA)

| Etapa | Arquivo | Status |
|-------|---------|--------|
| 1 | `errors.py` - Códigos de erro | ✅ |
| 2 | `governed_policies.py` - Core module | ✅ |
| 3 | `governed_autonomy.py` - Core module | ✅ |
| 4 | `admin_policies.py` - API endpoints | ✅ |
| 5 | `admin_autonomy.py` - API endpoints | ✅ |
| 6 | `server.py` - Registrar routers | ✅ |
| 7 | `routes.py` - Rotas console | ✅ |
| 8 | Templates - 8 templates HTML | ✅ |
| 9 | Runtime integration - evaluate_policies/autonomy | ✅ |
| 10 | Testes - test_governed_policies.py, test_governed_autonomy.py | ✅ |
