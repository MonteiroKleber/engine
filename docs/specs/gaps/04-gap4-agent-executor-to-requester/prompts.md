# GAP 4 — Prompts (Claude Code) (produção)

PROMPT 04.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/gaps/04-gap4-agent-executor-to-requester/spec.md`.
2) Mapear:
   - onde actor_id/roles entram nos requests e eventos do ledger hoje
   - como Agent Ops faz query de denied hoje (evento/payload)
   - onde o legacy write faz deny/allow hoje
3) Propor o patch mínimo para:
   - suportar `on_behalf_of` com validação
   - criar request governado append-only quando negado
   - expor endpoints admin read-only mínimos para listar requests (operação)

Saída:
- `docs/specs/gaps/04-gap4-agent-executor-to-requester/gaps.md`
[[CLAUDE_CODE_END]]

PROMPT 04.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/gaps/04-gap4-agent-executor-to-requester/spec.md`.
2) Escopo mínimo: implementar para `POST /bridge/write/{action}`.

Reforços obrigatórios (produção, sem spoof):
- `on_behalf_of` só pode ser aceito quando **a identidade do caller é verificada**:
  - em `ENGINE_AUTH_MODE=strict`, o caller deve estar autenticado via token (GAP2).
  - em `ENGINE_AUTH_MODE=dev`, permitir apenas em testes/dev (e registrar como unverified).
- “Agent” precisa ser uma propriedade **do registry confiável**, não do request:
  - usar um campo explícito no actor registry (ex.: `is_agent=true`) ou uma role canônica `agent`,
    mas a decisão deve estar em storage por instituição e ser resolvida pelo engine.
- `on_behalf_of` não pode alterar permissões:
  - gates (RBAC/mandates/autonomy/policies/approvals) continuam avaliados sobre o actor real (agent),
    e `on_behalf_of` entra apenas como contexto/auditoria e para roteamento de solicitação.
- Anti-inference:
  - endpoints admin read-only devem respeitar `(institution_id, dept_id)` e retornar 404 quando aplicável.

Tarefa:
1) Implementar `on_behalf_of` como campo estruturado, validado e auditado.
2) Implementar storage append-only de “agent requests” por instituição/dept.
3) No deny do legacy write, criar automaticamente a solicitação e emitir evento `AGENT_REQUEST_CREATED`.
4) Expor endpoints admin read-only mínimos para consulta/listagem das solicitações.
5) Testes E2E para deny→request e validações.

Saída:
- Patch mínimo + testes + update da doc do gap.
[[CLAUDE_CODE_END]]
