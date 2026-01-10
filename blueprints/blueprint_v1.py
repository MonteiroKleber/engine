"""Blueprint v1 - Domain templates for IDL Draft pre-population.

Blueprints provide domain-specific suggestions (actors, entities, usecases, etc.)
that can be used to accelerate onboarding WITHOUT inventing domain knowledge.

Key rules:
- Blueprints only PRE-FILL IDL Draft
- Blueprints NEVER skip gates
- Blueprints are versioned, deterministic, and auditable

Schema Version: blueprint.v1
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema


# =============================================================================
# Constants
# =============================================================================

BLUEPRINT_SCHEMA_VERSION = "blueprint.v1"


# =============================================================================
# Schema Loading
# =============================================================================

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "blueprint.v1.json"
_BLUEPRINT_SCHEMA: Optional[dict] = None


def _get_schema() -> dict:
    """Load and cache the blueprint schema."""
    global _BLUEPRINT_SCHEMA
    if _BLUEPRINT_SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _BLUEPRINT_SCHEMA = json.load(f)
    return _BLUEPRINT_SCHEMA


# =============================================================================
# Exceptions
# =============================================================================


class BlueprintValidationError(Exception):
    """Exception raised when blueprint validation fails.

    Error messages are prefixed with "SCHEMA: " following project conventions.
    """

    def __init__(self, message: str, path: str = ""):
        self.message = message
        self.path = path
        super().__init__(f"SCHEMA: {path}: {message}" if path else f"SCHEMA: {message}")


# =============================================================================
# Validation
# =============================================================================


def validate_blueprint(blueprint: dict) -> None:
    """Validate a blueprint against the schema.

    Args:
        blueprint: The blueprint dict to validate

    Raises:
        BlueprintValidationError: If validation fails (prefixed with "SCHEMA: ...")
    """
    schema = _get_schema()

    # JSON Schema validation
    try:
        jsonschema.validate(instance=blueprint, schema=schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else ""
        raise BlueprintValidationError(e.message, path)

    # Additional semantic validations

    # 1. Check for duplicate actor IDs
    defaults = blueprint.get("defaults", {})
    actors = defaults.get("actors", [])
    actor_ids = [a.get("id") for a in actors]
    if len(actor_ids) != len(set(actor_ids)):
        duplicates = [aid for aid in actor_ids if actor_ids.count(aid) > 1]
        raise BlueprintValidationError(
            f"Duplicate actor id: {duplicates[0]}", "defaults.actors"
        )

    # 2. Check for duplicate entity IDs
    entities = defaults.get("entities", [])
    entity_ids = [e.get("id") for e in entities]
    if len(entity_ids) != len(set(entity_ids)):
        duplicates = [eid for eid in entity_ids if entity_ids.count(eid) > 1]
        raise BlueprintValidationError(
            f"Duplicate entity id: {duplicates[0]}", "defaults.entities"
        )

    # 3. Check for duplicate usecase IDs
    usecases = defaults.get("usecases", [])
    usecase_ids = [u.get("id") for u in usecases]
    if len(usecase_ids) != len(set(usecase_ids)):
        duplicates = [uid for uid in usecase_ids if usecase_ids.count(uid) > 1]
        raise BlueprintValidationError(
            f"Duplicate usecase id: {duplicates[0]}", "defaults.usecases"
        )

    # 4. Check for duplicate field names within each entity
    for i, entity in enumerate(entities):
        fields = entity.get("fields", [])
        field_names = [f.get("name") for f in fields]
        if len(field_names) != len(set(field_names)):
            duplicates = [fn for fn in field_names if field_names.count(fn) > 1]
            raise BlueprintValidationError(
                f"Duplicate field name: {duplicates[0]}", f"defaults.entities[{i}].fields"
            )


# =============================================================================
# Canonicalization
# =============================================================================


def _sort_actors(actors: List[dict]) -> List[dict]:
    """Sort actors by id."""
    return sorted(actors, key=lambda a: a.get("id", ""))


def _sort_entities(entities: List[dict]) -> List[dict]:
    """Sort entities by id, and fields within each entity by name."""
    sorted_entities = []
    for entity in sorted(entities, key=lambda e: e.get("id", "")):
        entity_copy = deepcopy(entity)
        if "fields" in entity_copy:
            entity_copy["fields"] = sorted(
                entity_copy["fields"], key=lambda f: f.get("name", "")
            )
        sorted_entities.append(entity_copy)
    return sorted_entities


def _sort_usecases(usecases: List[dict]) -> List[dict]:
    """Sort usecases by id, and flow steps by step number."""
    sorted_usecases = []
    for usecase in sorted(usecases, key=lambda u: u.get("id", "")):
        usecase_copy = deepcopy(usecase)
        if "flow" in usecase_copy:
            usecase_copy["flow"] = sorted(
                usecase_copy["flow"], key=lambda s: s.get("step", 0)
            )
        sorted_usecases.append(usecase_copy)
    return sorted_usecases


def _sort_integrations(integrations: List[dict]) -> List[dict]:
    """Sort integrations by (system, type)."""
    return sorted(
        integrations,
        key=lambda i: (i.get("system", ""), i.get("type", ""))
    )


def canonicalize_blueprint(blueprint: dict) -> dict:
    """Canonicalize a blueprint for deterministic comparison.

    Applies stable ordering to all lists:
    - actors: sorted by id
    - entities: sorted by id, fields sorted by name
    - usecases: sorted by id, flow sorted by step
    - integrations: sorted by (system, type)

    Does NOT modify values, only ordering.

    Args:
        blueprint: The blueprint dict to canonicalize

    Returns:
        A new dict with canonical ordering (original is not mutated)
    """
    result = deepcopy(blueprint)

    defaults = result.get("defaults", {})

    if "actors" in defaults:
        defaults["actors"] = _sort_actors(defaults["actors"])

    if "entities" in defaults:
        defaults["entities"] = _sort_entities(defaults["entities"])

    if "usecases" in defaults:
        defaults["usecases"] = _sort_usecases(defaults["usecases"])

    if "integrations" in defaults:
        defaults["integrations"] = _sort_integrations(defaults["integrations"])

    result["defaults"] = defaults

    return result


# =============================================================================
# Loading
# =============================================================================


def load_blueprint(path: Path) -> dict:
    """Load and validate a blueprint from a JSON file.

    Args:
        path: Path to the blueprint JSON file

    Returns:
        Validated blueprint dict

    Raises:
        FileNotFoundError: If the file does not exist
        BlueprintValidationError: If the blueprint is invalid
    """
    if not path.exists():
        raise FileNotFoundError(f"Blueprint not found: {path}")

    try:
        with open(path) as f:
            blueprint = json.load(f)
    except json.JSONDecodeError as e:
        raise BlueprintValidationError(f"Invalid JSON: {e}")

    validate_blueprint(blueprint)

    return blueprint


# =============================================================================
# Helper Functions
# =============================================================================


def get_blueprint_actors(blueprint: dict) -> List[dict]:
    """Get actors from a blueprint.

    Args:
        blueprint: Validated blueprint dict

    Returns:
        List of actor dicts
    """
    return blueprint.get("defaults", {}).get("actors", [])


def get_blueprint_entities(blueprint: dict) -> List[dict]:
    """Get entities from a blueprint.

    Args:
        blueprint: Validated blueprint dict

    Returns:
        List of entity dicts
    """
    return blueprint.get("defaults", {}).get("entities", [])


def get_blueprint_usecases(blueprint: dict) -> List[dict]:
    """Get usecases from a blueprint.

    Args:
        blueprint: Validated blueprint dict

    Returns:
        List of usecase dicts
    """
    return blueprint.get("defaults", {}).get("usecases", [])


def get_blueprint_integrations(blueprint: dict) -> List[dict]:
    """Get integrations from a blueprint.

    Args:
        blueprint: Validated blueprint dict

    Returns:
        List of integration dicts
    """
    return blueprint.get("defaults", {}).get("integrations", [])


def get_blueprint_nonfunctional(blueprint: dict) -> Optional[dict]:
    """Get non-functional requirements from a blueprint.

    Args:
        blueprint: Validated blueprint dict

    Returns:
        Non-functional requirements dict or None
    """
    return blueprint.get("defaults", {}).get("nonfunctional")


def is_compatible_with_draft(blueprint: dict, draft_version: str = "idl_draft.v1") -> bool:
    """Check if blueprint is compatible with a given IDL Draft version.

    Args:
        blueprint: Validated blueprint dict
        draft_version: IDL Draft schema version to check

    Returns:
        True if compatible
    """
    compat = blueprint.get("compat", {})
    return compat.get("idl_draft_schema_version") == draft_version
