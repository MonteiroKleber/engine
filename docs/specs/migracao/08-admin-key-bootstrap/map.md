# Map — Migração 08 (Admin Key Bootstrap)

## Problema original (bootstrap lock)

Fluxo desejado em produção (sem shell):
1) criar instituição via `POST /admin/institutions` (global admin token)
2) criar admin key por instituição via `POST /admin/institutions/{id}/admin-keys`
3) usar `X-Admin-Key` para administrar actors/mandates/policies etc.

O problema era que:
- `POST /admin/institutions` aceitava `X-Admin-Token`
- mas `POST /admin/institutions/{id}/admin-keys` exigia `X-Admin-Key`
- e `X-Admin-Token` era recusado para instituições não-default

Resultado: instituição recém-criada não conseguia “subir” administração sem acesso shell.

## Fix aplicado (bootstrap one-time no endpoint)

Arquivo:
- `src/engine/api/admin_keys.py`

Regras:
- Para `institution_id != DEFAULT_INSTITUTION_ID`:
  - se **não existe nenhuma admin key** ainda: permite criar a primeira via `X-Admin-Token` (validado contra `ENGINE_ISE_ADMIN_TOKEN`)
  - se já existe key: recusa bootstrap e exige `X-Admin-Key`
- Para `DEFAULT_INSTITUTION_ID`: mantém compat (token legacy funciona como antes).

Auditoria:
- evento no ledger da instituição indicando `bootstrap_via_admin_token=true` quando aplicável.

## Hard gate

- `python -m pytest tests/test_admin_key_bootstrap.py -v`

