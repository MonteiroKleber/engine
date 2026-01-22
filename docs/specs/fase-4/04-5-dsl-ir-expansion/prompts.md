# Fase 4 — Etapa 4.5: Prompts (Claude Code)

PROMPT 4.5.1 (Diagnóstico + proposta de mudanças)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-4/04-5-dsl-ir-expansion/spec.md` e siga como contrato.
2) Mapear limitações atuais do `engine.idl_dsl` (subset) e do IRCS v1.
3) Propor um pacote pequeno de mudanças (max 5) que tragam valor imediato ao produto:
   - ex.: melhor suporte de operations, validações mais claras, tipos adicionais, melhor erro
4) Produzir:
   - `docs/specs/fase-4/04-5-dsl-ir-expansion/changes.md`
   - `docs/specs/fase-4/04-5-dsl-ir-expansion/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 4.5.2 (Implementação mínima)
[[CLAUDE_CODE_START]]

Decisão oficial desta etapa:
- Implementar apenas as mudanças listadas em `changes.md` (nada além).

Você está no repositório `/home/bazari/engine`.

Contrato (obrigatório):
1) Siga `docs/specs/fase-4/04-5-dsl-ir-expansion/spec.md`.
2) Implemente **somente** o que está listado em `docs/specs/fase-4/04-5-dsl-ir-expansion/changes.md`.
   - Se algo não estiver explicitamente em `changes.md`, não implemente.

Tarefa:
1) Implementar as mudanças aprovadas no `engine.idl_dsl` (parser/validações) e no IRCS emitter/schema, **somente conforme `changes.md`**.
2) Atualizar testes existentes e adicionar novos testes para cobrir cada mudança (um teste mínimo por mudança).
3) Garantir não regressão:
   - `examples/finance.idl` continua parseando e emitindo IR determinístico.
   - `PYTHONPATH=src python -m engine.idl_dsl examples/finance.idl --stdout` funciona.
4) Atualizar `docs/specs/fase-4/04-5-dsl-ir-expansion/gaps.md` com status final (gaps fechados vs aceitos, e evidências).

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]
