# Prompts — Expansão 03 (Approvals genéricos — Bazari)

## PROMPT 03.1 (Implementação mínima: approvals para `ModerationAction`)

[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/expansao/03-approvals-cases-bazari/spec.md`.
2) Mudança mínima e incremental: apenas o necessário para approvals “case genérico” do Bazari.
3) Não alterar auth nem o router dinâmico.
4) Regressão proibida: Finance/ACME/multi-pilot continuam passando.
5) **Proibido deletar qualquer coisa** fora da allowlist (inclui arquivos untracked). Se precisar “limpar”, faça via `git restore` em arquivos tracked e pare.

Allowlist de patch (somente estes arquivos podem mudar; qualquer outro é FAIL):
- `src/engine/core/approvals.py` (se necessário, sem redesign)
- `src/engine/core/dispatcher.py` (integração transition → approval request; apply no decide)
- `src/engine/core/state_store.py` (índice approval_id → target)
- `src/engine/core/errors.py` (novos codes determinísticos, se necessário)
- `src/engine/api/approvals.py` (se necessário, sem quebrar compat Finance)
- `tests/test_bazari_approvals_e2e.py` (novo)
- `docs/specs/expansao/03-approvals-cases-bazari/spec.md` (marcar ✅ IMPLEMENTADO + evidências)

Objetivo:
- Quando uma transition do workflow exigir approvals:
  - criar `approval_id`, emitir `APPROVAL_REQUESTED`, retornar `pending_approval`
- Quando `POST /approvals/{approval_id}/decide` for chamado:
  - validar permissão/role + SoD (sem self-approve)
  - aplicar transição final no entity correto (`ModerationAction`)
  - retornar `case_status=COMMITTED` ou `REJECTED`

Regras obrigatórias (hard):
A) STRICT real: testes usam `X-Actor-Token` + `X-Institution-Id`; proibido spoof (`X-Actor-Id`/`X-Actor-Roles`).
B) Não quebrar Finance: `tests/test_finance_idl_mode_e2e.py` deve continuar PASSANDO.
C) Idempotência/consistência:
   - decidir duas vezes o mesmo approval_id → 409 `APPROVAL_ALREADY_DECIDED`
   - approval_id inexistente → 404 `APPROVAL_NOT_FOUND`
D) Anti-scope-creep: só arquivos da allowlist podem mudar.

Tarefas:
1) Implementar “approval request” para cases Bazari:
   - Caminho recomendado: dentro de `dispatch_transition` (Expansão 02), quando a transition tiver `approvals`:
     - não aplicar efeitos finais
     - criar approval_id
     - persistir índice (approval_id → target entity/transition/decision_map) no state store
     - emitir `APPROVAL_REQUESTED` no ledger
     - retornar `{"status":"pending_approval","approval_id":...}`
2) Implementar “approval decide” genérico:
   - Ao decidir, usar o índice para achar o target:
     - garantir roles permitidas (policy/quorum mínimo)
     - validar SoD: proposer != decider
     - aplicar transição final no entity e persistir
     - emitir eventos do case
3) Teste E2E:
   - Criar `tests/test_bazari_approvals_e2e.py` com TestClient (lifespan), strict/idl:
     - montar bundle de teste mínimo (tmp_path) com workflow `ModerationActionFlow` contendo approvals
     - criar `ModerationAction` (via endpoint create já suportado)
     - chamar transition que requisita approval → 202 + approval_id
     - tentar decidir com role errada → 403 `APPROVAL_FORBIDDEN`
     - decidir com role correta → 200 `case_status=COMMITTED`
4) Atualizar spec com evidências e marcar ✅ IMPLEMENTADO somente após hard gates.

Hard gates (colar saída literal no resumo final):
1) `PYTHONPATH=src python3 -m pytest tests/test_bazari_approvals_e2e.py -v`
2) `PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v`
3) `git diff --name-only` (deve listar SOMENTE a allowlist)
4) `git status --porcelain | rg -n '^(\\?\\?| M ) (tmp/|var/)' && exit 1 || true`
[[CLAUDE_CODE_END]]

