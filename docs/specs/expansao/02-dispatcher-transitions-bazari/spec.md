# Expansão 02 — Dispatcher `transition` (Workflows) — Bazari

## Objetivo

Habilitar execução de `bind.kind=transition` para workflows definidos em bundles IDL, com um subset **mínimo, determinístico e auditável** do DSL.

Esta fase destrava endpoints do Bazari que representam **mudança de estado** (ex.: triage/apply) sem ainda depender de approvals.

## Escopo

Inclui:
- Suporte no runtime a `bind.kind=transition` via dispatcher.
- Roteamento mínimo no IDL router para chamar o dispatcher quando `bind.kind=transition`.
- Executor de efeitos **permitidos** (subset):
  - `set_state("<STATE>")`
  - `set_field("<field>", <literal>)` (apenas literal: string/int/bool/null)
  - `bump_version(1)` (somente `1`)
- Persistência no state store existente, mantendo isolamento por `institution_id` e (quando aplicável) por `dept_id`.
- Erros determinísticos (404, 409 e validações).
- Testes E2E (HTTP via TestClient) em `ENGINE_API_MODE=idl` + `ENGINE_AUTH_MODE=strict`.

Não inclui (próximas fases):
- `bind.kind=approval` (Fase 03).
- “Workflow engine genérico” (expressões arbitrárias, funções como `now()`, side-effects complexos).

## Contexto Bazari

- O bundle `docs/bazari/idl/bazari-mvp.idl` possui endpoints com transições (exemplos):
  - `POST /admin/reports/{report_id}/triage` → `workflow: ReportFlow`, `transition: Triage`
  - `POST /moderation/actions/{action_id}/apply` → `workflow: ModerationActionFlow`, `transition: Apply`

Na Fase 01 (`docs/bazari/idl/bazari-phase1.idl`) esses endpoints **não** existem (CRUD only). A Fase 02 prepara o runtime para que eles possam existir no bundle “MVP completo”.

## Regras de execução (subset)

### 1) Validação de workflow/transition

- Workflow deve existir nos contracts do bundle.
- Transition deve existir no workflow.
- O executor deve:
  - carregar o estado atual do entity (`{entity, entity_id}`)
  - aplicar efeitos na ordem declarada
  - persistir de forma determinística

### 2) Guard

Para esta fase, o guard é limitado a:
- literal `true` / `false`

Qualquer guard mais complexo deve falhar determinísticamente com `WORKFLOW_GUARD_UNSUPPORTED` (novo code) para evitar semântica ambígua.

### 3) `set_field` literals

Aceitar apenas literais (sem `now()`/`__NOW__`/expressões):
- string
- int
- bool
- null

Se o DSL do Bazari usar timestamps, isso deve ser feito no **cliente** (Bazari app) e enviado no payload como literal, ou ser habilitado em fase posterior.

## Erros determinísticos

Adicionar/reusar codes (exemplos):
- 404: `<ENTITY>_NOT_FOUND` (já existe para Bazari na Fase 01)
- 404: `WORKFLOW_NOT_FOUND`
- 404: `WORKFLOW_TRANSITION_NOT_FOUND`
- 400/422: `WORKFLOW_EFFECT_INVALID`
- 409: `WORKFLOW_TRANSITION_CONFLICT` (se tentar transicionar em estado inválido)
- 400: `WORKFLOW_GUARD_UNSUPPORTED`

## Hard gates (DoD)

Só marcar ✅ IMPLEMENTADO quando:

1) Migration checks aceitam `transition` como bind kind suportado.
2) Teste E2E passar:
   - `python -m pytest tests/test_bazari_dispatcher_transitions_e2e.py -v`
3) Regressão proibida:
   - `python -m pytest tests/test_finance_idl_mode_e2e.py -v`

## Notas de segurança

- Em STRICT, transições continuam sujeitas a RBAC/mandates/autonomy (gates existentes).
- Esta fase não altera auth nem router dinâmico.

---

## ✅ IMPLEMENTADO

Data: 2026-01-25

### Arquivos modificados

1. `src/engine/core/errors.py` — novos códigos de erro:
   - `WORKFLOW_NOT_FOUND`
   - `WORKFLOW_TRANSITION_NOT_FOUND`
   - `WORKFLOW_EFFECT_INVALID`
   - `WORKFLOW_TRANSITION_CONFLICT`
   - `WORKFLOW_GUARD_UNSUPPORTED`

2. `src/engine/loader/migration_check.py` — adicionado `"transition"` ao `SUPPORTED_BIND_KINDS`.

3. `src/engine/core/dispatcher.py`:
   - `dispatch_transition()` — implementação completa do dispatcher de transições
   - `_validate_guard()` — validação de guards (apenas `true`/`false` literal)
   - `_apply_effects()` — executor de efeitos (`set_state`, `set_field`, `bump_version`)

4. `src/engine/core/idl_router.py` — routing para `bind.kind=transition` (já existia).

5. `tests/test_bazari_dispatcher_transitions_e2e.py` — testes E2E:
   - `test_content_report_triage_transition` — transição PENDING → UNDER_REVIEW
   - `test_complex_guard_returns_unsupported` — guard não-literal retorna WORKFLOW_GUARD_UNSUPPORTED
   - `test_transition_conflict_wrong_state` — transição em estado errado retorna 409
   - `test_transition_not_found` — entidade inexistente retorna 404
   - `test_set_state_effect` — efeito set_state funciona

### Evidência de testes

```
$ python -m pytest tests/test_bazari_dispatcher_transitions_e2e.py -v
============================= test session starts ==============================
collected 5 items

tests/test_bazari_dispatcher_transitions_e2e.py::test_content_report_triage_transition PASSED [ 20%]
tests/test_bazari_dispatcher_transitions_e2e.py::test_complex_guard_returns_unsupported PASSED [ 40%]
tests/test_bazari_dispatcher_transitions_e2e.py::test_transition_conflict_wrong_state PASSED [ 60%]
tests/test_bazari_dispatcher_transitions_e2e.py::test_transition_not_found PASSED [ 80%]
tests/test_bazari_dispatcher_transitions_e2e.py::test_set_state_effect PASSED [100%]

============================== 5 passed in 0.29s ===============================
```

### Regressão verificada

```
$ python -m pytest tests/test_finance_idl_mode_e2e.py -v
============================= test session starts ==============================
collected 2 items

tests/test_finance_idl_mode_e2e.py::test_finance_flow_strict_idl_mode PASSED [ 50%]
tests/test_finance_idl_mode_e2e.py::test_strict_rejects_missing_actor_token PASSED [100%]

============================== 2 passed in 1.30s ===============================
```
