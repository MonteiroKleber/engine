"""Hash verification for bundle contracts."""

import hashlib
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file.

    Returns:
        Hex-encoded SHA-256 hash.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def normalize_hash(hash_value: str) -> str:
    """Normalize hash value by removing SHA256: prefix if present.

    Args:
        hash_value: Hash string, possibly with "SHA256:" prefix.

    Returns:
        Lowercase hex-encoded hash without prefix.
    """
    if hash_value.upper().startswith("SHA256:"):
        return hash_value[7:].lower()
    return hash_value.lower()


def verify_contract_hash(file_path: Path, expected_hash: str) -> bool:
    """Verify that a file matches its expected SHA-256 hash.

    Args:
        file_path: Path to the file.
        expected_hash: Expected SHA-256 hash (accepts "SHA256:<hex>" or "<hex>").

    Returns:
        True if hash matches, False otherwise.
    """
    actual_hash = compute_sha256(file_path)
    expected_normalized = normalize_hash(expected_hash)
    return actual_hash.lower() == expected_normalized
