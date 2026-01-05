# orchestrator/engine.py — Integração FORCED_GENERIC

## Objetivo
Garantir que o engine use blueprint genérico quando não existir blueprint específico.

## Fluxo obrigatório
1) Classificador tenta identificar blueprint.
2) Resolver via `resolve_blueprint(project_type)`.
3) Se não existir → FORCED_GENERIC.
4) Aplicar blueprint (GenericBlueprint) como no-op estruturado.

## Run log
- Registrar sempre `"blueprint": "GENERIC"` quando fallback ocorrer.

## Regras
- Nenhum caminho alternativo.
- Sem inferência.

## Critério de aceite (Dia 3)
- Pipeline roda com blueprint genérico.
- Run log contém `blueprint=GENERIC`.
