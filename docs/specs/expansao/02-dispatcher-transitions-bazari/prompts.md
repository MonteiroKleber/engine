# Prompts — Expansão 02 (Dispatcher `transition` — Bazari)

## PROMPT 02.1 (Implementação mínima: `bind.kind=transition` + executor subset)

[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/expansao/02-dispatcher-transitions-bazari/spec.md`.
2) Mudança mínima e incremental: implementar apenas o necessário para suportar `bind.kind=transition`.
3) Não alterar auth nem o router dinâmico.
4) Regressão proibida: Finance/ACME/multi-pilot continuam passando.
5) **Proibido deletar qualquer coisa** fora da allowlist (inclui arquivos untracked). Se precisar “limpar”, faça via `git restore` em arquivos tracked e pare.

Allowlist de patch (somente estes arquivos podem mudar; qualquer outro é FAIL):
- `src/engine/core/migration_check.py` (adicionar `transition` ao set suportado)
- `src/engine/core/idl_router.py` (rotear `bind.kind=transition` para o dispatcher; mudança mínima)
- `src/engine/core/dispatcher.py` (executar transition)
- `src/engine/core/state_store.py` (persistência/atualização determinística)
- `src/engine/core/errors.py` (novos codes determinísticos, se necessário)
- `tests/test_bazari_dispatcher_transitions_e2e.py` (novo)
- `docs/specs/expansao/02-dispatcher-transitions-bazari/spec.md` (marcar ✅ IMPLEMENTADO + evidências)

Objetivo:
Habilitar execução de `bind.kind=transition` com o subset:
- `set_state("<STATE>")`
- `set_field("<field>", <literal>)` (string/int/bool/null)
- `bump_version(1)`

Restrições sem negociação:
A) Guard: só aceitar `true`/`false` literal. Qualquer expressão → erro determinístico `WORKFLOW_GUARD_UNSUPPORTED`.
B) `set_field`: só literal. É proibido suportar `now()`/`__NOW__` nesta fase.
C) Não inventar “workflow engine” completo: apenas executor mínimo determinístico.

Tarefas:
1) Migration check:
   - `src/engine/core/migration_check.py`: incluir `transition` em `SUPPORTED_BIND_KINDS`.
2) Dispatcher:
   - Ao receber `bind.kind=transition`, ler `workflow` + `transition` do bind.
   - Carregar o entity atual pelo state store (404 se não existir).
   - Validar que o workflow/transition existe (se não, `WORKFLOW_NOT_FOUND` / `WORKFLOW_TRANSITION_NOT_FOUND`).
   - Validar estado atual vs `from`/`to` (se aplicável) e retornar `WORKFLOW_TRANSITION_CONFLICT` em mismatch.
   - Aplicar efeitos suportados na ordem; qualquer efeito fora do subset → `WORKFLOW_EFFECT_INVALID`.
   - Persistir o entity atualizado.
3) Teste E2E (HTTP via TestClient, strict/idl):
   - Criar `tests/test_bazari_dispatcher_transitions_e2e.py`.
   - Subir app em `ENGINE_API_MODE=idl` + `ENGINE_AUTH_MODE=strict`.
   - Provisionar admin key + actor tokens via admin endpoints (mesmo padrão dos testes de migração).
   - Usar um bundle de teste mínimo criado dentro do teste (tmp_path) ou reutilizar um bundle existente se já houver (preferir tmp_path).
   - Provar pelo menos 2 transições:
     - triage de report (ReportFlow: Pending→Triaged)
     - apply de moderation action (ModerationActionFlow: Approved→Applied) — sem approvals nesta fase (forçar estado inicial no fixture).
   - Provar erro determinístico para guard não-literal (criar uma operação com guard complexo e assert `WORKFLOW_GUARD_UNSUPPORTED`).
4) Atualizar spec:
   - Marcar ✅ IMPLEMENTADO e incluir evidência literal do comando:
     - `PYTHONPATH=src python3 -m pytest tests/test_bazari_dispatcher_transitions_e2e.py -v`
   - Confirmar que `tests/test_finance_idl_mode_e2e.py` continua passando.

Hard gates (colar saída literal no resumo final):
1) `PYTHONPATH=src python3 -m pytest tests/test_bazari_dispatcher_transitions_e2e.py -v`
2) `PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v`
3) Hard gate anti-scope-creep (allowlist estrita):
   - `git diff --name-only`
   - O output DEVE conter SOMENTE (ordem livre):
     - `src/engine/core/migration_check.py`
     - `src/engine/core/idl_router.py`
     - `src/engine/core/dispatcher.py`
     - `src/engine/core/state_store.py`
     - `src/engine/core/errors.py`
     - `tests/test_bazari_dispatcher_transitions_e2e.py`
     - `docs/specs/expansao/02-dispatcher-transitions-bazari/spec.md`
   - Se aparecer qualquer outro arquivo, é FAIL e você deve reverter antes de finalizar.
4) Patch limpo (sem tmp/var no git status):
   - `git status --porcelain | rg -n '^(\\?\\?| M ) (tmp/|var/)' && exit 1 || true`
[[CLAUDE_CODE_END]]
