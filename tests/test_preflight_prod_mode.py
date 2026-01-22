"""Tests for GAP 5 preflight production mode requirements.

Tests that ENGINE_INSTALL_MODE=prod enforces:
- ENGINE_ISE_ADMIN_TOKEN must be set
- ENGINE_AUTH_MODE must be 'strict'
"""

import os
import pytest
from unittest.mock import patch

from engine.core.preflight import (
    check_prod_mode_requirements,
    run_preflight_checks,
    PreflightResult,
)
from engine.core.errors import (
    PREFLIGHT_ADMIN_TOKEN_MISSING,
    PREFLIGHT_AUTH_MODE_INSECURE,
)


class TestCheckProdModeRequirements:
    """Tests for check_prod_mode_requirements()."""

    def test_dev_mode_skips_checks(self):
        """Dev mode should skip all production checks."""
        # Clear any existing env vars
        env = {
            "ENGINE_INSTALL_MODE": "dev",
        }
        with patch.dict(os.environ, env, clear=True):
            result = check_prod_mode_requirements()

        assert result.ok is True
        assert result.code is None

    def test_dev_mode_default_skips_checks(self):
        """Default (no ENGINE_INSTALL_MODE) should skip production checks."""
        # Ensure ENGINE_INSTALL_MODE is not set
        env = {}
        with patch.dict(os.environ, env, clear=True):
            # Remove if present
            os.environ.pop("ENGINE_INSTALL_MODE", None)
            result = check_prod_mode_requirements()

        assert result.ok is True

    def test_prod_mode_no_admin_token_fails(self):
        """Prod mode without ENGINE_ISE_ADMIN_TOKEN should fail."""
        env = {
            "ENGINE_INSTALL_MODE": "prod",
            "ENGINE_AUTH_MODE": "strict",
            # ENGINE_ISE_ADMIN_TOKEN intentionally not set
        }
        with patch.dict(os.environ, env, clear=True):
            result = check_prod_mode_requirements()

        assert result.ok is False
        assert result.code == PREFLIGHT_ADMIN_TOKEN_MISSING
        assert "ENGINE_ISE_ADMIN_TOKEN" in result.message

    def test_prod_mode_auth_mode_dev_fails(self):
        """Prod mode with ENGINE_AUTH_MODE=dev should fail."""
        env = {
            "ENGINE_INSTALL_MODE": "prod",
            "ENGINE_ISE_ADMIN_TOKEN": "test-token-123",
            "ENGINE_AUTH_MODE": "dev",
        }
        with patch.dict(os.environ, env, clear=True):
            result = check_prod_mode_requirements()

        assert result.ok is False
        assert result.code == PREFLIGHT_AUTH_MODE_INSECURE
        assert "ENGINE_AUTH_MODE" in result.message
        assert "dev" in result.message

    def test_prod_mode_auth_mode_default_fails(self):
        """Prod mode with default auth mode (dev) should fail."""
        env = {
            "ENGINE_INSTALL_MODE": "prod",
            "ENGINE_ISE_ADMIN_TOKEN": "test-token-123",
            # ENGINE_AUTH_MODE not set, defaults to "dev"
        }
        with patch.dict(os.environ, env, clear=True):
            result = check_prod_mode_requirements()

        assert result.ok is False
        assert result.code == PREFLIGHT_AUTH_MODE_INSECURE

    def test_prod_mode_all_requirements_met_passes(self):
        """Prod mode with all requirements should pass."""
        env = {
            "ENGINE_INSTALL_MODE": "prod",
            "ENGINE_ISE_ADMIN_TOKEN": "test-token-123",
            "ENGINE_AUTH_MODE": "strict",
        }
        with patch.dict(os.environ, env, clear=True):
            result = check_prod_mode_requirements()

        assert result.ok is True
        assert result.code is None

    def test_prod_mode_case_insensitive(self):
        """ENGINE_INSTALL_MODE should be case insensitive."""
        env = {
            "ENGINE_INSTALL_MODE": "PROD",
            "ENGINE_ISE_ADMIN_TOKEN": "test-token-123",
            "ENGINE_AUTH_MODE": "strict",
        }
        with patch.dict(os.environ, env, clear=True):
            result = check_prod_mode_requirements()

        assert result.ok is True

    def test_prod_mode_auth_mode_case_insensitive(self):
        """ENGINE_AUTH_MODE=strict should be case insensitive."""
        env = {
            "ENGINE_INSTALL_MODE": "prod",
            "ENGINE_ISE_ADMIN_TOKEN": "test-token-123",
            "ENGINE_AUTH_MODE": "STRICT",
        }
        with patch.dict(os.environ, env, clear=True):
            result = check_prod_mode_requirements()

        assert result.ok is True

    def test_error_details_provided(self):
        """Error results should include helpful details."""
        env = {
            "ENGINE_INSTALL_MODE": "prod",
            # Missing token
        }
        with patch.dict(os.environ, env, clear=True):
            result = check_prod_mode_requirements()

        assert result.ok is False
        assert result.details is not None
        assert len(result.details) > 0


class TestRunPreflightChecksWithProdMode:
    """Tests for run_preflight_checks() including prod mode checks."""

    @pytest.fixture
    def mock_session_secret(self):
        """Provide a valid session secret."""
        with patch.dict(os.environ, {
            "ENGINE_CONSOLE_SESSION_SECRET": "a" * 32,
        }):
            yield

    @pytest.fixture
    def mock_no_multi_tenant(self):
        """Mock no multi-tenant mode active."""
        with patch(
            "engine.core.preflight.is_multi_tenant_mode_active",
            return_value=False,
        ):
            yield

    def test_preflight_includes_prod_check(
        self, mock_session_secret, mock_no_multi_tenant
    ):
        """run_preflight_checks should include prod mode check."""
        env = {
            "ENGINE_INSTALL_MODE": "prod",
            "ENGINE_CONSOLE_SESSION_SECRET": "a" * 32,
            # Missing admin token
        }
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "engine.core.preflight.is_multi_tenant_mode_active",
                return_value=False,
            ):
                result = run_preflight_checks()

        assert result.ok is False
        assert result.code == PREFLIGHT_ADMIN_TOKEN_MISSING

    def test_preflight_passes_in_dev_mode(
        self, mock_session_secret, mock_no_multi_tenant
    ):
        """run_preflight_checks should pass in dev mode without prod requirements."""
        env = {
            "ENGINE_INSTALL_MODE": "dev",
            "ENGINE_CONSOLE_SESSION_SECRET": "a" * 32,
            # No admin token needed in dev mode
        }
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "engine.core.preflight.is_multi_tenant_mode_active",
                return_value=False,
            ):
                result = run_preflight_checks()

        assert result.ok is True

    def test_preflight_passes_with_all_prod_requirements(
        self, mock_session_secret, mock_no_multi_tenant
    ):
        """run_preflight_checks should pass with all prod requirements met."""
        env = {
            "ENGINE_INSTALL_MODE": "prod",
            "ENGINE_CONSOLE_SESSION_SECRET": "a" * 32,
            "ENGINE_ISE_ADMIN_TOKEN": "test-token-123",
            "ENGINE_AUTH_MODE": "strict",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "engine.core.preflight.is_multi_tenant_mode_active",
                return_value=False,
            ):
                result = run_preflight_checks()

        assert result.ok is True

    def test_session_secret_check_runs_before_prod_check(
        self, mock_no_multi_tenant
    ):
        """Session secret should be checked before prod mode requirements."""
        env = {
            "ENGINE_INSTALL_MODE": "prod",
            # No session secret
            # No admin token
        }
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "engine.core.preflight.is_multi_tenant_mode_active",
                return_value=False,
            ):
                result = run_preflight_checks()

        # Should fail on session secret first
        assert result.ok is False
        assert "SESSION_SECRET" in result.code


class TestErrorCodeConstants:
    """Tests for error code definitions."""

    def test_preflight_admin_token_missing_defined(self):
        """PREFLIGHT_ADMIN_TOKEN_MISSING should be defined."""
        assert PREFLIGHT_ADMIN_TOKEN_MISSING == "PREFLIGHT_ADMIN_TOKEN_MISSING"

    def test_preflight_auth_mode_insecure_defined(self):
        """PREFLIGHT_AUTH_MODE_INSECURE should be defined."""
        assert PREFLIGHT_AUTH_MODE_INSECURE == "PREFLIGHT_AUTH_MODE_INSECURE"
