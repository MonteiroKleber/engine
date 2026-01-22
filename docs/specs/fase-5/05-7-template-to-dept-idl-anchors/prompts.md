# Fase 5 — Etapa 5.7: Prompts (Claude Code)

PROMPT 5.7.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-5/05-7-template-to-dept-idl-anchors/spec.md` e siga como contrato.
2) Mapear:
   - como onboarding gera bundles hoje (templates)
   - onde `source_idl_sha256` fica placeholder
   - como persistir seed DSL/IR por dept no data root
3) Produzir:
   - `flow.md`
   - `gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 5.7.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Decisão oficial desta etapa:
- Templates devem gerar/registrar seed DSL/IR por dept e usar `source_idl_sha256` real.

Tarefa:
1) Implementar seed DSL/IR por dept no onboarding, com hash UTF-8.
2) Garantir que bundles gerados tenham `source_idl_sha256` consistente com a seed.
3) Adicionar testes.
4) Atualizar `flow.md` e `gaps.md`.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]

