"""Canonical Hash Utilities - Deterministic hashing for contract gates.

This module provides standardized hash computation for all artifacts
that require contract gate validation.

Rules:
- JSON: canonical serialization with sort_keys=True, separators=(',',':'), ensure_ascii=False
- Text: UTF-8 encoded, normalized line endings (CRLF -> LF)
- Hash: SHA256, full hex digest (64 chars)
"""

import hashlib
import json
from typing import Any, Dict


def compute_content_hash_sha256(payload: Dict[str, Any]) -> str:
    """Compute SHA256 hash of a dict using canonical JSON serialization.

    Args:
        payload: Dictionary to hash

    Returns:
        SHA256 hex digest (64 characters)
    """
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


def compute_text_hash_sha256(text: str) -> str:
    """Compute SHA256 hash of text content with normalized line endings.

    Used for YAML and other text artifacts.

    Args:
        text: Text content to hash

    Returns:
        SHA256 hex digest (64 characters)
    """
    # Normalize line endings: CRLF -> LF
    normalized = text.replace('\r\n', '\n')
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def compute_file_hash_sha256(file_path: str, is_text: bool = True) -> str:
    """Compute SHA256 hash of a file.

    Args:
        file_path: Path to the file
        is_text: If True, normalize line endings; if False, hash raw bytes

    Returns:
        SHA256 hex digest (64 characters)
    """
    if is_text:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return compute_text_hash_sha256(content)
    else:
        with open(file_path, 'rb') as f:
            content = f.read()
        return hashlib.sha256(content).hexdigest()


def compute_json_file_hash_sha256(file_path: str) -> str:
    """Compute SHA256 hash of a JSON file using canonical serialization.

    Loads the JSON and re-serializes canonically to ensure deterministic hash.

    Args:
        file_path: Path to the JSON file

    Returns:
        SHA256 hex digest (64 characters)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    return compute_content_hash_sha256(payload)
