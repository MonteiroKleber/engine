"""Blueprint Registry v1 - File-based registry with integrity verification.

The registry maintains an index.json file that tracks:
- All registered blueprints with their paths
- Content hashes for integrity verification
- Metadata (domain, version)

Key features:
- Deterministic ordering (sorted by blueprint_id)
- Content hash verification using SHA256 on canonicalized blueprints
- Integrity checks with "INTEGRITY:" prefix errors

Schema Version: blueprint_registry.v1
"""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema

from blueprints.blueprint_v1 import (
    canonicalize_blueprint,
    validate_blueprint,
    load_blueprint,
    BlueprintValidationError,
)


# =============================================================================
# Constants
# =============================================================================

REGISTRY_SCHEMA_VERSION = "blueprint_registry.v1"

_REGISTRY_DIR = Path(__file__).parent / "registry"
_INDEX_PATH = _REGISTRY_DIR / "index.json"
_BLUEPRINTS_DIR = _REGISTRY_DIR / "blueprints"

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "blueprint_registry.v1.json"
_REGISTRY_SCHEMA: Optional[dict] = None


# =============================================================================
# Schema Loading
# =============================================================================


def _get_registry_schema() -> dict:
    """Load and cache the registry schema."""
    global _REGISTRY_SCHEMA
    if _REGISTRY_SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _REGISTRY_SCHEMA = json.load(f)
    return _REGISTRY_SCHEMA


# =============================================================================
# Exceptions
# =============================================================================


class RegistryValidationError(Exception):
    """Exception raised when registry validation fails.

    Error messages are prefixed with "SCHEMA: " following project conventions.
    """

    def __init__(self, message: str, path: str = ""):
        self.message = message
        self.path = path
        super().__init__(f"SCHEMA: {path}: {message}" if path else f"SCHEMA: {message}")


class RegistryIntegrityError(Exception):
    """Exception raised when registry integrity verification fails.

    Error messages are prefixed with "INTEGRITY: " following project conventions.
    """

    def __init__(self, message: str, blueprint_id: str = ""):
        self.message = message
        self.blueprint_id = blueprint_id
        prefix = f"INTEGRITY: {blueprint_id}: " if blueprint_id else "INTEGRITY: "
        super().__init__(f"{prefix}{message}")


# =============================================================================
# Hash Computation
# =============================================================================


def compute_content_hash(blueprint: dict) -> str:
    """Compute SHA256 hash of a canonicalized blueprint.

    Args:
        blueprint: The blueprint dict (will be canonicalized before hashing)

    Returns:
        Hex-encoded SHA256 hash
    """
    # Canonicalize for deterministic hashing
    canonical = canonicalize_blueprint(blueprint)

    # Serialize with sorted keys and no whitespace variations
    content = json.dumps(canonical, sort_keys=True, separators=(",", ":"))

    # Compute hash
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# =============================================================================
# Registry Validation
# =============================================================================


def validate_registry(registry: dict) -> None:
    """Validate a registry against the schema.

    Args:
        registry: The registry dict to validate

    Raises:
        RegistryValidationError: If validation fails (prefixed with "SCHEMA: ...")
    """
    schema = _get_registry_schema()

    # JSON Schema validation
    try:
        jsonschema.validate(instance=registry, schema=schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else ""
        raise RegistryValidationError(e.message, path)

    # Additional semantic validations

    # Check for duplicate blueprint_ids
    blueprints = registry.get("blueprints", [])
    blueprint_ids = [b.get("blueprint_id") for b in blueprints]
    if len(blueprint_ids) != len(set(blueprint_ids)):
        duplicates = [bid for bid in blueprint_ids if blueprint_ids.count(bid) > 1]
        raise RegistryValidationError(
            f"Duplicate blueprint_id: {duplicates[0]}", "blueprints"
        )

    # Check ordering (must be sorted by blueprint_id)
    for i in range(len(blueprint_ids) - 1):
        if blueprint_ids[i] > blueprint_ids[i + 1]:
            raise RegistryValidationError(
                f"blueprints not sorted by blueprint_id: {blueprint_ids[i]} > {blueprint_ids[i + 1]}",
                "blueprints"
            )


# =============================================================================
# Registry Loading and Saving
# =============================================================================


def load_registry(registry_dir: Optional[Path] = None) -> dict:
    """Load the registry from index.json.

    Args:
        registry_dir: Optional path to registry directory (defaults to built-in)

    Returns:
        Validated registry dict

    Raises:
        FileNotFoundError: If index.json does not exist
        RegistryValidationError: If the registry is invalid
    """
    if registry_dir is None:
        registry_dir = _REGISTRY_DIR

    index_path = registry_dir / "index.json"

    if not index_path.exists():
        raise FileNotFoundError(f"Registry index not found: {index_path}")

    try:
        with open(index_path) as f:
            registry = json.load(f)
    except json.JSONDecodeError as e:
        raise RegistryValidationError(f"Invalid JSON: {e}")

    validate_registry(registry)

    return registry


def save_registry(registry: dict, registry_dir: Optional[Path] = None) -> None:
    """Save the registry to index.json.

    Args:
        registry: The registry dict to save
        registry_dir: Optional path to registry directory (defaults to built-in)

    Raises:
        RegistryValidationError: If the registry is invalid
    """
    # Validate before saving
    validate_registry(registry)

    if registry_dir is None:
        registry_dir = _REGISTRY_DIR

    index_path = registry_dir / "index.json"

    # Ensure directory exists
    registry_dir.mkdir(parents=True, exist_ok=True)

    with open(index_path, "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
        f.write("\n")


def create_empty_registry() -> dict:
    """Create an empty registry structure.

    Returns:
        Empty registry dict
    """
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "blueprints": []
    }


# =============================================================================
# Blueprint Registration
# =============================================================================


def register_blueprint(
    blueprint_path: Path,
    registry_dir: Optional[Path] = None
) -> dict:
    """Register a blueprint in the registry.

    This function:
    1. Loads and validates the blueprint
    2. Computes its content hash
    3. Copies it to the registry blueprints directory
    4. Updates index.json with the new entry (sorted by blueprint_id)

    Args:
        blueprint_path: Path to the blueprint JSON file
        registry_dir: Optional path to registry directory (defaults to built-in)

    Returns:
        The registry entry that was added

    Raises:
        FileNotFoundError: If the blueprint file does not exist
        BlueprintValidationError: If the blueprint is invalid
        RegistryValidationError: If the resulting registry is invalid
    """
    if registry_dir is None:
        registry_dir = _REGISTRY_DIR

    blueprints_dir = registry_dir / "blueprints"
    blueprints_dir.mkdir(parents=True, exist_ok=True)

    # Load and validate blueprint
    blueprint = load_blueprint(blueprint_path)

    # Extract metadata
    blueprint_id = blueprint["blueprint_id"]
    domain = blueprint["domain"]
    version = blueprint["version"]

    # Compute content hash
    content_hash = compute_content_hash(blueprint)

    # Copy blueprint to registry (using canonical form)
    target_path = blueprints_dir / f"{blueprint_id}.json"
    canonical = canonicalize_blueprint(blueprint)
    with open(target_path, "w") as f:
        json.dump(canonical, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Create registry entry
    entry = {
        "blueprint_id": blueprint_id,
        "path": f"blueprints/{blueprint_id}.json",
        "content_hash_sha256": content_hash,
        "domain": domain,
        "version": version,
    }

    # Load or create registry
    try:
        registry = load_registry(registry_dir)
    except FileNotFoundError:
        registry = create_empty_registry()

    # Update or add entry
    blueprints = registry["blueprints"]
    existing_idx = None
    for i, bp in enumerate(blueprints):
        if bp["blueprint_id"] == blueprint_id:
            existing_idx = i
            break

    if existing_idx is not None:
        blueprints[existing_idx] = entry
    else:
        blueprints.append(entry)

    # Sort by blueprint_id for deterministic ordering
    blueprints.sort(key=lambda b: b["blueprint_id"])

    # Save registry
    save_registry(registry, registry_dir)

    return entry


def unregister_blueprint(
    blueprint_id: str,
    registry_dir: Optional[Path] = None
) -> bool:
    """Remove a blueprint from the registry.

    Args:
        blueprint_id: ID of the blueprint to remove
        registry_dir: Optional path to registry directory (defaults to built-in)

    Returns:
        True if removed, False if not found
    """
    if registry_dir is None:
        registry_dir = _REGISTRY_DIR

    try:
        registry = load_registry(registry_dir)
    except FileNotFoundError:
        return False

    blueprints = registry["blueprints"]
    original_len = len(blueprints)
    blueprints[:] = [b for b in blueprints if b["blueprint_id"] != blueprint_id]

    if len(blueprints) == original_len:
        return False

    # Remove blueprint file
    blueprint_path = registry_dir / "blueprints" / f"{blueprint_id}.json"
    if blueprint_path.exists():
        blueprint_path.unlink()

    save_registry(registry, registry_dir)
    return True


# =============================================================================
# Integrity Verification
# =============================================================================


def verify_registry(registry_dir: Optional[Path] = None) -> List[str]:
    """Verify integrity of all blueprints in the registry.

    This function:
    1. Loads the registry
    2. For each entry, loads the blueprint and recomputes its hash
    3. Compares against the stored hash

    Args:
        registry_dir: Optional path to registry directory (defaults to built-in)

    Returns:
        List of error messages (empty if all OK)

    Raises:
        RegistryIntegrityError: If any integrity check fails
    """
    if registry_dir is None:
        registry_dir = _REGISTRY_DIR

    errors: List[str] = []

    try:
        registry = load_registry(registry_dir)
    except FileNotFoundError as e:
        raise RegistryIntegrityError(str(e))
    except RegistryValidationError as e:
        raise RegistryIntegrityError(f"Registry schema invalid: {e.message}")

    for entry in registry["blueprints"]:
        blueprint_id = entry["blueprint_id"]
        stored_hash = entry["content_hash_sha256"]
        relative_path = entry["path"]

        blueprint_path = registry_dir / relative_path

        # Check file exists
        if not blueprint_path.exists():
            errors.append(f"INTEGRITY: {blueprint_id}: file not found: {relative_path}")
            continue

        # Load and validate blueprint
        try:
            blueprint = load_blueprint(blueprint_path)
        except BlueprintValidationError as e:
            errors.append(f"INTEGRITY: {blueprint_id}: invalid blueprint: {e.message}")
            continue
        except json.JSONDecodeError as e:
            errors.append(f"INTEGRITY: {blueprint_id}: invalid JSON: {e}")
            continue

        # Verify hash
        computed_hash = compute_content_hash(blueprint)
        if computed_hash != stored_hash:
            errors.append(
                f"INTEGRITY: {blueprint_id}: hash mismatch: "
                f"expected {stored_hash[:16]}..., got {computed_hash[:16]}..."
            )

        # Verify blueprint_id matches entry
        if blueprint["blueprint_id"] != blueprint_id:
            errors.append(
                f"INTEGRITY: {blueprint_id}: blueprint_id mismatch in file: "
                f"{blueprint['blueprint_id']}"
            )

    if errors:
        # Raise with first error, but include count
        raise RegistryIntegrityError(
            f"{len(errors)} integrity error(s): {errors[0].replace('INTEGRITY: ', '')}"
        )

    return []


def verify_blueprint(
    blueprint_id: str,
    registry_dir: Optional[Path] = None
) -> bool:
    """Verify integrity of a single blueprint.

    Args:
        blueprint_id: ID of the blueprint to verify
        registry_dir: Optional path to registry directory (defaults to built-in)

    Returns:
        True if integrity check passes

    Raises:
        RegistryIntegrityError: If integrity check fails
        KeyError: If blueprint_id not found in registry
    """
    if registry_dir is None:
        registry_dir = _REGISTRY_DIR

    registry = load_registry(registry_dir)

    entry = None
    for bp in registry["blueprints"]:
        if bp["blueprint_id"] == blueprint_id:
            entry = bp
            break

    if entry is None:
        raise KeyError(f"Blueprint not found in registry: {blueprint_id}")

    stored_hash = entry["content_hash_sha256"]
    relative_path = entry["path"]
    blueprint_path = registry_dir / relative_path

    if not blueprint_path.exists():
        raise RegistryIntegrityError(
            f"file not found: {relative_path}", blueprint_id
        )

    blueprint = load_blueprint(blueprint_path)
    computed_hash = compute_content_hash(blueprint)

    if computed_hash != stored_hash:
        raise RegistryIntegrityError(
            f"hash mismatch: expected {stored_hash[:16]}..., got {computed_hash[:16]}...",
            blueprint_id
        )

    return True


# =============================================================================
# Query Functions
# =============================================================================


def get_blueprint_entry(
    blueprint_id: str,
    registry_dir: Optional[Path] = None
) -> Optional[dict]:
    """Get registry entry for a blueprint.

    Args:
        blueprint_id: ID of the blueprint
        registry_dir: Optional path to registry directory (defaults to built-in)

    Returns:
        Registry entry dict or None if not found
    """
    if registry_dir is None:
        registry_dir = _REGISTRY_DIR

    try:
        registry = load_registry(registry_dir)
    except FileNotFoundError:
        return None

    for entry in registry["blueprints"]:
        if entry["blueprint_id"] == blueprint_id:
            return deepcopy(entry)

    return None


def list_blueprints(
    domain: Optional[str] = None,
    registry_dir: Optional[Path] = None
) -> List[dict]:
    """List all blueprints in the registry.

    Args:
        domain: Optional filter by domain
        registry_dir: Optional path to registry directory (defaults to built-in)

    Returns:
        List of registry entries
    """
    if registry_dir is None:
        registry_dir = _REGISTRY_DIR

    try:
        registry = load_registry(registry_dir)
    except FileNotFoundError:
        return []

    blueprints = registry["blueprints"]

    if domain:
        blueprints = [b for b in blueprints if b["domain"] == domain]

    return deepcopy(blueprints)


def get_blueprint_path(
    blueprint_id: str,
    registry_dir: Optional[Path] = None
) -> Optional[Path]:
    """Get the file path for a blueprint.

    Args:
        blueprint_id: ID of the blueprint
        registry_dir: Optional path to registry directory (defaults to built-in)

    Returns:
        Path to blueprint file or None if not found
    """
    if registry_dir is None:
        registry_dir = _REGISTRY_DIR

    entry = get_blueprint_entry(blueprint_id, registry_dir)
    if entry is None:
        return None

    return registry_dir / entry["path"]
