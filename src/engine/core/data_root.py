"""Data root and namespaced path resolution."""

import os
from pathlib import Path
from typing import Optional


DEFAULT_DATA_ROOT = "var"


def get_data_root() -> Path:
    """Get data root directory from ENV or default.

    Returns:
        Path to data root directory.
    """
    env_value = os.environ.get("ENGINE_DATA_ROOT")
    if env_value:
        return Path(env_value)
    return Path(DEFAULT_DATA_ROOT)


def get_institution_root(institution_id: str) -> Path:
    """Get institution-specific root directory.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to institution root: <data_root>/institutions/<institution_id>/
    """
    data_root = get_data_root()
    return data_root / "institutions" / institution_id


def resolve_namespaced_path(
    institution_id: str,
    env_value: Optional[str],
    default_rel: str,
) -> Path:
    """Resolve a path that may be namespaced by institution.

    Rules:
    - If env_value is None: use institution_root/default_rel
    - If env_value is absolute: use absolute Path(env_value)
    - If env_value is relative: use institution_root/env_value

    Args:
        institution_id: Institution UUID for namespacing.
        env_value: Optional environment variable value.
        default_rel: Default relative path if env_value is None.

    Returns:
        Resolved path.
    """
    institution_root = get_institution_root(institution_id)

    if env_value is None:
        return institution_root / default_rel

    env_path = Path(env_value)
    if env_path.is_absolute():
        return env_path

    # Relative path - under institution root
    return institution_root / env_value
