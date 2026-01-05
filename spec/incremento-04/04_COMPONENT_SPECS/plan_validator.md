# validators/plan_validator.py — Especificação

## Objetivo
Validar PLAN com schema + regras internas como gate obrigatório.

## API
- `validate_plan(plan: dict) -> ValidationReport`

## ValidationReport
- `ok: bool`
- `errors: list[str]`
- `missing_fields: list[str]`

## Validações
1) JSON Schema: validar com `jsonschema` usando `schemas/plan.schema.json`.
2) Regras internas obrigatórias:
   - `order` deve ser sequência 1..N sem buracos.
   - `tasks[*].id` únicos.
   - `tasks[*].files` não vazio.
   - `tasks[*].acceptance` não vazio.

## Critério de aceite (Dia 2)
- plan inválido falha com erros claros.
- plan válido passa.
