"""PatchManifest - Write-once record of all patches applied.

Each patch application generates a PatchManifest that:
- Lists all files touched
- Records rewrite_ratio per file
- Records sha256_after per file
- Tracks policy violations if any
- Has a contract gate for integrity verification

Schema version: patch_manifest.v1
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from observability.canonical_hash import compute_content_hash_sha256, compute_text_hash_sha256


# Schema version
PATCH_MANIFEST_SCHEMA_VERSION = "patch_manifest.v1"

# Hashable fields (for contract gate)
HASHABLE_FIELDS = [
    "schema_version",
    "execution_id",
    "project",
    "patches",
    "policy",
    "result",
]

# Volatile fields (not in hash)
VOLATILE_FIELDS = [
    "content_hash_sha256",
    "timestamp",
    "contract_notes",
    "attempt",
]


@dataclass
class PatchEntry:
    """A single patch entry in the manifest."""

    path: str
    op: str  # "create", "modify", "delete", "append"
    rewrite_ratio: float = 0.0
    lines_added: int = 0
    lines_removed: int = 0
    sha256_after: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "op": self.op,
            "rewrite_ratio": self.rewrite_ratio,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "sha256_after": self.sha256_after,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatchEntry":
        return cls(
            path=data.get("path", ""),
            op=data.get("op", ""),
            rewrite_ratio=data.get("rewrite_ratio", 0.0),
            lines_added=data.get("lines_added", 0),
            lines_removed=data.get("lines_removed", 0),
            sha256_after=data.get("sha256_after", ""),
        )


@dataclass
class PatchPolicy:
    """Policy settings for patch application."""

    max_rewrite_ratio: float = 0.80
    blocked_paths: List[str] = field(default_factory=lambda: [
        "/home/bazari/engine",
        "/home/bazari/templates",
    ])
    allowlist_roots: List[str] = field(default_factory=lambda: [
        "/home/bazari/generated",
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_rewrite_ratio": self.max_rewrite_ratio,
            "blocked_paths": sorted(self.blocked_paths),
            "allowlist_roots": sorted(self.allowlist_roots),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatchPolicy":
        return cls(
            max_rewrite_ratio=data.get("max_rewrite_ratio", 0.80),
            blocked_paths=data.get("blocked_paths", []),
            allowlist_roots=data.get("allowlist_roots", []),
        )


@dataclass
class PatchManifest:
    """Manifest of all patches applied in a single operation.

    Contract Gate:
    - hashable_payload includes: schema_version, execution_id, project, patches, policy, result
    - content_hash_sha256 is computed from canonical JSON of hashable_payload
    - On load, hash is recomputed and compared
    """

    execution_id: str
    project: str
    patches: List[PatchEntry] = field(default_factory=list)
    policy: PatchPolicy = field(default_factory=PatchPolicy)
    result: str = "applied"  # "applied", "blocked", "rolled_back"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    attempt: int = 0  # For fix loop: 0 = initial, 1+ = fix attempts
    contract_notes: Optional[str] = None

    def to_hashable_dict(self) -> Dict[str, Any]:
        """Generate payload for hash computation (without volatile fields)."""
        return {
            "schema_version": PATCH_MANIFEST_SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "project": self.project,
            "patches": [p.to_dict() for p in sorted(self.patches, key=lambda x: x.path)],
            "policy": self.policy.to_dict(),
            "result": self.result,
        }

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Generate full canonical dict with schema_version and content_hash."""
        hashable = self.to_hashable_dict()
        content_hash = compute_content_hash_sha256(hashable)

        result = {
            "schema_version": PATCH_MANIFEST_SCHEMA_VERSION,
            "content_hash_sha256": content_hash,
            "execution_id": self.execution_id,
            "project": self.project,
            "patches": [p.to_dict() for p in sorted(self.patches, key=lambda x: x.path)],
            "policy": self.policy.to_dict(),
            "result": self.result,
            "timestamp": self.timestamp,
            "attempt": self.attempt,
        }

        if self.contract_notes is not None:
            result["contract_notes"] = self.contract_notes

        return result

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_canonical_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatchManifest":
        """Create from dictionary."""
        patches = [PatchEntry.from_dict(p) for p in data.get("patches", [])]
        policy = PatchPolicy.from_dict(data.get("policy", {}))

        return cls(
            execution_id=data.get("execution_id", ""),
            project=data.get("project", ""),
            patches=patches,
            policy=policy,
            result=data.get("result", "applied"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            attempt=data.get("attempt", 0),
            contract_notes=data.get("contract_notes"),
        )


def extract_hashable_payload(canonical_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Extract hashable payload from loaded canonical dict."""
    return {field: canonical_dict[field] for field in HASHABLE_FIELDS}


class PatchManifestStore:
    """Store for PatchManifest files with Contract Gate validation."""

    def __init__(self, store_root: str) -> None:
        self.store_root = Path(store_root)

    def _get_manifest_dir(self, project: str) -> Path:
        """Get directory for patch manifests."""
        manifest_dir = self.store_root / project / "patches"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        return manifest_dir

    def save(self, manifest: PatchManifest) -> Path:
        """Save manifest to disk and validate contract gate.

        Args:
            manifest: The PatchManifest to save

        Returns:
            Path to saved file

        Raises:
            RuntimeError: If contract gate validation fails
        """
        manifest_dir = self._get_manifest_dir(manifest.project)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Include attempt in filename for fix loop
        if manifest.attempt > 0:
            filename = f"patch_manifest_{manifest.execution_id}_attempt{manifest.attempt}_{timestamp}.json"
        else:
            filename = f"patch_manifest_{manifest.execution_id}_{timestamp}.json"

        file_path = manifest_dir / filename
        file_path.write_text(manifest.to_json())

        # Validate contract gate
        self._validate_contract_gate(file_path)

        return file_path

    def load(self, file_path: Path) -> PatchManifest:
        """Load manifest from disk and validate contract gate.

        Args:
            file_path: Path to manifest file

        Returns:
            PatchManifest

        Raises:
            RuntimeError: If contract gate validation fails
        """
        self._validate_contract_gate(file_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return PatchManifest.from_dict(data)

    def _validate_contract_gate(self, file_path: Path) -> None:
        """Validate contract gate: reload JSON and verify hash.

        Args:
            file_path: Path to manifest file

        Raises:
            RuntimeError: If hash mismatch
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)

        hashable_payload = extract_hashable_payload(loaded)
        recalculated_hash = compute_content_hash_sha256(hashable_payload)
        saved_hash = loaded.get("content_hash_sha256", "")

        if recalculated_hash != saved_hash:
            raise RuntimeError(
                f"PatchManifest Contract Gate FAILED: hash mismatch.\n"
                f"  File: {file_path}\n"
                f"  Expected hash: {saved_hash}\n"
                f"  Calculated hash: {recalculated_hash}"
            )

    def list_manifests(self, project: str) -> List[Path]:
        """List all manifest files for a project."""
        manifest_dir = self._get_manifest_dir(project)
        return sorted(manifest_dir.glob("patch_manifest_*.json"))

    def get_latest(self, project: str, execution_id: Optional[str] = None) -> Optional[Path]:
        """Get the most recent manifest file.

        Args:
            project: Project name
            execution_id: If provided, filter by execution_id

        Returns:
            Path to most recent manifest, or None
        """
        manifests = self.list_manifests(project)

        if execution_id:
            manifests = [m for m in manifests if execution_id in m.name]

        return manifests[-1] if manifests else None


def verify_manifest_prebuild(manifest: PatchManifest) -> tuple[bool, List[str]]:
    """Pre-build verification of a PatchManifest.

    Checks:
    - No patch path starts with blocked paths
    - No patch path contains ".."
    - All rewrite_ratio <= max_rewrite_ratio

    Args:
        manifest: The manifest to verify

    Returns:
        Tuple of (ok, errors)
    """
    errors: List[str] = []
    policy = manifest.policy

    for patch in manifest.patches:
        # Check for path traversal
        if ".." in patch.path:
            errors.append(f"Path traversal detected in: {patch.path}")

        # Check blocked paths
        for blocked in policy.blocked_paths:
            if patch.path.startswith(blocked):
                errors.append(f"Blocked path violation: {patch.path} starts with {blocked}")

        # Check rewrite ratio
        if patch.rewrite_ratio > policy.max_rewrite_ratio:
            errors.append(
                f"Rewrite ratio exceeded for {patch.path}: "
                f"{patch.rewrite_ratio:.2%} > {policy.max_rewrite_ratio:.0%}"
            )

    return (len(errors) == 0, errors)
