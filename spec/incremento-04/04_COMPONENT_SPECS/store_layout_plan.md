# store/fs_layout.md e store/artifacts_store.py — Layout do PLAN

## Objetivo
Documentar e implementar persistência/versionamento do `PLAN`.

## Layout obrigatório
- `store_data/{project}/PLAN/v{n}.json`

## Regras
- Versionamento sequencial `v1`, `v2`, ...
- Mesmo comportamento de `save_artifact/load_latest/next_version` usado em SRS/IR/RBAC.

## Critério de aceite (Dia 1 e Dia 4)
- Store pronto para `kind=PLAN`.
- CLI gera `PLAN/v1.json`.
