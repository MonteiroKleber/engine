# Gaps — Diagnóstico (Migração 01)

Este documento lista os **gaps reais** identificados no diagnóstico inicial para viabilizar `ENGINE_API_MODE=idl` com `ENGINE_AUTH_MODE=strict`, e registra como esses gaps foram endereçados nas migrações seguintes.

## Gaps críticos (bloqueadores de boot em IDL)

### GAP-01 — Bundle default sem `operations.json` (IDL mode hard-fail)
- **Impacto:** `ENGINE_API_MODE=idl` executa migration checks no boot e falha se o bundle ativo não tiver registry de operações.
- **Correção aplicada:** Migração 02 (Finance) + Migração 03 (ACME) + Migração 04 (Multi-pilot) garantem `operations.json` (single ou por dept) + Proof offline PASS.
- **Evidência:** `PYTHONPATH=src python3 -m engine.proof verify bundles/finance-pilot` / `bundles/acme_core` / `bundles/multi-pilot`.

### GAP-02 — IDL router não suportava STRICT (quebrava `X-Actor-Token`)
- **Impacto:** mesmo com `ENGINE_AUTH_MODE=strict`, rotas IDL aceitavam headers DEV spoofáveis.
- **Correção aplicada:** Migração 02/02.5–02.6: `src/engine/core/idl_router.py` passou a resolver actor via `engine.api.dependencies.get_actor_context()` (caminho canônico).
- **Evidência:** `src/engine/core/idl_router.py` contém `get_actor_context(` no handler.

### GAP-03 — Bootstrap de admin key por instituição impossível via HTTP
- **Impacto:** era possível criar instituição com `X-Admin-Token`, mas não criar admin key para a instituição recém-criada (bloqueava operação “sem shell”).
- **Correção aplicada:** Migração 08: `POST /admin/institutions/{institution_id}/admin-keys` permite bootstrap one-time via `X-Admin-Token` quando a instituição ainda não tem keys.
- **Evidência:** `python -m pytest tests/test_admin_key_bootstrap.py -v`.

## Gaps importantes (qualidade / operabilidade)

### GAP-04 — Pipelines que geram bundles podiam produzir bundle “meio válido”
- **Impacto:** onboarding/ISE podiam gerar bundles sem âncora ou sem operations, levando a falhas posteriores.
- **Correção aplicada:** Migração 05:
  - Onboarding: valida template “IDL-ready” em `ENGINE_API_MODE=idl`.
  - ISE: falha determinística se `source_idl_sha256` estiver ausente no IRCS.
- **Evidência:** `python -m pytest tests/test_onboarding_idl_ready.py -v` e `python -m pytest tests/test_ise_idl_ready.py -v`.

### GAP-05 — Baseline PROD/STRICT/IDL sem smoke test
- **Impacto:** risco alto de regressões em produção (envs obrigatórias, console, auth strict).
- **Correção aplicada:** Migração 06: `tests/test_prod_strict_idl_boot.py` valida boot + fluxo mínimo via HTTP em `ENGINE_INSTALL_MODE=prod`.

## Gaps restantes (após Migrações 02–08)
- Documentação de `map.md`/`gaps.md` e runbooks (múltiplas fases) precisa conter evidências completas (não placeholder).
- Política de cutover (Migração 07): ainda existem endpoints legacy-only em bundles parcialmente migrados (ex.: `GET /support/tickets/{id}` no multi-pilot/support) — isso é uma decisão de produto/escopo.
