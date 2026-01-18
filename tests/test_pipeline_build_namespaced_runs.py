"""Tests for pipeline build namespacing by institution."""

from pathlib import Path

import pytest

from engine.core.data_root import get_institution_root
from engine.pipeline.registry import (
    DevRunsRegistry,
    get_registry_path_for_institution,
    get_dev_runs_dir_for_institution,
    get_registry,
    reset_all_registries,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))

    # Clear any ENV overrides
    monkeypatch.delenv("ENGINE_DEV_RUNS_REGISTRY_PATH", raising=False)
    monkeypatch.delenv("ENGINE_PROD_BUNDLES_ROOT", raising=False)

    reset_all_registries()

    yield

    reset_all_registries()


class TestDevRunsPathResolution:
    """Test dev-runs path resolution for institutions."""

    def test_registry_path_under_institution_root(self, tmp_path, monkeypatch):
        """Registry path is under institution root by default."""
        institution_id = "11111111-1111-1111-1111-111111111111"

        path = get_registry_path_for_institution(institution_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "dev_runs_registry.jsonl"

    def test_dev_runs_dir_under_institution_root(self, tmp_path, monkeypatch):
        """Dev-runs directory is under institution root."""
        institution_id = "22222222-2222-2222-2222-222222222222"

        path = get_dev_runs_dir_for_institution(institution_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "dev-runs"

    def test_absolute_env_registry_path_overrides(self, tmp_path, monkeypatch):
        """Absolute ENGINE_DEV_RUNS_REGISTRY_PATH overrides namespacing."""
        institution_id = "33333333-3333-3333-3333-333333333333"
        absolute_path = tmp_path / "absolute" / "registry.jsonl"

        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(absolute_path))

        path = get_registry_path_for_institution(institution_id)

        assert path == absolute_path

    def test_relative_env_registry_path_under_institution_root(self, tmp_path, monkeypatch):
        """Relative ENGINE_DEV_RUNS_REGISTRY_PATH is under institution root."""
        institution_id = "44444444-4444-4444-4444-444444444444"

        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", "custom/registry.jsonl")

        path = get_registry_path_for_institution(institution_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "custom" / "registry.jsonl"

    def test_different_institutions_different_paths(self, tmp_path, monkeypatch):
        """Different institutions have different paths."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        path_a = get_registry_path_for_institution(inst_a)
        path_b = get_registry_path_for_institution(inst_b)

        assert path_a != path_b
        assert inst_a in str(path_a)
        assert inst_b in str(path_b)

        dir_a = get_dev_runs_dir_for_institution(inst_a)
        dir_b = get_dev_runs_dir_for_institution(inst_b)

        assert dir_a != dir_b
        assert inst_a in str(dir_a)
        assert inst_b in str(dir_b)


class TestRegistryInstanceIsolation:
    """Test registry instance isolation per institution."""

    def test_get_registry_returns_institution_specific_instance(self, tmp_path, monkeypatch):
        """get_registry with institution_id returns institution-specific registry."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        reg_a = get_registry(institution_id=inst_a)
        reg_b = get_registry(institution_id=inst_b)

        assert reg_a is not reg_b
        assert str(reg_a.path) != str(reg_b.path)

    def test_get_registry_returns_same_instance_for_same_institution(self, tmp_path, monkeypatch):
        """get_registry returns same instance for same institution."""
        institution_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"

        reg_1 = get_registry(institution_id=institution_id)
        reg_2 = get_registry(institution_id=institution_id)

        assert reg_1 is reg_2

    def test_registry_init_with_institution_id(self, tmp_path, monkeypatch):
        """DevRunsRegistry initialized with institution_id uses correct path."""
        institution_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"

        reg = DevRunsRegistry(institution_id=institution_id)

        expected_path = get_registry_path_for_institution(institution_id)
        assert reg.path == expected_path


class TestRegistryEventIsolation:
    """Test that registry events are isolated per institution."""

    def test_events_written_to_institution_specific_file(self, tmp_path, monkeypatch):
        """Events are written to institution-specific registry file."""
        institution_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

        reg = get_registry(institution_id=institution_id)

        # Write an event
        reg.emit_created(
            run_id="run-001",
            bundle_name="test-bundle",
            bundle_path="/path/to/bundle",
        )

        # Verify file exists at institution-specific path
        expected_path = get_registry_path_for_institution(institution_id)
        assert expected_path.exists()

        # Read and verify event
        events = reg.read_events()
        assert len(events) == 1
        assert events[0].run_id == "run-001"

    def test_events_isolated_between_institutions(self, tmp_path, monkeypatch):
        """Events from different institutions are in different files."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        reg_a = get_registry(institution_id=inst_a)
        reg_b = get_registry(institution_id=inst_b)

        # Write to institution A
        reg_a.emit_created(
            run_id="run-a-001",
            bundle_name="bundle-a",
            bundle_path="/path/a",
        )

        # Write to institution B
        reg_b.emit_created(
            run_id="run-b-001",
            bundle_name="bundle-b",
            bundle_path="/path/b",
        )

        # Verify isolation
        events_a = reg_a.read_events()
        events_b = reg_b.read_events()

        assert len(events_a) == 1
        assert events_a[0].run_id == "run-a-001"

        assert len(events_b) == 1
        assert events_b[0].run_id == "run-b-001"


class TestLegacyRegistryBehavior:
    """Test that legacy (no institution) registry behavior is preserved."""

    def test_get_registry_without_institution_returns_singleton(self, tmp_path, monkeypatch):
        """get_registry without institution_id returns legacy singleton."""
        reg_1 = get_registry()
        reg_2 = get_registry()

        assert reg_1 is reg_2

    def test_legacy_registry_uses_env_path(self, tmp_path, monkeypatch):
        """Legacy registry uses ENGINE_DEV_RUNS_REGISTRY_PATH directly."""
        legacy_path = tmp_path / "legacy" / "registry.jsonl"
        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(legacy_path))

        reset_all_registries()

        reg = get_registry()

        assert reg.path == legacy_path


class TestResetRegistries:
    """Test registry reset functionality."""

    def test_reset_clears_all_institution_registries(self, tmp_path, monkeypatch):
        """reset_all_registries clears all cached registry instances."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        # Create some registries
        reg_a_1 = get_registry(institution_id=inst_a)
        reg_b_1 = get_registry(institution_id=inst_b)

        # Reset
        reset_all_registries()

        # Get again - should be new instances
        reg_a_2 = get_registry(institution_id=inst_a)
        reg_b_2 = get_registry(institution_id=inst_b)

        assert reg_a_1 is not reg_a_2
        assert reg_b_1 is not reg_b_2
