"""Canonical JSON serialization for deterministic output."""

import json
from typing import Any, Dict


def canonical_json(obj: Any) -> str:
    """Serialize object to canonical JSON with sorted keys.

    Args:
        obj: Object to serialize (dict, list, dataclass with to_dict, or primitive)

    Returns:
        Canonical JSON string with sorted keys and no extra whitespace.
    """
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_dict(obj: Any) -> Dict[str, Any]:
    """Convert object to canonical dict with sorted keys.

    Args:
        obj: Object to convert.

    Returns:
        Dict with sorted keys at all levels.
    """
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()

    if isinstance(obj, dict):
        return {k: canonical_dict(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [canonical_dict(item) for item in obj]
    else:
        return obj


def normalize_roles(roles: list) -> list:
    """Normalize roles to lowercase and sorted.

    Args:
        roles: List of role strings.

    Returns:
        Sorted list of lowercase role strings.
    """
    return sorted([r.lower() for r in roles])


def normalize_key(text: str) -> str:
    """Normalize text to a valid key (lowercase, underscores).

    Args:
        text: Text to normalize.

    Returns:
        Normalized key string.
    """
    # Replace spaces and special chars with underscores
    key = text.lower().strip()
    key = "".join(c if c.isalnum() else "_" for c in key)
    # Remove consecutive underscores
    while "__" in key:
        key = key.replace("__", "_")
    # Remove leading/trailing underscores
    key = key.strip("_")
    return key or "unknown"
