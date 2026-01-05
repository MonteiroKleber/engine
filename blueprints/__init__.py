"""Blueprints module - Organização e ordenação de PLANs.

Blueprints NÃO criam:
- Entidades
- Endpoints
- Tarefas novas

Blueprints APENAS:
- Organizam o que já existe
- Reordenam tarefas
- Agrupam por fase/tipo
"""

from .generic_blueprint import GenericBlueprint, BlueprintResult, apply_blueprint
from .registry import (
    REGISTRY,
    resolve_blueprint,
    get_registered_types,
    is_registered,
    register_blueprint,
    unregister_blueprint,
    clear_registry,
    get_blueprint_info,
)

__all__ = [
    # Generic Blueprint
    "GenericBlueprint",
    "BlueprintResult",
    "apply_blueprint",
    # Registry
    "REGISTRY",
    "resolve_blueprint",
    "get_registered_types",
    "is_registered",
    "register_blueprint",
    "unregister_blueprint",
    "clear_registry",
    "get_blueprint_info",
]
