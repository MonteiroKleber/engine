# 04-6 Agent Ops — API Specification

**Status:** IMPLEMENTADO
**Data:** 2026-01-20
**Baseado em:** spec.md (contrato da etapa)
**Implementado:** 2026-01-20 (41 testes passando)

---

## 1. Read Model (Query Layer)

### 1.1 Princípios

- **Sem banco de dados**: usa `get_all_events()` do ledger + filtro em memória
- **Append-only registry**: JSONL similar a `institutions_registry.jsonl`
- **Isolamento multi-tenant**: todas as queries recebem `(institution_id, dept_id)`

### 1.2 Funções Propostas

#### `list_events_by_actor(institution_id, actor_id, limit=50) -> List[LedgerEvent]`

Retorna os últimos N eventos onde `event.actor_id == actor_id`.

```python
def list_events_by_actor(
    institution_id: str,
    actor_id: str,
    limit: int = 50,
    dept_id: Optional[str] = None
) -> List[LedgerEvent]:
    """
    Lista os últimos N eventos de um actor específico.

    Implementação:
    - Carrega eventos do ledger da instituição via get_ledger_for_institution()
    - Filtra por actor_id
    - Opcionalmente filtra por dept_id
    - Retorna últimos N (ordem decrescente por seq)
    """
    # ✅ IMPLEMENTADO em src/engine/agent_ops/read_model.py
```

**Campos usados do LedgerEvent:**
- `actor_id` (filtro principal)
- `dept_id` (filtro opcional)
- `seq` (ordenação)

---

#### `list_denied_events(institution_id, gate=None, limit=50) -> List[LedgerEvent]`

Retorna eventos que representam negações (DENIED).

```python
def list_denied_events(
    institution_id: str,
    gate: Optional[str] = None,  # "rbac", "policy", "mandate", "sod", "autonomy"
    dept_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    limit: int = 50
) -> List[LedgerEvent]:
    """
    Lista eventos de negação.

    Detecção de negação por event_type + payload:
    - RBAC_DECISION + payload.allowed == False
    - POLICY_PRE_DECISION + payload.allowed == False
    - POLICY_POST_DECISION + payload.allowed == False
    - MANDATE_EVALUATED + payload.allowed == False
    - AUTONOMY_EVALUATED + payload.allowed == False
    - SOD_VIOLATION (sempre negação)
    """
    # ✅ IMPLEMENTADO em src/engine/agent_ops/read_model.py
```

**Mapeamento gate → event_type:**

| Gate | event_type | Condição de negação |
|------|-----------|---------------------|
| `rbac` | `RBAC_DECISION` | `payload.allowed == False` |
| `policy` | `POLICY_PRE_DECISION`, `POLICY_POST_DECISION` | `payload.allowed == False` |
| `mandate` | `MANDATE_EVALUATED` | `payload.allowed == False` |
| `autonomy` | `AUTONOMY_EVALUATED` | `payload.allowed == False` |
| `sod` | `SOD_VIOLATION` | sempre |

---

#### `get_agent_registry(institution_id) -> List[AgentEntry]`

Retorna lista de agentes registrados.

```python
@dataclass
class AgentEntry:
    agent_id: str           # UUID ou identificador único
    actor_id: str           # actor_id usado no ledger
    name: str               # nome descritivo
    roles: List[str]        # roles atribuídas
    dept_ids: List[str]     # departamentos com acesso
    created_at: str         # ISO timestamp
    created_by: str         # actor_id de quem criou
    description: str = ""   # descrição opcional

def get_agent_registry(institution_id: str, dept_id: Optional[str] = None) -> List[AgentEntry]:
    """
    Lê o registry de agentes da instituição.

    Arquivo: var/institutions/{institution_id}/agents_registry.jsonl
    Formato: append-only JSONL
    """
    # ✅ IMPLEMENTADO em src/engine/agent_ops/registry.py
```

---

#### `register_agent(institution_id, entry, registered_by) -> AgentEntry`

Registra um novo agente (append ao JSONL).

```python
def register_agent(
    institution_id: str,
    entry: AgentEntry,
) -> AgentEntry:
    """
    Registra um agente novo.

    Regras:
    - Define created_at com timestamp atual se não fornecido
    - Appenda ao agents_registry.jsonl
    - NÃO requer aprovação de mandato (registro é metadado, não ação governada)
    """
    # ✅ IMPLEMENTADO em src/engine/agent_ops/registry.py
```

**Nota:** Registro de agente é metadado informativo. O agente só pode executar ações se tiver mandato válido no sistema de governança.

---

### 1.3 Armazenamento do Registry

**Localização:**
```
var/institutions/{institution_id}/agents_registry.jsonl
```

**Formato (append-only JSONL):**
```jsonl
{"agent_id": "agent-001", "actor_id": "bot-expense-processor", "name": "Expense Processor Bot", "roles": ["processor"], "dept_ids": ["finance"], "created_at": "2026-01-20T10:00:00Z", "created_by": "admin", "description": "Processa despesas automaticamente"}
{"agent_id": "agent-002", "actor_id": "bot-approval-notifier", "name": "Approval Notifier", "roles": ["viewer"], "dept_ids": ["finance", "hr"], "created_at": "2026-01-20T11:00:00Z", "created_by": "admin", "description": "Envia notificações de aprovação"}
```

**Por que JSONL append-only:**
- Consistente com padrão existente (`institutions_registry.jsonl`)
- Auditável (histórico preservado)
- Simples (sem dependência de DB)
- Idempotente para recovery

---

## 2. Console Routes

### 2.1 Rotas Propostas

| Método | Path | Template | Descrição |
|--------|------|----------|-----------|
| GET | `/console/agents` | `agents.html` | Lista de agentes registrados |
| GET | `/console/agents/{agent_id}` | `agents_detail.html` | Detalhe de um agente + histórico |
| GET | `/console/denied` | `denied.html` | Lista de tentativas negadas |

### 2.2 Parâmetros de Query

Todas as rotas seguem o padrão existente do console:

```
?institution_id=<id>&dept_id=<id>
```

### 2.3 Detalhamento das Rotas

#### GET /console/agents

**Parâmetros:**
- `institution_id` (required)
- `dept_id` (optional, filtra agentes por dept)

**Dados para template:**
```python
{
    "agents": List[AgentEntry],      # do registry
    "institution_id": str,
    "dept_id": str | None
}
```

---

#### GET /console/agents/{agent_id}

**Parâmetros:**
- `institution_id` (required)
- `limit` (optional, default=50)

**Dados para template:**
```python
{
    "agent": AgentEntry,                    # do registry
    "recent_events": List[LedgerEvent],     # últimos N eventos
    "denied_events": List[LedgerEvent],     # últimos N negados
    "institution_id": str,
    "stats": {
        "total_events": int,
        "denied_count": int,
        "last_active": str | None           # timestamp último evento
    }
}
```

---

#### GET /console/denied

**Parâmetros:**
- `institution_id` (required)
- `dept_id` (optional)
- `gate` (optional): `rbac`, `policy`, `mandate`, `sod`, `autonomy`
- `actor_id` (optional): filtrar por actor específico
- `limit` (optional, default=100)

**Dados para template:**
```python
{
    "denied_events": List[LedgerEvent],
    "filters": {
        "gate": str | None,
        "actor_id": str | None,
        "dept_id": str | None
    },
    "institution_id": str,
    "available_gates": ["rbac", "policy", "mandate", "sod", "autonomy"]
}
```

---

## 3. Autenticação e Autorização

### 3.1 Padrão Existente (Console)

O console já implementa:

1. **Session cookie** (`console_session`): signed com `itsdangerous`
2. **CSRF token**: validado em forms
3. **X-Admin-Token header**: acesso administrativo

### 3.2 Aplicação às Novas Rotas

- Todas as rotas `/console/agents*` e `/console/denied` requerem:
  - Session válida OU X-Admin-Token
  - `institution_id` sempre obrigatório no query param
  - Isolamento garantido: query só retorna dados da instituição especificada

### 3.3 Permissões

**Read-only por padrão:**
- GET em todas as rotas: qualquer usuário autenticado com acesso à instituição
- Registro de agente (POST futuro): requer role específica (ex: `admin`, `agent_admin`)

---

## 4. Templates HTML

### 4.1 agents.html

```html
{% extends "base.html" %}
{% block content %}
<h1>Agents Registry</h1>

<table>
  <thead>
    <tr>
      <th>Name</th>
      <th>Actor ID</th>
      <th>Roles</th>
      <th>Departments</th>
      <th>Created</th>
    </tr>
  </thead>
  <tbody>
    {% for agent in agents %}
    <tr>
      <td><a href="/console/agents/{{ agent.agent_id }}?institution_id={{ institution_id }}">{{ agent.name }}</a></td>
      <td><code>{{ agent.actor_id }}</code></td>
      <td>{{ agent.roles | join(", ") }}</td>
      <td>{{ agent.dept_ids | join(", ") }}</td>
      <td>{{ agent.created_at }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

### 4.2 agents_detail.html

```html
{% extends "base.html" %}
{% block content %}
<h1>{{ agent.name }}</h1>
<p><code>{{ agent.actor_id }}</code></p>
<p>{{ agent.description }}</p>

<h2>Stats</h2>
<ul>
  <li>Total events: {{ stats.total_events }}</li>
  <li>Denied: {{ stats.denied_count }}</li>
  <li>Last active: {{ stats.last_active or "Never" }}</li>
</ul>

<h2>Recent Events</h2>
<table>
  <thead>
    <tr><th>Time</th><th>Type</th><th>Step</th><th>Dept</th></tr>
  </thead>
  <tbody>
    {% for event in recent_events %}
    <tr>
      <td>{{ event.timestamp }}</td>
      <td>{{ event.event_type }}</td>
      <td>{{ event.step }}</td>
      <td>{{ event.dept_id }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<h2>Denied Attempts</h2>
<table>
  <thead>
    <tr><th>Time</th><th>Gate</th><th>Reason</th><th>Step</th></tr>
  </thead>
  <tbody>
    {% for event in denied_events %}
    <tr>
      <td>{{ event.timestamp }}</td>
      <td>{{ event.event_type }}</td>
      <td>{{ event.payload.reason or event.payload.code or "-" }}</td>
      <td>{{ event.step }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

### 4.3 denied.html

```html
{% extends "base.html" %}
{% block content %}
<h1>Denied Attempts</h1>

<form method="get">
  <input type="hidden" name="institution_id" value="{{ institution_id }}">
  <select name="gate">
    <option value="">All gates</option>
    {% for g in available_gates %}
    <option value="{{ g }}" {% if filters.gate == g %}selected{% endif %}>{{ g }}</option>
    {% endfor %}
  </select>
  <input type="text" name="actor_id" placeholder="Actor ID" value="{{ filters.actor_id or '' }}">
  <button type="submit">Filter</button>
</form>

<table>
  <thead>
    <tr><th>Time</th><th>Actor</th><th>Gate</th><th>Reason</th><th>Step</th><th>Dept</th></tr>
  </thead>
  <tbody>
    {% for event in denied_events %}
    <tr>
      <td>{{ event.timestamp }}</td>
      <td><code>{{ event.actor_id }}</code></td>
      <td>{{ event.event_type }}</td>
      <td>{{ event.payload.reason or event.payload.code or "-" }}</td>
      <td>{{ event.step }}</td>
      <td>{{ event.dept_id }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

---

## 5. Módulo Proposto

### 5.1 Estrutura de Arquivos

```
src/engine/
├── agent_ops/
│   ├── __init__.py
│   ├── read_model.py      # list_events_by_actor, list_denied_events
│   └── registry.py        # get_agent_registry, register_agent, AgentEntry
└── console/
    └── templates/
        ├── agents.html
        ├── agents_detail.html
        └── denied.html
```

### 5.2 Dependências

- `src/engine/core/ledger.py` (LedgerEvent, get_all_events, history)
- `src/engine/console/routes.py` (padrão de rotas existente)
- `src/engine/console/session.py` (autenticação)

---

## 6. Exemplos de Uso

### 6.1 Listar eventos de um agente

```python
from engine.agent_ops.read_model import list_events_by_actor

events = list_events_by_actor(
    institution_id="inst-001",
    actor_id="bot-expense-processor",
    limit=20
)
for e in events:
    print(f"{e.timestamp} | {e.event_type} | {e.step}")
```

### 6.2 Listar tentativas negadas por RBAC

```python
from engine.agent_ops.read_model import list_denied_events

denied = list_denied_events(
    institution_id="inst-001",
    gate="rbac",
    limit=50
)
for e in denied:
    print(f"{e.actor_id} blocked at {e.step}: {e.payload.get('reason')}")
```

### 6.3 Registrar um novo agente

```python
from engine.agent_ops.registry import register_agent, AgentEntry

entry = AgentEntry(
    agent_id="",  # será gerado
    actor_id="bot-new-processor",
    name="New Processor Bot",
    roles=["processor"],
    dept_ids=["finance"],
    created_at="",  # será preenchido
    created_by="admin"
)

registered = register_agent(
    institution_id="inst-001",
    entry=entry,
    registered_by="admin"
)
print(f"Registered: {registered.agent_id}")
```

---

## 7. Considerações de Performance

### 7.1 Limitações do Modelo Atual

- `get_all_events()` carrega todos os eventos em memória
- Filtro por `actor_id` requer scan completo
- Para instituições com muitos eventos (>10k), pode ser lento

### 7.2 Mitigações (Futuro)

1. **Índice em memória**: manter dict `actor_id -> [event_seq]` ao carregar
2. **Paginação**: limite de eventos por request
3. **Cache**: LRU cache de queries frequentes
4. **Índice de negações**: separar eventos DENIED em arquivo auxiliar

### 7.3 Escopo Atual

Para MVP, aceitar:
- Scan completo com `limit` para truncar resultado
- Sem cache (ledger já tem cache interno)
- Performance aceitável para <5k eventos por instituição

---

## 8. Implementação Realizada (2026-01-20)

### 8.1 Arquivos Criados

| Arquivo | LOC | Descrição |
|---------|-----|-----------|
| `src/engine/agent_ops/__init__.py` | ~20 | Exports públicos |
| `src/engine/agent_ops/read_model.py` | ~130 | Query functions: list_events_by_actor, list_denied_events, get_actor_stats, list_unique_actors, is_denied_event, get_gate_for_event |
| `src/engine/agent_ops/registry.py` | ~80 | AgentEntry dataclass, CRUD functions |
| `src/engine/console/templates/agents.html` | ~80 | Lista de agentes + actors do ledger |
| `src/engine/console/templates/agents_detail.html` | ~120 | Detalhe de agente com stats e eventos |
| `src/engine/console/templates/denied.html` | ~140 | Lista de negações com filtros |
| `tests/test_agent_ops.py` | ~600 | 41 testes cobrindo todas as funcionalidades |

### 8.2 Arquivos Modificados

| Arquivo | Mudanças |
|---------|----------|
| `src/engine/console/routes.py` | +3 rotas: /agents, /agents/{actor_id}, /denied |
| `src/engine/console/templates/base.html` | +2 nav links: Agents, Denied |

### 8.3 Cobertura de Testes

```
41 tests passing:
- TestIsDeniedEvent (5 tests)
- TestGetGateForEvent (3 tests)
- TestListEventsByActor (5 tests)
- TestListDeniedEvents (6 tests)
- TestGetActorStats (2 tests)
- TestListUniqueActors (2 tests)
- TestAgentRegistry (4 tests)
- TestConsoleAgentsAuth (2 tests)
- TestConsoleAgentsPage (3 tests)
- TestConsoleAgentDetailPage (1 test)
- TestConsoleDeniedPage (4 tests)
- TestMultiTenantIsolation (4 tests)
```

### 8.4 Verificação

```bash
# Todos os testes passam
python -m pytest tests/test_agent_ops.py -v
# 41 passed, 4 warnings (deprecation Starlette)
```

### 8.5 Funcionalidades Adicionais Implementadas

Além do especificado, implementamos:

1. **get_actor_stats()**: Retorna total_events, denied_count, last_active para um actor
2. **list_unique_actors()**: Lista todos os actors únicos no ledger de uma instituição
3. **Anti-inference protection**: Rota /agents/{actor_id} retorna 404 se actor não existe no registry E não tem eventos no ledger
4. **Gate legend**: Template denied.html mostra explicação de cada tipo de gate
5. **Detection criteria**: Template denied.html documenta as condições de detecção de negação
