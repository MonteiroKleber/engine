# Contexto e Escopo

## Objetivo imutável da Semana 5
Implementar contratos a partir do IR canônico:
- `schemas/rbac.schema.json` (oficial)
- `agents/contracts_agent.py` (gera OpenAPI + RBAC)
- `validators/openapi_validator.py` (gate)
- `validators/rbac_validator.py` (gate)
- policy: endpoint sem auth = erro
- versionamento de `openapi.yaml` e `rbac.json` no store
- hashes no run log: `oap_hash`, `rbac_hash`
- testes unitários + integração até contratos

## Dependências
- Não adicionar novas dependências.
- Reusar `PyYAML` para parsear YAML no validator, quando necessário.

## Artefatos persistidos (layout)
- SRS: `store_data/{project}/SRS/vN.json`
- IR: `store_data/{project}/IR/vN.json`
- OpenAPI: `store_data/{project}/OAS/vN.yaml`
- RBAC: `store_data/{project}/RBAC/vN.json`

## Run log (obrigatório)
Deve incluir hashes:
- `input_hash`, `srs_hash`, `ir_hash`
- `oap_hash` (hash do arquivo YAML salvo)
- `rbac_hash` (hash do arquivo JSON salvo)

## Definição de pronto (Semana 5 concluída)
- OpenAPI + RBAC gerados do IR.
- Gates e policies funcionando (schema + consistência + sem endpoint sem auth).
- Versionamento + hashes no run log.
- `pytest` verde.
- Demo:
  - `python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"`
  - cria `store_data/demo/OAS/v1.yaml`
  - cria `store_data/demo/RBAC/v1.json`
