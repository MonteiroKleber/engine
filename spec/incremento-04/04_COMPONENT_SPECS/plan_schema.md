# schemas/plan.schema.json — Especificação

## Objetivo
Adicionar/confirmar o schema oficial do plano em `schemas/plan.schema.json`.

## Fonte do schema
- Usar **exatamente** o schema da Semana 2.
- Elementos essenciais:
  - `meta.version`
  - `meta.strategy` (deve aceitar `PATCH_ONLY`)
  - `tasks[]` com `id`, `title`, `order`, `files`, `acceptance`

## Critério de aceite (Dia 1)
- Schema carregável por `tests/test_plan_schema.py` sem erro.
