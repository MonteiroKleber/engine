# Errors — Runtime Gates

**Data:** 2026-01-18
**Versao:** 1.0
**Etapa:** 04 — Runtime Gates

---

## 1. Visao Geral

Este documento define os codigos de erro deterministicos esperados para falhas de gate no runtime do Libervia Engine.

---

## 2. Principios

1. **Deterministico:** Mesmo input deve produzir mesmo erro.
2. **Rastreavel:** Erros incluem `case_id`, `request_id`, `actor_id` quando aplicavel.
3. **Especifico:** Codigo de erro identifica o gate que falhou.
4. **Auditavel:** Toda decisao deny emite evento no ledger.

---

## 3. Erros por Gate

### 3.1 RBAC Gate

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 403 | `RBAC_DENIED` | Actor nao tem permissao para a operacao |

**Payload de Erro:**
```json
{
  "error": "RBAC_DENIED",
  "message": "Permission denied: actor does not have 'expense.create' permission",
  "details": {
    "actor_id": "user-123",
    "actor_roles": ["employee"],
    "required_permission": "expense.create",
    "case_id": "expense-456"
  }
}
```

**Evento Ledger:**
```json
{
  "event_type": "RBAC_DECISION",
  "payload": {
    "permission": "expense.create",
    "decision": "deny",
    "actor_id": "user-123",
    "actor_roles": ["employee"]
  }
}
```

---

### 3.2 Policy Gate

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 403 | `POLICY_DENIED` | Policy rule violada (pre ou post phase) |

**Payload de Erro:**
```json
{
  "error": "POLICY_DENIED",
  "message": "Policy violation: amount exceeds maximum limit",
  "details": {
    "phase": "pre",
    "endpoint_sig": "POST /finance/expenses",
    "violations": [
      {
        "policy_id": "max-expense-1000",
        "rule_type": "numeric_max",
        "field_path": "amount",
        "expected": 1000,
        "actual": 5000,
        "message": "Amount exceeds limit of 1000"
      }
    ],
    "case_id": "expense-456",
    "actor_id": "user-123"
  }
}
```

**Evento Ledger:**
```json
{
  "event_type": "POLICY_PRE_DECISION",
  "payload": {
    "allow": false,
    "matched_policies": ["max-expense-1000"],
    "violations": [
      {
        "policy_id": "max-expense-1000",
        "field_path": "amount",
        "message": "Amount exceeds limit of 1000"
      }
    ]
  }
}
```

---

### 3.3 Mandate Gate

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 403 | `MANDATE_DENIED` | Nenhum mandate aplicavel ou mandate invalido |

**Payload de Erro (sem mandate aplicavel):**
```json
{
  "error": "MANDATE_DENIED",
  "message": "No applicable mandate for this operation",
  "details": {
    "phase": "pre",
    "endpoint_sig": "POST /finance/expenses",
    "reason": "no_matching_mandate",
    "case_id": "expense-456",
    "actor_id": "user-123"
  }
}
```

**Payload de Erro (mandate expirado):**
```json
{
  "error": "MANDATE_DENIED",
  "message": "Mandate has expired",
  "details": {
    "phase": "pre",
    "endpoint_sig": "POST /finance/expenses",
    "mandate_id": "mandate-789",
    "reason": "expired",
    "valid_until": "2026-01-01T00:00:00Z",
    "case_id": "expense-456",
    "actor_id": "user-123"
  }
}
```

**Evento Ledger:**
```json
{
  "event_type": "MANDATE_EVALUATED",
  "payload": {
    "allow": false,
    "mandate_id": null,
    "reason": "no_matching_mandate",
    "violations": [
      {
        "code": "NO_APPLICABLE_MANDATE",
        "message": "No mandate found for POST /finance/expenses"
      }
    ]
  }
}
```

---

### 3.4 Autonomy Gate

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 403 | `AUTONOMY_INSUFFICIENT` | Nivel de autonomia insuficiente ou sem rule aplicavel |

**Payload de Erro (sem rule aplicavel):**
```json
{
  "error": "AUTONOMY_INSUFFICIENT",
  "message": "No autonomy rule applicable for this operation",
  "details": {
    "phase": "pre",
    "endpoint_sig": "POST /finance/expenses",
    "reason": "no_matching_rule",
    "case_id": "expense-456",
    "actor_id": "user-123"
  }
}
```

**Payload de Erro (nivel insuficiente):**
```json
{
  "error": "AUTONOMY_INSUFFICIENT",
  "message": "Operation requires higher autonomy level",
  "details": {
    "phase": "pre",
    "endpoint_sig": "POST /finance/expenses",
    "current_level": 1,
    "required_level": 3,
    "rule_id": "autonomy-rule-finance",
    "case_id": "expense-456",
    "actor_id": "user-123"
  }
}
```

**Evento Ledger:**
```json
{
  "event_type": "AUTONOMY_EVALUATED",
  "payload": {
    "decision": "deny",
    "current_level": 1,
    "required_level": 3,
    "rule_id": "autonomy-rule-finance",
    "reason": "insufficient_level"
  }
}
```

---

### 3.5 SoD Gate (Separation of Duties)

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 409 | `SOD_VIOLATION` | Violacao de separacao de deveres |
| 500 | `SOD_RULE_INVALID` | Regra SoD mal configurada |

**Payload de Erro (violacao):**
```json
{
  "error": "SOD_VIOLATION",
  "message": "Separation of Duties violation: requester cannot approve own request",
  "details": {
    "rule_name": "REQUESTER_NEQ_DECIDER",
    "requester_id": "user-123",
    "decider_id": "user-123",
    "case_id": "approval-789"
  }
}
```

**Evento Ledger:**
```json
{
  "event_type": "SOD_VIOLATION",
  "payload": {
    "rule_name": "REQUESTER_NEQ_DECIDER",
    "requester_id": "user-123",
    "decider_id": "user-123"
  }
}
```

---

### 3.6 Approvals Gate

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 403 | `APPROVAL_DENIED` | Actor nao pode decidir esta aprovacao |
| 404 | `APPROVAL_NOT_FOUND` | Aprovacao nao encontrada |
| 409 | `APPROVAL_ALREADY_DECIDED` | Aprovacao ja foi decidida |

**Payload de Erro (nao pode decidir):**
```json
{
  "error": "APPROVAL_DENIED",
  "message": "Actor cannot decide this approval",
  "details": {
    "approval_id": "approval-789",
    "actor_id": "user-123",
    "actor_roles": ["employee"],
    "required_roles": ["manager", "admin"],
    "rule_name": "expense_approval"
  }
}
```

---

### 3.7 Invariants Gate

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 422 | `INVARIANT_VIOLATED` | Dados nao satisfazem invariantes |

**Payload de Erro:**
```json
{
  "error": "INVARIANT_VIOLATED",
  "message": "Expense data violates schema invariants",
  "details": {
    "violations": [
      {
        "field": "amount",
        "constraint": "positive_number",
        "actual": -100,
        "message": "Amount must be a positive number"
      },
      {
        "field": "description",
        "constraint": "required",
        "actual": null,
        "message": "Description is required"
      }
    ],
    "case_id": "expense-456"
  }
}
```

**Evento Ledger:**
```json
{
  "event_type": "INVARIANT_VIOLATED",
  "payload": {
    "violations": [
      {"field": "amount", "constraint": "positive_number"},
      {"field": "description", "constraint": "required"}
    ]
  }
}
```

---

### 3.8 Freeze Gate

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 423 | `INSTITUTION_FROZEN` | Instituicao em modo freeze |

**Payload de Erro:**
```json
{
  "error": "INSTITUTION_FROZEN",
  "message": "Institution is in freeze mode. All mutations are blocked.",
  "details": {
    "freeze_mode": true,
    "endpoint_sig": "POST /finance/expenses",
    "actor_id": "user-123"
  }
}
```

**Evento Ledger:**
```json
{
  "event_type": "INSTITUTION_FREEZE_BLOCKED",
  "payload": {
    "decision": "deny",
    "reason": "freeze_mode",
    "endpoint_sig": "POST /finance/expenses"
  }
}
```

---

### 3.9 Emergency Stop Gate

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 503 | `EMERGENCY_STOP` | Endpoint bloqueado por emergency stop |

**Payload de Erro:**
```json
{
  "error": "EMERGENCY_STOP",
  "message": "Endpoint blocked by emergency stop",
  "details": {
    "endpoint_sig": "POST /finance/expenses",
    "blocked_endpoints": ["POST /finance/expenses", "POST /approvals/*/decide"],
    "actor_id": "user-123"
  }
}
```

**Evento Ledger:**
```json
{
  "event_type": "INSTITUTION_EMERGENCY_STOP_BLOCKED",
  "payload": {
    "decision": "deny",
    "reason": "emergency_stop",
    "endpoint_sig": "POST /finance/expenses"
  }
}
```

---

### 3.10 EGE Drift Gate

| Codigo HTTP | Error Code | Descricao |
|-------------|------------|-----------|
| 409 | `EGE_DRIFT_ACTIVE` | Drift detectado, mutacoes bloqueadas |

**Payload de Erro:**
```json
{
  "error": "EGE_DRIFT_ACTIVE",
  "message": "Drift detected. Mutations blocked until drift is resolved.",
  "details": {
    "drift_status": "ACTIVE",
    "bundle_manifest_mismatch": true,
    "contract_ledger_mismatch": false,
    "endpoint_sig": "POST /finance/expenses",
    "actor_id": "user-123"
  }
}
```

**Evento Ledger:**
```json
{
  "event_type": "EGE_DRIFT_BLOCKED",
  "payload": {
    "drift_status": "ACTIVE",
    "bundle_manifest_mismatch": true,
    "contract_ledger_mismatch": false
  }
}
```

---

## 4. Erros de Contrato Ausente (Loader)

Estes erros ocorrem no boot, nao em runtime:

| Error Code | Descricao |
|------------|-----------|
| `BUNDLE_CONTRACT_MISSING` | Contrato obrigatorio ausente no bundle |
| `BUNDLE_HASH_MISMATCH` | Hash do contrato nao confere com manifest |
| `BUNDLE_MANIFEST_MISSING` | bundle.manifest.json ausente |
| `BUNDLE_MANIFEST_INVALID` | bundle.manifest.json mal formado |

**Resultado:** Sistema entra em `SAFE_MODE`.

---

## 5. Tabela Resumo

| Gate | HTTP | Error Code | Evento Ledger |
|------|------|------------|---------------|
| RBAC | 403 | `RBAC_DENIED` | `RBAC_DECISION` |
| Policy | 403 | `POLICY_DENIED` | `POLICY_*_DECISION` |
| Mandate | 403 | `MANDATE_DENIED` | `MANDATE_EVALUATED` |
| Autonomy | 403 | `AUTONOMY_INSUFFICIENT` | `AUTONOMY_EVALUATED` |
| SoD | 409 | `SOD_VIOLATION` | `SOD_VIOLATION` |
| SoD (config) | 500 | `SOD_RULE_INVALID` | - |
| Approvals | 403 | `APPROVAL_DENIED` | - |
| Invariants | 422 | `INVARIANT_VIOLATED` | `INVARIANT_VIOLATED` |
| Freeze | 423 | `INSTITUTION_FROZEN` | `INSTITUTION_FREEZE_BLOCKED` |
| Emergency Stop | 503 | `EMERGENCY_STOP` | `INSTITUTION_EMERGENCY_STOP_BLOCKED` |
| EGE Drift | 409 | `EGE_DRIFT_ACTIVE` | `EGE_DRIFT_BLOCKED` |

---

## 6. Novos Error Codes (MVP)

Para implementar a semantica canonica, os seguintes error codes precisam ser adicionados ou ajustados:

| Error Code | Condicao | Atual | Esperado |
|------------|----------|-------|----------|
| `MANDATE_DENIED` | Sem mandate aplicavel | allow | **deny** |
| `AUTONOMY_INSUFFICIENT` | Sem rule aplicavel | allow | **deny** |

---

## 7. Referencias

- [spec.md](spec.md) - Especificacao da Etapa 04
- [gates-matrix.md](gates-matrix.md) - Matriz de gates
- [errors.py](../../../../src/engine/core/errors.py) - Constantes de erro

---

**Status:** ESPECIFICACAO ATIVA
**Data:** 2026-01-18
