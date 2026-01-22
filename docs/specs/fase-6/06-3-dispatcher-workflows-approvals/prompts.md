# Etapa 6.3 — Prompts (Claude Code)

PROMPT 6.3.1 (Diagnóstico: approvals no legacy → dispatcher)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-6/06-3-dispatcher-workflows-approvals/spec.md` e siga como contrato.
2) Mapeie com evidências:
   - como approvals são criados e decididos hoje (core + API)
   - onde SoD/invariants entram no fluxo de approvals/commit
   - quais estruturas do state store guardam approval_index (se existir) e cases
3) Proponha o patch mínimo para implementar no dispatcher:
   - approval request
   - approval decide
   reutilizando motores existentes (sem duplicação).

Saída esperada (nesta pasta):
- `docs/specs/fase-6/06-3-dispatcher-workflows-approvals/map.md`
- `docs/specs/fase-6/06-3-dispatcher-workflows-approvals/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 6.3.2 (Implementação mínima: dispatcher v2)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/fase-6/06-3-dispatcher-workflows-approvals/spec.md`.
2) Não implementar rotas dinâmicas nesta etapa.
3) IMPORTANTE (escopo realista):
   - **Não implementar workflow/transition genérico** nesta etapa.
     O engine hoje não possui um workflow engine genérico que interprete `workflows.json`.
     Esta etapa é sobre approvals + commit/reject reaproveitando o que já existe.

Tarefa:
1) Implementar no dispatcher:
   - `dispatch_approval_request(...)`
   - `dispatch_approval_decide(...)`
2) Reusar motores existentes:
   - approvals engine (criar/decidir)
   - SoD/invariants/policies/mandates/autonomy emitters
3) Testes obrigatórios (via dispatcher, sem HTTP):
   - fluxo Finance completo: create → pending_approval → self-approve deny → manager approve COMMITTED
    - fluxo reject (se houver operação)
   - isolamento 2 instituições × 2 depts
4) Atualizar docs:
   - `spec.md` status IMPLEMENTADO
   - `map.md` e `gaps.md` com evidências.

Restrições:
- Não alterar semântica dos gates.
- Não remover rotas legacy.
- Mudanças mínimas e com testes.
[[CLAUDE_CODE_END]]
