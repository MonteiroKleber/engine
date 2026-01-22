# 04-3 Legacy Bridge Write-Mode (Governado) - API Design

**Status:** IMPLEMENTADO
**Data:** 2026-01-19

## Endpoints

### POST /bridge/write/{action}

**Descrição:** Enfileira ação de escrita governada no outbox do legacy.

**Auth:** X-Admin-Token header (obrigatório)

**Path Parameters:**
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `action` | string | Sim | Tipo da ação (e.g., `increase_limit`) |

**Request Body:**
```json
{
  "institution_id": "uuid",
  "dept_id": "dept-1",
  "params": {
    "customer_id": "CUST-123",
    "new_limit": 50000,
    "reason": "Credit review approved"
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |
| `dept_id` | string | Não | Department ID (para multi-dept) |
| `params` | object | Sim | Parâmetros da ação (schema por action_type) |

**Response 201 Created:**
```json
{
  "action_id": "550e8400-e29b-41d4-a716-446655440000",
  "action_type": "increase_limit",
  "status": "enqueued",
  "outbox_path": "legacy_bridge/outbox/550e8400-e29b-41d4-a716-446655440000.json",
  "outbox_sha256": "SHA256:abc123...",
  "intent_sha256": "SHA256:def456...",
  "mandate_id": "mandate-uuid",
  "created_at": "2026-01-19T10:30:00.123456Z"
}
```

**Response 202 Accepted (Pending Approval):**
```json
{
  "action_id": "550e8400-e29b-41d4-a716-446655440000",
  "action_type": "increase_limit",
  "status": "pending_approval",
  "approval_id": "approval-uuid",
  "intent_sha256": "SHA256:def456...",
  "message": "Action requires approval before execution"
}
```

**Response 403 Forbidden:**
```json
{
  "error": "LEGACY_WRITE_DENIED",
  "denied_by": "MANDATE",
  "message": "No applicable mandate for action",
  "violations": [
    {
      "gate": "mandate",
      "rule_id": null,
      "reason": "No mandate found for POST /bridge/write/increase_limit"
    }
  ]
}
```

**Response 400 Bad Request:**
```json
{
  "error": "LEGACY_WRITE_INVALID_PARAMS",
  "message": "Invalid params for action type",
  "validation_errors": [
    {
      "field": "new_limit",
      "error": "must be a positive number"
    }
  ]
}
```

**Erros Possíveis:**
| Código | HTTP | Descrição |
|--------|------|-----------|
| `LEGACY_WRITE_DENIED` | 403 | Governança bloqueou a ação |
| `LEGACY_WRITE_INVALID_PARAMS` | 400 | Parâmetros inválidos para action_type |
| `LEGACY_WRITE_UNKNOWN_ACTION` | 400 | Action type não suportado |
| `INSTITUTION_NOT_FOUND` | 404 | Instituição não existe |
| `ADMIN_KEY_INVALID` | 401 | Token admin inválido |

---

### GET /bridge/write/actions

**Descrição:** Lista ações de escrita para uma instituição.

**Auth:** X-Admin-Token header (obrigatório)

**Query Parameters:**
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |
| `dept_id` | string | Não | Filtrar por departamento |
| `status` | string | Não | Filtrar por status (pending, enqueued, acked) |
| `limit` | int | Não | Máximo de resultados (default 50) |

**Response 200 OK:**
```json
{
  "actions": [
    {
      "action_id": "uuid-1",
      "action_type": "increase_limit",
      "status": "enqueued",
      "created_at": "2026-01-19T10:30:00Z",
      "requested_by": "user-123"
    },
    {
      "action_id": "uuid-2",
      "action_type": "increase_limit",
      "status": "pending_approval",
      "created_at": "2026-01-19T10:25:00Z",
      "requested_by": "user-456",
      "approval_id": "approval-uuid"
    }
  ],
  "total": 2
}
```

---

### GET /bridge/write/actions/{action_id}

**Descrição:** Detalhes de uma ação de escrita específica.

**Auth:** X-Admin-Token header (obrigatório)

**Path Parameters:**
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `action_id` | string | Sim | UUID da ação |

**Query Parameters:**
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |

**Response 200 OK:**
```json
{
  "action_id": "550e8400-e29b-41d4-a716-446655440000",
  "action_type": "increase_limit",
  "status": "enqueued",
  "params": {
    "customer_id": "CUST-123",
    "new_limit": 50000,
    "reason": "Credit review approved"
  },
  "intent_sha256": "SHA256:def456...",
  "outbox_path": "legacy_bridge/outbox/550e8400.json",
  "outbox_sha256": "SHA256:abc123...",
  "requested_by": "user-123",
  "approved_by": "manager-456",
  "mandate_id": "mandate-uuid",
  "created_at": "2026-01-19T10:30:00.123456Z",
  "ledger_events": [
    "LEGACY_WRITE_INTENT_CREATED",
    "LEGACY_WRITE_ALLOWED",
    "LEGACY_WRITE_ENQUEUED"
  ]
}
```

---

### POST /bridge/write/actions/{action_id}/ack

**Descrição:** Registra confirmação de execução pelo aplicador externo.

**Auth:** X-Admin-Token header (obrigatório)

**Path Parameters:**
| Param | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `action_id` | string | Sim | UUID da ação |

**Request Body:**
```json
{
  "institution_id": "uuid",
  "result": "success",
  "external_ref": "LEGACY-TXN-12345",
  "executed_at": "2026-01-19T10:35:00Z",
  "details": {
    "previous_limit": 30000,
    "new_limit": 50000
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `institution_id` | string | Sim | UUID da instituição |
| `result` | string | Sim | "success" ou "failed" |
| `external_ref` | string | Não | Referência no sistema legado |
| `executed_at` | string | Não | ISO8601 timestamp da execução |
| `details` | object | Não | Detalhes adicionais do resultado |

**Response 200 OK:**
```json
{
  "action_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "acked",
  "acked_at": "2026-01-19T10:35:00Z"
}
```

---

## Modelos

### LegacyWriteAction

```python
@dataclass
class LegacyWriteAction:
    """Ação de escrita governada no legado."""

    # Identificação
    action_id: str                    # UUID v4
    action_type: str                  # e.g., "increase_limit"

    # Parâmetros
    params: Dict[str, Any]            # Schema por action_type

    # Integridade
    intent_sha256: str                # SHA256 dos params canônicos

    # Audit
    requested_by: str                 # Actor ID do solicitante
    approved_by: Optional[str]        # Actor ID que aprovou (se approval)
    mandate_id: Optional[str]         # ID do mandate que permitiu
    created_at: str                   # ISO8601 UTC

    # Tracking
    case_id: str                      # = action_id
    institution_id: str
    dept_id: Optional[str]

    # Status
    status: str                       # pending_approval, enqueued, acked, failed

    # Outbox
    outbox_path: Optional[str]        # Relative path to outbox file
    outbox_sha256: Optional[str]      # SHA256 do arquivo

    # Ack (opcional)
    acked_at: Optional[str]
    ack_result: Optional[str]         # success, failed
    external_ref: Optional[str]       # Ref no sistema legado
```

### OutboxFile

**Formato do arquivo outbox (JSON determinístico):**

```json
{
  "schema_version": "1.0",
  "action_id": "550e8400-e29b-41d4-a716-446655440000",
  "action_type": "increase_limit",
  "params": {
    "customer_id": "CUST-123",
    "new_limit": 50000,
    "reason": "Credit review approved"
  },
  "intent_sha256": "SHA256:def456...",
  "requested_by": "user-123",
  "approved_by": "manager-456",
  "mandate_id": "mandate-uuid",
  "created_at": "2026-01-19T10:30:00.123456Z",
  "case_id": "550e8400-e29b-41d4-a716-446655440000",
  "institution_id": "inst-uuid",
  "dept_id": "dept-1"
}
```

**Geração determinística:**
```python
import json

def write_outbox_file(action: LegacyWriteAction, outbox_dir: Path) -> Tuple[Path, str]:
    """Write outbox file with deterministic JSON.

    Returns: (file_path, sha256_hash)
    """
    content = {
        "schema_version": "1.0",
        "action_id": action.action_id,
        "action_type": action.action_type,
        "params": action.params,
        "intent_sha256": action.intent_sha256,
        "requested_by": action.requested_by,
        "approved_by": action.approved_by,
        "mandate_id": action.mandate_id,
        "created_at": action.created_at,
        "case_id": action.case_id,
        "institution_id": action.institution_id,
        "dept_id": action.dept_id,
    }

    # Deterministic JSON (sorted keys, minimal separators)
    json_bytes = json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    ).encode("utf-8")

    file_path = outbox_dir / f"{action.action_id}.json"
    file_path.write_bytes(json_bytes)

    sha256 = hashlib.sha256(json_bytes).hexdigest()
    return file_path, f"SHA256:{sha256}"
```

---

## Ledger Events

### LEGACY_WRITE_INTENT_CREATED

Emitido quando intenção de escrita é recebida.

```json
{
  "event_type": "LEGACY_WRITE_INTENT_CREATED",
  "tenant_id": "institution-uuid",
  "actor_id": "user-123",
  "case_id": "action-uuid",
  "step": "LEGACY_WRITE:increase_limit:intent",
  "payload": {
    "action_id": "action-uuid",
    "action_type": "increase_limit",
    "params_sha256": "SHA256:...",
    "requested_by": "user-123"
  }
}
```

### LEGACY_WRITE_ALLOWED

Emitido quando governança permite a escrita.

```json
{
  "event_type": "LEGACY_WRITE_ALLOWED",
  "tenant_id": "institution-uuid",
  "actor_id": "user-123",
  "case_id": "action-uuid",
  "step": "LEGACY_WRITE:increase_limit:allowed",
  "payload": {
    "action_id": "action-uuid",
    "mandate_id": "mandate-uuid",
    "mandate_endpoint": "POST /bridge/write/increase_limit",
    "autonomy_level": 3,
    "policy_matched": ["max-limit-policy"],
    "approved_by": "manager-456"
  }
}
```

### LEGACY_WRITE_DENIED

Emitido quando governança bloqueia a escrita.

```json
{
  "event_type": "LEGACY_WRITE_DENIED",
  "tenant_id": "institution-uuid",
  "actor_id": "user-123",
  "case_id": "action-uuid",
  "step": "LEGACY_WRITE:increase_limit:denied",
  "payload": {
    "action_id": "action-uuid",
    "denied_by": "MANDATE",
    "reason": "No applicable mandate for action",
    "violations": [
      {
        "gate": "mandate",
        "rule_id": null,
        "reason": "No mandate found"
      }
    ]
  }
}
```

### LEGACY_WRITE_ENQUEUED

Emitido quando arquivo é gravado no outbox.

```json
{
  "event_type": "LEGACY_WRITE_ENQUEUED",
  "tenant_id": "institution-uuid",
  "actor_id": "user-123",
  "case_id": "action-uuid",
  "step": "LEGACY_WRITE:increase_limit:enqueued",
  "payload": {
    "action_id": "action-uuid",
    "outbox_path": "legacy_bridge/outbox/action-uuid.json",
    "outbox_sha256": "SHA256:abc123..."
  }
}
```

### LEGACY_WRITE_ACKED

Emitido quando confirmação de execução é recebida.

```json
{
  "event_type": "LEGACY_WRITE_ACKED",
  "tenant_id": "institution-uuid",
  "actor_id": "system",
  "case_id": "action-uuid",
  "step": "LEGACY_WRITE:increase_limit:acked",
  "payload": {
    "action_id": "action-uuid",
    "result": "success",
    "external_ref": "LEGACY-TXN-12345",
    "executed_at": "2026-01-19T10:35:00Z"
  }
}
```

---

## Action Schemas

### increase_limit

**Descrição:** Aumenta limite de crédito de cliente no sistema legado.

**Schema:**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["customer_id", "new_limit"],
  "properties": {
    "customer_id": {
      "type": "string",
      "description": "Identificador do cliente no legado",
      "pattern": "^[A-Z]+-[0-9]+$"
    },
    "new_limit": {
      "type": "number",
      "description": "Novo limite em centavos",
      "minimum": 0,
      "maximum": 100000000
    },
    "reason": {
      "type": "string",
      "description": "Justificativa para o aumento",
      "maxLength": 500
    },
    "effective_date": {
      "type": "string",
      "format": "date",
      "description": "Data efetiva (YYYY-MM-DD)"
    }
  },
  "additionalProperties": false
}
```

**Exemplo de mandate para esta ação:**
```json
{
  "mandate_id": "increase-limit-mandate",
  "endpoint_sig": "POST /bridge/write/increase_limit",
  "phase": "pre",
  "allowed_roles": ["credit_manager", "branch_director"],
  "valid_from": "2026-01-01T00:00:00Z",
  "valid_until": "2026-12-31T23:59:59Z",
  "limits": [
    {
      "rule_type": "numeric_max",
      "field_path": "new_limit",
      "value": 50000000
    }
  ]
}
```

---

## Outbox File Location

**Estrutura de diretórios:**

```
var/
└── institutions/
    └── {institution_id}/
        └── legacy_bridge/
            ├── assets_registry.jsonl     # (existente)
            ├── snapshots.jsonl           # (existente)
            ├── state.json                # (existente)
            ├── outbox/                   # NOVO
            │   ├── {action_id_1}.json
            │   ├── {action_id_2}.json
            │   └── ...
            └── actions_registry.jsonl    # NOVO - registro de ações

# Com multi-departamento:
var/
└── institutions/
    └── {institution_id}/
        └── depts/
            └── {dept_id}/
                └── legacy_bridge/
                    ├── outbox/
                    │   └── {action_id}.json
                    └── actions_registry.jsonl
```

---

## Considerações de Segurança

1. **Auth:** Todas as rotas exigem X-Admin-Token válido
2. **Isolamento:** Outbox por instituição/departamento
3. **Integridade:** SHA256 de params (intent) e arquivo (outbox)
4. **Audit trail:** Eventos de ledger para toda a cadeia
5. **Não-execução direta:** Engine apenas grava outbox, não executa no legado
6. **Governança:** Mandate + Autonomy + Policy obrigatórios antes de enqueue

---

## Fluxo de Governança

```
┌─────────────────────────────────────────────────────────────────┐
│                POST /bridge/write/{action}                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Validate params against action schema                        │
│     └─ 400 if invalid                                            │
│                                                                  │
│  2. Compute intent_sha256 = SHA256(canonical_json(params))       │
│                                                                  │
│  3. Emit LEGACY_WRITE_INTENT_CREATED                             │
│                                                                  │
│  4. MANDATE GATE                                                 │
│     ├─ evaluate_mandates("pre", endpoint_sig, actor, params)     │
│     └─ if deny → Emit LEGACY_WRITE_DENIED → 403                  │
│                                                                  │
│  5. AUTONOMY GATE                                                │
│     ├─ evaluate_autonomy("pre", endpoint_sig)                    │
│     └─ if deny → Emit LEGACY_WRITE_DENIED → 403                  │
│                                                                  │
│  6. POLICY GATE                                                  │
│     ├─ evaluate_policies("pre", endpoint_sig, params)            │
│     └─ if deny → Emit LEGACY_WRITE_DENIED → 403                  │
│                                                                  │
│  7. APPROVAL CHECK                                               │
│     ├─ if approval rule exists:                                  │
│     │   ├─ Emit APPROVAL_REQUESTED                               │
│     │   └─ Return 202 { status: "pending_approval" }             │
│     └─ else: continue                                            │
│                                                                  │
│  8. Emit LEGACY_WRITE_ALLOWED                                    │
│                                                                  │
│  9. Write outbox file                                            │
│     ├─ Path: legacy_bridge/outbox/{action_id}.json               │
│     └─ Compute outbox_sha256                                     │
│                                                                  │
│  10. Emit LEGACY_WRITE_ENQUEUED                                  │
│                                                                  │
│  11. Return 201 { action_id, status: "enqueued", ... }           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testes Necessários

### Test Happy Path

```python
class TestLegacyWriteHappyPath:
    """Test complete write flow."""

    def test_write_with_valid_mandate_creates_outbox(self):
        """
        1. Configure mandate for POST /bridge/write/increase_limit
        2. POST /bridge/write/increase_limit with valid params
        3. Assert 201 response
        4. Assert outbox file exists with correct content
        5. Assert ledger has INTENT_CREATED, ALLOWED, ENQUEUED events
        """
        pass

    def test_write_audit_trail_complete(self):
        """Verify all events can be traced offline."""
        pass
```

### Test Deny Cases

```python
class TestLegacyWriteDenied:
    def test_no_mandate_returns_403(self):
        pass

    def test_expired_mandate_returns_403(self):
        pass

    def test_insufficient_autonomy_returns_403(self):
        pass

    def test_policy_violation_returns_403(self):
        pass

    def test_denied_emits_ledger_event(self):
        pass
```

### Test Isolation

```python
class TestLegacyWriteIsolation:
    def test_outbox_isolated_by_institution(self):
        pass

    def test_outbox_isolated_by_department(self):
        pass

    def test_cannot_access_other_institution_outbox(self):
        pass
```

### Test Approval Flow

```python
class TestLegacyWriteApproval:
    def test_approval_required_returns_202(self):
        pass

    def test_approval_denied_no_outbox_created(self):
        pass

    def test_approval_granted_creates_outbox(self):
        pass

    def test_sod_requester_cannot_approve(self):
        pass
```
