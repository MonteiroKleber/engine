# Prompts — Expansão 01 (Dispatcher CRUD genérico — Bazari)

## PROMPT 01.1 (Implementação mínima: CRUD genérico para entidades Bazari MVP)

[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/expansao/01-dispatcher-crud-bazari/spec.md`.
2) Mudança mínima e incremental: expandir apenas o dispatcher/state store no necessário para CRUD das entidades do Bazari MVP.
3) Não alterar semântica dos gates, nem o router dinâmico, nem auth.
4) Não quebrar o fluxo Finance/ACME/multi-pilot (regressão proibida).

Contexto:
- Hoje o dispatcher suporta entidades hardcoded (ex.: Expense/Ticket) e alguns binds.
- O Bazari MVP precisa de CRUD mínimo para:
  - `ContentReport`
  - `ChatReport`
  - `ChatBlock`
  - `ModerationAction`
- O DSL atual não suporta `bind.kind=list`; “listagem” deve ser implementada como semântica de `read` quando o path não tiver `{id}`.

Tarefas:
1) Dispatcher: adicionar suporte para as 4 entidades com binds:
   - `create`
   - `read` (inclui list quando não há id no path)
   - `delete` (mínimo necessário para `ChatBlock`)
2) State store:
   - persistir por instituição e dept (se aplicável), sem vazamento entre tenants.
   - usar formato JSON determinístico e alinhado ao padrão do repo (não inventar DB).
3) Erros determinísticos:
   - 404: `<ENTITY>_NOT_FOUND` (ou padrão equivalente já usado)
   - 403: denied por gate (reusar códigos existentes)
4) Testes obrigatórios:
   - criar `tests/test_bazari_dispatcher_crud.py` (ou nome equivalente) que:
     - sobe app em `ENGINE_API_MODE=idl` + `ENGINE_AUTH_MODE=strict` com TestClient (lifespan)
     - provisiona tokens via admin endpoint (`/admin/institutions/{id}/actors`)
     - exercita via HTTP pelo menos:
       - `POST /reports` (create ContentReport) → 200/201
       - `GET /reports/{id}` → 200
       - `GET /admin/reports` (list via read sem id) → 200 (ordem determinística)
       - `POST /chat/blocks` → 200/201
       - `DELETE /chat/blocks/{profile_id}` → 200/204 (decisão documentada)
     - valida isolamento (2 instituições) no mínimo para um endpoint.
5) Atualizar docs da fase:
   - marcar `docs/specs/expansao/01-dispatcher-crud-bazari/spec.md` como ✅ IMPLEMENTADO quando os testes passarem
   - registrar evidência literal dos comandos:
     - `python -m pytest tests/test_bazari_dispatcher_crud.py -v` (ou nome final)

Restrições:
- Não criar/commitar artefatos em `tmp/` nem `var/`.
- Não introduzir endpoints novos. Usar rotas já possíveis via IDL router/OperationRegistry (ou fixtures existentes de testes).
[[CLAUDE_CODE_END]]

---

## PROMPT 01.1R (Correção obrigatória: reverter scope creep + “hard gates” de patch mínimo)

[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contexto:
- A implementação anterior da Expansão 01 extrapolou o escopo (mexeu em router/gates/console/telemetria/bundles).
- Esta correção existe para garantir **mudança mínima**, rastreável e “bank-grade”.

Contrato (hard):
1) Siga `docs/specs/expansao/01-dispatcher-crud-bazari/spec.md`.
2) Mudança mínima: **somente** adicionar CRUD genérico no dispatcher/state store para entidades Bazari MVP.
3) É PROIBIDO alterar semântica de gates, router dinâmico, auth, console, bundles, onboarding/ISE.
4) É PROIBIDO adicionar bind kinds novos no runtime. “List” deve ser semântica de `read` (quando o id não existe).
5) É PROIBIDO rodar comandos destrutivos de limpeza de untracked (ex.: `git clean -fd` / `git clean -fdx`).
   Se precisar “limpar patch”, use apenas `git restore`/`git checkout` em arquivos versionados e confirme com `git diff --name-only`.

Arquivos permitidos neste prompt (hard allowlist):
- `src/engine/core/dispatcher.py`
- `src/engine/core/state_store.py`
- `src/engine/core/errors.py` (apenas novos error codes necessários)
- `tests/test_bazari_dispatcher_crud.py` (ou renome equivalente)
- `docs/specs/expansao/01-dispatcher-crud-bazari/spec.md` (apenas status/evidência)

Qualquer mudança fora disso é FALHA (inclui, mas não limitado a):
- `src/engine/core/idl_router.py`
- `src/engine/core/mandates.py`, `src/engine/core/autonomy.py`, `src/engine/core/policy.py`
- `src/engine/api/**`
- `src/engine/console/**`
- `bundles/**`
- `docs/specs/migracao/**`
- `docs/bazari/**` (não deletar artefatos do Bazari; se estiverem fora do patch, apenas ignore)

Tarefas:
1) Reverter completamente qualquer “scope creep” fora da allowlist acima.
   - Não deixar alterações residuais em `git status`.
2) Implementar (apenas) o necessário em `dispatcher.py` e `state_store.py` para:
   - entidades: `ContentReport`, `ChatReport`, `ChatBlock`, `ModerationAction`
   - binds: `create`, `read`, `delete`
   - “list” via `read`: quando o `path` não contém `{id}` e/ou quando o `path_params` não contém id, retornar coleção determinística.
3) Erros determinísticos:
   - 404: `<ENTITY>_NOT_FOUND` (ou padrão equivalente do repo)
   - manter 403/401 do pipeline existente (não duplicar gate logic)
4) Testes (obrigatórios) sem HTTP (para evitar tocar router):
   - `tests/test_bazari_dispatcher_crud.py` deve validar diretamente o dispatcher/state store:
     - create + read de `ContentReport`
     - list determinística (read sem id) para `ContentReport` e/ou `ModerationAction`
     - create + delete de `ChatBlock` (e read 404 após delete)
     - isolamento por `institution_id` (2 instituições) para pelo menos uma entidade
   - Os testes devem usar `tmp_path` (ou fixture equivalente) como base de storage, sem tocar `var/` do repo.

Hard gates (obrigatório colar saída literal no resumo final):
1) Provar patch mínimo por arquivos:
   - `git diff --name-only`
   - Deve conter APENAS a allowlist acima. Se tiver qualquer outro arquivo, é falha.
2) Provar que nada em `tmp/` ou `var/` entrou no patch:
   - `git status --porcelain | rg -n '^(\\?\\?| M ) (tmp/|var/)' && exit 1 || true`
3) Provar testes:
   - `python -m pytest tests/test_bazari_dispatcher_crud.py -v`

Saída esperada:
- Patch mínimo + testes verdes + evidências literais dos hard gates.
[[CLAUDE_CODE_END]]
