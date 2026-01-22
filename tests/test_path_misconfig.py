"""Tests for multi-tenant path misconfiguration detection (Etapa 2.6).

These tests verify that:
1. When require_institution_header_for_runtime=true, absolute paths for
   ENGINE_LEDGER_PATH and ENGINE_STATE_STORE_DIR are blocked.
2. Relative paths work correctly in multi-tenant mode.
3. Single-tenant/dev mode allows absolute paths (for backward compatibility).
"""

import os
import pytest
from pathlib import Path

from engine.core.preflight import (
    check_path_isolation,
    is_multi_tenant_mode_active,
    run_preflight_checks,
    PreflightResult,
    CRITICAL_PATH_ENVS,
)
from engine.core.errors import (
    PATH_MISCONFIG_ABSOLUTE_LEDGER,
    PATH_MISCONFIG_ABSOLUTE_STATE_STORE,
)
from engine.core.institutions import reset_registry
from engine.core.institution_config import (
    reset_config_cache,
    save_active_config,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    # Use temp paths for data directories
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")

    # Clear any existing ENV overrides for critical paths
    monkeypatch.delenv("ENGINE_LEDGER_PATH", raising=False)
    monkeypatch.delenv("ENGINE_STATE_STORE_DIR", raising=False)

    reset_registry()
    reset_config_cache()

    yield

    reset_registry()
    reset_config_cache()


class TestCheckPathIsolationFunction:
    """Test the check_path_isolation function directly."""

    def test_allows_any_path_when_not_multi_tenant(self, monkeypatch):
        """When require_multi_tenant=False, any path is allowed."""
        # Set absolute paths
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "/var/log/audit.jsonl")
        monkeypatch.setenv("ENGINE_STATE_STORE_DIR", "/data/state")

        result = check_path_isolation(require_multi_tenant=False)
        assert result.ok is True

    def test_allows_relative_paths_in_multi_tenant(self, monkeypatch):
        """When require_multi_tenant=True, relative paths are allowed."""
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "audit_ledger.jsonl")
        monkeypatch.setenv("ENGINE_STATE_STORE_DIR", "state")

        result = check_path_isolation(require_multi_tenant=True)
        assert result.ok is True

    def test_allows_unset_paths_in_multi_tenant(self, monkeypatch):
        """When require_multi_tenant=True and paths are unset, it's allowed."""
        # Ensure paths are not set
        monkeypatch.delenv("ENGINE_LEDGER_PATH", raising=False)
        monkeypatch.delenv("ENGINE_STATE_STORE_DIR", raising=False)

        result = check_path_isolation(require_multi_tenant=True)
        assert result.ok is True

    def test_rejects_absolute_ledger_path_in_multi_tenant(self, monkeypatch):
        """When require_multi_tenant=True, absolute ENGINE_LEDGER_PATH is rejected."""
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "/var/log/audit.jsonl")

        result = check_path_isolation(require_multi_tenant=True)

        assert result.ok is False
        assert result.code == PATH_MISCONFIG_ABSOLUTE_LEDGER
        assert "ENGINE_LEDGER_PATH" in result.message
        assert "absolute" in result.message.lower()

    def test_rejects_absolute_state_store_dir_in_multi_tenant(self, monkeypatch):
        """When require_multi_tenant=True, absolute ENGINE_STATE_STORE_DIR is rejected."""
        monkeypatch.setenv("ENGINE_STATE_STORE_DIR", "/data/state")

        result = check_path_isolation(require_multi_tenant=True)

        assert result.ok is False
        assert result.code == PATH_MISCONFIG_ABSOLUTE_STATE_STORE
        assert "ENGINE_STATE_STORE_DIR" in result.message
        assert "absolute" in result.message.lower()

    def test_rejects_both_absolute_paths_reports_first(self, monkeypatch):
        """When both paths are absolute, reports the first one."""
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "/var/log/audit.jsonl")
        monkeypatch.setenv("ENGINE_STATE_STORE_DIR", "/data/state")

        result = check_path_isolation(require_multi_tenant=True)

        assert result.ok is False
        # Should report first critical ENV (ledger)
        assert result.code == PATH_MISCONFIG_ABSOLUTE_LEDGER
        # But details should contain both
        assert len(result.details) == 2
        assert any("ENGINE_LEDGER_PATH" in d for d in result.details)
        assert any("ENGINE_STATE_STORE_DIR" in d for d in result.details)


class TestIsMultiTenantModeActive:
    """Test the is_multi_tenant_mode_active function."""

    def test_returns_false_when_no_institutions(self, tmp_path):
        """Returns False when no institutions exist."""
        result = is_multi_tenant_mode_active()
        assert result is False

    def test_returns_false_when_no_institution_requires_header(self, tmp_path):
        """Returns False when no institution has require_institution_header_for_runtime=True."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        # Create institution with default config (require_header=False)
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "test-inst"},
        )
        assert response.status_code == 201

        result = is_multi_tenant_mode_active()
        assert result is False

    def test_returns_true_when_any_institution_requires_header(self, tmp_path):
        """Returns True when any institution has require_institution_header_for_runtime=True."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        # Create institution
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "multi-tenant-inst"},
        )
        assert response.status_code == 201
        inst_id = response.json()["institution_id"]

        # Set require_institution_header_for_runtime=True
        response = client.put(
            f"/admin/institutions/{inst_id}/config",
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

        # Clear config cache to pick up new config
        reset_config_cache()

        result = is_multi_tenant_mode_active()
        assert result is True


class TestRunPreflightChecks:
    """Test the run_preflight_checks integration function."""

    def test_passes_when_no_multi_tenant_mode(self, tmp_path, monkeypatch):
        """Passes when no institution requires multi-tenant mode."""
        # Set absolute paths (would fail in multi-tenant mode)
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "/var/log/audit.jsonl")
        # Session secret required for preflight
        monkeypatch.setenv("ENGINE_CONSOLE_SESSION_SECRET", "a" * 32)

        result = run_preflight_checks()
        assert result.ok is True

    def test_fails_when_multi_tenant_with_absolute_path(self, tmp_path, monkeypatch):
        """Fails when multi-tenant mode is active and absolute paths are set."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        # Create institution with multi-tenant mode
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "strict-inst"},
        )
        assert response.status_code == 201
        inst_id = response.json()["institution_id"]

        # Set require_institution_header_for_runtime=True
        response = client.put(
            f"/admin/institutions/{inst_id}/config",
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

        # Clear config cache
        reset_config_cache()

        # Now set an absolute path
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "/var/log/audit.jsonl")

        result = run_preflight_checks()
        assert result.ok is False
        assert result.code == PATH_MISCONFIG_ABSOLUTE_LEDGER


class TestCriticalPathEnvs:
    """Test that CRITICAL_PATH_ENVS contains the expected variables."""

    def test_ledger_path_is_critical(self):
        """ENGINE_LEDGER_PATH is in CRITICAL_PATH_ENVS."""
        assert "ENGINE_LEDGER_PATH" in CRITICAL_PATH_ENVS
        assert CRITICAL_PATH_ENVS["ENGINE_LEDGER_PATH"] == PATH_MISCONFIG_ABSOLUTE_LEDGER

    def test_state_store_dir_is_critical(self):
        """ENGINE_STATE_STORE_DIR is in CRITICAL_PATH_ENVS."""
        assert "ENGINE_STATE_STORE_DIR" in CRITICAL_PATH_ENVS
        assert CRITICAL_PATH_ENVS["ENGINE_STATE_STORE_DIR"] == PATH_MISCONFIG_ABSOLUTE_STATE_STORE


class TestPreflightResultDataclass:
    """Test the PreflightResult dataclass."""

    def test_ok_result(self):
        """Test creating an OK result."""
        result = PreflightResult(ok=True)
        assert result.ok is True
        assert result.code is None
        assert result.message is None
        assert result.details is None

    def test_error_result(self):
        """Test creating an error result."""
        result = PreflightResult(
            ok=False,
            code="TEST_ERROR",
            message="Test error message",
            details=["detail 1", "detail 2"],
        )
        assert result.ok is False
        assert result.code == "TEST_ERROR"
        assert result.message == "Test error message"
        assert len(result.details) == 2


class TestEdgeCases:
    """Test edge cases for path validation."""

    def test_windows_style_path_treated_as_relative(self, monkeypatch):
        """Windows-style paths without leading slash are treated as relative."""
        # On Unix, this would be treated as relative path (no leading /)
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "C:\\var\\audit.jsonl")

        result = check_path_isolation(require_multi_tenant=True)
        # This should pass because on Unix, it's not an absolute path
        assert result.ok is True

    def test_empty_string_path_allowed(self, monkeypatch):
        """Empty string path is treated as relative."""
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "")

        result = check_path_isolation(require_multi_tenant=True)
        assert result.ok is True

    def test_dot_relative_path_allowed(self, monkeypatch):
        """Dot-relative paths are allowed."""
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "./audit.jsonl")
        monkeypatch.setenv("ENGINE_STATE_STORE_DIR", "../data")

        result = check_path_isolation(require_multi_tenant=True)
        assert result.ok is True


class TestBackwardCompatibility:
    """Test backward compatibility with existing setups."""

    def test_single_tenant_mode_allows_absolute_paths(self, tmp_path, monkeypatch):
        """Single-tenant mode (no require_institution_header) allows absolute paths."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        # Create institution WITHOUT multi-tenant mode
        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "single-tenant-inst"},
        )
        assert response.status_code == 201

        # Set absolute paths
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "/var/log/audit.jsonl")
        monkeypatch.setenv("ENGINE_STATE_STORE_DIR", "/data/state")
        # Session secret required for preflight
        monkeypatch.setenv("ENGINE_CONSOLE_SESSION_SECRET", "a" * 32)

        # Preflight should pass
        result = run_preflight_checks()
        assert result.ok is True

    def test_mixed_mode_one_strict_fails_absolute_paths(self, tmp_path, monkeypatch):
        """If even ONE institution is strict, absolute paths are blocked for all."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        # Create two institutions
        response1 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "relaxed-inst"},
        )
        inst_relaxed = response1.json()["institution_id"]

        response2 = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "strict-inst"},
        )
        inst_strict = response2.json()["institution_id"]

        # Set one institution to strict mode
        client.put(
            f"/admin/institutions/{inst_strict}/config",
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

        reset_config_cache()

        # Set absolute path
        monkeypatch.setenv("ENGINE_LEDGER_PATH", "/var/log/audit.jsonl")

        # Should fail because one institution is strict
        result = run_preflight_checks()
        assert result.ok is False
        assert result.code == PATH_MISCONFIG_ABSOLUTE_LEDGER
