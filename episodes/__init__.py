"""Episodes module - Append-only episode store for execution governance.

This module provides:
- Episode Store: Append-only storage for execution episodes
- Episode Manifest: Validation and helpers for episode manifest v1
- Approval Gate: Gate that blocks release without valid approval
"""

from .episode_manifest_v1 import (
    EPISODE_MANIFEST_SCHEMA_VERSION,
    EpisodeManifestValidationError,
    validate_episode_manifest,
    canonicalize_episode_manifest,
    load_episode_manifest,
    create_episode_manifest,
    get_episode_status,
    is_episode_approved,
    is_episode_finalized,
    get_episode_root_hash,
    get_input_hash,
    get_contract_hashes,
    get_output_hashes,
)

from .episode_store import (
    # Constants
    EPISODES_DIR,
    MANIFEST_FILENAME,
    RUNLOG_FILENAME,
    APPROVAL_FILENAME,
    INPUT_DIR,
    CONTRACTS_DIR,
    ARTIFACTS_DIR,
    APPROVALS_DIR,
    # Classes
    EpisodeStore,
    # Exceptions
    EpisodeStoreError,
    EpisodeNotFoundError,
    EpisodeDuplicateError,
    EpisodeIntegrityError,
    EpisodeImmutableError,
    # Hash functions
    compute_file_hash,
    compute_content_hash,
    compute_json_hash,
    compute_episode_root_hash,
)

from .approval_gate import (
    ApprovalGate,
    ApprovalGateError,
    GateResult,
    GateCheckResult,
    check_release_approval,
)

__all__ = [
    # Constants
    "EPISODE_MANIFEST_SCHEMA_VERSION",
    "EPISODES_DIR",
    "MANIFEST_FILENAME",
    "RUNLOG_FILENAME",
    "APPROVAL_FILENAME",
    "INPUT_DIR",
    "CONTRACTS_DIR",
    "ARTIFACTS_DIR",
    "APPROVALS_DIR",
    # Manifest
    "EpisodeManifestValidationError",
    "validate_episode_manifest",
    "canonicalize_episode_manifest",
    "load_episode_manifest",
    "create_episode_manifest",
    "get_episode_status",
    "is_episode_approved",
    "is_episode_finalized",
    "get_episode_root_hash",
    "get_input_hash",
    "get_contract_hashes",
    "get_output_hashes",
    # Store
    "EpisodeStore",
    "EpisodeStoreError",
    "EpisodeNotFoundError",
    "EpisodeDuplicateError",
    "EpisodeIntegrityError",
    "EpisodeImmutableError",
    # Hash functions
    "compute_file_hash",
    "compute_content_hash",
    "compute_json_hash",
    "compute_episode_root_hash",
    # Approval Gate
    "ApprovalGate",
    "ApprovalGateError",
    "GateResult",
    "GateCheckResult",
    "check_release_approval",
]
