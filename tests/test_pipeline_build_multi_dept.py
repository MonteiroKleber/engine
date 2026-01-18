"""Tests for pipeline build with multi-department bundles.

Note: The NL pipeline doesn't currently generate multi-dept IDL from natural
language. These tests verify that the ISE compiler (which the pipeline uses)
correctly handles multi-dept bundles and that trace.json includes mode info.
"""

import json
import os
import pytest
from pathlib import Path

from engine.ise.compiler import compile_bundle
from engine.pipeline.hashes import compute_hash


# Sample multi-department IDL
MULTI_DEPT_IDL = {
    "system": "MultiDeptPipelineTest",
    "version": "1.0.0",
    "departments": [
        {"dept_id": "finance"},
        {"dept_id": "hr"},
        {"dept_id": "procurement"},
    ],
    "contracts": [
        {
            "contract_id": "budget-request",
            "provider_dept": "finance",
            "consumers": ["hr", "procurement"],
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


class TestPipelineBuildMultiDept:
    """Tests for compile_bundle with multi-dept IDL (used by pipeline)."""

    @pytest.fixture
    def output_dir(self, tmp_path: Path) -> str:
        """Create temporary output directory."""
        return str(tmp_path / "bundles" / "dev-runs" / "test-run-id")

    def test_compile_multi_dept_creates_bundle(self, output_dir: str):
        """compile_bundle should create valid multi-dept bundle."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="pipeline-multi-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        assert result.success is True
        assert result.mode == "multi"
        assert result.bundle_path is not None
        assert Path(result.bundle_path).exists()

    def test_compile_multi_dept_has_contracts_json(self, output_dir: str):
        """Multi-dept bundle should have contracts.json at root."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="contracts-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        contracts_path = Path(result.bundle_path) / "contracts.json"
        assert contracts_path.exists()

        with open(contracts_path) as f:
            contracts_data = json.load(f)

        assert "contracts" in contracts_data
        assert len(contracts_data["contracts"]) == 1
        assert contracts_data["contracts"][0]["contract_id"] == "budget-request"

    def test_compile_multi_dept_has_departments_dir(self, output_dir: str):
        """Multi-dept bundle should have departments/ directory."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="depts-dir-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        depts_path = Path(result.bundle_path) / "departments"
        assert depts_path.exists()
        assert depts_path.is_dir()

        # Check each department exists
        for dept_id in ["finance", "hr", "procurement"]:
            dept_path = depts_path / dept_id
            assert dept_path.exists(), f"Department {dept_id} should exist"
            assert (dept_path / "rbac.json").exists()
            assert (dept_path / "workflows.json").exists()
            assert (dept_path / "openapi.yaml").exists()

    def test_compile_result_includes_departments(self, output_dir: str):
        """CompileResult should include departments list."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="result-depts-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        assert result.departments == ["finance", "hr", "procurement"]

    def test_manifest_has_mode_and_departments(self, output_dir: str):
        """Manifest should include mode and departments."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="manifest-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        manifest_path = Path(result.bundle_path) / "bundle.manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["mode"] == "multi"
        assert manifest["departments"] == ["finance", "hr", "procurement"]

    def test_bundle_hash_reflects_all_content(self, output_dir: str):
        """Bundle hash should include all files including per-dept."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="hash-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # All files should have SHA256 in result
        assert "contracts.json" in result.sha256s
        assert "departments/finance/rbac.json" in result.sha256s
        assert "departments/hr/rbac.json" in result.sha256s
        assert "departments/procurement/rbac.json" in result.sha256s

        # bundle_hash should be set
        assert result.bundle_hash is not None
        assert len(result.bundle_hash) == 64  # SHA256 hex string


class TestTraceJsonMultiDept:
    """Tests for trace.json generation with multi-dept bundles."""

    @pytest.fixture
    def output_dir(self, tmp_path: Path) -> str:
        """Create temporary output directory."""
        run_dir = tmp_path / "bundles" / "dev-runs" / "test-run-id"
        run_dir.mkdir(parents=True, exist_ok=True)
        return str(run_dir)

    def test_trace_json_includes_mode(self, output_dir: str):
        """Trace should include mode field."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="trace-mode-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # Simulate what orchestrator does - write trace.json
        run_dir = Path(output_dir)
        bundle_path = Path(result.bundle_path)
        manifest_path = bundle_path / "bundle.manifest.json"
        ledger_path = bundle_path / "contract_ledger.json"

        manifest_hash = compute_hash(manifest_path.read_bytes()) if manifest_path.exists() else ""
        ledger_hash = compute_hash(ledger_path.read_bytes()) if ledger_path.exists() else ""

        trace_data = {
            "run_id": "test-run-id",
            "bundle_name": "trace-mode-test",
            "mode": result.mode,
            "sir_sha256": "test-sir-hash",
            "draft_sha256": "test-draft-hash",
            "final_idl_sha256": "test-final-hash",
            "bundle_manifest_sha256": manifest_hash,
            "contract_ledger_sha256": ledger_hash,
        }
        if result.mode == "multi" and result.departments:
            trace_data["departments"] = result.departments

        trace_path = run_dir / "trace.json"
        trace_path.write_text(json.dumps(trace_data, indent=2))

        # Read and verify
        with open(trace_path) as f:
            loaded = json.load(f)

        assert loaded["mode"] == "multi"
        assert loaded["departments"] == ["finance", "hr", "procurement"]

    def test_single_mode_trace_no_departments(self, output_dir: str):
        """Single mode trace should not have departments field."""
        single_idl = {
            "system": "SingleTest",
            "version": "1.0.0",
            "entities": [{"name": "Expense", "entity_type": "expense"}],
        }

        idl = json.dumps(single_idl)
        result = compile_bundle(
            idl=idl,
            bundle_name="trace-single-test",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # Simulate trace generation
        trace_data = {
            "run_id": "test-run-id",
            "bundle_name": "trace-single-test",
            "mode": result.mode,
        }
        if result.mode == "multi" and result.departments:
            trace_data["departments"] = result.departments

        assert trace_data["mode"] == "single"
        assert "departments" not in trace_data
