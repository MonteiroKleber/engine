"""Tests for institution create and get operations."""

import uuid

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.errors import (
    INSTITUTION_SLUG_TAKEN,
    INSTITUTION_NOT_FOUND,
    INSTITUTION_ID_INVALID,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")

    reset_registry()

    yield

    reset_registry()


class TestCreateInstitution:
    """Test institution creation."""

    def test_create_institution_success(self, tmp_path, monkeypatch):
        """Create institution returns 201 with institution data."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "test-institution", "display_name": "Test Institution"},
        )

        assert response.status_code == 201
        data = response.json()

        assert data["slug"] == "test-institution"
        assert data["display_name"] == "Test Institution"
        assert data["schema_version"] == "1.0"
        assert "institution_id" in data
        assert "created_at" in data

        # Validate UUID format
        uuid.UUID(data["institution_id"])

    def test_create_institution_without_display_name(self, tmp_path, monkeypatch):
        """Create institution without display_name sets it to null."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "no-display-name"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "no-display-name"
        assert data["display_name"] is None


class TestDuplicateSlug:
    """Test duplicate slug handling."""

    def test_duplicate_slug_returns_409(self, tmp_path, monkeypatch):
        """Creating institution with duplicate slug returns 409."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create first
        response1 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "duplicate-test"},
        )
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "duplicate-test"},
        )

        assert response2.status_code == 409
        data = response2.json()
        assert data["code"] == INSTITUTION_SLUG_TAKEN


class TestGetBySlug:
    """Test get institution by slug."""

    def test_get_by_slug_success(self, tmp_path, monkeypatch):
        """Get institution by slug returns institution data."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create institution
        create_response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "my-institution", "display_name": "My Institution"},
        )
        assert create_response.status_code == 201
        created_data = create_response.json()

        # Get by slug
        get_response = client.get(
            "/admin/institutions/by-slug/my-institution",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert get_response.status_code == 200
        data = get_response.json()

        assert data["slug"] == "my-institution"
        assert data["display_name"] == "My Institution"
        assert data["institution_id"] == created_data["institution_id"]
        assert data["created_at"] == created_data["created_at"]

    def test_get_by_slug_not_found(self, tmp_path, monkeypatch):
        """Get institution by non-existent slug returns 404."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/admin/institutions/by-slug/nonexistent-slug",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == INSTITUTION_NOT_FOUND


class TestGetById:
    """Test get institution by ID."""

    def test_get_by_id_success(self, tmp_path, monkeypatch):
        """Get institution by ID returns institution data."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create institution
        create_response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "id-lookup-test", "display_name": "ID Lookup Test"},
        )
        assert create_response.status_code == 201
        created_data = create_response.json()
        institution_id = created_data["institution_id"]

        # Get by ID
        get_response = client.get(
            f"/admin/institutions/{institution_id}",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert get_response.status_code == 200
        data = get_response.json()

        assert data["institution_id"] == institution_id
        assert data["slug"] == "id-lookup-test"
        assert data["display_name"] == "ID Lookup Test"

    def test_get_by_id_not_found(self, tmp_path, monkeypatch):
        """Get institution by non-existent ID returns 404."""
        client = TestClient(app, raise_server_exceptions=False)

        fake_id = str(uuid.uuid4())
        response = client.get(
            f"/admin/institutions/{fake_id}",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == INSTITUTION_NOT_FOUND

    def test_get_by_invalid_id_returns_400(self, tmp_path, monkeypatch):
        """Get institution by invalid ID format returns 400."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/admin/institutions/not-a-valid-uuid",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == INSTITUTION_ID_INVALID


class TestCreateThenGetFlow:
    """Test full create -> get by slug -> get by id flow."""

    def test_full_create_get_flow(self, tmp_path, monkeypatch):
        """Create institution, then get by slug, then get by id - all return same data."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create
        create_response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "flow-test-inst", "display_name": "Flow Test"},
        )
        assert create_response.status_code == 201
        created_data = create_response.json()

        # Get by slug
        slug_response = client.get(
            "/admin/institutions/by-slug/flow-test-inst",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert slug_response.status_code == 200
        slug_data = slug_response.json()

        # Get by ID
        id_response = client.get(
            f"/admin/institutions/{created_data['institution_id']}",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert id_response.status_code == 200
        id_data = id_response.json()

        # All three should be identical
        assert created_data == slug_data == id_data
