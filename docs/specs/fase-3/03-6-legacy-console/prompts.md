# Fase 3 — Etapa 3.6: Prompts (Claude Code)

PROMPT 3.6.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-6-legacy-console/spec.md` e siga como contrato.
2) Mapear:
   - APIs/CLI disponíveis em `engine.legacy_bridge` (register/list/verify)
   - como o console atual resolve institution/dept context
   - o placeholder atual de `/console/legacy`
3) Produzir:
   - `docs/specs/fase-3/03-6-legacy-console/gaps.md`
   - `docs/specs/fase-3/03-6-legacy-console/api.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 3.6.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Permitir apenas uma ação mutável: `POST verify` (read-only no legado), com confirmação simples.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-6-legacy-console/spec.md` e siga como contrato.
2) Implementar rotas e templates para legacy assets:
   - listagem
   - detalhe
   - verify
3) Adicionar testes cobrindo auth e verify drift.
4) Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
