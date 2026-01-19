# Finance Contract Specification

**Data:** 2026-01-18
**Versao:** 1.0
**Etapa:** 05 — Finance Template "Golden"

---

## 1. Visao Geral

Este documento define as entidades, invariants, approvals, SoD e politicas minimas para o departamento Finance do Libervia Engine MVP.

O Finance e o **primeiro departamento canonico** e serve como referencia ("golden") para outros departamentos.

---

## 2. Entidades

### 2.1 Expense (Despesa)

| Campo | Tipo | Obrigatorio | Restricoes |
|-------|------|-------------|------------|
| `expense_id` | string (UUID) | Sim | Gerado pelo sistema |
| `tenant_id` | string | Sim | Do contexto do actor |
| `amount` | number | Sim | min: 0.01, max: 1.000.000.000 |
| `description` | string | Nao | max_len: 280 |
| `requester_id` | string | Sim | Actor que criou a despesa |
| `status` | enum | Sim | PENDING, COMMITTED, REJECTED |
| `created_at` | datetime | Sim | Timestamp de criacao |
| `updated_at` | datetime | Sim | Timestamp de atualizacao |

### 2.2 Approval (Aprovacao)

| Campo | Tipo | Obrigatorio | Restricoes |
|-------|------|-------------|------------|
| `approval_id` | string (UUID) | Sim | Gerado pelo sistema |
| `case_id` | string (UUID) | Sim | ID da despesa associada |
| `requester_id` | string | Sim | Actor que solicitou aprovacao |
| `approver_id` | string | Nao | Actor que decidiu (se decidido) |
| `status` | enum | Sim | PENDING, APPROVED, REJECTED |
| `decision` | enum | Nao | approve, reject |
| `comment` | string | Nao | Comentario da decisao |
| `created_at` | datetime | Sim | Timestamp de criacao |
| `decided_at` | datetime | Nao | Timestamp da decisao |

---

## 3. Invariants (Regras de Negocio)

### 3.1 Invariants de Expense

| Invariant | Campo | Regra | Codigo Erro |
|-----------|-------|-------|-------------|
| `expense.amount.min` | amount | >= 0.01 | 422 INVARIANT_VIOLATED |
| `expense.amount.max` | amount | <= 1.000.000.000 | 422 INVARIANT_VIOLATED |
| `expense.description.max_len` | description | len <= 280 | 422 INVARIANT_VIOLATED |

### 3.2 Validacao

Os invariants sao verificados no momento do **commit** da aprovacao (fase POST do `decide`).

```
POST /approvals/{approval_id}/decide (decision=approve)
  -> Invariants gate -> validate_expense_invariants()
  -> 422 se violado
```

---

## 4. Approvals (Regras de Aprovacao)

### 4.1 Regra: expense.create

| Propriedade | Valor |
|-------------|-------|
| **Trigger** | `POST /finance/expenses` |
| **Approver Roles** | manager |
| **Quorum** | 1 |

**Comportamento:**
- Toda despesa criada requer aprovacao de pelo menos 1 manager
- Apos criacao, emite evento `APPROVAL_REQUESTED` e retorna 202
- Despesa fica com status `PENDING` ate decisao

### 4.2 Fluxo de Aprovacao

```
1. analyst/admin -> POST /finance/expenses
   -> Cria expense (status=PENDING)
   -> Cria approval (status=PENDING)
   -> Emite APPROVAL_REQUESTED
   -> Retorna 202

2. manager/admin -> POST /approvals/{id}/decide
   -> Verifica can_decide (role manager/admin)
   -> Verifica SoD (requester != decider)

   SE decision=reject:
     -> Atualiza expense.status = REJECTED
     -> Atualiza approval.status = REJECTED
     -> Emite APPROVAL_DECIDED, CASE_REJECTED
     -> Retorna 200

   SE decision=approve:
     -> Avalia gates POST (Policy, Mandate, Autonomy)
     -> Valida Invariants
     -> Atualiza expense.status = COMMITTED
     -> Atualiza approval.status = APPROVED
     -> Emite APPROVAL_DECIDED, CASE_COMMITTED
     -> Retorna 200
```

---

## 5. Separation of Duties (SoD)

### 5.1 Regra: expense.create.requester_not_approver

| Propriedade | Valor |
|-------------|-------|
| **Case Step** | `APPROVAL:expense.create` |
| **Constraint** | `REQUESTER_NEQ_DECIDER` |
| **Codigo Erro** | 409 SOD_VIOLATION |

**Comportamento:**
- O actor que criou a despesa **nao pode** aprovar/rejeitar a mesma despesa
- Violacao retorna 409 com codigo `SOD_VIOLATION`

**Exemplo:**
```
analyst-1 -> POST /finance/expenses (cria despesa D1)
analyst-1 -> POST /approvals/{D1}/decide -> 409 SOD_VIOLATION
manager-2 -> POST /approvals/{D1}/decide -> 200 OK
```

---

## 6. RBAC (Controle de Acesso)

### 6.1 Roles

| Role | Permissoes |
|------|------------|
| **admin** | expense.create, expense.read, expense.delete, expense.approve, approval.decide |
| **manager** | expense.read, expense.approve, approval.decide |
| **analyst** | expense.create, expense.read |
| **viewer** | expense.read |

### 6.2 Mapeamento Endpoint -> Permissao

| Endpoint | Metodo | Permissao Requerida |
|----------|--------|---------------------|
| `/finance/expenses` | POST | expense.create |
| `/finance/expenses` | GET | expense.read |
| `/finance/expenses/{id}` | GET | expense.read |
| `/finance/expenses/{id}` | DELETE | expense.delete |
| `/approvals/{id}/decide` | POST | approval.decide |

---

## 7. Mandates (Autorizacoes Explicitas)

### 7.1 Mandate: expense-create-pre

| Propriedade | Valor |
|-------------|-------|
| **Endpoint** | `POST /finance/expenses` |
| **Phase** | pre |
| **Allowed Roles** | analyst, admin |
| **Limits** | amount <= 100.000 (piloto) |

### 7.2 Mandate: approval-decide-post

| Propriedade | Valor |
|-------------|-------|
| **Endpoint** | `POST /approvals/{approval_id}/decide` |
| **Phase** | post |
| **Allowed Roles** | manager, admin |

### 7.3 Semantica Canonica

- **Mandate existe e aplica:** Avalia regras do mandate
- **Mandate existe, nao aplica:** DENY (MANDATE_DENIED)
- **Arquivo mandates.json ausente:** allow (sem contrato = allow)

---

## 8. Autonomy (Niveis de Autonomia)

### 8.1 Nivel Atual: L0

L0 = Full Human Oversight (supervisao humana completa)

### 8.2 Rules

| Rule | Endpoint | Phase | Required Level |
|------|----------|-------|----------------|
| expense-create-pre | POST /finance/expenses | pre | 0 |
| approval-decide-post | POST /approvals/{approval_id}/decide | post | 0 |

### 8.3 Semantica Canonica

- **Rule existe e aplica:** Avalia current_level >= required_level
- **Rule existe, nao aplica:** DENY (AUTONOMY_INSUFFICIENT)
- **Arquivo autonomy.json ausente:** allow (sem contrato = allow)

---

## 9. Policies (Politicas Dinamicas)

### 9.1 Status no Piloto

O piloto nao inclui policies ativas (`policies: []`).

Policies podem ser adicionadas posteriormente para regras dinamicas como:
- Limite de valor por tenant
- Restricoes temporais
- Regras de categoria

### 9.2 Semantica

- **Policy existe e aplica:** Avalia condicoes da policy
- **Policy nao aplica:** allow (default)

---

## 10. Eventos no Ledger

### 10.1 Eventos de Caso (Finance)

| Evento | Quando | Payload |
|--------|--------|---------|
| `EXPENSE_CREATED` | Despesa criada | expense_id, amount, requester_id |
| `APPROVAL_REQUESTED` | Aprovacao solicitada | approval_id, case_id, rule_name |
| `APPROVAL_DECIDED` | Decisao tomada | approval_id, decision, decider_id |
| `CASE_COMMITTED` | Despesa aprovada | expense_id |
| `CASE_REJECTED` | Despesa rejeitada | expense_id |

### 10.2 Eventos de Gate

| Gate | Evento Allow | Evento Deny |
|------|-------------|-------------|
| RBAC | RBAC_DECISION (allow) | RBAC_DECISION (deny) |
| Policy | POLICY_*_DECISION (allow) | POLICY_*_DECISION (deny) |
| Mandate | MANDATE_EVALUATED (allow) | MANDATE_EVALUATED (deny) |
| Autonomy | AUTONOMY_EVALUATED (allow) | AUTONOMY_EVALUATED (deny) |
| SoD | - | SOD_VIOLATION |
| Invariants | - | INVARIANT_VIOLATED |

---

## 11. Codigos de Erro

| Codigo HTTP | Codigo Interno | Gate | Descricao |
|-------------|----------------|------|-----------|
| 403 | RBAC_DENIED | RBAC | Sem permissao para operacao |
| 403 | POLICY_VIOLATED | Policy | Policy PRE/POST violada |
| 403 | MANDATE_DENIED | Mandate | Nenhum mandate aplicavel |
| 403 | MANDATE_VIOLATED | Mandate | Limite de mandate violado |
| 403 | AUTONOMY_INSUFFICIENT | Autonomy | Nivel de autonomia insuficiente |
| 409 | SOD_VIOLATION | SoD | Segregacao de funcoes violada |
| 422 | INVARIANT_VIOLATED | Invariants | Regra de negocio violada |
| 423 | INSTITUTION_FREEZE | Freeze | Instituicao em modo freeze |
| 503 | INSTITUTION_EMERGENCY_STOP | Emergency | Instituicao em emergency stop |

---

## 12. Referencias

- [spec.md](spec.md) - Especificacao da Etapa 05
- [gates-matrix.md](../04-runtime-gates/gates-matrix.md) - Matriz de Gates
- [errors.md](../04-runtime-gates/errors.md) - Codigos de erro detalhados
- [finance-bundle.md](finance-bundle.md) - Composicao do bundle

---

**Status:** ESPECIFICACAO ATIVA
**Data:** 2026-01-18
