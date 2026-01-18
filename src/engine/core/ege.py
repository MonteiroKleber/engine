"""EGE (Engine Governance Enforcement) core module.

Implements deterministic drift detection for bundle/contract hash mismatches.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from engine.core.data_root import get_institution_root
from engine.core.institution_config import get_effective_config, HASH_PREFIX
from engine.core.ledger import get_ledger_for_institution
from engine.ise.release import get_bundles_root_for_institution


# Schema version for drift state
DRIFT_STATE_SCHEMA_VERSION = "1.0"

# Drift state file name
DRIFT_STATE_FILE = "ege_drift_state.json"


@dataclass
class DriftState:
    """Drift state for an institution."""

    schema_version: str = DRIFT_STATE_SCHEMA_VERSION
    status: str = "UNPINNED"  # CLEAR | ACTIVE | UNPINNED
    checked_at: Optional[str] = None  # UTC ISO8601

    # Expected hashes from config
    expected_bundle_manifest_sha256: Optional[str] = None
    expected_contract_ledger_sha256: Optional[str] = None

    # Observed hashes from CURRENT bundle
    observed_bundle_manifest_sha256: Optional[str] = None
    observed_contract_ledger_sha256: Optional[str] = None

    # Mismatch flags
    bundle_manifest_mismatch: bool = False
    contract_ledger_mismatch: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DriftState":
        """Create from dictionary."""
        return cls(
            schema_version=data.get("schema_version", DRIFT_STATE_SCHEMA_VERSION),
            status=data.get("status", "UNPINNED"),
            checked_at=data.get("checked_at"),
            expected_bundle_manifest_sha256=data.get("expected_bundle_manifest_sha256"),
            expected_contract_ledger_sha256=data.get("expected_contract_ledger_sha256"),
            observed_bundle_manifest_sha256=data.get("observed_bundle_manifest_sha256"),
            observed_contract_ledger_sha256=data.get("observed_contract_ledger_sha256"),
            bundle_manifest_mismatch=data.get("bundle_manifest_mismatch", False),
            contract_ledger_mismatch=data.get("contract_ledger_mismatch", False),
        )


def compute_file_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        path: Path to file.

    Returns:
        Hash in "SHA256:<hex>" format.

    Raises:
        FileNotFoundError: If file doesn't exist.
        OSError: If file can't be read.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"{HASH_PREFIX}{h.hexdigest()}"


def _get_drift_state_path(institution_id: str) -> Path:
    """Get path to drift state file for institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to ege_drift_state.json file.
    """
    return get_institution_root(institution_id) / DRIFT_STATE_FILE


def load_drift_state(institution_id: str) -> Optional[DriftState]:
    """Load drift state for institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        DriftState if file exists and is valid, None otherwise.
    """
    state_path = _get_drift_state_path(institution_id)

    if not state_path.exists():
        return None

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DriftState.from_dict(data)
    except (json.JSONDecodeError, OSError, TypeError, KeyError):
        return None


def save_drift_state(institution_id: str, state: DriftState) -> None:
    """Save drift state for institution (atomic write).

    Args:
        institution_id: Institution UUID.
        state: DriftState to save.
    """
    state_path = _get_drift_state_path(institution_id)

    # Ensure directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write via temp file
    state_json = json.dumps(state.to_dict(), indent=2)
    fd, temp_path = tempfile.mkstemp(
        dir=state_path.parent,
        prefix=".ege_drift_state_",
        suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(state_json)
        os.replace(temp_path, state_path)
    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _normalize_hash(value: Optional[str]) -> Optional[str]:
    """Normalize hash to canonical format.

    Args:
        value: Hash string or None.

    Returns:
        Normalized hash with SHA256: prefix, or None.
    """
    if value is None:
        return None
    if value.startswith(HASH_PREFIX):
        return value
    return f"{HASH_PREFIX}{value}"


def check_drift(institution_id: str) -> DriftState:
    """Check drift status for an institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        DriftState with current status.

    Behavior:
    - Reads pinned hashes from institution config.
    - If both pinned hashes are None => status=UNPINNED.
    - Resolves CURRENT symlink; if missing => status=UNPINNED.
    - Reads observed hashes from CURRENT/bundle.manifest.json and CURRENT/contract_ledger.json.
    - If pinned present and mismatched => status=ACTIVE.
    - Else => status=CLEAR.
    """
    config = get_effective_config(institution_id)

    # Normalize expected hashes
    expected_manifest = _normalize_hash(config.pinned_bundle_manifest_sha256)
    expected_ledger = _normalize_hash(config.pinned_contract_ledger_sha256)

    # Get bundles root for institution
    bundles_root = get_bundles_root_for_institution(institution_id)
    current_path = bundles_root / "CURRENT"

    # Initialize state
    state = DriftState(
        schema_version=DRIFT_STATE_SCHEMA_VERSION,
        checked_at=datetime.now(timezone.utc).isoformat(),
        expected_bundle_manifest_sha256=expected_manifest,
        expected_contract_ledger_sha256=expected_ledger,
    )

    # If no pinned hashes, status is UNPINNED
    if expected_manifest is None and expected_ledger is None:
        state.status = "UNPINNED"

        # Still try to populate observed hashes if CURRENT exists
        if current_path.exists() and current_path.is_symlink():
            try:
                resolved = current_path.resolve()
                manifest_path = resolved / "bundle.manifest.json"
                ledger_path = resolved / "contract_ledger.json"

                if manifest_path.exists():
                    state.observed_bundle_manifest_sha256 = compute_file_sha256(manifest_path)
                if ledger_path.exists():
                    state.observed_contract_ledger_sha256 = compute_file_sha256(ledger_path)
            except OSError:
                pass

        return state

    # Check if CURRENT symlink exists
    if not current_path.exists():
        # No CURRENT symlink => UNPINNED (not SAFE_MODE, not blocked)
        state.status = "UNPINNED"
        return state

    # Resolve CURRENT and read observed hashes
    try:
        resolved = current_path.resolve()

        manifest_path = resolved / "bundle.manifest.json"
        ledger_path = resolved / "contract_ledger.json"

        # Read observed hashes
        if manifest_path.exists():
            state.observed_bundle_manifest_sha256 = compute_file_sha256(manifest_path)
        if ledger_path.exists():
            state.observed_contract_ledger_sha256 = compute_file_sha256(ledger_path)

    except OSError:
        # Can't read CURRENT => UNPINNED
        state.status = "UNPINNED"
        return state

    # Compare hashes
    if expected_manifest is not None:
        if state.observed_bundle_manifest_sha256 != expected_manifest:
            state.bundle_manifest_mismatch = True

    if expected_ledger is not None:
        if state.observed_contract_ledger_sha256 != expected_ledger:
            state.contract_ledger_mismatch = True

    # Determine status
    if state.bundle_manifest_mismatch or state.contract_ledger_mismatch:
        state.status = "ACTIVE"
    else:
        state.status = "CLEAR"

    return state


def emit_ege_drift_checked(institution_id: str, state: DriftState) -> None:
    """Emit ledger event for drift check.

    Args:
        institution_id: Institution UUID.
        state: DriftState from check.
    """
    try:
        ledger = get_ledger_for_institution(institution_id)

        # Decision: deny if ACTIVE, allow otherwise
        decision = "deny" if state.status == "ACTIVE" else "allow"

        ledger.append(
            event_type="EGE_DRIFT_CHECKED",
            tenant_id=institution_id,
            actor_id="SYSTEM",
            actor_roles=["system"],
            case_id=institution_id,
            step="EGE:drift.check",
            payload={
                "status": state.status,
                "decision": decision,
                "bundle_manifest_mismatch": state.bundle_manifest_mismatch,
                "contract_ledger_mismatch": state.contract_ledger_mismatch,
                "expected_bundle_manifest_sha256": state.expected_bundle_manifest_sha256,
                "expected_contract_ledger_sha256": state.expected_contract_ledger_sha256,
                "observed_bundle_manifest_sha256": state.observed_bundle_manifest_sha256,
                "observed_contract_ledger_sha256": state.observed_contract_ledger_sha256,
            },
        )
    except Exception:
        # Don't fail drift check on ledger write errors
        pass
