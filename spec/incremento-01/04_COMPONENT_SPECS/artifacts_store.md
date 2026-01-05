# store/artifacts_store.py — Especificação

## Objetivo
Persistir artefatos (principalmente SRS) com versionamento e registrar logs de execução.

## Layout fixo
`{store_root}/{project_name}/SRS/vN.json`
`{store_root}/{project_name}/logs/`
`{store_root}/{project_name}/runs/{execution_id}.json`

## Funções obrigatórias
### next_version(project, kind) -> int
- Retorna o próximo número inteiro disponível (1 se não existir nada).
- Considerar apenas arquivos `v*.json` dentro do diretório do `kind`.

### save_artifact(project, kind, version, content_dict) -> str
- Garante diretórios.
- Serializa JSON com UTF-8.
- Salva em `{store_root}/{project}/{kind}/v{version}.json`.
- Retorna o path salvo.

### load_latest(project, kind) -> dict | None
- Carrega a maior versão disponível.
- Retorna `None` se não existir.

### write_run_log(execution_id, payload) -> str
- Escreve JSON em `{store_root}/{project}/runs/{execution_id}.json`.
- `payload` deve ser serializável em JSON.
- Retorna o path.

## Regras
- Não “pular” versões.
- Não alterar conteúdo já salvo.
