# Fase 5 — Etapa 5.6: Prompts (Claude Code)

PROMPT 5.6.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-5/05-6-ege-per-dept-evolution/spec.md` e siga como contrato.
2) Mapear estado atual do EGE:
   - proposals/pins
   - rollback governado
   - traces
3) Identificar o que precisa virar “por dept” (storage, API, console).
4) Produzir:
   - `flow.md`
   - `gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 5.6.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Implementar pin/drift/rollback por dept com mudanças mínimas.
2) Adicionar testes de isolamento.
3) Atualizar `flow.md` e `gaps.md`.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]

