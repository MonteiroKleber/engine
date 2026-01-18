"""Tests for EGE Pin management (core/ege_pins.py).

Phase 8.1.1 - Pin on Deploy (Governed)
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.core.ege_pins import (
    get_pin_status,
    create_pin_update_proposal,
    accept_pin_update_proposal,
    block_pin_update_proposal,
    auto_propose_and_accept_pin,
    get_observed_hashes,
    is_pin_update_proposal,
    PROPOSAL_TYPE_PIN_UPDATE,
)
from engine.core.ege_proposals import (
    list_proposals,
    load_current_state,
    reset_proposals_registry,
)
from engine.core.institution_config import (
    InstitutionConfig,
    save_active_config,
    get_effective_config,
    reset_config_cache,
    invalidate_config_cache,
    CONFIG_SCHEMA_VERSION,
)
from engine.core.errors import (
    EGE_PIN_PROPOSAL_NOT_FOUND,
    EGE_PIN_PROPOSAL_WRONG_TYPE,
    EGE_PIN_ALREADY_MATCHED,
    EGE_PIN_CONFIG_UNAVAILABLE,
    EGE_PIN_OBSERVED_UNAVAILABLE,
    EGE_PROPOSAL_ALREADY_DECIDED,
    INSTITUTION_CONFIG_INVALID,
)
from engine.core.ledger import AuditLedger, set_ledger, get_ledger_for_institution
from engine.ise.release import get_bundles_root_for_institution


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path / "bundles"))

    # Set up ledger
    ledger_path = tmp_path / "audit_ledger.jsonl"
    ledger = AuditLedger(ledger_path)
    set_ledger(ledger)

    reset_config_cache()
    reset_proposals_registry()

    yield

    reset_config_cache()
    reset_proposals_registry()
    set_ledger(None)


@pytest.fixture
def institution_id():
    """Test institution ID."""
    return "test-inst-pins-001"


@pytest.fixture
def setup_bundle(institution_id):
    """Set up a bundle with CURRENT symlink for testing.

    Bundles are resolved via:
    get_bundles_root_for_institution() -> resolve_namespaced_path()
    -> <ENGINE_DATA_ROOT>/institutions/<id>/bundles/ (if ENGINE_PROD_BUNDLES_ROOT not set)

    Uses the bundles root function directly to get the right path.
    """
    # Get the bundles root path for this institution
    bundles_root = get_bundles_root_for_institution(institution_id)
    bundles_root.mkdir(parents=True, exist_ok=True)

    # Create a bundle
    bundle_dir = bundles_root / "test-bundle-20240101-120000"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest
    manifest = {
        "name": "test-bundle",
        "version": "1.0.0",
        "created_at": "2024-01-01T12:00:00Z",
    }
    manifest_path = bundle_dir / "bundle.manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)

    # Create contract ledger
    ledger = {"contracts": []}
    ledger_path = bundle_dir / "contract_ledger.json"
    with open(ledger_path, "w") as f:
        json.dump(ledger, f)

    # Create CURRENT symlink
    current_link = bundles_root / "CURRENT"
    if current_link.exists() or current_link.is_symlink():
        current_link.unlink()
    current_link.symlink_to(bundle_dir)

    return {
        "bundles_root": bundles_root,
        "bundle_dir": bundle_dir,
        "manifest_path": manifest_path,
        "ledger_path": ledger_path,
    }


class TestGetPinStatus:
    """Test get_pin_status function."""

    def test_get_pin_status_unpinned(self, institution_id, setup_bundle):
        """Returns UNPINNED when no hashes are pinned."""
        # No config saved = default config with no pinned hashes
        status, error_code, error_msg = get_pin_status(institution_id)

        assert error_code is None
        assert status is not None
        assert status.drift_status == "UNPINNED"
        assert status.pinned_manifest is None
        assert status.pinned_ledger is None
        assert status.observed_manifest is not None

    def test_get_pin_status_clear(self, institution_id, setup_bundle):
        """Returns CLEAR when pinned hashes match observed."""
        # First get the observed hashes
        observed_manifest, observed_ledger = get_observed_hashes(institution_id)

        # Pin them
        config = get_effective_config(institution_id)
        config_dict = config.to_dict()
        config_dict["pinned_bundle_manifest_sha256"] = observed_manifest
        config_dict["pinned_contract_ledger_sha256"] = observed_ledger
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        status, error_code, error_msg = get_pin_status(institution_id)

        assert error_code is None
        assert status.drift_status == "CLEAR"

    def test_get_pin_status_active(self, institution_id, setup_bundle):
        """Returns ACTIVE when pinned hashes differ from observed."""
        # Pin different hashes
        config = get_effective_config(institution_id)
        config_dict = config.to_dict()
        config_dict["pinned_bundle_manifest_sha256"] = "SHA256:" + "a" * 64
        config_dict["pinned_contract_ledger_sha256"] = "SHA256:" + "b" * 64
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        status, error_code, error_msg = get_pin_status(institution_id)

        assert error_code is None
        assert status.drift_status == "ACTIVE"


class TestCreatePinUpdateProposal:
    """Test create_pin_update_proposal function."""

    def test_create_proposal_success(self, institution_id, setup_bundle):
        """Creates proposal when hashes don't match."""
        # No pinned hashes = proposal should succeed
        proposal_id, error_code, error_msg = create_pin_update_proposal(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="test-actor",
        )

        assert error_code is None
        assert proposal_id is not None
        assert is_pin_update_proposal(institution_id, proposal_id)

    def test_create_proposal_fails_when_matched(self, institution_id, setup_bundle):
        """Fails with EGE_PIN_ALREADY_MATCHED when hashes match."""
        # First get the observed hashes and pin them
        observed_manifest, observed_ledger = get_observed_hashes(institution_id)

        config = get_effective_config(institution_id)
        config_dict = config.to_dict()
        config_dict["pinned_bundle_manifest_sha256"] = observed_manifest
        config_dict["pinned_contract_ledger_sha256"] = observed_ledger
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        proposal_id, error_code, error_msg = create_pin_update_proposal(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="test-actor",
        )

        assert proposal_id is None
        assert error_code == EGE_PIN_ALREADY_MATCHED

    def test_create_proposal_emits_ledger_event(self, institution_id, setup_bundle):
        """Creates EGE_PIN_PROPOSAL_CREATED ledger event."""
        create_pin_update_proposal(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="test-actor",
        )

        ledger = get_ledger_for_institution(institution_id)
        if ledger._path.exists():
            with open(ledger._path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

            created_events = [
                e for e in events if e.get("event_type") == "EGE_PIN_PROPOSAL_CREATED"
            ]
            assert len(created_events) >= 1


class TestAcceptPinUpdateProposal:
    """Test accept_pin_update_proposal function."""

    def test_accept_proposal_updates_config(self, institution_id, setup_bundle):
        """Accepting proposal updates config with observed hashes."""
        # Get observed hashes before creating proposal
        observed_manifest, observed_ledger = get_observed_hashes(institution_id)

        # Create proposal
        proposal_id, _, _ = create_pin_update_proposal(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="test-actor",
        )

        # Accept proposal
        result, error_code, error_msg = accept_pin_update_proposal(
            institution_id=institution_id,
            proposal_id=proposal_id,
            actor_id="test-actor",
        )

        assert error_code is None
        assert result is not None
        assert result["status"] == "accepted"

        # Verify config was updated
        invalidate_config_cache(institution_id)
        config = get_effective_config(institution_id)
        assert config.pinned_bundle_manifest_sha256 == observed_manifest
        assert config.pinned_contract_ledger_sha256 == observed_ledger

    def test_accept_proposal_emits_ledger_event(self, institution_id, setup_bundle):
        """Accepting proposal emits EGE_PIN_PROPOSAL_ACCEPTED event."""
        proposal_id, _, _ = create_pin_update_proposal(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="test-actor",
        )

        accept_pin_update_proposal(
            institution_id=institution_id,
            proposal_id=proposal_id,
            actor_id="test-actor",
        )

        ledger = get_ledger_for_institution(institution_id)
        if ledger._path.exists():
            with open(ledger._path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

            accepted_events = [
                e for e in events if e.get("event_type") == "EGE_PIN_PROPOSAL_ACCEPTED"
            ]
            assert len(accepted_events) >= 1

    def test_accept_proposal_not_found(self, institution_id):
        """Returns EGE_PIN_PROPOSAL_NOT_FOUND for unknown proposal."""
        result, error_code, error_msg = accept_pin_update_proposal(
            institution_id=institution_id,
            proposal_id="nonexistent-id",
            actor_id="test-actor",
        )

        assert result is None
        assert error_code == EGE_PIN_PROPOSAL_NOT_FOUND


class TestBlockPinUpdateProposal:
    """Test block_pin_update_proposal function."""

    def test_block_proposal_does_not_update_config(self, institution_id, setup_bundle):
        """Blocking proposal does NOT update config."""
        # Create proposal
        proposal_id, _, _ = create_pin_update_proposal(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="test-actor",
        )

        # Get config before blocking
        config_before = get_effective_config(institution_id)
        pinned_before = config_before.pinned_bundle_manifest_sha256

        # Block proposal
        result, error_code, error_msg = block_pin_update_proposal(
            institution_id=institution_id,
            proposal_id=proposal_id,
            actor_id="test-actor",
            reason="Test block",
        )

        assert error_code is None
        assert result is not None
        assert result["status"] == "blocked"

        # Verify config was NOT updated
        invalidate_config_cache(institution_id)
        config_after = get_effective_config(institution_id)
        assert config_after.pinned_bundle_manifest_sha256 == pinned_before

    def test_block_proposal_emits_ledger_event(self, institution_id, setup_bundle):
        """Blocking proposal emits EGE_PIN_PROPOSAL_BLOCKED event."""
        proposal_id, _, _ = create_pin_update_proposal(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="test-actor",
        )

        block_pin_update_proposal(
            institution_id=institution_id,
            proposal_id=proposal_id,
            actor_id="test-actor",
            reason="Test block",
        )

        ledger = get_ledger_for_institution(institution_id)
        if ledger._path.exists():
            with open(ledger._path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

            blocked_events = [
                e for e in events if e.get("event_type") == "EGE_PIN_PROPOSAL_BLOCKED"
            ]
            assert len(blocked_events) >= 1

    def test_block_proposal_already_decided(self, institution_id, setup_bundle):
        """Returns EGE_PROPOSAL_ALREADY_DECIDED for already decided proposal."""
        proposal_id, _, _ = create_pin_update_proposal(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="test-actor",
        )

        # Accept it first
        accept_pin_update_proposal(
            institution_id=institution_id,
            proposal_id=proposal_id,
            actor_id="test-actor",
        )

        # Try to block
        result, error_code, error_msg = block_pin_update_proposal(
            institution_id=institution_id,
            proposal_id=proposal_id,
            actor_id="test-actor",
        )

        assert result is None
        assert error_code == EGE_PROPOSAL_ALREADY_DECIDED


class TestAutoProposeAndAcceptPin:
    """Test auto_propose_and_accept_pin function."""

    def test_auto_propose_creates_proposal(self, institution_id, setup_bundle):
        """Creates proposal when auto_propose is True (default)."""
        # Default config has auto_propose_pin_on_deploy=True, auto_accept_pin_on_deploy=False
        proposal_id, error_code, error_msg = auto_propose_and_accept_pin(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="SYSTEM",
        )

        assert error_code is None
        assert proposal_id is not None

        # Verify proposal is OPEN (not auto-accepted)
        states = load_current_state(institution_id)
        assert proposal_id in states
        assert states[proposal_id].status == "OPEN"

    def test_auto_propose_disabled(self, institution_id, setup_bundle):
        """Does nothing when auto_propose is False."""
        # Disable auto_propose
        config = get_effective_config(institution_id)
        config_dict = config.to_dict()
        config_dict["auto_propose_pin_on_deploy"] = False
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        proposal_id, error_code, error_msg = auto_propose_and_accept_pin(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="SYSTEM",
        )

        assert error_code is None
        assert proposal_id is None

    def test_auto_accept_accepts_immediately(self, institution_id, setup_bundle):
        """Auto-accepts proposal when auto_accept is True."""
        # Enable auto_accept
        config = get_effective_config(institution_id)
        config_dict = config.to_dict()
        config_dict["auto_propose_pin_on_deploy"] = True
        config_dict["auto_accept_pin_on_deploy"] = True
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        # Get observed hashes before
        observed_manifest, observed_ledger = get_observed_hashes(institution_id)

        proposal_id, error_code, error_msg = auto_propose_and_accept_pin(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="SYSTEM",
        )

        assert error_code is None
        assert proposal_id is not None

        # Verify proposal is DECIDED (auto-accepted)
        states = load_current_state(institution_id)
        assert proposal_id in states
        assert states[proposal_id].status == "DECIDED"
        assert states[proposal_id].decision == "accept"

        # Verify config was updated
        invalidate_config_cache(institution_id)
        config = get_effective_config(institution_id)
        assert config.pinned_bundle_manifest_sha256 == observed_manifest

    def test_auto_accept_emits_ledger_event(self, institution_id, setup_bundle):
        """Emits EGE_PIN_AUTO_ACCEPTED when auto-accepting."""
        config = get_effective_config(institution_id)
        config_dict = config.to_dict()
        config_dict["auto_propose_pin_on_deploy"] = True
        config_dict["auto_accept_pin_on_deploy"] = True
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        auto_propose_and_accept_pin(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="SYSTEM",
        )

        ledger = get_ledger_for_institution(institution_id)
        if ledger._path.exists():
            with open(ledger._path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

            auto_events = [
                e for e in events if e.get("event_type") == "EGE_PIN_AUTO_ACCEPTED"
            ]
            assert len(auto_events) >= 1

    def test_already_matched_is_idempotent(self, institution_id, setup_bundle):
        """Returns success (None, None, None) when already matched."""
        # Pin current hashes
        observed_manifest, observed_ledger = get_observed_hashes(institution_id)
        config = get_effective_config(institution_id)
        config_dict = config.to_dict()
        config_dict["pinned_bundle_manifest_sha256"] = observed_manifest
        config_dict["pinned_contract_ledger_sha256"] = observed_ledger
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        proposal_id, error_code, error_msg = auto_propose_and_accept_pin(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="SYSTEM",
        )

        # Should return None, None, None (idempotent success)
        assert proposal_id is None
        assert error_code is None
        assert error_msg is None


class TestConfigValidation:
    """Test config validation for auto_accept requires auto_propose."""

    def test_auto_accept_requires_auto_propose(self, institution_id):
        """Config validation fails if auto_accept=True but auto_propose=False."""
        config_dict = {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "auto_propose_pin_on_deploy": False,
            "auto_accept_pin_on_deploy": True,
        }

        # This should fail validation
        from engine.core.institution_config import _validate_config

        valid, error_code, error_msg = _validate_config(config_dict)

        assert not valid
        assert error_code == INSTITUTION_CONFIG_INVALID
        assert "auto_accept_pin_on_deploy requires auto_propose_pin_on_deploy" in error_msg

    def test_valid_config_with_both_true(self, institution_id):
        """Config is valid when both auto_accept and auto_propose are True."""
        config_dict = {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "auto_propose_pin_on_deploy": True,
            "auto_accept_pin_on_deploy": True,
        }

        from engine.core.institution_config import _validate_config

        valid, error_code, error_msg = _validate_config(config_dict)

        assert valid
        assert error_code is None


class TestPinProposalsNotInDriftList:
    """Test that PIN_UPDATE proposals are distinguishable from drift proposals."""

    def test_pin_proposal_marked_as_pin_type(self, institution_id, setup_bundle):
        """PIN_UPDATE proposals can be identified by type."""
        proposal_id, _, _ = create_pin_update_proposal(
            institution_id=institution_id,
            release_id="20240101-120000",
            bundle_name="test-bundle",
            actor_id="test-actor",
        )

        assert is_pin_update_proposal(institution_id, proposal_id)

    def test_drift_proposal_not_pin_type(self, institution_id, setup_bundle):
        """Drift resolution proposals are NOT PIN_UPDATE type."""
        from engine.core.ege import DriftState, save_drift_state
        from engine.core.ege_proposals import create_drift_resolution_proposal

        # Create drift state
        drift_state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
            expected_contract_ledger_sha256="SHA256:" + "b" * 64,
            observed_bundle_manifest_sha256="SHA256:" + "c" * 64,
            observed_contract_ledger_sha256="SHA256:" + "d" * 64,
            bundle_manifest_mismatch=True,
            contract_ledger_mismatch=True,
        )
        save_drift_state(institution_id, drift_state)

        # Create drift resolution proposal
        proposal, _, _ = create_drift_resolution_proposal(institution_id, drift_state)

        assert proposal is not None
        assert not is_pin_update_proposal(institution_id, proposal.proposal_id)
