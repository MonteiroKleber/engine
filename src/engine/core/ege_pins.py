"""EGE Pin management - PIN_UPDATE proposal workflow.

Implements deterministic pin update proposals for bundle deployments.
Uses the existing append-only proposals registry for storage.
"""

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from engine.core.data_root import get_institution_root
from engine.core.ege import compute_file_sha256, check_drift, DriftState
from engine.core.ege_proposals import (
    ProposalRecord,
    ProposalState,
    load_current_state,
    _get_file_lock,
    _get_next_seq,
    _get_proposals_path,
    _now_iso,
)
from engine.core.institution_config import (
    get_effective_config,
    save_active_config,
    invalidate_config_cache,
    HASH_PREFIX,
)
from engine.core.ledger import get_ledger_for_institution
from engine.core.errors import (
    EGE_PIN_PROPOSAL_NOT_FOUND,
    EGE_PIN_PROPOSAL_WRONG_TYPE,
    EGE_PIN_ALREADY_MATCHED,
    EGE_PIN_CONFIG_UNAVAILABLE,
    EGE_PIN_OBSERVED_UNAVAILABLE,
    EGE_REGISTRY_UNAVAILABLE,
    EGE_PROPOSAL_ALREADY_DECIDED,
)
from engine.ise.release import get_bundles_root_for_institution


# Proposal type for PIN_UPDATE
PROPOSAL_TYPE_PIN_UPDATE = "PIN_UPDATE"


@dataclass
class PinProposalPayload:
    """Payload for PIN_UPDATE proposal."""

    release_id: str
    bundle_name: str
    observed_bundle_manifest_sha256: str
    observed_contract_ledger_sha256: Optional[str]
    previous_pinned_bundle_manifest_sha256: Optional[str]
    previous_pinned_contract_ledger_sha256: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class PinStatus:
    """Status of pinned vs observed hashes."""

    pinned_manifest: Optional[str]
    pinned_ledger: Optional[str]
    observed_manifest: Optional[str]
    observed_ledger: Optional[str]
    drift_status: str  # CLEAR, ACTIVE, or UNPINNED

    @property
    def pinned(self) -> Dict[str, Optional[str]]:
        """Get pinned hashes as dict."""
        return {
            "bundle_manifest_sha256": self.pinned_manifest,
            "contract_ledger_sha256": self.pinned_ledger,
        }

    @property
    def observed(self) -> Dict[str, Optional[str]]:
        """Get observed hashes as dict."""
        return {
            "bundle_manifest_sha256": self.observed_manifest,
            "contract_ledger_sha256": self.observed_ledger,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pinned": self.pinned,
            "observed": self.observed,
            "drift": {
                "status": self.drift_status,
            },
        }


def get_observed_hashes(institution_id: str) -> Tuple[str, Optional[str]]:
    """Get observed hashes from CURRENT bundle.

    Reads CURRENT symlink for institution, locates bundle.manifest.json
    and contract_ledger.json, computes SHA256 hashes.

    Args:
        institution_id: Institution UUID.

    Returns:
        Tuple of (manifest_sha256, ledger_sha256).
        Ledger may be None if file doesn't exist.

    Raises:
        ValueError: If cannot read CURRENT bundle (with EGE_PIN_OBSERVED_UNAVAILABLE code).
    """
    bundles_root = get_bundles_root_for_institution(institution_id)
    current_path = bundles_root / "CURRENT"

    if not current_path.exists():
        raise ValueError(f"{EGE_PIN_OBSERVED_UNAVAILABLE}:CURRENT symlink not found")

    if not current_path.is_symlink():
        raise ValueError(f"{EGE_PIN_OBSERVED_UNAVAILABLE}:CURRENT is not a symlink")

    try:
        resolved = current_path.resolve()

        manifest_path = resolved / "bundle.manifest.json"
        if not manifest_path.exists():
            raise ValueError(f"{EGE_PIN_OBSERVED_UNAVAILABLE}:bundle.manifest.json not found")

        manifest_sha = compute_file_sha256(manifest_path)

        ledger_path = resolved / "contract_ledger.json"
        ledger_sha = None
        if ledger_path.exists():
            ledger_sha = compute_file_sha256(ledger_path)

        return manifest_sha, ledger_sha

    except OSError as e:
        raise ValueError(f"{EGE_PIN_OBSERVED_UNAVAILABLE}:Failed to read CURRENT bundle: {e}")


def get_pin_status(
    institution_id: str,
) -> Tuple[Optional[PinStatus], Optional[str], Optional[str]]:
    """Get pin status comparing pinned and observed hashes.

    Args:
        institution_id: Institution UUID.

    Returns:
        Tuple of (PinStatus, error_code, error_message).
        On success: (PinStatus, None, None)
        On failure: (None, error_code, error_message)
    """
    try:
        config = get_effective_config(institution_id)
    except Exception as e:
        return None, EGE_PIN_CONFIG_UNAVAILABLE, f"Failed to read config: {e}"

    pinned_manifest = config.pinned_bundle_manifest_sha256
    pinned_ledger = config.pinned_contract_ledger_sha256

    # Get observed hashes (may raise)
    try:
        observed_manifest, observed_ledger = get_observed_hashes(institution_id)
    except ValueError as e:
        error_msg = str(e)
        if error_msg.startswith(EGE_PIN_OBSERVED_UNAVAILABLE):
            return None, EGE_PIN_OBSERVED_UNAVAILABLE, error_msg.split(":", 1)[1] if ":" in error_msg else error_msg
        return None, EGE_PIN_OBSERVED_UNAVAILABLE, str(e)

    # Compute drift status using existing check_drift
    drift_state = check_drift(institution_id)

    return PinStatus(
        pinned_manifest=pinned_manifest,
        pinned_ledger=pinned_ledger,
        observed_manifest=observed_manifest,
        observed_ledger=observed_ledger,
        drift_status=drift_state.status,
    ), None, None


def _normalize_hash(value: Optional[str]) -> Optional[str]:
    """Normalize hash to canonical format."""
    if value is None:
        return None
    if value.startswith(HASH_PREFIX):
        return value
    return f"{HASH_PREFIX}{value}"


def _emit_pin_event(
    institution_id: str,
    event_type: str,
    proposal_id: str,
    payload: Dict[str, Any],
) -> None:
    """Emit ledger event for pin operation.

    Args:
        institution_id: Institution UUID.
        event_type: Event type (EGE_PIN_PROPOSAL_CREATED, etc).
        proposal_id: Proposal UUID.
        payload: Event payload.
    """
    try:
        ledger = get_ledger_for_institution(institution_id)

        step_map = {
            "EGE_PIN_PROPOSAL_CREATED": "EGE:pin.propose",
            "EGE_PIN_PROPOSAL_ACCEPTED": "EGE:pin.accept",
            "EGE_PIN_PROPOSAL_BLOCKED": "EGE:pin.block",
            "EGE_PIN_AUTO_ACCEPTED": "EGE:pin.auto_accept",
        }
        step = step_map.get(event_type, "EGE:pin.unknown")

        ledger.append(
            event_type=event_type,
            tenant_id=institution_id,
            actor_id=payload.get("actor_id", "SYSTEM"),
            actor_roles=["admin"],
            case_id=proposal_id,
            step=step,
            payload=payload,
        )
    except Exception:
        # Don't fail on ledger write errors
        pass


def create_pin_update_proposal(
    institution_id: str,
    release_id: str,
    bundle_name: str,
    actor_id: str = "SYSTEM",
    request_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Create a PIN_UPDATE proposal.

    Args:
        institution_id: Institution UUID.
        release_id: Release ID (e.g., YYYYMMDD-HHMMSS).
        bundle_name: Name of the deployed bundle.
        actor_id: Actor creating the proposal.
        request_id: Optional request ID for tracing.

    Returns:
        Tuple of (proposal_id, error_code, error_message).
        On success: (proposal_id, None, None)
        On failure: (None, error_code, error_message)
    """
    # Get config for previous pinned hashes
    try:
        config = get_effective_config(institution_id)
        previous_pinned_manifest = config.pinned_bundle_manifest_sha256
        previous_pinned_ledger = config.pinned_contract_ledger_sha256
    except Exception as e:
        return None, EGE_PIN_CONFIG_UNAVAILABLE, f"Failed to read config: {e}"

    # Get observed hashes
    try:
        observed_manifest, observed_ledger = get_observed_hashes(institution_id)
    except ValueError as e:
        error_msg = str(e)
        if error_msg.startswith(EGE_PIN_OBSERVED_UNAVAILABLE):
            return None, EGE_PIN_OBSERVED_UNAVAILABLE, error_msg.split(":", 1)[1] if ":" in error_msg else error_msg
        return None, EGE_PIN_OBSERVED_UNAVAILABLE, str(e)

    # Normalize hashes for comparison
    norm_observed_manifest = _normalize_hash(observed_manifest)
    norm_observed_ledger = _normalize_hash(observed_ledger)
    norm_pinned_manifest = _normalize_hash(previous_pinned_manifest)
    norm_pinned_ledger = _normalize_hash(previous_pinned_ledger)

    # Check if hashes already match - return EGE_PIN_ALREADY_MATCHED
    manifest_match = norm_observed_manifest == norm_pinned_manifest
    ledger_match = norm_observed_ledger == norm_pinned_ledger or (norm_observed_ledger is None and norm_pinned_ledger is None)

    if manifest_match and ledger_match:
        return None, EGE_PIN_ALREADY_MATCHED, "Observed hashes already match pinned hashes"

    lock = _get_file_lock(institution_id)

    with lock:
        proposal_id = str(uuid.uuid4())
        seq = _get_next_seq(institution_id)
        now = _now_iso()

        # Create proposal record with PIN_UPDATE type in the record
        # Store type and payload in the observed/expected fields plus use a marker
        record = ProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation="create",
            status="OPEN",
            created_at=now,
            # Store observed hashes
            observed_bundle_manifest_sha256=observed_manifest,
            observed_contract_ledger_sha256=observed_ledger,
            # Store previous pinned as "expected" for consistency
            expected_bundle_manifest_sha256=previous_pinned_manifest,
            expected_contract_ledger_sha256=previous_pinned_ledger,
        )

        try:
            proposals_path = _get_proposals_path(institution_id)
            proposals_path.parent.mkdir(parents=True, exist_ok=True)

            with open(proposals_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except OSError as e:
            return None, EGE_REGISTRY_UNAVAILABLE, f"Failed to write proposal: {e}"

    # Store PIN_UPDATE metadata in a separate JSONL for tracking
    # This uses a simple metadata store alongside the proposal
    _store_pin_proposal_metadata(
        institution_id=institution_id,
        proposal_id=proposal_id,
        release_id=release_id,
        bundle_name=bundle_name,
    )

    # Emit ledger event
    _emit_pin_event(
        institution_id=institution_id,
        event_type="EGE_PIN_PROPOSAL_CREATED",
        proposal_id=proposal_id,
        payload={
            "proposal_id": proposal_id,
            "proposal_type": PROPOSAL_TYPE_PIN_UPDATE,
            "release_id": release_id,
            "bundle_name": bundle_name,
            "observed_bundle_manifest_sha256": observed_manifest,
            "observed_contract_ledger_sha256": observed_ledger,
            "previous_pinned_bundle_manifest_sha256": previous_pinned_manifest,
            "previous_pinned_contract_ledger_sha256": previous_pinned_ledger,
            "actor_id": actor_id,
        },
    )

    return proposal_id, None, None


def _get_pin_metadata_path(institution_id: str) -> Path:
    """Get path to pin proposals metadata file."""
    return get_institution_root(institution_id) / "ege_pin_proposals.jsonl"


def _store_pin_proposal_metadata(
    institution_id: str,
    proposal_id: str,
    release_id: str,
    bundle_name: str,
) -> None:
    """Store PIN_UPDATE proposal metadata.

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID.
        release_id: Release ID.
        bundle_name: Bundle name.
    """
    metadata_path = _get_pin_metadata_path(institution_id)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = {
        "proposal_id": proposal_id,
        "proposal_type": PROPOSAL_TYPE_PIN_UPDATE,
        "release_id": release_id,
        "bundle_name": bundle_name,
        "created_at": _now_iso(),
    }

    with open(metadata_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(metadata) + "\n")


def _load_pin_proposal_metadata(institution_id: str) -> Dict[str, Dict[str, Any]]:
    """Load PIN_UPDATE proposal metadata.

    Returns:
        Dictionary mapping proposal_id to metadata.
    """
    metadata_path = _get_pin_metadata_path(institution_id)

    if not metadata_path.exists():
        return {}

    metadata = {}
    with open(metadata_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    proposal_id = entry.get("proposal_id")
                    if proposal_id:
                        metadata[proposal_id] = entry
                except json.JSONDecodeError:
                    continue

    return metadata


def is_pin_update_proposal(institution_id: str, proposal_id: str) -> bool:
    """Check if a proposal is a PIN_UPDATE type.

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID.

    Returns:
        True if proposal is PIN_UPDATE type.
    """
    metadata = _load_pin_proposal_metadata(institution_id)
    return proposal_id in metadata


def get_pin_proposal_metadata(
    institution_id: str,
    proposal_id: str,
) -> Optional[Dict[str, Any]]:
    """Get metadata for a PIN_UPDATE proposal.

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID.

    Returns:
        Metadata dict or None if not found.
    """
    metadata = _load_pin_proposal_metadata(institution_id)
    return metadata.get(proposal_id)


def accept_pin_update_proposal(
    institution_id: str,
    proposal_id: str,
    actor_id: str = "SYSTEM",
    request_id: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """Accept a PIN_UPDATE proposal, updating pinned hashes in config.

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID.
        actor_id: Actor accepting the proposal.
        request_id: Optional request ID for tracing.

    Returns:
        Tuple of (result_dict, error_code, error_message).
        On success: ({"proposal_id": ..., "status": "accepted", "pinned_after": {...}}, None, None)
        On failure: (None, error_code, error_message)
    """
    # Verify proposal exists
    states = load_current_state(institution_id)
    if proposal_id not in states:
        return None, EGE_PIN_PROPOSAL_NOT_FOUND, f"Proposal '{proposal_id}' not found"

    proposal = states[proposal_id]

    # Verify it's a PIN_UPDATE type
    if not is_pin_update_proposal(institution_id, proposal_id):
        return None, EGE_PIN_PROPOSAL_WRONG_TYPE, f"Proposal '{proposal_id}' is not a PIN_UPDATE type"

    # Verify not already decided
    if proposal.status == "DECIDED":
        return None, EGE_PROPOSAL_ALREADY_DECIDED, f"Proposal '{proposal_id}' is already decided"

    # Get metadata
    metadata = get_pin_proposal_metadata(institution_id, proposal_id)

    lock = _get_file_lock(institution_id)

    with lock:
        now = _now_iso()
        seq = _get_next_seq(institution_id)

        # Create decide record
        record = ProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation="decide",
            status="DECIDED",
            created_at=proposal.created_at,
            expected_bundle_manifest_sha256=proposal.expected_bundle_manifest_sha256,
            expected_contract_ledger_sha256=proposal.expected_contract_ledger_sha256,
            observed_bundle_manifest_sha256=proposal.observed_bundle_manifest_sha256,
            observed_contract_ledger_sha256=proposal.observed_contract_ledger_sha256,
            decision="accept",
            reason="PIN_UPDATE accepted",
            decided_at=now,
            decider_actor_id=actor_id,
        )

        try:
            proposals_path = _get_proposals_path(institution_id)
            proposals_path.parent.mkdir(parents=True, exist_ok=True)

            with open(proposals_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except OSError as e:
            return None, EGE_REGISTRY_UNAVAILABLE, f"Failed to write decision: {e}"

    # Update institution config with observed hashes
    try:
        config = get_effective_config(institution_id)
        config_dict = config.to_dict()
        config_dict["pinned_bundle_manifest_sha256"] = proposal.observed_bundle_manifest_sha256
        config_dict["pinned_contract_ledger_sha256"] = proposal.observed_contract_ledger_sha256

        save_active_config(institution_id, config_dict, actor_id)
        invalidate_config_cache(institution_id)
    except Exception as e:
        return None, EGE_PIN_CONFIG_UNAVAILABLE, f"Failed to update config: {e}"

    # Get the new pinned values
    pinned_after = {
        "bundle_manifest_sha256": proposal.observed_bundle_manifest_sha256,
        "contract_ledger_sha256": proposal.observed_contract_ledger_sha256,
    }

    # Emit ledger event
    _emit_pin_event(
        institution_id=institution_id,
        event_type="EGE_PIN_PROPOSAL_ACCEPTED",
        proposal_id=proposal_id,
        payload={
            "proposal_id": proposal_id,
            "release_id": metadata.get("release_id") if metadata else None,
            "observed_bundle_manifest_sha256": proposal.observed_bundle_manifest_sha256,
            "observed_contract_ledger_sha256": proposal.observed_contract_ledger_sha256,
            "pinned_before": {
                "bundle_manifest_sha256": proposal.expected_bundle_manifest_sha256,
                "contract_ledger_sha256": proposal.expected_contract_ledger_sha256,
            },
            "pinned_after": pinned_after,
            "actor_id": actor_id,
        },
    )

    return {
        "proposal_id": proposal_id,
        "status": "accepted",
        "pinned_after": pinned_after,
    }, None, None


def block_pin_update_proposal(
    institution_id: str,
    proposal_id: str,
    actor_id: str = "SYSTEM",
    request_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """Block a PIN_UPDATE proposal (does not update config).

    Args:
        institution_id: Institution UUID.
        proposal_id: Proposal UUID.
        actor_id: Actor blocking the proposal.
        request_id: Optional request ID for tracing.
        reason: Optional reason for blocking.

    Returns:
        Tuple of (result_dict, error_code, error_message).
        On success: ({"proposal_id": ..., "status": "blocked"}, None, None)
        On failure: (None, error_code, error_message)
    """
    # Verify proposal exists
    states = load_current_state(institution_id)
    if proposal_id not in states:
        return None, EGE_PIN_PROPOSAL_NOT_FOUND, f"Proposal '{proposal_id}' not found"

    proposal = states[proposal_id]

    # Verify it's a PIN_UPDATE type
    if not is_pin_update_proposal(institution_id, proposal_id):
        return None, EGE_PIN_PROPOSAL_WRONG_TYPE, f"Proposal '{proposal_id}' is not a PIN_UPDATE type"

    # Verify not already decided
    if proposal.status == "DECIDED":
        return None, EGE_PROPOSAL_ALREADY_DECIDED, f"Proposal '{proposal_id}' is already decided"

    # Get metadata
    metadata = get_pin_proposal_metadata(institution_id, proposal_id)

    lock = _get_file_lock(institution_id)

    with lock:
        now = _now_iso()
        seq = _get_next_seq(institution_id)

        # Create decide record
        record = ProposalRecord(
            seq=seq,
            proposal_id=proposal_id,
            operation="decide",
            status="DECIDED",
            created_at=proposal.created_at,
            expected_bundle_manifest_sha256=proposal.expected_bundle_manifest_sha256,
            expected_contract_ledger_sha256=proposal.expected_contract_ledger_sha256,
            observed_bundle_manifest_sha256=proposal.observed_bundle_manifest_sha256,
            observed_contract_ledger_sha256=proposal.observed_contract_ledger_sha256,
            decision="block",
            reason=reason or "PIN_UPDATE blocked",
            decided_at=now,
            decider_actor_id=actor_id,
        )

        try:
            proposals_path = _get_proposals_path(institution_id)
            proposals_path.parent.mkdir(parents=True, exist_ok=True)

            with open(proposals_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except OSError as e:
            return None, EGE_REGISTRY_UNAVAILABLE, f"Failed to write decision: {e}"

    # Emit ledger event
    _emit_pin_event(
        institution_id=institution_id,
        event_type="EGE_PIN_PROPOSAL_BLOCKED",
        proposal_id=proposal_id,
        payload={
            "proposal_id": proposal_id,
            "release_id": metadata.get("release_id") if metadata else None,
            "observed_bundle_manifest_sha256": proposal.observed_bundle_manifest_sha256,
            "observed_contract_ledger_sha256": proposal.observed_contract_ledger_sha256,
            "reason": reason,
            "actor_id": actor_id,
        },
    )

    return {
        "proposal_id": proposal_id,
        "status": "blocked",
    }, None, None


def auto_propose_and_accept_pin(
    institution_id: str,
    release_id: str,
    bundle_name: str,
    actor_id: str = "SYSTEM",
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Auto-propose and optionally auto-accept pin update after deploy.

    Called after DEPLOYED status. Checks institution config:
    - If auto_propose_pin_on_deploy == True: creates PIN_UPDATE proposal
    - If auto_accept_pin_on_deploy == True: immediately accepts it

    Args:
        institution_id: Institution UUID.
        release_id: Release ID.
        bundle_name: Bundle name.
        actor_id: Actor ID.

    Returns:
        Tuple of (proposal_id, error_code, error_message).
        On success: (proposal_id, None, None)
        On EGE_PIN_ALREADY_MATCHED: (None, None, None) - idempotent
        On failure: (None, error_code, error_message)
    """
    config = get_effective_config(institution_id)

    # If auto_propose disabled, do nothing
    if not config.auto_propose_pin_on_deploy:
        return None, None, None

    # Create proposal
    proposal_id, error_code, error_message = create_pin_update_proposal(
        institution_id=institution_id,
        release_id=release_id,
        bundle_name=bundle_name,
        actor_id=actor_id,
    )

    # If already matched, return success (idempotent)
    if error_code == EGE_PIN_ALREADY_MATCHED:
        return None, None, None

    if error_code:
        return None, error_code, error_message

    # If auto_accept enabled, accept immediately
    if config.auto_accept_pin_on_deploy:
        result, err_code, err_msg = accept_pin_update_proposal(
            institution_id=institution_id,
            proposal_id=proposal_id,
            actor_id=actor_id,
        )

        if err_code:
            return proposal_id, err_code, err_msg

        # Emit auto-accept event
        _emit_pin_event(
            institution_id=institution_id,
            event_type="EGE_PIN_AUTO_ACCEPTED",
            proposal_id=proposal_id,
            payload={
                "proposal_id": proposal_id,
                "release_id": release_id,
                "bundle_name": bundle_name,
                "observed_bundle_manifest_sha256": result.get("pinned_after", {}).get("bundle_manifest_sha256") if result else None,
                "observed_contract_ledger_sha256": result.get("pinned_after", {}).get("contract_ledger_sha256") if result else None,
                "actor_id": actor_id,
            },
        )

    return proposal_id, None, None
