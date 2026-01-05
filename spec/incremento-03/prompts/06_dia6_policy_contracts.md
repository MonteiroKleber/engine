# Prompt — Dia 6: Policies obrigatórias (endpoint sem auth = ERRO)

Implemente a Tarefa 5.8 (Dia 6) da Semana 5.

Atualizar `validators/policy_validator.py` com policy de contratos:
- Todo `operationId` no OpenAPI deve existir em `rbac.permissions[].operation_id`.
- `rbac.roles` deve conter `authenticated`.
- Nenhuma operação pode ficar sem permissão.
- Proibir OpenAPI sem `components/schemas`.

Critério de aceite:
- Se apagar uma permissão do RBAC, policy falha.
- Se remover `operationId` de uma rota, openapi validator falha.
