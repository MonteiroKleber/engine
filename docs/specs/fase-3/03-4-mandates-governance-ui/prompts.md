# Fase 3 — Etapa 3.4: Prompts (Claude Code)

PROMPT 3.4.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-4-mandates-governance-ui/spec.md` e siga como contrato.
2) Mapear:
   - como `admin_mandates.py` está exposto (rotas, auth)
   - como o console atual faz auth e render
   - como chamar o core `governed_mandates.py` de dentro do console
3) Produzir:
   - `docs/specs/fase-3/03-4-mandates-governance-ui/gaps.md`
   - `docs/specs/fase-3/03-4-mandates-governance-ui/ux.md` (telas mínimas e fluxos)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 3.4.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Todas as ações mutáveis no console devem ser governadas (proposal/decide/apply) e exigir `X-Admin-Token`.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-4-mandates-governance-ui/spec.md` e siga como contrato.
2) Implementar as rotas e templates do console para governança de mandatos.
3) Implementar forms e redirects simples, sem JS pesado.
4) Adicionar testes cobrindo:
   - auth
   - create proposal
   - approve/reject
   - apply
   - efetivo muda (smoke)
5) Atualizar `gaps.md` e `ux.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
