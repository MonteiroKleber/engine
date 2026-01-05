# Prompt — Dia 1: Schemas oficiais (RBAC) + layout no store

Implemente as Tarefas 5.1 e 5.2 (Dia 1) da Semana 5.

1) Adicionar `schemas/rbac.schema.json`
- Usar **exatamente** o schema RBAC da Semana 2 (roles + permissions com operation_id + required_role).

2) Definir layout de store (documentar e implementar)
- Atualizar `store/fs_layout.md` documentando:
  - `store_data/{project}/OAS/v{n}.yaml`
  - `store_data/{project}/RBAC/v{n}.json`
- Preparar `store/artifacts_store.py` para salvar YAML e JSON nesses paths.

Critério de aceite:
- Schema RBAC carregável.
- Store preparado para salvar YAML e JSON.
