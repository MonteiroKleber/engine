# store/artifacts_store.py — Atualização para IR

## Objetivo
Adicionar suporte ao kind `IR`.

## Layout
- `store_data/{project}/IR/v{n}.json`

## Regras
- Mesma lógica de versionamento do SRS.
- `next_version(project, kind)` deve funcionar para `kind="IR"`.

## Critério de aceite (Dia 4)
- Após rodar o CLI, existem `SRS/v1.json` e `IR/v1.json`.
