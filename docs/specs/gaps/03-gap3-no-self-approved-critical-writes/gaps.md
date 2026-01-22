# GAP 3 — Eliminar "self-approved" em writes críticos — Análise de Gaps

**Status:** ✅ IMPLEMENTED
**Data:** 2026-01-21
**Implementado em:** 2026-01-21
**Baseado em:** spec.md (contrato), mapeamento do código atual

---

## 1. Mapeamento do Código Atual

### 1.1 Como Approvals Funciona Hoje

#### 1.1.1 Core - Approvals Policy

**Arquivo:** [approvals.py](src/engine/core/approvals.py)

```python
@dataclass
class ApprovalRule:
    """Approval rule definition."""
    rule_name: str        # e.g., "expense.create"
    trigger_api: str      # e.g., "POST /finance/expenses"
    approver_roles: List[str]  # Roles que podem aprovar
    quorum: int = 1       # Número de aprovações necessárias

class ApprovalsPolicy:
    """Approvals policy loaded from approvals.json."""

    def get_rule_for_api(self, api: str) -> Optional[ApprovalRule]:
        """Get approval rule for an API endpoint."""
        return self._api_rules.get(api)
```

**Funções principais:**
- `set_approvals_policy(policy, dept_id)` - Registra policy por dept
- `get_approvals_policy(dept_id)` - Obtém policy para dept
- `emit_approval_requested()` - Registra pedido no ledger
- `emit_approval_decided()` - Registra decisão no ledger
- `find_approval_requested(approval_id)` - Busca evento no ledger
- `can_actor_decide(actor, rule)` - Verifica se ator pode decidir

#### 1.1.2 API - Approvals Endpoint

**Arquivo:** [api/approvals.py](src/engine/api/approvals.py)

Endpoint principal: `POST /approvals/{approval_id}/decide`

```python
@router.post("/{approval_id}/decide")
async def decide_approval(
    approval_id: str,
    body: DecideRequest,  # { decision: "approve"|"reject", reason?: str }
    actor: ActorContext = Depends(get_actor_context),
) -> Dict[str, Any]:
    # 1. Validar decisão
    # 2. Buscar APPROVAL_REQUESTED no ledger
    # 3. Verificar se já decidido
    # 4. Verificar role do ator (can_actor_decide)
    # 5. Verificar SoD
    # 6. Se reject: atualizar estado + emitir eventos
    # 7. Se approve: validar policy/mandate/autonomy gates, invariants, commit
```

#### 1.1.3 Finance - Uso de Approvals

**Arquivo:** [api/finance.py:229-279](src/engine/api/finance.py#L229-L279)

```python
# Check if approval is required for this API
policy = get_approvals_policy(dept_id)
if policy:
    rule = policy.get_rule_for_api(api_trigger)  # "POST /finance/expenses"
    if rule:
        # Generate IDs
        expense_id = generate_expense_id()
        approval_id = generate_approval_id()

        # Save to state store
        state_store.create_expense(expense_id, approval_id, ...)

        # Emit APPROVAL_REQUESTED event
        emit_approval_requested(approval_id, rule, actor, payload_sha256)

        return JSONResponse(
            status_code=202,  # ← PENDING_APPROVAL
            content={
                "status": "pending_approval",
                "expense_id": expense_id,
                "approval_id": approval_id,
            },
        )
```

**Fluxo completo Finance:**
1. Request `POST /finance/expenses` chega
2. RBAC gate verifica permission
3. Policy/Mandate/Autonomy gates (pre-phase)
4. Se `approvals.json` tem rule para `POST /finance/expenses`:
   - Retorna `202 PENDING_APPROVAL` com `approval_id`
   - Nada é criado até approval formal
5. Manager chama `POST /approvals/{approval_id}/decide { decision: "approve" }`
   - Policy/Mandate/Autonomy gates (post-phase)
   - Invariants validated
   - Caso committed

---

### 1.2 Como Legacy Write Funciona Hoje

#### 1.2.1 Registry - Write Flow

**Arquivo:** [write_registry.py](src/engine/legacy_bridge/write_registry.py)

```python
def request_write(
    self,
    action_type: str,
    params: Dict[str, Any],
    actor_id: str,
    actor_roles: Optional[List[str]] = None,
) -> WriteResult:
    """Request a governed write action."""

    # 1. Validate action type
    if action_type not in ACTION_SCHEMAS:
        return WriteResult(error_code=LEGACY_WRITE_ACTION_TYPE_UNKNOWN)

    # 2. Validate params
    validation_errors = validate_action_params(action_type, params)

    # 3. Create action
    action = LegacyWriteAction(
        action_id=action_id,
        action_type=action_type,
        params=params,
        requested_by=actor_id,
        status=ActionStatus.PENDING,
    )

    # 4. Emit LEGACY_WRITE_INTENT_CREATED
    self._emit_ledger_event(LEGACY_WRITE_INTENT_CREATED, ...)

    # 5. Evaluate governance gates
    # 5a. Mandate gate
    mandate_result = evaluate_mandates(...)
    if not mandate_result.allow:
        return self._handle_denial(denied_by="MANDATE")

    # 5b. Autonomy gate
    autonomy_result = evaluate_autonomy(...)
    if autonomy_result.decision != "allow":
        return self._handle_denial(denied_by="AUTONOMY")

    # 5c. Policy gate
    policy_result = evaluate_policies(...)
    if not policy_result.allow:
        return self._handle_denial(denied_by="POLICY")

    # 6. All gates passed - emit LEGACY_WRITE_ALLOWED
    self._emit_ledger_event(
        event_type=LEGACY_WRITE_ALLOWED,
        payload={
            "approved_by": actor_id,  # ← SELF-APPROVED! PROBLEMA!
            "mandate_id": mandate_result.mandate_id,
        },
    )

    # 7. Write to outbox
    outbox_result = self._outbox.write_action(action)

    # 8. Emit LEGACY_WRITE_ENQUEUED
    ...
```

#### 1.2.2 Problema Principal: Self-Approved

**Arquivo:** [write_registry.py:302-314](src/engine/legacy_bridge/write_registry.py#L302-L314)

```python
self._emit_ledger_event(
    event_type=LEGACY_WRITE_ALLOWED,
    action_id=action_id,
    step=f"LEGACY_WRITE:{action_type}",
    payload={
        "action_id": action_id,
        "mandate_id": mandate_result.mandate_id,
        "autonomy_level": autonomy_result.current_level,
        "approved_by": actor_id,  # Self-approved in this MVP ← PROBLEMA
    },
    actor_id=actor_id,
    actor_roles=actor_roles,
)
```

**O que está errado:**
- `approved_by` é setado como o próprio `actor_id` (requester)
- Não há verificação de approval formal
- Não há verificação de role institucional explícita
- O write crítico (`increase_limit`) pode ser executado sem ato formal

#### 1.2.3 Write Models

**Arquivo:** [write_models.py](src/engine/legacy_bridge/write_models.py)

```python
@dataclass
class LegacyWriteAction:
    requested_by: str = ""  # Actor ID who requested
    approved_by: Optional[str] = None  # Actor who approved (if approval flow)
    mandate_id: Optional[str] = None  # Mandate that allowed action
    # ...
```

O campo `approved_by` existe, mas é setado automaticamente como `requested_by`.

---

### 1.3 Comparação: Finance vs Legacy Write

| Aspecto | Finance (expense.create) | Legacy Write (increase_limit) |
|---------|-------------------------|------------------------------|
| Approvals configurado | ✅ Lê approvals.json | ❌ Não consulta |
| Retorna 202 PENDING | ✅ Se rule existe | ❌ Nunca |
| Aguarda decide formal | ✅ POST /approvals/{id}/decide | ❌ Auto-aprova |
| approved_by | Actor que chamou /decide | Requester (self) |
| SoD check | ✅ Em /decide | ❌ Não verifica |

---

## 2. Gaps Identificados

### GAP-3A: Legacy Write não consulta approvals.json

**Prioridade:** ALTA
**Área:** write_registry.py

**O que falta:**
- Chamar `get_approvals_policy(dept_id)` no início de `request_write()`
- Verificar se existe rule para `POST /bridge/write/{action_type}`
- Se existir rule: retornar PENDING_APPROVAL

**Arquivos a modificar:**
```
src/engine/legacy_bridge/write_registry.py
└── request_write():
    - Verificar approvals policy antes dos gates
    - Se rule existe: criar approval request e retornar PENDING
    - Adicionar novo status: ActionStatus.PENDING_APPROVAL
```

**Estimativa:** ~30 linhas

---

### GAP-3B: Sem endpoint para decidir approval de legacy write

**Prioridade:** ALTA
**Área:** API

**O que falta:**
- Ou (A) integrar com `/approvals/{id}/decide` existente
- Ou (B) criar endpoint específico `/bridge/write/{action_id}/decide`

**Opção A (preferida):**
- Usar o mesmo approval subsystem de finance
- Modificar `decide_approval()` para reconhecer legacy write
- Menor duplicação de código

**Opção B (fallback):**
- Criar endpoint separado
- Mais isolamento, mas duplica lógica

**Estimativa:** ~50 linhas (Opção A)

---

### GAP-3C: Sem evento LEGACY_WRITE_APPROVAL_REQUESTED

**Prioridade:** MÉDIA
**Área:** Ledger

**O que falta:**
- Novo evento para correlacionar approval_id ↔ action_id
- Payload deve incluir ambos IDs

**Arquivos a modificar:**
```
src/engine/legacy_bridge/write_registry.py
└── Emitir LEGACY_WRITE_APPROVAL_REQUESTED com:
    - action_id
    - approval_id
    - action_type
    - params_sha256
```

**Estimativa:** ~15 linhas

---

### GAP-3D: Sem status PENDING_APPROVAL em ActionStatus

**Prioridade:** ALTA
**Área:** Models

**O que falta:**
```python
class ActionStatus(str, Enum):
    PENDING = "pending"  # Created but not yet allowed
    PENDING_APPROVAL = "pending_approval"  # ← NOVO
    ENQUEUED = "enqueued"
    ACKED = "acked"
    FAILED = "failed"
    DENIED = "denied"
```

**Arquivos a modificar:**
```
src/engine/legacy_bridge/write_models.py
└── Adicionar PENDING_APPROVAL ao enum
```

**Estimativa:** ~3 linhas

---

### GAP-3E: Sem deny default em produção

**Prioridade:** ALTA
**Área:** Configuração

**Spec requer:**
> em produção (`ENGINE_INSTALL_MODE=prod`): negar deterministicamente (não "auto-approve")

**O que falta:**
- Criar `ENGINE_INSTALL_MODE` env var (dev/prod)
- Em prod, se não houver approvals rule: deny
- Em dev, permitir apenas com role `admin` + mandate válido

**Arquivos a modificar:**
```
src/engine/core/install_mode.py (NOVO)
├── InstallMode enum (DEV, PROD)
└── get_install_mode()

src/engine/legacy_bridge/write_registry.py
└── Em request_write():
    - Se prod + sem rule: deny
    - Se dev + sem rule: verificar role admin + mandate
```

**Estimativa:** ~25 linhas

---

### GAP-3F: approved_by não é verificável

**Prioridade:** ALTA
**Área:** Audit

**O que falta:**
- `approved_by` deve ser setado apenas após ato formal
- Ato formal = decision via approval subsystem
- Não deve ser auto-preenchido

**Arquivos a modificar:**
```
src/engine/legacy_bridge/write_registry.py
└── Remover "approved_by": actor_id do payload LEGACY_WRITE_ALLOWED
```

**Estimativa:** ~5 linhas

---

### GAP-3G: Sem testes para fluxo de approval em legacy write

**Prioridade:** MÉDIA
**Área:** Testes

**O que falta:**
```
tests/test_legacy_write_approval.py (NOVO)
├── test_write_with_approvals_returns_202
├── test_write_decide_approve_creates_outbox
├── test_write_decide_reject_denies
├── test_prod_mode_no_rule_denies
├── test_dev_mode_admin_role_allows
└── test_self_approve_not_possible
```

**Estimativa:** ~100 linhas

---

## 3. Proposta de Patch Mínimo

### Opção A: Integrar com Approvals Subsystem (Preferida)

**Vantagens:**
- Reutiliza código existente (`/approvals/{id}/decide`)
- SoD já implementado
- Consistência com finance flow
- Menos código novo

**Mudanças necessárias:**

| Fase | Arquivo | Mudança |
|------|---------|---------|
| 1 | `write_models.py` | Adicionar `PENDING_APPROVAL`, `approval_id` |
| 2 | `write_registry.py` | Consultar approvals policy antes dos gates |
| 3 | `write_registry.py` | Se rule existe: criar approval request e retornar |
| 4 | `api/approvals.py` | Reconhecer legacy write em `decide_approval()` |
| 5 | `install_mode.py` (novo) | `ENGINE_INSTALL_MODE` config |
| 6 | `write_registry.py` | Deny default em prod sem rule |

### Opção B: Role Explícita Institucional (Fallback)

**Se Opção A for muito invasiva:**
- Criar role `legacy_write.admin`
- Verificar role + mandate válido antes de permitir
- Não usar approval subsystem

**Mudanças necessárias:**

| Fase | Arquivo | Mudança |
|------|---------|---------|
| 1 | `write_registry.py` | Verificar role `legacy_write.admin` |
| 2 | `write_registry.py` | Verificar mandate com authority |
| 3 | `write_registry.py` | Registrar no payload quem aprovou |
| 4 | `install_mode.py` (novo) | `ENGINE_INSTALL_MODE` config |

---

## 4. Fluxo Proposto (Opção A)

### 4.1 Request Write com Approval

```
POST /bridge/write/increase_limit
{
  "customer_id": "cust-123",
  "new_limit": 50000
}

→ write_registry.request_write()
  1. Validar action_type e params
  2. Consultar get_approvals_policy(dept_id)
  3. Se rule existe para "POST /bridge/write/increase_limit":
     a. Criar LegacyWriteAction com status=PENDING_APPROVAL
     b. Gerar approval_id
     c. emit_approval_requested()
     d. Emitir LEGACY_WRITE_APPROVAL_REQUESTED
     e. Retornar WriteResult(pending_approval=True, approval_id=X)
  4. Se não existe rule:
     - Se prod: deny
     - Se dev + admin role + mandate: allow (outbox direto)
     - Se dev sem admin: deny
```

### 4.2 Decide Approval

```
POST /approvals/{approval_id}/decide
{
  "decision": "approve"
}

→ decide_approval()
  1. Buscar APPROVAL_REQUESTED
  2. Detectar se é legacy write (via step ou payload)
  3. Verificar role do ator
  4. Verificar SoD
  5. Se approve:
     a. Buscar action via action_id (correlacionado)
     b. Continuar fluxo de governance gates (mandate/autonomy/policy)
     c. Se all pass: write outbox + emit LEGACY_WRITE_ENQUEUED
     d. Setar approved_by = ator que decidiu
  6. Se reject:
     a. Marcar action como DENIED
     b. emit LEGACY_WRITE_DENIED
```

---

## 5. Configuração de Approvals

### 5.1 Exemplo approvals.json

```json
{
  "version": "1.0.0",
  "name": "approvals",
  "rules": [
    {
      "rule_name": "expense.create",
      "trigger": {
        "api": "POST /finance/expenses"
      },
      "approver_roles": ["manager"],
      "quorum": 1
    },
    {
      "rule_name": "legacy.increase_limit",
      "trigger": {
        "api": "POST /bridge/write/increase_limit"
      },
      "approver_roles": ["credit_manager", "risk_officer"],
      "quorum": 1
    }
  ]
}
```

---

## 6. Eventos de Ledger (Atualizado)

### Sequência com Approval

```
1. LEGACY_WRITE_INTENT_CREATED
   - action_id, action_type, params_sha256, requested_by

2. LEGACY_WRITE_APPROVAL_REQUESTED (NOVO)
   - action_id, approval_id, approver_roles

3. APPROVAL_REQUESTED (existente)
   - approval_id, rule_name, target.api

4. APPROVAL_DECIDED (existente)
   - approval_id, decision, decided_by

5. LEGACY_WRITE_ALLOWED
   - action_id, approved_by (= decided_by, não requester)

6. LEGACY_WRITE_ENQUEUED
   - action_id, outbox_path, outbox_sha256
```

---

## 7. Critérios de Aceite (do spec)

| # | Critério | Como verificar |
|---|----------|----------------|
| 1 | `approved_by` não é auto-preenchido | Inspecionar payload LEGACY_WRITE_ALLOWED |
| 2 | `increase_limit` com approvals → 202 | Request retorna pending_approval |
| 3 | Após decide approve → outbox | Verificar outbox criado |
| 4 | Após decide reject → denied | Verificar status DENIED |
| 5 | Prod sem rule → deny | Request retorna erro |
| 6 | Testes cobrem 3 cenários | pytest tests/test_legacy_write_approval.py |

---

## 8. Estimativa Total

| Componente | Linhas |
|------------|--------|
| write_models.py (enum + field) | ~10 |
| write_registry.py (approval flow) | ~60 |
| api/approvals.py (legacy recognize) | ~40 |
| install_mode.py (novo) | ~25 |
| error codes | ~5 |
| testes | ~100 |
| **Total** | **~240 linhas** |

---

## 9. Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Correlação approval_id ↔ action_id | Armazenar em write_state.json + ledger event |
| State store para legacy write | Usar write_state.json existente (não state_store) |
| Integração com /approvals/decide | Detectar via step name (LEGACY_WRITE:*) |
| Backward compat em dev | `ENGINE_INSTALL_MODE=dev` por default |

---

## 10. Recomendação

**Implementar Opção A** (integração com approvals subsystem):

1. É consistente com o padrão já usado em finance
2. Reutiliza SoD, role checking, e ledger events
3. Menor risco de introduzir bugs
4. Mais fácil de auditar (mesmo caminho para qualquer action crítica)

A integração requer:
- Modificar `write_registry.py` para consultar approvals policy
- Modificar `api/approvals.py` para reconhecer legacy write
- Criar `ENGINE_INSTALL_MODE` para prod vs dev behavior

---

## 11. Implementação Realizada

**Data:** 2026-01-21

### 11.1 Arquivos Criados

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `src/engine/core/install_mode.py` | ~45 | ENGINE_INSTALL_MODE config (dev/prod) |
| `tests/test_legacy_write_approval.py` | ~350 | 16 testes automatizados |

### 11.2 Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/engine/legacy_bridge/write_models.py` | `PENDING_APPROVAL` status, `approval_id` field |
| `src/engine/legacy_bridge/write_registry.py` | Approval flow integration, `complete_approved_action()`, `reject_action()`, `get_action_by_approval_id()` |
| `src/engine/api/approvals.py` | `_handle_legacy_write_decision()`, detecção de legacy write approvals |
| `src/engine/core/errors.py` | 4 novos códigos de erro (`LEGACY_WRITE_APPROVAL_REQUIRED`, etc.) |
| `tests/test_legacy_bridge_write.py` | Updated to require admin role in dev mode |

### 11.3 Funcionalidades Implementadas

✅ **GAP-3A: Legacy Write consulta approvals.json**
- `request_write()` consulta `get_approvals_policy(dept_id)`
- Se rule existe para endpoint: retorna `PENDING_APPROVAL`
- Evento `LEGACY_WRITE_APPROVAL_REQUESTED` emitido

✅ **GAP-3B: Integração com /approvals/{id}/decide**
- `_handle_legacy_write_decision()` detecta legacy write approvals
- Chama `complete_approved_action()` ou `reject_action()`
- `approved_by` é setado como o actor que decidiu (não requester)

✅ **GAP-3C: Evento LEGACY_WRITE_APPROVAL_REQUESTED**
- Correlaciona `action_id` ↔ `approval_id`
- Payload inclui `approver_roles`, `params_sha256`

✅ **GAP-3D: Status PENDING_APPROVAL**
- `ActionStatus.PENDING_APPROVAL` adicionado ao enum
- `approval_id` field adicionado ao model

✅ **GAP-3E: ENGINE_INSTALL_MODE**
- Env var `ENGINE_INSTALL_MODE` (dev/prod)
- Default: `dev` (compatibilidade)
- Prod mode: deny sem approval rule (determinístico)
- Dev mode: allow apenas com role `admin` + mandate

✅ **GAP-3F: approved_by verificável**
- `approved_by` NUNCA é setado como requester
- Em approval flow: setado como o actor que decidiu
- Em dev admin bypass: permanece `None`, ledger registra `approval_mode: "dev_admin_bypass"`

✅ **GAP-3G: Testes automatizados**
- 16 testes cobrindo todos os critérios de aceite
- Cobertura: approval flow, prod mode, dev mode, no self-approved

### 11.4 Resultados dos Testes

```
$ python -m pytest tests/test_legacy_write_approval.py -v
============================== 16 passed in 2.09s ==============================

$ python -m pytest tests/test_legacy_bridge_write.py -v
============================== 28 passed in 0.46s ==============================
```

### 11.5 Critérios de Aceite Verificados

| # | Critério | Status | Teste |
|---|----------|--------|-------|
| 1 | `approved_by` não é auto-preenchido | ✅ | `test_approval_flow_approved_by_is_different` |
| 2 | `increase_limit` com approvals → 202 | ✅ | `test_write_with_approval_rule_returns_pending` |
| 3 | Após decide approve → outbox | ✅ | `test_approve_action_creates_outbox` |
| 4 | Após decide reject → denied | ✅ | `test_reject_action_marks_denied` |
| 5 | Prod sem rule → deny | ✅ | `test_prod_mode_no_rule_denies` |
| 6 | Dev sem admin → deny | ✅ | `test_dev_mode_no_rule_no_admin_denied` |
| 7 | Dev com admin → allow | ✅ | `test_dev_mode_no_rule_admin_allowed` |

### 11.6 Fluxo Implementado

**Com approval rule:**
```
1. POST /bridge/write/increase_limit
   → LEGACY_WRITE_INTENT_CREATED
   → LEGACY_WRITE_APPROVAL_REQUESTED
   → APPROVAL_REQUESTED
   → Returns: { pending_approval: true, approval_id: "..." }

2. POST /approvals/{approval_id}/decide { decision: "approve" }
   → APPROVAL_DECIDED
   → LEGACY_WRITE_ALLOWED { approved_by: "approver-id", approval_mode: "formal_approval" }
   → LEGACY_WRITE_ENQUEUED
   → Returns: { action_status: "enqueued", outbox_path: "..." }
```

**Sem approval rule (prod):**
```
1. POST /bridge/write/increase_limit
   → LEGACY_WRITE_INTENT_CREATED
   → LEGACY_WRITE_DENIED { denied_by: "NO_APPROVAL_RULE" }
   → Returns: { error_code: "LEGACY_WRITE_NO_APPROVAL_RULE_PROD" }
```

**Sem approval rule (dev + admin):**
```
1. POST /bridge/write/increase_limit (with admin role)
   → LEGACY_WRITE_INTENT_CREATED
   → LEGACY_WRITE_ALLOWED { approval_mode: "dev_admin_bypass", admin_actor_id: "..." }
   → LEGACY_WRITE_ENQUEUED
   → Returns: { success: true, outbox_path: "..." }
```

### 11.7 Notas de Implementação

1. **Detecção de legacy write approval:** Via `rule_name.startswith("legacy.")` ou `"bridge/write" in rule_name`
2. **Correlação:** `get_action_by_approval_id()` busca action pelo `approval_id`
3. **approved_by garantido diferente:** Fluxo de approval garante que `approved_by != requested_by`
4. **Backward compat:** `ENGINE_INSTALL_MODE=dev` por default, testes existentes atualizados com role `admin`
5. **Outbox unchanged:** Continua sendo o único ponto de escrita para sistemas legados
