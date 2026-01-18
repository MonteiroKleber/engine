"""Tests for EGE drift middleware blocking (api/server.py middleware)."""

import json
import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.ege import save_drift_state, DriftState
from engine.core.ege_proposals import reset_proposals_registry
from engine.core.institution_config import (
    save_active_config,
    reset_config_cache,
)
from engine.core.errors import EGE_DRIFT_BLOCKED
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


def _setup_active_drift(institution_id):
    """Set up ACTIVE drift state for testing."""
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
    return drift_state


def _setup_clear_drift(institution_id):
    """Set up CLEAR drift state for testing."""
    drift_state = DriftState(
        status="CLEAR",
        checked_at="2024-01-01T00:00:00Z",
    )
    save_drift_state(institution_id, drift_state)
    return drift_state


def _setup_config_with_enforcement(institution_id, enforce_drift=True):
    """Set up institution config with EGE enforcement setting."""
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
        "ege_enforce_drift": enforce_drift,
    }
    save_active_config(institution_id, config_dict, "test")
    reset_config_cache()


class TestDriftMiddlewareBlock:
    """Test EGE drift middleware blocking write operations."""

    def test_post_blocked_when_drift_active(self, client, institution_id):
        """POST requests blocked when drift is ACTIVE."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        response = client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": institution_id},
            json={"amount": 100, "description": "Test expense"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == EGE_DRIFT_BLOCKED

    def test_put_blocked_when_drift_active(self, client, institution_id):
        """PUT requests blocked when drift is ACTIVE."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        response = client.put(
            "/some/resource",
            headers={"X-Institution-Id": institution_id},
            json={"data": "test"},
        )

        # Should be blocked by drift middleware (even if endpoint doesn't exist)
        assert response.status_code == 409
        assert response.json()["code"] == EGE_DRIFT_BLOCKED

    def test_patch_blocked_when_drift_active(self, client, institution_id):
        """PATCH requests blocked when drift is ACTIVE."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        response = client.patch(
            "/some/resource",
            headers={"X-Institution-Id": institution_id},
            json={"data": "test"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == EGE_DRIFT_BLOCKED

    def test_delete_blocked_when_drift_active(self, client, institution_id):
        """DELETE requests blocked when drift is ACTIVE."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        response = client.delete(
            "/some/resource",
            headers={"X-Institution-Id": institution_id},
        )

        assert response.status_code == 409
        assert response.json()["code"] == EGE_DRIFT_BLOCKED

    def test_get_allowed_when_drift_active(self, client, institution_id):
        """GET requests allowed even when drift is ACTIVE."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        response = client.get(
            "/health",
        )

        # Health endpoint should return 200
        assert response.status_code == 200


class TestDriftMiddlewareBypass:
    """Test EGE drift middleware bypass paths."""

    def test_health_bypasses_drift_check(self, client, institution_id):
        """Health endpoint bypasses drift check."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        # This is a GET so would be allowed anyway, but path should bypass
        response = client.get("/health")

        assert response.status_code == 200

    def test_admin_endpoints_bypass_drift_check(self, client, institution_id):
        """Admin endpoints bypass drift check."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        # Admin endpoint POST should be allowed
        response = client.post(
            "/admin/ege/drift/check",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": institution_id,
            },
        )

        # Should not be blocked by drift middleware
        # (may get other errors but not EGE_DRIFT_BLOCKED)
        assert response.json().get("code") != EGE_DRIFT_BLOCKED

    def test_docs_bypasses_drift_check(self, client, institution_id):
        """Docs endpoint bypasses drift check."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        response = client.get("/docs")

        # Should not be blocked by drift
        assert response.json().get("code") != EGE_DRIFT_BLOCKED if response.headers.get("content-type", "").startswith("application/json") else True

    def test_openapi_bypasses_drift_check(self, client, institution_id):
        """OpenAPI endpoint bypasses drift check."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        response = client.get("/openapi.json")

        # Should not be blocked by drift
        assert response.status_code != 409 or response.json().get("code") != EGE_DRIFT_BLOCKED


class TestDriftMiddlewareAllow:
    """Test EGE drift middleware allowing requests."""

    def test_post_allowed_when_drift_clear(self, client, institution_id):
        """POST allowed when drift status is CLEAR."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_clear_drift(institution_id)

        response = client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": institution_id},
            json={"amount": 100, "description": "Test expense"},
        )

        # Should not be blocked by drift (may get other validation errors)
        assert response.json().get("code") != EGE_DRIFT_BLOCKED

    def test_post_allowed_when_no_drift_state(self, client, institution_id):
        """POST allowed when no drift state exists."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        # Don't set up any drift state

        response = client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": institution_id},
            json={"amount": 100, "description": "Test expense"},
        )

        # Should not be blocked by drift
        assert response.json().get("code") != EGE_DRIFT_BLOCKED

    def test_post_allowed_when_enforcement_disabled(self, client, institution_id):
        """POST allowed when ege_enforce_drift is false."""
        _setup_config_with_enforcement(institution_id, enforce_drift=False)
        _setup_active_drift(institution_id)  # Drift is active but enforcement is off

        response = client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": institution_id},
            json={"amount": 100, "description": "Test expense"},
        )

        # Should not be blocked by drift because enforcement is disabled
        assert response.json().get("code") != EGE_DRIFT_BLOCKED

    def test_post_allowed_when_drift_unpinned(self, client, institution_id):
        """POST allowed when drift status is UNPINNED."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)

        # Set UNPINNED state
        drift_state = DriftState(status="UNPINNED", checked_at="2024-01-01T00:00:00Z")
        save_drift_state(institution_id, drift_state)

        response = client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": institution_id},
            json={"amount": 100, "description": "Test expense"},
        )

        # Should not be blocked by drift
        assert response.json().get("code") != EGE_DRIFT_BLOCKED


class TestDriftMiddlewareLedgerEvents:
    """Test EGE drift middleware emits ledger events."""

    def test_block_emits_ledger_event(self, client, institution_id):
        """Blocking emits EGE_DRIFT_BLOCKED ledger event."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Id": "test-actor",
            },
            json={"amount": 100},
        )

        ledger = get_ledger()
        with open(ledger._path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        blocked_events = [
            e for e in events if e.get("event_type") == "EGE_DRIFT_BLOCKED"
        ]
        assert len(blocked_events) >= 1

        event = blocked_events[-1]
        assert event["step"] == "EGE:drift.block"
        assert event["payload"]["decision"] == "deny"
        assert event["payload"]["drift_status"] == "ACTIVE"
        assert event["payload"]["method"] == "POST"
        assert event["payload"]["path"] == "/finance/expenses"

    def test_block_event_includes_mismatch_flags(self, client, institution_id):
        """Block event includes bundle and ledger mismatch flags."""
        _setup_config_with_enforcement(institution_id, enforce_drift=True)
        _setup_active_drift(institution_id)

        client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": institution_id},
            json={"amount": 100},
        )

        ledger = get_ledger()
        with open(ledger._path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        blocked_events = [
            e for e in events if e.get("event_type") == "EGE_DRIFT_BLOCKED"
        ]
        event = blocked_events[-1]

        assert event["payload"]["bundle_manifest_mismatch"] is True
        assert event["payload"]["contract_ledger_mismatch"] is True


class TestDriftMiddlewareInstitutionIsolation:
    """Test EGE drift middleware is per-institution."""

    def test_drift_isolated_per_institution(self, client, tmp_path, monkeypatch):
        """Drift state is isolated per institution."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # Set up DEFAULT with active drift
        _setup_config_with_enforcement(DEFAULT_INSTITUTION_ID, enforce_drift=True)
        _setup_active_drift(DEFAULT_INSTITUTION_ID)

        # POST to DEFAULT should be blocked
        response1 = client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": DEFAULT_INSTITUTION_ID},
            json={"amount": 100},
        )
        assert response1.status_code == 409
        assert response1.json()["code"] == EGE_DRIFT_BLOCKED

        # Different institution without drift state should not be blocked
        other_inst_id = "other-institution-123"
        _setup_config_with_enforcement(other_inst_id, enforce_drift=True)
        # No drift state for other institution

        response2 = client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": other_inst_id},
            json={"amount": 100},
        )
        # Should not be blocked by drift (may get other errors)
        assert response2.json().get("code") != EGE_DRIFT_BLOCKED
