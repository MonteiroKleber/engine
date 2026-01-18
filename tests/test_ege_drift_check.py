"""Tests for EGE drift check (core/ege.py)."""

import json
import os
import pytest
from pathlib import Path

from engine.core.ege import (
    compute_file_sha256,
    load_drift_state,
    save_drift_state,
    check_drift,
    emit_ege_drift_checked,
    DriftState,
    DRIFT_STATE_SCHEMA_VERSION,
    DRIFT_STATE_FILE,
)
from engine.core.institution_config import (
    save_active_config,
    reset_config_cache,
    HASH_PREFIX,
)
from engine.core.ledger import AuditLedger, set_ledger, get_ledger, get_ledger_for_institution


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

    yield

    reset_config_cache()
    set_ledger(None)


@pytest.fixture
def institution_id():
    """Test institution ID."""
    return "test-inst-drift-001"


@pytest.fixture
def bundles_dir(tmp_path):
    """Create bundles directory."""
    bundles = tmp_path / "bundles"
    bundles.mkdir(parents=True, exist_ok=True)
    return bundles


def _create_bundle(bundles_dir, bundle_name, manifest_content, ledger_content):
    """Create a bundle with manifest and ledger files."""
    bundle_path = bundles_dir / bundle_name
    bundle_path.mkdir(parents=True, exist_ok=True)

    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest_content, f)

    ledger_path = bundle_path / "contract_ledger.json"
    with open(ledger_path, "w") as f:
        json.dump(ledger_content, f)

    return bundle_path


def _create_current_symlink(bundles_dir, target_bundle):
    """Create CURRENT symlink to bundle."""
    current_path = bundles_dir / "CURRENT"
    if current_path.exists() or current_path.is_symlink():
        current_path.unlink()
    current_path.symlink_to(target_bundle)
    return current_path


class TestComputeFileSha256:
    """Test compute_file_sha256 function."""

    def test_compute_hash_deterministic(self, tmp_path):
        """Same content produces same hash."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        hash1 = compute_file_sha256(test_file)
        hash2 = compute_file_sha256(test_file)

        assert hash1 == hash2
        assert hash1.startswith(HASH_PREFIX)

    def test_compute_hash_different_content(self, tmp_path):
        """Different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("Content A")
        file2.write_text("Content B")

        hash1 = compute_file_sha256(file1)
        hash2 = compute_file_sha256(file2)

        assert hash1 != hash2

    def test_compute_hash_format(self, tmp_path):
        """Hash has correct format."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        file_hash = compute_file_sha256(test_file)

        assert file_hash.startswith(HASH_PREFIX)
        # SHA256 hex is 64 chars
        hex_part = file_hash[len(HASH_PREFIX):]
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_compute_hash_nonexistent_file(self, tmp_path):
        """Raises FileNotFoundError for missing file."""
        missing = tmp_path / "missing.txt"

        with pytest.raises(FileNotFoundError):
            compute_file_sha256(missing)


class TestDriftState:
    """Test DriftState dataclass."""

    def test_to_dict(self):
        """Convert state to dictionary."""
        state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            bundle_manifest_mismatch=True,
        )

        d = state.to_dict()

        assert d["status"] == "ACTIVE"
        assert d["bundle_manifest_mismatch"] is True

    def test_from_dict(self):
        """Create state from dictionary."""
        d = {
            "schema_version": "1.0",
            "status": "CLEAR",
            "checked_at": "2024-01-01T00:00:00Z",
        }

        state = DriftState.from_dict(d)

        assert state.status == "CLEAR"
        assert state.checked_at == "2024-01-01T00:00:00Z"


class TestLoadSaveDriftState:
    """Test load_drift_state and save_drift_state."""

    def test_load_nonexistent_returns_none(self, institution_id):
        """Loading nonexistent state returns None."""
        state = load_drift_state(institution_id)

        assert state is None

    def test_save_and_load(self, institution_id):
        """Save and load drift state."""
        state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:abc123",
            bundle_manifest_mismatch=True,
        )

        save_drift_state(institution_id, state)
        loaded = load_drift_state(institution_id)

        assert loaded is not None
        assert loaded.status == "ACTIVE"
        assert loaded.bundle_manifest_mismatch is True
        assert loaded.expected_bundle_manifest_sha256 == "SHA256:abc123"

    def test_save_creates_directory(self, tmp_path, monkeypatch):
        """Save creates institution directory if needed."""
        data_root = tmp_path / "new_data"
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(data_root))

        state = DriftState(status="CLEAR")

        save_drift_state("new-inst-id", state)

        assert (data_root / "institutions" / "new-inst-id" / DRIFT_STATE_FILE).exists()


class TestCheckDrift:
    """Test check_drift function."""

    def test_check_drift_no_pinned_hashes_returns_unpinned(self, institution_id):
        """No pinned hashes returns UNPINNED status."""
        state = check_drift(institution_id)

        assert state.status == "UNPINNED"
        assert state.bundle_manifest_mismatch is False
        assert state.contract_ledger_mismatch is False

    def test_check_drift_no_current_symlink_returns_unpinned(
        self, institution_id, bundles_dir, tmp_path, monkeypatch
    ):
        """Missing CURRENT symlink returns UNPINNED."""
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_dir))

        # Set pinned hashes in config
        config_dict = {
            "flags": {
                "require_institution_header_for_runtime": False,
                "allow_legacy_routes": True,
                "enable_contracts_stub": True,
            },
            "limits": {"rate_limit_per_minute": 100, "max_body_bytes": 262144},
            "defaults": {"default_dept": "finance", "default_bundle_name": "test"},
            "freeze_mode": False,
            "emergency_stop": {"enabled": False, "blocked_endpoints": []},
            "pinned_bundle_manifest_sha256": "SHA256:" + "a" * 64,
            "pinned_contract_ledger_sha256": "SHA256:" + "b" * 64,
            "ege_enforce_drift": True,
        }
        save_active_config(institution_id, config_dict, "test")
        reset_config_cache()

        state = check_drift(institution_id)

        assert state.status == "UNPINNED"

    def test_check_drift_matching_hashes_returns_clear(
        self, institution_id, bundles_dir, tmp_path, monkeypatch
    ):
        """Matching hashes returns CLEAR status."""
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_dir))

        # Create bundle
        manifest = {"version": "1.0", "hash": "test"}
        ledger = {"contracts": []}
        bundle_path = _create_bundle(bundles_dir, "v1", manifest, ledger)
        _create_current_symlink(bundles_dir, bundle_path)

        # Compute actual hashes
        manifest_hash = compute_file_sha256(bundle_path / "bundle.manifest.json")
        ledger_hash = compute_file_sha256(bundle_path / "contract_ledger.json")

        # Set pinned hashes to match
        config_dict = {
            "flags": {
                "require_institution_header_for_runtime": False,
                "allow_legacy_routes": True,
                "enable_contracts_stub": True,
            },
            "limits": {"rate_limit_per_minute": 100, "max_body_bytes": 262144},
            "defaults": {"default_dept": "finance", "default_bundle_name": "test"},
            "freeze_mode": False,
            "emergency_stop": {"enabled": False, "blocked_endpoints": []},
            "pinned_bundle_manifest_sha256": manifest_hash,
            "pinned_contract_ledger_sha256": ledger_hash,
            "ege_enforce_drift": True,
        }
        save_active_config(institution_id, config_dict, "test")
        reset_config_cache()

        state = check_drift(institution_id)

        assert state.status == "CLEAR"
        assert state.bundle_manifest_mismatch is False
        assert state.contract_ledger_mismatch is False
        assert state.observed_bundle_manifest_sha256 == manifest_hash
        assert state.observed_contract_ledger_sha256 == ledger_hash

    def test_check_drift_manifest_mismatch_returns_active(
        self, institution_id, bundles_dir, tmp_path, monkeypatch
    ):
        """Manifest mismatch returns ACTIVE status."""
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_dir))

        # Create bundle
        manifest = {"version": "1.0"}
        ledger = {"contracts": []}
        bundle_path = _create_bundle(bundles_dir, "v1", manifest, ledger)
        _create_current_symlink(bundles_dir, bundle_path)

        # Compute ledger hash but use wrong manifest hash
        ledger_hash = compute_file_sha256(bundle_path / "contract_ledger.json")
        wrong_manifest_hash = "SHA256:" + "f" * 64

        config_dict = {
            "flags": {
                "require_institution_header_for_runtime": False,
                "allow_legacy_routes": True,
                "enable_contracts_stub": True,
            },
            "limits": {"rate_limit_per_minute": 100, "max_body_bytes": 262144},
            "defaults": {"default_dept": "finance", "default_bundle_name": "test"},
            "freeze_mode": False,
            "emergency_stop": {"enabled": False, "blocked_endpoints": []},
            "pinned_bundle_manifest_sha256": wrong_manifest_hash,
            "pinned_contract_ledger_sha256": ledger_hash,
            "ege_enforce_drift": True,
        }
        save_active_config(institution_id, config_dict, "test")
        reset_config_cache()

        state = check_drift(institution_id)

        assert state.status == "ACTIVE"
        assert state.bundle_manifest_mismatch is True
        assert state.contract_ledger_mismatch is False

    def test_check_drift_ledger_mismatch_returns_active(
        self, institution_id, bundles_dir, tmp_path, monkeypatch
    ):
        """Ledger mismatch returns ACTIVE status."""
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_dir))

        # Create bundle
        manifest = {"version": "1.0"}
        ledger = {"contracts": []}
        bundle_path = _create_bundle(bundles_dir, "v1", manifest, ledger)
        _create_current_symlink(bundles_dir, bundle_path)

        # Compute manifest hash but use wrong ledger hash
        manifest_hash = compute_file_sha256(bundle_path / "bundle.manifest.json")
        wrong_ledger_hash = "SHA256:" + "e" * 64

        config_dict = {
            "flags": {
                "require_institution_header_for_runtime": False,
                "allow_legacy_routes": True,
                "enable_contracts_stub": True,
            },
            "limits": {"rate_limit_per_minute": 100, "max_body_bytes": 262144},
            "defaults": {"default_dept": "finance", "default_bundle_name": "test"},
            "freeze_mode": False,
            "emergency_stop": {"enabled": False, "blocked_endpoints": []},
            "pinned_bundle_manifest_sha256": manifest_hash,
            "pinned_contract_ledger_sha256": wrong_ledger_hash,
            "ege_enforce_drift": True,
        }
        save_active_config(institution_id, config_dict, "test")
        reset_config_cache()

        state = check_drift(institution_id)

        assert state.status == "ACTIVE"
        assert state.bundle_manifest_mismatch is False
        assert state.contract_ledger_mismatch is True

    def test_check_drift_both_mismatch_returns_active(
        self, institution_id, bundles_dir, tmp_path, monkeypatch
    ):
        """Both hash mismatches returns ACTIVE with both flags set."""
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_dir))

        # Create bundle
        manifest = {"version": "1.0"}
        ledger = {"contracts": []}
        bundle_path = _create_bundle(bundles_dir, "v1", manifest, ledger)
        _create_current_symlink(bundles_dir, bundle_path)

        # Use wrong hashes for both
        wrong_manifest_hash = "SHA256:" + "a" * 64
        wrong_ledger_hash = "SHA256:" + "b" * 64

        config_dict = {
            "flags": {
                "require_institution_header_for_runtime": False,
                "allow_legacy_routes": True,
                "enable_contracts_stub": True,
            },
            "limits": {"rate_limit_per_minute": 100, "max_body_bytes": 262144},
            "defaults": {"default_dept": "finance", "default_bundle_name": "test"},
            "freeze_mode": False,
            "emergency_stop": {"enabled": False, "blocked_endpoints": []},
            "pinned_bundle_manifest_sha256": wrong_manifest_hash,
            "pinned_contract_ledger_sha256": wrong_ledger_hash,
            "ege_enforce_drift": True,
        }
        save_active_config(institution_id, config_dict, "test")
        reset_config_cache()

        state = check_drift(institution_id)

        assert state.status == "ACTIVE"
        assert state.bundle_manifest_mismatch is True
        assert state.contract_ledger_mismatch is True


class TestEmitDriftCheckedEvent:
    """Test emit_ege_drift_checked function."""

    def test_emit_event_on_clear(self, institution_id, tmp_path):
        """Emit event with allow decision on CLEAR."""
        state = DriftState(status="CLEAR", checked_at="2024-01-01T00:00:00Z")

        emit_ege_drift_checked(institution_id, state)

        ledger = get_ledger_for_institution(institution_id)
        if not ledger._path.exists():
            events = []
        else:
            with open(ledger._path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

        drift_events = [e for e in events if e.get("event_type") == "EGE_DRIFT_CHECKED"]
        assert len(drift_events) >= 1
        event = drift_events[-1]
        assert event["payload"]["status"] == "CLEAR"
        assert event["payload"]["decision"] == "allow"
        assert event["step"] == "EGE:drift.check"

    def test_emit_event_on_active(self, institution_id, tmp_path):
        """Emit event with deny decision on ACTIVE."""
        state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            bundle_manifest_mismatch=True,
        )

        emit_ege_drift_checked(institution_id, state)

        ledger = get_ledger_for_institution(institution_id)
        if not ledger._path.exists():
            events = []
        else:
            with open(ledger._path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

        drift_events = [e for e in events if e.get("event_type") == "EGE_DRIFT_CHECKED"]
        assert len(drift_events) >= 1
        event = drift_events[-1]
        assert event["payload"]["status"] == "ACTIVE"
        assert event["payload"]["decision"] == "deny"
        assert event["payload"]["bundle_manifest_mismatch"] is True

    def test_emit_event_on_unpinned(self, institution_id, tmp_path):
        """Emit event with allow decision on UNPINNED."""
        state = DriftState(status="UNPINNED", checked_at="2024-01-01T00:00:00Z")

        emit_ege_drift_checked(institution_id, state)

        ledger = get_ledger_for_institution(institution_id)
        if not ledger._path.exists():
            events = []
        else:
            with open(ledger._path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

        drift_events = [e for e in events if e.get("event_type") == "EGE_DRIFT_CHECKED"]
        assert len(drift_events) >= 1
        event = drift_events[-1]
        assert event["payload"]["status"] == "UNPINNED"
        assert event["payload"]["decision"] == "allow"
