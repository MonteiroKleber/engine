# Tests — Semana 5

## Unitários
- `tests/test_rbac_validator.py`: schema + regras extras (authenticated, unique operation_id).
- `tests/test_openapi_validator.py`: regras mínimas (openapi/paths, operationId, responses, tags).
- `tests/test_contracts_agent.py`: 5 rotas por entidade; methods com operationId; RBAC permission por operationId.

## Integração
- `tests/test_pipeline_to_contracts.py`:
  - pipeline gera OAS e RBAC
  - versionamento incrementa
  - run log inclui `oap_hash` e `rbac_hash`
  - hashes batem com arquivos salvos
