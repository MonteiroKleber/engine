"""Tests for GAP 5 institution secure defaults in production mode.

Tests that ENGINE_INSTALL_MODE=prod creates institutions with secure defaults:
- require_institution_header_for_runtime=True
- allow_legacy_routes=False
- enable_contracts_stub=False
"""

import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from engine.core.institution_config import (
    get_secure_config_flags,
    get_secure_defaults_for_prod,
    create_secure_config_for_institution,
    get_effective_config,
    get_active_config_path,
    CONFIG_SCHEMA_VERSION,
    reset_config_cache,
)
from engine.core.institutions import (
    InstitutionsRegistry,
    reset_registry,
)


@pytest.fixture
def temp_data_root(tmp_path):
    """Create temporary data root for tests."""
    data_root = tmp_path / "data"
    data_root.mkdir()

    institutions_dir = data_root / "institutions"
    institutions_dir.mkdir()

    registry_path = data_root / "institutions_registry.jsonl"

    with patch.dict(os.environ, {
        "ENGINE_DATA_ROOT": str(data_root),
        "ENGINE_INSTITUTIONS_REGISTRY_PATH": str(registry_path),
        "ENGINE_INSTITUTIONS_DIR": str(institutions_dir),
    }):
        yield data_root

    # Cleanup
    reset_registry()
    reset_config_cache()


class TestGetSecureConfigFlags:
    """Tests for get_secure_config_flags()."""

    def test_returns_secure_defaults(self):
        """Should return secure defaults for production."""
        flags = get_secure_config_flags()

        assert flags.require_institution_header_for_runtime is True
        assert flags.allow_legacy_routes is False
        assert flags.enable_contracts_stub is False


class TestGetSecureDefaultsForProd:
    """Tests for get_secure_defaults_for_prod()."""

    def test_returns_complete_config_dict(self):
        """Should return a complete config dictionary."""
        config = get_secure_defaults_for_prod()

        assert "schema_version" in config
        assert "flags" in config
        assert "limits" in config
        assert "defaults" in config
        assert "freeze_mode" in config
        assert "emergency_stop" in config

    def test_flags_are_secure(self):
        """Flags should have secure production values."""
        config = get_secure_defaults_for_prod()

        assert config["flags"]["require_institution_header_for_runtime"] is True
        assert config["flags"]["allow_legacy_routes"] is False
        assert config["flags"]["enable_contracts_stub"] is False

    def test_schema_version_is_current(self):
        """Schema version should be current."""
        config = get_secure_defaults_for_prod()

        assert config["schema_version"] == CONFIG_SCHEMA_VERSION

    def test_freeze_mode_disabled(self):
        """Freeze mode should be disabled by default."""
        config = get_secure_defaults_for_prod()

        assert config["freeze_mode"] is False

    def test_emergency_stop_disabled(self):
        """Emergency stop should be disabled by default."""
        config = get_secure_defaults_for_prod()

        assert config["emergency_stop"]["enabled"] is False
        assert config["emergency_stop"]["blocked_endpoints"] == []


class TestCreateSecureConfigForInstitution:
    """Tests for create_secure_config_for_institution()."""

    def test_creates_config_file(self, temp_data_root):
        """Should create ACTIVE.json file with secure defaults."""
        institution_id = "test-inst-001"

        # Create institution directory
        inst_dir = temp_data_root / "institutions" / institution_id
        inst_dir.mkdir(parents=True)

        config, error_code, error_message = create_secure_config_for_institution(
            institution_id=institution_id,
            updated_by="test-actor",
        )

        assert config is not None
        assert error_code is None
        assert error_message is None

        # Check file exists
        config_path = get_active_config_path(institution_id)
        assert config_path.exists()

        # Check content
        with open(config_path, "r") as f:
            saved_config = json.load(f)

        assert saved_config["flags"]["require_institution_header_for_runtime"] is True
        assert saved_config["flags"]["allow_legacy_routes"] is False
        assert saved_config["flags"]["enable_contracts_stub"] is False

    def test_sets_updated_by(self, temp_data_root):
        """Should set updated_by field correctly."""
        institution_id = "test-inst-002"

        inst_dir = temp_data_root / "institutions" / institution_id
        inst_dir.mkdir(parents=True)

        config, _, _ = create_secure_config_for_institution(
            institution_id=institution_id,
            updated_by="my-custom-actor",
        )

        config_path = get_active_config_path(institution_id)
        with open(config_path, "r") as f:
            saved_config = json.load(f)

        assert saved_config["updated_by"] == "my-custom-actor"


class TestInstitutionCreationInProdMode:
    """Tests for institution creation with secure defaults in prod mode."""

    def test_prod_mode_creates_secure_config(self, temp_data_root):
        """Creating institution in prod mode should create secure config."""
        reset_registry()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "prod",
        }):
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, error_code, error_message = registry.create(
                slug="test-prod-inst",
                display_name="Test Production Institution",
            )

        assert institution is not None
        assert error_code is None

        # Check config was created
        config_path = temp_data_root / "institutions" / institution.institution_id / "config" / "ACTIVE.json"
        assert config_path.exists()

        # Check flags are secure
        with open(config_path, "r") as f:
            config = json.load(f)

        assert config["flags"]["require_institution_header_for_runtime"] is True
        assert config["flags"]["allow_legacy_routes"] is False
        assert config["flags"]["enable_contracts_stub"] is False

    def test_dev_mode_does_not_create_config(self, temp_data_root):
        """Creating institution in dev mode should NOT create config."""
        reset_registry()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "dev",
        }):
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, error_code, error_message = registry.create(
                slug="test-dev-inst",
                display_name="Test Development Institution",
            )

        assert institution is not None
        assert error_code is None

        # Config should NOT exist
        config_path = temp_data_root / "institutions" / institution.institution_id / "config" / "ACTIVE.json"
        assert not config_path.exists()

    def test_default_mode_does_not_create_config(self, temp_data_root):
        """Creating institution without ENGINE_INSTALL_MODE should not create config."""
        reset_registry()

        # Ensure ENGINE_INSTALL_MODE is not set
        env = {
            "ENGINE_DATA_ROOT": str(temp_data_root),
            "ENGINE_INSTITUTIONS_REGISTRY_PATH": str(temp_data_root / "institutions_registry.jsonl"),
            "ENGINE_INSTITUTIONS_DIR": str(temp_data_root / "institutions"),
        }
        with patch.dict(os.environ, env, clear=True):
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, error_code, error_message = registry.create(
                slug="test-default-inst",
                display_name="Test Default Institution",
            )

        assert institution is not None

        # Config should NOT exist (default is dev mode)
        config_path = temp_data_root / "institutions" / institution.institution_id / "config" / "ACTIVE.json"
        assert not config_path.exists()

    def test_prod_mode_case_insensitive(self, temp_data_root):
        """ENGINE_INSTALL_MODE=PROD should work (case insensitive)."""
        reset_registry()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "PROD",
        }):
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, error_code, error_message = registry.create(
                slug="test-prod-upper",
                display_name="Test Prod Uppercase",
            )

        assert institution is not None

        # Config should exist
        config_path = temp_data_root / "institutions" / institution.institution_id / "config" / "ACTIVE.json"
        assert config_path.exists()

    def test_secure_config_sets_system_updated_by(self, temp_data_root):
        """Secure config should be created with system:secure_defaults as updated_by."""
        reset_registry()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "prod",
        }):
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, _, _ = registry.create(slug="test-system-updated")

        config_path = temp_data_root / "institutions" / institution.institution_id / "config" / "ACTIVE.json"
        with open(config_path, "r") as f:
            config = json.load(f)

        assert config["updated_by"] == "system:secure_defaults"


class TestGetEffectiveConfigWithSecureDefaults:
    """Tests for get_effective_config() after secure config creation."""

    def test_effective_config_uses_secure_defaults(self, temp_data_root):
        """get_effective_config should return secure defaults after creation in prod mode."""
        reset_registry()
        reset_config_cache()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "prod",
        }):
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, _, _ = registry.create(slug="test-effective-config")

        # Get effective config
        config = get_effective_config(institution.institution_id)

        assert config.flags.require_institution_header_for_runtime is True
        assert config.flags.allow_legacy_routes is False
        assert config.flags.enable_contracts_stub is False

    def test_effective_config_returns_permissive_defaults_in_dev(self, temp_data_root):
        """get_effective_config should return permissive defaults in dev mode."""
        reset_registry()
        reset_config_cache()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "dev",
        }):
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, _, _ = registry.create(slug="test-dev-effective")

        # Get effective config (no ACTIVE.json exists)
        config = get_effective_config(institution.institution_id)

        # Should return permissive defaults
        assert config.flags.require_institution_header_for_runtime is False
        assert config.flags.allow_legacy_routes is True
        assert config.flags.enable_contracts_stub is True


class TestGAP53NonSilentProdMode:
    """Tests for GAP 5.3 - non-silent secure config failure in prod mode.

    In ENGINE_INSTALL_MODE=prod, if secure config creation fails,
    institution creation must fail deterministically.
    """

    def test_prod_mode_fails_if_config_creation_fails(self, temp_data_root):
        """In prod mode, institution creation should fail if secure config fails."""
        reset_registry()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "prod",
        }):
            # Mock create_secure_config_for_institution to fail
            with patch(
                "engine.core.institution_config.create_secure_config_for_institution",
                return_value=(None, "MOCK_ERROR", "Simulated config failure"),
            ):
                registry = InstitutionsRegistry(
                    registry_path=temp_data_root / "institutions_registry.jsonl",
                    institutions_dir=temp_data_root / "institutions",
                )

                institution, error_code, error_message = registry.create(
                    slug="test-prod-fail",
                    display_name="Test Prod Failure",
                )

        # Institution should NOT be created
        assert institution is None
        assert error_code == "INSTITUTION_SECURE_CONFIG_REQUIRED"
        assert "Production mode requires secure config" in error_message
        assert "MOCK_ERROR" in error_message

    def test_prod_mode_fails_with_deterministic_error_code(self, temp_data_root):
        """In prod mode, config failure should return deterministic error code."""
        reset_registry()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "prod",
        }):
            with patch(
                "engine.core.institution_config.create_secure_config_for_institution",
                return_value=(None, "ANY_ERROR", "Any error message"),
            ):
                registry = InstitutionsRegistry(
                    registry_path=temp_data_root / "institutions_registry.jsonl",
                    institutions_dir=temp_data_root / "institutions",
                )

                institution, error_code, error_message = registry.create(
                    slug="test-deterministic-error",
                )

        # Error code should always be INSTITUTION_SECURE_CONFIG_REQUIRED
        from engine.core.errors import INSTITUTION_SECURE_CONFIG_REQUIRED
        assert error_code == INSTITUTION_SECURE_CONFIG_REQUIRED

    def test_prod_mode_fails_on_exception(self, temp_data_root):
        """In prod mode, exception during config creation should fail."""
        reset_registry()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "prod",
        }):
            # Make create_secure_config_for_institution raise an exception
            with patch(
                "engine.core.institution_config.create_secure_config_for_institution",
                side_effect=RuntimeError("Disk full or something"),
            ):
                registry = InstitutionsRegistry(
                    registry_path=temp_data_root / "institutions_registry.jsonl",
                    institutions_dir=temp_data_root / "institutions",
                )

                institution, error_code, error_message = registry.create(
                    slug="test-prod-exception",
                )

        # Should fail with deterministic error
        assert institution is None
        assert error_code == "INSTITUTION_SECURE_CONFIG_REQUIRED"
        assert "Exception" in error_message
        assert "Disk full" in error_message

    def test_dev_mode_continues_on_config_failure(self, temp_data_root):
        """In dev mode, config failure should NOT fail institution creation."""
        reset_registry()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "dev",
        }):
            # Note: In dev mode, config creation is skipped entirely,
            # but let's verify the behavior is backward compatible
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, error_code, error_message = registry.create(
                slug="test-dev-continues",
                display_name="Test Dev Continues",
            )

        # Institution should be created successfully
        assert institution is not None
        assert error_code is None
        assert error_message is None

    def test_dev_mode_backward_compatible_no_config(self, temp_data_root):
        """In dev mode, no config file should be created (backward compatible)."""
        reset_registry()

        with patch.dict(os.environ, {
            "ENGINE_INSTALL_MODE": "dev",
        }):
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, _, _ = registry.create(slug="test-dev-no-config")

        # No config should exist
        config_path = temp_data_root / "institutions" / institution.institution_id / "config" / "ACTIVE.json"
        assert not config_path.exists()

    def test_default_mode_backward_compatible(self, temp_data_root):
        """Default mode (no ENGINE_INSTALL_MODE) should be dev-like."""
        reset_registry()

        # Explicitly remove ENGINE_INSTALL_MODE
        env = {
            "ENGINE_DATA_ROOT": str(temp_data_root),
            "ENGINE_INSTITUTIONS_REGISTRY_PATH": str(temp_data_root / "institutions_registry.jsonl"),
            "ENGINE_INSTITUTIONS_DIR": str(temp_data_root / "institutions"),
        }
        with patch.dict(os.environ, env, clear=True):
            registry = InstitutionsRegistry(
                registry_path=temp_data_root / "institutions_registry.jsonl",
                institutions_dir=temp_data_root / "institutions",
            )

            institution, error_code, error_message = registry.create(
                slug="test-default-mode",
            )

        # Should succeed (dev mode behavior)
        assert institution is not None
        assert error_code is None


class TestErrorCodeConstantsGAP53:
    """Tests for GAP 5.3 error code definitions."""

    def test_institution_secure_config_required_defined(self):
        """INSTITUTION_SECURE_CONFIG_REQUIRED should be defined."""
        from engine.core.errors import INSTITUTION_SECURE_CONFIG_REQUIRED
        assert INSTITUTION_SECURE_CONFIG_REQUIRED == "INSTITUTION_SECURE_CONFIG_REQUIRED"
