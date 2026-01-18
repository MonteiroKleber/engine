"""Tests for require_institution_header_for_runtime flag behavior."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.institution_config import (
    reset_config_cache,
    get_effective_config,
    InstitutionConfig,
)
from engine.core.errors import INSTITUTION_HEADER_REQUIRED


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
        json={"slug": "require-header-test"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


class TestRequireInstitutionHeaderDefault:
    """Test require_institution_header_for_runtime default value."""

    def test_require_header_default_is_false(self, tmp_path, monkeypatch):
        """require_institution_header_for_runtime defaults to False."""
        config = InstitutionConfig()
        assert config.flags.require_institution_header_for_runtime is False

    def test_effective_config_has_require_header_false(self, tmp_path, monkeypatch):
        """get_effective_config returns require_institution_header_for_runtime=False by default."""
        institution_id = "11111111-1111-1111-1111-111111111111"
        config = get_effective_config(institution_id)
        assert config.flags.require_institution_header_for_runtime is False

    def test_api_returns_require_header_false(self, client, created_institution):
        """GET config API returns require_institution_header_for_runtime=False by default."""
        response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response.status_code == 200
        assert response.json()["flags"]["require_institution_header_for_runtime"] is False


class TestRequireInstitutionHeaderConfiguration:
    """Test require_institution_header_for_runtime can be configured."""

    def test_set_require_header_true(self, client, created_institution):
        """Can set require_institution_header_for_runtime to True."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": True,
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
        assert response.json()["flags"]["require_institution_header_for_runtime"] is True

    def test_set_require_header_false(self, client, created_institution):
        """Can set require_institution_header_for_runtime to False."""
        # First set to True
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": True,
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

        # Then set to False
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
        assert response.json()["flags"]["require_institution_header_for_runtime"] is False


class TestRequireInstitutionHeaderEnforcement:
    """Test require_institution_header_for_runtime enforcement behavior.

    When require_institution_header_for_runtime is True for an institution,
    requests without X-Institution-Id header should be rejected.
    Note: X-Tenant-Id is NOT accepted per spec - only X-Institution-Id.
    """

    def test_request_with_header_accepted_when_required(self, client, created_institution):
        """Request with institution header is accepted when required."""
        # Set require header to True
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": True,
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

        # Reset cache
        reset_config_cache()

        # Request WITH header should work
        response = client.get(
            "/health",
            headers={"X-Institution-Id": created_institution},
        )
        # Health endpoint should return 200 or 503 (safe mode)
        assert response.status_code in [200, 503]


class TestRequireInstitutionHeaderValidation:
    """Test require_institution_header_for_runtime validation."""

    def test_rejects_non_boolean_value(self, client, created_institution):
        """Rejects non-boolean value for require_institution_header_for_runtime."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": "yes",
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

    def test_rejects_integer_value(self, client, created_institution):
        """Rejects integer value for require_institution_header_for_runtime."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": 1,
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


class TestRequireInstitutionHeaderIsolation:
    """Test require_institution_header_for_runtime is isolated per institution."""

    def test_different_institutions_different_values(self, client):
        """Different institutions can have different require_institution_header_for_runtime values."""
        # Create two institutions
        resp1 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "header-inst-a"},
        )
        inst_a = resp1.json()["institution_id"]

        resp2 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "header-inst-b"},
        )
        inst_b = resp2.json()["institution_id"]

        # Set different values
        client.put(
            f"/admin/institutions/{inst_a}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": True,
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

        assert get_a.json()["flags"]["require_institution_header_for_runtime"] is True
        assert get_b.json()["flags"]["require_institution_header_for_runtime"] is False


class TestRequireInstitutionHeaderAdminBypass:
    """Test that admin endpoints bypass require_institution_header_for_runtime."""

    def test_admin_endpoints_work_without_header(self, client, created_institution):
        """Admin endpoints work without institution header even when required."""
        # Set require header to True
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": True,
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

        # Admin endpoint should still work without institution header
        response = client.get(
            f"/admin/institutions/{created_institution}",
            headers={"X-Admin-Token": "test-admin-token"},
            # Note: no X-Institution-Id header
        )
        assert response.status_code == 200

    def test_health_endpoint_works_without_header(self, client, created_institution):
        """Health endpoint works without institution header (skipped by middleware)."""
        # Set require header to True
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": True,
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

        # Health endpoint should work without header
        # (institution middleware skips /health)
        response = client.get("/health")
        assert response.status_code in [200, 503]


class TestRequireInstitutionHeaderHistory:
    """Test require_institution_header_for_runtime changes are recorded in history."""

    def test_require_header_in_history(self, client, created_institution):
        """require_institution_header_for_runtime changes are recorded in history."""
        # Make some changes
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": True,
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
        assert history[0]["flags"]["require_institution_header_for_runtime"] is True
        assert history[1]["flags"]["require_institution_header_for_runtime"] is False
