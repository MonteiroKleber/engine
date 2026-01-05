# Plano de testes (Semana 5)

## Unitários (novos)
- `tests/test_rbac_validator.py`
- `tests/test_openapi_validator.py`
- `tests/test_contracts_agent.py`

Obrigatório:
- ContractsAgent cria 5 rotas por entidade.
- Todo método tem `operationId`, `tags` e `responses`.
- RBAC contém permission para cada `operationId`.

## Integração (novo)
- `tests/test_pipeline_to_contracts.py`

Obrigatório:
- pipeline completo gera OAS e RBAC.
- versionamento incrementa (v1 → v2) em execuções repetidas.
- run log inclui `oap_hash` e `rbac_hash`.
- hashes batem com os arquivos salvos.

## Critério final
- `pytest` verde.
