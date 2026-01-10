"""Episode Manifest v1 - Immutable episode records for execution governance.

This module provides validation and canonicalization for episode manifests.
Episodes are append-only records documenting: entrada → contratos → artefatos → (aprovação) → release

Key rules:
- schema_version is fixed at "episode_manifest.v1"
- episode_id = execution_id (deterministic)
- All content hashes use sha256 prefix format
- integrity.episode_root_hash_sha256 derived from all files in episode directory
- Append-only: once finalized, episodes cannot be modified

Schema Version: episode_manifest.v1
"""

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema


# =============================================================================
# Constants
# =============================================================================

EPISODE_MANIFEST_SCHEMA_VERSION = "episode_manifest.v1"

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "episode_manifest.v1.json"
_EPISODE_MANIFEST_SCHEMA: Optional[dict] = None


# =============================================================================
# Schema Loading
# =============================================================================


def _get_schema() -> dict:
    """Load and cache the episode manifest schema."""
    global _EPISODE_MANIFEST_SCHEMA
    if _EPISODE_MANIFEST_SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _EPISODE_MANIFEST_SCHEMA = json.load(f)
    return _EPISODE_MANIFEST_SCHEMA


# =============================================================================
# Exceptions
# =============================================================================


class EpisodeManifestValidationError(Exception):
    """Exception raised when episode manifest validation fails.

    Error messages are prefixed with "SCHEMA: " following project conventions.
    """

    def __init__(self, message: str, path: str = ""):
        self.message = message
        self.path = path
        super().__init__(f"SCHEMA: {path}: {message}" if path else f"SCHEMA: {message}")


# =============================================================================
# Validation
# =============================================================================


def validate_episode_manifest(manifest: dict) -> None:
    """Validate an episode manifest against the schema.

    Args:
        manifest: The episode manifest dict to validate

    Raises:
        EpisodeManifestValidationError: If validation fails (prefixed with "SCHEMA: ...")
    """
    schema = _get_schema()

    # JSON Schema validation
    try:
        jsonschema.validate(instance=manifest, schema=schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else ""
        raise EpisodeManifestValidationError(e.message, path)


# =============================================================================
# Canonicalization
# =============================================================================


def canonicalize_episode_manifest(manifest: dict) -> dict:
    """Canonicalize an episode manifest for deterministic comparison/hashing.

    Applies stable ordering to:
    - integrity.file_hashes: sorted by path

    Does NOT modify values, only ordering.

    Args:
        manifest: The episode manifest dict to canonicalize

    Returns:
        A new dict with canonical ordering (original is not mutated)
    """
    result = deepcopy(manifest)

    # Sort file_hashes by path
    if "integrity" in result and result["integrity"]:
        file_hashes = result["integrity"].get("file_hashes")
        if file_hashes:
            result["integrity"]["file_hashes"] = sorted(
                file_hashes,
                key=lambda x: x.get("path", "")
            )

    return result


# =============================================================================
# Loading
# =============================================================================


def load_episode_manifest(path: Path) -> dict:
    """Load and validate an episode manifest from a JSON file.

    Args:
        path: Path to the episode manifest JSON file

    Returns:
        Validated episode manifest dict

    Raises:
        FileNotFoundError: If the file does not exist
        EpisodeManifestValidationError: If the manifest is invalid
    """
    if not path.exists():
        raise FileNotFoundError(f"Episode manifest not found: {path}")

    try:
        with open(path) as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        raise EpisodeManifestValidationError(f"Invalid JSON: {e}")

    validate_episode_manifest(manifest)

    return manifest


# =============================================================================
# Helper Functions
# =============================================================================


def get_episode_status(manifest: dict) -> str:
    """Get the status from an episode manifest.

    Args:
        manifest: Validated episode manifest dict

    Returns:
        Status string ("pending", "approved", "rejected", "released")
    """
    return manifest.get("status", "pending")


def is_episode_approved(manifest: dict) -> bool:
    """Check if an episode has status "approved".

    Args:
        manifest: Validated episode manifest dict

    Returns:
        True if status is "approved"
    """
    return manifest.get("status") == "approved"


def is_episode_finalized(manifest: dict) -> bool:
    """Check if an episode is finalized (has valid root hash).

    Args:
        manifest: Episode manifest dict

    Returns:
        True if episode has a non-placeholder root hash
    """
    root_hash = manifest.get("integrity", {}).get("episode_root_hash_sha256")
    if not root_hash:
        return False
    # Placeholder hash is all zeros
    return root_hash != "sha256:" + "0" * 64


def get_episode_root_hash(manifest: dict) -> Optional[str]:
    """Get the root hash from an episode manifest.

    Args:
        manifest: Episode manifest dict

    Returns:
        Root hash string or None
    """
    return manifest.get("integrity", {}).get("episode_root_hash_sha256")


def get_input_hash(manifest: dict) -> Optional[str]:
    """Get the input hash from an episode manifest.

    Args:
        manifest: Episode manifest dict

    Returns:
        Input hash string or None
    """
    return manifest.get("inputs", {}).get("input_hash_sha256")


def get_contract_hashes(manifest: dict) -> Dict[str, Optional[str]]:
    """Get all contract hashes from an episode manifest.

    Args:
        manifest: Episode manifest dict

    Returns:
        Dict of contract type to hash
    """
    contracts = manifest.get("contracts", {})
    return {
        "idl": contracts.get("idl_hash_sha256"),
        "srs": contracts.get("srs_hash_sha256"),
        "ir": contracts.get("ir_hash_sha256"),
        "openapi": contracts.get("openapi_hash_sha256"),
        "plan": contracts.get("plan_hash_sha256"),
    }


def get_output_hashes(manifest: dict) -> Dict[str, Optional[str]]:
    """Get all output hashes from an episode manifest.

    Args:
        manifest: Episode manifest dict

    Returns:
        Dict of output type to hash
    """
    outputs = manifest.get("outputs", {})
    return {
        "repo": outputs.get("repo_hash_sha256"),
        "release_artifact": outputs.get("release_artifact_hash_sha256"),
    }


def create_episode_manifest(
    episode_id: str,
    execution_id: str,
    input_mode: str,
    input_hash: str,
    created_by: Optional[str] = None,
    contracts: Optional[Dict[str, Optional[str]]] = None,
    outputs: Optional[Dict[str, Optional[str]]] = None,
    previous_episode_id: Optional[str] = None,
    change_request_id: Optional[str] = None,
    cr_hash_sha256: Optional[str] = None,
    integrity_hash: Optional[str] = None,
    file_hashes: Optional[List[dict]] = None,
) -> dict:
    """Create a new episode manifest dict.

    Args:
        episode_id: Episode identifier (should match execution_id)
        execution_id: Execution ID from runlog
        input_mode: Input mode (natural, draft, idl)
        input_hash: SHA256 hash of input
        created_by: Optional creator identifier
        contracts: Optional dict of contract hashes
        outputs: Optional dict of output hashes
        previous_episode_id: Optional link to previous episode
        change_request_id: Optional external change request ID
        cr_hash_sha256: Optional SHA256 hash of the change request
        integrity_hash: Optional root hash (placeholder if not finalized)
        file_hashes: Optional list of file hashes

    Returns:
        Episode manifest dict (NOT validated - may need finalization)
    """
    contracts = contracts or {}
    outputs = outputs or {}

    manifest = {
        "schema_version": EPISODE_MANIFEST_SCHEMA_VERSION,
        "episode_id": episode_id,
        "execution_id": execution_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "created_by": created_by,
        "inputs": {
            "input_mode": input_mode,
            "input_hash_sha256": input_hash,
        },
        "contracts": {
            "idl_hash_sha256": contracts.get("idl"),
            "srs_hash_sha256": contracts.get("srs"),
            "ir_hash_sha256": contracts.get("ir"),
            "openapi_hash_sha256": contracts.get("openapi"),
            "plan_hash_sha256": contracts.get("plan"),
        },
        "outputs": {
            "repo_hash_sha256": outputs.get("repo"),
            "release_artifact_hash_sha256": outputs.get("release_artifact"),
        },
        "links": {
            "previous_episode_id": previous_episode_id,
            "change_request_id": change_request_id,
            "cr_hash_sha256": cr_hash_sha256,
        },
        "integrity": {
            "episode_root_hash_sha256": integrity_hash or "sha256:" + "0" * 64,
            "algorithm": "sha256",
            "file_hashes": file_hashes,
        },
        "status": "pending",
        "approval_status": None,
    }

    return manifest
