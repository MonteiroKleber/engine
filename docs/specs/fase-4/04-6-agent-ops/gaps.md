# 04-6 Agent Ops — Gaps Analysis

**Status:** IMPLEMENTADO
**Data:** 2026-01-20
**Baseado em:** spec.md (contrato) + api.md (design proposto)
**Completado:** 2026-01-20 (todos os 6 gaps resolvidos, 41 testes passando)

---

## 1. Estado Atual

### 1.1 O que já existe

| Componente | Status | Localização |
|------------|--------|-------------|
| LedgerEvent com `actor_id` | ✅ Completo | `src/engine/core/ledger.py:23-45` |
| Eventos de negação (DENIED) | ✅ Completo | `src/engine/core/errors.py` |
| Console com session auth | ✅ Completo | `src/engine/console/session.py` |
| Query params `institution_id/dept_id` | ✅ Completo | `src/engine/console/routes.py` |
| `get_all_events()` no ledger | ✅ Completo | `src/engine/core/ledger.py:history()` |

### 1.2 O que NÃO existe

| Componente | Status | Impacto |
|------------|--------|---------|
| Query por `actor_id` | ❌ Não existe | Requer scan completo |
| Filtro de eventos DENIED | ❌ Não existe | Requer implementação |
| Agent registry (JSONL) | ❌ Não existe | Novo arquivo/módulo |
| Rotas `/console/agents*` | ❌ Não existe | Novas rotas |
| Rota `/console/denied` | ❌ Não existe | Nova rota |
| Templates agents.html, etc. | ❌ Não existe | Novos templates |

---

## 2. Gaps Identificados

### GAP-1: Ausência de Read Model por Actor ✅ RESOLVIDO

**Impacto:** ALTO
**Área:** Query/Observability
**Status:** ✅ IMPLEMENTADO em `src/engine/agent_ops/read_model.py`

**Implementado:**
- `list_events_by_actor(institution_id, actor_id, limit, dept_id)`
- `get_actor_stats(institution_id, actor_id, dept_id)` - retorna total_events, denied_count, last_active
- `list_unique_actors(institution_id, dept_id)` - lista todos os actors do ledger

**Testes:** 7 testes cobrindo filtros, limits, ordenação e dept_id

---

### GAP-2: Ausência de Query para Eventos Negados ✅ RESOLVIDO

**Impacto:** ALTO
**Área:** Observability/Debugging
**Status:** ✅ IMPLEMENTADO em `src/engine/agent_ops/read_model.py`

**Implementado:**
- `is_denied_event(event)` - detecção determinística de negação
- `get_gate_for_event(event_type)` - mapeamento event_type → gate
- `list_denied_events(institution_id, gate, dept_id, actor_id, limit)`
- Constante `GATE_EVENT_TYPES` com mapeamento completo

**Detecção determinística:**
- `RBAC_DECISION` + `payload.allowed == False` → gate "rbac"
- `POLICY_PRE_DECISION/POST_DECISION` + `payload.allowed == False` → gate "policy"
- `MANDATE_EVALUATED` + `payload.allowed == False` → gate "mandate"
- `AUTONOMY_EVALUATED` + `payload.allowed == False` → gate "autonomy"
- `SOD_VIOLATION` (sempre) → gate "sod"

**Testes:** 11 testes cobrindo is_denied_event, get_gate_for_event, list_denied_events com filtros

---

### GAP-3: Ausência de Agent Registry ✅ RESOLVIDO

**Impacto:** MÉDIO
**Área:** Metadados/Operações
**Status:** ✅ IMPLEMENTADO em `src/engine/agent_ops/registry.py`

**Implementado:**
- `AgentEntry` dataclass com: actor_id, name, roles, dept_ids, created_at, created_by, description
- `get_agent_registry(institution_id, dept_id)` - lista agentes com filtro opcional por dept
- `register_agent(institution_id, entry)` - append ao JSONL
- `get_agent_by_actor_id(institution_id, actor_id)` - busca por actor_id

**Storage:** `var/institutions/{institution_id}/agents_registry.jsonl` (append-only JSONL)

**Testes:** 4 testes cobrindo CRUD e filtro por dept

---

### GAP-4: Rotas de Console Ausentes ✅ RESOLVIDO

**Impacto:** ALTO
**Área:** UI/Console
**Status:** ✅ IMPLEMENTADO em `src/engine/console/routes.py`

**Rotas implementadas:**
```python
@app.get("/console/agents")              # Lista de agentes + actors do ledger
@app.get("/console/agents/{actor_id}")   # Detalhe de agente/actor com stats e eventos
@app.get("/console/denied")              # Tentativas negadas com filtros por gate/actor
```

**Funcionalidades:**
- Dual auth: Session cookie OU X-Admin-Token header
- Multi-tenant isolation: filtro obrigatório por institution_id
- Anti-inference: /agents/{actor_id} retorna 404 se actor não existe
- Filtros: gate, actor_id, dept_id (denied page)

**Testes:** 10 testes cobrindo auth, rendering, filtros, 404

---

### GAP-5: Templates Ausentes ✅ RESOLVIDO

**Impacto:** MÉDIO
**Área:** UI/Templates
**Status:** ✅ IMPLEMENTADO em `src/engine/console/templates/`

**Templates criados:**
```
src/engine/console/templates/
├── agents.html           # Lista de agentes + actors (~80 LOC)
├── agents_detail.html    # Detalhe + stats + eventos (~120 LOC)
└── denied.html           # Negações com filtros (~140 LOC)
```

**Funcionalidades adicionais:**
- agents.html: Mostra agentes do registry + actors do ledger (combinados)
- agents_detail.html: Stats (total, denied, last_active) + eventos recentes + negações
- denied.html: Gate legend explicando cada tipo + Detection criteria + filtros funcionais

**Nav links:** Adicionados em base.html para Agents e Denied

---

### GAP-6: Ausência de Testes para Isolamento Multi-Tenant ✅ RESOLVIDO

**Impacto:** ALTO (DoD requirement)
**Área:** Testes
**Status:** ✅ IMPLEMENTADO em `tests/test_agent_ops.py`

**Testes de isolamento implementados (TestMultiTenantIsolation):**
- `test_isolation_events_by_institution` - eventos de inst-A não aparecem em inst-B
- `test_isolation_events_by_dept` - eventos de dept-X não aparecem em query por dept-Y
- `test_isolation_registry_by_institution` - agentes de inst-A não aparecem em inst-B
- `test_isolation_unique_actors_by_dept` - actors de dept-X não aparecem em list por dept-Y

**Cobertura:** 2 instituições × 2 departamentos conforme DoD

---

## 3. Plano de Implementação Mínimo

### Fase 1: Read Model (sem UI)

**Arquivos novos:**
```
src/engine/agent_ops/
├── __init__.py
├── read_model.py     # list_events_by_actor, list_denied_events
└── registry.py       # AgentEntry, get_agent_registry, register_agent
```

**Estimativa:** ~150 linhas de código

**Testes:**
- `test_list_events_by_actor_empty`
- `test_list_events_by_actor_filters_correctly`
- `test_list_events_by_actor_respects_limit`
- `test_list_denied_events_by_gate`
- `test_list_denied_events_all_gates`
- `test_agent_registry_crud`

---

### Fase 2: Console Routes

**Arquivos modificados:**
```
src/engine/console/routes.py   # +3 rotas
```

**Arquivos novos:**
```
src/engine/console/templates/
├── agents.html
├── agents_detail.html
└── denied.html
```

**Estimativa:** ~100 linhas Python + ~150 linhas HTML

**Testes:**
- `test_console_agents_requires_auth`
- `test_console_agents_lists_registry`
- `test_console_agents_detail_shows_events`
- `test_console_denied_filters_by_gate`
- `test_console_denied_isolation`

---

### Fase 3: Testes de Isolamento

**Arquivo:**
```
tests/test_agent_ops.py
```

**Testes específicos para DoD:**
- `test_isolation_two_institutions_agents_separate`
- `test_isolation_two_depts_events_separate`
- `test_isolation_denied_not_cross_pollute`

**Estimativa:** ~100 linhas de teste

---

## 4. Dependências

### 4.1 Dependências Internas

| Módulo | Usado para |
|--------|-----------|
| `src/engine/core/ledger.py` | LedgerEvent, get_all_events |
| `src/engine/core/errors.py` | Códigos de erro para mapeamento |
| `src/engine/console/session.py` | Autenticação |
| `src/engine/console/routes.py` | Padrão de rotas |

### 4.2 Dependências Externas

Nenhuma nova. Usa apenas:
- `dataclasses` (stdlib)
- `json` (stdlib)
- `pathlib` (stdlib)
- `jinja2` (já usado pelo console)

---

## 5. Riscos e Mitigações

### R1: Performance com muitos eventos

**Risco:** `list_events_by_actor` faz scan completo do ledger.

**Mitigação:**
- Usar `limit` para truncar resultado
- Para MVP, aceitar até ~5k eventos por instituição
- Futuro: índice secundário por actor_id

---

### R2: Consistência do Registry

**Risco:** Registry JSONL pode ficar inconsistente se processo morrer durante append.

**Mitigação:**
- Usar append atômico (write completo + fsync)
- Consistente com padrão já usado em `institutions_registry.jsonl`

---

### R3: Actor ID não validado

**Risco:** Registrar agente com `actor_id` que não existe ou é de outro tenant.

**Mitigação:**
- Registry é apenas metadado informativo
- Ações reais dependem de mandato válido (validado em runtime)
- Opcional: warning se actor_id nunca apareceu no ledger

---

## 6. Definition of Done Checklist

Baseado em `spec.md`:

- [x] Console mostra lista de agentes e histórico por agente (com base no ledger)
  - ✅ GAP-3 (registry), GAP-4 (rotas), GAP-5 (templates) - RESOLVIDOS

- [x] Console mostra "denied attempts" com razão determinística (gate/código)
  - ✅ GAP-2 (query denied), GAP-4 (rotas), GAP-5 (templates) - RESOLVIDOS

- [x] Testes cobrindo isolamento (duas instituições, dois depts)
  - ✅ GAP-6 (testes) - RESOLVIDO (4 testes de isolamento)

---

## 7. Ordem de Implementação Recomendada

1. **GAP-3** → Agent Registry (fundação para lista de agentes)
2. **GAP-1** → Read Model por actor (fundação para histórico)
3. **GAP-2** → Query de negados (fundação para denied page)
4. **GAP-4** → Rotas do console
5. **GAP-5** → Templates
6. **GAP-6** → Testes de isolamento

**Total estimado:** ~400 linhas de código + ~100 linhas de teste + ~150 linhas de templates

---

## 8. Arquivos de Referência

| Arquivo | Descrição | Relevância |
|---------|-----------|------------|
| [src/engine/core/ledger.py](src/engine/core/ledger.py) | LedgerEvent dataclass, history() | Base para read model |
| [src/engine/core/errors.py](src/engine/core/errors.py) | Códigos DENIED | Mapeamento de gates |
| [src/engine/console/routes.py](src/engine/console/routes.py) | Rotas existentes | Padrão a seguir |
| [src/engine/console/session.py](src/engine/console/session.py) | Auth do console | Reutilizar |
| [var/institutions/README.md](var/institutions/README.md) | Estrutura multi-tenant | Padrão de storage |

---

## 9. Implementação Realizada (2026-01-20)

### 9.1 Resumo

| Métrica | Estimado | Real |
|---------|----------|------|
| Linhas de código | ~400 | ~230 |
| Linhas de teste | ~100 | ~600 |
| Linhas de templates | ~150 | ~340 |
| Testes | ~10 | 41 |

### 9.2 Arquivos Criados

```
src/engine/agent_ops/
├── __init__.py           # Exports públicos
├── read_model.py         # Query functions (is_denied_event, list_events_by_actor, etc)
└── registry.py           # AgentEntry dataclass, CRUD functions

src/engine/console/templates/
├── agents.html           # Lista de agentes/actors
├── agents_detail.html    # Detalhe com stats e eventos
└── denied.html           # Negações com filtros e legend

tests/
└── test_agent_ops.py     # 41 testes completos
```

### 9.3 Verificação Final

```bash
# Todos os 41 testes passam
python -m pytest tests/test_agent_ops.py -v
# 41 passed, 4 warnings

# Warnings são deprecation do Starlette (TemplateResponse), não afetam funcionalidade
```

### 9.4 Todos os 6 Gaps Resolvidos

| Gap | Descrição | Status |
|-----|-----------|--------|
| GAP-1 | Read Model por Actor | ✅ |
| GAP-2 | Query para Eventos Negados | ✅ |
| GAP-3 | Agent Registry | ✅ |
| GAP-4 | Rotas de Console | ✅ |
| GAP-5 | Templates | ✅ |
| GAP-6 | Testes de Isolamento | ✅ |
