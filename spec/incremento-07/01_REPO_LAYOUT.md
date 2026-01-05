# Estrutura e integração (Semana 9)

## Novos arquivos (no engine)
- `/home/bazari/engine/blueprints/generic_blueprint.py`
- `/home/bazari/engine/blueprints/registry.py`
- `/home/bazari/engine/validators/blueprint_policy_validator.py`

## Arquivo atualizado
- `/home/bazari/engine/orchestrator/engine.py`

## Integração obrigatória
- Classificador tenta identificar blueprint.
- Se não existir no registry: FORCED_GENERIC.
- Run log registra:
  - `blueprint: "GENERIC"`

## Anti-invenção
- Blueprint só pode consumir `ir`, `oas`, `rbac`, `plan`.
- Blueprint não pode produzir entidades/endpoints/tasks nem alterar contratos.
