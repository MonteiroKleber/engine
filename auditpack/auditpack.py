"""AuditPack - Generate auditable ZIP packages from episodes.

This module provides functionality to create reproducible, verifiable
audit packages from episode directories.

Key features:
- Deterministic ZIP generation (sorted paths, canonical index)
- Security checks (no secrets, credentials, or sensitive files)
- Root hash derivation for verification
- README with offline verification instructions

Error prefixes:
- SECURITY: for security-related errors
- AUDITPACK: for general auditpack errors
"""

import hashlib
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import jsonschema


# =============================================================================
# Constants
# =============================================================================

AUDITPACK_INDEX_SCHEMA_VERSION = "auditpack_index.v1"

# Schema path
_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "auditpack_index.v1.json"
_AUDITPACK_INDEX_SCHEMA: Optional[dict] = None

# Forbidden patterns (security)
FORBIDDEN_PATTERNS: List[str] = [
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "secrets/",
    "secrets.",
    ".secrets",
    "credentials/",
    "credentials.",
    ".credentials",
    "private_key",
    "private_keys/",
    ".pem",
    ".key",
    "id_rsa",
    "id_ed25519",
    "token",
    "tokens/",
    "api_key",
    "apikey",
    "password",
    "passwd",
    "aws_access_key",
    "aws_secret",
    ".git/",
    ".gitignore",
]

# Files to exclude from auditpack (not security, just noise)
EXCLUDED_PATTERNS: List[str] = [
    "__pycache__/",
    ".pyc",
    ".pyo",
    ".DS_Store",
    "Thumbs.db",
]


# =============================================================================
# Schema Loading
# =============================================================================


def _get_schema() -> dict:
    """Load and cache the auditpack_index schema."""
    global _AUDITPACK_INDEX_SCHEMA
    if _AUDITPACK_INDEX_SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _AUDITPACK_INDEX_SCHEMA = json.load(f)
    return _AUDITPACK_INDEX_SCHEMA


# =============================================================================
# Exceptions
# =============================================================================


class AuditPackError(Exception):
    """Base exception for auditpack errors.

    Error messages are prefixed with "AUDITPACK: " following project conventions.
    """

    def __init__(self, message: str, error_code: str = "AUDITPACK_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(f"AUDITPACK: {message}")


class AuditPackSecurityError(AuditPackError):
    """Exception raised when security check fails.

    Error messages are prefixed with "SECURITY: " following project conventions.
    """

    def __init__(self, message: str, forbidden_path: str = ""):
        self.forbidden_path = forbidden_path
        super().__init__(message, "AUDITPACK_SECURITY_BLOCKED")
        # Override the message format for security errors
        Exception.__init__(self, f"SECURITY: {message}")


class AuditPackValidationError(AuditPackError):
    """Exception raised when index validation fails."""

    def __init__(self, message: str, path: str = ""):
        self.path = path
        super().__init__(message, "AUDITPACK_VALIDATION_ERROR")


# =============================================================================
# Hash Computation
# =============================================================================


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        path: Path to file

    Returns:
        Hash string in format "sha256:<hex>"
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


def compute_root_hash(files: List[dict]) -> str:
    """Compute root hash from sorted list of file entries.

    The root hash is derived from concatenating "<path>\\n<sha256>\\n"
    for each file in sorted order by path.

    Args:
        files: List of dicts with 'path' and 'sha256' keys

    Returns:
        Root hash string in format "sha256:<hex>"
    """
    # Sort by path for deterministic ordering
    sorted_files = sorted(files, key=lambda x: x["path"])

    # Build canonical blob
    blob_parts = []
    for f in sorted_files:
        blob_parts.append(f"{f['path']}\n{f['sha256']}\n")

    blob = "".join(blob_parts)
    return compute_content_hash(blob.encode("utf-8"))


# =============================================================================
# Security Checks
# =============================================================================


def _is_forbidden_path(path: str) -> Optional[str]:
    """Check if a path matches any forbidden pattern.

    Args:
        path: Path to check (relative)

    Returns:
        Matched pattern or None
    """
    path_lower = path.lower()

    for pattern in FORBIDDEN_PATTERNS:
        pattern_lower = pattern.lower()
        if pattern_lower in path_lower:
            return pattern

    return None


def _is_excluded_path(path: str) -> bool:
    """Check if a path should be excluded (not security, just noise).

    Args:
        path: Path to check

    Returns:
        True if should be excluded
    """
    path_lower = path.lower()

    for pattern in EXCLUDED_PATTERNS:
        if pattern.lower() in path_lower:
            return True

    return False


def verify_no_secrets(paths: List[Path], base_path: Optional[Path] = None) -> None:
    """Verify that no paths contain secrets or sensitive files.

    Args:
        paths: List of paths to check
        base_path: Base path for relative path computation

    Raises:
        AuditPackSecurityError: If a forbidden path is found
    """
    for path in paths:
        # Get relative path for pattern matching
        if base_path:
            try:
                rel_path = str(path.relative_to(base_path))
            except ValueError:
                rel_path = str(path)
        else:
            rel_path = str(path)

        forbidden = _is_forbidden_path(rel_path)
        if forbidden:
            raise AuditPackSecurityError(
                f"Forbidden path pattern '{forbidden}' found in: {rel_path}",
                forbidden_path=rel_path,
            )


# =============================================================================
# Index Generation
# =============================================================================


def compute_auditpack_index(
    episode_id: str,
    files: List[Tuple[Path, str]],
    source_root_hash: Optional[str] = None,
    include_artifacts: bool = False,
    execution_id: Optional[str] = None,
) -> dict:
    """Compute the auditpack index from a list of files.

    Args:
        episode_id: Episode identifier
        files: List of tuples (file_path, zip_path)
        source_root_hash: Root hash from original episode manifest
        include_artifacts: Whether artifacts were included
        execution_id: Optional execution ID

    Returns:
        Auditpack index dict
    """
    file_entries = []
    total_size = 0
    has_approval = False
    has_change_request = False
    has_legacy_verify = False

    for file_path, zip_path in files:
        file_hash = compute_file_hash(file_path)
        file_size = file_path.stat().st_size
        total_size += file_size

        file_entries.append({
            "path": zip_path,
            "sha256": file_hash,
            "size_bytes": file_size,
        })

        # Track what's included
        if "approval" in zip_path.lower():
            has_approval = True
        if "change_request" in zip_path.lower():
            has_change_request = True
        if "legacy" in zip_path.lower():
            has_legacy_verify = True

    # Sort by path for determinism
    file_entries.sort(key=lambda x: x["path"])

    # Compute root hash
    root_hash = compute_root_hash(file_entries)

    index = {
        "schema_version": AUDITPACK_INDEX_SCHEMA_VERSION,
        "episode_id": episode_id,
        "execution_id": execution_id,
        "created_at_volatile": datetime.utcnow().isoformat() + "Z",
        "source_episode_root_hash": source_root_hash,
        "files": file_entries,
        "root_hash_sha256": root_hash,
        "algorithm": "sha256",
        "include_artifacts": include_artifacts,
        "stats": {
            "total_files": len(file_entries),
            "total_size_bytes": total_size,
            "has_approval": has_approval,
            "has_change_request": has_change_request,
            "has_legacy_verify": has_legacy_verify,
        },
    }

    return index


def validate_auditpack_index(index: dict) -> None:
    """Validate an auditpack index against the schema.

    Args:
        index: The index dict to validate

    Raises:
        AuditPackValidationError: If validation fails
    """
    schema = _get_schema()

    try:
        jsonschema.validate(instance=index, schema=schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else ""
        raise AuditPackValidationError(e.message, path)


# =============================================================================
# README Generation
# =============================================================================


def generate_readme_audit(episode_id: str, index: dict) -> str:
    """Generate README_AUDIT.md content.

    Args:
        episode_id: Episode identifier
        index: Auditpack index dict

    Returns:
        README content as string
    """
    stats = index.get("stats", {})
    source_hash = index.get("source_episode_root_hash", "N/A")
    root_hash = index.get("root_hash_sha256", "N/A")

    content = f"""# AuditPack - Episode {episode_id}

## Overview

This audit package contains all artifacts necessary for offline verification
of episode `{episode_id}`.

## Contents

- **Total Files**: {stats.get('total_files', 0)}
- **Total Size**: {stats.get('total_size_bytes', 0)} bytes
- **Has Approval**: {'Yes' if stats.get('has_approval') else 'No'}
- **Has Change Request**: {'Yes' if stats.get('has_change_request') else 'No'}
- **Has Legacy Verify**: {'Yes' if stats.get('has_legacy_verify') else 'No'}

## Integrity Hashes

- **Source Episode Root Hash**: `{source_hash}`
- **AuditPack Root Hash**: `{root_hash}`

## Verification Instructions

### 1. Verify Index Integrity

The `index.json` file contains SHA256 hashes of all files in this package.
To verify file integrity:

```bash
# For each file in index.json, verify the hash
python3 -c "
import json
import hashlib
from pathlib import Path

with open('index.json') as f:
    index = json.load(f)

errors = []
for entry in index['files']:
    path = Path(entry['path'])
    if not path.exists():
        errors.append(f'Missing: {{path}}')
        continue

    with open(path, 'rb') as f:
        actual = 'sha256:' + hashlib.sha256(f.read()).hexdigest()

    if actual != entry['sha256']:
        errors.append(f'Hash mismatch: {{path}}')

if errors:
    print('ERRORS:')
    for e in errors:
        print(f'  - {{e}}')
else:
    print('All files verified successfully!')
"
```

### 2. Verify Root Hash

The root hash is computed by concatenating `<path>\\n<sha256>\\n` for each
file (sorted by path) and hashing the result:

```bash
python3 -c "
import json
import hashlib

with open('index.json') as f:
    index = json.load(f)

files = sorted(index['files'], key=lambda x: x['path'])
blob = ''.join(f\\"{{f['path']}}\\\\n{{f['sha256']}}\\\\n\\" for f in files)
computed = 'sha256:' + hashlib.sha256(blob.encode()).hexdigest()

if computed == index['root_hash_sha256']:
    print(f'Root hash verified: {{computed}}')
else:
    print(f'Root hash MISMATCH!')
    print(f'  Expected: {{index[\"root_hash_sha256\"]}}')
    print(f'  Computed: {{computed}}')
"
```

### 3. Verify Episode Manifest

Check that the episode manifest inside `episode/manifest.json` matches
the original episode's integrity hash (if available).

### 4. Cross-Reference with SHA256SUMS

The `hashes/sha256sums.txt` file can be verified using standard tools:

```bash
cd auditpack
sha256sum -c hashes/sha256sums.txt
```

## File Structure

```
auditpack/
├── index.json              # Canonical index with all hashes
├── README_AUDIT.md         # This file
├── episode/
│   ├── manifest.json       # Episode manifest
│   ├── runlog.json         # Execution runlog
│   ├── approvals/          # Approval files (if any)
│   ├── change_request/     # Change request (if any)
│   ├── contracts/          # Generated contracts
│   └── legacy/             # Legacy verification (if any)
└── hashes/
    └── sha256sums.txt      # SHA256 checksums
```

## Notes

- This package was generated automatically by the Bazari Engine
- All timestamps in `created_at_volatile` are excluded from hash computation
- The source episode root hash is from the original episode manifest
- The auditpack root hash is computed from this package's contents

## Understanding Hash Differences

### Why do source and auditpack hashes differ?

The **Source Episode Root Hash** and **AuditPack Root Hash** will typically differ.
This is **expected and correct** behavior:

1. **Source Episode Root Hash**: Computed at episode finalization, BEFORE approval.
   This captures the state of contracts, runlog, and inputs at generation time.

2. **AuditPack Root Hash**: Computed at auditpack generation, AFTER approval.
   This includes the approval file which was added after finalization.

### The Append-Only Model

The Bazari Engine uses an **append-only** model for episode integrity:

```
Episode Finalization        Approval Added           AuditPack Generated
        |                        |                          |
        v                        v                          v
   [contracts]              [contracts]                [contracts]
   [runlog.json]      +     [runlog.json]       +      [runlog.json]
   [manifest.json]          [manifest.json]            [manifest.json]
                            [approval.json]  <--NEW    [approval.json]
                                                       [index.json]
                                                       [sha256sums.txt]
        |                        |                          |
        v                        v                          v
   root_hash_v1             (not recomputed)           root_hash_v2
```

- **Original files remain untouched** - their hashes are preserved
- **Only new files are appended** - approval, index, sha256sums
- **No data is modified or deleted** - full audit trail maintained

### Verifying Integrity Despite Different Hashes

To verify that the original episode content is intact:

1. **Check individual file hashes**: All files listed in `manifest.json`
   should have identical hashes in the auditpack.

2. **Verify append-only property**: The only new files should be:
   - `approvals/approval.json` (the approval record)
   - AuditPack metadata (index.json, sha256sums.txt, README_AUDIT.md)

3. **Cross-reference manifests**: The `manifest.json` inside the auditpack
   should match the source episode's manifest byte-for-byte.

### What Would Indicate Tampering?

The following would indicate potential tampering:

- Any file in `manifest.json.integrity.file_hashes` has a different hash
- The `manifest.json` content differs from the source
- Files were removed (not just added)
- Contract files (ir.json, srs.json, openapi.json) have different hashes

## Schema Version

- AuditPack Index: `{AUDITPACK_INDEX_SCHEMA_VERSION}`

---

Generated by Bazari Engine AuditPack
"""
    return content


def generate_sha256sums(files: List[Tuple[Path, str]]) -> str:
    """Generate sha256sums.txt content.

    Args:
        files: List of tuples (file_path, zip_path)

    Returns:
        SHA256SUMS content as string
    """
    lines = []

    for file_path, zip_path in sorted(files, key=lambda x: x[1]):
        file_hash = compute_file_hash(file_path)
        # Extract just the hex part (without sha256: prefix)
        hex_hash = file_hash.replace("sha256:", "")
        lines.append(f"{hex_hash}  {zip_path}")

    return "\n".join(lines) + "\n"


# =============================================================================
# AuditPack Builder
# =============================================================================


def _collect_episode_files(
    episode_dir: Path,
    include_artifacts: bool = False,
) -> List[Tuple[Path, str]]:
    """Collect files from episode directory.

    Args:
        episode_dir: Path to episode directory
        include_artifacts: Whether to include artifacts

    Returns:
        List of tuples (file_path, zip_path)
    """
    files = []

    # Always include manifest and runlog
    manifest_path = episode_dir / "manifest.json"
    if manifest_path.exists():
        files.append((manifest_path, "auditpack/episode/manifest.json"))

    runlog_path = episode_dir / "runlog.json"
    if runlog_path.exists():
        files.append((runlog_path, "auditpack/episode/runlog.json"))

    # Include approvals
    approvals_dir = episode_dir / "approvals"
    if approvals_dir.exists():
        for f in approvals_dir.iterdir():
            if f.is_file() and not _is_excluded_path(str(f)):
                zip_path = f"auditpack/episode/approvals/{f.name}"
                files.append((f, zip_path))

    # Include change_request
    cr_dir = episode_dir / "change_request"
    if cr_dir.exists():
        for f in cr_dir.iterdir():
            if f.is_file() and not _is_excluded_path(str(f)):
                zip_path = f"auditpack/episode/change_request/{f.name}"
                files.append((f, zip_path))

    # Include contracts
    contracts_dir = episode_dir / "contracts"
    if contracts_dir.exists():
        for f in contracts_dir.iterdir():
            if f.is_file() and not _is_excluded_path(str(f)):
                zip_path = f"auditpack/episode/contracts/{f.name}"
                files.append((f, zip_path))

    # Include input files
    input_dir = episode_dir / "input"
    if input_dir.exists():
        for f in input_dir.iterdir():
            if f.is_file() and not _is_excluded_path(str(f)):
                zip_path = f"auditpack/episode/input/{f.name}"
                files.append((f, zip_path))

    # Include legacy verification if exists
    legacy_dir = episode_dir / "legacy"
    if legacy_dir.exists():
        for f in legacy_dir.iterdir():
            if f.is_file() and not _is_excluded_path(str(f)):
                zip_path = f"auditpack/episode/legacy/{f.name}"
                files.append((f, zip_path))

    # Optionally include artifacts
    if include_artifacts:
        artifacts_dir = episode_dir / "artifacts"
        if artifacts_dir.exists():
            for f in artifacts_dir.iterdir():
                if f.is_file() and not _is_excluded_path(str(f)):
                    zip_path = f"auditpack/episode/artifacts/{f.name}"
                    files.append((f, zip_path))

    return files


def build_auditpack(
    episode_dir: Path,
    out_zip: Path,
    include_artifacts: bool = False,
) -> dict:
    """Build an auditpack ZIP from an episode directory.

    Args:
        episode_dir: Path to episode directory
        out_zip: Output path for the ZIP file
        include_artifacts: Whether to include artifacts

    Returns:
        Dict with build result info

    Raises:
        AuditPackError: If episode directory not found
        AuditPackSecurityError: If forbidden files found
    """
    if not episode_dir.exists():
        raise AuditPackError(f"Episode directory not found: {episode_dir}")

    manifest_path = episode_dir / "manifest.json"
    if not manifest_path.exists():
        raise AuditPackError(f"Episode manifest not found: {manifest_path}")

    # Load manifest to get episode info
    with open(manifest_path) as f:
        manifest = json.load(f)

    episode_id = manifest.get("episode_id", episode_dir.name)
    execution_id = manifest.get("execution_id")
    source_root_hash = manifest.get("integrity", {}).get("episode_root_hash_sha256")

    # Collect files
    files = _collect_episode_files(episode_dir, include_artifacts)

    if not files:
        raise AuditPackError("No files found in episode directory")

    # Security check - verify no secrets
    file_paths = [f[0] for f in files]
    verify_no_secrets(file_paths, episode_dir)

    # Compute index
    index = compute_auditpack_index(
        episode_id=episode_id,
        files=files,
        source_root_hash=source_root_hash,
        include_artifacts=include_artifacts,
        execution_id=execution_id,
    )

    # Validate index
    validate_auditpack_index(index)

    # Generate README
    readme_content = generate_readme_audit(episode_id, index)

    # Generate sha256sums
    sha256sums_content = generate_sha256sums(files)

    # Create ZIP with deterministic ordering
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add index.json first (canonical)
        index_json = json.dumps(index, indent=2, sort_keys=True)
        zf.writestr("auditpack/index.json", index_json)

        # Add README
        zf.writestr("auditpack/README_AUDIT.md", readme_content)

        # Add sha256sums
        zf.writestr("auditpack/hashes/sha256sums.txt", sha256sums_content)

        # Add episode files (sorted for determinism)
        for file_path, zip_path in sorted(files, key=lambda x: x[1]):
            zf.write(file_path, zip_path)

    return {
        "success": True,
        "episode_id": episode_id,
        "out_zip": str(out_zip),
        "root_hash": index["root_hash_sha256"],
        "source_root_hash": source_root_hash,
        "total_files": len(files),
        "include_artifacts": include_artifacts,
        "index": index,
    }
