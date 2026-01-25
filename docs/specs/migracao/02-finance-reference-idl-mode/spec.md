# Migração 02 — Finance Reference (IDL mode)

## Objetivo
Estabelecer um “golden path” (single dept) que:
- sobe em `ENGINE_API_MODE=idl` sem colisões de rotas
- passa Proof offline do bundle
- prova `ENGINE_AUTH_MODE=strict` via E2E HTTP (TestClient)

## Hard gates (exigir output literal no resumo/PR)
- `PYTHONPATH=src python3 -m engine.proof verify bundles/finance-pilot`
- `python -m pytest tests/test_finance_idl_mode_e2e.py -v`

