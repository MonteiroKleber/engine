"""Tests for bundle root namespacing by institution."""

from pathlib import Path

import pytest

from engine.core.data_root import get_institution_root
from engine.ise.release import (
    get_bundles_root,
    get_bundles_root_for_institution,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))

    # Clear any ENV overrides
    monkeypatch.delenv("ENGINE_PROD_BUNDLES_ROOT", raising=False)

    yield


class TestBundlesRootPathResolution:
    """Test bundles root path resolution for institutions."""

    def test_default_path_under_institution_root(self, tmp_path, monkeypatch):
        """Default bundles root path is under institution root."""
        institution_id = "11111111-1111-1111-1111-111111111111"

        path = get_bundles_root_for_institution(institution_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "bundles"

    def test_absolute_env_path_overrides(self, tmp_path, monkeypatch):
        """Absolute ENGINE_PROD_BUNDLES_ROOT overrides institution namespacing."""
        institution_id = "22222222-2222-2222-2222-222222222222"
        absolute_path = tmp_path / "absolute" / "bundles"

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(absolute_path))

        path = get_bundles_root_for_institution(institution_id)

        assert path == absolute_path

    def test_relative_env_path_under_institution_root(self, tmp_path, monkeypatch):
        """Relative ENGINE_PROD_BUNDLES_ROOT is under institution root."""
        institution_id = "33333333-3333-3333-3333-333333333333"

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", "custom/bundles")

        path = get_bundles_root_for_institution(institution_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "custom" / "bundles"

    def test_different_institutions_different_paths(self, tmp_path, monkeypatch):
        """Different institutions have different bundles root paths."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        path_a = get_bundles_root_for_institution(inst_a)
        path_b = get_bundles_root_for_institution(inst_b)

        assert path_a != path_b
        assert inst_a in str(path_a)
        assert inst_b in str(path_b)


class TestLegacyBundlesRootBehavior:
    """Test that legacy (no institution) bundles root behavior is preserved."""

    def test_get_bundles_root_uses_env(self, tmp_path, monkeypatch):
        """Legacy get_bundles_root uses ENGINE_PROD_BUNDLES_ROOT."""
        legacy_path = str(tmp_path / "legacy" / "bundles")
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", legacy_path)

        root = get_bundles_root()

        assert root == legacy_path

    def test_get_bundles_root_uses_default(self, tmp_path, monkeypatch):
        """Legacy get_bundles_root uses default when env not set."""
        root = get_bundles_root()

        # Default is /var/lib/engine/bundles
        assert root == "/var/lib/engine/bundles"


class TestStagingDirectoryIsolation:
    """Test that staging directories would be isolated per institution."""

    def test_staging_dir_under_institution_bundles_root(self, tmp_path, monkeypatch):
        """Staging directory is under institution's bundles root."""
        institution_id = "44444444-4444-4444-4444-444444444444"

        bundles_root = get_bundles_root_for_institution(institution_id)
        staging_dir = bundles_root / "STAGING"

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert staging_dir == expected_root / "bundles" / "STAGING"

    def test_staging_dirs_isolated_between_institutions(self, tmp_path, monkeypatch):
        """Staging directories are isolated between institutions."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        bundles_root_a = get_bundles_root_for_institution(inst_a)
        bundles_root_b = get_bundles_root_for_institution(inst_b)

        staging_a = bundles_root_a / "STAGING"
        staging_b = bundles_root_b / "STAGING"

        assert staging_a != staging_b
        assert inst_a in str(staging_a)
        assert inst_b in str(staging_b)
