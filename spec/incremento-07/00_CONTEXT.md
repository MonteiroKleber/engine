# Contexto e Escopo

## Objetivo imutável da Semana 9
Garantir que o motor:
- funcione sem blueprint específico
- não invente nada
- use apenas SRS + IR + OAS + RBAC + PLAN
- tenha fallback seguro e determinístico

Blueprint passa a ser:
- atalho controlado, nunca criatividade.

## Contexto fixo
- Root: `/home/bazari/`
- Engine: `/home/bazari/engine/`

## Componentes a implementar/atualizar
- `blueprints/generic_blueprint.py`
- `blueprints/registry.py`
- `validators/blueprint_policy_validator.py`
- `orchestrator/engine.py` (integração FORCED_GENERIC + log)
- testes unitários e de sistema

## Regras absolutas (anti-invenção)
- GenericBlueprint:
  - NÃO cria entidades
  - NÃO cria endpoints
  - NÃO cria tarefas novas
  - NÃO altera IR/OAS/PLAN
  - Apenas organiza/ordena o que já existe

## Critério de pronto (Semana 9 concluída)
- Blueprint Genérico implementado e registrado.
- FORCED_GENERIC funcionando (fallback sem heurística).
- Gates impedem invenção.
- Sistema funciona sem blueprint específico.
- Testes verdes.
- Demo CLI registra blueprint como GENERIC e build passa.
