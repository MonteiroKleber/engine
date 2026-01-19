"""Tests for institution config default values."""

import pytest

from engine.core.institution_config import (
    InstitutionConfig,
    ConfigFlags,
    ConfigLimits,
    ConfigDefaults,
    CONFIG_SCHEMA_VERSION,
    get_effective_config,
    reset_config_cache,
)
from engine.core.institution_context import DEFAULT_INSTITUTION_ID


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))

    reset_config_cache()

    yield

    reset_config_cache()


class TestDefaultFlagValues:
    """Test default flag values."""

    def test_allow_legacy_routes_default_true(self, tmp_path, monkeypatch):
        """allow_legacy_routes defaults to True."""
        config = InstitutionConfig()
        assert config.flags.allow_legacy_routes is True

    def test_require_institution_header_for_runtime_default_false(self, tmp_path, monkeypatch):
        """require_institution_header_for_runtime defaults to False."""
        config = InstitutionConfig()
        assert config.flags.require_institution_header_for_runtime is False

    def test_enable_contracts_stub_default_true(self, tmp_path, monkeypatch):
        """enable_contracts_stub defaults to True."""
        config = InstitutionConfig()
        assert config.flags.enable_contracts_stub is True


class TestDefaultLimitValues:
    """Test default limit values."""

    def test_max_body_bytes_default_256kib(self, tmp_path, monkeypatch):
        """max_body_bytes defaults to 256 KiB (262144)."""
        config = InstitutionConfig()
        assert config.limits.max_body_bytes == 262144

    def test_rate_limit_per_minute_default_100(self, tmp_path, monkeypatch):
        """rate_limit_per_minute defaults to 100."""
        config = InstitutionConfig()
        assert config.limits.rate_limit_per_minute == 100


class TestDefaultDefaultValues:
    """Test default 'defaults' section values."""

    def test_default_dept_default_finance(self, tmp_path, monkeypatch):
        """default_dept defaults to 'finance'."""
        config = InstitutionConfig()
        assert config.defaults.default_dept == "finance"

    def test_default_bundle_name_default_finance_pilot(self, tmp_path, monkeypatch):
        """default_bundle_name defaults to 'finance-pilot'."""
        config = InstitutionConfig()
        assert config.defaults.default_bundle_name == "finance-pilot"


class TestEffectiveConfigDefaults:
    """Test get_effective_config returns defaults when no config exists."""

    def test_effective_config_returns_defaults_for_unknown_institution(self, tmp_path, monkeypatch):
        """get_effective_config returns defaults for unknown institution."""
        institution_id = "11111111-1111-1111-1111-111111111111"

        config = get_effective_config(institution_id)

        # Verify defaults
        assert config.schema_version == CONFIG_SCHEMA_VERSION
        assert config.updated_at is None
        assert config.updated_by is None
        assert config.flags.allow_legacy_routes is True
        assert config.flags.require_institution_header_for_runtime is False
        assert config.flags.enable_contracts_stub is True
        assert config.limits.max_body_bytes == 262144
        assert config.limits.rate_limit_per_minute == 100
        assert config.defaults.default_dept == "finance"
        assert config.defaults.default_bundle_name == "finance-pilot"

    def test_effective_config_returns_defaults_for_default_institution(self, tmp_path, monkeypatch):
        """get_effective_config returns defaults for default institution."""
        config = get_effective_config(DEFAULT_INSTITUTION_ID)

        # Verify defaults
        assert config.schema_version == CONFIG_SCHEMA_VERSION
        assert config.flags.allow_legacy_routes is True
        assert config.flags.require_institution_header_for_runtime is False
        assert config.flags.enable_contracts_stub is True


class TestSchemaVersion:
    """Test schema version."""

    def test_schema_version_is_1_4(self, tmp_path, monkeypatch):
        """Config schema version is 1.4 (Etapa 2.4 Governed Rollback)."""
        assert CONFIG_SCHEMA_VERSION == "1.4"

    def test_config_has_schema_version(self, tmp_path, monkeypatch):
        """Config instance has schema_version field."""
        config = InstitutionConfig()
        assert config.schema_version == "1.4"


class TestConfigToDict:
    """Test config serialization."""

    def test_to_dict_includes_all_fields(self, tmp_path, monkeypatch):
        """to_dict includes all fields."""
        config = InstitutionConfig()
        data = config.to_dict()

        assert "schema_version" in data
        assert "updated_at" in data
        assert "updated_by" in data
        assert "flags" in data
        assert "limits" in data
        assert "defaults" in data

    def test_to_dict_flags_structure(self, tmp_path, monkeypatch):
        """to_dict has correct flags structure."""
        config = InstitutionConfig()
        data = config.to_dict()

        assert "allow_legacy_routes" in data["flags"]
        assert "require_institution_header_for_runtime" in data["flags"]
        assert "enable_contracts_stub" in data["flags"]

    def test_to_dict_limits_structure(self, tmp_path, monkeypatch):
        """to_dict has correct limits structure."""
        config = InstitutionConfig()
        data = config.to_dict()

        assert "max_body_bytes" in data["limits"]
        assert "rate_limit_per_minute" in data["limits"]

    def test_to_dict_defaults_structure(self, tmp_path, monkeypatch):
        """to_dict has correct defaults structure."""
        config = InstitutionConfig()
        data = config.to_dict()

        assert "default_dept" in data["defaults"]
        assert "default_bundle_name" in data["defaults"]


class TestConfigFromDict:
    """Test config deserialization."""

    def test_from_dict_with_empty_dict(self, tmp_path, monkeypatch):
        """from_dict with empty dict returns defaults."""
        config = InstitutionConfig.from_dict({})

        assert config.flags.allow_legacy_routes is True
        assert config.flags.require_institution_header_for_runtime is False
        assert config.flags.enable_contracts_stub is True
        assert config.limits.max_body_bytes == 262144
        assert config.limits.rate_limit_per_minute == 100
        assert config.defaults.default_dept == "finance"
        assert config.defaults.default_bundle_name == "finance-pilot"

    def test_from_dict_with_partial_flags(self, tmp_path, monkeypatch):
        """from_dict with partial flags uses defaults for missing."""
        config = InstitutionConfig.from_dict({
            "flags": {"allow_legacy_routes": False},
        })

        assert config.flags.allow_legacy_routes is False
        assert config.flags.require_institution_header_for_runtime is False  # Default
        assert config.flags.enable_contracts_stub is True  # Default

    def test_from_dict_roundtrip(self, tmp_path, monkeypatch):
        """from_dict(to_dict()) preserves values."""
        original = InstitutionConfig(
            schema_version="1.4",
            updated_at="2024-01-01T00:00:00+00:00",
            updated_by="test-actor",
            flags=ConfigFlags(
                allow_legacy_routes=False,
                require_institution_header_for_runtime=True,
                enable_contracts_stub=False,
            ),
            limits=ConfigLimits(
                max_body_bytes=2048,
                rate_limit_per_minute=30,
            ),
            defaults=ConfigDefaults(
                default_dept="hr",
                default_bundle_name="hr-bundle",
            ),
        )

        data = original.to_dict()
        restored = InstitutionConfig.from_dict(data)

        assert restored.schema_version == original.schema_version
        assert restored.updated_at == original.updated_at
        assert restored.updated_by == original.updated_by
        assert restored.flags.allow_legacy_routes == original.flags.allow_legacy_routes
        assert restored.flags.require_institution_header_for_runtime == original.flags.require_institution_header_for_runtime
        assert restored.flags.enable_contracts_stub == original.flags.enable_contracts_stub
        assert restored.limits.max_body_bytes == original.limits.max_body_bytes
        assert restored.limits.rate_limit_per_minute == original.limits.rate_limit_per_minute
        assert restored.defaults.default_dept == original.defaults.default_dept
        assert restored.defaults.default_bundle_name == original.defaults.default_bundle_name
