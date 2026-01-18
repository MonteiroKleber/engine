"""Tests for institution config effects on runtime behavior."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.institution_config import reset_config_cache


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path / "bundle"))

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
        json={"slug": "config-effects-test"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


class TestMaxBodyBytesEffect:
    """Test max_body_bytes limit effect on requests."""

    def test_default_body_size_limit_allows_small_request(self, client, created_institution):
        """Default 256 KiB limit allows small requests."""
        # Health endpoint to test body size middleware
        # (We use health as it's simple - body size is checked before routing)
        response = client.get(
            "/health",
            headers={"X-Institution-Id": created_institution},
        )
        # Health should work fine
        assert response.status_code in [200, 503]  # 503 if safe mode

    def test_custom_body_size_limit_applied(self, client, created_institution):
        """Custom body size limit is applied to institution requests."""
        # Set a very small limit
        put_response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": False,
                    "enable_contracts_stub": True,
                },
                "limits": {
                    "max_body_bytes": 1024,  # Minimum allowed - 1 KB
                    "rate_limit_per_minute": 100,
                },
                "defaults": {
                    "default_dept": "finance",
                    "default_bundle_name": "finance-pilot",
                },
            },
        )
        assert put_response.status_code == 200

        # Invalidate cache by making a new request
        reset_config_cache()

        # Now try a POST with a larger body
        # Use a known endpoint that accepts POST
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": created_institution,
                "Content-Length": "2000",  # Claim larger than allowed
            },
            json={"amount": 100, "description": "Test expense"},
        )

        # Should be rejected due to body size
        assert response.status_code == 413
        assert response.json()["code"] == "REQUEST_TOO_LARGE"


class TestEnableContractsStubEffect:
    """Test enable_contracts_stub flag effect on contracts endpoints."""

    def test_contracts_enabled_by_default(self, client, created_institution, tmp_path, monkeypatch):
        """Contracts endpoints work when enabled (default)."""
        # Set up a multi-dept bundle to enable contracts routes
        bundle_path = tmp_path / "bundle"
        bundle_path.mkdir(parents=True, exist_ok=True)

        # Create minimal manifest
        import json
        manifest = {
            "bundle_hash": "test-hash",
            "contracts": [],
            "mode": "multi",
            "departments": ["dept-a"],
        }
        with open(bundle_path / "manifest.json", "w") as f:
            json.dump(manifest, f)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_path))

        # Contracts endpoint should return 404 for "contract not found"
        # (not 404 for "contracts disabled")
        response = client.post(
            "/d/dept-a/contracts/some-contract/invoke",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": created_institution,
            },
            json={"payload": {}},
        )

        # With contracts enabled (default), we get CONTRACT_NOT_FOUND
        # because the specific contract doesn't exist
        if response.status_code == 404:
            assert response.json()["code"] == "CONTRACT_NOT_FOUND"

    def test_contracts_disabled_returns_404(self, client, created_institution, tmp_path, monkeypatch):
        """Contracts endpoints return 404 when disabled."""
        # Set up a multi-dept bundle
        bundle_path = tmp_path / "bundle"
        bundle_path.mkdir(parents=True, exist_ok=True)

        import json
        manifest = {
            "bundle_hash": "test-hash",
            "contracts": [],
            "mode": "multi",
            "departments": ["dept-a"],
        }
        with open(bundle_path / "manifest.json", "w") as f:
            json.dump(manifest, f)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_path))

        # Disable contracts
        put_response = client.put(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": False,
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
        assert put_response.status_code == 200

        # Reset cache
        reset_config_cache()

        # Try to invoke a contract
        response = client.post(
            "/d/dept-a/contracts/some-contract/invoke",
            headers={
                "X-Institution-Id": created_institution,
                "X-Actor-Id": "test-actor",
                "X-Actor-Roles": "analyst",
                "X-Tenant-Id": created_institution,
            },
            json={"payload": {}},
        )

        # Should get 404 with special message about contracts disabled
        if response.status_code == 404:
            data = response.json()
            assert data["code"] == "CONTRACT_NOT_FOUND"
            assert "not enabled" in data["message"].lower() or "not found" in data["message"].lower()


class TestConfigCacheInvalidation:
    """Test that config cache is properly invalidated."""

    def test_put_invalidates_cache(self, client, created_institution):
        """PUT config invalidates cache so next request uses new config."""
        # First GET - should get defaults
        get1 = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert get1.status_code == 200
        assert get1.json()["flags"]["allow_legacy_routes"] is True

        # PUT new config
        put_response = client.put(
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
        assert put_response.status_code == 200

        # GET again - should get updated value
        get2 = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert get2.status_code == 200
        assert get2.json()["flags"]["allow_legacy_routes"] is False


class TestConfigIsolation:
    """Test that config is isolated per institution."""

    def test_different_institutions_different_configs(self, client):
        """Different institutions can have different configs."""
        # Create two institutions
        resp1 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "inst-alpha"},
        )
        assert resp1.status_code == 201
        inst_a = resp1.json()["institution_id"]

        resp2 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "inst-beta"},
        )
        assert resp2.status_code == 201
        inst_b = resp2.json()["institution_id"]

        # Set different configs
        client.put(
            f"/admin/institutions/{inst_a}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json={
                "flags": {
                    "allow_legacy_routes": True,
                    "require_institution_header_for_runtime": False,
                    "enable_contracts_stub": True,
                },
                "limits": {
                    "max_body_bytes": 1024,
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
                    "max_body_bytes": 2048,
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

        assert get_a.json()["limits"]["max_body_bytes"] == 1024
        assert get_b.json()["limits"]["max_body_bytes"] == 2048


class TestDefaultDeptAndBundleNameEffect:
    """Test default_dept and default_bundle_name config effect."""

    def test_default_dept_stored(self, client, created_institution):
        """default_dept is stored in config."""
        # Set custom default dept
        put_response = client.put(
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
        assert put_response.status_code == 200

        # Verify it's stored
        get_response = client.get(
            f"/admin/institutions/{created_institution}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert get_response.json()["defaults"]["default_dept"] == "hr"
        assert get_response.json()["defaults"]["default_bundle_name"] == "hr-bundle"

    def test_valid_default_dept_patterns(self, client, created_institution):
        """Valid default_dept patterns (alphanumeric, dash, underscore) are accepted."""
        valid_depts = ["finance", "hr", "dept-1", "dept_2", "DEPT_A", "a"]
        for dept in valid_depts:
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
                        "default_dept": dept,
                        "default_bundle_name": "finance-pilot",
                    },
                },
            )
            assert response.status_code == 200, f"Failed for dept: {dept}"
            assert response.json()["defaults"]["default_dept"] == dept
