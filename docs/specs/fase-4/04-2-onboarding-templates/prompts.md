# Fase 4 — Etapa 4.2: Prompts (Claude Code)

PROMPT 4.2.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-2-onboarding-templates/spec.md` e siga como contrato.
2) Mapear:
   - como criar/listar instituições hoje (registry/admin)
   - onde ficam bundles por instituição (bundles root / releases)
   - como rodar proof programaticamente (engine.proof)
   - quais bundles podem ser usados como templates iniciais
3) Produzir:
   - `docs/specs/fase-4/04-2-onboarding-templates/gaps.md`
   - `docs/specs/fase-4/04-2-onboarding-templates/api.md` (rotas console + modelos)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 4.2.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Onboarding deve sempre executar proof verify e bloquear “pronto” se FAIL.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-2-onboarding-templates/spec.md` e siga como contrato.
2) Implementar UI e rotas de onboarding no console.
3) Implementar registry simples de templates (lista fixa inicial) e geração de bundle por instituição.
4) Integrar proof verify e exibir report.
5) Adicionar testes para happy-path e fail-path.
6) Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
