# Migração 06 — Baseline PROD/STRICT/IDL

## Objetivo
Ter um baseline testável e operável para:
- `ENGINE_INSTALL_MODE=prod`
- `ENGINE_AUTH_MODE=strict`
- `ENGINE_API_MODE=idl`

## Hard gates
- `python -m pytest tests/test_prod_strict_idl_boot.py -v`
- `PYTHONPATH=src python3 -m engine.proof verify bundles/finance-pilot`

