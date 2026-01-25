# Expansão 03 — Approvals genéricos para “cases” (Bazari)

## Objetivo

Tornar o runtime capaz de lidar com approvals **para entidades/casos além de Expense**, com foco no Bazari:
- `ModerationAction` como “case” governado
- transições que **exigem approval** (ex.: Ban/Remove/Shadowban; Revert)
- decisão via `POST /approvals/{approval_id}/decide` aplicando efeitos/transições corretas

## Escopo

Inclui:
- Modelo/índice determinístico de approvals para entidades genéricas:
  - `approval_id → {institution_id, dept_id, entity, entity_id, workflow, transition, decision_map, payload_sha256}`
- Suporte a “approval requested” disparado por workflow transition:
  - quando a transition tem bloco `approvals` (do IR), o runtime:
    - valida gates (rbac/mandate/autonomy/sod/policy) para o *request*
    - emite `APPROVAL_REQUESTED`
    - retorna `pending_approval` com `approval_id` (sem commitar efeitos finais)
- Suporte a “approval decide” genérico:
  - valida role/quorum/distinct_actors conforme approvals policy
  - aplica transição final (Approve/Reject/Revert) no entity correto
  - emite `CASE_COMMITTED`/`CASE_REJECTED` (ou evento equivalente) para o case do Bazari

Não inclui (fases seguintes):
- “Workflow approvals engine completo” com múltiplos approvals em cadeia.
- UI/console para approvals (apenas runtime + testes).

## Regras canônicas

- `ENGINE_AUTH_MODE=strict` obrigatório nos testes: usar `X-Actor-Token` (nunca spoof).
- O request de approval deve ser **idempotente** (mesma entidade + mesmo payload → mesmo approval_id, se aplicável), ou retornar 409 determinístico.
- Self-approve é proibido quando configurado (SoD): o ator que propôs a ação não pode decidir o approval da própria ação.

## Integração com a Expansão 02 (transition)

Expansão 02 executa `bind.kind=transition` com efeitos mínimos.  
Nesta fase, quando a transition do workflow tiver `approvals`, o runtime NÃO executa os efeitos finais: ele cria um approval pending e retorna `pending_approval`.

## Contratos/bundles alvo

- `docs/bazari/idl/bazari-mvp.idl` (com approvals no workflow `ModerationActionFlow`)

## Erros determinísticos (exemplos)

- `APPROVAL_NOT_FOUND` (404)
- `APPROVAL_ALREADY_DECIDED` (409)
- `APPROVAL_FORBIDDEN` (403) — role não pode decidir
- `APPROVAL_SOD_VIOLATION` (403) — self-approve/SoD
- `APPROVAL_INDEX_NOT_FOUND` (500) — bug/estado inconsistente

## Hard gates (DoD)

Só marcar ✅ IMPLEMENTADO quando:

1) `python -m pytest tests/test_bazari_approvals_e2e.py -v` PASS
2) Regressão proibida:
   - `python -m pytest tests/test_finance_idl_mode_e2e.py -v` PASS
3) Patch limpo (sem `tmp/`/`var/` no git status)

---

## ✅ IMPLEMENTADO

Data: 2026-01-25

### Arquivos modificados

1. `src/engine/core/errors.py` — novos códigos de erro:
   - `APPROVAL_NOT_FOUND`
   - `APPROVAL_ALREADY_DECIDED`
   - `APPROVAL_FORBIDDEN`
   - `APPROVAL_SOD_VIOLATION`
   - `APPROVAL_INDEX_NOT_FOUND`

2. `src/engine/core/state_store.py`:
   - Adicionado `generic_approval_index` para indexar approvals de workflow transitions
   - `index_generic_approval()` — indexa approval com entity_type, entity_id, workflow, transition, proposer_id
   - `get_generic_approval()` — busca approval pelo approval_id

3. `src/engine/core/dispatcher.py`:
   - `dispatch_transition()` — quando `transition_def.approvals` existe:
     - Gera approval_id
     - Atualiza entity status para PENDING_APPROVAL
     - Indexa approval no state store
     - Emite APPROVAL_REQUESTED
     - Retorna 202 com `pending_approval`

4. `src/engine/api/approvals.py`:
   - `_handle_generic_approval_decision()` — handler para decidir approvals de workflow transitions
   - Integração no `decide_approval` para detectar generic approvals
   - Validação de SoD (proposer != decider)
   - Aplica efeitos da transition ao aprovar
   - Emite CASE_COMMITTED/CASE_REJECTED

5. `tests/test_bazari_approvals_e2e.py` — testes E2E:
   - `test_moderation_action_approval_flow` — cria ModerationAction, transition → 202 + approval_id
   - `test_approval_forbidden_wrong_role` — role errada não pode decidir
   - `test_approval_sod_violation` — proposer não pode decidir própria proposta
   - `test_approval_decide_success` — admin pode decidir proposta de moderator
   - `test_transition_without_approvals` — transition sem approvals aplica imediatamente (200)

### Evidência de testes

```
$ PYTHONPATH=src python3 -m pytest tests/test_bazari_approvals_e2e.py -v
============================= test session starts ==============================
collected 5 items

tests/test_bazari_approvals_e2e.py::test_moderation_action_approval_flow PASSED [ 20%]
tests/test_bazari_approvals_e2e.py::test_approval_forbidden_wrong_role PASSED [ 40%]
tests/test_bazari_approvals_e2e.py::test_approval_sod_violation PASSED   [ 60%]
tests/test_bazari_approvals_e2e.py::test_approval_decide_success PASSED  [ 80%]
tests/test_bazari_approvals_e2e.py::test_transition_without_approvals PASSED [100%]

============================== 5 passed in 0.37s ===============================
```

### Regressão verificada

```
$ PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v
============================= test session starts ==============================
collected 2 items

tests/test_finance_idl_mode_e2e.py::test_finance_flow_strict_idl_mode PASSED [ 50%]
tests/test_finance_idl_mode_e2e.py::test_strict_rejects_missing_actor_token PASSED [100%]

============================== 2 passed in 1.37s ===============================
```

### Git diff (somente allowlist)

```
$ git diff --name-only
src/engine/api/approvals.py
src/engine/core/dispatcher.py
src/engine/core/errors.py
src/engine/core/state_store.py

$ git status --porcelain | grep -E '^(\?\?| M ) (tmp/|var/)' && exit 1 || echo "Clean"
Clean - no tmp/var files
```

