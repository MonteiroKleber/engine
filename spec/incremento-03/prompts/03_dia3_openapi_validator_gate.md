# Prompt — Dia 3: OpenAPI Validator Gate

Implemente a Tarefa 5.4 (Dia 3) da Semana 5.

Criar `validators/openapi_validator.py`.

Regras mínimas obrigatórias:
- OpenAPI deve ter `openapi` e `paths`.
- Proibir `paths` vazio.
- Todo método em `paths` deve ter:
  - `operationId`
  - `responses`
- Proibir path vazio.
- Proibir operação sem `tags`.

O validator retorna `ValidationReport` com:
- `ok`, `errors`, `missing_fields`

Critério de aceite:
- OpenAPI inválido falha com erros explícitos.
- OpenAPI mínimo válido passa.
