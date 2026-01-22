# Fase 5 — Etapa 5.3: Prompts (Claude Code)

PROMPT 5.3.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-5/05-3-ise-compile-dept-package/spec.md` e siga como contrato.
2) Mapear:
   - onde o ISE compila IRCS hoje (`compile-ircs`)
   - onde bundles por instituição são armazenados (onboarding/templates)
   - como proof é executado e bloqueia “ready”
3) Propor o path canônico para bundles por dept.
4) Produzir nesta pasta:
   - `flow.md`
   - `gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 5.3.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Decisão oficial desta etapa:
- Um “dept package” é um bundle com contratos do dept e `source_idl_sha256` real.

Tarefa:
1) Implementar caminho “workspace dept IRCS” → “bundle por dept” (com proof PASS).
2) Adicionar testes E2E: DSL (dept) → IRCS → bundle → loader ACTIVE.
3) Atualizar `flow.md` e `gaps.md`.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]

