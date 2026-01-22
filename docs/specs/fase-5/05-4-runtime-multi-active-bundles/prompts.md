# Fase 5 — Etapa 5.4: Prompts (Claude Code)

PROMPT 5.4.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-5/05-4-runtime-multi-active-bundles/spec.md` e siga como contrato.
2) Mapear:
   - routing atual por dept
   - loader single vs multi-mode
   - onde está o “bundle ativo” por instituição hoje
3) Propor a mudança mínima para suportar “active bundle por dept”.
4) Produzir:
   - `flow.md`
   - `gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 5.4.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Implementar suporte a múltiplos bundles ativos por instituição (por dept).
2) Adicionar testes E2E para 2 depts ativos com bundles separados.
3) Atualizar `flow.md` e `gaps.md`.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]

