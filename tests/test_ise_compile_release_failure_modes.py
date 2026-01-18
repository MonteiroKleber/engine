"""Tests for ISE compile/release failure modes."""

import json
import subprocess
from unittest.mock import MagicMock, patch
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

# Invalid IDL (no expense entity)
INVALID_IDL_NO_EXPENSE = json.dumps({
    "system": "other-system",
    "version": "1.0.0",
    "entities": [
        {"type": "invoice", "name": "Invoice"},
    ],
    "actors": [],
    "usecases": [],
})


@pytest.fixture
def mock_scripts(tmp_path, monkeypatch):
    """Create mock scripts and configure environment."""
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


class TestScriptNotFound:
    """Test behavior when scripts don't exist."""

    def test_verify_script_not_found(self, tmp_path, monkeypatch):
        """Missing verify script should return ISE_SCRIPT_UNAVAILABLE."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", "/nonexistent/verify.sh")
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", "/nonexistent/deploy.sh")

        result = compile_release(
            idl=VALID_IDL,
            bundle_name="test-bundle",
        )

        assert result.status == "failed"
        assert result.error_code == errors.ISE_SCRIPT_UNAVAILABLE
        assert "verify" in result.error_message.lower()

    def test_deploy_script_not_found(self, tmp_path, monkeypatch):
        """Missing deploy script should return ISE_SCRIPT_UNAVAILABLE."""
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 0")
        verify_script.chmod(0o755)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", "/nonexistent/deploy.sh")

        result = compile_release(
            idl=VALID_IDL,
            bundle_name="test-bundle",
        )

        assert result.status == "failed"
        assert result.error_code == errors.ISE_SCRIPT_UNAVAILABLE
        assert "deploy" in result.error_message.lower()


class TestVerifyFailure:
    """Test behavior when verify script fails."""

    def test_verify_nonzero_exit_returns_failed(self, mock_scripts):
        """Verify returning non-zero should return status 'failed'."""

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            script_name = Path(cmd[0]).name
            if "verify" in script_name:
                result.returncode = 1
                result.stderr = "Hash mismatch"
            else:
                result.returncode = 0
            result.stdout = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        assert result.status == "failed"
        assert result.error_code == errors.ISE_VERIFY_FAILED
        assert result.exit_code == 1
        assert result.script_output == "Hash mismatch"

    def test_verify_exit_codes(self, mock_scripts):
        """Different verify exit codes should be captured."""
        for exit_code in [1, 2, 127, 255]:

            def mock_run(cmd, **kwargs):
                result = MagicMock()
                script_name = Path(cmd[0]).name
                if "verify" in script_name:
                    result.returncode = exit_code
                    result.stderr = f"Exit {exit_code}"
                else:
                    result.returncode = 0
                result.stdout = ""
                return result

            with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
                result = compile_release(
                    idl=VALID_IDL,
                    bundle_name="test-bundle",
                )

            assert result.status == "failed"
            assert result.exit_code == exit_code


class TestDeployFailure:
    """Test behavior when deploy script fails."""

    def test_deploy_nonzero_exit_returns_rolled_back(self, mock_scripts):
        """Deploy returning non-zero should return status 'rolled_back'."""

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            script_name = Path(cmd[0]).name
            if "deploy" in script_name:
                result.returncode = 1
                result.stderr = "Deployment failed, rolled back"
            else:
                result.returncode = 0
            result.stdout = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        assert result.status == "rolled_back"
        assert result.error_code == errors.ISE_DEPLOY_FAILED
        assert result.exit_code == 1
        assert "rolled back" in result.error_message.lower()

    def test_deploy_exit_code_captured(self, mock_scripts):
        """Deploy exit code should be in result."""

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            script_name = Path(cmd[0]).name
            if "deploy" in script_name:
                result.returncode = 42
                result.stderr = "Custom error"
            else:
                result.returncode = 0
            result.stdout = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        assert result.status == "rolled_back"
        assert result.exit_code == 42

        # Check to_dict includes exit_code
        d = result.to_dict()
        assert d["status"] == "rolled_back"
        assert d["error"]["exit_code"] == 42

    def test_deploy_output_captured(self, mock_scripts):
        """Deploy stderr/stdout should be captured."""

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            script_name = Path(cmd[0]).name
            if "deploy" in script_name:
                result.returncode = 1
                result.stderr = "Error details here"
                result.stdout = ""
            else:
                result.returncode = 0
                result.stderr = ""
            result.stdout = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=VALID_IDL,
                bundle_name="test-bundle",
            )

        assert result.script_output == "Error details here"

        d = result.to_dict()
        assert d["error"]["output"] == "Error details here"


class TestCompilationFailure:
    """Test behavior when IDL compilation fails."""

    def test_invalid_idl_returns_failed(self, mock_scripts):
        """Invalid IDL should return failed status."""
        result = compile_release(
            idl=INVALID_IDL_NO_EXPENSE,
            bundle_name="test-bundle",
            validate_finance_pilot=True,
        )

        assert result.status == "failed"
        assert result.error_code == errors.ISE_IDL_INSUFFICIENT

    def test_invalid_json_returns_failed(self, mock_scripts):
        """Invalid JSON should return failed status."""
        result = compile_release(
            idl="not valid json {",
            bundle_name="test-bundle",
        )

        assert result.status == "failed"
        assert result.error_code in (errors.ISE_IDL_INVALID_JSON, errors.ISE_IDL_PARSE_FAILED)


class TestReleaseResultToDict:
    """Test ReleaseResult.to_dict() method."""

    def test_deployed_to_dict(self):
        """Deployed result should have minimal fields."""
        result = ReleaseResult(
            status="deployed",
            release_id="20250115-120000",
            bundle_name="my-bundle",
            bundle_hash="abc123",
        )

        d = result.to_dict()
        assert d == {
            "status": "deployed",
            "release_id": "20250115-120000",
            "bundle_name": "my-bundle",
            "bundle_hash": "abc123",
        }

    def test_rolled_back_to_dict(self):
        """Rolled back result should include error details."""
        result = ReleaseResult(
            status="rolled_back",
            release_id="20250115-120000",
            bundle_name="my-bundle",
            bundle_hash="abc123",
            error_code=errors.ISE_DEPLOY_FAILED,
            error_message="Deploy failed",
            exit_code=1,
            script_output="Error output",
        )

        d = result.to_dict()
        assert d["status"] == "rolled_back"
        assert d["error"]["code"] == errors.ISE_DEPLOY_FAILED
        assert d["error"]["message"] == "Deploy failed"
        assert d["error"]["exit_code"] == 1
        assert d["error"]["output"] == "Error output"

    def test_failed_to_dict(self):
        """Failed result should include error details."""
        result = ReleaseResult(
            status="failed",
            release_id="20250115-120000",
            bundle_name="my-bundle",
            error_code=errors.ISE_VERIFY_FAILED,
            error_message="Verification failed",
            exit_code=2,
        )

        d = result.to_dict()
        assert d["status"] == "failed"
        assert d["error"]["code"] == errors.ISE_VERIFY_FAILED
        assert d["error"]["exit_code"] == 2


class TestScriptTimeout:
    """Test behavior when scripts timeout."""

    def test_verify_timeout(self, mock_scripts):
        """Verify timeout should return failed."""

        def mock_run(cmd, **kwargs):
            script_name = Path(cmd[0]).name
            if "verify" in script_name:
                raise subprocess.TimeoutExpired(cmd, 60)

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

        assert result.status == "failed"
        assert result.error_code == errors.ISE_VERIFY_FAILED
        assert "timed out" in result.error_message.lower()

    def test_deploy_timeout(self, mock_scripts):
        """Deploy timeout should return rolled_back."""

        def mock_run(cmd, **kwargs):
            script_name = Path(cmd[0]).name
            if "deploy" in script_name:
                raise subprocess.TimeoutExpired(cmd, 120)

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

        assert result.status == "rolled_back"
        assert result.error_code == errors.ISE_DEPLOY_FAILED
        assert "timed out" in result.error_message.lower()
