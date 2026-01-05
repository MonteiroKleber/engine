# Prompt — Dia 6: Testes unitários do planner + validator

Implemente a Tarefa 6.8 (Dia 6) da Semana 6.

Criar:
- `tests/test_plan_validator.py`
- `tests/test_planner_agent.py`
- `tests/test_plan_schema.py` (se ainda não existir)

Testes obrigatórios:
- planner cria tasks na ordem correta.
- `order` é 1..N.
- cada task tem `files` e `acceptance`.
- validator rejeita:
  - order faltando
  - id duplicado
  - task sem files

Critério de aceite:
- testes unit verdes.
