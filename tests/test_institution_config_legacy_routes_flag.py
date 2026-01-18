"""Tests for allow_legacy_routes flag configuration.

Note: The actual enforcement of allow_legacy_routes is deferred to a future phase.
These tests verify the flag can be configured and stored correctly.
"""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.institution_config import (
    reset_config_cache,
    get_effective_config,
    InstitutionConfig,
)


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
        json={"slug": "legacy-routes-test"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


class TestAllowLegacyRoutesDefault:
    """Test allow_legacy_routes default value."""

    def test_allow_legacy_routes_default_is_true(self, tmp_path, monkeypatch):
        """allow_legacy_routes defaults to True."""
        config = InstitutionConfig()
        assert config.flags.allow_legacy_routes is True

    def test_effective_config_has_allow_legacy_routes_true(self, tmp_path, monkeypatch):
        """get_effective_config returns allow_legacy_routes=True by default."""
        institution_id = "11111111-1111-1111-1111-111111111111"
        config = get_effective_config(institution_id)
        assert config.flags.allow_legacy_routes is True

    def test_api_returns_allow_legacy_routes_true(self, client, created_institution):
        """GET config API returns allow_legacy_routes=True by default."""
        response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200
        assert response.json()["flags"]["allow_legacy_routes"] is True


class TestAllowLegacyRoutesConfiguration:
    """Test allow_legacy_routes can be configured."""

    def test_set_allow_legacy_routes_false(self, client, created_institution):
        """Can set allow_legacy_routes to False."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": False,
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
            },
        )
        assert response.status_code == 200
        assert response.json()["flags"]["allow_legacy_routes"] is False

    def test_set_allow_legacy_routes_true(self, client, created_institution):
        """Can set allow_legacy_routes to True."""
        # First set to False
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": False,
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
            },
        )

        # Then set to True
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
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
            },
        )
        assert response.status_code == 200
        assert response.json()["flags"]["allow_legacy_routes"] is True

    def test_allow_legacy_routes_persists(self, client, created_institution):
        """allow_legacy_routes setting persists across GET calls."""
        # Set to False
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": False,
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
            },
        )

        # GET should return False
        response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200
        assert response.json()["flags"]["allow_legacy_routes"] is False


class TestAllowLegacyRoutesValidation:
    """Test allow_legacy_routes validation."""

    def test_rejects_non_boolean_value(self, client, created_institution):
        """Rejects non-boolean value for allow_legacy_routes."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": "yes",
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
            },
        )
        # Pydantic validation error
        assert response.status_code == 422

    def test_rejects_null_value(self, client, created_institution):
        """Rejects null value for allow_legacy_routes."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": None,
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
            },
        )
        # Pydantic validation error
        assert response.status_code == 422


class TestAllowLegacyRoutesIsolation:
    """Test allow_legacy_routes is isolated per institution."""

    def test_different_institutions_different_values(self, client):
        """Different institutions can have different allow_legacy_routes values."""
        # Create two institutions
        resp1 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "legacy-inst-a"},
        )
        inst_a = resp1.json()["institution_id"]

        resp2 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "legacy-inst-b"},
        )
        inst_b = resp2.json()["institution_id"]

        # Set different values
        client.put(
            f"/admin/institutions/{inst_a}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": False,
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
            },
        )

        client.put(
            f"/admin/institutions/{inst_b}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
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
            },
        )

        # Verify isolation
        get_a = client.get(
            f"/admin/institutions/{inst_a}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        get_b = client.get(
            f"/admin/institutions/{inst_b}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert get_a.json()["flags"]["allow_legacy_routes"] is False
        assert get_b.json()["flags"]["allow_legacy_routes"] is True


class TestAllowLegacyRoutesHistory:
    """Test allow_legacy_routes changes are recorded in history."""

    def test_allow_legacy_routes_in_history(self, client, created_institution):
        """allow_legacy_routes changes are recorded in history."""
        # Make some changes
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": False,
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
            },
        )

        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
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
            },
        )

        # Get history
        response = client.get(
            f"/admin/institutions/{created_institution}/config/history",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200

        history = response.json()["items"]
        assert len(history) == 2
        assert history[0]["flags"]["allow_legacy_routes"] is False
        assert history[1]["flags"]["allow_legacy_routes"] is True
