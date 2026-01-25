# Migração 07 — Legacy Cutover Policy

## Objetivo
Instrumentar e documentar um cutover seguro do legacy:
- `ENGINE_API_MODE=both`: medir uso de legacy (telemetria determinística)
- `ENGINE_API_MODE=idl`: cutover final (sem legacy routers)

## Hard gates
- `python -m pytest tests/test_legacy_cutover.py -v`

