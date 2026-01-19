# Fase 2 — Etapa 2.8: AXIOM MVP (Mandatos Governados via EGE Proposals)

**Data:** 2026-01-18  
**Status:** DRAFT (autoridade da etapa)  
**Origem:** `docs/specs/fase-2/00-plano.md` (Etapa 2.8)

## Objetivo

Subir um nível acima dos gates: tornar **mandatos** objetos institucionais governados.

Em vez de “editar mandates.json no bundle”, a instituição cria/alterar/revoga mandatos via:

- **EGE proposal** → **aprovação** → **aplicação** → **audit ledger**

## Escopo

Inclui
- Modelo de “Mandate Proposal” (criar/revogar/alterar) versionado e auditável.
- Integração mínima com EGE proposals:
  - criar proposal
  - aprovar/rejeitar
  - aplicar mudança (gera novo estado institucional)
- Persistência e prova:
  - registrar ato no ledger
  - manter histórico

Não inclui
- UI
- Conselhos (councils)
- Políticas complexas de review graduada (pode vir depois)

## Princípios

- Nenhuma execução fora de mandato.
- Mandato é revogável.
- Mudança de mandato nunca é “por conversa” ou “por acesso direto ao arquivo”.

## Decisões canônicas (MVP)

1) **Escopo inicial**: governar apenas `mandates.json` do dept (não autonomy/policies nesta etapa).
2) **Formato**: manter schema de `mandates.json` já existente.
3) **Aplicação**: gerar uma nova versão de `mandates.json` em um “institution state store” governado, sem exigir rebuild completo do bundle.
   - Se isso não for possível no design atual, alternativa: gerar um novo bundle/release com mandates atualizados (mais pesado, mas consistente).

## Deliverables

1) `docs/specs/fase-2/02-8-axiom-mandates-governed/flow.md`
- Fluxo: proposal → approve → apply → audit.

2) Implementação mínima
- API/CLI para:
  - criar proposal de mandate
  - aprovar/rejeitar
  - aplicar mudança
- Eventos no ledger:
  - `MANDATE_PROPOSED`, `MANDATE_APPROVED`, `MANDATE_REJECTED`, `MANDATE_APPLIED`, `MANDATE_REVOKED`

3) Testes
- Criar mandate → não aplica até aprovado
- Aprovar → aplica e passa a permitir endpoint
- Revogar → bloqueia endpoint

## Definition of Done

- Mandates podem ser criados/revogados via mecanismo governado (EGE), com auditoria.
- Runtime passa a respeitar a versão de mandates aplicada pela instituição.
- Testes automatizados cobrem o fluxo.
