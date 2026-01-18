"""Bundle manifest generator.

Generates bundle.manifest.json in the format expected by the loader:
{
  "name": "bundle-name",
  "version": "1.0.0",
  "description": "...",
  "contracts": [
    {"file": "rbac.json", "sha256": "SHA256:...", "required": true},
    ...
  ]
}
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set


def sha256_bytes(data: bytes) -> str:
    """Compute SHA256 hash of bytes.

    Args:
        data: Raw bytes to hash.

    Returns:
        Hex-encoded SHA256 hash.
    """
    return hashlib.sha256(data).hexdigest()


def sha256_str(text: str) -> str:
    """Compute SHA256 hash of string (UTF-8 encoded).

    Args:
        text: String to hash.

    Returns:
        Hex-encoded SHA256 hash.
    """
    return sha256_bytes(text.encode("utf-8"))


# Contracts that are required for the bundle to load (required=true in manifest)
# Per MVP decision: policies.json, mandates.json, autonomy.json are mandatory institutional contracts
REQUIRED_CONTRACTS: Set[str] = frozenset({
    "rbac.json",
    "approvals.json",
    "workflows.json",
    "sod.json",
    "invariants.json",
    "contract_ledger.json",
    # Institutional contracts (MVP decision 2026-01-17)
    "policies.json",
    "mandates.json",
    "autonomy.json",
})

# Contracts that are optional (required=false in manifest)
OPTIONAL_CONTRACTS: Set[str] = frozenset({
    "openapi.yaml",
    "contracts.json",  # interdepartmental contracts (multi mode)
})


def generate_manifest(
    bundle_name: str,
    version: str,
    contracts: Dict[str, str],
    system_name: str = "Unknown",
    mode: str = "single",
    departments: Optional[List[str]] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate bundle manifest in loader-compatible format.

    Generates manifest with contracts as array of objects with file, sha256, required.
    This format is compatible with the runtime loader (load_bundle.py).

    Args:
        bundle_name: Name of the bundle.
        version: Version string from IDL.
        contracts: Dict mapping contract filename to content.
        system_name: Name of the system from IDL.
        mode: Bundle mode - "single" or "multi".
        departments: List of department IDs (for multi mode).
        description: Optional description for the bundle.

    Returns:
        Manifest dict ready for JSON serialization.
    """
    # Build contracts array in loader format
    contracts_array: List[Dict[str, Any]] = []
    all_hashes: Dict[str, str] = {}

    for filename in sorted(contracts.keys()):
        content = contracts[filename]
        hash_hex = sha256_str(content)
        all_hashes[filename] = hash_hex

        # Determine if required based on filename (base name for multi-dept paths)
        base_name = filename.split("/")[-1] if "/" in filename else filename
        is_required = base_name in REQUIRED_CONTRACTS

        contracts_array.append({
            "file": filename,
            "sha256": f"SHA256:{hash_hex}",
            "required": is_required,
        })

    # Compute bundle hash (hash of all contract hashes concatenated, sorted by filename)
    hash_concat = "".join(
        f"{k}:{v}" for k, v in sorted(all_hashes.items())
    )
    bundle_hash = sha256_str(hash_concat)

    # Build manifest in loader-compatible format
    manifest: Dict[str, Any] = {
        "name": bundle_name,
        "version": version,
        "description": description or f"{system_name} bundle",
        "contracts": contracts_array,
    }

    # Include extra metadata (loader ignores these but useful for tooling)
    manifest["_metadata"] = {
        "manifest_version": "1.0",
        "system_name": system_name,
        "mode": mode,
        "bundle_hash": bundle_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Include departments list for multi mode
    if mode == "multi" and departments:
        manifest["_metadata"]["departments"] = sorted(departments)

    return manifest


def get_bundle_hash(manifest: Dict[str, Any]) -> Optional[str]:
    """Extract bundle_hash from manifest metadata.

    Args:
        manifest: Manifest dict.

    Returns:
        Bundle hash string, or None if not found.
    """
    metadata = manifest.get("_metadata", {})
    return metadata.get("bundle_hash")


def generate_manifest_json(
    bundle_name: str,
    version: str,
    contracts: Dict[str, str],
    system_name: str = "Unknown",
) -> str:
    """Generate bundle manifest as JSON string.

    Args:
        bundle_name: Name of the bundle.
        version: Version string from IDL.
        contracts: Dict mapping contract filename to content.
        system_name: Name of the system from IDL.

    Returns:
        JSON string with sorted keys.
    """
    manifest = generate_manifest(bundle_name, version, contracts, system_name)
    return json.dumps(manifest, indent=2, sort_keys=True)
