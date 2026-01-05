# Prompt — Dia 4: Contracts Agent (IR → OpenAPI + RBAC)

Implemente a Tarefa 5.5 (Dia 4) da Semana 5.

Criar `agents/contracts_agent.py`.

Implementar `ContractsAgent.generate_contracts(ir: dict) -> tuple[str, dict]` retornando:
- `openapi_yaml_str`
- `rbac_dict`

Regras determinísticas v1:
- Baseado em `ir.api_intent.resources` e `ir.domain.entities`.
- Para cada resource/entity gerar CRUD padrão:
  - GET /api/<entityPlural> → list<Entity>
  - POST /api/<entityPlural> → create<Entity>
  - GET /api/<entityPlural>/{id} → get<Entity>
  - PUT /api/<entityPlural>/{id} → update<Entity>
  - DELETE /api/<entityPlural>/{id} → delete<Entity>
- `operationId` fixo conforme acima.
- `tags = [Entity]`.
- `responses` mínimo:
  - 200 para GET/PUT/DELETE
  - 201 para POST
  - 400 e 500 sempre presentes
- `components/schemas/<Entity>` com campos do IR; `id` sempre string.

RBAC:
- `roles = ["authenticated", "admin"]`
- Todos operationIds exigem `"authenticated"`.

Regra:
- Não inventar endpoints além de CRUD.

Critério de aceite:
- Para IR com 1 entidade, gera OpenAPI com 5 rotas.
- Gera RBAC com permissões para todas as operations.
