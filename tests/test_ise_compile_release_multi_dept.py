"""Tests for ISE compile/release with multi-department bundles."""

import json
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from engine.ise.release import compile_release, ReleaseResult
from engine.ise import errors


# Multi-department IDL
MULTI_DEPT_IDL = json.dumps({
    "system": "multi-dept-release-test",
    "version": "1.0.0",
    "departments": [
        {"dept_id": "finance"},
        {"dept_id": "hr"},
    ],
    "contracts": [
        {
            "contract_id": "budget-request",
            "provider_dept": "finance",
            "consumers": ["hr"],
            "approval_required": True,
        },
    ],
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
        {"role": "admin", "permissions": [{"resource": "expense", "actions": ["create", "approve"]}]},
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


class TestMultiDeptCompileRelease:
    """Tests for compile_release with multi-department bundles."""

    def test_multi_dept_compile_release_success(self, mock_scripts, monkeypatch):
        """compile_release should succeed with multi-dept IDL."""

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=MULTI_DEPT_IDL,
                bundle_name="multi-dept-bundle",
                validate_finance_pilot=False,  # Skip validation for multi-dept
            )

        assert result.status == "deployed"
        assert result.bundle_name == "multi-dept-bundle"
        assert result.bundle_hash is not None
        assert result.release_id is not None

    def test_multi_dept_staging_has_departments_dir(self, mock_scripts, monkeypatch):
        """Staging bundle should have departments/ directory."""
        staging_path = None

        def mock_run(cmd, **kwargs):
            nonlocal staging_path
            script_name = Path(cmd[0]).name
            if "verify" in script_name:
                staging_path = cmd[1]
                # Check staging bundle structure
                bundle_path = Path(staging_path)
                assert bundle_path.exists()
                assert (bundle_path / "departments").exists()
                assert (bundle_path / "departments").is_dir()

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            compile_release(
                idl=MULTI_DEPT_IDL,
                bundle_name="staging-check-bundle",
                validate_finance_pilot=False,
            )

        assert staging_path is not None
        assert "STAGING" in staging_path

    def test_multi_dept_staging_has_contracts_json(self, mock_scripts, monkeypatch):
        """Staging bundle should have contracts.json."""
        staging_path = None

        def mock_run(cmd, **kwargs):
            nonlocal staging_path
            script_name = Path(cmd[0]).name
            if "verify" in script_name:
                staging_path = cmd[1]
                contracts_path = Path(staging_path) / "contracts.json"
                assert contracts_path.exists()

                with open(contracts_path) as f:
                    contracts_data = json.load(f)
                assert "contracts" in contracts_data
                assert len(contracts_data["contracts"]) == 1

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            compile_release(
                idl=MULTI_DEPT_IDL,
                bundle_name="contracts-check-bundle",
                validate_finance_pilot=False,
            )

        assert staging_path is not None

    def test_multi_dept_staging_has_dept_artifacts(self, mock_scripts, monkeypatch):
        """Staging bundle should have artifacts for each department."""
        staging_path = None

        def mock_run(cmd, **kwargs):
            nonlocal staging_path
            script_name = Path(cmd[0]).name
            if "verify" in script_name:
                staging_path = cmd[1]
                bundle_path = Path(staging_path)

                # Check each department
                for dept_id in ["finance", "hr"]:
                    dept_path = bundle_path / "departments" / dept_id
                    assert dept_path.exists(), f"Department {dept_id} should exist"
                    assert (dept_path / "rbac.json").exists()
                    assert (dept_path / "workflows.json").exists()
                    assert (dept_path / "approvals.json").exists()
                    assert (dept_path / "sod.json").exists()
                    assert (dept_path / "invariants.json").exists()
                    assert (dept_path / "openapi.yaml").exists()

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            compile_release(
                idl=MULTI_DEPT_IDL,
                bundle_name="dept-artifacts-bundle",
                validate_finance_pilot=False,
            )

        assert staging_path is not None

    def test_multi_dept_manifest_has_mode(self, mock_scripts, monkeypatch):
        """Staging bundle manifest should have mode=multi."""
        staging_path = None

        def mock_run(cmd, **kwargs):
            nonlocal staging_path
            script_name = Path(cmd[0]).name
            if "verify" in script_name:
                staging_path = cmd[1]
                manifest_path = Path(staging_path) / "bundle.manifest.json"

                with open(manifest_path) as f:
                    manifest = json.load(f)

                assert manifest["mode"] == "multi"
                assert manifest["departments"] == ["finance", "hr"]

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            compile_release(
                idl=MULTI_DEPT_IDL,
                bundle_name="manifest-mode-bundle",
                validate_finance_pilot=False,
            )

        assert staging_path is not None


class TestMultiDeptScriptOrder:
    """Test script execution order with multi-dept bundles."""

    def test_verify_before_deploy(self, mock_scripts, monkeypatch):
        """Verify should be called before deploy for multi-dept bundles."""
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
                idl=MULTI_DEPT_IDL,
                bundle_name="order-test-bundle",
                validate_finance_pilot=False,
            )

        assert len(call_order) == 2
        assert call_order[0] == "verify_bundle.sh"
        assert call_order[1] == "deploy_engine_prod.sh"
        assert result.status == "deployed"

    def test_verify_fail_stops_deploy(self, mock_scripts, monkeypatch):
        """If verify fails for multi-dept, deploy should NOT be called."""
        call_order = []

        def mock_run(cmd, **kwargs):
            script_name = Path(cmd[0]).name
            call_order.append(script_name)

            result = MagicMock()
            if "verify" in script_name:
                result.returncode = 1
                result.stderr = "Multi-dept verification failed"
            else:
                result.returncode = 0
            result.stdout = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=MULTI_DEPT_IDL,
                bundle_name="verify-fail-bundle",
                validate_finance_pilot=False,
            )

        assert len(call_order) == 1
        assert call_order[0] == "verify_bundle.sh"
        assert result.status == "failed"
        assert result.error_code == errors.ISE_VERIFY_FAILED


class TestMultiDeptDeployFailure:
    """Test deploy failure handling with multi-dept bundles."""

    def test_deploy_fail_returns_rolled_back(self, mock_scripts, monkeypatch):
        """Deploy failure for multi-dept should return rolled_back status."""

        def mock_run(cmd, **kwargs):
            script_name = Path(cmd[0]).name
            result = MagicMock()

            if "verify" in script_name:
                result.returncode = 0
            else:
                result.returncode = 1
                result.stderr = "Deploy failed"

            result.stdout = ""
            return result

        with patch("engine.ise.release.subprocess.run", side_effect=mock_run):
            result = compile_release(
                idl=MULTI_DEPT_IDL,
                bundle_name="deploy-fail-bundle",
                validate_finance_pilot=False,
            )

        assert result.status == "rolled_back"
        assert result.error_code == errors.ISE_DEPLOY_FAILED
        assert result.bundle_hash is not None  # Hash should still be set


class TestMultiDeptValidation:
    """Test validation handling for multi-dept bundles."""

    def test_invalid_dept_id_returns_error(self, mock_scripts, monkeypatch):
        """Invalid dept_id should return compile error."""
        invalid_idl = json.dumps({
            "system": "invalid-dept-test",
            "version": "1.0.0",
            "departments": [
                {"dept_id": "invalid.dept"},  # Invalid: contains dot
            ],
        })

        # No need to mock subprocess - compile will fail before scripts
        result = compile_release(
            idl=invalid_idl,
            bundle_name="invalid-dept-bundle",
            validate_finance_pilot=False,
        )

        assert result.status == "failed"
        assert "ISE_DEPT_ID_INVALID" in (result.error_code or "")

    def test_unknown_provider_returns_error(self, mock_scripts, monkeypatch):
        """Unknown provider_dept should return compile error."""
        invalid_idl = json.dumps({
            "system": "unknown-provider-test",
            "version": "1.0.0",
            "departments": [
                {"dept_id": "finance"},
            ],
            "contracts": [
                {
                    "contract_id": "test-contract",
                    "provider_dept": "unknown",  # Not in departments
                    "consumers": ["finance"],
                },
            ],
        })

        result = compile_release(
            idl=invalid_idl,
            bundle_name="unknown-provider-bundle",
            validate_finance_pilot=False,
        )

        assert result.status == "failed"
        assert "ISE_CONTRACT_PROVIDER_UNKNOWN" in (result.error_code or "")
