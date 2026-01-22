# Fase 5 — Etapa 5.5: Prompts (Claude Code)

PROMPT 5.5.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-5/05-5-console-context-ux/spec.md` e siga como contrato.
2) Mapear quais páginas são:
   - institucionais (global)
   - por dept
3) Propor UX mínima para reduzir confusão sem rework grande.
4) Produzir:
   - `ux.md`
   - `gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 5.5.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Decisão oficial desta etapa:
- Cada página deve declarar explicitamente seu escopo (institution-only vs dept-scoped).

Tarefa:
1) Implementar ajustes mínimos de UX e contexto.
2) Adicionar testes de navegação (preservação de contexto).
3) Atualizar `ux.md` e `gaps.md`.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]

