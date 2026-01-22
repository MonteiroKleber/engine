# Gaps — Etapa 3.4: UI de Governança Operacional (Mandatos)

**Data:** 2026-01-19
**Status:** DRAFT
**Prompt inicial:** 3.4.1 (Diagnóstico)

## Resumo

| Gap | Severidade | Status |
|-----|------------|--------|
| GAP-01: Rotas console mandates não existem | Alto | RESOLVIDO |
| GAP-02: Templates para mandates não existem | Alto | RESOLVIDO |
| GAP-03: Formulário de criação de proposal | Alto | RESOLVIDO |
| GAP-04: Ações decide/apply via console | Alto | RESOLVIDO |
| GAP-05: Diff antes/depois de mandato | Médio | RESOLVIDO |
| GAP-06: Nav link Mandates no base.html | Baixo | RESOLVIDO |

---

## Mapeamento: admin_mandates.py (API existente)

### Localização
`src/engine/api/admin_mandates.py`

### Rotas disponíveis (prefixo `/admin/mandates`)

| Rota | Método | Descrição | Auth |
|------|--------|-----------|------|
| `/proposals` | POST | Criar proposal (create/update/revoke) | X-Admin-Key ou X-Admin-Token |
| `/proposals` | GET | Listar proposals | X-Admin-Key ou X-Admin-Token |
| `/proposals/{id}/decide` | POST | Aprovar ou rejeitar | X-Admin-Key ou X-Admin-Token |
| `/governed` | GET | Listar mandatos governados | X-Admin-Key ou X-Admin-Token |
| `/effective` | GET | Listar mandatos efetivos (bundle + governed) | X-Admin-Key ou X-Admin-Token |

### Auth requerida
- `X-Institution-Id` header obrigatório
- `require_admin_auth(request, institution_id)` via `admin_auth.py`
- Suporta X-Admin-Key (per-institution) ou X-Admin-Token (legacy DEFAULT)

### Request Models

```python
class MandateProposalRequest(BaseModel):
    operation: str       # "create", "update", "revoke"
    mandate_id: str
    mandate_data: Optional[Dict]  # required for create/update
    reason: str
    dept_id: Optional[str]

class DecideProposalRequest(BaseModel):
    decision: str       # "approve" or "reject"
    reason: Optional[str]
```

### Response Models

```python
class MandateProposalResponse(BaseModel):
    proposal_id: str
    status: str         # "OPEN" or "DECIDED"
    created_at: str
    mandate_operation: str
    dept_id: Optional[str]
    mandate_id: str
    mandate_data: Optional[Dict]
    reason: str
    created_by: str
    decision: Optional[str]
    decision_reason: Optional[str]
    decided_at: Optional[str]
    decided_by: Optional[str]
```

---

## Mapeamento: governed_mandates.py (Core)

### Localização
`src/engine/core/governed_mandates.py`

### Funções principais

| Função | Descrição |
|--------|-----------|
| `propose_mandate_change()` | Cria proposal (valida schema, emite ledger) |
| `decide_mandate_proposal()` | Aprova/rejeita (auto-aplica se aprovado) |
| `apply_mandate_change()` | Aplica mudança (chamado internamente) |
| `list_mandate_proposals()` | Lista proposals (filtro status/dept) |
| `list_governed_mandates()` | Lista mandatos governados atuais |
| `get_effective_mandates()` | Retorna mandatos efetivos (merged) |

### Dataclasses

```python
@dataclass
class MandateProposalState:
    proposal_id: str
    status: str              # "OPEN" or "DECIDED"
    mandate_operation: str   # "create", "update", "revoke"
    mandate_id: str
    mandate_data: Optional[Dict]
    reason: str
    created_by: str
    decision: Optional[str]
    decision_reason: Optional[str]
    decided_at: Optional[str]
    decided_by: Optional[str]
```

### Workflow

```
propose_mandate_change()
    │
    ├── Valida operation (create/update/revoke)
    ├── Valida mandate_data contra schema
    ├── Verifica conflitos (already exists, not found)
    ├── Persiste em JSONL
    └── Emite MANDATE_PROPOSED no ledger
          │
          ▼
decide_mandate_proposal()
    │
    ├── Valida proposal existe e está OPEN
    ├── Persiste decisão em JSONL
    ├── Emite MANDATE_APPROVED ou MANDATE_REJECTED
    └── Se aprovado: chama apply_mandate_change()
          │
          ▼
apply_mandate_change()
    │
    ├── Atualiza governed_mandates_state.json
    ├── Persiste em governed_mandates.jsonl
    ├── Emite MANDATE_APPLIED ou MANDATE_REVOKED
    └── Invalida cache de effective mandates
```

---

## Mapeamento: Console Auth (routes.py)

### Auth atual
O console usa `_require_admin_token()` que valida via `verify_admin_token()`:
```python
def _require_admin_token(token: Optional[str]) -> None:
    if not verify_admin_token(token):
        raise HTTPException(status_code=401, ...)
```

### Diferença para admin_mandates.py
- Console: usa `X-Admin-Token` simples
- Admin API: usa `require_admin_auth()` que suporta X-Admin-Key + X-Admin-Token

### Decisão necessária
Para as rotas mutáveis do console (POST), usar:
1. **Opção A**: Manter `verify_admin_token()` (mais simples)
2. **Opção B**: Migrar para `require_admin_auth()` (mais seguro, per-institution)

**Recomendação**: Usar `require_admin_auth()` para rotas POST, manter `verify_admin_token()` para GET.

---

## Mapeamento: Console Templates (padrões)

### Base template
`base.html` define:
- Header com nav links dinâmicos
- `{{ admin_token }}` passado via `hx-headers`
- Context institucional (institution_name, dept_id)

### Padrões de dados
Handlers passam dict para template:
```python
return templates.TemplateResponse(
    "page.html",
    {
        "request": request,
        "active_page": "nome",
        "admin_token": x_admin_token or "",
        "institution_id": institution_id,
        "institution_name": institution_name,
        "dept_id": dept_id,
        # dados específicos...
    },
)
```

### Componentes reutilizáveis
- `.card` para seções
- `.badge` para status (badge-active, badge-error, badge-unpinned)
- `table` para listas
- `.info-row` para key-value pairs
- `.code-block` para código/JSON
- `.btn-link` para botões secundários

---

## GAP-01: Rotas console mandates não existem

### Spec requer
- `GET /console/mandates`
- `GET /console/mandates/proposals`
- `GET /console/mandates/proposals/new`
- `POST /console/mandates/proposals`
- `POST /console/mandates/proposals/{id}/decide`
- `POST /console/mandates/proposals/{id}/apply`

### Estado atual
Nenhuma rota `/console/mandates` existe.

### Solução proposta
Criar 6 handlers em `routes.py`:
1. `console_mandates` — lista mandatos efetivos
2. `console_mandates_proposals` — lista proposals
3. `console_mandates_proposals_new` — form para nova proposal
4. `console_mandates_proposals_create` — POST cria proposal
5. `console_mandates_proposals_decide` — POST decide
6. `console_mandates_proposals_apply` — POST aplica (opcional)

---

## GAP-02: Templates para mandates não existem

### Spec requer
- listagem + detalhes
- forms simples com validação mínima

### Solução proposta
Criar templates:
- `mandates.html` — lista efetivos + link para proposals
- `mandates_proposals.html` — lista proposals com status
- `mandates_proposal_new.html` — form para criar proposal
- `mandates_proposal_detail.html` — detalhes + ações decide

---

## GAP-03: Formulário de criação de proposal

### Spec requer
- criar proposal (create/update/revoke)
- validação mínima

### Desafios
- Mandate data é JSON complexo com schema definido
- Form precisa capturar: operation, mandate_id, mandate_data, reason

### Solução proposta
- Select para operation (create/update/revoke)
- Input para mandate_id
- Textarea para mandate_data (JSON)
- Textarea para reason
- Validação client-side básica (JSON válido)
- Validação server-side via schema

---

## GAP-04: Ações decide/apply via console

### Spec requer
- decidir (approve/reject)
- aplicar quando aprovado

### Estado atual
`decide_mandate_proposal()` já aplica automaticamente quando aprovado.

### Solução proposta
- Form com radio buttons: approve/reject
- Input para reason
- POST redireciona para lista com flash message
- Não precisa de rota `/apply` separada (já é automático)

---

## GAP-05: Diff antes/depois de mandato

### Spec requer
> Mostrar diffs simples: "antes/depois" do mandato efetivo

### Desafio
Para update/revoke, mostrar o mandato atual vs proposto.

### Solução proposta
- No template de detalhe da proposal:
  - Se update: mostrar current_data vs proposed_data
  - Se revoke: mostrar current_data vs "(será removido)"
  - Se create: mostrar "(não existe)" vs proposed_data
- Usar `<pre class="code-block">` com cores para diff

---

## GAP-06: Nav link Mandates no base.html

### Estado atual
Nav tem: Home, Status, Bundles, Contracts, Proof, Legacy

### Solução proposta
Adicionar entre Status e Bundles:
```html
<a href="/console/mandates?institution_id={{ institution_id }}..."
   class="{% if active_page == 'mandates' %}active{% endif %}">Mandates</a>
```

---

## Checklist de Implementação (PROMPT 3.4.2)

- [x] GAP-01: Criar rotas GET para listagem
- [x] GAP-01: Criar rotas POST para mutação
- [x] GAP-02: Criar templates mandates*.html
- [x] GAP-03: Form para nova proposal
- [x] GAP-04: Ações decide/apply
- [x] GAP-05: Diff antes/depois
- [x] GAP-06: Nav link no base.html
- [x] Testes: auth, GET pages, POST actions

## Implementação (PROMPT 3.4.2) — Concluído 2026-01-19

### Rotas implementadas (`routes.py`)

| Rota | Método | Handler | Descrição |
|------|--------|---------|-----------|
| `/console/mandates` | GET | `console_mandates` | Lista mandatos efetivos |
| `/console/mandates/proposals` | GET | `console_mandates_proposals` | Lista proposals |
| `/console/mandates/proposals/new` | GET | `console_mandates_proposals_new` | Form nova proposal |
| `/console/mandates/proposals` | POST | `console_mandates_proposals_create` | Cria proposal |
| `/console/mandates/proposals/{id}` | GET | `console_mandates_proposal_detail` | Detalhe + decide |
| `/console/mandates/proposals/{id}/decide` | POST | `console_mandates_proposal_decide` | Decide (approve/reject) |

### Templates implementados

| Template | Descrição |
|----------|-----------|
| `mandates.html` | Lista mandatos efetivos com source (bundle/governed) |
| `mandates_proposals.html` | Lista proposals com status badges |
| `mandates_proposal_new.html` | Form criar proposal (operation, mandate_id, mandate_data, reason) |
| `mandates_proposal_detail.html` | Detalhe + diff + form decide |

### Testes adicionados (`test_console.py`)

| Classe | Testes |
|--------|--------|
| `TestConsoleMandatesAuth` | 4 testes (401 para GET/POST sem token) |
| `TestConsoleMandatesPage` | 3 testes (HTML, links) |
| `TestConsoleMandatesProposalsPage` | 3 testes |
| `TestConsoleMandatesProposalNewPage` | 3 testes (form fields) |
| `TestConsoleMandatesProposalCreate` | 3 testes (success, invalid JSON, empty data) |
| `TestConsoleMandatesProposalDecide` | 3 testes (approve, reject, reject sem reason) |
| `TestConsoleMandatesEffectiveChanges` | 1 teste (governed aparece após approve) |
| `TestConsoleMandatesNavLink` | 1 teste |

**Total: 76 testes passando (21 novos para Etapa 3.4)**

---

## Funções Core a Reutilizar

| Função | Import |
|--------|--------|
| `propose_mandate_change()` | `engine.core.governed_mandates` |
| `decide_mandate_proposal()` | `engine.core.governed_mandates` |
| `list_mandate_proposals()` | `engine.core.governed_mandates` |
| `list_governed_mandates()` | `engine.core.governed_mandates` |
| `get_effective_mandates()` | `engine.core.governed_mandates` |
| `get_bundle_mandates()` | `engine.core.mandates` |

**Nota**: Chamar funções core diretamente (Python), não via HTTP.

---

## Decisões de Design

1. **Auth para POST**: Usar `require_admin_auth()` ou manter `verify_admin_token()`?
   - Recomendação: `verify_admin_token()` para simplicidade (console já usa)

2. **Redirect após POST**: Usar redirect HTTP ou HTMX swap?
   - Recomendação: Redirect HTTP tradicional para segurança

3. **Validação JSON no form**: Client-side ou apenas server-side?
   - Recomendação: Ambos (try/catch JS + schema no server)

4. **Rota `/apply` separada**: Necessária?
   - Recomendação: Não — `decide(approve)` já aplica automaticamente
