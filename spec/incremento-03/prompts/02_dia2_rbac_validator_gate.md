# Prompt — Dia 2: RBAC Validator Gate

Implemente a Tarefa 5.3 (Dia 2) da Semana 5.

Criar `validators/rbac_validator.py`.

Função obrigatória:
- `validate_rbac(rbac: dict) -> ValidationReport`

Regras:
- Validar com `jsonschema` usando `schemas/rbac.schema.json`.
- `roles` deve conter no mínimo `authenticated`.
- `permissions[*].operation_id` deve ser único.

Retorno:
- `ValidationReport` com `ok`, `errors`, `missing_fields`.

Critério de aceite:
- RBAC inválido é rejeitado.
- RBAC válido passa.
- Duplicidade de operation_id falha.
