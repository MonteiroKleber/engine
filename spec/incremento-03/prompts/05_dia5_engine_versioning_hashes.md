# Prompt — Dia 5: Integrar no Engine + versionamento + hashes

Implemente as Tarefas 5.6 e 5.7 (Dia 5) da Semana 5.

1) Atualizar `orchestrator/engine.py` para adicionar etapas:
- carregar/usar IR gerado
- `contracts_agent.generate_contracts(IR)` → openapi_yaml, rbac
- `openapi_validator` (gate)
- `rbac_validator` (gate)
- `policy_validator` (contratos) (gate)
- salvar OpenAPI em `OAS/vN.yaml`
- salvar RBAC em `RBAC/vN.json`
- atualizar run log com hashes:
  - `oap_hash` (hash do YAML salvo)
  - `rbac_hash` (hash do JSON salvo)

2) Atualizar Artifact Store para salvar YAML
- Criar `save_text_artifact(project, kind, version, content_str, ext)`
  OU
- Adaptar `save_artifact` para aceitar `str` e escolher extensão.

Critério de aceite:
- CLI gera: `SRS/v1.json`, `IR/v1.json`, `OAS/v1.yaml`, `RBAC/v1.json`.
- Run log contém `input_hash`, `srs_hash`, `ir_hash`, `oap_hash`, `rbac_hash`.
