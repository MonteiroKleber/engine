# Prompt — Dia 2: Registry de Blueprints

Implemente o Dia 2 da Semana 9.

Criar:
- `/home/bazari/engine/blueprints/registry.py`

Implementar lógica fechada:
```py
def resolve_blueprint(project_type: str):
    if project_type in REGISTRY:
        return REGISTRY[project_type]
    return GenericBlueprint  # FORCED_GENERIC
```

Regras:
- Sem heurística.
- Sem inferência.
