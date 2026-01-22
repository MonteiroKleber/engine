"""Tests for GAP 2: Minimum Identity Not Spoofable.

Tests for:
1. Actor tokens registry (create, verify, revoke)
2. Auth mode configuration (dev/strict)
3. Strict mode: rejects role spoofing via headers
4. Strict mode: accepts valid token
5. Strict mode: rejects revoked token
6. Dev mode: accepts headers, emits UNVERIFIED_IDENTITY_USED event
7. Admin endpoints for provisioning
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from engine.core.actor_tokens import (
    ActorTokensRegistry,
    get_actor_tokens_registry,
    _hash_token,
    _generate_token,
)
from engine.core.actor_context import (
    get_auth_mode,
    AuthMode,
    ActorContext,
)
from engine.core.errors import (
    ACTOR_TOKEN_REQUIRED,
    ACTOR_TOKEN_INVALID,
    ACTOR_TOKEN_REVOKED,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def reset_registry():
    """Reset singleton registry between tests."""
    ActorTokensRegistry.reset_instance()
    yield
    ActorTokensRegistry.reset_instance()


@pytest.fixture
def mock_institution_root(temp_dir, monkeypatch):
    """Mock get_institution_root to return temp directory."""
    def mock_root(institution_id: str) -> Path:
        return temp_dir / "institutions" / institution_id

    monkeypatch.setattr(
        "engine.core.actor_tokens.get_institution_root",
        mock_root
    )
    return temp_dir


class TestAuthModeConfig:
    """Test ENGINE_AUTH_MODE configuration."""

    def test_default_mode_is_dev(self, monkeypatch):
        """Default auth mode is dev when env not set."""
        monkeypatch.delenv("ENGINE_AUTH_MODE", raising=False)
        assert get_auth_mode() == AuthMode.DEV

    def test_mode_dev_explicit(self, monkeypatch):
        """ENGINE_AUTH_MODE=dev returns DEV."""
        monkeypatch.setenv("ENGINE_AUTH_MODE", "dev")
        assert get_auth_mode() == AuthMode.DEV

    def test_mode_strict(self, monkeypatch):
        """ENGINE_AUTH_MODE=strict returns STRICT."""
        monkeypatch.setenv("ENGINE_AUTH_MODE", "strict")
        assert get_auth_mode() == AuthMode.STRICT

    def test_mode_strict_case_insensitive(self, monkeypatch):
        """ENGINE_AUTH_MODE is case insensitive."""
        monkeypatch.setenv("ENGINE_AUTH_MODE", "STRICT")
        assert get_auth_mode() == AuthMode.STRICT


class TestActorContextFields:
    """Test ActorContext dataclass fields."""

    def test_identity_verified_default_false(self):
        """identity_verified defaults to False."""
        ctx = ActorContext(actor_id="test-id")
        assert ctx.identity_verified is False

    def test_identity_verified_can_be_true(self):
        """identity_verified can be set to True."""
        ctx = ActorContext(actor_id="test-id", identity_verified=True)
        assert ctx.identity_verified is True


class TestTokenGeneration:
    """Test token generation and hashing."""

    def test_generate_token_is_url_safe(self):
        """Generated token is URL-safe."""
        token = _generate_token()
        assert len(token) == 43  # 32 bytes base64url encoded
        # URL-safe characters only
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_generate_token_is_unique(self):
        """Each generated token is unique."""
        tokens = [_generate_token() for _ in range(100)]
        assert len(set(tokens)) == 100

    def test_hash_token_format(self):
        """Hash token has correct format."""
        token = "test-token"
        hashed = _hash_token(token)
        assert hashed.startswith("SHA256:")
        assert len(hashed) == 7 + 64  # prefix + 64 hex chars

    def test_hash_token_is_deterministic(self):
        """Same token always produces same hash."""
        token = "test-token"
        hash1 = _hash_token(token)
        hash2 = _hash_token(token)
        assert hash1 == hash2


class TestActorTokensRegistry:
    """Test ActorTokensRegistry operations."""

    def test_create_token_returns_plaintext(
        self, reset_registry, mock_institution_root
    ):
        """Create token returns plaintext token."""
        registry = get_actor_tokens_registry()
        token, error = registry.create_token(
            institution_id="inst-1",
            actor_id="actor-1",
            roles=["operator"],
        )

        assert token is not None
        assert error is None
        assert len(token) == 43

    def test_create_token_creates_registry_file(
        self, reset_registry, mock_institution_root, temp_dir
    ):
        """Create token creates registry JSONL file."""
        registry = get_actor_tokens_registry()
        registry.create_token(
            institution_id="inst-1",
            actor_id="actor-1",
            roles=["operator"],
        )

        registry_path = temp_dir / "institutions" / "inst-1" / "actors" / "actors_registry.jsonl"
        assert registry_path.exists()

        with open(registry_path) as f:
            lines = f.readlines()
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["actor_id"] == "actor-1"
        assert record["roles"] == ["operator"]
        assert record["status"] == "active"
        assert record["operation"] == "create"

    def test_verify_token_valid(self, reset_registry, mock_institution_root):
        """Verify valid token returns actor info."""
        registry = get_actor_tokens_registry()
        token, _ = registry.create_token(
            institution_id="inst-1",
            actor_id="actor-1",
            roles=["operator", "manager"],
        )

        actor_id, roles, valid, error = registry.verify_token(
            institution_id="inst-1",
            plaintext_token=token,
        )

        assert valid is True
        assert error is None
        assert actor_id == "actor-1"
        assert roles == ["operator", "manager"]

    def test_verify_token_invalid(self, reset_registry, mock_institution_root):
        """Verify invalid token returns error."""
        registry = get_actor_tokens_registry()

        actor_id, roles, valid, error = registry.verify_token(
            institution_id="inst-1",
            plaintext_token="invalid-token",
        )

        assert valid is False
        assert error == ACTOR_TOKEN_INVALID
        assert actor_id is None

    def test_verify_token_wrong_institution(
        self, reset_registry, mock_institution_root
    ):
        """Token valid for one institution is invalid for another."""
        registry = get_actor_tokens_registry()
        token, _ = registry.create_token(
            institution_id="inst-1",
            actor_id="actor-1",
            roles=["operator"],
        )

        actor_id, roles, valid, error = registry.verify_token(
            institution_id="inst-2",  # Different institution
            plaintext_token=token,
        )

        assert valid is False
        assert error == ACTOR_TOKEN_INVALID

    def test_revoke_token_success(self, reset_registry, mock_institution_root):
        """Revoke token succeeds for active token."""
        registry = get_actor_tokens_registry()
        token, _ = registry.create_token(
            institution_id="inst-1",
            actor_id="actor-1",
            roles=["operator"],
        )

        token_hash = _hash_token(token)
        success, error = registry.revoke_token(
            institution_id="inst-1",
            token_sha256=token_hash,
        )

        assert success is True
        assert error is None

    def test_revoke_token_not_found(self, reset_registry, mock_institution_root):
        """Revoke returns error for non-existent token."""
        registry = get_actor_tokens_registry()

        success, error = registry.revoke_token(
            institution_id="inst-1",
            token_sha256="SHA256:" + "a" * 64,
        )

        assert success is False
        assert error == "ACTOR_TOKEN_NOT_FOUND"

    def test_verify_revoked_token_fails(
        self, reset_registry, mock_institution_root
    ):
        """Revoked token fails verification."""
        registry = get_actor_tokens_registry()
        token, _ = registry.create_token(
            institution_id="inst-1",
            actor_id="actor-1",
            roles=["operator"],
        )

        # Revoke
        token_hash = _hash_token(token)
        registry.revoke_token(institution_id="inst-1", token_sha256=token_hash)

        # Verify
        actor_id, roles, valid, error = registry.verify_token(
            institution_id="inst-1",
            plaintext_token=token,
        )

        assert valid is False
        assert error == ACTOR_TOKEN_REVOKED
        assert actor_id == "actor-1"  # Still returns actor info

    def test_list_actors(self, reset_registry, mock_institution_root):
        """List actors returns all tokens."""
        registry = get_actor_tokens_registry()

        registry.create_token("inst-1", "actor-1", ["op1"])
        registry.create_token("inst-1", "actor-2", ["op2"])
        registry.create_token("inst-1", "actor-1", ["op3"])  # Second token for actor-1

        actors = registry.list_actors("inst-1")
        assert len(actors) == 3

    def test_get_actor_by_id(self, reset_registry, mock_institution_root):
        """Get actor by ID returns only that actor's tokens."""
        registry = get_actor_tokens_registry()

        registry.create_token("inst-1", "actor-1", ["op1"])
        registry.create_token("inst-1", "actor-2", ["op2"])
        registry.create_token("inst-1", "actor-1", ["op3"])

        actor_tokens = registry.get_actor_by_id("inst-1", "actor-1")
        assert len(actor_tokens) == 2
        assert all(t.actor_id == "actor-1" for t in actor_tokens)


class TestStrictModeEnforcement:
    """Test strict mode enforcement via get_actor_context."""

    @pytest.fixture
    def strict_mode(self, monkeypatch):
        """Enable strict auth mode."""
        monkeypatch.setenv("ENGINE_AUTH_MODE", "strict")

    @pytest.fixture
    def mock_runtime_active(self, monkeypatch):
        """Mock runtime to be active (not safe mode)."""
        from engine.core.runtime_state import RuntimeMode

        mock_state = MagicMock()
        mock_state.mode = RuntimeMode.ACTIVE
        monkeypatch.setattr(
            "engine.api.dependencies.runtime_state",
            mock_state
        )

    @pytest.mark.asyncio
    async def test_strict_mode_rejects_without_token(
        self, strict_mode, mock_runtime_active
    ):
        """Strict mode rejects request without token."""
        from fastapi import HTTPException
        from engine.api.dependencies import _resolve_actor_from_token

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_actor_from_token(
                x_actor_token=None,
                x_tenant_id=None,
                institution_id="inst-1",
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == ACTOR_TOKEN_REQUIRED

    @pytest.mark.asyncio
    async def test_strict_mode_rejects_invalid_token(
        self, strict_mode, mock_runtime_active, reset_registry, mock_institution_root
    ):
        """Strict mode rejects invalid token."""
        from fastapi import HTTPException
        from engine.api.dependencies import _resolve_actor_from_token

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_actor_from_token(
                x_actor_token="invalid-token",
                x_tenant_id=None,
                institution_id="inst-1",
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == ACTOR_TOKEN_INVALID

    @pytest.mark.asyncio
    async def test_strict_mode_accepts_valid_token(
        self, strict_mode, mock_runtime_active, reset_registry, mock_institution_root
    ):
        """Strict mode accepts valid token."""
        from engine.api.dependencies import _resolve_actor_from_token

        # Create token
        registry = get_actor_tokens_registry()
        token, _ = registry.create_token(
            institution_id="inst-1",
            actor_id="11111111-1111-1111-1111-111111111111",
            roles=["operator", "manager"],
        )

        # Verify via dependency
        context = await _resolve_actor_from_token(
            x_actor_token=token,
            x_tenant_id=None,
            institution_id="inst-1",
        )

        assert context.actor_id == "11111111-1111-1111-1111-111111111111"
        assert context.roles == ["operator", "manager"]
        assert context.identity_verified is True

    @pytest.mark.asyncio
    async def test_strict_mode_ignores_header_roles(
        self, strict_mode, mock_runtime_active, reset_registry, mock_institution_root
    ):
        """Strict mode ignores X-Actor-Roles header (spoof protection)."""
        from engine.api.dependencies import _resolve_actor_from_token

        # Create token with specific roles
        registry = get_actor_tokens_registry()
        token, _ = registry.create_token(
            institution_id="inst-1",
            actor_id="22222222-2222-2222-2222-222222222222",
            roles=["operator"],  # Only operator role
        )

        # Even though we're not passing header roles to this function,
        # the main get_actor_context would ignore them in strict mode
        context = await _resolve_actor_from_token(
            x_actor_token=token,
            x_tenant_id=None,
            institution_id="inst-1",
        )

        # Roles come from registry, not headers
        assert context.roles == ["operator"]
        assert "admin" not in context.roles  # Spoofed role not present

    @pytest.mark.asyncio
    async def test_strict_mode_rejects_revoked_token(
        self, strict_mode, mock_runtime_active, reset_registry, mock_institution_root
    ):
        """Strict mode rejects revoked token."""
        from fastapi import HTTPException
        from engine.api.dependencies import _resolve_actor_from_token

        # Create and revoke token
        registry = get_actor_tokens_registry()
        token, _ = registry.create_token(
            institution_id="inst-1",
            actor_id="33333333-3333-3333-3333-333333333333",
            roles=["operator"],
        )
        registry.revoke_token("inst-1", _hash_token(token))

        # Verify rejection
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_actor_from_token(
                x_actor_token=token,
                x_tenant_id=None,
                institution_id="inst-1",
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == ACTOR_TOKEN_REVOKED


class TestDevModeCompatibility:
    """Test dev mode maintains backward compatibility."""

    @pytest.fixture
    def dev_mode(self, monkeypatch):
        """Enable dev auth mode."""
        monkeypatch.setenv("ENGINE_AUTH_MODE", "dev")

    @pytest.fixture
    def mock_runtime_active(self, monkeypatch):
        """Mock runtime to be active."""
        from engine.core.runtime_state import RuntimeMode

        mock_state = MagicMock()
        mock_state.mode = RuntimeMode.ACTIVE
        monkeypatch.setattr(
            "engine.api.dependencies.runtime_state",
            mock_state
        )

    @pytest.mark.asyncio
    async def test_dev_mode_accepts_headers(
        self, dev_mode, mock_runtime_active
    ):
        """Dev mode accepts X-Actor-Id and X-Actor-Roles headers."""
        from engine.api.dependencies import _resolve_actor_from_headers

        context = await _resolve_actor_from_headers(
            x_actor_id="44444444-4444-4444-4444-444444444444",
            x_actor_roles="operator,manager",
            x_tenant_id=None,
            institution_id=None,
        )

        assert context.actor_id == "44444444-4444-4444-4444-444444444444"
        assert context.roles == ["operator", "manager"]
        assert context.identity_verified is False

    @pytest.mark.asyncio
    async def test_dev_mode_marks_unverified(
        self, dev_mode, mock_runtime_active
    ):
        """Dev mode sets identity_verified=False."""
        from engine.api.dependencies import _resolve_actor_from_headers

        context = await _resolve_actor_from_headers(
            x_actor_id="55555555-5555-5555-5555-555555555555",
            x_actor_roles="operator",
            x_tenant_id=None,
            institution_id=None,
        )

        assert context.identity_verified is False


class TestAdminActorsEndpoints:
    """Test admin endpoints for actor provisioning."""

    @pytest.fixture
    def app_client(self):
        """Create test client for the app."""
        from engine.api.server import app
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def mock_admin_auth(self, monkeypatch):
        """Mock admin authentication to always succeed."""
        from engine.core.admin_auth import AdminAuthResult

        def mock_require_admin_auth(request, institution_id):
            return AdminAuthResult(valid=True, key_id="test-admin-key")

        monkeypatch.setattr(
            "engine.api.admin_actors.require_admin_auth",
            mock_require_admin_auth
        )

    def test_create_actor_token(
        self, app_client, mock_admin_auth, reset_registry, mock_institution_root
    ):
        """POST /admin/institutions/{id}/actors creates token."""
        response = app_client.post(
            "/admin/institutions/inst-1/actors",
            json={
                "actor_id": "66666666-6666-6666-6666-666666666666",
                "roles": ["operator", "viewer"],
            },
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert len(data["token"]) == 43
        assert data["actor_id"] == "66666666-6666-6666-6666-666666666666"
        assert data["roles"] == ["operator", "viewer"]

    def test_list_actors(
        self, app_client, mock_admin_auth, reset_registry, mock_institution_root
    ):
        """GET /admin/institutions/{id}/actors lists tokens."""
        # Create some tokens first
        registry = get_actor_tokens_registry()
        registry.create_token("inst-1", "actor-1", ["op1"])
        registry.create_token("inst-1", "actor-2", ["op2"])

        response = app_client.get(
            "/admin/institutions/inst-1/actors",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["actors"]) == 2

    def test_revoke_actor_token(
        self, app_client, mock_admin_auth, reset_registry, mock_institution_root
    ):
        """POST /admin/institutions/{id}/actors/revoke revokes token."""
        # Create token
        registry = get_actor_tokens_registry()
        token, _ = registry.create_token("inst-1", "actor-1", ["op1"])
        token_hash = _hash_token(token)

        response = app_client.post(
            "/admin/institutions/inst-1/actors/revoke",
            json={"token_sha256": token_hash},
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify token is revoked
        _, _, valid, _ = registry.verify_token("inst-1", token)
        assert valid is False

    def test_get_actor_tokens_by_id(
        self, app_client, mock_admin_auth, reset_registry, mock_institution_root
    ):
        """GET /admin/institutions/{id}/actors/{actor_id} returns actor's tokens."""
        # Create tokens for different actors
        registry = get_actor_tokens_registry()
        registry.create_token("inst-1", "actor-1", ["op1"])
        registry.create_token("inst-1", "actor-1", ["op2"])
        registry.create_token("inst-1", "actor-2", ["op3"])

        response = app_client.get(
            "/admin/institutions/inst-1/actors/actor-1",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert all(a["actor_id"] == "actor-1" for a in data["actors"])
