# Fase 2 — Etapa 2.8: Prompts (Claude Code)

PROMPT 2.8.1 (Diagnóstico + decisão de aplicação)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-2/02-8-axiom-mandates-governed/spec.md` e siga como contrato.
2) Mapeie:
   - onde `mandates.json` é carregado hoje (bundle/dept)
   - se existe algum state store institucional que possa sobrescrever contracts do bundle
   - como o EGE proposal/pin funciona hoje
3) Proponha a opção mínima para “aplicar mandate governado”:
   - Opção A: override governado de mandates (sem rebuild)
   - Opção B: novo bundle/release (com rebuild)
4) Produza:
   - `docs/specs/fase-2/02-8-axiom-mandates-governed/flow.md`
   - `docs/specs/fase-2/02-8-axiom-mandates-governed/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 2.8.2 (Implementação única: Mandatos Governados end-to-end)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Implementar **Opção A**: override governado de `mandates.json` (sem rebuild de bundle/release).
- Precedência: mandates governados (instituição) **sobrescrevem** mandates do bundle para o mesmo `(institution_id, dept_id)`.
- Persistência: append-only (JSONL) + audit ledger.

Você está no repositório `/home/bazari/engine`.

Tarefa (end-to-end, em um único patch):

A) Storage governado (append-only)
1) Criar módulo `src/engine/core/governed_mandates.py` (ou nome equivalente claro) com:
   - modelo de registro (institution_id, dept_id, mandate_id, action=create|revoke|update, payload, created_at)
   - persistência append-only em JSONL dentro do namespace da instituição
   - funções:
     - `propose_mandate_change(...)` (não aplica)
     - `decide_mandate_change(...)` (approve/reject)
     - `apply_mandate_change(...)` (gera estado efetivo)
     - `get_effective_mandates(institution_id, dept_id)`
   - validação determinística de schema (reusar validação do runtime `mandates.json` se existir)

B) Integração com EGE proposals
2) Integrar com o mecanismo existente de proposals do EGE:
   - criar proposal do tipo “MANDATE_CHANGE”
   - aprovar/rejeitar
   - aplicar somente após aprovado

C) Integração no runtime (lookup)
3) Alterar o runtime para carregar mandates efetivos assim:
   - primeiro verificar override governado (se existir)
   - senão usar `mandates.json` do bundle
4) Garantir isolamento por `(institution_id, dept_id)`.

D) API/CLI mínima
5) Expor endpoints (admin) ou CLI (mínimo aceitável para MVP) para:
   - criar proposal de mandato
   - aprovar/rejeitar
   - aplicar/revogar

E) Hot reload / consistência
6) Garantir que mudança aplicada entra em vigor sem restart perigoso:
   - opção simples: recarregar mandates efetivos em cada request (com cache curto)
   - ou invalidar cache no apply

F) Ledger events (prova)
7) Emitir eventos determinísticos no ledger:
   - `MANDATE_PROPOSED`
   - `MANDATE_APPROVED`
   - `MANDATE_REJECTED`
   - `MANDATE_APPLIED`
   - `MANDATE_REVOKED`

G) Testes obrigatórios (E2E)
8) Cobrir com testes:
   - mandato proposto não muda execução
   - após aprovação+apply, endpoint passa a permitir (antes negava)
   - revogação volta a negar
   - isolamento: mudança em (A, finance) não afeta (A, support) nem (B, finance)

Documentação
- Atualizar `docs/specs/fase-2/02-8-axiom-mandates-governed/flow.md` e `docs/specs/fase-2/02-8-axiom-mandates-governed/gaps.md` marcando gaps fechados.

Restrições
- Mudanças mínimas, com testes.
- Não introduzir UI.
- Não permitir “editar arquivo de mandates” direto como caminho privilegiado.
[[CLAUDE_CODE_END]]
