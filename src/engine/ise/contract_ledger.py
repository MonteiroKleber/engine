"""Contract ledger generator for audit trail."""

import json
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid


def generate_contract_ledger(
    bundle_name: str,
    version: str,
    contracts: Dict[str, str],
    manifest_hash: str,
    idl_source: str,
) -> Dict[str, Any]:
    """Generate contract ledger for audit trail.

    Args:
        bundle_name: Name of the bundle.
        version: Version string from IDL.
        contracts: Dict mapping contract filename to content hash.
        manifest_hash: SHA256 hash of the manifest.
        idl_source: Original IDL source (for hash computation).

    Returns:
        Contract ledger dict ready for JSON serialization.
    """
    from .manifest import sha256_str

    # Generate deterministic ledger ID based on bundle content
    ledger_seed = f"{bundle_name}:{version}:{manifest_hash}"
    ledger_id = sha256_str(ledger_seed)[:16]

    # Build contract entries
    contract_entries: List[Dict[str, Any]] = []
    for filename, content_hash in sorted(contracts.items()):
        contract_entries.append({
            "contract_name": filename,
            "content_hash": content_hash,
            "status": "active",
        })

    return {
        "ledger_version": "1.0",
        "ledger_id": ledger_id,
        "bundle_name": bundle_name,
        "bundle_version": version,
        "manifest_hash": manifest_hash,
        "idl_hash": sha256_str(idl_source),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contracts": contract_entries,
        "audit_trail": [
            {
                "event": "bundle_compiled",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": {
                    "contract_count": len(contracts),
                    "bundle_name": bundle_name,
                },
            }
        ],
    }


def generate_contract_ledger_json(
    bundle_name: str,
    version: str,
    contracts: Dict[str, str],
    manifest_hash: str,
    idl_source: str,
) -> str:
    """Generate contract ledger as JSON string.

    Args:
        bundle_name: Name of the bundle.
        version: Version string from IDL.
        contracts: Dict mapping contract filename to content hash.
        manifest_hash: SHA256 hash of the manifest.
        idl_source: Original IDL source.

    Returns:
        JSON string with sorted keys.
    """
    ledger = generate_contract_ledger(
        bundle_name, version, contracts, manifest_hash, idl_source
    )
    return json.dumps(ledger, indent=2, sort_keys=True)
