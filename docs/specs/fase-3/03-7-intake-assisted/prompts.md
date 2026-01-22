# Fase 3 — Etapa 3.7: Prompts (Claude Code)

PROMPT 3.7.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-7-intake-assisted/spec.md` e siga como contrato.
2) Mapear no código:
   - qual pipeline NL/SIR/Draft/Gaps/Finalize existe hoje
   - onde são persistidos drafts/runs
   - como o DSL→IR (idl_dsl) pode ser usado como fallback
3) Produzir:
   - `docs/specs/fase-3/03-7-intake-assisted/gaps.md` (gaps + plano mínimo)
   - `docs/specs/fase-3/03-7-intake-assisted/api.md` (rotas e modelos)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 3.7.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Fluxo assistido apenas. Sem deploy, sem apply, sem ações mutáveis em produção.

Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-3/03-7-intake-assisted/spec.md` e siga como contrato.
2) Implementar rotas e templates do console para intake:
   - input texto
   - draft + gaps
   - finalize com respostas
   - export (IR/DSL)
3) Garantir fallback: se NL pipeline não estiver disponível, aceitar DSL colado e gerar IR via `engine.idl_dsl`.
4) Adicionar testes para fluxo e export.
5) Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
