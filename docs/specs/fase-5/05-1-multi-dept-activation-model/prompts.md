# Fase 5 — Etapa 5.1: Prompts (Claude Code)

PROMPT 5.1.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-5/05-1-multi-dept-activation-model/spec.md` e siga como contrato.
2) Mapear no código atual:
   - como o runtime resolve dept hoje (routing e loader)
   - onde existe o conceito de CURRENT/pinned por instituição
   - como multi-dept funciona hoje (bundle multi-mode vs single)
3) Propor o modelo canônico mínimo para “active depts set”:
   - storage (por instituição)
   - formato (determinístico)
   - eventos no ledger
   - compatibilidade com o modo atual (não quebrar)
4) Produzir nesta pasta:
   - `flow.md` (diagramas + precedência)
   - `gaps.md` (o que falta para implementar)

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 5.1.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-5/05-1-multi-dept-activation-model/spec.md` e siga como contrato.
2) Implementar o modelo canônico de “active depts set” com mudanças mínimas e backward-compatible.
3) Adicionar testes focados em:
   - resolução do bundle por dept
   - isolamento (2 instituições × 2 depts)
4) Atualizar `flow.md` e `gaps.md` com status final.

Saída esperada:
- Patch mínimo + testes + docs.
[[CLAUDE_CODE_END]]

