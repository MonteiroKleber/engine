# Estrutura do repositório e convenções (Semana 5)

## Delta de estrutura (em relação à Semana 4)
Adicionar/atualizar no repo `/home/bazari/engine`:
- Adicionar `schemas/rbac.schema.json`.
- Criar `agents/contracts_agent.py`.
- Criar `validators/openapi_validator.py`.
- Criar `validators/rbac_validator.py`.
- Atualizar `store/fs_layout.md` documentando novos kinds (OAS, RBAC).
- Atualizar `store/artifacts_store.py` para salvar YAML e JSON e versionar `OAS/` e `RBAC/`.
- Atualizar `validators/policy_validator.py` com policies de contratos (OAS x RBAC).
- Atualizar `orchestrator/engine.py` para integrar geração/validação/salvamento dos contratos.
- Criar testes unitários e integração até contratos.

## Store layout (obrigatório)
Raiz: `store_root` (default `./store_data`).

- `store_data/{project}/OAS/v{n}.yaml`
- `store_data/{project}/RBAC/v{n}.json`

## Run log: hashes (obrigatório)
Arquivo: `{store_root}/{project}/runs/{execution_id}.json`

Campos mínimos recomendados:
- `oap_hash`: sha256 hex do conteúdo do arquivo `OAS/vN.yaml` salvo (bytes exatos)
- `rbac_hash`: sha256 hex do conteúdo do arquivo `RBAC/vN.json` salvo (JSON canonicalizado ou bytes salvos — escolher 1 e padronizar)

Recomendação para estabilidade:
- Para `rbac_hash`: usar JSON canonicalizado (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`).
- Para `oap_hash`: hashear os bytes UTF-8 exatamente como gravados (usar `\n` como newline).
