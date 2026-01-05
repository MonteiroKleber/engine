# agents/planner_agent.py — Especificação

## Objetivo
Gerar um `PLAN` determinístico v1 a partir de:
- `ir: dict`
- `openapi: dict`
- `rbac: dict`

## API
- `class PlannerAgent:`
  - `generate_plan(ir: dict, openapi: dict, rbac: dict) -> dict`

## Estratégia (congelada)
- `meta.strategy` deve ser `PATCH_ONLY`.

## Regra determinística v1
Gerar um plano fixo baseado:
- nas entidades em `ir.domain.entities`
- nas operações em OpenAPI (para compor acceptance/checagens)

## Estrutura do plano (ordem fixa, por entidade)
Para cada entidade `Entity` em `ir.domain.entities`, gerar tasks sempre na mesma ordem:

1) DB migrations
- files:
  - `backend/src/main/resources/db/migration/V{n}__create_<entity>.sql`
- acceptance (exemplos mínimos):
  - "migration compila"
  - "tabela existe"

2) Backend model (JPA Entity)
- files:
  - `backend/src/main/java/.../domain/<Entity>.java`
- acceptance:
  - "build backend passa"

3) Repository
- files:
  - `backend/src/main/java/.../repo/<Entity>Repository.java`
- acceptance:
  - "build backend passa"

4) Service
- files:
  - `backend/src/main/java/.../service/<Entity>Service.java`
- acceptance:
  - "build backend passa"

5) Controller CRUD alinhado ao OpenAPI
- files:
  - `backend/src/main/java/.../api/<Entity>Controller.java`
- acceptance:
  - "contract tests passam"
  - incluir (em texto) referência a operationIds relevantes

6) Security mapping (RBAC)
- files:
  - `backend/src/main/java/.../security/SecurityConfig.java`
- acceptance:
  - "endpoint exige auth"

7) Frontend pages CRUD
- files:
  - `frontend/src/pages/<entity>/List.tsx`
  - `frontend/src/pages/<entity>/New.tsx`
  - `frontend/src/pages/<entity>/Detail.tsx`
- acceptance:
  - "typecheck passa"

8) API client
- files:
  - `frontend/src/api/client.ts`
- acceptance:
  - "build frontend passa"

## Regras
- `tasks[*].order` deve ser global (1..N no plano inteiro).
- `tasks[*].files` e `tasks[*].acceptance` devem ser listas não vazias.
- IDs devem ser estáveis e únicos (ex.: prefixo por entidade + tipo de task).

## Critério de aceite (Dia 3)
- Plan contém tasks para todas entidades.
- Cada task tem files reais e acceptance testável.
- Ordem 1..N.
