# Fase 5 — Etapa 5.2: Prompts (Claude Code)

PROMPT 5.2.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-5/05-2-intake-dept-workspace/spec.md` e siga como contrato.
2) Mapear:
   - como o console intake (Etapa 3.7) funciona hoje e onde guarda state
   - como o DSL→IRCS funciona (engine.idl_dsl)
   - onde armazenar artefatos por instituição/dept (data root)
3) Produzir nesta pasta:
   - `api.md` (rotas console + modelos)
   - `gaps.md` (gaps + plano mínimo)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 5.2.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Decisão oficial desta etapa:
- Workspace é por dept: cada definição tem `(institution_id, dept_id)` e guarda DSL + IRCS.

Tarefa:
1) Implementar UI read-mostly no console para:
   - criar/upload DSL por dept
   - gerar IRCS e armazenar no workspace
   - listar versões por dept (mínimo: latest + timestamp)
2) Adicionar testes do fluxo.
3) Atualizar `api.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]

