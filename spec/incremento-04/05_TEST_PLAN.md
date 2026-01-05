# Plano de testes (Semana 6)

## Unitários (novos)
- `tests/test_plan_schema.py` (se não existir)
- `tests/test_plan_validator.py`
- `tests/test_planner_agent.py`

Obrigatório:
- planner cria tasks na ordem correta.
- `order` é 1..N sem buracos.
- cada task tem `files` e `acceptance` não vazios.
- validator rejeita: order faltando, id duplicado, task sem files.

## Integração (novo)
- `tests/test_pipeline_to_plan.py`

Obrigatório:
- pipeline completo gera PLAN.
- versionamento incrementa.
- run log contém `plan_hash`.
- `plan_hash` bate com o arquivo salvo.

## Critério final
- `pytest` verde.
