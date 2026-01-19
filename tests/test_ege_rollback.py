"""Tests for EGE Governed Rollback (Etapa 2.4).

Tests:
- Rollback to pinned release on deploy failure
- SAFE_MODE activation when no pinned release exists
- Rollback blocked by freeze/emergency
- Audit events emitted correctly
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.core.ege_rollback import (
    execute_governed_rollback,
    get_pinned_release_path,
    check_rollback_blocked,
    get_current_release_id,
    RollbackResult,
)
from engine.core.institution_config import (
    InstitutionConfig,
    save_active_config,
    get_effective_config,
    reset_config_cache,
    invalidate_config_cache,
)
from engine.core.runtime_state import runtime_state, RuntimeMode
from engine.core.errors import (
    EGE_ROLLBACK_NO_PINNED_RELEASE,
    EGE_ROLLBACK_PINNED_RELEASE_MISSING,
    EGE_ROLLBACK_BLOCKED_FROZEN,
    EGE_ROLLBACK_BLOCKED_EMERGENCY,
)
from engine.core.ledger import AuditLedger, set_ledger
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

    # Reset runtime state
    runtime_state.set_active()
    reset_config_cache()

    yield

    runtime_state.set_active()
    reset_config_cache()
    set_ledger(None)


@pytest.fixture
def institution_id():
    """Test institution ID."""
    return "test-inst-rollback-001"


@pytest.fixture
def setup_pinned_release(institution_id):
    """Set up a pinned release for testing.

    Creates:
    - releases/20260101-120000/finance-pilot/ with valid manifest
    - CURRENT symlink pointing to it
    - Config with pinned_release_id set
    """
    bundles_root = get_bundles_root_for_institution(institution_id)
    bundles_root.mkdir(parents=True, exist_ok=True)

    # Create releases directory
    releases_dir = bundles_root / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)

    # Create pinned release
    release_id = "20260101-120000"
    release_dir = releases_dir / release_id
    bundle_dir = release_dir / "finance-pilot"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest
    manifest = {
        "name": "finance-pilot",
        "version": "1.0.0",
        "created_at": "2026-01-01T12:00:00Z",
        "contracts": [],
    }
    manifest_path = bundle_dir / "bundle.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Create ledger
    ledger = {
        "ledger_version": "1.0",
        "bundle_name": "finance-pilot",
        "contracts": [],
    }
    ledger_path = bundle_dir / "contract_ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2))

    # Create CURRENT symlink
    current_link = bundles_root / "CURRENT"
    if current_link.exists() or current_link.is_symlink():
        current_link.unlink()
    current_link.symlink_to(bundle_dir)

    # Compute manifest hash
    import hashlib
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ledger_hash = hashlib.sha256(ledger_path.read_bytes()).hexdigest()

    # Set up config with pinned release
    config_dict = {
        "pinned_release_id": release_id,
        "pinned_bundle_manifest_sha256": manifest_hash,
        "pinned_contract_ledger_sha256": ledger_hash,
    }
    save_active_config(institution_id, config_dict, "test")
    invalidate_config_cache(institution_id)

    return {
        "release_id": release_id,
        "bundle_path": bundle_dir,
        "manifest_hash": manifest_hash,
        "ledger_hash": ledger_hash,
        "bundles_root": bundles_root,
    }


class TestGetPinnedReleasePath:
    """Tests for get_pinned_release_path()."""

    def test_returns_path_when_pinned_release_id_set(self, institution_id, setup_pinned_release):
        """Should return path when pinned_release_id is configured."""
        path, error_code, error_message = get_pinned_release_path(institution_id)

        assert error_code is None
        assert error_message is None
        assert path is not None
        assert path.exists()
        assert path.name == "finance-pilot"

    def test_returns_error_when_no_pin_configured(self, institution_id):
        """Should return error when no pin is configured."""
        # Empty config - no pins
        save_active_config(institution_id, {}, "test")
        invalidate_config_cache(institution_id)

        path, error_code, error_message = get_pinned_release_path(institution_id)

        assert path is None
        assert error_code == EGE_ROLLBACK_NO_PINNED_RELEASE
        assert "No pinned release" in error_message

    def test_returns_error_when_pinned_release_missing(self, institution_id):
        """Should return error when pinned release directory is missing."""
        # Set pinned_release_id to non-existent release
        config_dict = {
            "pinned_release_id": "20260101-999999",
        }
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        path, error_code, error_message = get_pinned_release_path(institution_id)

        assert path is None
        assert error_code == EGE_ROLLBACK_PINNED_RELEASE_MISSING
        assert "not found" in error_message


class TestCheckRollbackBlocked:
    """Tests for check_rollback_blocked()."""

    def test_not_blocked_by_default(self, institution_id):
        """Should not be blocked when no freeze/emergency."""
        save_active_config(institution_id, {}, "test")
        invalidate_config_cache(institution_id)

        is_blocked, error_code, error_message = check_rollback_blocked(institution_id)

        assert is_blocked is False
        assert error_code is None
        assert error_message is None

    def test_blocked_when_frozen(self, institution_id):
        """Should be blocked when institution is frozen."""
        config_dict = {"freeze_mode": True}
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        is_blocked, error_code, error_message = check_rollback_blocked(institution_id)

        assert is_blocked is True
        assert error_code == EGE_ROLLBACK_BLOCKED_FROZEN
        assert "frozen" in error_message

    def test_blocked_when_emergency_stop(self, institution_id):
        """Should be blocked when emergency stop is active."""
        config_dict = {"emergency_stop": {"enabled": True}}
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        is_blocked, error_code, error_message = check_rollback_blocked(institution_id)

        assert is_blocked is True
        assert error_code == EGE_ROLLBACK_BLOCKED_EMERGENCY
        assert "emergency" in error_message


class TestExecuteGovernedRollback:
    """Tests for execute_governed_rollback()."""

    def test_rollback_success_with_pinned_release(self, institution_id, setup_pinned_release):
        """Scenario: exists release pinada A, deploy B fails -> rollback to A."""
        # Create a "failed" release B
        bundles_root = setup_pinned_release["bundles_root"]
        releases_dir = bundles_root / "releases"

        failed_release_id = "20260118-150000"
        failed_dir = releases_dir / failed_release_id / "finance-pilot"
        failed_dir.mkdir(parents=True, exist_ok=True)

        # Point CURRENT to failed release
        current_link = bundles_root / "CURRENT"
        if current_link.exists() or current_link.is_symlink():
            current_link.unlink()
        current_link.symlink_to(failed_dir)

        # Execute rollback
        result = execute_governed_rollback(
            institution_id=institution_id,
            failed_release_id=failed_release_id,
            reason="Deploy failed smoke test",
        )

        # Verify success
        assert result.success is True
        assert result.rolled_back_to == setup_pinned_release["release_id"]
        assert result.previous_release == failed_release_id
        assert result.safe_mode_activated is False

        # Verify CURRENT now points to pinned release
        current_target = current_link.resolve()
        assert current_target == setup_pinned_release["bundle_path"]

        # Verify runtime is still ACTIVE
        assert runtime_state.is_active()

    def test_rollback_activates_safe_mode_when_no_pin(self, institution_id):
        """Scenario: no pinned release -> SAFE_MODE activated."""
        # Empty config - no pins
        save_active_config(institution_id, {}, "test")
        invalidate_config_cache(institution_id)

        # Execute rollback
        result = execute_governed_rollback(
            institution_id=institution_id,
            failed_release_id="20260118-150000",
            reason="Deploy failed",
        )

        # Verify failure with SAFE_MODE
        assert result.success is False
        assert result.error_code == EGE_ROLLBACK_NO_PINNED_RELEASE
        assert result.safe_mode_activated is True

        # Verify runtime is in SAFE_MODE
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == EGE_ROLLBACK_NO_PINNED_RELEASE

    def test_rollback_blocked_by_freeze(self, institution_id, setup_pinned_release):
        """Should fail when institution is frozen."""
        # Set freeze mode
        config = get_effective_config(institution_id)
        config_dict = config.to_dict()
        config_dict["freeze_mode"] = True
        save_active_config(institution_id, config_dict, "test")
        invalidate_config_cache(institution_id)

        result = execute_governed_rollback(
            institution_id=institution_id,
            failed_release_id="20260118-150000",
            reason="Deploy failed",
        )

        assert result.success is False
        assert result.error_code == EGE_ROLLBACK_BLOCKED_FROZEN
        assert result.safe_mode_activated is False

    def test_rollback_emits_audit_events(self, institution_id, setup_pinned_release, tmp_path):
        """Should emit EGE_ROLLBACK_STARTED and EGE_ROLLBACK_COMPLETED events."""
        # Execute rollback
        result = execute_governed_rollback(
            institution_id=institution_id,
            failed_release_id="20260118-150000",
            reason="Deploy failed",
        )

        assert result.success is True

        # Read ledger directly - get_ledger_for_institution returns institution-specific ledger
        from engine.core.ledger import get_ledger_for_institution
        ledger = get_ledger_for_institution(institution_id)

        # Read events from ledger file
        events = []
        if ledger._path.exists():
            with open(ledger._path, "r") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))

        # Find rollback events
        rollback_events = [e for e in events if "ROLLBACK" in e.get("event_type", "")]

        assert len(rollback_events) >= 2, f"Expected at least 2 rollback events, got {len(rollback_events)}"

        # Check for STARTED event(s)
        started_events = [e for e in rollback_events if e["event_type"] == "EGE_ROLLBACK_STARTED"]
        assert len(started_events) >= 1, "Expected at least one EGE_ROLLBACK_STARTED event"
        # Check the most recent STARTED event has correct payload
        assert started_events[-1]["payload"]["failed_release_id"] == "20260118-150000"

        # Check for COMPLETED event(s)
        completed_events = [e for e in rollback_events if e["event_type"] == "EGE_ROLLBACK_COMPLETED"]
        assert len(completed_events) >= 1, "Expected at least one EGE_ROLLBACK_COMPLETED event"
        # Check the most recent COMPLETED event has correct payload
        assert completed_events[-1]["payload"]["rolled_back_to"] == setup_pinned_release["release_id"]


class TestGetCurrentReleaseId:
    """Tests for get_current_release_id()."""

    def test_returns_release_id_from_current(self, institution_id, setup_pinned_release):
        """Should return release ID from CURRENT symlink."""
        release_id = get_current_release_id(institution_id)
        assert release_id == setup_pinned_release["release_id"]

    def test_returns_none_when_no_current(self, institution_id):
        """Should return None when CURRENT doesn't exist."""
        bundles_root = get_bundles_root_for_institution(institution_id)
        bundles_root.mkdir(parents=True, exist_ok=True)

        release_id = get_current_release_id(institution_id)
        assert release_id is None


class TestRollbackIntegrationWithRelease:
    """Integration tests for rollback via release.py."""

    def test_handle_deploy_failure_triggers_rollback(self, institution_id, setup_pinned_release):
        """_handle_deploy_failure should trigger governed rollback."""
        from engine.ise.release import _handle_deploy_failure, ReleaseResult

        # Create failed release
        bundles_root = setup_pinned_release["bundles_root"]
        releases_dir = bundles_root / "releases"
        failed_release_id = "20260118-160000"
        failed_dir = releases_dir / failed_release_id / "finance-pilot"
        failed_dir.mkdir(parents=True, exist_ok=True)

        # Point CURRENT to failed
        current_link = bundles_root / "CURRENT"
        if current_link.exists() or current_link.is_symlink():
            current_link.unlink()
        current_link.symlink_to(failed_dir)

        # Call handler
        result = _handle_deploy_failure(
            institution_id=institution_id,
            release_id=failed_release_id,
            bundle_name="finance-pilot",
            bundle_hash="abc123",
            error_code="ISE_DEPLOY_FAILED",
            error_message="Smoke test failed",
        )

        # Verify result
        assert result.status == "rolled_back"
        assert "rolled back to" in result.error_message
        assert setup_pinned_release["release_id"] in result.error_message

        # Verify CURRENT points to pinned
        current_target = current_link.resolve()
        assert current_target == setup_pinned_release["bundle_path"]

    def test_handle_deploy_failure_without_institution_uses_legacy(self):
        """_handle_deploy_failure without institution_id uses legacy behavior."""
        from engine.ise.release import _handle_deploy_failure

        result = _handle_deploy_failure(
            institution_id=None,  # Legacy mode
            release_id="20260118-160000",
            bundle_name="finance-pilot",
            bundle_hash="abc123",
            error_code="ISE_DEPLOY_FAILED",
            error_message="Deploy failed",
        )

        # Legacy mode just returns rolled_back status
        assert result.status == "rolled_back"
        assert "rolled back" in result.error_message.lower()
        assert "legacy" in result.error_message.lower()

    def test_handle_deploy_failure_activates_safe_mode_when_no_pin(self, institution_id):
        """_handle_deploy_failure should activate SAFE_MODE when no pin exists."""
        from engine.ise.release import _handle_deploy_failure

        # Empty config - no pins
        save_active_config(institution_id, {}, "test")
        invalidate_config_cache(institution_id)

        result = _handle_deploy_failure(
            institution_id=institution_id,
            release_id="20260118-160000",
            bundle_name="finance-pilot",
            bundle_hash="abc123",
            error_code="ISE_DEPLOY_FAILED",
            error_message="Deploy failed",
        )

        # Verify failed with SAFE_MODE
        assert result.status == "failed"
        assert "SAFE_MODE activated" in result.error_message

        # Verify runtime in SAFE_MODE
        assert runtime_state.is_safe_mode()


class TestPinnedReleaseIdInConfig:
    """Tests for pinned_release_id config field."""

    def test_pinned_release_id_saved_on_pin_accept(self, institution_id):
        """Accept pin should save pinned_release_id to config."""
        from engine.core.ege_pins import create_pin_update_proposal, accept_pin_update_proposal

        # Set up a new bundle with different hashes (not matching config)
        bundles_root = get_bundles_root_for_institution(institution_id)
        bundles_root.mkdir(parents=True, exist_ok=True)
        releases_dir = bundles_root / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)

        # Create release
        release_id = "20260118-200000"
        bundle_dir = releases_dir / release_id / "finance-pilot"
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # Create manifest (different from anything pinned)
        manifest = {
            "name": "finance-pilot",
            "version": "2.0.0",
            "created_at": "2026-01-18T20:00:00Z",
            "contracts": [{"name": "new_contract.json"}],
        }
        manifest_path = bundle_dir / "bundle.manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # Create ledger
        ledger = {
            "ledger_version": "1.0",
            "bundle_name": "finance-pilot",
            "contracts": [],
        }
        ledger_path = bundle_dir / "contract_ledger.json"
        ledger_path.write_text(json.dumps(ledger, indent=2))

        # Create CURRENT symlink
        current_link = bundles_root / "CURRENT"
        if current_link.exists() or current_link.is_symlink():
            current_link.unlink()
        current_link.symlink_to(bundle_dir)

        # Start with empty config (no pins)
        save_active_config(institution_id, {}, "test")
        invalidate_config_cache(institution_id)

        # Now create a pin proposal for this new release
        proposal_id, error_code, error_message = create_pin_update_proposal(
            institution_id=institution_id,
            release_id=release_id,
            bundle_name="finance-pilot",
            actor_id="test",
        )

        assert proposal_id is not None, f"Failed to create proposal: {error_message}"

        # Accept proposal
        accept_result, error_code, error_message = accept_pin_update_proposal(
            institution_id=institution_id,
            proposal_id=proposal_id,
            actor_id="test",
        )

        assert accept_result is not None, f"Failed to accept proposal: {error_message}"
        assert accept_result["status"] == "accepted"

        # Verify config has pinned_release_id
        invalidate_config_cache(institution_id)
        config = get_effective_config(institution_id)
        assert config.pinned_release_id == release_id

    def test_config_validation_accepts_valid_release_id(self, institution_id):
        """Config should accept valid YYYYMMDD-HHMMSS format."""
        config_dict = {"pinned_release_id": "20260118-143052"}
        config, error_code, error_message, _ = save_active_config(
            institution_id, config_dict, "test"
        )

        assert config is not None
        assert error_code is None
        assert config.pinned_release_id == "20260118-143052"

    def test_config_validation_rejects_invalid_release_id(self, institution_id):
        """Config should reject invalid release_id format."""
        config_dict = {"pinned_release_id": "invalid-format"}
        config, error_code, error_message, _ = save_active_config(
            institution_id, config_dict, "test"
        )

        assert config is None
        assert error_code is not None
        assert "format" in error_message.lower()
