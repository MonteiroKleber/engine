# Migração 08 — Admin Key Bootstrap (por instituição)

## Objetivo
Permitir que uma instituição recém-criada consiga criar a **primeira** admin key via HTTP, sem acesso shell, mantendo governança:
- bootstrap one-time via `X-Admin-Token` (global)
- depois disso, exigir `X-Admin-Key` (por instituição)

## Hard gates
- `python -m pytest tests/test_admin_key_bootstrap.py -v`

