# UX — Etapa 3.4: UI de Governança Operacional (Mandatos)

**Data:** 2026-01-19
**Status:** IMPLEMENTADO (PROMPT 3.4.2)
**Prompt inicial:** 3.4.1 (Diagnóstico)

## Personas

1. **Operador/Admin**: Precisa governar mandatos de forma segura
2. **Auditor/CTO**: Precisa verificar que mudanças seguem workflow

## Fluxos Principais

### Fluxo 1: Visualizar Mandatos Efetivos

```
[Home] --> [Status] --> [Mandates]
                            │
                            ├── Ver mandatos efetivos (bundle + governed)
                            ├── Ver fonte de cada mandato (bundle/governed)
                            └── Link para "Ver Proposals"
```

### Fluxo 2: Criar Nova Proposal

```
[Mandates] --> [Proposals] --> [+ Nova Proposal]
                                      │
                                      ├── Selecionar operation (create/update/revoke)
                                      ├── Informar mandate_id
                                      ├── Informar mandate_data (JSON)
                                      ├── Informar reason
                                      └── [Submeter]
                                            │
                                            ▼
                                      [Proposals List] (com nova proposal OPEN)
```

### Fluxo 3: Aprovar/Rejeitar Proposal

```
[Proposals] --> [Proposal Detail]
                      │
                      ├── Ver detalhes da proposal
                      ├── Ver diff (antes/depois)
                      └── Formulário decide:
                            ├── [Aprovar] (com reason opcional)
                            └── [Rejeitar] (com reason obrigatório)
                                  │
                                  ▼
                            [Proposals List] (status DECIDED)
```

---

## Telas

### Tela 1: Mandates (Lista Efetivos)

**Rota**: `GET /console/mandates?institution_id=...&dept_id=...`

**Layout**:
```
┌─────────────────────────────────────────────────────────────────┐
│ AXIOM Console                            [Home] [Mandates] ...  │
├─────────────────────────────────────────────────────────────────┤
│ Context: Institution Name / dept-a                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ┌─ Effective Mandates ──────────────────────────────────────┐  │
│ │ Source: merged (bundle + governed)                        │  │
│ │                                                           │  │
│ │ ┌────────────┬─────────────────┬───────┬─────────────┐   │  │
│ │ │ Mandate ID │ Endpoint        │ Phase │ Roles       │   │  │
│ │ ├────────────┼─────────────────┼───────┼─────────────┤   │  │
│ │ │ M001       │ POST /invoices  │ PRE   │ admin,mgr   │   │  │
│ │ │ M002 (gov) │ POST /payments  │ POST  │ admin       │   │  │
│ │ │ M003       │ PUT /contracts  │ PRE   │ admin       │   │  │
│ │ └────────────┴─────────────────┴───────┴─────────────┘   │  │
│ │                                                           │  │
│ │ [View Proposals] [+ New Proposal]                         │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ ┌─ Governed Mandates (Overrides) ───────────────────────────┐  │
│ │ 2 mandates governados atualmente                          │  │
│ │                                                           │  │
│ │ • M002: created via proposal abc-123 (2026-01-19)         │  │
│ │ • M005: revoked (não aparece nos efetivos)                │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Dados**:
- Lista de mandatos efetivos (via `get_effective_mandates()`)
- Lista de mandatos governados (via `list_governed_mandates()`)
- Source: "bundle", "governed", ou "merged"

---

### Tela 2: Proposals (Lista)

**Rota**: `GET /console/mandates/proposals?institution_id=...&dept_id=...`

**Layout**:
```
┌─────────────────────────────────────────────────────────────────┐
│ AXIOM Console                            [Home] [Mandates] ...  │
├─────────────────────────────────────────────────────────────────┤
│ Context: Institution Name / dept-a                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ┌─ Mandate Proposals ───────────────────────────────────────┐  │
│ │                                                           │  │
│ │ [+ New Proposal]                        Filter: [All ▼]   │  │
│ │                                                           │  │
│ │ ┌────────┬──────────┬─────────┬─────────┬──────────────┐ │  │
│ │ │ Status │ Operation│ Mandate │ Created │ Action       │ │  │
│ │ ├────────┼──────────┼─────────┼─────────┼──────────────┤ │  │
│ │ │ [OPEN] │ create   │ M010    │ 5m ago  │ [View]       │ │  │
│ │ │ [OPEN] │ update   │ M002    │ 1h ago  │ [View]       │ │  │
│ │ │ [APPR] │ create   │ M008    │ 2h ago  │ [View]       │ │  │
│ │ │ [REJ]  │ revoke   │ M001    │ 1d ago  │ [View]       │ │  │
│ │ └────────┴──────────┴─────────┴─────────┴──────────────┘ │  │
│ │                                                           │  │
│ │ Showing 4 proposals                                       │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Badges**:
- `[OPEN]` - badge-unpinned (cinza)
- `[APPR]` - badge-active (verde)
- `[REJ]` - badge-error (vermelho)

**Dados**:
- Lista via `list_mandate_proposals(institution_id, dept_id)`

---

### Tela 3: New Proposal (Form)

**Rota**: `GET /console/mandates/proposals/new?institution_id=...&dept_id=...`

**Layout**:
```
┌─────────────────────────────────────────────────────────────────┐
│ AXIOM Console                            [Home] [Mandates] ...  │
├─────────────────────────────────────────────────────────────────┤
│ Context: Institution Name / dept-a                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ┌─ Create Mandate Proposal ─────────────────────────────────┐  │
│ │                                                           │  │
│ │ Operation:                                                │  │
│ │ (•) Create new mandate                                    │  │
│ │ ( ) Update existing mandate                               │  │
│ │ ( ) Revoke mandate                                        │  │
│ │                                                           │  │
│ │ Mandate ID: [________________________]                    │  │
│ │                                                           │  │
│ │ Mandate Data (JSON):                                      │  │
│ │ ┌─────────────────────────────────────────────────────┐  │  │
│ │ │ {                                                   │  │  │
│ │ │   "mandate_id": "M010",                             │  │  │
│ │ │   "endpoint_sig": "POST /api/invoices",             │  │  │
│ │ │   "phase": "PRE",                                   │  │  │
│ │ │   "allowed_roles": ["admin", "manager"],            │  │  │
│ │ │   "limits": []                                      │  │  │
│ │ │ }                                                   │  │  │
│ │ └─────────────────────────────────────────────────────┘  │  │
│ │                                                           │  │
│ │ Reason for proposal:                                      │  │
│ │ ┌─────────────────────────────────────────────────────┐  │  │
│ │ │ Adding new mandate for invoice creation workflow    │  │  │
│ │ └─────────────────────────────────────────────────────┘  │  │
│ │                                                           │  │
│ │ [Cancel]                            [Submit Proposal]     │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Validação client-side**:
- mandate_id: obrigatório
- mandate_data: JSON válido (para create/update)
- reason: obrigatório

**POST**: `/console/mandates/proposals`
- Redirect para lista com success/error message

---

### Tela 4: Proposal Detail + Decide

**Rota**: `GET /console/mandates/proposals/{id}?institution_id=...&dept_id=...`

**Layout (OPEN proposal)**:
```
┌─────────────────────────────────────────────────────────────────┐
│ AXIOM Console                            [Home] [Mandates] ...  │
├─────────────────────────────────────────────────────────────────┤
│ Context: Institution Name / dept-a                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ┌─ Proposal: abc-1234 ──────────────────────────── [OPEN] ──┐  │
│ │                                                           │  │
│ │ Operation: UPDATE                                         │  │
│ │ Mandate: M002                                             │  │
│ │ Created: 2026-01-19T10:30:00Z by admin                    │  │
│ │ Reason: "Updating allowed roles to include finance team"  │  │
│ │                                                           │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ ┌─ Diff: Before → After ────────────────────────────────────┐  │
│ │                                                           │  │
│ │ CURRENT (bundle)            PROPOSED                      │  │
│ │ ┌─────────────────────┐    ┌─────────────────────┐       │  │
│ │ │ {                   │    │ {                   │       │  │
│ │ │   "mandate_id":     │    │   "mandate_id":     │       │  │
│ │ │     "M002",         │    │     "M002",         │       │  │
│ │ │   "allowed_roles":  │    │   "allowed_roles":  │       │  │
│ │ │     ["admin"]       │ →  │     ["admin",       │       │  │
│ │ │ }                   │    │      "finance"]     │       │  │
│ │ └─────────────────────┘    │ }                   │       │  │
│ │                            └─────────────────────┘       │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ ┌─ Decision ────────────────────────────────────────────────┐  │
│ │                                                           │  │
│ │ (•) Approve                                               │  │
│ │ ( ) Reject                                                │  │
│ │                                                           │  │
│ │ Reason (required for reject):                             │  │
│ │ ┌─────────────────────────────────────────────────────┐  │  │
│ │ │                                                     │  │  │
│ │ └─────────────────────────────────────────────────────┘  │  │
│ │                                                           │  │
│ │ [Cancel]                              [Submit Decision]   │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Layout (DECIDED proposal)**: Mesmo, mas sem form de decisão e com resultado mostrado.

---

## Componentes UI

### Badge de Status

| Status | Classe | Cor |
|--------|--------|-----|
| OPEN | badge-unpinned | cinza |
| APPROVED | badge-active | verde |
| REJECTED | badge-error | vermelho |

### Diff Component

Para mostrar antes/depois:
```html
<div class="grid grid-2">
    <div class="card">
        <h4>Current</h4>
        <pre class="code-block">{{ current_data | tojson(indent=2) }}</pre>
    </div>
    <div class="card">
        <h4>Proposed</h4>
        <pre class="code-block">{{ proposed_data | tojson(indent=2) }}</pre>
    </div>
</div>
```

### Form de Proposal

```html
<form method="POST" action="/console/mandates/proposals">
    <input type="hidden" name="institution_id" value="{{ institution_id }}">
    <input type="hidden" name="dept_id" value="{{ dept_id }}">

    <div class="form-group">
        <label>Operation</label>
        <select name="operation" required>
            <option value="create">Create new mandate</option>
            <option value="update">Update existing mandate</option>
            <option value="revoke">Revoke mandate</option>
        </select>
    </div>

    <div class="form-group">
        <label>Mandate ID</label>
        <input type="text" name="mandate_id" required>
    </div>

    <div class="form-group" id="mandate-data-group">
        <label>Mandate Data (JSON)</label>
        <textarea name="mandate_data" rows="10"></textarea>
    </div>

    <div class="form-group">
        <label>Reason</label>
        <textarea name="reason" required></textarea>
    </div>

    <button type="submit">Submit Proposal</button>
</form>
```

---

## Rotas Summary

| Rota | Método | Template | Ação |
|------|--------|----------|------|
| `/console/mandates` | GET | mandates.html | Lista efetivos |
| `/console/mandates/proposals` | GET | mandates_proposals.html | Lista proposals |
| `/console/mandates/proposals/new` | GET | mandates_proposal_new.html | Form criar |
| `/console/mandates/proposals` | POST | - | Cria proposal, redirect |
| `/console/mandates/proposals/{id}` | GET | mandates_proposal_detail.html | Detalhe + decide |
| `/console/mandates/proposals/{id}/decide` | POST | - | Decide, redirect |

---

## Mensagens de Feedback

### Success Messages
- "Proposal created successfully" (após criar)
- "Proposal approved and mandate applied" (após aprovar)
- "Proposal rejected" (após rejeitar)

### Error Messages
- "Invalid JSON in mandate_data"
- "Mandate already exists" (para create)
- "Mandate not found" (para update/revoke)
- "Proposal already decided"

---

## Considerações de Segurança

1. **Todas as rotas POST** requerem `X-Admin-Token` válido
2. **CSRF**: Usar token no form ou confiar em header HTMX
3. **Validação server-side**: Sempre validar mandate_data via schema
4. **Confirmação**: Para approve, mostrar diff e pedir confirmação
5. **Audit Trail**: Todas as ações já emitem eventos no ledger
