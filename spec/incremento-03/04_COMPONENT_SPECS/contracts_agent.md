# agents/contracts_agent.py — Especificação

## Objetivo
Gerar contratos determinísticos v1 a partir do IR:
- OpenAPI (YAML string)
- RBAC (dict)

## API
- `class ContractsAgent:`
  - `generate_contracts(ir: dict) -> tuple[str, dict]`

Retorno:
- `openapi_yaml_str`: string YAML
- `rbac_dict`: dict compatível com `schemas/rbac.schema.json`

## Regras determinísticas v1 (sem LLM)
Baseado em:
- `ir.api_intent.resources`
- `ir.domain.entities`

### Pluralização (determinística v1)
- `entityPlural = lowercase(entity_name) + "s"` (sem regras especiais).

### Endpoints CRUD (somente)
Para cada resource/entity gerar exatamente 5 operações:
- `GET /api/<entityPlural>` → `list<Entity>`
- `POST /api/<entityPlural>` → `create<Entity>`
- `GET /api/<entityPlural>/{id}` → `get<Entity>`
- `PUT /api/<entityPlural>/{id}` → `update<Entity>`
- `DELETE /api/<entityPlural>/{id}` → `delete<Entity>`

### Padrões fixos
- `operationId`: `listCompany`, `createCompany`, etc.
- `tags`: `[Entity]` (string da entidade)
- `responses` mínimo:
  - `200` para GET/PUT/DELETE
  - `201` para POST
  - `400` e `500` sempre presentes

### Schemas
- Criar `components/schemas/<Entity>` com campos do IR.
- Campo `id` sempre presente (tipo string).

### RBAC
- `roles = ["authenticated", "admin"]`
- Para cada `operationId` gerado, criar permission exigindo `required_role="authenticated"`.

## Restrições
- Não inventar endpoints além de CRUD.

## Critério de aceite (Dia 4)
- Para um IR com 1 entidade, gera OpenAPI com 5 rotas.
- Gera RBAC com permissões para todas as operations.
