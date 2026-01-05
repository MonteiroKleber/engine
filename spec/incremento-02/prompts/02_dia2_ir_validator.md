# Prompt — Dia 2: IR Validator (gate obrigatório)

Implemente a Tarefa 4.2 (Dia 2) da Semana 4.

Criar `validators/ir_validator.py` com:

Função obrigatória:
- `validate_ir(ir: dict) -> ValidationReport`

`ValidationReport` deve ter:
- `ok: bool`
- `errors: list[str]`
- `missing_fields: list[str]`

Regras:
- Validar com `jsonschema` usando `schemas/ir.schema.json`.
- Se inválido: `ok=false` e listar erros.
- Se válido: `ok=true`.

Critério de aceite:
- Validator detecta IR inválido e retorna erros.
- Validator aceita IR válido.
