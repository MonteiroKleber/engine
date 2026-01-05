# Prompt — Dia 1: Schema oficial do Plan + layout do store

Implemente as Tarefas 6.1 e 6.2 (Dia 1) da Semana 6.

1) Adicionar/confirmar `schemas/plan.schema.json`
- Usar **exatamente** o schema da Semana 2 (meta.version + meta.strategy PATCH_ONLY + tasks com id/title/order/files/acceptance).

2) Atualizar layout do store (doc + implementação)
- Documentar em `store/fs_layout.md`:
  - `store_data/{project}/PLAN/v{n}.json`
- Atualizar `store/artifacts_store.py` para suportar `kind=PLAN` com versionamento.

Critério de aceite:
- schema carregável.
- store pronto para PLAN.
