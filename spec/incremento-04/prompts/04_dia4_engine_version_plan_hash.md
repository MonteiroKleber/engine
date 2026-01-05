# Prompt — Dia 4: Integrar no Engine + versionar + plan_hash

Implemente as Tarefas 6.5 e 6.6 (Dia 4) da Semana 6.

1) Atualizar `orchestrator/engine.py`:
- Após salvar OAS/RBAC:
  - `planner_agent.generate_plan(IR, OAS, RBAC)` → plan
  - `plan_validator` (gate)
  - `policy_validator` (PLAN) (gate)
  - salvar `PLAN/vN.json`
  - atualizar run log com `plan_hash` (hash do PLAN salvo)

2) Atualizar `store/artifacts_store.py`:
- suportar `kind=PLAN` com versionamento e persistência.

Critério de aceite:
- CLI gera `PLAN/v1.json`.
- run log inclui `plan_hash`.
