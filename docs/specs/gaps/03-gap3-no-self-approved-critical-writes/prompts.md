# GAP 3 — Prompts (Claude Code) (produção)

PROMPT 03.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/gaps/03-gap3-no-self-approved-critical-writes/spec.md`.
2) Mapear:
   - como approvals funciona hoje (core + API) e como finance usa
   - como legacy write decide e grava outbox hoje
3) Propor o patch mínimo para eliminar “self-approved” no legacy write, escolhendo:
   - Opção A: integrar com approvals subsystem (preferido)
   - Opção B: role explícita institucional (fallback)

Saída:
- `docs/specs/gaps/03-gap3-no-self-approved-critical-writes/gaps.md`
[[CLAUDE_CODE_END]]

PROMPT 03.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/gaps/03-gap3-no-self-approved-critical-writes/spec.md`.
2) Não mude para aplicar direto no legado. Continua outbox.

Reforços obrigatórios (produção, sem interpretação):
- O `endpoint_sig` para approvals do Legacy Write deve ser **canônico e estável**:
  - usar exatamente `POST /bridge/write/{action}` como assinatura base (igual pattern do runtime),
  - e usar `action` apenas como detalhe de payload (não criar N assinaturas por action).
- Em produção, “sem approvals configurados” **não pode** virar self-approved:
  - deve ser deny determinístico (erro estável) — não enfileirar.
- Nota de modo de produção:
  - Se `ENGINE_INSTALL_MODE` ainda não existir no código, implemente o mínimo necessário para distinguir `dev` vs `prod`
    (sem redesign), ou amarre o comportamento “produção” a uma condição já existente (ex.: `ENGINE_AUTH_MODE=strict`),
    mas deixe explícito no código e nos testes.
- Integração approvals deve ser real:
  - criar `approval_id` via approvals subsystem,
  - somente após `POST /approvals/{approval_id}/decide` (approve) enfileirar outbox.

Tarefa:
1) Remover/invalidar o comportamento “self-approved” no legacy write.
2) Implementar um caminho governado:
   - se approvals configurados para o endpoint_sig: criar approval request e retornar `202` (não enfileirar)
   - se approvals não configurados:
     - em produção: negar determinístico
     - em dev: permitir apenas com role `admin` + mandate válido (fallback compat)
3) Garantir ledger events determinísticos para:
   - intent
   - approval_requested/decided (se aplicável)
   - enqueued
4) Testes E2E para allow/deny e fluxo approval.

Saída:
- Patch mínimo + testes + update da doc do gap.
[[CLAUDE_CODE_END]]
