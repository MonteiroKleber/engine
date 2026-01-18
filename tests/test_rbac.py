"""Tests for Actor Context + RBAC (Etapa 3.2)."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy, RBACPolicy
from engine.loader.load_bundle import load_bundle
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


@pytest.fixture(autouse=True)
def reset_state():
    """Reset runtime state and RBAC policy before each test."""
    runtime_state.set_active()
    set_rbac_policy(None)
    yield
    runtime_state.set_active()
    set_rbac_policy(None)


def create_rbac_json(bundle_path: Path, roles: list) -> str:
    """Create rbac.json and return its SHA-256 hash."""
    rbac_data = {
        "version": "1.0.0",
        "name": "rbac",
        "roles": roles,
    }
    rbac_path = bundle_path / "rbac.json"
    with open(rbac_path, "w", encoding="utf-8") as f:
        json.dump(rbac_data, f)
    return compute_sha256(rbac_path)


def create_minimal_bundle(bundle_path: Path, rbac_roles: list) -> None:
    """Create a minimal valid bundle with RBAC config."""
    # Create rbac.json
    rbac_hash = create_rbac_json(bundle_path, rbac_roles)

    # Create manifest
    manifest = {
        "name": "test-bundle",
        "version": "1.0.0",
        "contracts": [
            {
                "file": "rbac.json",
                "sha256": f"SHA256:{rbac_hash}",
                "required": True,
            }
        ],
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


class TestActorMissing:
    """Test 401 ACTOR_MISSING when X-Actor-Id header is missing."""

    def test_missing_actor_id_returns_401(self, tmp_path: Path):
        """Request without X-Actor-Id should return 401 ACTOR_MISSING."""
        # Create bundle with RBAC
        create_minimal_bundle(tmp_path, [
            {"name": "viewer", "permissions": ["expense.read"]}
        ])
        load_bundle(tmp_path)

        client = TestClient(app)

        # POST without X-Actor-Id
        response = client.post("/finance/expenses")
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "ACTOR_MISSING"
        assert data["message"] == "Actor is required"

        # GET without X-Actor-Id
        response = client.get("/finance/expenses/exp-001")
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "ACTOR_MISSING"


class TestActorInvalid:
    """Test 401 ACTOR_INVALID when X-Actor-Id is not a valid UUID."""

    def test_invalid_actor_id_returns_401(self, tmp_path: Path):
        """Request with invalid UUID should return 401 ACTOR_INVALID."""
        create_minimal_bundle(tmp_path, [
            {"name": "viewer", "permissions": ["expense.read"]}
        ])
        load_bundle(tmp_path)

        client = TestClient(app)

        # POST with invalid UUID
        response = client.post(
            "/finance/expenses",
            headers={"X-Actor-Id": "not-a-valid-uuid"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "ACTOR_INVALID"
        assert data["message"] == "Actor is invalid"

        # GET with invalid UUID
        response = client.get(
            "/finance/expenses/exp-001",
            headers={"X-Actor-Id": "12345"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "ACTOR_INVALID"


class TestRBACForbidden:
    """Test 403 RBAC_FORBIDDEN when actor lacks permission."""

    def test_no_permission_returns_403(self, tmp_path: Path):
        """Actor without required permission should get 403."""
        # Create bundle with viewer role (only expense.read)
        create_minimal_bundle(tmp_path, [
            {"name": "viewer", "permissions": ["expense.read"]}
        ])
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # POST requires expense.create - viewer doesn't have it
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "viewer",
            },
        )
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "RBAC_FORBIDDEN"
        assert data["message"] == "Forbidden"

    def test_no_roles_returns_403(self, tmp_path: Path):
        """Actor without any roles should get 403."""
        create_minimal_bundle(tmp_path, [
            {"name": "viewer", "permissions": ["expense.read"]}
        ])
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # Actor has no roles - should be forbidden
        response = client.get(
            "/finance/expenses/exp-001",
            headers={"X-Actor-Id": actor_id},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "RBAC_FORBIDDEN"


class TestRBACAllowed:
    """Test 200 when actor has required permission."""

    def test_with_permission_returns_200(self, tmp_path: Path):
        """Actor with required permission should get 200."""
        # Create bundle with analyst role (expense.create + expense.read)
        create_minimal_bundle(tmp_path, [
            {"name": "analyst", "permissions": ["expense.create", "expense.read"]}
        ])
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # POST with analyst role
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert data["actor_id"] == actor_id

        # GET with analyst role
        response = client.get(
            "/finance/expenses/exp-001",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "retrieved"
        assert data["id"] == "exp-001"

    def test_viewer_can_read_not_create(self, tmp_path: Path):
        """Viewer role can read but not create expenses."""
        create_minimal_bundle(tmp_path, [
            {"name": "viewer", "permissions": ["expense.read"]}
        ])
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # GET should succeed
        response = client.get(
            "/finance/expenses/exp-001",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "viewer",
            },
        )
        assert response.status_code == 200

        # POST should fail
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "viewer",
            },
        )
        assert response.status_code == 403

    def test_multiple_roles_combined(self, tmp_path: Path):
        """Actor with multiple roles gets combined permissions."""
        create_minimal_bundle(tmp_path, [
            {"name": "reader", "permissions": ["expense.read"]},
            {"name": "creator", "permissions": ["expense.create"]},
        ])
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # Actor with both roles can do both
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "reader,creator",
            },
        )
        assert response.status_code == 200

        response = client.get(
            "/finance/expenses/exp-001",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "reader,creator",
            },
        )
        assert response.status_code == 200


class TestSafeModeInteraction:
    """Test RBAC behavior when runtime is in SAFE_MODE."""

    def test_safe_mode_returns_503(self, tmp_path: Path):
        """When in SAFE_MODE, finance endpoints should return 503."""
        # Don't load bundle - runtime stays in default state
        # Set SAFE_MODE manually
        runtime_state.set_safe_mode("BUNDLE_MANIFEST_MISSING", ["Test"])

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # Even with valid actor, should get 503
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "admin",
            },
        )
        assert response.status_code == 503
        data = response.json()
        assert data["code"] == "SAFE_MODE"

    def test_health_still_works_in_safe_mode(self):
        """Health endpoint should work in SAFE_MODE (3.1 behavior)."""
        runtime_state.set_safe_mode("BUNDLE_MANIFEST_MISSING", ["Test"])

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["mode"] == "SAFE_MODE"
        assert data["reason_code"] == "BUNDLE_MANIFEST_MISSING"


class TestActorContextParsing:
    """Test actor context parsing edge cases."""

    def test_valid_uuid_formats(self, tmp_path: Path):
        """Various valid UUID formats should be accepted."""
        create_minimal_bundle(tmp_path, [
            {"name": "admin", "permissions": ["expense.read"]}
        ])
        load_bundle(tmp_path)

        client = TestClient(app)

        # Standard UUID
        response = client.get(
            "/finance/expenses/exp-001",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
        )
        assert response.status_code == 200

        # UUID without dashes (should fail - not standard format)
        response = client.get(
            "/finance/expenses/exp-001",
            headers={
                "X-Actor-Id": "550e8400e29b41d4a716446655440000",
                "X-Actor-Roles": "admin",
            },
        )
        # Python's uuid.UUID accepts this format
        assert response.status_code == 200

    def test_tenant_id_optional(self, tmp_path: Path):
        """X-Tenant-Id is optional and doesn't affect RBAC."""
        create_minimal_bundle(tmp_path, [
            {"name": "admin", "permissions": ["expense.read"]}
        ])
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())
        # Use default institution ID (always valid) for tenant_id
        tenant_id = "00000000-0000-0000-0000-000000000000"

        # With tenant ID (using default institution)
        response = client.get(
            "/finance/expenses/exp-001",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "admin",
                "X-Tenant-Id": tenant_id,
            },
        )
        assert response.status_code == 200

        # Without tenant ID (defaults to same institution)
        response = client.get(
            "/finance/expenses/exp-001",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "admin",
            },
        )
        assert response.status_code == 200

    def test_roles_parsing(self, tmp_path: Path):
        """Roles should be parsed correctly from comma-separated string."""
        create_minimal_bundle(tmp_path, [
            {"name": "role_a", "permissions": ["expense.create"]},
            {"name": "role_b", "permissions": ["expense.read"]},
        ])
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # Comma-separated roles
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "role_a, role_b",  # With space
            },
        )
        assert response.status_code == 200

        # Roles with extra spaces
        response = client.get(
            "/finance/expenses/exp-001",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "  role_b  ,  role_a  ",
            },
        )
        assert response.status_code == 200
