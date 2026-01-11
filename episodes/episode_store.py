"""Episode Store - Append-only storage for execution episodes.

This module provides an append-only store for episode execution records.
Each episode is an immutable directory containing:
  .engine/episodes/<episode_id>/
    manifest.json          # Episode manifest with all hashes
    input/                 # Input files
    contracts/             # Generated contracts (IDL, SRS, IR, OpenAPI, Plan)
    artifacts/             # Generated artifacts
    runlog.json           # Execution runlog
    approvals/            # Approval files
      approval.json       # When approved

Key rules:
- Append-only: once created, episodes cannot be modified
- episode_root_hash_sha256 derived from sorted list of files + hashes
- Any modification to episode directory is detectable via integrity check
- episode_id = execution_id (deterministic)

Storage structure:
    .engine/episodes/
        <episode_id>/
            manifest.json
            input/
            contracts/
            artifacts/
            runlog.json
            approvals/
                approval.json (when exists)
"""

import hashlib
import json
import os
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jsonschema

from .episode_manifest_v1 import (
    EPISODE_MANIFEST_SCHEMA_VERSION,
    EpisodeManifestValidationError,
    validate_episode_manifest,
    canonicalize_episode_manifest,
)


# =============================================================================
# Constants
# =============================================================================

EPISODES_DIR = ".engine/episodes"
MANIFEST_FILENAME = "manifest.json"
RUNLOG_FILENAME = "runlog.json"
APPROVAL_FILENAME = "approval.json"
CHANGE_REQUEST_FILENAME = "change_request.json"

INPUT_DIR = "input"
CONTRACTS_DIR = "contracts"
ARTIFACTS_DIR = "artifacts"
APPROVALS_DIR = "approvals"
CHANGE_REQUEST_DIR = "change_request"


# =============================================================================
# Exceptions
# =============================================================================


class EpisodeStoreError(Exception):
    """Base exception for episode store errors.

    Error messages are prefixed with "GOVERNANCE: " following project conventions.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(f"GOVERNANCE: {message}")


class EpisodeNotFoundError(EpisodeStoreError):
    """Exception raised when an episode is not found."""

    def __init__(self, episode_id: str):
        super().__init__(f"Episode not found: {episode_id}")
        self.episode_id = episode_id


class EpisodeDuplicateError(EpisodeStoreError):
    """Exception raised when trying to create a duplicate episode."""

    def __init__(self, episode_id: str):
        super().__init__(f"Episode already exists: {episode_id}")
        self.episode_id = episode_id


class EpisodeIntegrityError(EpisodeStoreError):
    """Exception raised when episode integrity check fails."""

    def __init__(self, episode_id: str, message: str):
        super().__init__(f"Integrity error for episode {episode_id}: {message}")
        self.episode_id = episode_id


class EpisodeImmutableError(EpisodeStoreError):
    """Exception raised when trying to modify a finalized episode."""

    def __init__(self, episode_id: str):
        super().__init__(f"Episode is immutable: {episode_id}")
        self.episode_id = episode_id


# =============================================================================
# Hash Computation
# =============================================================================


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        path: Path to file

    Returns:
        Hash string in format "sha256:<hex>"

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    with open(path, "rb") as f:
        hash_hex = hashlib.sha256(f.read()).hexdigest()
    return f"sha256:{hash_hex}"


def compute_content_hash(content: bytes) -> str:
    """Compute SHA256 hash of content.

    Args:
        content: Content as bytes

    Returns:
        Hash string in format "sha256:<hex>"
    """
    hash_hex = hashlib.sha256(content).hexdigest()
    return f"sha256:{hash_hex}"


def compute_json_hash(data: dict) -> str:
    """Compute SHA256 hash of JSON data (canonicalized).

    Args:
        data: Dict to hash

    Returns:
        Hash string in format "sha256:<hex>"
    """
    content = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return compute_content_hash(content.encode())


def compute_episode_root_hash(episode_dir: Path) -> Tuple[str, List[dict]]:
    """Compute the root hash of an episode directory.

    Walks all files in the episode directory (excluding manifest.json),
    sorts them by path, computes individual hashes, then combines into
    a root hash.

    Args:
        episode_dir: Path to episode directory

    Returns:
        Tuple of (root_hash, file_hashes_list)
    """
    file_hashes = []

    for root, dirs, files in os.walk(episode_dir):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in sorted(files):
            # Skip manifest.json - it contains the hash, can't hash itself
            if filename == MANIFEST_FILENAME:
                continue

            filepath = Path(root) / filename
            rel_path = filepath.relative_to(episode_dir)

            file_hash = compute_file_hash(filepath)
            file_hashes.append({
                "path": str(rel_path),
                "hash": file_hash,
            })

    # Sort by path for deterministic ordering
    file_hashes.sort(key=lambda x: x["path"])

    # Compute root hash from concatenated hashes
    combined = "".join(f"{fh['path']}:{fh['hash']}" for fh in file_hashes)
    root_hash = compute_content_hash(combined.encode())

    return root_hash, file_hashes


# =============================================================================
# Episode Store
# =============================================================================


class EpisodeStore:
    """Append-only store for execution episodes.

    Manages the lifecycle of episodes:
    - Create episode directory structure
    - Register artifacts with integrity hashes
    - Finalize episode (compute root hash, make immutable)
    - Verify episode integrity
    - Add approvals
    """

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize the episode store.

        Args:
            base_path: Base path for .engine directory (default: current dir)
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.episodes_dir = self.base_path / EPISODES_DIR

    # -------------------------------------------------------------------------
    # Path Helpers
    # -------------------------------------------------------------------------

    def _get_episode_dir(self, episode_id: str) -> Path:
        """Get the directory path for an episode."""
        return self.episodes_dir / episode_id

    def _get_manifest_path(self, episode_id: str) -> Path:
        """Get the path to an episode's manifest."""
        return self._get_episode_dir(episode_id) / MANIFEST_FILENAME

    def _get_runlog_path(self, episode_id: str) -> Path:
        """Get the path to an episode's runlog."""
        return self._get_episode_dir(episode_id) / RUNLOG_FILENAME

    def _get_approval_path(self, episode_id: str) -> Path:
        """Get the path to an episode's approval file."""
        return self._get_episode_dir(episode_id) / APPROVALS_DIR / APPROVAL_FILENAME

    def _get_input_dir(self, episode_id: str) -> Path:
        """Get the input directory for an episode."""
        return self._get_episode_dir(episode_id) / INPUT_DIR

    def _get_contracts_dir(self, episode_id: str) -> Path:
        """Get the contracts directory for an episode."""
        return self._get_episode_dir(episode_id) / CONTRACTS_DIR

    def _get_artifacts_dir(self, episode_id: str) -> Path:
        """Get the artifacts directory for an episode."""
        return self._get_episode_dir(episode_id) / ARTIFACTS_DIR

    def _get_approvals_dir(self, episode_id: str) -> Path:
        """Get the approvals directory for an episode."""
        return self._get_episode_dir(episode_id) / APPROVALS_DIR

    def _get_change_request_dir(self, episode_id: str) -> Path:
        """Get the change_request directory for an episode."""
        return self._get_episode_dir(episode_id) / CHANGE_REQUEST_DIR

    def _get_change_request_path(self, episode_id: str) -> Path:
        """Get the path to an episode's change request file."""
        return self._get_change_request_dir(episode_id) / CHANGE_REQUEST_FILENAME

    # -------------------------------------------------------------------------
    # Episode Operations
    # -------------------------------------------------------------------------

    def exists(self, episode_id: str) -> bool:
        """Check if an episode exists.

        Args:
            episode_id: Episode identifier

        Returns:
            True if episode directory exists
        """
        return self._get_episode_dir(episode_id).exists()

    def is_finalized(self, episode_id: str) -> bool:
        """Check if an episode is finalized (has manifest with real root hash).

        Args:
            episode_id: Episode identifier

        Returns:
            True if episode is finalized (has non-placeholder root hash)
        """
        manifest_path = self._get_manifest_path(episode_id)
        if not manifest_path.exists():
            return False

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            root_hash = manifest.get("integrity", {}).get("episode_root_hash_sha256")
            # Placeholder hash means not finalized
            placeholder = "sha256:" + "0" * 64
            return root_hash is not None and root_hash != placeholder
        except (json.JSONDecodeError, KeyError):
            return False

    def create_episode(
        self,
        episode_id: str,
        execution_id: str,
        input_mode: str,
        input_hash: str,
        created_by: Optional[str] = None,
        previous_episode_id: Optional[str] = None,
        change_request_id: Optional[str] = None,
        cr_hash_sha256: Optional[str] = None,
    ) -> Path:
        """Create a new episode directory structure.

        Args:
            episode_id: Episode identifier (should match execution_id)
            execution_id: Execution ID from runlog
            input_mode: Input mode (natural, draft, idl)
            input_hash: SHA256 hash of input
            created_by: Optional creator identifier
            previous_episode_id: Optional link to previous episode
            change_request_id: Optional external change request ID
            cr_hash_sha256: Optional SHA256 hash of the change request

        Returns:
            Path to episode directory

        Raises:
            EpisodeDuplicateError: If episode already exists
        """
        if self.exists(episode_id):
            raise EpisodeDuplicateError(episode_id)

        episode_dir = self._get_episode_dir(episode_id)

        # Create directory structure
        episode_dir.mkdir(parents=True, exist_ok=True)
        self._get_input_dir(episode_id).mkdir(exist_ok=True)
        self._get_contracts_dir(episode_id).mkdir(exist_ok=True)
        self._get_artifacts_dir(episode_id).mkdir(exist_ok=True)
        self._get_approvals_dir(episode_id).mkdir(exist_ok=True)

        # Create change_request directory if this is a change execution
        if change_request_id is not None:
            self._get_change_request_dir(episode_id).mkdir(exist_ok=True)

        # Create initial manifest (without integrity - not finalized yet)
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
                "idl_hash_sha256": None,
                "srs_hash_sha256": None,
                "ir_hash_sha256": None,
                "openapi_hash_sha256": None,
                "plan_hash_sha256": None,
            },
            "outputs": {
                "repo_hash_sha256": None,
                "release_artifact_hash_sha256": None,
            },
            "links": {
                "previous_episode_id": previous_episode_id,
                "change_request_id": change_request_id,
                "cr_hash_sha256": cr_hash_sha256,
            },
            "integrity": {
                "episode_root_hash_sha256": "sha256:" + "0" * 64,  # Placeholder
                "algorithm": "sha256",
                "file_hashes": None,
            },
            "status": "pending",
            "approval_status": None,
        }

        # Save manifest
        manifest_path = self._get_manifest_path(episode_id)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        return episode_dir

    def register_contract(
        self,
        episode_id: str,
        contract_type: str,
        content: bytes,
        filename: Optional[str] = None,
    ) -> str:
        """Register a contract file in the episode.

        Args:
            episode_id: Episode identifier
            contract_type: Type of contract (idl, srs, ir, openapi, plan)
            content: Contract content as bytes
            filename: Optional filename (default: {contract_type}.json)

        Returns:
            SHA256 hash of the contract

        Raises:
            EpisodeNotFoundError: If episode not found
            EpisodeImmutableError: If episode is finalized
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        if self.is_finalized(episode_id):
            raise EpisodeImmutableError(episode_id)

        # Compute hash
        content_hash = compute_content_hash(content)

        # Save contract file
        contracts_dir = self._get_contracts_dir(episode_id)
        fname = filename or f"{contract_type}.json"
        contract_path = contracts_dir / fname
        with open(contract_path, "wb") as f:
            f.write(content)

        # Update manifest
        manifest = self.get_manifest(episode_id)
        hash_key = f"{contract_type}_hash_sha256"
        if hash_key in manifest.get("contracts", {}):
            manifest["contracts"][hash_key] = content_hash

        self._save_manifest(episode_id, manifest)

        return content_hash

    def register_artifact(
        self,
        episode_id: str,
        artifact_type: str,
        content: bytes,
        filename: str,
    ) -> str:
        """Register an artifact file in the episode.

        Args:
            episode_id: Episode identifier
            artifact_type: Type of artifact (repo, release)
            content: Artifact content as bytes
            filename: Filename

        Returns:
            SHA256 hash of the artifact

        Raises:
            EpisodeNotFoundError: If episode not found
            EpisodeImmutableError: If episode is finalized
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        if self.is_finalized(episode_id):
            raise EpisodeImmutableError(episode_id)

        # Compute hash
        content_hash = compute_content_hash(content)

        # Save artifact file
        artifacts_dir = self._get_artifacts_dir(episode_id)
        artifact_path = artifacts_dir / filename
        with open(artifact_path, "wb") as f:
            f.write(content)

        # Update manifest outputs
        manifest = self.get_manifest(episode_id)
        hash_key = f"{artifact_type}_hash_sha256"
        if hash_key in manifest.get("outputs", {}):
            manifest["outputs"][hash_key] = content_hash

        self._save_manifest(episode_id, manifest)

        return content_hash

    def register_input(
        self,
        episode_id: str,
        content: bytes,
        filename: str,
    ) -> str:
        """Register an input file in the episode.

        Args:
            episode_id: Episode identifier
            content: Input content as bytes
            filename: Filename

        Returns:
            SHA256 hash of the input

        Raises:
            EpisodeNotFoundError: If episode not found
            EpisodeImmutableError: If episode is finalized
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        if self.is_finalized(episode_id):
            raise EpisodeImmutableError(episode_id)

        # Compute hash
        content_hash = compute_content_hash(content)

        # Save input file
        input_dir = self._get_input_dir(episode_id)
        input_path = input_dir / filename
        with open(input_path, "wb") as f:
            f.write(content)

        return content_hash

    def register_runlog(
        self,
        episode_id: str,
        runlog: dict,
    ) -> str:
        """Register the runlog for an episode.

        Args:
            episode_id: Episode identifier
            runlog: Runlog dict

        Returns:
            SHA256 hash of the runlog

        Raises:
            EpisodeNotFoundError: If episode not found
            EpisodeImmutableError: If episode is finalized
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        if self.is_finalized(episode_id):
            raise EpisodeImmutableError(episode_id)

        # Save runlog
        runlog_path = self._get_runlog_path(episode_id)
        content = json.dumps(runlog, indent=2, sort_keys=True)
        with open(runlog_path, "w") as f:
            f.write(content)

        return compute_content_hash(content.encode())

    def register_change_request(
        self,
        episode_id: str,
        change_request: dict,
    ) -> str:
        """Register a change request for an episode.

        Stores the change request in the episode's change_request directory.

        Args:
            episode_id: Episode identifier
            change_request: Change request dict

        Returns:
            SHA256 hash of the change request (canonical)

        Raises:
            EpisodeNotFoundError: If episode not found
            EpisodeImmutableError: If episode is finalized
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        if self.is_finalized(episode_id):
            raise EpisodeImmutableError(episode_id)

        # Create change_request directory if not exists
        cr_dir = self._get_change_request_dir(episode_id)
        cr_dir.mkdir(exist_ok=True)

        # Save change request (formatted for readability)
        cr_path = self._get_change_request_path(episode_id)
        content = json.dumps(change_request, indent=2, sort_keys=True)
        with open(cr_path, "w") as f:
            f.write(content)

        return compute_content_hash(content.encode())

    def get_change_request(self, episode_id: str) -> Optional[dict]:
        """Get the change request for an episode if it exists.

        Args:
            episode_id: Episode identifier

        Returns:
            Change request dict or None

        Raises:
            EpisodeNotFoundError: If episode not found
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        cr_path = self._get_change_request_path(episode_id)
        if not cr_path.exists():
            return None

        with open(cr_path) as f:
            return json.load(f)

    def finalize_episode(self, episode_id: str) -> dict:
        """Finalize an episode - compute root hash and make immutable.

        Args:
            episode_id: Episode identifier

        Returns:
            Final manifest

        Raises:
            EpisodeNotFoundError: If episode not found
            EpisodeImmutableError: If already finalized
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        if self.is_finalized(episode_id):
            raise EpisodeImmutableError(episode_id)

        episode_dir = self._get_episode_dir(episode_id)

        # Compute root hash from all files
        root_hash, file_hashes = compute_episode_root_hash(episode_dir)

        # Update manifest with integrity info
        manifest = self.get_manifest(episode_id)
        manifest["integrity"]["episode_root_hash_sha256"] = root_hash
        manifest["integrity"]["file_hashes"] = file_hashes

        # Check for approval
        approval_path = self._get_approval_path(episode_id)
        if approval_path.exists():
            try:
                with open(approval_path) as f:
                    approval = json.load(f)
                manifest["approval_status"] = {
                    "has_approval": True,
                    "decision": approval.get("decision"),
                    "approver_name": approval.get("approver", {}).get("display_name"),
                }
                if approval.get("decision") == "approve":
                    manifest["status"] = "approved"
                elif approval.get("decision") == "reject":
                    manifest["status"] = "rejected"
            except (json.JSONDecodeError, KeyError):
                manifest["approval_status"] = {
                    "has_approval": True,
                    "decision": None,
                    "approver_name": None,
                }
        else:
            manifest["approval_status"] = {
                "has_approval": False,
                "decision": None,
                "approver_name": None,
            }

        # Save final manifest
        self._save_manifest(episode_id, manifest)

        return manifest

    def get_manifest(self, episode_id: str) -> dict:
        """Get the manifest for an episode.

        Args:
            episode_id: Episode identifier

        Returns:
            Manifest dict

        Raises:
            EpisodeNotFoundError: If episode not found
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        manifest_path = self._get_manifest_path(episode_id)
        with open(manifest_path) as f:
            return json.load(f)

    def _save_manifest(self, episode_id: str, manifest: dict) -> None:
        """Save manifest to disk."""
        manifest_path = self._get_manifest_path(episode_id)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

    def list_episodes(
        self,
        status: Optional[str] = None,
    ) -> List[dict]:
        """List all episodes with optional filtering.

        Args:
            status: Filter by status (pending, approved, rejected, released)

        Returns:
            List of episode summary dicts
        """
        episodes = []

        if not self.episodes_dir.exists():
            return episodes

        for episode_dir in sorted(self.episodes_dir.iterdir()):
            if not episode_dir.is_dir():
                continue

            manifest_path = episode_dir / MANIFEST_FILENAME
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)

                ep_status = manifest.get("status", "pending")
                if status and ep_status != status:
                    continue

                approval_status = manifest.get("approval_status") or {}
                episodes.append({
                    "episode_id": manifest.get("episode_id"),
                    "execution_id": manifest.get("execution_id"),
                    "status": ep_status,
                    "created_at": manifest.get("created_at"),
                    "input_mode": manifest.get("inputs", {}).get("input_mode"),
                    "has_approval": approval_status.get("has_approval", False),
                })
            except (json.JSONDecodeError, KeyError):
                continue

        return episodes

    # -------------------------------------------------------------------------
    # Approval Operations
    # -------------------------------------------------------------------------

    def add_approval(
        self,
        episode_id: str,
        approval: dict,
    ) -> dict:
        """Add an approval to an episode.

        Note: This is allowed even after finalization - approvals are the
        one exception to immutability. After adding approval, the manifest
        is updated but episode_root_hash is NOT recomputed (approval is
        separate from the content hash).

        Args:
            episode_id: Episode identifier
            approval: Approval dict (validated)

        Returns:
            Updated manifest

        Raises:
            EpisodeNotFoundError: If episode not found
            EpisodeStoreError: If approval episode_id doesn't match
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        # Verify approval is for this episode
        if approval.get("episode_id") != episode_id:
            raise EpisodeStoreError(
                f"Approval episode_id mismatch: expected {episode_id}, "
                f"got {approval.get('episode_id')}"
            )

        # Save approval file
        approvals_dir = self._get_approvals_dir(episode_id)
        approvals_dir.mkdir(exist_ok=True)
        approval_path = self._get_approval_path(episode_id)

        with open(approval_path, "w") as f:
            json.dump(approval, f, indent=2, sort_keys=True)

        # Update manifest approval_status
        manifest = self.get_manifest(episode_id)
        manifest["approval_status"] = {
            "has_approval": True,
            "decision": approval.get("decision"),
            "approver_name": approval.get("approver", {}).get("display_name"),
        }

        if approval.get("decision") == "approve":
            manifest["status"] = "approved"
        elif approval.get("decision") == "reject":
            manifest["status"] = "rejected"

        self._save_manifest(episode_id, manifest)

        return manifest

    def get_approval(self, episode_id: str) -> Optional[dict]:
        """Get the approval for an episode if it exists.

        Args:
            episode_id: Episode identifier

        Returns:
            Approval dict or None
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        approval_path = self._get_approval_path(episode_id)
        if not approval_path.exists():
            return None

        with open(approval_path) as f:
            return json.load(f)

    def has_valid_approval(self, episode_id: str) -> Tuple[bool, Optional[str]]:
        """Check if episode has a valid approval with decision 'approve'.

        Args:
            episode_id: Episode identifier

        Returns:
            Tuple of (is_valid, error_message)
        """
        approval = self.get_approval(episode_id)

        if approval is None:
            return False, "APPROVAL_REQUIRED"

        # Verify episode_id matches
        if approval.get("episode_id") != episode_id:
            return False, "APPROVAL_INVALID"

        # Verify decision is approve
        if approval.get("decision") != "approve":
            return False, "APPROVAL_INVALID"

        return True, None

    # -------------------------------------------------------------------------
    # Integrity Verification
    # -------------------------------------------------------------------------

    def verify_integrity(self, episode_id: str) -> Tuple[bool, Optional[str]]:
        """Verify the integrity of an episode.

        Recomputes the root hash and compares with stored hash.

        Note: If an approval was added after finalization, the hash will differ.
        This is EXPECTED behavior - approvals are append-only additions.
        The function will return a specific message distinguishing this case
        from unauthorized modifications.

        Args:
            episode_id: Episode identifier

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if integrity verified
            - (True, "approval_added") if only difference is approval file
            - (False, error_message) if integrity compromised

        Raises:
            EpisodeNotFoundError: If episode not found
        """
        if not self.exists(episode_id):
            raise EpisodeNotFoundError(episode_id)

        manifest = self.get_manifest(episode_id)
        stored_hash = manifest.get("integrity", {}).get("episode_root_hash_sha256")

        if not stored_hash or stored_hash == "sha256:" + "0" * 64:
            return False, "Episode not finalized"

        episode_dir = self._get_episode_dir(episode_id)
        current_hash, current_files = compute_episode_root_hash(episode_dir)

        if current_hash != stored_hash:
            # Check if the only difference is the approval file
            stored_files = manifest.get("integrity", {}).get("file_hashes", [])
            stored_paths = {f["path"] for f in stored_files} if stored_files else set()
            # current_files is a list of dicts with "path" and "hash" keys
            current_paths = {f["path"] for f in current_files}

            # Find new files
            new_paths = current_paths - stored_paths

            # Check if only approval-related files were added
            approval_paths = {"approvals/approval.json"}
            if new_paths and new_paths.issubset(approval_paths):
                # Verify that existing files haven't changed
                existing_ok = True
                for stored_file in stored_files or []:
                    stored_path = stored_file["path"]
                    stored_file_hash = stored_file["hash"]
                    for current_file in current_files:
                        if current_file["path"] == stored_path:
                            if current_file["hash"] != stored_file_hash:
                                existing_ok = False
                                break
                    if not existing_ok:
                        break

                if existing_ok:
                    return True, "approval_added"

            return False, f"Hash mismatch: expected {stored_hash}, got {current_hash}"

        return True, None

    def verify_all(self) -> Dict[str, Tuple[bool, Optional[str]]]:
        """Verify integrity of all episodes.

        Returns:
            Dict mapping episode_id to (is_valid, error_message)
        """
        results = {}

        if not self.episodes_dir.exists():
            return results

        for episode_dir in self.episodes_dir.iterdir():
            if not episode_dir.is_dir():
                continue

            episode_id = episode_dir.name
            try:
                results[episode_id] = self.verify_integrity(episode_id)
            except EpisodeNotFoundError:
                results[episode_id] = (False, "Episode directory corrupted")

        return results
