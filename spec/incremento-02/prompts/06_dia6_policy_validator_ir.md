# Prompt — Dia 6: Regras de consistência (policy validator)

Implemente a Tarefa 4.7 (Dia 6) da Semana 4.

Atualizar `validators/policy_validator.py` para incluir policy do IR:

Policies obrigatórias:
- `api_intent.resources` deve conter todas entidades
- `ui.pages` deve existir para cada entidade (mínimo list/new/detail)
- `nfr.security.auth_required` deve ser boolean
- se `domain.entities` estiver vazio → FAIL (bloqueia)

Critério de aceite:
- Policy falha quando IR está inconsistente
- Policy passa quando IR está consistente
