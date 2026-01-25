# Map — Migração 06 (Baseline PROD/STRICT/IDL)

## Modos (o que cada um faz)

- `ENGINE_INSTALL_MODE=prod`
  - preflight exige secrets e auth estrita (não aceita “dev” em produção)
- `ENGINE_AUTH_MODE=strict`
  - requests de operação exigem `X-Actor-Token`
  - spoof (`X-Actor-Id`/`X-Actor-Roles`) não é aceito
- `ENGINE_API_MODE=idl`
  - engine roda migration checks no boot e falha hard se bundle não for migrado
  - legacy routers são omitidos (evita colisão e “escape” para legacy)

## Pontos do código (paths)

Preflight (prod):
- `src/engine/core/preflight.py`
- `src/engine/core/install_mode.py`

IDL mode hard checks no boot:
- `src/engine/api/server.py` (lifespan)
- `src/engine/core/migration_check.py`

Auth STRICT (canônico):
- `src/engine/api/dependencies.py:get_actor_context()`
- `src/engine/core/idl_router.py` chama `get_actor_context()` para rotas IDL.

Admin bootstrap (sem shell):
- `POST /admin/institutions` (global via `X-Admin-Token`)
- `POST /admin/institutions/{id}/admin-keys` (bootstrap one-time via `X-Admin-Token`)
- `POST /admin/institutions/{id}/actors` (via `X-Admin-Key`)

## Evidência (hard gates)

- Smoke test: `python -m pytest tests/test_prod_strict_idl_boot.py -v`
- Proof offline do bundle de referência: `PYTHONPATH=src python3 -m engine.proof verify bundles/finance-pilot`

