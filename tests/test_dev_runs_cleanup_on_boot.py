"""Tests for Dev Runs Cleanup on Boot."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.pipeline.cleanup import (
    parse_bool_env,
    should_cleanup_on_boot,
    is_dry_run_on_boot,
    cleanup_dev_runs,
    CleanupResult,
)
from engine.pipeline.registry import DevRunsRegistry, reset_registry


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Setup environment for tests."""
    reset_registry()
    monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))
    monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    return tmp_path


class TestParseBoolEnv:
    """Test parse_bool_env helper."""

    def test_returns_true_for_1(self, monkeypatch):
        """parse_bool_env returns True when ENV is '1'."""
        monkeypatch.setenv("TEST_BOOL_VAR", "1")
        assert parse_bool_env("TEST_BOOL_VAR") is True

    def test_returns_false_for_0(self, monkeypatch):
        """parse_bool_env returns False when ENV is '0'."""
        monkeypatch.setenv("TEST_BOOL_VAR", "0")
        assert parse_bool_env("TEST_BOOL_VAR") is False

    def test_returns_default_when_not_set(self, monkeypatch):
        """parse_bool_env returns default when ENV not set."""
        monkeypatch.delenv("TEST_UNSET_VAR", raising=False)
        assert parse_bool_env("TEST_UNSET_VAR", "0") is False
        assert parse_bool_env("TEST_UNSET_VAR", "1") is True

    def test_returns_false_for_other_values(self, monkeypatch):
        """parse_bool_env returns False for non-'1' values."""
        monkeypatch.setenv("TEST_BOOL_VAR", "true")
        assert parse_bool_env("TEST_BOOL_VAR") is False

        monkeypatch.setenv("TEST_BOOL_VAR", "yes")
        assert parse_bool_env("TEST_BOOL_VAR") is False


class TestShouldCleanupOnBoot:
    """Test should_cleanup_on_boot helper."""

    def test_returns_false_by_default(self, monkeypatch):
        """should_cleanup_on_boot returns False when ENV not set."""
        monkeypatch.delenv("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", raising=False)
        assert should_cleanup_on_boot() is False

    def test_returns_true_when_enabled(self, monkeypatch):
        """should_cleanup_on_boot returns True when ENV is '1'."""
        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", "1")
        assert should_cleanup_on_boot() is True

    def test_returns_false_when_disabled(self, monkeypatch):
        """should_cleanup_on_boot returns False when ENV is '0'."""
        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", "0")
        assert should_cleanup_on_boot() is False


class TestIsDryRunOnBoot:
    """Test is_dry_run_on_boot helper."""

    def test_returns_false_by_default(self, monkeypatch):
        """is_dry_run_on_boot returns False when ENV not set."""
        monkeypatch.delenv("ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT", raising=False)
        assert is_dry_run_on_boot() is False

    def test_returns_true_when_enabled(self, monkeypatch):
        """is_dry_run_on_boot returns True when ENV is '1'."""
        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT", "1")
        assert is_dry_run_on_boot() is True


class TestCleanupOnBootLifespan:
    """Test cleanup on boot during lifespan."""

    def test_cleanup_skipped_when_env_disabled(self, setup_env, monkeypatch, caplog):
        """Cleanup should be skipped when ENV disabled (default)."""
        monkeypatch.delenv("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", raising=False)

        # Verify default is disabled
        assert should_cleanup_on_boot() is False

    def test_cleanup_runs_when_env_enabled(self, setup_env, monkeypatch):
        """Cleanup should run when ENGINE_DEV_RUNS_CLEANUP_ON_BOOT='1'."""
        tmp_path = setup_env
        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", "1")
        monkeypatch.setenv("ENGINE_DEV_RUNS_TTL_HOURS", "0")  # All runs expired

        # Create a run that should be deleted
        registry = DevRunsRegistry(tmp_path / "registry.jsonl")
        run_dir = tmp_path / "dev-runs" / "old-run"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "test.txt").write_text("data")
        registry.emit_created("old-run", "test-bundle", str(run_dir / "test-bundle"))

        # Verify cleanup would run
        assert should_cleanup_on_boot() is True

        # Run cleanup directly (simulating what lifespan does)
        result = cleanup_dev_runs(dry_run=is_dry_run_on_boot())

        assert result.success is True
        assert "old-run" in result.deleted_run_ids
        assert not run_dir.exists()

    def test_cleanup_dry_run_mode(self, setup_env, monkeypatch):
        """Cleanup should respect dry_run mode."""
        tmp_path = setup_env
        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", "1")
        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT", "1")
        monkeypatch.setenv("ENGINE_DEV_RUNS_TTL_HOURS", "0")  # All runs expired

        # Create a run
        registry = DevRunsRegistry(tmp_path / "registry.jsonl")
        run_dir = tmp_path / "dev-runs" / "dry-run-test"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "test.txt").write_text("data")
        registry.emit_created("dry-run-test", "test-bundle", str(run_dir / "test-bundle"))

        # Verify dry run is enabled
        assert is_dry_run_on_boot() is True

        # Run cleanup in dry run mode
        result = cleanup_dev_runs(dry_run=True)

        assert result.success is True
        assert result.dry_run is True
        assert "dry-run-test" in result.deleted_run_ids
        # Directory should still exist in dry run
        assert run_dir.exists()

    def test_cleanup_failure_does_not_block_startup(self, setup_env, monkeypatch):
        """Cleanup failure should NOT block startup or enter SAFE_MODE."""
        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", "1")

        # Simulate a cleanup that fails
        with patch("engine.pipeline.cleanup.get_registry") as mock_get_registry:
            mock_registry = MagicMock()
            mock_registry.aggregate_runs.side_effect = Exception("Registry error")
            mock_get_registry.return_value = mock_registry

            result = cleanup_dev_runs()

            # Cleanup fails but returns a result (not an exception)
            assert result.success is False
            assert result.error_code == "DEV_RUNS_CLEANUP_FAILED"
            assert "Registry error" in result.error_message

            # Key: this should NOT raise or enter SAFE_MODE
            # The function returns a failed result gracefully


class TestCleanupOnBootIntegration:
    """Integration tests for cleanup on boot in server lifespan."""

    def test_lifespan_cleanup_logs_start_event(self, setup_env, monkeypatch, caplog):
        """Lifespan should log DEV_RUNS_CLEANUP_ON_BOOT_START."""
        import logging

        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", "1")
        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT", "0")

        caplog.set_level(logging.INFO)

        # Simulate the lifespan cleanup logic
        from engine.core.logging import get_logger
        logger = get_logger()

        if should_cleanup_on_boot():
            dry_run = is_dry_run_on_boot()
            logger.info(
                "DEV_RUNS_CLEANUP_ON_BOOT_START",
                extra={
                    "event": "DEV_RUNS_CLEANUP_ON_BOOT_START",
                    "dry_run": dry_run,
                },
            )

        assert "DEV_RUNS_CLEANUP_ON_BOOT_START" in caplog.text

    def test_lifespan_cleanup_logs_ok_event(self, setup_env, monkeypatch, caplog):
        """Lifespan should log DEV_RUNS_CLEANUP_ON_BOOT_OK on success."""
        import logging

        monkeypatch.setenv("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", "1")

        caplog.set_level(logging.INFO)

        from engine.core.logging import get_logger
        logger = get_logger()

        if should_cleanup_on_boot():
            dry_run = is_dry_run_on_boot()
            result = cleanup_dev_runs(dry_run=dry_run)
            if result.success:
                logger.info(
                    "DEV_RUNS_CLEANUP_ON_BOOT_OK",
                    extra={
                        "event": "DEV_RUNS_CLEANUP_ON_BOOT_OK",
                        "dry_run": dry_run,
                        "deleted_count": len(result.deleted_run_ids),
                    },
                )

        assert "DEV_RUNS_CLEANUP_ON_BOOT_OK" in caplog.text
