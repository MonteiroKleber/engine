"""Tests for admin keys ledger events.

Verifies that:
- ADMIN_KEY_CREATED is emitted when key is created
- ADMIN_KEY_REVOKED is emitted when key is revoked
- ADMIN_KEY_USED is emitted on successful auth
- ADMIN_KEY_DENIED is emitted on failed auth
"""

import json
import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.institution_config import reset_config_cache
from engine.core.admin_keys import reset_admin_keys_registry
from engine.core.ledger import AuditLedger, set_ledger, get_ledger
from engine.core.institution_context import DEFAULT_INSTITUTION_ID


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

    # Set up ledger
    ledger_path = tmp_path / "audit_ledger.jsonl"
    ledger = AuditLedger(ledger_path)
    set_ledger(ledger)

    reset_registry()
    reset_config_cache()
    reset_admin_keys_registry()

    yield

    reset_registry()
    reset_config_cache()
    reset_admin_keys_registry()
    set_ledger(None)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


def get_ledger_events():
    """Read all events from ledger."""
    ledger = get_ledger()
    if ledger is None:
        return []

    if not ledger._path.exists():
        return []

    events = []
    with open(ledger._path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def get_institution_ledger_events(institution_id, tmp_path=None):
    """Read events from institution-specific ledger."""
    from engine.core.ledger import get_ledger_for_institution

    ledger = get_ledger_for_institution(institution_id)
    if not ledger._path.exists():
        return []

    events = []
    with open(ledger._path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def filter_events(events, event_type):
    """Filter events by type."""
    return [e for e in events if e.get("event_type") == event_type]


class TestAdminKeyCreatedEvent:
    """Test ADMIN_KEY_CREATED ledger event."""

    def test_create_key_emits_event(self, client):
        """Creating a key emits ADMIN_KEY_CREATED event."""
        response = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        assert response.status_code == 201
        key_id = response.json()["key_id"]

        events = get_ledger_events()
        created_events = filter_events(events, "ADMIN_KEY_CREATED")

        assert len(created_events) >= 1
        event = created_events[-1]
        assert event["payload"]["key_id"] == key_id
        assert event["step"] == "ADMIN:key.created"
        assert event["tenant_id"] == DEFAULT_INSTITUTION_ID

    def test_create_key_with_expiry_includes_in_event(self, client):
        """Created key with expiry includes expires_at in event."""
        expires_at = "2030-12-31T23:59:59Z"
        response = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"expires_at": expires_at},
        )
        assert response.status_code == 201

        events = get_ledger_events()
        created_events = filter_events(events, "ADMIN_KEY_CREATED")

        assert len(created_events) >= 1
        event = created_events[-1]
        assert event["payload"]["expires_at"] == expires_at


class TestAdminKeyRevokedEvent:
    """Test ADMIN_KEY_REVOKED ledger event."""

    def test_revoke_key_emits_event(self, client):
        """Revoking a key emits ADMIN_KEY_REVOKED event."""
        # Create key
        create_resp = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        key_id = create_resp.json()["key_id"]

        # Revoke key
        response = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys/{key_id}/revoke",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200

        events = get_ledger_events()
        revoked_events = filter_events(events, "ADMIN_KEY_REVOKED")

        assert len(revoked_events) >= 1
        event = revoked_events[-1]
        assert event["payload"]["key_id"] == key_id
        assert event["step"] == "ADMIN:key.revoked"
        assert "revoked_at" in event["payload"]


class TestAdminKeyUsedEvent:
    """Test ADMIN_KEY_USED ledger event."""

    def test_successful_auth_emits_used_event(self, client):
        """Successful authentication emits ADMIN_KEY_USED event."""
        # Create key
        create_resp = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        key_id = create_resp.json()["key_id"]
        secret = create_resp.json()["plaintext_secret"]

        # Clear events so far
        events_before = len(get_ledger_events())

        # Use the key for authentication
        response = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Key": secret},
        )
        assert response.status_code == 200

        events = get_ledger_events()
        used_events = filter_events(events, "ADMIN_KEY_USED")

        # Should have at least one ADMIN_KEY_USED event
        assert len(used_events) >= 1
        event = used_events[-1]
        assert event["payload"]["key_id"] == key_id
        assert event["payload"]["decision"] == "allow"
        assert event["step"] == "ADMIN:auth.allow"

    def test_legacy_token_auth_emits_used_event(self, client):
        """Legacy token auth emits ADMIN_KEY_USED with reason=legacy_token."""
        # Use legacy token for list
        response = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200

        # Events go to institution-specific ledger
        events = get_institution_ledger_events(DEFAULT_INSTITUTION_ID)
        used_events = filter_events(events, "ADMIN_KEY_USED")

        # Find the event for legacy token
        legacy_events = [e for e in used_events if e["payload"].get("reason") == "legacy_token"]
        assert len(legacy_events) >= 1
        event = legacy_events[-1]
        assert event["payload"]["key_id"] is None  # No key_id for legacy token
        assert event["payload"]["decision"] == "allow"


class TestAdminKeyDeniedEvent:
    """Test ADMIN_KEY_DENIED ledger event."""

    def test_invalid_key_emits_denied_event(self, client):
        """Invalid key emits ADMIN_KEY_DENIED event."""
        response = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Key": "invalid-key-secret"},
        )
        assert response.status_code == 401

        events = get_ledger_events()
        denied_events = filter_events(events, "ADMIN_KEY_DENIED")

        assert len(denied_events) >= 1
        event = denied_events[-1]
        assert event["payload"]["decision"] == "deny"
        assert event["step"] == "ADMIN:auth.deny"

    def test_revoked_key_emits_denied_event(self, client):
        """Revoked key emits ADMIN_KEY_DENIED event."""
        # Create and revoke key
        create_resp = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        key_id = create_resp.json()["key_id"]
        secret = create_resp.json()["plaintext_secret"]

        client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys/{key_id}/revoke",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # Try to use revoked key
        response = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Key": secret},
        )
        assert response.status_code == 401

        events = get_ledger_events()
        denied_events = filter_events(events, "ADMIN_KEY_DENIED")

        # Find denied event for this key
        key_denied = [e for e in denied_events if e["payload"].get("key_id") == key_id]
        assert len(key_denied) >= 1
        event = key_denied[-1]
        assert event["payload"]["reason"] == "ADMIN_KEY_REVOKED"

    def test_wrong_legacy_token_emits_denied_event(self, client):
        """Wrong legacy token emits ADMIN_KEY_DENIED event."""
        response = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "wrong-token"},
        )
        assert response.status_code == 401

        events = get_ledger_events()
        denied_events = filter_events(events, "ADMIN_KEY_DENIED")

        # Find denied event for legacy token
        legacy_denied = [e for e in denied_events if e["payload"].get("reason") == "legacy_token_invalid"]
        assert len(legacy_denied) >= 1

    def test_legacy_token_for_non_default_emits_denied_event(self, client):
        """Legacy token for non-DEFAULT emits ADMIN_KEY_DENIED event."""
        # Create non-DEFAULT institution
        inst_resp = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "non-default-for-denied"},
        )
        inst_id = inst_resp.json()["institution_id"]

        # Try to use legacy token for non-DEFAULT
        response = client.get(
            f"/admin/institutions/{inst_id}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 401

        # Events go to institution-specific ledger
        events = get_institution_ledger_events(inst_id)
        denied_events = filter_events(events, "ADMIN_KEY_DENIED")

        # Find denied event for legacy token on non-default
        non_default_denied = [e for e in denied_events if e["payload"].get("reason") == "legacy_token_non_default"]
        assert len(non_default_denied) >= 1


class TestEventAuditTrail:
    """Test complete audit trail for key lifecycle."""

    def test_full_key_lifecycle_events(self, client):
        """Full key lifecycle generates complete audit trail."""
        # 1. Create key
        create_resp = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        key_id = create_resp.json()["key_id"]
        secret = create_resp.json()["plaintext_secret"]

        # 2. Use key
        client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Key": secret},
        )

        # 3. Revoke key
        client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys/{key_id}/revoke",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # 4. Try to use revoked key (should fail)
        client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Key": secret},
        )

        events = get_ledger_events()

        # Filter events for this key
        key_events = [e for e in events if e.get("payload", {}).get("key_id") == key_id]

        # Should have: CREATED, USED (success), REVOKED, DENIED (revoked)
        event_types = [e["event_type"] for e in key_events]

        assert "ADMIN_KEY_CREATED" in event_types
        assert "ADMIN_KEY_USED" in event_types
        assert "ADMIN_KEY_REVOKED" in event_types
        assert "ADMIN_KEY_DENIED" in event_types
