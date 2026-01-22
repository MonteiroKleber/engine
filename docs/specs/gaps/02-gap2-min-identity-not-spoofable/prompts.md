# GAP 2 — Prompts (Claude Code) (produção)

PROMPT 02.1 (Diagnóstico)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/gaps/02-gap2-min-identity-not-spoofable/spec.md`.
2) Mapear:
   - onde ActorContext é criado hoje
   - onde roles entram hoje
   - como ledger registra actor_id/roles hoje (para auditoria)
3) Propor o patch mínimo para `ENGINE_AUTH_MODE=strict`, incluindo:
   - storage do registry por instituição
   - formato do token e lookup
   - endpoints admin mínimos para provisionar/revogar tokens
   - erro determinístico

Saída:
- `docs/specs/gaps/02-gap2-min-identity-not-spoofable/gaps.md`
[[CLAUDE_CODE_END]]

PROMPT 02.2 (Implementação mínima)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/gaps/02-gap2-min-identity-not-spoofable/spec.md`.
2) Não implemente OAuth/JWT externos. Use somente storage local por instituição.

Reforços obrigatórios (produção, sem ambiguidade):
- `ENGINE_AUTH_MODE=strict` deve ignorar completamente headers não confiáveis:
  - ignorar `X-Actor-Id`
  - ignorar `X-Actor-Roles`
  - resolver `actor_id` e `roles` **somente** via token validado.
- Token deve ser aceito por:
  - `Authorization: Bearer <token>` (preferência)
  - ou `X-Actor-Token: <token>`
- O registry é sempre **por instituição**:
  - em strict, `X-Institution-Id` é obrigatório antes de qualquer lookup
  - token de uma instituição nunca pode autenticar em outra.
- Storage de token:
  - nunca persistir token em claro; persistir apenas `SHA256:<hex>` do token.
- Erros e auditoria:
  - negações em strict devem ser determinísticas (código estável) e gerar evento no ledger com `allowed=false` + `reason_code`.

Tarefa:
1) Implementar `ENGINE_AUTH_MODE` com `dev` e `strict`.
2) Implementar registry por instituição (append-only JSONL + state.json) para tokens de ator:
   - token -> actor_id + roles (+ opcional scopes)
3) Implementar endpoints admin mínimos para provisionamento:
   - criar token de ator
   - revogar token
   - listar atores
   (usar auth admin existente)
4) Atualizar `get_actor_context()` para:
   - em strict: exigir token, resolver actor+roles do registry, ignorar `X-Actor-Id` e `X-Actor-Roles`
   - em dev: manter compat e emitir evento UNVERIFIED_IDENTITY (ledger)
5) Adicionar testes E2E:
   - strict: rejeita spoof de roles
   - strict: aceita token válido
   - strict: token revogado falha
   - strict: token de instituição A não autentica em instituição B
   - provisionamento cria registry e emite evento no ledger (se aplicável)

Saída:
- Patch mínimo + testes + atualização da doc do gap.
[[CLAUDE_CODE_END]]
