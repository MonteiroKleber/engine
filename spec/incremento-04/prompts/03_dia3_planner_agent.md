# Prompt — Dia 3: Planner Agent (IR + OAS + RBAC → PLAN)

Implemente a Tarefa 6.4 (Dia 3) da Semana 6.

Criar `agents/planner_agent.py`.

Implementar `PlannerAgent.generate_plan(ir: dict, openapi: dict, rbac: dict) -> dict`.

Regra determinística v1 (sem LLM):
- Gerar um plano fixo baseado nas entidades do IR e operações do OpenAPI.

Estrutura do plano (ordem fixa):
Para cada entidade em `ir.domain.entities`, gerar tasks sempre nesta ordem:
1) DB migrations → `backend/src/main/resources/db/migration/V{n}__create_<entity>.sql` (acceptance: "migration compila", "tabela existe")
2) Backend model (JPA Entity) → `backend/src/main/java/.../domain/<Entity>.java` ("build backend passa")
3) Repository → `backend/src/main/java/.../repo/<Entity>Repository.java`
4) Service → `backend/src/main/java/.../service/<Entity>Service.java`
5) Controller CRUD alinhado ao OpenAPI → `backend/src/main/java/.../api/<Entity>Controller.java` ("contract tests passam" + referenciar operationIds)
6) Security mapping (RBAC) → `backend/src/main/java/.../security/SecurityConfig.java` ("endpoint exige auth")
7) Frontend pages CRUD → `frontend/src/pages/<entity>/List.tsx`, `New.tsx`, `Detail.tsx` ("typecheck passa")
8) API client → `frontend/src/api/client.ts` ("build frontend passa")

Regras:
- O Planner só gera o PLAN (não implementa código).
- `order` deve ser global 1..N.
- Cada task deve ter `files` e `acceptance` não vazios.

Critério de aceite:
- Plan contém tasks para todas entidades.
- Ordem 1..N.
- acceptance testável.
