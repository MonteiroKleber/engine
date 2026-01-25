# Prompts — Expansão 04 (Bazari Phase 1 bundle “IDL-ready” + E2E PROD)

## PROMPT 04.1 (Implementação mínima: compilar DSL → bundle + E2E em PROD/STRICT/IDL)

[[CLAUDE_CODE_START]]
Você está no repositório `/home/bazari/engine`.

Contrato:
1) Siga `docs/specs/expansao/04-bazari-phase1-bundle-idl-ready/spec.md`.
2) Mudança mínima: **somente** testes + docs desta fase. Não alterar core (dispatcher/router/auth/ISE).
3) Regressão proibida: Finance continua passando.
4) **Proibido deletar qualquer coisa** fora da allowlist (inclui arquivos untracked). Se precisar “limpar”, faça via `git restore` em arquivos tracked e pare.

Allowlist de patch (somente estes arquivos podem mudar/criar; qualquer outro é FAIL):
- `tests/test_bazari_phase1_bundle_prod_strict_idl_e2e.py` (novo)
- `docs/specs/expansao/04-bazari-phase1-bundle-idl-ready/spec.md` (marcar ✅ IMPLEMENTADO + evidências)

Contexto:
- O DSL canônico do bundle é `docs/bazari/idl/bazari-phase1.idl`.
- A pipeline canônica já existe no repo:
  - parse DSL → IRCS: `engine.idl_dsl.parse_dsl(source_text)`
  - IRCS → bundle: `engine.ise.compiler.compile_from_ircs(ir, bundle_name, output_dir)`
- O objetivo é provar que um cliente pode operar o engine em PROD/STRICT/IDL com um bundle gerado canonicamente.

Tarefas:

A) Criar E2E “bundle gerado + boot prod + fluxo CRUD”
1) Criar `tests/test_bazari_phase1_bundle_prod_strict_idl_e2e.py` que:
   - usa `tmp_path` como `ENGINE_DATA_ROOT`
   - lê `docs/bazari/idl/bazari-phase1.idl`
   - gera IRCS em memória via `engine.idl_dsl.parse_dsl()`
   - compila bundle em `bundle_dir = tmp_path / "bundles" / "bazari-phase1"` via `compile_from_ircs(ir, "bazari-phase1", str(bundle_dir))`
   - valida `result.success == True` (ou equivalente do retorno)
   - roda Proof offline no bundle gerado (preferir API interna se existir; senão `subprocess.run`):
     - `PYTHONPATH=src python3 -m engine.proof verify <bundle_dir>`

2) Subir o app em `ENGINE_INSTALL_MODE=prod` + `ENGINE_AUTH_MODE=strict` + `ENGINE_API_MODE=idl` apontando para `ENGINE_BUNDLE_PATH=<bundle_dir>`, com TestClient e lifespan:
   - envs mínimos (determinísticos):
     - `ENGINE_INSTALL_MODE=prod`
     - `ENGINE_AUTH_MODE=strict`
     - `ENGINE_API_MODE=idl`
     - `ENGINE_ISE_ADMIN_TOKEN="test-admin-token-32-chars-minimum____"`
     - `ENGINE_CONSOLE_SESSION_SECRET="test-" + "x"*60`
     - `ENGINE_DATA_ROOT=str(tmp_path/"data_root")`
     - `ENGINE_INSTITUTIONS_DIR=<ENGINE_DATA_ROOT>/institutions`
     - `ENGINE_INSTITUTIONS_REGISTRY_PATH=<ENGINE_DATA_ROOT>/institutions_registry.jsonl`
     - `ENGINE_BUNDLE_PATH=str(bundle_dir)`
   - Import determinístico do app (evitar env vazando entre testes):
     - `import importlib; import engine.api.server as server; importlib.reload(server); app = server.app`
   - `with TestClient(app) as client: ...`

3) Dentro do E2E, validar:
   - `GET /health` → 200
   - `GET /console/login` → 200

4) Bootstrap completo via HTTP (sem shell):
   - criar instituição:
     - `POST /admin/institutions` com header `X-Admin-Token: test-admin-token-32-chars-minimum____`
   - criar primeira admin key (bootstrap one-time; Migração 08):
     - `POST /admin/institutions/{institution_id}/admin-keys` com `X-Admin-Token` → retorna `plaintext_secret`
   - provisionar actor tokens via endpoint admin:
     - `POST /admin/institutions/{institution_id}/actors` com `X-Admin-Key: <plaintext_secret>`
     - criar pelo menos:
       - actor `user` com roles `["user"]`
       - actor `moderator` com roles `["moderator"]`
       - (opcional) actor `admin` com roles `["admin"]`
     - capturar `token` de cada criação.

5) Exercitar endpoints do Bazari Phase 1 (STRICT token-based):
   - headers sempre:
     - `X-Institution-Id: <institution_id>`
     - `X-Actor-Token: <token>`
   - Proibido usar `X-Actor-Id`/`X-Actor-Roles`/`X-Tenant-Id`.
   - Fluxo mínimo recomendado (cobre ~10 endpoints):
     - `POST /reports` (user) → 200/201 + `id`
     - `GET /reports/{id}` (moderator) → 200
     - `GET /reports/my` (user) → 200 (lista contém o report)
     - `GET /moderation/reports` (moderator) → 200 (lista determinística)
     - `POST /chat/reports` (user) → 200/201
     - `POST /chat/blocks` (user) → 200/201
     - `DELETE /chat/blocks/{profile_id}` (user) → 200/204 (documentar qual)
     - `POST /moderation/actions` (moderator) → 200/201 + `id`
     - `GET /moderation/actions/{id}` (moderator) → 200
     - `GET /moderation/actions` (moderator) → 200 (lista determinística)

B) Atualizar spec
- Atualizar `docs/specs/expansao/04-bazari-phase1-bundle-idl-ready/spec.md` para ✅ IMPLEMENTADO somente após passar nos hard gates e colar as saídas literais.

Hard gates (colar saída literal no resumo final):
1) `PYTHONPATH=src python3 -m pytest tests/test_bazari_phase1_bundle_prod_strict_idl_e2e.py -v`
2) `PYTHONPATH=src python3 -m pytest tests/test_finance_idl_mode_e2e.py -v`
3) Anti-scope-creep (allowlist estrita):
   - `git diff --name-only` deve conter SOMENTE:
     - `tests/test_bazari_phase1_bundle_prod_strict_idl_e2e.py`
     - `docs/specs/expansao/04-bazari-phase1-bundle-idl-ready/spec.md`
4) Patch limpo (sem tmp/var no git status):
   - `git status --porcelain | rg -n '^(\\?\\?| M ) (tmp/|var/)' && exit 1 || true`

Restrições:
- Não criar/commitar artefatos em `tmp/` nem `var/`.
[[CLAUDE_CODE_END]]
