# validators/rbac_validator.py — Especificação

## Objetivo
Validar RBAC (schema + regras adicionais) como gate obrigatório.

## API
- `validate_rbac(rbac: dict) -> ValidationReport`

## ValidationReport
- `ok: bool`
- `errors: list[str]`
- `missing_fields: list[str]`

## Regras
1) Validar com `jsonschema` usando `schemas/rbac.schema.json`.
2) Regras adicionais:
   - `roles` deve conter no mínimo `authenticated`.
   - `permissions[*].operation_id` deve ser único (sem duplicados).

## Critério de aceite (Dia 2)
- RBAC inválido é rejeitado.
- RBAC válido passa.
- Duplicidade de `operation_id` falha.
