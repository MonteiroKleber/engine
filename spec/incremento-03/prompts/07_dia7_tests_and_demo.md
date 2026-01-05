# Prompt — Dia 7: Testes completos + demo

Implemente as Tarefas 5.9, 5.10 e 5.11 (Dia 7) da Semana 5.

1) Testes unitários
Criar:
- `tests/test_rbac_validator.py`
- `tests/test_openapi_validator.py`
- `tests/test_contracts_agent.py`

Obrigatório:
- ContractsAgent cria 5 rotas por entidade.
- Todos methods têm `operationId`.
- RBAC contém permission para cada `operationId`.

2) Integração
Criar:
- `tests/test_pipeline_to_contracts.py`

Obrigatório:
- pipeline completo gera OAS e RBAC.
- versionamento incrementa.
- run log inclui `oap_hash` e `rbac_hash`.
- hashes batem com arquivos salvos.

3) Demo CLI obrigatória
Rodar:
- `python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"`

Artefatos obrigatórios:
- `store_data/demo/OAS/v1.yaml`
- `store_data/demo/RBAC/v1.json`

Critério de aceite:
- `pytest` verde.
- demo CLI gera contratos sempre.
- gates impedem operação sem auth.
