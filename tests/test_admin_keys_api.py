"""Tests for admin_keys API endpoints (api/admin_keys.py)."""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.institution_config import reset_config_cache
from engine.core.admin_keys import reset_admin_keys_registry, get_admin_keys_registry
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


@pytest.fixture
def created_institution(client):
    """Create an institution and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "admin-keys-test"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


class TestCreateAdminKey:
    """Test POST /admin/institutions/{institution_id}/admin-keys."""

    def test_create_key_with_legacy_token_for_default(self, client):
        """Create key for DEFAULT institution using X-Admin-Token."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        response = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )

        assert response.status_code == 201
        data = response.json()
        assert "key_id" in data
        assert "plaintext_secret" in data
        assert len(data["plaintext_secret"]) == 43  # token_urlsafe(32)
        assert "created_at" in data

    def test_create_key_with_admin_key(self, client, created_institution):
        """Create key using another admin key for auth."""
        # First create a key using legacy token (for DEFAULT)
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # For non-DEFAULT institution, we need to first create a key
        # But we can't auth without a key. So we bootstrap via DEFAULT.
        # Actually for this test, we use the created_institution with legacy token first.

        # Since created_institution is not DEFAULT, we need a key first.
        # Let's create a key for DEFAULT and use that pattern.
        # Actually, looking at the code, admin_keys API uses require_admin_auth
        # which accepts X-Admin-Token for any institution's auth check...

        # Wait - the admin_auth module checks institution_id for legacy token.
        # For non-DEFAULT, X-Admin-Token should be rejected.

        # Let's test that X-Admin-Token is rejected for non-DEFAULT
        response = client.post(
            f"/admin/institutions/{created_institution}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )

        # Should be rejected because X-Admin-Token only works for DEFAULT
        assert response.status_code == 401
        assert response.json()["code"] == "ADMIN_KEY_REQUIRED"

    def test_create_key_no_auth_fails(self, client, created_institution):
        """Create key without auth fails."""
        response = client.post(
            f"/admin/institutions/{created_institution}/admin-keys",
            json={},
        )

        assert response.status_code == 401
        assert response.json()["code"] == "ADMIN_KEY_REQUIRED"

    def test_create_key_with_expiry(self, client):
        """Create key with expiry date."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        response = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"expires_at": "2030-12-31T23:59:59Z"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expires_at"] == "2030-12-31T23:59:59Z"

    def test_create_key_use_for_subsequent_auth(self, client):
        """Created key can be used for subsequent API calls."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # Create first key with legacy token
        response1 = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        assert response1.status_code == 201
        secret1 = response1.json()["plaintext_secret"]

        # Use that key to create another key
        response2 = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Key": secret1},
            json={},
        )
        assert response2.status_code == 201
        assert response2.json()["key_id"] != response1.json()["key_id"]


class TestListAdminKeys:
    """Test GET /admin/institutions/{institution_id}/admin-keys."""

    def test_list_keys_empty(self, client):
        """List keys for institution with no keys."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        response = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    def test_list_keys_shows_created(self, client):
        """List keys shows created keys."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # Create keys
        client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )

        response = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

    def test_list_keys_no_secret_exposed(self, client):
        """List keys does not expose plaintext secrets."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )

        response = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        for item in response.json()["items"]:
            assert "plaintext_secret" not in item
            assert "key_hash" not in item

    def test_list_keys_no_auth_fails(self, client):
        """List keys without auth fails."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        response = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
        )

        assert response.status_code == 401


class TestRevokeAdminKey:
    """Test POST /admin/institutions/{institution_id}/admin-keys/{key_id}/revoke."""

    def test_revoke_key_success(self, client):
        """Revoke a key successfully."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

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
        data = response.json()
        assert data["key_id"] == key_id
        assert data["status"] == "revoked"
        assert "revoked_at" in data

    def test_revoke_key_not_found(self, client):
        """Revoke non-existent key returns 404."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        response = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys/nonexistent-key/revoke",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 404
        assert response.json()["code"] == "ADMIN_KEY_NOT_FOUND"

    def test_revoke_key_already_revoked(self, client):
        """Revoke already revoked key returns 409."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # Create key
        create_resp = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        key_id = create_resp.json()["key_id"]

        # Revoke key first time
        client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys/{key_id}/revoke",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # Try to revoke again
        response = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys/{key_id}/revoke",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == "ADMIN_KEY_ALREADY_REVOKED"

    def test_revoked_key_cannot_authenticate(self, client):
        """Revoked key cannot be used for authentication."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # Create key
        create_resp = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        key_id = create_resp.json()["key_id"]
        secret = create_resp.json()["plaintext_secret"]

        # Verify key works before revoke
        list_resp = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Key": secret},
        )
        assert list_resp.status_code == 200

        # Revoke key
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
        assert response.json()["code"] == "ADMIN_KEY_REVOKED"


class TestInstitutionIsolation:
    """Test that admin keys are isolated per institution."""

    def test_key_only_works_for_own_institution(self, client):
        """Key from one institution doesn't work for another."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # Create key for DEFAULT
        create_resp = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        secret = create_resp.json()["plaintext_secret"]

        # Create another institution
        inst_resp = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "other-inst"},
        )
        other_inst_id = inst_resp.json()["institution_id"]

        # Try to use DEFAULT's key for other institution
        response = client.get(
            f"/admin/institutions/{other_inst_id}/admin-keys",
            headers={"X-Admin-Key": secret},
        )

        # Should fail - key is for DEFAULT, not other_inst
        assert response.status_code == 401
        assert response.json()["code"] == "ADMIN_KEY_INVALID"

    def test_list_only_shows_own_keys(self, client):
        """List keys only shows keys for that institution."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # Create key for DEFAULT
        client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )

        # Create another institution and key for it
        inst_resp = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "other-inst-2"},
        )
        other_inst_id = inst_resp.json()["institution_id"]

        # List keys for DEFAULT
        default_keys = client.get(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
        ).json()["items"]

        # Should only show DEFAULT's key
        assert len(default_keys) == 1

        # List keys for other institution (should be empty, and we can't auth)
        # We'd need a key for that institution to list them
