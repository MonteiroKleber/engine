# orchestrator/engine.py — Integração do PLAN

## Objetivo
Integrar geração/validação/persistência do PLAN após contratos (OAS + RBAC).

## Etapas novas (após salvar OAS/RBAC)
1) `planner_agent.generate_plan(IR, OAS, RBAC)` → `plan`
2) `plan_validator` (gate)
3) `policy_validator` (PLAN) (gate)
4) salvar `PLAN/vN.json`
5) atualizar run log com `plan_hash`

## Gates
- Se gate falhar: não salvar PLAN.

## Critério de aceite (Dia 4)
- CLI gera `PLAN/v1.json`.
- Run log inclui `plan_hash`.
