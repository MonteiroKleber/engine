# validators/ir_validator.py — Especificação

## Objetivo
Validar IR contra `schemas/ir.schema.json` (gate obrigatório por schema).

## API
### validate_ir(ir: dict) -> ValidationReport

## ValidationReport
- `ok: bool`
- `errors: list[str]`
- `missing_fields: list[str]`

## Regras
- Validar com `jsonschema` usando `schemas/ir.schema.json`.
- Se inválido:
  - `ok=false`
  - `errors` com mensagens legíveis (pelo menos path + mensagem)
  - `missing_fields` preenchido quando detectável (ex.: `required`)
- Se válido:
  - `ok=true`
  - `errors=[]`, `missing_fields=[]`

## Critério de aceite (Dia 2)
- Detecta IR inválido e retorna erros.
- Aceita IR válido.
