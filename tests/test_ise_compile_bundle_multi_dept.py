"""Tests for ISE multi-department bundle compilation."""

import json
import os
import pytest
from pathlib import Path

from engine.ise.compiler import compile_bundle, CompileResult
from engine.ise.idl_parser import (
    parse_idl,
    IDLParseError,
    ParsedIDL,
    IDLDepartment,
    IDLContract,
)
from engine.ise import errors


# Sample multi-department IDL for testing
MULTI_DEPT_IDL = {
    "system": "MultiDeptSystem",
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
            "input_schema": {"type": "object", "properties": {"amount": {"type": "number"}}},
            "output_schema": {"type": "object", "properties": {"approved": {"type": "boolean"}}},
            "approval_required": True,
        },
        {
            "contract_id": "headcount-approval",
            "provider_dept": "hr",
            "consumers": ["finance"],
            "input_schema": {"type": "object", "properties": {"count": {"type": "integer"}}},
            "output_schema": {"type": "object", "properties": {"approved": {"type": "boolean"}}},
            "approval_required": False,
        },
    ],
    "entities": [
        {"name": "Expense", "entity_type": "expense"},
    ],
    "rbac": {
        "roles": [
            {"name": "admin", "permissions": ["expense.create", "expense.read", "expense.approve"]},
            {"name": "analyst", "permissions": ["expense.create", "expense.read"]},
        ]
    },
    "approvals": {
        "rules": [
            {
                "rule_name": "expense_approval",
                "trigger": {"api": "POST /finance/expenses"},
                "approver_roles": ["admin"],
                "quorum": 1,
            }
        ]
    },
}


# Single department IDL (for backward compatibility testing)
SINGLE_DEPT_IDL = {
    "system": "SingleDeptSystem",
    "version": "1.0.0",
    "entities": [
        {"name": "Expense", "entity_type": "expense"},
    ],
    "rbac": {
        "roles": [
            {"name": "admin", "permissions": ["expense.create", "expense.read", "expense.approve"]},
        ]
    },
}


class TestIDLParserMultiDept:
    """Tests for IDL parser multi-department support."""

    def test_parse_departments(self):
        """Should parse departments list."""
        parsed = parse_idl(MULTI_DEPT_IDL)

        assert parsed.is_multi_dept is True
        assert len(parsed.departments) == 3
        dept_ids = [d.dept_id for d in parsed.departments]
        assert "finance" in dept_ids
        assert "hr" in dept_ids
        assert "procurement" in dept_ids

    def test_parse_contracts(self):
        """Should parse interdepartmental contracts."""
        parsed = parse_idl(MULTI_DEPT_IDL)

        assert len(parsed.contracts) == 2
        contract_ids = [c.contract_id for c in parsed.contracts]
        assert "budget-request" in contract_ids
        assert "headcount-approval" in contract_ids

        # Check budget-request contract details
        budget_contract = next(c for c in parsed.contracts if c.contract_id == "budget-request")
        assert budget_contract.provider_dept == "finance"
        assert sorted(budget_contract.consumers) == ["hr", "procurement"]
        assert budget_contract.approval_required is True

    def test_single_dept_not_multi(self):
        """Single-dept IDL should not be flagged as multi-dept."""
        parsed = parse_idl(SINGLE_DEPT_IDL)

        assert parsed.is_multi_dept is False
        assert len(parsed.departments) == 0
        assert len(parsed.contracts) == 0

    def test_invalid_dept_id_with_dot(self):
        """Dept ID with dot should raise error."""
        idl = {
            "system": "Test",
            "version": "1.0.0",
            "departments": [{"dept_id": "dept.invalid"}],
        }
        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)
        assert exc_info.value.code == errors.ISE_DEPT_ID_INVALID

    def test_invalid_dept_id_with_slash(self):
        """Dept ID with slash should raise error."""
        idl = {
            "system": "Test",
            "version": "1.0.0",
            "departments": [{"dept_id": "../etc"}],
        }
        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)
        assert exc_info.value.code == errors.ISE_DEPT_ID_INVALID

    def test_invalid_dept_id_with_space(self):
        """Dept ID with space should raise error."""
        idl = {
            "system": "Test",
            "version": "1.0.0",
            "departments": [{"dept_id": "dept name"}],
        }
        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)
        assert exc_info.value.code == errors.ISE_DEPT_ID_INVALID

    def test_valid_dept_id_with_hyphen_underscore(self):
        """Dept ID with hyphen and underscore should be valid."""
        idl = {
            "system": "Test",
            "version": "1.0.0",
            "departments": [
                {"dept_id": "dept-one"},
                {"dept_id": "dept_two"},
                {"dept_id": "Dept123"},
            ],
        }
        parsed = parse_idl(idl)
        assert len(parsed.departments) == 3

    def test_invalid_contract_id(self):
        """Invalid contract ID should raise error."""
        idl = {
            "system": "Test",
            "version": "1.0.0",
            "departments": [{"dept_id": "finance"}],
            "contracts": [
                {
                    "contract_id": "invalid.contract",
                    "provider_dept": "finance",
                    "consumers": [],
                }
            ],
        }
        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)
        assert exc_info.value.code == errors.ISE_CONTRACT_ID_INVALID

    def test_unknown_provider_dept(self):
        """Contract with unknown provider should raise error."""
        idl = {
            "system": "Test",
            "version": "1.0.0",
            "departments": [{"dept_id": "finance"}],
            "contracts": [
                {
                    "contract_id": "test-contract",
                    "provider_dept": "unknown",
                    "consumers": ["finance"],
                }
            ],
        }
        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)
        assert exc_info.value.code == errors.ISE_CONTRACT_PROVIDER_UNKNOWN

    def test_unknown_consumer_dept(self):
        """Contract with unknown consumer should raise error."""
        idl = {
            "system": "Test",
            "version": "1.0.0",
            "departments": [{"dept_id": "finance"}],
            "contracts": [
                {
                    "contract_id": "test-contract",
                    "provider_dept": "finance",
                    "consumers": ["unknown"],
                }
            ],
        }
        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)
        assert exc_info.value.code == errors.ISE_CONTRACT_CONSUMER_UNKNOWN


class TestCompileMultiDeptBundle:
    """Tests for multi-department bundle compilation."""

    @pytest.fixture
    def output_dir(self, tmp_path: Path) -> str:
        """Create temporary output directory."""
        return str(tmp_path / "bundles")

    def test_compile_multi_dept_success(self, output_dir: str):
        """Multi-dept IDL should compile successfully."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        assert result.success is True
        assert result.mode == "multi"
        assert sorted(result.departments) == ["finance", "hr", "procurement"]

    def test_compile_multi_dept_creates_departments_dir(self, output_dir: str):
        """Multi-dept bundle should create departments/ directory."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        bundle_path = Path(result.bundle_path)
        assert (bundle_path / "departments").exists()
        assert (bundle_path / "departments").is_dir()

    def test_compile_multi_dept_creates_per_dept_artifacts(self, output_dir: str):
        """Each department should have its own contract files."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        bundle_path = Path(result.bundle_path)

        for dept_id in ["finance", "hr", "procurement"]:
            dept_path = bundle_path / "departments" / dept_id
            assert dept_path.exists(), f"Department dir for {dept_id} should exist"
            assert (dept_path / "rbac.json").exists()
            assert (dept_path / "workflows.json").exists()
            assert (dept_path / "approvals.json").exists()
            assert (dept_path / "sod.json").exists()
            assert (dept_path / "invariants.json").exists()
            assert (dept_path / "openapi.yaml").exists()

    def test_compile_multi_dept_creates_contracts_json(self, output_dir: str):
        """Multi-dept bundle should have contracts.json at root."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        bundle_path = Path(result.bundle_path)
        contracts_path = bundle_path / "contracts.json"
        assert contracts_path.exists()

        with open(contracts_path) as f:
            contracts_data = json.load(f)

        assert "contracts" in contracts_data
        assert len(contracts_data["contracts"]) == 2
        contract_ids = [c["contract_id"] for c in contracts_data["contracts"]]
        assert "budget-request" in contract_ids
        assert "headcount-approval" in contract_ids

    def test_compile_multi_dept_manifest_has_mode(self, output_dir: str):
        """Manifest should include mode=multi in _metadata."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        bundle_path = Path(result.bundle_path)
        manifest_path = bundle_path / "bundle.manifest.json"

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Mode and departments are now in _metadata (loader-compatible format)
        assert manifest["_metadata"]["mode"] == "multi"
        assert sorted(manifest["_metadata"]["departments"]) == ["finance", "hr", "procurement"]

    def test_compile_multi_dept_manifest_has_all_contracts(self, output_dir: str):
        """Manifest should list all contract files including per-dept."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        bundle_path = Path(result.bundle_path)
        manifest_path = bundle_path / "bundle.manifest.json"

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Contracts is now an array of objects with "file" key (loader-compatible format)
        contract_files = [c["file"] for c in manifest["contracts"]]

        # Should have root-level files
        # Note: manifest is generated before adding itself to the dict,
        # so it only includes contracts known at generation time
        assert "contracts.json" in contract_files

        # Should have per-department files
        for dept_id in ["finance", "hr", "procurement"]:
            assert f"departments/{dept_id}/rbac.json" in contract_files
            assert f"departments/{dept_id}/workflows.json" in contract_files

    def test_compile_single_dept_backward_compatible(self, output_dir: str):
        """Single-dept IDL should still compile as before."""
        idl = json.dumps(SINGLE_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="single-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        assert result.success is True
        assert result.mode == "single"
        assert result.departments == []

        bundle_path = Path(result.bundle_path)
        # Should NOT have departments/ directory
        assert not (bundle_path / "departments").exists()
        # Should have flat structure
        assert (bundle_path / "rbac.json").exists()
        assert (bundle_path / "workflows.json").exists()

    def test_compile_invalid_dept_id_returns_error(self, output_dir: str):
        """Invalid dept_id should return error result."""
        idl = json.dumps({
            "system": "Test",
            "version": "1.0.0",
            "departments": [{"dept_id": "invalid.dept"}],
        })
        result = compile_bundle(
            idl=idl,
            bundle_name="invalid-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        assert result.success is False
        assert result.error_code == errors.ISE_DEPT_ID_INVALID

    def test_compile_unknown_provider_returns_error(self, output_dir: str):
        """Unknown provider in contract should return error."""
        idl = json.dumps({
            "system": "Test",
            "version": "1.0.0",
            "departments": [{"dept_id": "finance"}],
            "contracts": [
                {
                    "contract_id": "test-contract",
                    "provider_dept": "unknown",
                    "consumers": ["finance"],
                }
            ],
        })
        result = compile_bundle(
            idl=idl,
            bundle_name="invalid-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        assert result.success is False
        assert result.error_code == errors.ISE_CONTRACT_PROVIDER_UNKNOWN


class TestContractsEmitter:
    """Tests for contracts.json emitter."""

    def test_emit_contracts_structure(self):
        """Emitted contracts should have correct structure."""
        from engine.ise.emit.contracts_emit import emit_contracts

        parsed = parse_idl(MULTI_DEPT_IDL)
        contracts_data = emit_contracts(parsed)

        assert "version" in contracts_data
        assert contracts_data["version"] == "1.0"
        assert "contracts" in contracts_data
        assert isinstance(contracts_data["contracts"], list)

    def test_emit_contracts_content(self):
        """Emitted contracts should have correct content."""
        from engine.ise.emit.contracts_emit import emit_contracts

        parsed = parse_idl(MULTI_DEPT_IDL)
        contracts_data = emit_contracts(parsed)

        contracts = contracts_data["contracts"]
        assert len(contracts) == 2

        budget_contract = next(c for c in contracts if c["contract_id"] == "budget-request")
        assert budget_contract["provider_dept"] == "finance"
        assert sorted(budget_contract["consumers"]) == ["hr", "procurement"]
        assert budget_contract["approval_required"] is True
        assert "input_schema" in budget_contract
        assert "output_schema" in budget_contract

    def test_emit_contracts_empty_when_no_contracts(self):
        """Should return empty contracts list when no contracts defined."""
        from engine.ise.emit.contracts_emit import emit_contracts

        parsed = parse_idl(SINGLE_DEPT_IDL)
        contracts_data = emit_contracts(parsed)

        assert contracts_data["contracts"] == []


class TestMultiDeptCompileResult:
    """Tests for CompileResult in multi-dept mode."""

    @pytest.fixture
    def output_dir(self, tmp_path: Path) -> str:
        """Create temporary output directory."""
        return str(tmp_path / "bundles")

    def test_result_has_departments_list(self, output_dir: str):
        """CompileResult should include departments list."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        assert result.departments == ["finance", "hr", "procurement"]

    def test_result_contracts_include_dept_paths(self, output_dir: str):
        """CompileResult contracts should include department paths."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        # Check that contracts list includes dept-scoped paths
        assert "departments/finance/rbac.json" in result.contracts
        assert "departments/hr/rbac.json" in result.contracts
        assert "departments/procurement/rbac.json" in result.contracts
        assert "contracts.json" in result.contracts

    def test_result_sha256s_include_all_files(self, output_dir: str):
        """SHA256s should be computed for all files including nested."""
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name="multi-dept-bundle",
            output_dir=output_dir,
            validate_finance_pilot=False,
        )

        assert "departments/finance/rbac.json" in result.sha256s
        assert "contracts.json" in result.sha256s
        assert "bundle.manifest.json" in result.sha256s

        # All SHA256s should be 64-character hex strings
        for sha in result.sha256s.values():
            assert len(sha) == 64
            assert all(c in "0123456789abcdef" for c in sha)
