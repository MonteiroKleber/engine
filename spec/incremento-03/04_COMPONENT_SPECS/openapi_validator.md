# validators/openapi_validator.py — Especificação

## Objetivo
Validar OpenAPI (gate obrigatório) com regras mínimas determinísticas.

## Entrada
- OpenAPI como YAML string (gerado pelo ContractsAgent) ou como dict (após parse).

## API
- `validate_openapi(openapi_yaml_or_dict) -> ValidationReport`

## ValidationReport
- `ok: bool`
- `errors: list[str]`
- `missing_fields: list[str]`

## Regras mínimas obrigatórias (policy gate)
- Deve ter `openapi` e `paths`.
- Proibir `paths` vazio.
- Para cada path em `paths`:
  - proibir path string vazia
  - para cada método HTTP em `paths[path]`:
    - deve ter `operationId`
    - deve ter `responses`
    - deve ter `tags` (proibir operação sem tags)

## Notas
- Este validator não precisa validar o spec completo OpenAPI 3.x; apenas as regras acima.
- Recomenda-se parse via `yaml.safe_load`.

## Critério de aceite (Dia 3)
- OpenAPI inválido falha com erros explícitos.
- OpenAPI mínimo válido passa.
