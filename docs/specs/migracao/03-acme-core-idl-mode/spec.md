# Migração 03 — ACME Core (IDL mode)

## Objetivo
Migrar `bundles/acme_core` para operar em `ENGINE_API_MODE=idl`, mantendo governança.

## Regras importantes
- `mandates.json`/`autonomy.json` **existem**: listas vazias implicam deny; não remover “para fazer passar”.

## Hard gates
- `PYTHONPATH=src python3 -m engine.proof verify bundles/acme_core`
- `python -m pytest tests/test_acme_core_idl_mode_e2e.py -v`

