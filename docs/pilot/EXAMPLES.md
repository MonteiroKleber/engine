# Examples — Libervia Engine Pilot

## PT-BR

### Fluxo Completo: Criar e Aprovar Despesa

#### 1. Analista cria despesa

```bash
curl -X POST http://localhost:8000/finance/expenses \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: analyst-001" \
  -H "X-Actor-Roles: analyst" \
  -H "X-Tenant-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"amount": 1500.00, "description": "Material de escritório"}'
```

**Resposta (202 Accepted):**
```json
{
  "status": "pending_approval",
  "expense_id": "exp-uuid-here",
  "approval_id": "apr-uuid-here",
  "step": "APPROVAL:expense.create"
}
```

#### 2. Gerente aprova despesa

```bash
curl -X POST http://localhost:8000/approvals/apr-uuid-here/decide \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: manager-001" \
  -H "X-Actor-Roles: manager" \
  -H "X-Tenant-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"decision": "approve"}'
```

**Resposta (200 OK):**
```json
{
  "status": "decided",
  "decision": "approve",
  "case_status": "COMMITTED",
  "expense_id": "exp-uuid-here"
}
```

#### 3. Gerente rejeita despesa

```bash
curl -X POST http://localhost:8000/approvals/apr-uuid-here/decide \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: manager-001" \
  -H "X-Actor-Roles: manager" \
  -H "X-Tenant-Id: 00000000-0000-0000-0000-000000000001" \
  -d '{"decision": "reject", "reason": "Orçamento insuficiente"}'
```

**Resposta (200 OK):**
```json
{
  "status": "decided",
  "decision": "reject",
  "case_status": "REJECTED",
  "expense_id": "exp-uuid-here"
}
```

### Cenários de Erro

#### RBAC: Sem permissão (403)

```bash
curl -X POST http://localhost:8000/finance/expenses \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: viewer-001" \
  -H "X-Actor-Roles: viewer" \
  -d '{"amount": 100.00}'
```

**Resposta (403 Forbidden):**
```json
{
  "code": "FORBIDDEN",
  "message": "Permission denied: expense.create"
}
```

#### SoD: Self-approval (409)

```bash
# Analista tenta aprovar própria despesa
curl -X POST http://localhost:8000/approvals/apr-uuid-here/decide \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: analyst-001" \
  -H "X-Actor-Roles: analyst,manager" \
  -d '{"decision": "approve"}'
```

**Resposta (409 Conflict):**
```json
{
  "code": "SOD_VIOLATION",
  "message": "SoD violation: no_self_approval"
}
```

#### Invariante: Valor inválido (422)

```bash
# Despesa com amount=0 (inválido)
curl -X POST http://localhost:8000/finance/expenses \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: analyst-001" \
  -H "X-Actor-Roles: analyst" \
  -d '{"amount": 0, "description": "teste"}'

# Depois, ao aprovar:
curl -X POST http://localhost:8000/approvals/apr-uuid-here/decide \
  -H "X-Actor-Id: manager-001" \
  -H "X-Actor-Roles: manager" \
  -d '{"decision": "approve"}'
```

**Resposta (422 Unprocessable Entity):**
```json
{
  "code": "INVARIANT_VIOLATION",
  "message": "Invariant violation",
  "violations": ["amount must be >= 0.01"]
}
```

#### Rate Limit (429)

```bash
# Após exceder limite (ex: 60 req/min)
curl -X POST http://localhost:8000/finance/expenses \
  -H "X-Actor-Id: analyst-001" \
  -H "X-Actor-Roles: analyst" \
  -d '{"amount": 100}'
```

**Resposta (429 Too Many Requests):**
```json
{
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded"
}
```

---

## EN

### Complete Flow: Create and Approve Expense

#### 1. Analyst creates expense

```bash
curl -X POST http://localhost:8000/finance/expenses \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: analyst-001" \
  -H "X-Actor-Roles: analyst" \
  -H "X-Tenant-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"amount": 1500.00, "description": "Office supplies"}'
```

**Response (202 Accepted):**
```json
{
  "status": "pending_approval",
  "expense_id": "exp-uuid-here",
  "approval_id": "apr-uuid-here",
  "step": "APPROVAL:expense.create"
}
```

#### 2. Manager approves expense

```bash
curl -X POST http://localhost:8000/approvals/apr-uuid-here/decide \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: manager-001" \
  -H "X-Actor-Roles: manager" \
  -H "X-Tenant-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"decision": "approve"}'
```

**Response (200 OK):**
```json
{
  "status": "decided",
  "decision": "approve",
  "case_status": "COMMITTED",
  "expense_id": "exp-uuid-here"
}
```

#### 3. Manager rejects expense

```bash
curl -X POST http://localhost:8000/approvals/apr-uuid-here/decide \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: manager-001" \
  -H "X-Actor-Roles: manager" \
  -H "X-Tenant-Id: 00000000-0000-0000-0000-000000000001" \
  -d '{"decision": "reject", "reason": "Insufficient budget"}'
```

**Response (200 OK):**
```json
{
  "status": "decided",
  "decision": "reject",
  "case_status": "REJECTED",
  "expense_id": "exp-uuid-here"
}
```

### Error Scenarios

#### RBAC: No permission (403)

```bash
curl -X POST http://localhost:8000/finance/expenses \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: viewer-001" \
  -H "X-Actor-Roles: viewer" \
  -d '{"amount": 100.00}'
```

**Response (403 Forbidden):**
```json
{
  "code": "FORBIDDEN",
  "message": "Permission denied: expense.create"
}
```

#### SoD: Self-approval (409)

```bash
# Analyst tries to approve own expense
curl -X POST http://localhost:8000/approvals/apr-uuid-here/decide \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: analyst-001" \
  -H "X-Actor-Roles: analyst,manager" \
  -d '{"decision": "approve"}'
```

**Response (409 Conflict):**
```json
{
  "code": "SOD_VIOLATION",
  "message": "SoD violation: no_self_approval"
}
```

#### Invariant: Invalid value (422)

```bash
# Expense with amount=0 (invalid)
curl -X POST http://localhost:8000/finance/expenses \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: analyst-001" \
  -H "X-Actor-Roles: analyst" \
  -d '{"amount": 0, "description": "test"}'

# Then, when approving:
curl -X POST http://localhost:8000/approvals/apr-uuid-here/decide \
  -H "X-Actor-Id: manager-001" \
  -H "X-Actor-Roles: manager" \
  -d '{"decision": "approve"}'
```

**Response (422 Unprocessable Entity):**
```json
{
  "code": "INVARIANT_VIOLATION",
  "message": "Invariant violation",
  "violations": ["amount must be >= 0.01"]
}
```

#### Rate Limit (429)

```bash
# After exceeding limit (e.g., 60 req/min)
curl -X POST http://localhost:8000/finance/expenses \
  -H "X-Actor-Id: analyst-001" \
  -H "X-Actor-Roles: analyst" \
  -d '{"amount": 100}'
```

**Response (429 Too Many Requests):**
```json
{
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded"
}
```
