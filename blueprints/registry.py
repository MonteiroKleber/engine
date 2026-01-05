"""Registry de Blueprints - Mapeamento fechado de tipos de projeto para blueprints.

REGRAS ABSOLUTAS:
- Sem heurística
- Sem inferência
- Lógica puramente baseada em lookup no REGISTRY
- Se não encontrado, retorna GenericBlueprint (FORCED_GENERIC)

O registry é uma estrutura fechada:
- Tipos de projeto são explicitamente mapeados
- Não há tentativa de "adivinhar" o blueprint correto
- O GenericBlueprint é o fallback seguro (no-op)
"""

from typing import Dict, Type, Optional

from blueprints.generic_blueprint import GenericBlueprint


# ==================== REGISTRY ====================

# Mapeamento fechado: project_type -> Blueprint class
# Inicialmente vazio, será expandido em dias posteriores
REGISTRY: Dict[str, Type[GenericBlueprint]] = {
    # Dia 3+: Adicionar blueprints específicos aqui
    # "crud": CRUDBlueprint,
    # "auth": AuthBlueprint,
    # "report": ReportBlueprint,
}


# ==================== RESOLVE FUNCTION ====================


def resolve_blueprint(project_type: str) -> Type[GenericBlueprint]:
    """Resolve o blueprint para um tipo de projeto.

    Lógica fechada:
    1. Se project_type está no REGISTRY, retorna o blueprint registrado
    2. Caso contrário, retorna GenericBlueprint (FORCED_GENERIC)

    NÃO FAZ:
    - Heurística baseada em nome
    - Inferência baseada em conteúdo
    - Fuzzy matching
    - Fallback para múltiplos tipos

    Args:
        project_type: Tipo do projeto (ex: "crud", "auth", "report")

    Returns:
        Classe do blueprint a ser usado
    """
    # Normalizar para lowercase para consistência
    normalized_type = project_type.lower().strip() if project_type else ""

    # Lookup direto no registry
    if normalized_type in REGISTRY:
        return REGISTRY[normalized_type]

    # FORCED_GENERIC: fallback seguro
    return GenericBlueprint


def get_registered_types() -> list[str]:
    """Retorna lista de tipos de projeto registrados.

    Returns:
        Lista de project_types com blueprints específicos
    """
    return list(REGISTRY.keys())


def is_registered(project_type: str) -> bool:
    """Verifica se um tipo de projeto tem blueprint específico.

    Args:
        project_type: Tipo do projeto

    Returns:
        True se há blueprint específico registrado
    """
    normalized_type = project_type.lower().strip() if project_type else ""
    return normalized_type in REGISTRY


def register_blueprint(
    project_type: str,
    blueprint_class: Type[GenericBlueprint],
) -> None:
    """Registra um blueprint para um tipo de projeto.

    ATENÇÃO: Esta função modifica o REGISTRY global.
    Deve ser usada apenas durante inicialização do sistema.

    Args:
        project_type: Tipo do projeto
        blueprint_class: Classe do blueprint

    Raises:
        ValueError: Se project_type for vazio
        TypeError: Se blueprint_class não for subclasse de GenericBlueprint
    """
    if not project_type or not project_type.strip():
        raise ValueError("project_type cannot be empty")

    if not isinstance(blueprint_class, type):
        raise TypeError("blueprint_class must be a class")

    if not issubclass(blueprint_class, GenericBlueprint):
        raise TypeError(
            f"blueprint_class must be subclass of GenericBlueprint, "
            f"got {blueprint_class.__name__}"
        )

    normalized_type = project_type.lower().strip()
    REGISTRY[normalized_type] = blueprint_class


def unregister_blueprint(project_type: str) -> bool:
    """Remove um blueprint do registry.

    ATENÇÃO: Esta função modifica o REGISTRY global.
    Deve ser usada apenas para testes ou cleanup.

    Args:
        project_type: Tipo do projeto a remover

    Returns:
        True se foi removido, False se não existia
    """
    normalized_type = project_type.lower().strip() if project_type else ""

    if normalized_type in REGISTRY:
        del REGISTRY[normalized_type]
        return True

    return False


def clear_registry() -> None:
    """Limpa todo o registry.

    ATENÇÃO: Esta função modifica o REGISTRY global.
    Deve ser usada apenas para testes.
    """
    REGISTRY.clear()


# ==================== BLUEPRINT INFO ====================


def get_blueprint_info(project_type: str) -> Dict[str, str]:
    """Retorna informações sobre o blueprint para um tipo de projeto.

    Args:
        project_type: Tipo do projeto

    Returns:
        Dicionário com informações do blueprint
    """
    blueprint_class = resolve_blueprint(project_type)

    return {
        "project_type": project_type,
        "blueprint_class": blueprint_class.__name__,
        "is_generic": blueprint_class == GenericBlueprint,
        "is_registered": is_registered(project_type),
    }
