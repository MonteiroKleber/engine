# blueprints/registry.py — Registry de Blueprints

## Objetivo
Resolver blueprint por `project_type` com fallback FORCED_GENERIC.

## API
```py
def resolve_blueprint(project_type: str):
    if project_type in REGISTRY:
        return REGISTRY[project_type]
    return GenericBlueprint  # FORCED_GENERIC
```

## Regras
- Lógica fechada: sem heurística, sem inferência.
- Se não existir no registry: sempre `GenericBlueprint`.

## Critério de aceite (Dia 2)
- `resolve_blueprint("unknown")` retorna GenericBlueprint.
