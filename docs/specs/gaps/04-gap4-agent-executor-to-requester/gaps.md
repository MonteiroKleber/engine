# GAP 4 — Diagnóstico: Agentes IA como atores governados

## 1. Mapeamento: Onde actor_id/roles entram nos requests e ledger

### 1.1 Entry Points para ActorContext

**Arquivo: [dependencies.py](src/engine/api/dependencies.py)**

A função `get_actor_context()` (linhas 64-118) é o ponto de entrada para todos os requests:

```python
async def get_actor_context(
    request: Request,
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
    x_actor_roles: Optional[str] = Header(None, alias="X-Actor-Roles"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
    x_actor_token: Optional[str] = Header(None, alias="X-Actor-Token"),
    x_institution_id: Optional[str] = Header(None, alias="X-Institution-Id"),
) -> ActorContext
```

**Modos de autenticação:**
- **Dev mode (ENGINE_AUTH_MODE=dev):** Aceita headers livres (`X-Actor-Id`, `X-Actor-Roles`)
- **Strict mode (ENGINE_AUTH_MODE=strict):** Requer `X-Actor-Token`, resolve de registry

**Arquivo: [actor_context.py](src/engine/core/actor_context.py)**

```python
@dataclass
class ActorContext:
    actor_id: str
    roles: List[str] = field(default_factory=list)
    tenant_id: str = DEFAULT_TENANT_ID
    identity_verified: bool = False  # True se resolvido do registry
```

### 1.2 Como actor_id/roles chegam ao Ledger

**Arquivo: [ledger.py](src/engine/core/ledger.py:229-296)**

Toda emissão de evento passa pelo método `append()`:

```python
def append(
    self,
    event_type: str,
    tenant_id: str,
    actor_id: str,
    actor_roles: List[str],
    case_id: str,
    step: str,
    payload: Optional[Dict[str, Any]] = None,
    dept_id: Optional[str] = None,
) -> Optional[LedgerEvent]
```

O LedgerEvent armazena actor em formato canônico (linhas 61-84):

```python
def to_canonical_dict(self) -> Dict[str, Any]:
    result = {
        ...
        "actor": {
            "id": self.actor_id,
            "roles": sorted(self.actor_roles),
        },
    }
```

### 1.3 Pontos que emitem eventos com actor_id

| Componente | Arquivo | Método | actor_id source |
|------------|---------|--------|-----------------|
| Legacy Write | write_registry.py:156-176 | `_emit_ledger_event()` | parâmetro `actor_id` |
| Approvals | api/approvals.py | `emit_approval_decided()` | `actor.actor_id` |
| Finance | api/finance.py | vários | `actor.actor_id` |
| RBAC | core/rbac.py | `emit_rbac_decision()` | `actor.actor_id` |
| Mandates | core/mandates.py | `emit_mandate_decision()` | `actor.actor_id` |
| Policy | core/policy.py | `emit_policy_decision()` | `actor.actor_id` |
| Autonomy | core/autonomy.py | `emit_autonomy_evaluated()` | `actor.actor_id` |

**Observação crítica:** Nenhum destes pontos suporta `on_behalf_of`. O actor_id é sempre o chamador direto.

---

## 2. Mapeamento: Como Agent Ops faz query de denied

### 2.1 Read Model para Denied Events

**Arquivo: [agent_ops/read_model.py](src/engine/agent_ops/read_model.py)**

A função `is_denied_event()` (linhas 28-64) detecta negações:

```python
def is_denied_event(event: LedgerEvent) -> bool:
    event_type = event.event_type

    # SOD_VIOLATION é sempre negação
    if event_type == "SOD_VIOLATION":
        return True

    # Eventos com campo payload.allowed
    decision_types = {
        "RBAC_DECISION",
        "POLICY_PRE_DECISION",
        "POLICY_POST_DECISION",
        "MANDATE_EVALUATED",
        "AUTONOMY_EVALUATED",
    }

    if event_type in decision_types:
        return event.payload.get("allowed") is False
```

### 2.2 Lista de Denied por Actor

**Arquivo: [agent_ops/read_model.py:119-180](src/engine/agent_ops/read_model.py)**

```python
def list_denied_events(
    institution_id: str,
    gate: Optional[str] = None,
    dept_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    limit: int = 100,
) -> List[LedgerEvent]
```

Filtros disponíveis:
- `gate`: rbac, policy, mandate, autonomy, sod
- `actor_id`: filtra por actor específico
- `dept_id`: isolamento por departamento

### 2.3 Console Route para Denied

**Arquivo: [console/routes.py:4557-4653](src/engine/console/routes.py)**

```python
@router.get("/denied", response_class=HTMLResponse)
async def console_denied(
    request: Request,
    institution_id: str,
    dept_id: Optional[str],
    gate: Optional[str],
    actor_id: Optional[str],
    ...
) -> HTMLResponse
```

**Observação:** A query de denied NÃO suporta filtro por `on_behalf_of`. Se um agente faz request em nome de outro actor, a negação fica registrada no actor_id do agente, não do delegante.

---

## 3. Mapeamento: Onde legacy write faz deny/allow

### 3.1 Flow de Governance no Legacy Write

**Arquivo: [legacy_bridge/write_registry.py](src/engine/legacy_bridge/write_registry.py)**

O método `request_write()` (linhas 189-417) implementa o flow:

```
1. Validação (tipo, params)
   ↓
2. LEGACY_WRITE_INTENT_CREATED → ledger
   ↓
3. Check approval policy
   ├─ Se rule existe → PENDING_APPROVAL (retorna)
   ├─ Se prod mode + sem rule → DENY (NO_APPROVAL_RULE_PROD)
   └─ Se dev mode + sem rule → requer admin role
   ↓
4. Mandate gate → evaluate_mandates()
   ├─ DENY (MANDATE) ou
   └─ continue
   ↓
5. Autonomy gate → evaluate_autonomy()
   ├─ DENY (AUTONOMY) ou
   └─ continue
   ↓
6. Policy gate → evaluate_policies()
   ├─ DENY (POLICY) ou
   └─ continue
   ↓
7. LEGACY_WRITE_ALLOWED → ledger
   ↓
8. Write outbox
   ↓
9. LEGACY_WRITE_ENQUEUED → ledger
```

### 3.2 Pontos de Deny

**Método: `_handle_denial()` (linhas 716-776)**

```python
def _handle_denial(
    self,
    action: LegacyWriteAction,
    denied_by: str,  # MANDATE | AUTONOMY | POLICY | NO_APPROVAL_RULE | etc
    reason: str,
    actor_id: str,
    actor_roles: Optional[List[str]],
    error_code: Optional[str] = None,
) -> WriteResult
```

Emite evento `LEGACY_WRITE_DENIED`:

```python
self._emit_ledger_event(
    event_type=LEGACY_WRITE_DENIED,
    action_id=action.action_id,
    step=f"LEGACY_WRITE:{action.action_type}",
    payload={
        "action_id": action.action_id,
        "denied_by": denied_by,
        "reason": reason,
    },
    actor_id=actor_id,
    actor_roles=actor_roles,
)
```

### 3.3 Pontos de Allow

**Dev mode admin bypass (linhas 360-380):**

```python
self._emit_ledger_event(
    event_type=LEGACY_WRITE_ALLOWED,
    action_id=action_id,
    step=f"LEGACY_WRITE:{action_type}",
    payload={
        "action_id": action_id,
        "mandate_id": mandate_result.mandate_id,
        "autonomy_level": autonomy_result.current_level,
        "approval_mode": "dev_admin_bypass",  # GAP 3
        "admin_actor_id": actor_id,
    },
    actor_id=actor_id,
    actor_roles=actor_roles,
)
```

**Formal approval (linhas 602-617):**

```python
self._emit_ledger_event(
    event_type=LEGACY_WRITE_ALLOWED,
    action_id=action.action_id,
    step=f"LEGACY_WRITE:{action.action_type}",
    payload={
        "action_id": action.action_id,
        "mandate_id": mandate_result.mandate_id,
        "autonomy_level": autonomy_result.current_level,
        "approval_mode": "formal_approval",  # GAP 3
        "approved_by": approved_by,
        "approval_id": action.approval_id,
    },
    actor_id=approved_by,
    actor_roles=approver_roles,
)
```

**Observação crítica:** Não existe campo `on_behalf_of` nos payloads. Quando um agente faz request, seu actor_id é registrado como executor, sem referência ao delegante original.

---

## 4. Análise: O que falta para GAP 4

### 4.1 Delegation Chain (`on_behalf_of`)

**Estado atual:**
- Não existe header `X-On-Behalf-Of`
- Não existe validação de "actor é agente"
- Não existe propagação de delegante nos eventos

**Mudanças necessárias:**

1. **ActorContext** - Adicionar campo `on_behalf_of`:
   ```python
   @dataclass
   class ActorContext:
       actor_id: str
       roles: List[str] = field(default_factory=list)
       tenant_id: str = DEFAULT_TENANT_ID
       identity_verified: bool = False
       on_behalf_of: Optional[str] = None  # NEW
       is_agent: bool = False  # NEW
   ```

2. **dependencies.py** - Validar `X-On-Behalf-Of`:
   - Só aceitar se actor tem role `agent`
   - Validar que `on_behalf_of` é UUID válido
   - Validar que delegante existe no registry (opcional - pode ser externo)

3. **Ledger events** - Incluir `on_behalf_of` no payload quando presente

### 4.2 Auto-solicitação (deny → request)

**Estado atual:**
- Deny emite `LEGACY_WRITE_DENIED` e retorna erro
- Não existe storage de "agent requests"
- Não existe evento `AGENT_REQUEST_CREATED`

**Mudanças necessárias:**

1. **Novo storage:** `institutions/<id>/agent_requests/`
   - `requests.jsonl` (append-only)
   - `state.json` (lookup rápido)

2. **Novo módulo:** `engine/agent_ops/agent_requests.py`
   ```python
   @dataclass
   class AgentRequest:
       request_id: str
       created_at: str
       institution_id: str
       dept_id: Optional[str]
       agent_actor_id: str
       on_behalf_of: Optional[str]
       endpoint_sig: str
       action_type: str
       deny_code: str
       deny_details: Dict[str, Any]
       status: str  # "pending", "resolved"
   ```

3. **Modificação em write_registry.py:**
   - Quando deny e actor é agente → criar AgentRequest
   - Emitir `AGENT_REQUEST_CREATED`

4. **Novo evento de ledger:** `AGENT_REQUEST_CREATED`
   ```python
   payload = {
       "request_id": request_id,
       "agent_actor_id": agent_actor_id,
       "on_behalf_of": on_behalf_of,
       "endpoint_sig": endpoint_sig,
       "deny_code": deny_code,
   }
   ```

### 4.3 Admin Endpoints para Agent Requests

**Mudanças necessárias:**

1. **Novos endpoints em api/admin.py ou console/routes.py:**
   ```python
   @router.get("/agent-requests")
   async def list_agent_requests(
       institution_id: str,
       status: Optional[str] = None,
       agent_id: Optional[str] = None,
   ) -> List[AgentRequest]

   @router.get("/agent-requests/{request_id}")
   async def get_agent_request(
       institution_id: str,
       request_id: str,
   ) -> AgentRequest
   ```

---

## 5. Proposta de Patch Mínimo

### 5.1 Arquivos a modificar

| Arquivo | Mudança |
|---------|---------|
| `core/actor_context.py` | Adicionar campos `on_behalf_of`, `is_agent` |
| `core/errors.py` | Adicionar error codes para agent requests |
| `api/dependencies.py` | Validar `X-On-Behalf-Of` header |
| `legacy_bridge/write_registry.py` | Criar agent request quando deny + is_agent |
| `core/ledger.py` | (nenhuma - usa payload) |

### 5.2 Novos arquivos

| Arquivo | Descrição |
|---------|-----------|
| `agent_ops/agent_requests.py` | Registry de agent requests |
| `console/routes.py` | Endpoints para listar agent requests |

### 5.3 Sequência de Implementação

1. **Fase 1: on_behalf_of básico**
   - Adicionar campo em ActorContext
   - Validar header em dependencies.py
   - Incluir no payload dos eventos de legacy write

2. **Fase 2: Auto-request**
   - Criar agent_requests.py
   - Modificar write_registry para criar request quando deny + is_agent
   - Emitir AGENT_REQUEST_CREATED

3. **Fase 3: Admin visibility**
   - Adicionar endpoints de listagem
   - (Console UI é futuro)

### 5.4 Testes a criar

```python
# tests/test_agent_delegation.py

def test_on_behalf_of_rejected_if_not_agent():
    """Actors sem role 'agent' não podem usar on_behalf_of."""

def test_on_behalf_of_accepted_for_agent():
    """Actors com role 'agent' podem usar on_behalf_of."""

def test_on_behalf_of_appears_in_ledger():
    """on_behalf_of aparece no payload dos eventos."""

def test_agent_deny_creates_request():
    """Deny para agente cria registro em agent_requests."""

def test_agent_request_created_event():
    """Evento AGENT_REQUEST_CREATED é emitido com payload correto."""

def test_agent_requests_listing():
    """Admin pode listar agent requests por institution."""
```

---

## 6. Riscos e Mitigações

### 6.1 Risco: Spoof via on_behalf_of

**Descrição:** Actor malicioso envia `X-On-Behalf-Of` fingindo ser agente.

**Mitigação:**
- Validar que actor tem role `agent` (do registry)
- Em strict mode, validar token primeiro
- Log explícito de delegation chains

### 6.2 Risco: Agent registry não confiável

**Descrição:** Em dev mode, qualquer actor pode se declarar como agent.

**Mitigação:**
- Usar strict mode em produção (ENGINE_AUTH_MODE=strict)
- role `agent` só pode ser atribuída via admin endpoints

### 6.3 Risco: Explosão de agent_requests

**Descrição:** Agente em loop criando infinitas requests.

**Mitigação:**
- Rate limiting na criação de requests (futuro)
- Cleanup policy para requests antigas (futuro)
- Para MVP: aceitar risco controlado

---

## 7. Resumo Executivo

**O que existe:**
- ActorContext com actor_id/roles
- Ledger registra actor em todos os eventos
- Agent Ops pode consultar denied por actor_id
- Legacy write tem pontos claros de deny/allow

**O que falta:**
- Header `X-On-Behalf-Of` para delegation
- Validação de role `agent`
- Storage de agent_requests quando deny
- Evento `AGENT_REQUEST_CREATED`
- Endpoints admin para listar requests

**Patch mínimo:**
- 2 arquivos modificados (actor_context, write_registry)
- 1 arquivo novo (agent_requests.py)
- ~200 linhas de código
- ~6 testes

**Impacto esperado:**
- Agente passa a operar como solicitante institucional
- Negações geram rastros formais e acionáveis
- Admin pode ver e eventualmente agir sobre requests

---

## 8. Implementação Realizada

**Status:** ✅ IMPLEMENTED
**Data:** 2026-01-21

### 8.1 Arquivos Criados

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `src/engine/agent_ops/agent_requests.py` | ~250 | Storage append-only para agent requests |
| `tests/test_agent_delegation.py` | ~450 | 20 testes automatizados |

### 8.2 Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/engine/core/actor_context.py` | Campos `is_agent`, `on_behalf_of`, método `can_delegate()` |
| `src/engine/core/actor_tokens.py` | Campo `is_agent` em records/state, `verify_token()` retorna is_agent |
| `src/engine/api/dependencies.py` | Header `X-On-Behalf-Of`, validação `_validate_on_behalf_of()` |
| `src/engine/core/errors.py` | 4 novos códigos de erro |
| `src/engine/legacy_bridge/write_registry.py` | Parâmetros `is_agent`/`on_behalf_of`, auto-request em deny |
| `src/engine/console/routes.py` | Endpoints `/agent-requests` e `/agent-requests/{id}` |

### 8.3 Funcionalidades Implementadas

✅ **GAP-4A: on_behalf_of como campo estruturado**
- Header `X-On-Behalf-Of` validado em `get_actor_context()`
- Validação: deve ser UUID válido
- Apenas agentes podem usar (is_agent=True ou role 'agent' em dev mode)

✅ **GAP-4B: is_agent no actor registry**
- Campo `is_agent` em `ActorTokenRecord` e `ActorTokenState`
- `create_token()` aceita parâmetro `is_agent`
- `verify_token()` retorna `is_agent` como 5º elemento

✅ **GAP-4C: Validação de delegation**
- Strict mode: requer `is_agent=True` do registry
- Dev mode: aceita `agent` role como hint, emite `UNVERIFIED_DELEGATION_USED`
- Deny determinístico com `ON_BEHALF_OF_NOT_AGENT` se não autorizado

✅ **GAP-4D: Storage de agent requests**
- `AgentRequestsRegistry` com append-only JSONL
- Path: `institutions/<id>/agent_requests/requests.jsonl`
- State: `institutions/<id>/agent_requests/state.json`

✅ **GAP-4E: Auto-request em deny**
- `_handle_denial()` cria agent request se `is_agent=True`
- Emite evento `AGENT_REQUEST_CREATED` com payload estruturado

✅ **GAP-4F: Eventos de ledger atualizados**
- `LEGACY_WRITE_INTENT_CREATED`: inclui `on_behalf_of` e `is_agent`
- `LEGACY_WRITE_DENIED`: inclui `on_behalf_of` e `is_agent`
- `AGENT_REQUEST_CREATED`: novo evento para auto-solicitation

✅ **GAP-4G: Endpoints admin read-only**
- `GET /console/agent-requests`: lista requests com filtros
- `GET /console/agent-requests/{id}`: detalhe de um request
- Respeita isolamento por `institution_id`/`dept_id`

✅ **GAP-4H: Testes automatizados**
- 20 testes cobrindo todos os critérios de aceite
- Classes: ActorContext, ActorTokens, AgentRequests, LegacyWrite, Ledger, Validation

### 8.4 Resultados dos Testes

```
$ python -m pytest tests/test_agent_delegation.py -v
============================== 20 passed in 1.05s ==============================

$ python -m pytest tests/test_legacy_write_approval.py tests/test_legacy_bridge_write.py -v
============================== 44 passed in 0.46s ==============================
```

### 8.5 Critérios de Aceite Verificados

| # | Critério | Status | Teste |
|---|----------|--------|-------|
| 1 | on_behalf_of só aceito para agents | ✅ | `test_on_behalf_of_not_agent_strict_mode` |
| 2 | on_behalf_of válido aparece no ledger | ✅ | `test_intent_created_includes_on_behalf_of` |
| 3 | Deny de agente gera registro | ✅ | `test_agent_deny_creates_request` |
| 4 | Evento AGENT_REQUEST_CREATED emitido | ✅ | `test_agent_request_created_event` |
| 5 | Outbox não enfileirado em deny | ✅ | `test_agent_deny_creates_request` |
| 6 | is_agent vem do registry | ✅ | `test_create_token_with_is_agent` |

### 8.6 Fluxo Implementado

**Agent com on_behalf_of, denied:**
```
1. POST /bridge/write/increase_limit
   Headers: X-On-Behalf-Of: <delegatee-uuid>
   Actor: agent-uuid (is_agent=True)

   → Validação de on_behalf_of (UUID válido, actor é agent)
   → LEGACY_WRITE_INTENT_CREATED { on_behalf_of, is_agent: true }
   → Gate evaluation (mandate/autonomy/policy)
   → LEGACY_WRITE_DENIED { on_behalf_of, is_agent: true }
   → AGENT_REQUEST_CREATED { agent_actor_id, on_behalf_of, deny_code }
   → Returns: { error_code: "LEGACY_WRITE_DENIED_*", denied_by: "..." }
```

**Agent request storage:**
```
institutions/<id>/agent_requests/
├── requests.jsonl  (append-only)
└── state.json      (lookup)
```

**Admin query:**
```
GET /console/agent-requests?institution_id=<uuid>&status=pending
→ Returns: { requests: [...] }
```

### 8.7 Códigos de Erro Adicionados

| Código | HTTP | Descrição |
|--------|------|-----------|
| `ON_BEHALF_OF_NOT_AGENT` | 403 | Actor não é agent e tentou usar on_behalf_of |
| `ON_BEHALF_OF_INVALID` | 400 | on_behalf_of não é UUID válido |
| `AGENT_REQUEST_NOT_FOUND` | 404 | Request não encontrado |
| `AGENT_REQUESTS_REGISTRY_UNAVAILABLE` | 500 | Falha ao acessar registry |

### 8.8 Notas de Implementação

1. **Verificação de agent:** Em strict mode, `is_agent` vem do registry (confiável). Em dev mode, aceita role 'agent' como hint mas emite warning.

2. **on_behalf_of não altera permissões:** Gates (RBAC/mandates/autonomy/policies) são avaliados sobre o actor real (agent), não sobre o delegatee. `on_behalf_of` é apenas para auditoria e roteamento de solicitação.

3. **Auto-request silencioso:** A criação de agent request em deny não falha a operação se houver erro no registry de requests.

4. **Isolamento por institution/dept:** Agent requests são isolados por `institution_id` e opcionalmente por `dept_id`.

5. **Backward compatibility:** Todos os parâmetros novos (`is_agent`, `on_behalf_of`) são opcionais e defaultam a valores seguros.
