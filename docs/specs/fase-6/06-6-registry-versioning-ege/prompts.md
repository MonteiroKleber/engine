# Etapa 6.6 — Prompts (Claude Code)

PROMPT 6.6.1 (Diagnóstico: EGE ↔ versão ativa ↔ router/openapi)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Tarefa:
1) Leia `docs/specs/fase-6/06-6-registry-versioning-ege/spec.md` e siga como contrato.
2) Mapeie com evidências:
   - como o “release ativo” é definido por instituição (CURRENT symlink / config / pins)
   - onde EGE aplica pin e onde rollback governa a reversão
   - como `load_bundle()` escolhe o bundle ativo
   - como o dynamic router 6.4 resolve `OperationSpec` em runtime (cache vs lookup)
   - como `/openapi.json` é gerado (6.5) e se depende de estado em memória
3) Identifique o menor ponto de integração para disparar reload governado ao aplicar pin/rollback.

Saída esperada (nesta pasta):
- `docs/specs/fase-6/06-6-registry-versioning-ege/map.md`
- `docs/specs/fase-6/06-6-registry-versioning-ege/gaps.md`

Restrições:
- Não implementar mudanças neste prompt.
[[CLAUDE_CODE_END]]

PROMPT 6.6.2 (Implementação mínima: reload governado + snapshot)
[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/fase-6/06-6-registry-versioning-ege/spec.md`.
2) Mudanças mínimas, sem redesenhar EGE.
3) Limitação aceita nesta etapa (FastAPI):
   - Não tentar remover/re-registrar rotas em runtime.
   - O objetivo do hot-swap é manter **consistência** para rotas já registradas: execução + OpenAPI + snapshot.
   - Rotas novas (paths/methods novos) podem exigir restart (aceito nesta etapa).
4) IMPORTANTE:
   - O handler do router dinâmico (6.4) **não pode** capturar `OperationSpec` em closure no momento do registro.
     Ele deve resolver o `OperationSpec` em runtime (por lookup) para refletir o registry recarregado.

Tarefa:
1) Implementar `ActiveRuntimeSnapshot` por instituição e `reload_active_runtime(institution_id, reason)`.
2) No boot:
   - preencher snapshot com `active_release_id`, `manifest_hash`, `operations_hash`.
3) Integrar com EGE:
   - ao aplicar pin e ao executar rollback governado, chamar `reload_active_runtime(...)`.
4) Garantir que OpenAPI reflita o registry/snapshot atual:
   - `/openapi.json` e `/d/{dept_id}/openapi.json` não podem ficar “stale”.
5) Ledger event:
   - emitir `RUNTIME_RELOADED` (ou equivalente já existente) com hashes.
6) Testes:
   - simular duas versões de bundle em `tmp_path`, alternar “ativo”, chamar reload e validar:
     - snapshot mudou
     - openapi mudou (operationId/paths)
     - dispatcher continua funcionando para uma rota que só existe na versão ativa.

Documentação:
- Atualizar `spec.md` status IMPLEMENTADO
- Atualizar `map.md` e `gaps.md` com evidências.

Restrições:
- Não exigir restart do processo para refletir mudança.
- Não introduzir polling por request como mecanismo principal.
[[CLAUDE_CODE_END]]
