# Migração 04 — Multi-pilot (Multi-dept — IDL mode)

## Objetivo
Migrar `bundles/multi-pilot` (multi-dept) para IDL:
- `departments/<dept>/operations.json`
- Proof offline PASS
- E2E STRICT cobrindo `/d/{dept_id}`.

## Hard gates
- `PYTHONPATH=src python3 -m engine.proof verify bundles/multi-pilot`
- `python -m pytest tests/test_multi_pilot_idl_mode_e2e.py -v`

