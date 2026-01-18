"""Tests for institution slug validation."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry, validate_slug
from engine.core.errors import INSTITUTION_SLUG_INVALID


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")

    reset_registry()

    yield

    reset_registry()


class TestSlugValidationUnit:
    """Unit tests for validate_slug function."""

    def test_valid_simple_slug(self):
        """Simple lowercase slug is valid."""
        valid, err = validate_slug("myinstitution")
        assert valid is True
        assert err is None

    def test_valid_slug_with_numbers(self):
        """Slug with numbers is valid."""
        valid, err = validate_slug("inst123")
        assert valid is True
        assert err is None

    def test_valid_slug_with_hyphen(self):
        """Slug with hyphen in middle is valid."""
        valid, err = validate_slug("my-institution")
        assert valid is True
        assert err is None

    def test_valid_min_length_slug(self):
        """Minimum length slug (3 chars) is valid."""
        valid, err = validate_slug("abc")
        assert valid is True
        assert err is None

    def test_valid_max_length_slug(self):
        """Maximum length slug (63 chars) is valid."""
        slug = "a" + "b" * 61 + "c"  # 63 chars
        valid, err = validate_slug(slug)
        assert valid is True
        assert err is None

    def test_invalid_empty_slug(self):
        """Empty slug is invalid."""
        valid, err = validate_slug("")
        assert valid is False
        assert "empty" in err.lower()

    def test_invalid_too_short_slug(self):
        """Slug shorter than 3 chars is invalid."""
        valid, err = validate_slug("ab")
        assert valid is False
        assert "3 characters" in err

    def test_invalid_too_long_slug(self):
        """Slug longer than 63 chars is invalid."""
        slug = "a" * 64
        valid, err = validate_slug(slug)
        assert valid is False
        assert "63 characters" in err

    def test_invalid_starts_with_hyphen(self):
        """Slug starting with hyphen is invalid."""
        valid, err = validate_slug("-myinst")
        assert valid is False
        assert "start" in err.lower()

    def test_invalid_ends_with_hyphen(self):
        """Slug ending with hyphen is invalid."""
        valid, err = validate_slug("myinst-")
        assert valid is False
        assert "end" in err.lower()

    def test_invalid_uppercase(self):
        """Slug with uppercase is invalid."""
        valid, err = validate_slug("MyInstitution")
        assert valid is False
        assert "lowercase" in err.lower()

    def test_invalid_underscore(self):
        """Slug with underscore is invalid."""
        valid, err = validate_slug("my_institution")
        assert valid is False

    def test_invalid_special_chars(self):
        """Slug with special characters is invalid."""
        valid, err = validate_slug("my.institution")
        assert valid is False

    def test_invalid_space(self):
        """Slug with space is invalid."""
        valid, err = validate_slug("my institution")
        assert valid is False


class TestSlugValidationApi:
    """API tests for slug validation on create."""

    def test_invalid_slug_returns_400(self, tmp_path, monkeypatch):
        """Creating institution with invalid slug returns 400."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "My-Invalid-Slug"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == INSTITUTION_SLUG_INVALID

    def test_slug_too_short_returns_400(self, tmp_path, monkeypatch):
        """Creating institution with slug < 3 chars returns 400."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "ab"},
        )

        # Pydantic may catch this first with 422, or our validation with 400
        assert response.status_code in (400, 422)

    def test_slug_starts_with_hyphen_returns_400(self, tmp_path, monkeypatch):
        """Creating institution with slug starting with hyphen returns 400."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "-invalid"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == INSTITUTION_SLUG_INVALID

    def test_slug_ends_with_hyphen_returns_400(self, tmp_path, monkeypatch):
        """Creating institution with slug ending with hyphen returns 400."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "invalid-"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == INSTITUTION_SLUG_INVALID

    def test_valid_slug_succeeds(self, tmp_path, monkeypatch):
        """Creating institution with valid slug succeeds."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "valid-institution-123"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "valid-institution-123"
