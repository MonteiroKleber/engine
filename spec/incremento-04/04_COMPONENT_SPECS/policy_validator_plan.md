# validators/policy_validator.py — Policies do PLAN (Semana 6)

## Objetivo
Aplicar regras de consistência/executabilidade do PLAN além do schema.

## Policies obrigatórias
- Para cada entidade do IR deve existir ao menos:
  - 1 task de DB
  - 1 task de backend controller
  - 1 task de frontend page

- Todo `operationId` do OAS deve aparecer em alguma task de controller/contract test (via string em `acceptance`).

- Se `meta.strategy != PATCH_ONLY` → FAIL.

## Critério de aceite (Dia 5)
- remover tasks essenciais quebra policy.
- plan com tasks incompletas falha.
