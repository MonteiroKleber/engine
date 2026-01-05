# Prompt — Dia 2: Artifact Store + Schemas

Implemente `store/artifacts_store.py` conforme layout fixo:
- store_data/{project_name}/SRS/vN.json
- store_data/{project_name}/logs/
- store_data/{project_name}/runs/

Funções obrigatórias:
- save_artifact(project, kind, version, content_dict)
- load_latest(project, kind)
- next_version(project, kind)
- write_run_log(execution_id, payload)

Depois, coloque em `schemas/`:
- `srs.schema.json` (Semana 2)
- `blueprint.schema.json`

Aceite:
- consegue salvar e versionar SRS.json
- schemas existem localmente.
