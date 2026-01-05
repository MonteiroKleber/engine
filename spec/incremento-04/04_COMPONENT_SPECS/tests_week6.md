# Tests — Semana 6

## Unitários
- `tests/test_plan_schema.py`: carrega `schemas/plan.schema.json`.
- `tests/test_plan_validator.py`: schema + regras internas (order 1..N, ids únicos, files/acceptance não vazios).
- `tests/test_planner_agent.py`: gera tasks por entidade na ordem correta e com conteúdo mínimo.

## Integração
- `tests/test_pipeline_to_plan.py`:
  - pipeline completo gera PLAN
  - versionamento incrementa
  - run log inclui `plan_hash`
  - `plan_hash` bate com arquivo
