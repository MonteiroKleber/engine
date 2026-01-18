"""Tests for freeze_mode middleware enforcement."""

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
        json={"slug": "freeze-test"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


def _full_config(freeze_mode=False):
    """Build full config for PUT request."""
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
            "enabled": False,
            "blocked_endpoints": [],
        },
    }


class TestFreezeModeDefault:
    """Test freeze_mode default behavior."""

    def test_freeze_mode_default_is_false(self, client, created_institution):
        """freeze_mode defaults to False."""
        response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200
        assert response.json()["freeze_mode"] is False

    def test_post_allowed_when_not_frozen(self, client, created_institution):
        """POST requests work when freeze_mode is False."""
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
        # Should not be blocked by freeze (may fail for other reasons like missing bundle)
        assert response.status_code != 423


class TestFreezeModeBlocksPost:
    """Test freeze_mode blocks POST requests."""

    def test_freeze_blocks_post_finance(self, client, created_institution):
        """freeze_mode=True blocks POST /finance/expenses."""
        # Enable freeze mode
        put_response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=True),
        )
        assert put_response.status_code == 200
        assert put_response.json()["freeze_mode"] is True

        reset_config_cache()

        # Try POST - should be blocked
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
        assert response.status_code == 423
        assert response.json()["code"] == "INSTITUTION_FROZEN"

    def test_freeze_blocks_approvals_decide(self, client, created_institution):
        """freeze_mode=True blocks POST /approvals/{id}/decide."""
        # Enable freeze mode
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=True),
        )
        reset_config_cache()

        # Try POST to approvals decide - should be blocked
        response = client.post(
            "/approvals/some-approval-id/decide",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "manager",
                "X-Tenant-Id": created_institution,
            },
            json={"decision": "approve"},
        )
        assert response.status_code == 423
        assert response.json()["code"] == "INSTITUTION_FROZEN"


class TestFreezeModeAllowsGet:
    """Test freeze_mode allows GET requests."""

    def test_freeze_allows_get(self, client, created_institution):
        """freeze_mode=True allows GET requests."""
        # Enable freeze mode
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=True),
        )
        reset_config_cache()

        # GET /health should work
        response = client.get(
            "/health",
            headers={"X-Institution-Id": created_institution},
        )
        assert response.status_code in [200, 503]  # 503 if safe mode


class TestFreezeModeBypassPaths:
    """Test paths that bypass freeze check."""

    def test_health_not_blocked(self, client, created_institution):
        """/health is never blocked by freeze mode."""
        # Enable freeze mode
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=True),
        )
        reset_config_cache()

        # /health should not be blocked
        response = client.get("/health")
        assert response.status_code in [200, 503]
        assert response.status_code != 423

    def test_admin_not_blocked(self, client, created_institution):
        """/admin/* is never blocked by freeze mode."""
        # Enable freeze mode
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=True),
        )
        reset_config_cache()

        # Admin endpoints should work
        response = client.get(
            f"/admin/institutions/{created_institution}",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code != 423


class TestFreezeModeEmitsLedgerEvent:
    """Test freeze_mode emits ledger events on block."""

    def test_freeze_emits_ledger_event(self, client, created_institution, tmp_path):
        """Blocked request emits INSTITUTION_FREEZE_BLOCKED event."""
        # Enable freeze mode
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=True),
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
        assert response.status_code == 423

        # Check ledger for event
        ledger = get_ledger()
        assert ledger is not None

        # Read ledger file to find the freeze blocked event
        ledger_path = ledger._path
        with open(ledger_path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        # Find the freeze blocked event
        freeze_events = [e for e in events if e.get("event_type") == "INSTITUTION_FREEZE_BLOCKED"]
        assert len(freeze_events) >= 1

        # Verify event structure
        event = freeze_events[-1]
        assert event["payload"]["decision"] == "deny"
        assert event["payload"]["reason"] == "freeze_mode"
        assert event["step"] == "ADMIN:freeze.block"


class TestFreezeModeIsolation:
    """Test freeze_mode is isolated per institution."""

    def test_different_institutions_different_freeze_state(self, client):
        """Different institutions can have different freeze_mode values."""
        # Create two institutions
        resp1 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "inst-frozen"},
        )
        inst_frozen = resp1.json()["institution_id"]

        resp2 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "inst-active"},
        )
        inst_active = resp2.json()["institution_id"]

        # Freeze one, leave other active
        client.put(
            f"/admin/institutions/{inst_frozen}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=True),
        )

        client.put(
            f"/admin/institutions/{inst_active}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=_full_config(freeze_mode=False),
        )

        reset_config_cache()

        # Frozen institution should block POST
        response_frozen = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": inst_frozen,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": inst_frozen,
            },
            json={"amount": 100},
        )
        assert response_frozen.status_code == 423

        # Active institution should not block POST
        response_active = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": inst_active,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": inst_active,
            },
            json={"amount": 100},
        )
        assert response_active.status_code != 423
