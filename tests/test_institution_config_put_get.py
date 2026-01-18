"""Tests for institution config PUT and GET API routes."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.institution_config import reset_config_cache
from engine.core.errors import (
    INSTITUTION_CONFIG_INVALID,
    INSTITUTION_NOT_FOUND,
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
        json={"slug": "test-config-inst"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


class TestGetConfig:
    """Test GET /admin/institutions/{id}/config."""

    def test_get_config_returns_defaults(self, client, created_institution):
        """GET config returns defaults when no config saved."""
        response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["schema_version"] == "1.3"
        assert data["updated_at"] is None
        assert data["updated_by"] is None
        assert data["flags"]["allow_legacy_routes"] is True
        assert data["flags"]["require_institution_header_for_runtime"] is False
        assert data["flags"]["enable_contracts_stub"] is True
        assert data["limits"]["max_body_bytes"] == 262144
        assert data["limits"]["rate_limit_per_minute"] == 100
        assert data["defaults"]["default_dept"] == "finance"
        assert data["defaults"]["default_bundle_name"] == "finance-pilot"
        assert data["freeze_mode"] is False
        assert data["emergency_stop"]["enabled"] is False
        assert data["emergency_stop"]["blocked_endpoints"] == []

    def test_get_config_unauthorized_without_token(self, client, created_institution):
        """GET config requires admin token."""
        response = client.get(
            f"/admin/institutions/{created_institution}/config",
        )

        assert response.status_code == 401
        assert response.json()["code"] == "ISE_ADMIN_UNAUTHORIZED"

    def test_get_config_unauthorized_with_wrong_token(self, client, created_institution):
        """GET config rejects wrong admin token."""
        response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "wrong-token"},
        )

        assert response.status_code == 401
        assert response.json()["code"] == "ISE_ADMIN_UNAUTHORIZED"

    def test_get_config_404_for_nonexistent_institution(self, client):
        """GET config returns 404 for nonexistent institution."""
        response = client.get(
            "/admin/institutions/11111111-1111-1111-1111-111111111111/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 404
        assert response.json()["code"] == INSTITUTION_NOT_FOUND

    def test_get_config_for_default_institution(self, client):
        """GET config works for default institution (00000000-0000-0000-0000-000000000000)."""
        default_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(
            f"/admin/institutions/{default_id}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["schema_version"] == "1.3"


class TestPutConfig:
    """Test PUT /admin/institutions/{id}/config."""

    def test_put_config_updates_flags(self, client, created_institution):
        """PUT config updates flags."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Actor-Id": "admin-user-1",
            },
            json={
                "flags": {
                    "allow_legacy_routes": False,
                    "require_institution_header_for_runtime": True,
                    "enable_contracts_stub": False,
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
        data = response.json()
        assert data["flags"]["allow_legacy_routes"] is False
        assert data["flags"]["require_institution_header_for_runtime"] is True
        assert data["flags"]["enable_contracts_stub"] is False
        assert data["updated_by"] == "admin-user-1"
        assert data["updated_at"] is not None

    def test_put_config_updates_limits(self, client, created_institution):
        """PUT config updates limits."""
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
                    "max_body_bytes": 524288,
                    "rate_limit_per_minute": 200,
                },
                "defaults": {
                    "default_dept": "finance",
                    "default_bundle_name": "finance-pilot",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["limits"]["max_body_bytes"] == 524288
        assert data["limits"]["rate_limit_per_minute"] == 200

    def test_put_config_updates_defaults(self, client, created_institution):
        """PUT config updates defaults."""
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
                    "default_dept": "hr",
                    "default_bundle_name": "hr-bundle",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["defaults"]["default_dept"] == "hr"
        assert data["defaults"]["default_bundle_name"] == "hr-bundle"

    def test_put_config_requires_full_body(self, client, created_institution):
        """PUT config requires full config body (no partial updates)."""
        # Attempt partial update with only flags
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": False,
                    "require_institution_header_for_runtime": True,
                    "enable_contracts_stub": False,
                },
            },
        )

        # Pydantic validation should reject missing required fields
        assert response.status_code == 422

    def test_put_config_unauthorized_without_token(self, client, created_institution):
        """PUT config requires admin token."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
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

        assert response.status_code == 401

    def test_put_config_404_for_nonexistent_institution(self, client):
        """PUT config returns 404 for nonexistent institution."""
        response = client.put(
            "/admin/institutions/11111111-1111-1111-1111-111111111111/config",
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

        assert response.status_code == 404
        assert response.json()["code"] == INSTITUTION_NOT_FOUND


class TestPutConfigValidation:
    """Test PUT config validation."""

    def test_put_config_rejects_unknown_flag(self, client, created_institution):
        """PUT config rejects unknown flag."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": False,
                    "enable_contracts_stub": True,
                    "unknown_flag": True,
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

        # Pydantic with extra="forbid" returns 422 for unknown fields
        assert response.status_code == 422

    def test_put_config_rejects_unknown_limit(self, client, created_institution):
        """PUT config rejects unknown limit."""
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
                    "unknown_limit": 100,
                },
                "defaults": {
                    "default_dept": "finance",
                    "default_bundle_name": "finance-pilot",
                },
            },
        )

        # Pydantic with extra="forbid" returns 422 for unknown fields
        assert response.status_code == 422

    def test_put_config_rejects_unknown_default(self, client, created_institution):
        """PUT config rejects unknown default."""
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
                    "unknown_default": "value",
                },
            },
        )

        # Pydantic with extra="forbid" returns 422 for unknown fields
        assert response.status_code == 422

    def test_put_config_rejects_invalid_default_dept(self, client, created_institution):
        """PUT config rejects invalid default_dept (fails regex)."""
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
                    "default_dept": "invalid dept!",  # Invalid - contains space and !
                    "default_bundle_name": "finance-pilot",
                },
            },
        )

        assert response.status_code == 422

    def test_put_config_rejects_max_body_bytes_below_1024(self, client, created_institution):
        """PUT config rejects max_body_bytes below 1024."""
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
                    "max_body_bytes": 512,  # Below minimum of 1024
                    "rate_limit_per_minute": 100,
                },
                "defaults": {
                    "default_dept": "finance",
                    "default_bundle_name": "finance-pilot",
                },
            },
        )

        assert response.status_code == 422

    def test_put_config_rejects_rate_limit_below_1(self, client, created_institution):
        """PUT config rejects rate_limit_per_minute below 1."""
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
                    "rate_limit_per_minute": 0,  # Below minimum of 1
                },
                "defaults": {
                    "default_dept": "finance",
                    "default_bundle_name": "finance-pilot",
                },
            },
        )

        assert response.status_code == 422

    def test_put_config_rejects_rate_limit_above_100000(self, client, created_institution):
        """PUT config rejects rate_limit_per_minute above 100000."""
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
                    "rate_limit_per_minute": 100001,  # Above maximum of 100000
                },
                "defaults": {
                    "default_dept": "finance",
                    "default_bundle_name": "finance-pilot",
                },
            },
        )

        assert response.status_code == 422

    def test_put_config_rejects_non_boolean_flag(self, client, created_institution):
        """PUT config rejects non-boolean flag value."""
        response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": "yes",  # Should be boolean
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

        # Pydantic validation error (422) is expected here
        assert response.status_code == 422


class TestGetAfterPut:
    """Test GET returns updated config after PUT."""

    def test_get_returns_updated_config(self, client, created_institution):
        """GET returns config that was PUT."""
        # PUT config
        put_response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Actor-Id": "admin-user-1",
            },
            json={
                "flags": {
                    "allow_legacy_routes": False,
                    "require_institution_header_for_runtime": True,
                    "enable_contracts_stub": False,
                },
                "limits": {
                    "max_body_bytes": 4096,
                    "rate_limit_per_minute": 10,
                },
                "defaults": {
                    "default_dept": "hr",
                    "default_bundle_name": "hr-bundle",
                },
            },
        )
        assert put_response.status_code == 200

        # GET config
        get_response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["flags"]["allow_legacy_routes"] is False
        assert data["flags"]["require_institution_header_for_runtime"] is True
        assert data["flags"]["enable_contracts_stub"] is False
        assert data["limits"]["max_body_bytes"] == 4096
        assert data["limits"]["rate_limit_per_minute"] == 10
        assert data["defaults"]["default_dept"] == "hr"
        assert data["defaults"]["default_bundle_name"] == "hr-bundle"
        assert data["updated_by"] == "admin-user-1"


class TestConfigHistory:
    """Test GET /admin/institutions/{id}/config/history."""

    def test_history_empty_for_new_institution(self, client, created_institution):
        """History is empty for institution with no config updates."""
        response = client.get(
            f"/admin/institutions/{created_institution}/config/history",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    def test_history_contains_updates(self, client, created_institution):
        """History contains config updates in order."""
        # First update
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Actor-Id": "actor-1",
            },
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

        # Second update
        client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Actor-Id": "actor-2",
            },
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
        data = response.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["updated_by"] == "actor-1"
        assert data["items"][0]["seq"] == 1
        assert data["items"][1]["updated_by"] == "actor-2"
        assert data["items"][1]["seq"] == 2

    def test_history_unauthorized_without_token(self, client, created_institution):
        """History requires admin token."""
        response = client.get(
            f"/admin/institutions/{created_institution}/config/history",
        )

        assert response.status_code == 401

    def test_history_404_for_nonexistent_institution(self, client):
        """History returns 404 for nonexistent institution."""
        response = client.get(
            "/admin/institutions/11111111-1111-1111-1111-111111111111/config/history",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 404
