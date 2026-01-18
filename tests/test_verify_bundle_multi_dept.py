"""Tests for verify_bundle.sh with multi-department bundles."""

import json
import os
import subprocess
import pytest
from pathlib import Path

from engine.ise.compiler import compile_bundle


# Sample multi-department IDL
MULTI_DEPT_IDL = {
    "system": "MultiDeptVerifyTest",
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
        {"name": "Expense", "entity_type": "expense"},
    ],
    "rbac": {
        "roles": [
            {"name": "admin", "permissions": ["expense.create", "expense.approve"]},
        ]
    },
}

# Single-department IDL for backward compatibility
SINGLE_DEPT_IDL = {
    "system": "SingleDeptVerifyTest",
    "version": "1.0.0",
    "entities": [
        {"name": "Expense", "entity_type": "expense"},
    ],
    "rbac": {
        "roles": [
            {"name": "admin", "permissions": ["expense.create", "expense.approve"]},
        ]
    },
}

# Path to verify_bundle.sh
VERIFY_SCRIPT = Path(__file__).parent.parent / "ops" / "checks" / "verify_bundle.sh"


class TestVerifyBundleMultiDept:
    """Tests for verify_bundle.sh with multi-department bundles."""

    @pytest.fixture
    def output_dir(self, tmp_path: Path) -> str:
        """Create temporary output directory."""
        return str(tmp_path / "bundles")

    def test_verify_multi_dept_bundle_passes(self, output_dir: str):
        """verify_bundle.sh should pass for valid multi-dept bundle."""
        # Compile multi-dept bundle
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-verify-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )
        assert result.success is True
        assert result.mode == "multi"

        # Run verify script
        proc = subprocess.run(
            [str(VERIFY_SCRIPT), result.bundle_path],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should pass
        assert proc.returncode == 0, f"Verify failed: {proc.stdout}\n{proc.stderr}"
        assert "VERIFICATION PASSED" in proc.stdout

    def test_verify_single_dept_bundle_passes(self, output_dir: str):
        """verify_bundle.sh should pass for valid single-dept bundle."""
        # Compile single-dept bundle
        idl = json.dumps(SINGLE_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="single-verify-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )
        assert result.success is True
        assert result.mode == "single"

        # Run verify script
        proc = subprocess.run(
            [str(VERIFY_SCRIPT), result.bundle_path],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should pass
        assert proc.returncode == 0, f"Verify failed: {proc.stdout}\n{proc.stderr}"
        assert "VERIFICATION PASSED" in proc.stdout

    def test_verify_detects_mode(self, output_dir: str):
        """verify_bundle.sh should correctly detect bundle mode."""
        # Compile multi-dept bundle
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="mode-detect-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # Run verify script
        proc = subprocess.run(
            [str(VERIFY_SCRIPT), result.bundle_path],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should detect multi mode
        assert "Bundle mode: multi" in proc.stdout

    def test_verify_fails_missing_contracts_json(self, output_dir: str):
        """verify_bundle.sh should fail if contracts.json missing in multi mode."""
        # Compile multi-dept bundle
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="missing-contracts-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # Remove contracts.json
        contracts_path = Path(result.bundle_path) / "contracts.json"
        contracts_path.unlink()

        # Run verify script
        proc = subprocess.run(
            [str(VERIFY_SCRIPT), result.bundle_path],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should fail
        assert proc.returncode != 0
        assert "contracts.json not found" in proc.stdout

    def test_verify_fails_missing_department_dir(self, output_dir: str):
        """verify_bundle.sh should fail if department directory missing."""
        # Compile multi-dept bundle
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="missing-dept-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # Remove one department directory
        import shutil
        finance_path = Path(result.bundle_path) / "departments" / "finance"
        shutil.rmtree(finance_path)

        # Run verify script
        proc = subprocess.run(
            [str(VERIFY_SCRIPT), result.bundle_path],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should fail
        assert proc.returncode != 0
        assert "Department directory not found" in proc.stdout or "departments/finance" in proc.stdout

    def test_verify_fails_missing_department_artifact(self, output_dir: str):
        """verify_bundle.sh should fail if department artifact missing."""
        # Compile multi-dept bundle
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="missing-artifact-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # Remove rbac.json from finance department
        rbac_path = Path(result.bundle_path) / "departments" / "finance" / "rbac.json"
        rbac_path.unlink()

        # Run verify script
        proc = subprocess.run(
            [str(VERIFY_SCRIPT), result.bundle_path],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should fail
        assert proc.returncode != 0
        assert "Missing artifact" in proc.stdout or "rbac.json" in proc.stdout

    def test_verify_fails_hash_mismatch(self, output_dir: str):
        """verify_bundle.sh should fail if hash mismatch detected."""
        # Compile multi-dept bundle
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="hash-mismatch-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # Modify contracts.json content (this will cause hash mismatch)
        contracts_path = Path(result.bundle_path) / "contracts.json"
        with open(contracts_path, "r") as f:
            data = json.load(f)
        data["modified"] = True
        with open(contracts_path, "w") as f:
            json.dump(data, f)

        # Run verify script
        proc = subprocess.run(
            [str(VERIFY_SCRIPT), result.bundle_path],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should fail due to hash mismatch
        assert proc.returncode != 0
        assert "Hash mismatch" in proc.stdout

    def test_verify_validates_all_departments(self, output_dir: str):
        """verify_bundle.sh should validate artifacts in all departments."""
        # Compile multi-dept bundle
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="all-depts-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # Run verify script
        proc = subprocess.run(
            [str(VERIFY_SCRIPT), result.bundle_path],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should check both departments
        assert "Checking department: finance" in proc.stdout
        assert "Checking department: hr" in proc.stdout
        assert proc.returncode == 0

    def test_verify_nonexistent_bundle(self, tmp_path: Path):
        """verify_bundle.sh should fail for nonexistent bundle."""
        fake_path = tmp_path / "nonexistent"

        proc = subprocess.run(
            [str(VERIFY_SCRIPT), str(fake_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert proc.returncode != 0
        assert "does not exist" in proc.stdout
