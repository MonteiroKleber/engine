# Gates Matrix — Finance Department

**Data:** 2026-01-18
**Versao:** 1.0
**Etapa:** 04 — Runtime Gates

---

## 1. Visao Geral

Este documento mapeia os endpoints mutaveis do departamento Finance e seus gates de enforcement no runtime do Libervia Engine.

---

## 2. Endpoints Mutaveis

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/finance/expenses` | POST | Criar despesa |
| `/d/{dept}/finance/expenses` | POST | Criar despesa (multi-mode) |
| `/approvals/{approval_id}/decide` | POST | Decidir aprovacao (aprovar/rejeitar) |

---

## 3. Ordem de Enforcement dos Gates

### 3.1 POST /finance/expenses (Criar Despesa)

```
CAMADA MIDDLEWARE (primeiro):
  1. security_headers_middleware
  2. body_size_middleware
  3. rate_limit_middleware
  4. legacy_routes_middleware (multi-mode)
  5. freeze_emergency_stop_middleware
     +-- Emergency Stop (se habilitado && endpoint bloqueado) -> 503
     +-- Freeze (se freeze_mode && metodo mutavel) -> 423
  6. ege_drift_middleware (se drift ACTIVE && ege_enforce_drift) -> 409
  7. dept_routing_middleware
  |
  v
CAMADA HANDLER: create_expense_handler()
  8. RBAC gate -> gate_rbac("expense.create") -> 403 se negado
  9. Policy PRE gate -> evaluate_policies(phase="pre") -> 403 se violado
  10. Mandate PRE gate -> evaluate_mandates(phase="pre") -> 403 se violado
  11. Autonomy PRE gate -> evaluate_autonomy(phase="pre") -> 403 se negado
  12. Approvals gate -> verifica se aprovacao necessaria
      +-- Se necessario: cria approval, emite APPROVAL_REQUESTED -> 202
      +-- Se nao: retorna criado -> 200
```

**Evidencia:** [finance.py](../../../../src/engine/api/finance.py), [server.py](../../../../src/engine/api/server.py)

### 3.2 POST /approvals/{approval_id}/decide (Decidir Aprovacao)

```
CAMADA MIDDLEWARE (primeiro):
  1-7. [Mesmo que acima]
  |
  v
CAMADA HANDLER: decide_approval()
  8. Can-decide gate -> can_actor_decide() -> 403 se negado
  9. SoD gate -> check_sod() -> 409 se violacao / 500 se regra invalida
  |
  v
  SE decisao == "reject":
    10. Atualiza status para REJECTED
    11. Emite APPROVAL_DECIDED, CASE_REJECTED
    -> 200 sucesso
  |
  v
  SE decisao == "approve":
    10. Policy POST gate -> evaluate_policies(phase="post") -> 403 se violado
    11. Mandate POST gate -> evaluate_mandates(phase="post") -> 403 se violado
    12. Autonomy POST gate -> evaluate_autonomy(phase="post") -> 403 se negado
    13. Invariants gate -> validate_expense_invariants() -> 422 se violado
    14. Atualiza status para COMMITTED
    15. Emite APPROVAL_DECIDED, CASE_COMMITTED
    -> 200 sucesso
```

**Evidencia:** [approvals.py](../../../../src/engine/api/approvals.py)

---

## 4. Matriz de Gates por Endpoint

| Gate | POST /finance/expenses | POST /approvals/.../decide |
|------|------------------------|---------------------------|
| Freeze | Middleware (5) | Middleware (5) |
| Emergency Stop | Middleware (5) | Middleware (5) |
| EGE Drift | Middleware (6) | Middleware (6) |
| RBAC | Handler (8) | Indireto via can_decide |
| Policy PRE | Handler (9) | - |
| Mandate PRE | Handler (10) | - |
| Autonomy PRE | Handler (11) | - |
| Approvals | Handler (12) | - |
| Can-decide | - | Handler (8) |
| SoD | - | Handler (9) |
| Policy POST | - | Handler (10) se approve |
| Mandate POST | - | Handler (11) se approve |
| Autonomy POST | - | Handler (12) se approve |
| Invariants | - | Handler (13) se approve |

---

## 5. Comportamento Default dos Gates

### 5.1 Tabela de Defaults (Semantica Canonica Implementada)

| Gate | Contrato Ausente | Regra NAO Aplicavel | Default | **Status** |
|------|------------------|---------------------|---------|------------|
| **RBAC** | DENY | N/A | DENY | OK - Fail-secure |
| **Policy** | allow | allow | ALLOW | Medio |
| **Mandate** | allow | **DENY** | DENY | **RESOLVIDO** |
| **Autonomy** | allow | **DENY** | DENY | **RESOLVIDO** |
| **SoD** | allow | allow | ALLOW | Baixo |
| **Invariants** | allow | N/A | ALLOW | Medio |
| **Freeze** | - | N/A | DENY se ativo | OK |
| **Emergency Stop** | - | N/A | DENY se ativo | OK |
| **EGE Drift** | - | N/A | DENY se ativo | OK |

### 5.2 Mandate: Semantica Canonica (RESOLVIDO)

**Localizacao:** [mandates.py:689-703](../../../../src/engine/core/mandates.py)

```python
# Em evaluate_mandates():
# No matching mandate found - DENY per canonical semantics
# "Nenhuma execução fora de mandato" - no execution outside of mandate
return MandateEvalResult(
    allow=False,
    mandate_id=None,
    violations=[
        MandateViolation(
            mandate_id=None,
            code=MANDATE_DENIED,
            rule_type=None,
            field_path=None,
            message=f"No mandate applicable for ({endpoint_sig}, {phase})",
        )
    ],
)
```

**Comportamento:**
- `mandates.json` ausente → allow (sem contrato = allow)
- `mandates.json` existe, mandate aplica → avalia regras do mandate
- `mandates.json` existe, nenhum mandate aplica → **DENY (MANDATE_DENIED)**

### 5.3 Autonomy: Semantica Canonica (RESOLVIDO)

**Localizacao:** [autonomy.py:349-357](../../../../src/engine/core/autonomy.py)

```python
# Em evaluate_autonomy():
# No matching rule - DENY per canonical semantics
# If autonomy.json exists but no rule matches → deny (AUTONOMY_INSUFFICIENT)
return AutonomyEvalResult(
    decision="deny",
    current_level=current_level,
    required_level=MAX_LEVEL + 1,  # Impossible to satisfy
    rule_id=None,
    reason=f"No autonomy rule applicable for ({endpoint_sig}, {phase})",
)
```

**Comportamento:**
- `autonomy.json` ausente → allow (sem contrato = allow)
- `autonomy.json` existe, rule aplica → avalia current_level >= required_level
- `autonomy.json` existe, nenhum rule aplica → **DENY (AUTONOMY_INSUFFICIENT)**

---

## 6. Eventos no Ledger

### 6.1 Eventos por Gate

| Gate | Evento Allow | Evento Deny |
|------|-------------|-------------|
| RBAC | `RBAC_DECISION` (decision="allow") | `RBAC_DECISION` (decision="deny") |
| Policy PRE | `POLICY_PRE_DECISION` (allow=true) | `POLICY_PRE_DECISION` (allow=false) |
| Policy POST | `POLICY_POST_DECISION` (allow=true) | `POLICY_POST_DECISION` (allow=false) |
| Mandate | `MANDATE_EVALUATED` (allow=true) | `MANDATE_EVALUATED` (allow=false) |
| Autonomy | `AUTONOMY_EVALUATED` (decision="allow") | `AUTONOMY_EVALUATED` (decision="deny") |
| SoD | - | `SOD_VIOLATION` |
| Invariants | - | `INVARIANT_VIOLATED` |
| Freeze | - | `INSTITUTION_FREEZE_BLOCKED` |
| Emergency Stop | - | `INSTITUTION_EMERGENCY_STOP_BLOCKED` |
| EGE Drift | - | `EGE_DRIFT_BLOCKED` |
| Approvals | `APPROVAL_REQUESTED` | - |
| Approval Decision | `APPROVAL_DECIDED`, `CASE_COMMITTED` | `APPROVAL_DECIDED`, `CASE_REJECTED` |

### 6.2 Campos Comuns em Eventos

Todos os eventos incluem:
- `event_type` - tipo do evento
- `tenant_id` - do contexto do actor
- `actor_id` - do contexto do actor
- `actor_roles` - do contexto do actor
- `case_id` - expense_id ou approval_id
- `step` - nome padronizado (ex: `POLICY_GATE:pre:POST /finance/expenses`)
- `payload` - detalhes da decisao

---

## 7. Resumo de GAPs

| # | GAP | Severidade | Status | Resolucao |
|---|-----|------------|--------|-----------|
| 1 | Mandate allow-by-default quando regra nao aplicavel | **CRITICO** | **RESOLVIDO** | Implementada semantica canonica em mandates.py |
| 2 | Autonomy allow-by-default quando regra nao aplicavel | **CRITICO** | **RESOLVIDO** | Implementada semantica canonica em autonomy.py |
| 3 | Invariants checados apenas no commit de aprovacao | Medio | Aberto | Por design - validacao ocorre no commit |
| 4 | Freeze/EGE apenas em middleware (handler nao verifica) | Baixo | Aberto | Middleware suficiente para rotas padrao |

---

## 8. Fluxo Completo: Finance End-to-End

```
Employee -> POST /finance/expenses
  |
  +-- [Middleware: Freeze/EmergencyStop/Drift] -> 423/503/409 se bloqueado
  +-- [RBAC: expense.create] -> 403 se sem permissao
  +-- [Policy PRE] -> 403 se policy violada
  +-- [Mandate PRE] -> 403 se mandate violado OU nao ha mandate aplicavel
  +-- [Autonomy PRE] -> 403 se autonomia insuficiente OU nao ha rule aplicavel
  +-- [Approvals: regra matched?]
      +-- SIM: cria approval (status=PENDING), emite APPROVAL_REQUESTED -> 202
      +-- NAO: cria expense diretamente -> 200
  |
  v (se approval necessario)
Manager -> POST /approvals/{id}/decide
  |
  +-- [Middleware: Freeze/EmergencyStop/Drift] -> 423/503/409 se bloqueado
  +-- [Can-decide: manager tem role?] -> 403 se nao
  +-- [SoD: requester != decider?] -> 409 se violacao
  |
  +-- SE REJECT:
  |     +-- Atualiza status para REJECTED
  |     +-- Emite APPROVAL_DECIDED, CASE_REJECTED
  |     -> 200
  |
  +-- SE APPROVE:
      +-- [Policy POST] -> 403 se policy violada
      +-- [Mandate POST] -> 403 se mandate violado OU nao ha mandate aplicavel
      +-- [Autonomy POST] -> 403 se autonomia insuficiente OU nao ha rule aplicavel
      +-- [Invariants: schema valido?] -> 422 se invalido
      +-- Atualiza status para COMMITTED
      +-- Emite APPROVAL_DECIDED, CASE_COMMITTED
      -> 200
```

---

## 9. Referencias

- [spec.md](spec.md) - Especificacao da Etapa 04
- [errors.md](errors.md) - Codigos de erro por gate
- [finance.py](../../../../src/engine/api/finance.py) - Handler de despesas
- [approvals.py](../../../../src/engine/api/approvals.py) - Handler de aprovacoes
- [mandates.py](../../../../src/engine/core/mandates.py) - Avaliacao de mandatos
- [autonomy.py](../../../../src/engine/core/autonomy.py) - Avaliacao de autonomia
- [policy.py](../../../../src/engine/core/policy.py) - Avaliacao de policies

---

**Status:** ESPECIFICACAO ATIVA (GAPs criticos RESOLVIDOS)
**Data:** 2026-01-18
**Atualizado:** 2026-01-18 - Implementacao da semantica canonica para Mandate e Autonomy

---

## 10. Bundle Default: finance-pilot

O bundle default `bundles/finance-pilot/` foi atualizado para funcionar com a semantica canonica:

### 10.1 Contratos Institucionais Minimos

| Contrato | Conteudo | Justificativa |
|----------|----------|---------------|
| `rbac.json` | Roles: admin, manager, analyst, viewer | Manager adicionado para approvals |
| `mandates.json` | 2 mandates (expense create + approval decide) | Cobre endpoints do piloto |
| `autonomy.json` | 2 rules (expense create + approval decide), L0 | Cobre endpoints do piloto |
| `policies.json` | Vazio (policies: []) | Sem policies no MVP |

### 10.2 Mandates do Piloto

```json
{
  "mandate_id": "expense-create-pre",
  "endpoint_sig": "POST /finance/expenses",
  "phase": "pre",
  "allowed_roles": ["analyst", "admin"],
  "limits": [{"rule_type": "numeric_max", "field_path": "amount", "value": 100000}]
},
{
  "mandate_id": "approval-decide-post",
  "endpoint_sig": "POST /approvals/{approval_id}/decide",
  "phase": "post",
  "allowed_roles": ["manager", "admin"]
}
```

### 10.3 Autonomy do Piloto

```json
{
  "current_level": 0,
  "rules": [
    {"rule_id": "expense-create-pre", "endpoint_sig": "POST /finance/expenses", "phase": "pre", "required_level": 0},
    {"rule_id": "approval-decide-post", "endpoint_sig": "POST /approvals/{approval_id}/decide", "phase": "post", "required_level": 0}
  ]
}
```

### 10.4 Fluxo Permitido no Piloto

1. **analyst** ou **admin** → POST /finance/expenses (ate 100.000) → 202 + approval
2. **manager** ou **admin** → POST /approvals/{id}/decide → 200 (COMMITTED/REJECTED)
