"""Tests for ISE compile/release authentication."""

import json
import os
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from engine.api.server import app
from engine.ise import errors


# Valid IDL for tests
VALID_IDL = json.dumps({
    "system": "finance-pilot",
    "version": "1.0.0",
    "entities": [
        {
            "type": "expense",
            "name": "Expense",
            "fields": [
                {"name": "amount", "type": "number", "required": True},
            ],
        }
    ],
    "actors": [
        {"role": "employee", "permissions": [{"resource": "expense", "actions": ["create"]}]},
    ],
    "usecases": [],
})


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


def _get_error_code(data: dict) -> str:
    """Extract error code from response data.

    The error envelope may have different structures depending on
    how the exception was raised.
    """
    # Direct error_code field
    if "error_code" in data:
        return data["error_code"]
    # Wrapped in code field (from server exception handler)
    if "code" in data:
        return data["code"]
    # Nested in status field (from ReleaseResult)
    if "status" in data and data.get("error"):
        return data["error"].get("code", "")
    return ""


class TestAuthNoToken:
    """Test authentication when no token is configured."""

    def test_no_env_token_returns_401(self, client, monkeypatch):
        """If ENGINE_ISE_ADMIN_TOKEN is not set, deny all requests."""
        # Ensure env var is not set
        monkeypatch.delenv("ENGINE_ISE_ADMIN_TOKEN", raising=False)

        response = client.post(
            "/ise/compile/release",
            json={"idl": VALID_IDL, "bundle_name": "test"},
        )

        assert response.status_code == 401
        # Verify ISE_ADMIN_UNAUTHORIZED is somewhere in response
        assert errors.ISE_ADMIN_UNAUTHORIZED in str(response.json())

    def test_no_env_token_with_header_returns_401(self, client, monkeypatch):
        """If ENGINE_ISE_ADMIN_TOKEN is not set, even with header, deny."""
        monkeypatch.delenv("ENGINE_ISE_ADMIN_TOKEN", raising=False)

        response = client.post(
            "/ise/compile/release",
            json={"idl": VALID_IDL, "bundle_name": "test"},
            headers={"X-Admin-Token": "some-token"},
        )

        assert response.status_code == 401


class TestAuthWrongToken:
    """Test authentication with wrong token."""

    def test_wrong_token_returns_401(self, client, monkeypatch):
        """Wrong token should return 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-secret-token")

        response = client.post(
            "/ise/compile/release",
            json={"idl": VALID_IDL, "bundle_name": "test"},
            headers={"X-Admin-Token": "wrong-token"},
        )

        assert response.status_code == 401
        assert errors.ISE_ADMIN_UNAUTHORIZED in str(response.json())

    def test_empty_token_returns_401(self, client, monkeypatch):
        """Empty token should return 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-secret-token")

        response = client.post(
            "/ise/compile/release",
            json={"idl": VALID_IDL, "bundle_name": "test"},
            headers={"X-Admin-Token": ""},
        )

        assert response.status_code == 401


class TestAuthMissingHeader:
    """Test authentication with missing header."""

    def test_missing_header_returns_401(self, client, monkeypatch):
        """Missing X-Admin-Token header should return 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-secret-token")

        response = client.post(
            "/ise/compile/release",
            json={"idl": VALID_IDL, "bundle_name": "test"},
            # No X-Admin-Token header
        )

        assert response.status_code == 401
        assert errors.ISE_ADMIN_UNAUTHORIZED in str(response.json())


class TestAuthCorrectToken:
    """Test authentication with correct token."""

    def test_correct_token_passes_auth(self, client, monkeypatch, tmp_path):
        """Correct token should pass authentication (may fail on scripts)."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-secret-token")
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        # Create mock scripts that don't exist - will fail with ISE_SCRIPT_UNAVAILABLE
        # but this proves auth passed
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", "/nonexistent/verify.sh")

        response = client.post(
            "/ise/compile/release",
            json={"idl": VALID_IDL, "bundle_name": "test"},
            headers={"X-Admin-Token": "correct-secret-token"},
        )

        # Should NOT be 401 - auth passed
        assert response.status_code != 401

        # Should be 500 (script unavailable) which proves auth passed
        assert response.status_code == 500
        assert errors.ISE_SCRIPT_UNAVAILABLE in str(response.json())

    def test_token_case_sensitive(self, client, monkeypatch):
        """Token comparison should be case-sensitive."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "Secret-Token")

        response = client.post(
            "/ise/compile/release",
            json={"idl": VALID_IDL, "bundle_name": "test"},
            headers={"X-Admin-Token": "secret-token"},  # lowercase
        )

        assert response.status_code == 401


class TestVerifyAdminTokenFunction:
    """Test verify_admin_token function directly."""

    def test_verify_no_env_no_token(self, monkeypatch):
        """No env, no token -> False."""
        from engine.ise.release import verify_admin_token
        monkeypatch.delenv("ENGINE_ISE_ADMIN_TOKEN", raising=False)

        assert verify_admin_token(None) is False
        assert verify_admin_token("") is False
        assert verify_admin_token("any-token") is False

    def test_verify_env_set_no_token(self, monkeypatch):
        """Env set, no token -> False."""
        from engine.ise.release import verify_admin_token
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "secret")

        assert verify_admin_token(None) is False
        assert verify_admin_token("") is False

    def test_verify_env_set_wrong_token(self, monkeypatch):
        """Env set, wrong token -> False."""
        from engine.ise.release import verify_admin_token
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct")

        assert verify_admin_token("wrong") is False

    def test_verify_env_set_correct_token(self, monkeypatch):
        """Env set, correct token -> True."""
        from engine.ise.release import verify_admin_token
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct")

        assert verify_admin_token("correct") is True
