# store/fs_layout.md e store/artifacts_store.py — Layout de contratos

## Objetivo
Documentar e implementar persistência/versionamento para:
- OpenAPI: `OAS/vN.yaml`
- RBAC: `RBAC/vN.json`

## Layout obrigatório
- `store_data/{project}/OAS/v{n}.yaml`
- `store_data/{project}/RBAC/v{n}.json`

## Regras
- Versionamento sequencial: `v1`, `v2`, ...
- O store deve suportar salvar:
  - JSON (dict → `.json`)
  - YAML (string → `.yaml`)

## API sugerida (uma opção)
- `save_artifact(project, kind, version, content_dict)` para JSON.
- `save_text_artifact(project, kind, version, content_str, ext)` para YAML.

## Critério de aceite (Dia 1)
- Store preparado para salvar YAML e JSON nos paths obrigatórios.
