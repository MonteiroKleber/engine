# validators/policy_validator.py — Policies de contratos (Semana 5)

## Objetivo
Aplicar regras de consistência entre OpenAPI e RBAC, e bloquear endpoint sem auth.

## Policies obrigatórias
- Todo `operationId` no OpenAPI deve existir em `rbac.permissions[].operation_id`.
- `rbac.roles` deve conter `authenticated`.
- Nenhuma operação pode ficar sem permissão.
- Proibir OpenAPI sem `components/schemas`.

## Interpretação de “endpoint sem auth = ERRO”
- Se existir `operationId` no OpenAPI sem permission correspondente no RBAC → FAIL.
- Se existir permission com `required_role` vazio/nulo → FAIL.

## Critério de aceite (Dia 6)
- Se apagar uma permissão do RBAC, policy falha.
- Se remover `operationId` de uma rota, openapi validator falha.
