"""Offline bundle verification.

Verifies bundle integrity and source_idl_sha256 linkage without requiring runtime.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.loader.verify_hashes import compute_sha256, normalize_hash

from .errors import (
    PROOF_MANIFEST_MISSING,
    PROOF_MANIFEST_INVALID_JSON,
    PROOF_MANIFEST_INVALID_SCHEMA,
    PROOF_CONTRACT_MISSING,
    PROOF_CONTRACT_HASH_MISMATCH,
    PROOF_CONTRACT_INVALID_PATH,
    PROOF_CONTRACT_HASH_INVALID_FORMAT,
    PROOF_LEDGER_MISSING,
    PROOF_LEDGER_INVALID_JSON,
    PROOF_LEDGER_INVALID_SCHEMA,
    PROOF_LEDGER_MANIFEST_HASH_MISMATCH,
    PROOF_LEDGER_MANIFEST_HASH_INVALID,
    PROOF_LEDGER_CONTRACT_MISSING,
    PROOF_LEDGER_CONTRACT_EXTRA,
    PROOF_LEDGER_CONTRACT_HASH_MISMATCH,
    PROOF_SOURCE_IDL_MISSING,
    PROOF_SOURCE_IDL_INVALID_FORMAT,
    PROOF_PATH_TRAVERSAL,
)


@dataclass
class ProofResult:
    """Result of offline proof verification."""

    passed: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    bundle_name: Optional[str] = None
    bundle_version: Optional[str] = None
    source_idl_sha256: Optional[str] = None
    manifest_hash: Optional[str] = None
    contracts_verified: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "bundle_name": self.bundle_name,
            "bundle_version": self.bundle_version,
            "source_idl_sha256": self.source_idl_sha256,
            "manifest_hash": self.manifest_hash,
            "contracts_verified": self.contracts_verified,
            "details": self.details,
        }


def is_valid_sha256_hex(value: str) -> bool:
    """Check if value is a valid 64-character hex string (SHA256).

    Args:
        value: String to validate.

    Returns:
        True if valid SHA256 hex, False otherwise.
    """
    if not isinstance(value, str):
        return False
    if len(value) != 64:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def is_safe_path(bundle_path: Path, file_path: str) -> bool:
    """Check if file_path is safe (no path traversal).

    Args:
        bundle_path: Root bundle directory (resolved).
        file_path: Relative file path from manifest.

    Returns:
        True if path is safe, False if path traversal detected.
    """
    # Reject absolute paths
    if os.path.isabs(file_path):
        return False

    # Reject paths with ..
    if ".." in file_path.split(os.sep) or ".." in file_path.split("/"):
        return False

    # Resolve the full path and ensure it's within bundle
    try:
        full_path = (bundle_path / file_path).resolve()
        bundle_resolved = bundle_path.resolve()

        # Check if full_path is within bundle_resolved
        # Using os.path.commonpath is safer than string comparison
        try:
            common = Path(os.path.commonpath([str(bundle_resolved), str(full_path)]))
            return common == bundle_resolved
        except ValueError:
            # Different drives on Windows
            return False
    except (OSError, RuntimeError):
        return False


def _fail(code: str, message: str, **kwargs: Any) -> ProofResult:
    """Create a failed ProofResult."""
    return ProofResult(
        passed=False,
        error_code=code,
        error_message=message,
        **kwargs,
    )


def _pass(
    bundle_name: str,
    bundle_version: str,
    source_idl_sha256: str,
    manifest_hash: str,
    contracts_verified: int,
) -> ProofResult:
    """Create a passed ProofResult."""
    return ProofResult(
        passed=True,
        bundle_name=bundle_name,
        bundle_version=bundle_version,
        source_idl_sha256=source_idl_sha256,
        manifest_hash=manifest_hash,
        contracts_verified=contracts_verified,
    )


def verify_bundle_offline(bundle_path: Path) -> ProofResult:
    """Verify bundle integrity offline.

    Performs the following checks:
    1. Reads and validates bundle.manifest.json
    2. Verifies SHA256 hash of each contract file
    3. Reads and validates contract_ledger.json
    4. Verifies manifest_hash in ledger matches actual manifest hash
    5. Verifies contracts[] in ledger match manifest (1:1, same files and hashes)
    6. Validates source_idl_sha256 presence and format

    Args:
        bundle_path: Path to the bundle directory.

    Returns:
        ProofResult with passed=True on success, or error details on failure.
    """
    bundle_path = Path(bundle_path).resolve()

    # ================================================================
    # Step 1: Read and validate manifest
    # ================================================================
    manifest_path = bundle_path / "bundle.manifest.json"

    if not manifest_path.exists():
        return _fail(
            PROOF_MANIFEST_MISSING,
            f"bundle.manifest.json not found at {manifest_path}",
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        return _fail(
            PROOF_MANIFEST_INVALID_JSON,
            f"Invalid JSON in bundle.manifest.json: {e}",
        )

    # Validate manifest schema (minimal required fields)
    if not isinstance(manifest.get("contracts"), list):
        return _fail(
            PROOF_MANIFEST_INVALID_SCHEMA,
            "bundle.manifest.json missing 'contracts' array",
        )

    bundle_name = manifest.get("name", "unknown")
    bundle_version = manifest.get("version", "unknown")

    # Compute manifest hash for later verification
    manifest_hash = compute_sha256(manifest_path)

    # ================================================================
    # Step 2: Verify each contract hash
    # ================================================================
    manifest_contracts: Dict[str, str] = {}  # file -> normalized hash

    for contract in manifest.get("contracts", []):
        contract_file = contract.get("file")
        contract_sha256 = contract.get("sha256")
        required = contract.get("required", True)

        if not contract_file:
            continue

        # Security: Check for path traversal
        if not is_safe_path(bundle_path, contract_file):
            return _fail(
                PROOF_PATH_TRAVERSAL,
                f"Unsafe path detected: {contract_file}",
                details={"file": contract_file},
            )

        contract_path = bundle_path / contract_file

        # Check file exists
        if not contract_path.exists():
            if required:
                return _fail(
                    PROOF_CONTRACT_MISSING,
                    f"Required contract missing: {contract_file}",
                    details={"file": contract_file},
                )
            continue

        # Validate hash format
        if contract_sha256:
            normalized = normalize_hash(contract_sha256)
            if not is_valid_sha256_hex(normalized):
                return _fail(
                    PROOF_CONTRACT_HASH_INVALID_FORMAT,
                    f"Invalid SHA256 format for {contract_file}: {contract_sha256}",
                    details={"file": contract_file, "sha256": contract_sha256},
                )

            # Verify hash
            actual_hash = compute_sha256(contract_path)
            if actual_hash.lower() != normalized:
                return _fail(
                    PROOF_CONTRACT_HASH_MISMATCH,
                    f"Hash mismatch for {contract_file}",
                    details={
                        "file": contract_file,
                        "expected": normalized,
                        "actual": actual_hash,
                    },
                )

            # Store for cross-check with ledger
            manifest_contracts[contract_file] = normalized

    contracts_verified = len(manifest_contracts)

    # ================================================================
    # Step 3: Read and validate ledger
    # ================================================================
    ledger_path = bundle_path / "contract_ledger.json"

    if not ledger_path.exists():
        return _fail(
            PROOF_LEDGER_MISSING,
            f"contract_ledger.json not found at {ledger_path}",
        )

    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            ledger = json.load(f)
    except json.JSONDecodeError as e:
        return _fail(
            PROOF_LEDGER_INVALID_JSON,
            f"Invalid JSON in contract_ledger.json: {e}",
        )

    # Validate ledger schema (minimal required fields)
    if not isinstance(ledger.get("contracts"), list):
        return _fail(
            PROOF_LEDGER_INVALID_SCHEMA,
            "contract_ledger.json missing 'contracts' array",
        )

    # ================================================================
    # Step 4: Verify manifest_hash in ledger
    # ================================================================
    ledger_manifest_hash = ledger.get("manifest_hash")

    if not ledger_manifest_hash:
        return _fail(
            PROOF_LEDGER_INVALID_SCHEMA,
            "contract_ledger.json missing 'manifest_hash'",
        )

    if not is_valid_sha256_hex(ledger_manifest_hash):
        return _fail(
            PROOF_LEDGER_MANIFEST_HASH_INVALID,
            f"Invalid manifest_hash format in ledger: {ledger_manifest_hash}",
        )

    if ledger_manifest_hash.lower() != manifest_hash.lower():
        return _fail(
            PROOF_LEDGER_MANIFEST_HASH_MISMATCH,
            "Ledger manifest_hash does not match actual manifest hash",
            details={
                "ledger_manifest_hash": ledger_manifest_hash,
                "actual_manifest_hash": manifest_hash,
            },
        )

    # ================================================================
    # Step 5: Cross-check contracts between manifest and ledger
    # ================================================================
    ledger_contracts: Dict[str, str] = {}  # file -> normalized hash

    for lc in ledger.get("contracts", []):
        # Ledger uses "contract_name" for the file
        contract_name = lc.get("contract_name")
        content_hash = lc.get("content_hash")

        if contract_name and content_hash:
            normalized = normalize_hash(content_hash)
            ledger_contracts[contract_name] = normalized

    # Check all manifest contracts are in ledger with matching hash
    for file, manifest_hash_val in manifest_contracts.items():
        if file not in ledger_contracts:
            return _fail(
                PROOF_LEDGER_CONTRACT_MISSING,
                f"Contract {file} in manifest but not in ledger",
                details={"file": file},
            )
        if ledger_contracts[file] != manifest_hash_val:
            return _fail(
                PROOF_LEDGER_CONTRACT_HASH_MISMATCH,
                f"Hash mismatch for {file} between manifest and ledger",
                details={
                    "file": file,
                    "manifest_hash": manifest_hash_val,
                    "ledger_hash": ledger_contracts[file],
                },
            )

    # Check no extra contracts in ledger
    for file in ledger_contracts:
        if file not in manifest_contracts:
            return _fail(
                PROOF_LEDGER_CONTRACT_EXTRA,
                f"Contract {file} in ledger but not in manifest",
                details={"file": file},
            )

    # ================================================================
    # Step 6: Validate source_idl_sha256
    # ================================================================
    source_idl_sha256 = ledger.get("source_idl_sha256")

    if not source_idl_sha256:
        return _fail(
            PROOF_SOURCE_IDL_MISSING,
            "source_idl_sha256 not found in contract_ledger.json",
        )

    if not is_valid_sha256_hex(source_idl_sha256):
        return _fail(
            PROOF_SOURCE_IDL_INVALID_FORMAT,
            f"Invalid source_idl_sha256 format: {source_idl_sha256}",
            details={"source_idl_sha256": source_idl_sha256},
        )

    # ================================================================
    # Step 7: All checks passed
    # ================================================================
    return _pass(
        bundle_name=bundle_name,
        bundle_version=bundle_version,
        source_idl_sha256=source_idl_sha256,
        manifest_hash=manifest_hash,
        contracts_verified=contracts_verified,
    )
