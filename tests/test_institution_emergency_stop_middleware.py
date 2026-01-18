"""Tests for emergency_stop middleware enforcement."""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.institution_config import reset_config_cache
from engine.core.ledger import AuditLedger, set_ledger, get_ledger


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path / "bundle"))

    # Create minimal bundle
    bundle_path = tmp_path / "bundle"
    bundle_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "bundle_hash": "test-hash",
        "contracts": [],
        "mode": "single",
    }
    with open(bundle_path / "manifest.json", "w") as f:
        json.dump(manifest, f)

    # Set up ledger for event testing
    ledger_path = tmp_path / "audit_ledger.jsonl"
    ledger = AuditLedger(ledger_path)
    set_ledger(ledger)

    reset_registry()
    reset_config_cache()

    yield

    reset_registry()
    reset_config_cache()
    set_ledger(None)


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
        json={"slug": "emergency-stop-test"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


def _full_config(emergency_stop_enabled=False, blocked_endpoints=None):
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
        "freeze_mode": False,
        "emergency_stop": {
            "enabled": emergency_stop_enabled,
            "blocked_endpoints": blocked_endpoints,
        },
    }


class TestEmergencyStopDefault:
    """Test emergency_stop default behavior."""

    def test_emergency_stop_default_disabled(self, client, created_institution):
        """emergency_stop defaults to disabled."""
        response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["emergency_stop"]["enabled"] is False
        assert data["emergency_stop"]["blocked_endpoints"] == []

    def test_post_allowed_when_emergency_stop_disabled(self, client, created_institution):
        """POST requests work when emergency_stop is disabled."""
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": created_institution,
            },
            json={"amount": 100, "description": "Test expense"},
        )
        # Should not be blocked by emergency stop
        assert response.status_code != 503 or response.json().get("code") != "INSTITUTION_EMERGENCY_STOPPED"


class TestEmergencyStopBlocksConfiguredEndpoint:
    """Test emergency_stop blocks only configured endpoints."""

    def test_blocks_configured_endpoint(self, client, created_institution):
        """emergency_stop blocks the configured endpoint."""
        # Enable emergency stop for POST /finance/expenses
        put_response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=True,
                blocked_endpoints=["POST /finance/expenses"],
            ),
        )
        assert put_response.status_code == 200
        assert put_response.json()["emergency_stop"]["enabled"] is True

        reset_config_cache()

        # Try POST /finance/expenses - should be blocked
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": created_institution,
            },
            json={"amount": 100, "description": "Test expense"},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "INSTITUTION_EMERGENCY_STOPPED"

    def test_allows_unconfigured_endpoint(self, client, created_institution):
        """emergency_stop allows endpoints not in blocked_endpoints."""
        # Enable emergency stop for POST /finance/expenses only
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=True,
                blocked_endpoints=["POST /finance/expenses"],
            ),
        )
        reset_config_cache()

        # POST /approvals/{id}/decide should NOT be blocked
        response = client.post(
            "/approvals/some-id/decide",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "manager",
                "X-Tenant-Id": created_institution,
            },
            json={"decision": "approve"},
        )
        # Should not return 503 INSTITUTION_EMERGENCY_STOPPED
        if response.status_code == 503:
            assert response.json().get("code") != "INSTITUTION_EMERGENCY_STOPPED"

    def test_blocks_approvals_decide(self, client, created_institution):
        """emergency_stop can block POST /approvals/{approval_id}/decide."""
        # Enable emergency stop for approvals decide
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=True,
                blocked_endpoints=["POST /approvals/{approval_id}/decide"],
            ),
        )
        reset_config_cache()

        # Try POST /approvals/{id}/decide - should be blocked
        response = client.post(
            "/approvals/any-approval-id/decide",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "manager",
                "X-Tenant-Id": created_institution,
            },
            json={"decision": "approve"},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "INSTITUTION_EMERGENCY_STOPPED"


class TestEmergencyStopDisabledDoesNotBlock:
    """Test emergency_stop.enabled=False does not block."""

    def test_disabled_with_endpoints_does_not_block(self, client, created_institution):
        """emergency_stop with enabled=False does not block even with blocked_endpoints."""
        # Configure blocked_endpoints but keep enabled=False
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=False,
                blocked_endpoints=["POST /finance/expenses"],
            ),
        )
        reset_config_cache()

        # POST should NOT be blocked because enabled=False
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": created_institution,
            },
            json={"amount": 100, "description": "Test expense"},
        )
        # Should not be blocked by emergency stop
        if response.status_code == 503:
            assert response.json().get("code") != "INSTITUTION_EMERGENCY_STOPPED"


class TestEmergencyStopBypassPaths:
    """Test paths that bypass emergency stop check."""

    def test_health_not_blocked(self, client, created_institution):
        """/health is never blocked by emergency stop."""
        # Enable emergency stop
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=True,
                blocked_endpoints=["POST /finance/expenses"],
            ),
        )
        reset_config_cache()

        # /health should not be blocked
        response = client.get("/health")
        assert response.status_code in [200, 503]
        if response.status_code == 503:
            assert response.json().get("code") != "INSTITUTION_EMERGENCY_STOPPED"

    def test_admin_not_blocked(self, client, created_institution):
        """/admin/* is never blocked by emergency stop."""
        # Enable emergency stop
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=True,
                blocked_endpoints=["POST /finance/expenses"],
            ),
        )
        reset_config_cache()

        # Admin endpoints should work
        response = client.get(
            f"/admin/institutions/{created_institution}",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        if response.status_code == 503:
            assert response.json().get("code") != "INSTITUTION_EMERGENCY_STOPPED"


class TestEmergencyStopEmitsLedgerEvent:
    """Test emergency_stop emits ledger events on block."""

    def test_emergency_stop_emits_ledger_event(self, client, created_institution, tmp_path):
        """Blocked request emits INSTITUTION_EMERGENCY_STOP_BLOCKED event."""
        # Enable emergency stop
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=True,
                blocked_endpoints=["POST /finance/expenses"],
            ),
        )
        reset_config_cache()

        # Try POST - should be blocked and emit event
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": created_institution,
            },
            json={"amount": 100},
        )
        assert response.status_code == 503

        # Check ledger for event
        ledger = get_ledger()
        assert ledger is not None

        # Read ledger file to find the emergency stop blocked event
        ledger_path = ledger._path
        with open(ledger_path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        # Find the emergency stop blocked event
        stop_events = [e for e in events if e.get("event_type") == "INSTITUTION_EMERGENCY_STOP_BLOCKED"]
        assert len(stop_events) >= 1

        # Verify event structure
        event = stop_events[-1]
        assert event["payload"]["decision"] == "deny"
        assert event["payload"]["reason"] == "emergency_stop"
        assert event["payload"]["endpoint_sig"] == "POST /finance/expenses"
        assert event["step"] == "ADMIN:emergency_stop.block"


class TestEmergencyStopIsolation:
    """Test emergency_stop is isolated per institution."""

    def test_different_institutions_different_emergency_stop(self, client):
        """Different institutions can have different emergency_stop configs."""
        # Create two institutions
        resp1 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "inst-blocked"},
        )
        inst_blocked = resp1.json()["institution_id"]

        resp2 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "inst-allowed"},
        )
        inst_allowed = resp2.json()["institution_id"]

        # Block one, leave other open
        client.put(
            f"/admin/institutions/{inst_blocked}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=True,
                blocked_endpoints=["POST /finance/expenses"],
            ),
        )

        client.put(
            f"/admin/institutions/{inst_allowed}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=False,
                blocked_endpoints=[],
            ),
        )

        reset_config_cache()

        # Blocked institution should block POST
        response_blocked = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": inst_blocked,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": inst_blocked,
            },
            json={"amount": 100},
        )
        assert response_blocked.status_code == 503
        assert response_blocked.json()["code"] == "INSTITUTION_EMERGENCY_STOPPED"

        # Allowed institution should not block POST
        response_allowed = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": inst_allowed,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": inst_allowed,
            },
            json={"amount": 100},
        )
        if response_allowed.status_code == 503:
            assert response_allowed.json().get("code") != "INSTITUTION_EMERGENCY_STOPPED"


class TestEmergencyStopMultipleEndpoints:
    """Test emergency_stop with multiple blocked endpoints."""

    def test_multiple_blocked_endpoints(self, client, created_institution):
        """emergency_stop can block multiple endpoints."""
        # Block both endpoints
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(
                emergency_stop_enabled=True,
                blocked_endpoints=[
                    "POST /finance/expenses",
                    "POST /approvals/{approval_id}/decide",
                ],
            ),
        )
        reset_config_cache()

        # Both should be blocked
        response1 = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": created_institution,
            },
            json={"amount": 100},
        )
        assert response1.status_code == 503
        assert response1.json()["code"] == "INSTITUTION_EMERGENCY_STOPPED"

        response2 = client.post(
            "/approvals/some-id/decide",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "manager",
                "X-Tenant-Id": created_institution,
            },
            json={"decision": "approve"},
        )
        assert response2.status_code == 503
        assert response2.json()["code"] == "INSTITUTION_EMERGENCY_STOPPED"
