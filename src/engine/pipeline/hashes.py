"""Hash utilities for pipeline artifacts."""

import hashlib
import json
from typing import Any, Dict


def compute_hash(data: Any) -> str:
    """Compute SHA256 hash of data.

    Args:
        data: Data to hash. If dict/list, serializes to canonical JSON.

    Returns:
        SHA256 hex digest.
    """
    if isinstance(data, (dict, list)):
        # Canonical JSON serialization
        json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
        content = json_str.encode("utf-8")
    elif isinstance(data, str):
        content = data.encode("utf-8")
    elif isinstance(data, bytes):
        content = data
    else:
        content = str(data).encode("utf-8")

    return hashlib.sha256(content).hexdigest()


def compute_trace_hashes(
    sir: Dict[str, Any],
    draft: Dict[str, Any],
    idl_final: Dict[str, Any],
) -> Dict[str, str]:
    """Compute trace hashes for pipeline artifacts.

    Args:
        sir: SIR dictionary.
        draft: Draft IDL dictionary.
        idl_final: Final IDL dictionary.

    Returns:
        Dictionary with hash_sir, hash_draft, hash_idl_final.
    """
    return {
        "hash_sir": compute_hash(sir),
        "hash_draft": compute_hash(draft),
        "hash_idl_final": compute_hash(idl_final),
    }
