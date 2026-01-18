"""Tests for institution config v1.1 validation (freeze_mode, emergency_stop)."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.institution_config import reset_config_cache


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")

    reset_registry()
    reset_config_cache()

    yield

    reset_registry()
    reset_config_cache()


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def created_institution(client):
    """Create an institution and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "config-v11-test"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


def _full_config(freeze_mode=False, emergency_stop_enabled=False, blocked_endpoints=None):
    """Build full config for PUT request."""
    if blocked_endpoints is None:
        blocked_endpoints = []
    return {
        "flags": {
            "allow_legacy_routes": True,
            "require_institution_header_for_runtime": False,
            "enable_contracts_stub": True,
        },
        "limits": {
            "max_body_bytes": 262144,
            "rate_limit_per_minute": 100,
        },
        "defaults": {
            "default_dept": "finance",
            "default_bundle_name": "finance-pilot",
        },
        "freeze_mode": freeze_mode,
        "emergency_stop": {
            "enabled": emergency_stop_enabled,
            "blocked_endpoints": blocked_endpoints,
        },
    }


class TestFreezeModeValidation:
    """Test freeze_mode validation."""

    def test_accepts_freeze_mode_true(self, client, created_institution):
        """PUT accepts freeze_mode=True."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=True),
        )
        assert response.status_code == 200
        assert response.json()["freeze_mode"] is True

    def test_accepts_freeze_mode_false(self, client, created_institution):
        """PUT accepts freeze_mode=False."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=False),
        )
        assert response.status_code == 200
        assert response.json()["freeze_mode"] is False

    def test_rejects_freeze_mode_non_boolean(self, client, created_institution):
        """PUT rejects non-boolean freeze_mode."""
        config = _full_config()
        config["freeze_mode"] = "yes"
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=config,
        )
        assert response.status_code == 422


class TestEmergencyStopEnabledValidation:
    """Test emergency_stop.enabled validation."""

    def test_accepts_enabled_true(self, client, created_institution):
        """PUT accepts emergency_stop.enabled=True."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(emergency_stop_enabled=True),
        )
        assert response.status_code == 200
        assert response.json()["emergency_stop"]["enabled"] is True

    def test_accepts_enabled_false(self, client, created_institution):
        """PUT accepts emergency_stop.enabled=False."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(emergency_stop_enabled=False),
        )
        assert response.status_code == 200
        assert response.json()["emergency_stop"]["enabled"] is False

    def test_rejects_enabled_non_boolean(self, client, created_institution):
        """PUT rejects non-boolean emergency_stop.enabled."""
        config = _full_config()
        config["emergency_stop"]["enabled"] = "yes"
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=config,
        )
        assert response.status_code == 422


class TestBlockedEndpointsValidation:
    """Test emergency_stop.blocked_endpoints validation."""

    def test_accepts_empty_blocked_endpoints(self, client, created_institution):
        """PUT accepts empty blocked_endpoints array."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(blocked_endpoints=[]),
        )
        assert response.status_code == 200
        assert response.json()["emergency_stop"]["blocked_endpoints"] == []

    def test_accepts_valid_endpoint_sig_finance(self, client, created_institution):
        """PUT accepts valid endpoint_sig: POST /finance/expenses."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(blocked_endpoints=["POST /finance/expenses"]),
        )
        assert response.status_code == 200
        assert "POST /finance/expenses" in response.json()["emergency_stop"]["blocked_endpoints"]

    def test_accepts_valid_endpoint_sig_approvals(self, client, created_institution):
        """PUT accepts valid endpoint_sig: POST /approvals/{approval_id}/decide."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(blocked_endpoints=["POST /approvals/{approval_id}/decide"]),
        )
        assert response.status_code == 200
        assert "POST /approvals/{approval_id}/decide" in response.json()["emergency_stop"]["blocked_endpoints"]

    def test_rejects_unknown_endpoint_sig(self, client, created_institution):
        """PUT rejects unknown endpoint_sig with 400 INSTITUTION_EMERGENCY_ENDPOINT_UNKNOWN."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(blocked_endpoints=["POST /unknown/endpoint"]),
        )
        assert response.status_code == 400
        assert response.json()["code"] == "INSTITUTION_EMERGENCY_ENDPOINT_UNKNOWN"

    def test_rejects_duplicate_blocked_endpoints(self, client, created_institution):
        """PUT rejects duplicate blocked_endpoints with 400 INSTITUTION_CONFIG_INVALID."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(blocked_endpoints=[
                "POST /finance/expenses",
                "POST /finance/expenses",  # Duplicate
            ]),
        )
        assert response.status_code == 400
        assert response.json()["code"] == "INSTITUTION_CONFIG_INVALID"
        assert "duplicate" in response.json()["message"].lower()

    def test_accepts_multiple_valid_endpoints(self, client, created_institution):
        """PUT accepts multiple valid endpoint_sigs."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(blocked_endpoints=[
                "POST /finance/expenses",
                "POST /approvals/{approval_id}/decide",
            ]),
        )
        assert response.status_code == 200
        endpoints = response.json()["emergency_stop"]["blocked_endpoints"]
        assert "POST /finance/expenses" in endpoints
        assert "POST /approvals/{approval_id}/decide" in endpoints


class TestConfigPutEmitsLedgerEventWithFreezeDetails:
    """Test PUT config emits ledger event with freeze/emergency_stop details."""

    def test_put_emits_event_with_freeze_details(self, client, created_institution, tmp_path, monkeypatch):
        """PUT config emits INSTITUTION_CONFIG_UPDATED with freeze/emergency_stop details."""
        import json
        from engine.core.ledger import AuditLedger, set_ledger

        # Set up ledger
        ledger_path = tmp_path / "audit_ledger.jsonl"
        ledger = AuditLedger(ledger_path)
        set_ledger(ledger)

        try:
            # PUT config with freeze_mode and emergency_stop
            response = client.put(
                f"/admin/institutions/{created_institution}/config",
                headers={"X-Admin-Token": "test-admin-token"},
                json=_full_config(
                    freeze_mode=True,
                    emergency_stop_enabled=True,
                    blocked_endpoints=["POST /finance/expenses"],
                ),
            )
            assert response.status_code == 200

            # Read ledger to find the config updated event
            with open(ledger_path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

            # Find INSTITUTION_CONFIG_UPDATED event
            config_events = [e for e in events if e.get("event_type") == "INSTITUTION_CONFIG_UPDATED"]
            assert len(config_events) >= 1

            # Verify payload contains freeze/emergency_stop details
            event = config_events[-1]
            assert event["payload"]["freeze_mode"] is True
            assert event["payload"]["emergency_stop.enabled"] is True
            assert event["payload"]["emergency_stop.blocked_endpoints_count"] == 1
        finally:
            set_ledger(None)


class TestConfigSchemaVersion:
    """Test schema version handling."""

    def test_get_returns_schema_version_1_1(self, client, created_institution):
        """GET config returns schema_version 1.1."""
        # First PUT a config to ensure it's saved
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(),
        )

        response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200
        assert response.json()["schema_version"] == "1.3"


class TestConfigHistoryIncludesFreezeFields:
    """Test config history includes freeze_mode and emergency_stop."""

    def test_history_includes_freeze_mode(self, client, created_institution):
        """Config history includes freeze_mode."""
        # PUT config with freeze_mode
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=True),
        )

        # GET history
        response = client.get(
            f"/admin/institutions/{created_institution}/config/history",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) >= 1
        assert items[-1]["freeze_mode"] is True

    def test_history_includes_emergency_stop(self, client, created_institution):
        """Config history includes emergency_stop."""
        # PUT config with emergency_stop
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=True,
                blocked_endpoints=["POST /finance/expenses"],
            ),
        )

        # GET history
        response = client.get(
            f"/admin/institutions/{created_institution}/config/history",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) >= 1
        assert items[-1]["emergency_stop"]["enabled"] is True
        assert "POST /finance/expenses" in items[-1]["emergency_stop"]["blocked_endpoints"]


class TestEmergencyStopUnknownFields:
    """Test emergency_stop rejects unknown fields."""

    def test_rejects_unknown_emergency_stop_field(self, client, created_institution):
        """PUT rejects unknown field in emergency_stop."""
        config = _full_config()
        config["emergency_stop"]["unknown_field"] = "value"
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=config,
        )
        assert response.status_code == 422


class TestFreezeModeAndEmergencyStopCombination:
    """Test freeze_mode and emergency_stop can be used together."""

    def test_both_enabled(self, client, created_institution):
        """PUT accepts both freeze_mode=True and emergency_stop.enabled=True."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                freeze_mode=True,
                emergency_stop_enabled=True,
                blocked_endpoints=["POST /finance/expenses"],
            ),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["freeze_mode"] is True
        assert data["emergency_stop"]["enabled"] is True
        assert "POST /finance/expenses" in data["emergency_stop"]["blocked_endpoints"]
