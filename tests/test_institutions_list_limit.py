"""Tests for institution list with limit."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")

    reset_registry()

    yield

    reset_registry()


class TestListInstitutions:
    """Test listing institutions with limit."""

    def test_list_empty_returns_empty_array(self, tmp_path, monkeypatch):
        """List with no institutions returns empty items array."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["next_cursor"] is None

    def test_list_returns_all_when_under_limit(self, tmp_path, monkeypatch):
        """List returns all institutions when count is under limit."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create 3 institutions
        slugs = ["inst-one", "inst-two", "inst-three"]
        for slug in slugs:
            client.post(
                "/admin/institutions",
                headers={"X-Admin-Token": "test-admin-token"},
                json={"slug": slug},
            )

        # List with default limit
        response = client.get(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["next_cursor"] is None

    def test_list_limit_truncates(self, tmp_path, monkeypatch):
        """List with limit=2 returns only 2 institutions."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create 3 institutions
        slugs = ["inst-alpha", "inst-beta", "inst-gamma"]
        for slug in slugs:
            client.post(
                "/admin/institutions",
                headers={"X-Admin-Token": "test-admin-token"},
                json={"slug": slug},
            )

        # List with limit=2
        response = client.get(
            "/admin/institutions?limit=2",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

        # Should return LAST 2 by creation order (most recent N)
        item_slugs = [item["slug"] for item in data["items"]]
        assert item_slugs == ["inst-beta", "inst-gamma"]

    def test_list_preserves_creation_order(self, tmp_path, monkeypatch):
        """List returns institutions in creation order."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create institutions in specific order
        slugs = ["first-created", "second-created", "third-created", "fourth-created"]
        for slug in slugs:
            client.post(
                "/admin/institutions",
                headers={"X-Admin-Token": "test-admin-token"},
                json={"slug": slug},
            )

        # List all
        response = client.get(
            "/admin/institutions?limit=10",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 4

        # Should be in creation order
        item_slugs = [item["slug"] for item in data["items"]]
        assert item_slugs == slugs

    def test_list_limit_1_returns_last(self, tmp_path, monkeypatch):
        """List with limit=1 returns only the last created institution."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create 3 institutions
        slugs = ["inst-first", "inst-middle", "inst-last"]
        for slug in slugs:
            client.post(
                "/admin/institutions",
                headers={"X-Admin-Token": "test-admin-token"},
                json={"slug": slug},
            )

        # List with limit=1
        response = client.get(
            "/admin/institutions?limit=1",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["slug"] == "inst-last"

    def test_list_next_cursor_always_null(self, tmp_path, monkeypatch):
        """List always returns next_cursor as null (no pagination in this phase)."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create 5 institutions
        for i in range(5):
            client.post(
                "/admin/institutions",
                headers={"X-Admin-Token": "test-admin-token"},
                json={"slug": f"inst-{i}"},
            )

        # List with limit=2
        response = client.get(
            "/admin/institutions?limit=2",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["next_cursor"] is None

    def test_list_default_limit_is_50(self, tmp_path, monkeypatch):
        """List without limit parameter uses default of 50."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create 3 institutions (less than default)
        for i in range(3):
            client.post(
                "/admin/institutions",
                headers={"X-Admin-Token": "test-admin-token"},
                json={"slug": f"default-limit-{i}"},
            )

        # List without limit
        response = client.get(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        # Should return all 3 (under default limit of 50)
        assert len(data["items"]) == 3
