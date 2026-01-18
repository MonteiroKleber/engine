# Etapa 06 — Prompts (Claude Code)

PROMPT 06.1
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-1/06-multi-institution-admin/spec.md`.
2) Mapeie no código:
   - como o `X-Institution-Id` é aplicado
   - como paths em disco são segregados
   - como admin keys e institution registry funcionam
3) Escreva:
   - `docs/specs/fase-1/06-multi-institution-admin/isolation.md`
   - `docs/specs/fase-1/06-multi-institution-admin/admin-auth.md`

Regras:
- Se não houver testes de isolamento cross-tenant, marque como gap.
[[CLAUDE_CODE_END]]

PROMPT 06.2
[[CLAUDE_CODE_START]]
Se houver gaps de isolamento/admin:
1) Implemente o mínimo necessário (sem refactor amplo).
2) Adicione testes cross-tenant que provem isolamento (path traversal, inference, etc.).
3) Garanta eventos no ledger para uso/negação de admin.
[[CLAUDE_CODE_END]]

