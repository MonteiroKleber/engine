"""Tests for ISE compile/release script execution order."""

import json
import subprocess
from unittest.mock import MagicMock, patch, call
from pathlib import Path

import pytest

from engine.ise.release import compile_release, ReleaseResult
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
def mock_scripts(tmp_path, monkeypatch):
    """Create mock scripts and configure environment."""
    # Create mock script files
    verify_script = tmp_path / "verify_bundle.sh"
    verify_script.write_text("#!/bin/bash\nexit 0")
    verify_script.chmod(0o755)

    deploy_script = tmp_path / "deploy_engine_prod.sh"
    deploy_script.write_text("#!/bin/bash\nexit 0")
    deploy_script.chmod(0o755)

    bundles_root = tmp_path / "bundles"
    bundles_root.mkdir()

    monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
    monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))
    monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

    return {
        "verify_script": str(verify_script),
        "deploy_script": str(deploy_script),
        "bundles_root": str(bundles_root),
    }


class TestScriptExecutionOrder:
    """Test that scripts are called in correct order."""

    def test_verify_called_before_deploy(self, mock_scripts, monkeypatch):
        """Verify script must be called before deploy script."""
        call_order = []

        def mock_run(cmd, **kwargs):
            script_name = Path(cmd[0]).name
            call_order.append(script_name)

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        # Verify order
        assert len(call_order) == 2
        assert call_order[0] == "verify_bundle.sh"
        assert call_order[1] == "deploy_engine_prod.sh"
        assert result.status == "deployed"

    def test_verify_fail_stops_deploy(self, mock_scripts, monkeypatch):
        """If verify fails, deploy should NOT be called."""
        call_order = []

        def mock_run(cmd, **kwargs):
            script_name = Path(cmd[0]).name
            call_order.append(script_name)

            result = MagicMock()
            if "verify" in script_name:
                result.returncode = 1
                result.stderr = "Verification failed"
            else:
                result.returncode = 0
            result.stdout = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        # Only verify should be called
        assert len(call_order) == 1
        assert call_order[0] == "verify_bundle.sh"
        assert result.status == "failed"
        assert result.error_code == errors.ISE_VERIFY_FAILED

    def test_verify_receives_staging_path(self, mock_scripts, monkeypatch):
        """Verify script should receive staging bundle path as argument."""
        verify_call = None

        def mock_run(cmd, **kwargs):
            nonlocal verify_call
            script_name = Path(cmd[0]).name
            if "verify" in script_name:
                verify_call = list(cmd)

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            compile_release(
                idl=VALID_IDL,
                bundle_name="my-bundle",
            )

        # Verify was called with staging path
        assert verify_call is not None
        assert len(verify_call) == 2
        assert "verify_bundle.sh" in verify_call[0]
        assert "STAGING/my-bundle" in verify_call[1]

    def test_deploy_called_without_arguments(self, mock_scripts, monkeypatch):
        """Deploy script should be called without arguments."""
        deploy_call = None

        def mock_run(cmd, **kwargs):
            nonlocal deploy_call
            script_name = Path(cmd[0]).name
            if "deploy" in script_name:
                deploy_call = list(cmd)

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        # Deploy was called with just the script path
        assert deploy_call is not None
        assert len(deploy_call) == 1
        assert "deploy_engine_prod.sh" in deploy_call[0]


class TestBundleStagingCopy:
    """Test bundle is copied to staging before verification."""

    def test_bundle_copied_to_staging(self, mock_scripts, monkeypatch):
        """Bundle should be copied to STAGING directory."""
        staging_path = None

        def mock_run(cmd, **kwargs):
            nonlocal staging_path
            script_name = Path(cmd[0]).name
            if "verify" in script_name:
                staging_path = cmd[1]
                # Check staging bundle exists
                assert Path(staging_path).exists()
                # Check it contains expected files
                assert (Path(staging_path) / "bundle.manifest.json").exists()
                assert (Path(staging_path) / "rbac.json").exists()

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        assert staging_path is not None
        assert "STAGING" in staging_path


class TestDeploySuccess:
    """Test successful deployment."""

    def test_deploy_success_returns_deployed(self, mock_scripts, monkeypatch):
        """Successful deploy should return status 'deployed'."""

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "Success"
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        assert result.status == "deployed"
        assert result.bundle_name == "test-bundle"
        assert result.bundle_hash is not None
        assert result.release_id is not None
        # Release ID format: YYYYMMDD-HHMMSS
        assert len(result.release_id) == 15
        assert "-" in result.release_id

    def test_deploy_success_to_dict(self, mock_scripts, monkeypatch):
        """Successful deploy to_dict should not have error field."""

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        d = result.to_dict()
        assert d["status"] == "deployed"
        assert "error" not in d
        assert d["bundle_name"] == "test-bundle"
