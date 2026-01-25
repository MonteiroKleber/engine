# Migração 05 — Onboarding + ISE IDL-ready

## Objetivo
Garantir que os pipelines que **produzem bundles** (onboarding via console e ISE via compiler) nunca gerem bundles “meio válidos” em `ENGINE_API_MODE=idl`.

## Hard gates
- `python -m pytest tests/test_onboarding_idl_ready.py -v`
- `python -m pytest tests/test_ise_idl_ready.py -v`

