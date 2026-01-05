# Prompt — Dia 2: Plan Validator Gate

Implemente a Tarefa 6.3 (Dia 2) da Semana 6.

Criar `validators/plan_validator.py`.

Função obrigatória:
- `validate_plan(plan: dict) -> ValidationReport`

Validações:
- JSON Schema com `schemas/plan.schema.json`.
- Regras internas obrigatórias:
  - `order` deve ser 1..N sem buraco.
  - `id` únicos.
  - `files` não vazio.
  - `acceptance` não vazio.

Critério de aceite:
- plan inválido falha com erros claros.
- plan válido passa.
