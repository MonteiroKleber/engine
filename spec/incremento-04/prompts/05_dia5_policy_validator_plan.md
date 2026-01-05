# Prompt — Dia 5: Policy Validator do Plan (regras de execução)

Implemente a Tarefa 6.7 (Dia 5) da Semana 6.

Atualizar `validators/policy_validator.py` para incluir policies do PLAN:
- Para cada entidade do IR deve existir ao menos:
  - 1 task de DB
  - 1 task de backend controller
  - 1 task de frontend page

- Todo `operationId` do OAS deve aparecer em alguma task de controller/contract test (via string em `acceptance`).

- Se `meta.strategy != PATCH_ONLY` → FAIL.

Critério de aceite:
- remover tasks essenciais quebra policy.
- plan com tasks incompletas falha.
