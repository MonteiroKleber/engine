"""Tests for Admin Institutions endpoint authentication."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.ise import errors as ise_errors


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    # Set temp paths to avoid polluting real directories
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))

    # Reset global registry
    reset_registry()

    yield

    reset_registry()


class TestMissingAdminToken:
    """Test that missing admin token returns 401."""

    def test_create_institution_without_token_returns_401(self, tmp_path, monkeypatch):
        """POST /admin/institutions without token returns 401."""
        # Ensure admin token is set (so we know it's not "no token configured")
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "secret-token")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            json={"slug": "test-inst", "display_name": "Test Institution"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED
        assert "message" in data

    def test_get_institution_by_slug_without_token_returns_401(self, tmp_path, monkeypatch):
        """GET /admin/institutions/by-slug/{slug} without token returns 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "secret-token")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/admin/institutions/by-slug/test-inst")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED

    def test_get_institution_by_id_without_token_returns_401(self, tmp_path, monkeypatch):
        """GET /admin/institutions/{institution_id} without token returns 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "secret-token")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/admin/institutions/550e8400-e29b-41d4-a716-446655440000")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED

    def test_list_institutions_without_token_returns_401(self, tmp_path, monkeypatch):
        """GET /admin/institutions without token returns 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "secret-token")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/admin/institutions")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED


class TestInvalidAdminToken:
    """Test that invalid admin token returns 401."""

    def test_create_institution_with_invalid_token_returns_401(self, tmp_path, monkeypatch):
        """POST /admin/institutions with invalid token returns 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-token")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "wrong-token"},
            json={"slug": "test-inst", "display_name": "Test Institution"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED

    def test_get_institution_by_slug_with_invalid_token_returns_401(self, tmp_path, monkeypatch):
        """GET /admin/institutions/by-slug/{slug} with invalid token returns 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-token")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/admin/institutions/by-slug/test-inst",
            headers={"X-Admin-Token": "wrong-token"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED


class TestNoTokenConfigured:
    """Test that no token configured denies all access."""

    def test_no_token_env_set_returns_401(self, tmp_path, monkeypatch):
        """Without ENGINE_ISE_ADMIN_TOKEN env, all access is denied."""
        # Ensure no token is configured
        monkeypatch.delenv("ENGINE_ISE_ADMIN_TOKEN", raising=False)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "any-token"},
            json={"slug": "test-inst"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED
