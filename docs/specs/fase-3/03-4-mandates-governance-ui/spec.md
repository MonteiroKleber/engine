# Fase 3 — Etapa 3.4: UI de Governança Operacional (Mandatos)

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-3/00-plano.md` (Etapa 3.4)

## Objetivo

Adicionar ao console uma UI mínima para operar **mandatos governados** de forma segura.

Isso é a primeira etapa do console que envolve mutação, então o foco é:
- ações governadas (proposal/decide/apply)
- confirmação explícita
- evidência e trilha (ledger)

## Escopo

Inclui
- Páginas no console para:
  - listar mandatos efetivos (bundle vs governado)
  - listar proposals
  - criar proposal (create/update/revoke)
  - decidir (approve/reject)
  - aplicar (apply) quando aprovado
- Mostrar diffs simples:
  - “antes/depois” do mandato efetivo

Não inclui
- UI genérica para policies/autonomy
- chat

## Regras não negociáveis

- Nenhuma mutação direta em arquivo. Tudo passa por proposal.
- As rotas do console que mutam devem ser **restritas** e usar o mesmo auth do admin.
- Toda mutação deve registrar evento no ledger (já existe no core).

## Endpoints

Reusar os endpoints já implementados em `admin_mandates.py`:
- `POST /admin/mandates/proposals`
- `POST /admin/mandates/proposals/{id}/decide`
- `GET /admin/mandates/proposals`
- `GET /admin/mandates/governed`
- `GET /admin/mandates/effective`

O console pode chamar esses endpoints internamente (Python) ou via HTTP, mas preferir chamada interna para manter simples.

## Entregas mínimas

1) Rotas console
- `GET /console/mandates?institution_id=...&dept_id=...`
- `GET /console/mandates/proposals?institution_id=...&dept_id=...`
- `GET /console/mandates/proposals/new?institution_id=...&dept_id=...`
- `POST /console/mandates/proposals` (submete proposal)
- `POST /console/mandates/proposals/{id}/decide` (approve/reject)
- `POST /console/mandates/proposals/{id}/apply`

2) Templates
- listagem + detalhes
- forms simples com validação mínima

3) Testes
- exige `X-Admin-Token`
- GET read pages funcionam
- POSTs chamam o core e retornam redirect/resultado

## Definition of Done

- Operador consegue governar mandatos via console com segurança:
  - criar proposal
  - aprovar
  - aplicar
  - ver efetivo

