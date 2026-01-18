"""Tests for admin EGE API endpoints (api/admin_ege.py)."""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.ege import (
    compute_file_sha256,
    save_drift_state,
    DriftState,
)
from engine.core.ege_proposals import reset_proposals_registry
from engine.core.institution_config import (
    save_active_config,
    reset_config_cache,
    invalidate_config_cache,
    get_effective_config,
)
from engine.core.errors import (
    EGE_NO_DRIFT_ACTIVE,
    EGE_PROPOSAL_NOT_FOUND,
    EGE_PROPOSAL_ALREADY_DECIDED,
    EGE_DECISION_INVALID,
    INSTITUTION_HEADER_REQUIRED,
)
from engine.core.ledger import AuditLedger, set_ledger, get_ledger


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path / "bundles"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path / "bundle"))

    # Create minimal bundle for server boot
    bundle_path = tmp_path / "bundle"
    bundle_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "bundle_hash": "test-hash",
        "contracts": [],
        "mode": "single",
    }
    with open(bundle_path / "manifest.json", "w") as f:
        json.dump(manifest, f)

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
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def institution_id():
    """Test institution ID."""
    from engine.core.institution_context import DEFAULT_INSTITUTION_ID

    return DEFAULT_INSTITUTION_ID


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


class TestDriftCheckEndpoint:
    """Test POST /admin/ege/drift/check endpoint."""

    def test_check_drift_no_auth_fails(self, client, institution_id):
        """Check drift without auth fails."""
        response = client.post(
            "/admin/ege/drift/check",
            headers={"X-Institution-Id": institution_id},
        )

        assert response.status_code == 401

    def test_check_drift_no_institution_header_fails(self, client):
        """Check drift without institution header fails."""
        response = client.post(
            "/admin/ege/drift/check",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == INSTITUTION_HEADER_REQUIRED

    def test_check_drift_returns_unpinned_when_no_pins(
        self, client, institution_id
    ):
        """Check drift returns UNPINNED when no hashes pinned."""
        response = client.post(
            "/admin/ege/drift/check",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "UNPINNED"
        assert data["state"]["status"] == "UNPINNED"

    def test_check_drift_returns_clear_when_hashes_match(
        self, client, institution_id, bundles_dir, monkeypatch
    ):
        """Check drift returns CLEAR when hashes match."""
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_dir))

        # Create bundle
        manifest = {"version": "1.0"}
        ledger = {"contracts": []}
        bundle_path = _create_bundle(bundles_dir, "v1", manifest, ledger)
        _create_current_symlink(bundles_dir, bundle_path)

        # Compute hashes
        manifest_hash = compute_file_sha256(bundle_path / "bundle.manifest.json")
        ledger_hash = compute_file_sha256(bundle_path / "contract_ledger.json")

        # Set pinned hashes
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

        response = client.post(
            "/admin/ege/drift/check",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CLEAR"
        assert data["state"]["bundle_manifest_mismatch"] is False
        assert data["state"]["contract_ledger_mismatch"] is False

    def test_check_drift_returns_active_on_mismatch(
        self, client, institution_id, bundles_dir, monkeypatch
    ):
        """Check drift returns ACTIVE when hashes don't match."""
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_dir))

        # Create bundle
        manifest = {"version": "1.0"}
        ledger = {"contracts": []}
        bundle_path = _create_bundle(bundles_dir, "v1", manifest, ledger)
        _create_current_symlink(bundles_dir, bundle_path)

        # Set wrong pinned hashes
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

        response = client.post(
            "/admin/ege/drift/check",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ACTIVE"
        assert data["state"]["bundle_manifest_mismatch"] is True
        assert data["state"]["contract_ledger_mismatch"] is True

    def test_check_drift_emits_ledger_event(self, client, institution_id):
        """Check drift emits EGE_DRIFT_CHECKED ledger event."""
        response = client.post(
            "/admin/ege/drift/check",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 200

        ledger = get_ledger()
        with open(ledger._path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        drift_events = [
            e for e in events if e.get("event_type") == "EGE_DRIFT_CHECKED"
        ]
        assert len(drift_events) >= 1


class TestCreateProposalEndpoint:
    """Test POST /admin/ege/proposals endpoint."""

    def test_create_proposal_no_auth_fails(self, client, institution_id):
        """Create proposal without auth fails."""
        response = client.post(
            "/admin/ege/proposals",
            headers={"X-Institution-Id": institution_id},
        )

        assert response.status_code == 401

    def test_create_proposal_no_institution_header_fails(self, client):
        """Create proposal without institution header fails."""
        response = client.post(
            "/admin/ege/proposals",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == INSTITUTION_HEADER_REQUIRED

    def test_create_proposal_fails_when_no_drift(self, client, institution_id):
        """Cannot create proposal when no active drift."""
        response = client.post(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 409
        assert response.json()["code"] == EGE_NO_DRIFT_ACTIVE

    def test_create_proposal_success_when_drift_active(
        self, client, institution_id, bundles_dir, monkeypatch
    ):
        """Create proposal succeeds when drift is ACTIVE."""
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_dir))

        # Create bundle
        manifest = {"version": "1.0"}
        ledger = {"contracts": []}
        bundle_path = _create_bundle(bundles_dir, "v1", manifest, ledger)
        _create_current_symlink(bundles_dir, bundle_path)

        # Set wrong pinned hashes to create ACTIVE drift
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

        # Set drift state to ACTIVE
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

        response = client.post(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "proposal_id" in data
        assert data["status"] == "OPEN"
        assert data["expected_bundle_manifest_sha256"] == "SHA256:" + "a" * 64

    def test_create_proposal_emits_ledger_event(
        self, client, institution_id
    ):
        """Create proposal emits EGE_PROPOSAL_CREATED ledger event."""
        # Set drift state to ACTIVE
        drift_state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
            observed_bundle_manifest_sha256="SHA256:" + "c" * 64,
            bundle_manifest_mismatch=True,
        )
        save_drift_state(institution_id, drift_state)

        response = client.post(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 201

        ledger = get_ledger()
        with open(ledger._path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        created_events = [
            e for e in events if e.get("event_type") == "EGE_PROPOSAL_CREATED"
        ]
        assert len(created_events) >= 1


class TestListProposalsEndpoint:
    """Test GET /admin/ege/proposals endpoint."""

    def test_list_proposals_no_auth_fails(self, client, institution_id):
        """List proposals without auth fails."""
        response = client.get(
            "/admin/ege/proposals",
            headers={"X-Institution-Id": institution_id},
        )

        assert response.status_code == 401

    def test_list_proposals_empty(self, client, institution_id):
        """List proposals returns empty list for new institution."""
        response = client.get(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    def test_list_proposals_returns_created(self, client, institution_id):
        """List proposals returns created proposals."""
        # Set drift state to ACTIVE
        drift_state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
            observed_bundle_manifest_sha256="SHA256:" + "c" * 64,
            bundle_manifest_mismatch=True,
        )
        save_drift_state(institution_id, drift_state)

        # Create proposal
        client.post(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        response = client.get(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "OPEN"

    def test_list_proposals_respects_limit(self, client, institution_id):
        """List proposals respects limit parameter."""
        # Set drift state to ACTIVE
        drift_state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
            observed_bundle_manifest_sha256="SHA256:" + "c" * 64,
            bundle_manifest_mismatch=True,
        )
        save_drift_state(institution_id, drift_state)

        # Create multiple proposals
        for _ in range(5):
            client.post(
                "/admin/ege/proposals",
                headers={
                    "X-Admin-Token": "test-admin-token",
                    "X-Institution-Id": institution_id,
                },
            )

        response = client.get(
            "/admin/ege/proposals?limit=3",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3


class TestDecideProposalEndpoint:
    """Test POST /admin/ege/proposals/{proposal_id}/decide endpoint."""

    def test_decide_proposal_no_auth_fails(self, client, institution_id):
        """Decide proposal without auth fails."""
        response = client.post(
            "/admin/ege/proposals/some-id/decide",
            headers={"X-Institution-Id": institution_id},
            json={"decision": "accept"},
        )

        assert response.status_code == 401

    def test_decide_proposal_not_found(self, client, institution_id):
        """Decide nonexistent proposal returns 404."""
        response = client.post(
            "/admin/ege/proposals/nonexistent-id/decide",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
            json={"decision": "accept"},
        )

        assert response.status_code == 404
        assert response.json()["code"] == EGE_PROPOSAL_NOT_FOUND

    def test_decide_proposal_accept(
        self, client, institution_id, bundles_dir, monkeypatch
    ):
        """Accept proposal updates config and clears drift."""
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_dir))

        # Create bundle
        manifest = {"version": "1.0"}
        ledger = {"contracts": []}
        bundle_path = _create_bundle(bundles_dir, "v1", manifest, ledger)
        _create_current_symlink(bundles_dir, bundle_path)

        # Compute actual hashes for observed
        observed_manifest_hash = compute_file_sha256(
            bundle_path / "bundle.manifest.json"
        )
        observed_ledger_hash = compute_file_sha256(bundle_path / "contract_ledger.json")

        # Set initial config with wrong pinned hashes
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

        # Set drift state to ACTIVE with observed hashes
        drift_state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
            expected_contract_ledger_sha256="SHA256:" + "b" * 64,
            observed_bundle_manifest_sha256=observed_manifest_hash,
            observed_contract_ledger_sha256=observed_ledger_hash,
            bundle_manifest_mismatch=True,
            contract_ledger_mismatch=True,
        )
        save_drift_state(institution_id, drift_state)

        # Create proposal
        create_resp = client.post(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )
        proposal_id = create_resp.json()["proposal_id"]

        # Accept proposal
        response = client.post(
            f"/admin/ege/proposals/{proposal_id}/decide",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
                "X-Actor-Id": "test-actor",
            },
            json={"decision": "accept", "reason": "Approved by test"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "DECIDED"
        assert data["decision"] == "accept"
        assert data["decider_actor_id"] == "test-actor"
        assert data["reason"] == "Approved by test"

        # Verify config was updated
        invalidate_config_cache(institution_id)
        config = get_effective_config(institution_id)
        assert config.pinned_bundle_manifest_sha256 == observed_manifest_hash
        assert config.pinned_contract_ledger_sha256 == observed_ledger_hash

    def test_decide_proposal_block(self, client, institution_id):
        """Block proposal leaves drift ACTIVE."""
        # Set drift state to ACTIVE
        drift_state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
            observed_bundle_manifest_sha256="SHA256:" + "c" * 64,
            bundle_manifest_mismatch=True,
        )
        save_drift_state(institution_id, drift_state)

        # Create proposal
        create_resp = client.post(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )
        proposal_id = create_resp.json()["proposal_id"]

        # Block proposal
        response = client.post(
            f"/admin/ege/proposals/{proposal_id}/decide",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
            json={"decision": "block", "reason": "Blocked for security review"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "DECIDED"
        assert data["decision"] == "block"

    def test_decide_proposal_already_decided(self, client, institution_id):
        """Cannot decide already decided proposal."""
        # Set drift state to ACTIVE
        drift_state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
            observed_bundle_manifest_sha256="SHA256:" + "c" * 64,
            bundle_manifest_mismatch=True,
        )
        save_drift_state(institution_id, drift_state)

        # Create proposal
        create_resp = client.post(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )
        proposal_id = create_resp.json()["proposal_id"]

        # First decision
        client.post(
            f"/admin/ege/proposals/{proposal_id}/decide",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
            json={"decision": "accept"},
        )

        # Second decision should fail
        response = client.post(
            f"/admin/ege/proposals/{proposal_id}/decide",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
            json={"decision": "block"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == EGE_PROPOSAL_ALREADY_DECIDED

    def test_decide_proposal_invalid_decision(self, client, institution_id):
        """Invalid decision value fails."""
        # Set drift state to ACTIVE
        drift_state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
            observed_bundle_manifest_sha256="SHA256:" + "c" * 64,
            bundle_manifest_mismatch=True,
        )
        save_drift_state(institution_id, drift_state)

        # Create proposal
        create_resp = client.post(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )
        proposal_id = create_resp.json()["proposal_id"]

        # Invalid decision
        response = client.post(
            f"/admin/ege/proposals/{proposal_id}/decide",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
            json={"decision": "invalid-decision"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == EGE_DECISION_INVALID

    def test_decide_proposal_emits_ledger_event(self, client, institution_id):
        """Decide proposal emits EGE_PROPOSAL_DECIDED ledger event."""
        # Set drift state to ACTIVE
        drift_state = DriftState(
            status="ACTIVE",
            checked_at="2024-01-01T00:00:00Z",
            expected_bundle_manifest_sha256="SHA256:" + "a" * 64,
            observed_bundle_manifest_sha256="SHA256:" + "c" * 64,
            bundle_manifest_mismatch=True,
        )
        save_drift_state(institution_id, drift_state)

        # Create proposal
        create_resp = client.post(
            "/admin/ege/proposals",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )
        proposal_id = create_resp.json()["proposal_id"]

        # Decide proposal
        client.post(
            f"/admin/ege/proposals/{proposal_id}/decide",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
            json={"decision": "accept", "reason": "Test reason"},
        )

        ledger = get_ledger()
        with open(ledger._path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        decided_events = [
            e for e in events if e.get("event_type") == "EGE_PROPOSAL_DECIDED"
        ]
        assert len(decided_events) >= 1
        event = decided_events[-1]
        assert event["payload"]["decision"] == "accept"
        assert event["payload"]["reason"] == "Test reason"
