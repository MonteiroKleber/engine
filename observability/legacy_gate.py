"""Legacy contract gate validation for Engine integration.

Validates legacy artifacts (inventory, human_process) against:
1) schema_version field
2) content_hash_sha256 (deterministic hash)

Uses same canonicalization as /home/bazari/legacy/legacy/hash_utils.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Fields excluded from hash computation (same as legacy repo)
EXCLUDED_FIELDS = frozenset(["content_hash_sha256", "extracted_at"])

# Expected schema versions
EXPECTED_SCHEMA_VERSIONS = {
    "inventory": "legacy_inventory.v1",
    "human_process": "human_process.v1",
    "legacy_runlog": "legacy_runlog.v1",
}


@dataclass
class LegacyValidationResult:
    """Result of legacy bundle validation."""

    provided: bool = False
    bundle_path: Optional[str] = None  # Directory path of the bundle
    inventory_path: Optional[str] = None
    human_process_path: Optional[str] = None
    legacy_runlog_path: Optional[str] = None
    legacy_schema_ok: Optional[bool] = None
    legacy_contract_gate_ok: Optional[bool] = None
    legacy_contract_gate_errors: List[str] = field(default_factory=list)
    legacy_hashes: Dict[str, str] = field(default_factory=dict)
    schema_invalid: bool = False  # True if failure is specifically schema_version mismatch
    error_codes: List[str] = field(default_factory=list)  # ALWAYS present, 1:1 with errors

    def to_dict(self) -> dict:
        """Convert to dict for RunLog with canonical ALWAYS present fields."""
        return {
            "ok": self.ok,
            "bundle_path": self.bundle_path,
            "errors": self.legacy_contract_gate_errors,
            "error_codes": self.error_codes,
            # Additional detail fields
            "provided": self.provided,
            "inventory_path": self.inventory_path,
            "human_process_path": self.human_process_path,
            "legacy_runlog_path": self.legacy_runlog_path,
            "legacy_schema_ok": self.legacy_schema_ok,
            "legacy_contract_gate_ok": self.legacy_contract_gate_ok,
            "legacy_contract_gate_errors": self.legacy_contract_gate_errors,
            "legacy_hashes": self.legacy_hashes,
        }

    @property
    def ok(self) -> bool:
        """True if validation passed or not provided."""
        if not self.provided:
            return True
        return (
            self.legacy_schema_ok is True
            and self.legacy_contract_gate_ok is True
        )


def _prefix_err(prefix: str, msg: str) -> str:
    """Add prefix to error message (idempotent)."""
    if msg.startswith("SCHEMA: ") or msg.startswith("INTEGRITY: "):
        return msg
    return f"{prefix}: {msg}"


def _err_code(msg: str) -> str:
    """Map error message to deterministic error_code."""
    if msg.startswith("SCHEMA: "):
        return "LEGACY_SCHEMA_INVALID"
    if msg.startswith("INTEGRITY: "):
        return "LEGACY_INTEGRITY_FAILED"
    return "LEGACY_UNKNOWN"


def _push_err(result: LegacyValidationResult, msg: str) -> None:
    """Append error and error_code in sync (1:1 pairing)."""
    result.legacy_contract_gate_errors.append(msg)
    result.error_codes.append(_err_code(msg))


def _filter_payload(obj: Any) -> Any:
    """Recursively filter out excluded fields."""
    if isinstance(obj, dict):
        return {
            k: _filter_payload(v)
            for k, v in obj.items()
            if k not in EXCLUDED_FIELDS
        }
    elif isinstance(obj, list):
        return [_filter_payload(item) for item in obj]
    else:
        return obj


def compute_content_hash_sha256(payload: dict) -> str:
    """Compute SHA256 hash of payload in canonical JSON form.

    Rules (same as legacy repo):
    - sort_keys=True
    - separators=(',', ':')
    - Excludes: content_hash_sha256, extracted_at
    """
    filtered = _filter_payload(payload)
    canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_legacy_artifact(
    path: str,
    artifact_type: str,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate a single legacy artifact.

    Args:
        path: Path to JSON file
        artifact_type: One of "inventory", "human_process", "legacy_runlog"

    Returns:
        (ok, computed_hash, error_message)
    """
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return False, None, f"File not found: {path}"
    except json.JSONDecodeError as e:
        return False, None, f"Invalid JSON in {path}: {e}"

    # Validate schema_version
    expected_version = EXPECTED_SCHEMA_VERSIONS.get(artifact_type)
    if expected_version:
        actual_version = data.get("schema_version")
        if actual_version != expected_version:
            return False, None, (
                f"Schema version mismatch in {path}: "
                f"expected '{expected_version}', got '{actual_version}'"
            )

    # Validate content_hash_sha256 (skip for runlog - it's a log file, not a contract)
    if artifact_type == "legacy_runlog":
        # Runlog doesn't have content_hash_sha256, just validate schema
        return True, None, None

    stored_hash = data.get("content_hash_sha256")
    if not stored_hash:
        return False, None, f"Missing content_hash_sha256 in {path}"

    computed_hash = compute_content_hash_sha256(data)
    if stored_hash != computed_hash:
        return False, computed_hash, (
            f"Hash mismatch in {path}: "
            f"stored={stored_hash[:16]}... computed={computed_hash[:16]}..."
        )

    return True, computed_hash, None


def validate_legacy_bundle(
    legacy_bundle: Optional[Dict[str, str]],
) -> LegacyValidationResult:
    """Validate a legacy bundle.

    Args:
        legacy_bundle: Dict with keys:
            - inventory_path: path to legacy_inventory.v1.json
            - human_process_path: path to human_process.v1.json
            - legacy_runlog_path: path to legacy_runlog.v1.json (optional)
            OR
            - bundle_path: path to bundle directory (will auto-resolve files)

    Returns:
        LegacyValidationResult with validation status
    """
    result = LegacyValidationResult()

    if legacy_bundle is None:
        return result

    result.provided = True

    # Support bundle_path (directory) or individual paths
    bundle_path = legacy_bundle.get("bundle_path")
    if bundle_path:
        # Resolve paths from bundle directory
        bundle_dir = Path(bundle_path)
        result.bundle_path = str(bundle_dir)
        result.inventory_path = str(bundle_dir / "legacy_inventory.v1.json")
        result.human_process_path = str(bundle_dir / "human_process.v1.json")
        runlog_path = bundle_dir / "legacy_runlog.v1.json"
        if runlog_path.exists():
            result.legacy_runlog_path = str(runlog_path)
    else:
        result.inventory_path = legacy_bundle.get("inventory_path")
        result.human_process_path = legacy_bundle.get("human_process_path")
        result.legacy_runlog_path = legacy_bundle.get("legacy_runlog_path")

    schema_ok = True
    gate_ok = True
    hashes = {}

    # Load ledger if bundle_path provided
    ledger = {}
    if bundle_path:
        ledger_path = Path(bundle_path) / "legacy_contracts.v1.json"
        if ledger_path.exists():
            try:
                with open(ledger_path, "r") as f:
                    ledger = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                _push_err(result, _prefix_err("INTEGRITY", f"Failed to load ledger: {e}"))
                gate_ok = False

    # Validate inventory
    if result.inventory_path:
        ok, computed_hash, error = validate_legacy_artifact(
            result.inventory_path, "inventory"
        )
        if not ok:
            if "Schema version" in (error or ""):
                schema_ok = False
                _push_err(result, _prefix_err("SCHEMA", error or "Unknown error"))
            else:
                _push_err(result, _prefix_err("INTEGRITY", error or "Unknown error"))
            gate_ok = False
        else:
            hashes["inventory"] = computed_hash
            # Validate against ledger
            ledger_hash = ledger.get("artifacts", {}).get("legacy_inventory", {}).get("sha256")
            if ledger_hash and computed_hash != ledger_hash:
                gate_ok = False
                _push_err(result, _prefix_err(
                    "INTEGRITY",
                    f"Inventory hash mismatch with ledger: "
                    f"computed={computed_hash[:16]}... ledger={ledger_hash[:16]}..."
                ))

    # Validate human_process
    if result.human_process_path:
        ok, computed_hash, error = validate_legacy_artifact(
            result.human_process_path, "human_process"
        )
        if not ok:
            if "Schema version" in (error or ""):
                schema_ok = False
                _push_err(result, _prefix_err("SCHEMA", error or "Unknown error"))
            else:
                _push_err(result, _prefix_err("INTEGRITY", error or "Unknown error"))
            gate_ok = False
        else:
            hashes["human_process"] = computed_hash
            # Validate against ledger
            ledger_hash = ledger.get("artifacts", {}).get("human_process", {}).get("sha256")
            if ledger_hash and computed_hash != ledger_hash:
                gate_ok = False
                _push_err(result, _prefix_err(
                    "INTEGRITY",
                    f"Human process hash mismatch with ledger: "
                    f"computed={computed_hash[:16]}... ledger={ledger_hash[:16]}..."
                ))

    # Validate legacy_runlog (optional)
    if result.legacy_runlog_path:
        ok, computed_hash, error = validate_legacy_artifact(
            result.legacy_runlog_path, "legacy_runlog"
        )
        if not ok:
            if "Schema version" in (error or ""):
                schema_ok = False
                _push_err(result, _prefix_err("SCHEMA", error or "Unknown error"))
            else:
                _push_err(result, _prefix_err("INTEGRITY", error or "Unknown error"))
            gate_ok = False
        else:
            hashes["legacy_runlog"] = computed_hash

    result.legacy_schema_ok = schema_ok
    result.legacy_contract_gate_ok = gate_ok
    result.legacy_hashes = hashes
    # schema_invalid=True only when schema validation failed (not integrity/tamper)
    result.schema_invalid = not schema_ok

    return result
