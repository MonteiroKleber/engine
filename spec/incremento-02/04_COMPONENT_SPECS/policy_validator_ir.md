# validators/policy_validator.py — Policies do IR (Semana 4)

## Objetivo
Aplicar regras de consistência de IR além do schema.

## Policies obrigatórias
- `api_intent.resources` deve conter todas as entidades.
- `ui.pages` deve existir para cada entidade (mínimo list/new/detail).
- `nfr.security.auth_required` deve ser boolean.
- Se `domain.entities` estiver vazio → FAIL (bloqueia).

## Resultado
- Deve produzir um relatório com `ok` e lista de erros (mensagens curtas).

## Critério de aceite (Dia 6)
- Policy falha quando IR está inconsistente.
- Policy passa quando IR está consistente.
