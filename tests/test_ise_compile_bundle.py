"""Tests for ISE bundle compilation."""

import json
import pytest

from engine.ise import (
    compile_bundle_to_memory,
    parse_idl,
    errors,
)


# Sample IDL for finance-pilot MVP
VALID_IDL = json.dumps({
    "system": "finance-pilot",
    "version": "1.0.0",
    "entities": [
        {
            "type": "expense",
            "name": "Expense",
            "fields": [
                {"name": "amount", "type": "number", "required": True},
                {"name": "description", "type": "string", "required": False},
            ],
        }
    ],
    "actors": [
        {
            "role": "employee",
            "permissions": [
                {"resource": "expense", "actions": ["create"]},
            ],
        },
        {
            "role": "manager",
            "permissions": [
                {"resource": "expense", "actions": ["create", "approve"]},
            ],
        },
    ],
    "usecases": [
        {
            "name": "Submit Expense",
            "actor": "employee",
            "description": "Employee submits expense that must be approved by manager",
            "main_flow": "create -> approve",
        }
    ],
})


# IDL without expense entity (should fail finance-pilot validation)
IDL_NO_EXPENSE = json.dumps({
    "system": "other-system",
    "version": "1.0.0",
    "entities": [
        {
            "type": "invoice",
            "name": "Invoice",
            "fields": [
                {"name": "total", "type": "number", "required": True},
            ],
        }
    ],
    "actors": [
        {"role": "user", "permissions": []},
    ],
    "usecases": [],
})


# IDL with approval keywords
IDL_WITH_APPROVAL = json.dumps({
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
        {"role": "manager", "permissions": [{"resource": "expense", "actions": ["approve"]}]},
    ],
    "usecases": [
        {
            "name": "Submit Expense",
            "actor": "employee",
            "description": "Employee submits expense that must be approved by manager",
            "main_flow": "create -> approve",
            "approval_role": "manager",
        }
    ],
})


# IDL with SoD keywords
IDL_WITH_SOD = json.dumps({
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
        {"role": "manager", "permissions": [{"resource": "expense", "actions": ["approve"]}]},
    ],
    "usecases": [
        {
            "name": "Submit Expense",
            "actor": "employee",
            "description": "Employee cannot approve their own expense. Segregation of duties required.",
            "main_flow": "create -> approve",
            "approval_role": "manager",
        }
    ],
})


class TestCompileBundleToMemory:
    """Test compile_bundle_to_memory function."""

    def test_compile_valid_idl(self):
        """Test compiling valid IDL produces all contracts."""
        result = compile_bundle_to_memory(
            idl=VALID_IDL,
            bundle_name="test-bundle",
        )

        assert result["success"] is True
        assert result["bundle_name"] == "test-bundle"
        assert result["version"] == "1.0.0"
        assert result["bundle_hash"] is not None

        # Check all expected contracts exist
        contracts = result["contracts"]
        assert "bundle.manifest.json" in contracts
        assert "contract_ledger.json" in contracts
        assert "rbac.json" in contracts
        assert "workflows.json" in contracts
        assert "approvals.json" in contracts
        assert "sod.json" in contracts
        assert "invariants.json" in contracts
        assert "openapi.yaml" in contracts

        # Check SHA256 hashes exist for all contracts
        sha256s = result["sha256s"]
        for contract_name in contracts:
            assert contract_name in sha256s
            assert len(sha256s[contract_name]) == 64  # SHA256 hex is 64 chars

    def test_compile_invalid_json(self):
        """Test compiling invalid JSON returns error."""
        result = compile_bundle_to_memory(
            idl="not valid json {",
            bundle_name="test-bundle",
        )

        assert result["success"] is False
        # IDLParseError wraps JSONDecodeError with ISE_IDL_PARSE_FAILED
        assert result["error_code"] in (errors.ISE_IDL_INVALID_JSON, errors.ISE_IDL_PARSE_FAILED)

    def test_compile_no_expense_fails_finance_pilot(self):
        """Test IDL without expense entity fails finance-pilot validation."""
        result = compile_bundle_to_memory(
            idl=IDL_NO_EXPENSE,
            bundle_name="test-bundle",
            validate_finance_pilot=True,
        )

        assert result["success"] is False
        assert result["error_code"] == errors.ISE_IDL_INSUFFICIENT
        assert "expense" in result["error_message"].lower()

    def test_compile_no_expense_passes_without_validation(self):
        """Test IDL without expense entity passes when validation disabled."""
        result = compile_bundle_to_memory(
            idl=IDL_NO_EXPENSE,
            bundle_name="test-bundle",
            validate_finance_pilot=False,
        )

        assert result["success"] is True

    def test_compile_with_approval_keywords(self):
        """Test IDL with approval keywords generates approval rules."""
        result = compile_bundle_to_memory(
            idl=IDL_WITH_APPROVAL,
            bundle_name="test-bundle",
        )

        assert result["success"] is True

        # Check approvals contract has rules
        approvals = json.loads(result["contracts"]["approvals.json"])
        assert "rules" in approvals
        assert len(approvals["rules"]) > 0

    def test_compile_with_sod_keywords(self):
        """Test IDL with SoD keywords generates SoD rules."""
        result = compile_bundle_to_memory(
            idl=IDL_WITH_SOD,
            bundle_name="test-bundle",
        )

        assert result["success"] is True

        # Check sod contract has rules
        sod = json.loads(result["contracts"]["sod.json"])
        assert "rules" in sod
        assert len(sod["rules"]) > 0

    def test_deterministic_output(self):
        """Test same IDL produces same output (determinism)."""
        result1 = compile_bundle_to_memory(
            idl=VALID_IDL,
            bundle_name="test-bundle",
        )
        result2 = compile_bundle_to_memory(
            idl=VALID_IDL,
            bundle_name="test-bundle",
        )

        # Bundle hash should be identical
        assert result1["bundle_hash"] == result2["bundle_hash"]

        # All contract SHA256s should be identical
        for contract_name in result1["sha256s"]:
            # Skip timestamp-containing files
            if contract_name in ("bundle.manifest.json", "contract_ledger.json"):
                continue
            assert result1["sha256s"][contract_name] == result2["sha256s"][contract_name]

    def test_rbac_contract_structure(self):
        """Test RBAC contract has correct structure."""
        result = compile_bundle_to_memory(
            idl=VALID_IDL,
            bundle_name="test-bundle",
        )

        rbac = json.loads(result["contracts"]["rbac.json"])
        assert rbac["version"] == "1.0"
        assert rbac["name"] == "rbac"
        assert "roles" in rbac

        # Check roles - permissions are embedded in roles
        roles = {r["name"] for r in rbac["roles"]}
        assert "employee" in roles
        assert "manager" in roles

        # Check that roles have permissions
        for role in rbac["roles"]:
            assert "permissions" in role

    def test_openapi_contract_structure(self):
        """Test OpenAPI contract has correct structure."""
        result = compile_bundle_to_memory(
            idl=VALID_IDL,
            bundle_name="test-bundle",
        )

        import yaml
        openapi = yaml.safe_load(result["contracts"]["openapi.yaml"])

        assert openapi["openapi"] == "3.0.3"
        assert "info" in openapi
        assert openapi["info"]["title"] == "finance-pilot API"
        assert openapi["info"]["version"] == "1.0.0"
        assert "paths" in openapi
        assert "/finance/expenses" in openapi["paths"]

    def test_invariants_contract_structure(self):
        """Test invariants contract has correct structure."""
        result = compile_bundle_to_memory(
            idl=VALID_IDL,
            bundle_name="test-bundle",
        )

        invariants = json.loads(result["contracts"]["invariants.json"])
        assert invariants["version"] == "1.0"
        assert invariants["name"] == "invariants"
        assert "expense" in invariants

        # Check amount constraints
        assert "amount" in invariants["expense"]
        assert "min" in invariants["expense"]["amount"]
        assert "max" in invariants["expense"]["amount"]

    def test_workflows_contract_structure(self):
        """Test workflows contract has correct structure."""
        result = compile_bundle_to_memory(
            idl=VALID_IDL,
            bundle_name="test-bundle",
        )

        workflows = json.loads(result["contracts"]["workflows.json"])
        assert workflows["version"] == "1.0"
        assert workflows["name"] == "workflows"
        assert "workflows" in workflows
        assert len(workflows["workflows"]) > 0


class TestParseIDL:
    """Test IDL parser."""

    def test_parse_valid_idl(self):
        """Test parsing valid IDL."""
        parsed = parse_idl(VALID_IDL)

        assert parsed.system_name == "finance-pilot"
        assert parsed.version == "1.0.0"
        assert len(parsed.entities) == 1
        assert parsed.entities[0].entity_type == "expense"
        assert len(parsed.actors) == 2
        assert len(parsed.usecases) == 1

    def test_parse_minimal_idl(self):
        """Test parsing minimal IDL."""
        minimal = json.dumps({
            "entities": [{"type": "expense", "name": "Expense"}],
        })
        parsed = parse_idl(minimal)

        assert parsed.system_name == "Unknown"
        assert parsed.version == "0.0.0"
        assert len(parsed.entities) == 1

    def test_finance_pilot_validation_pass(self):
        """Test finance-pilot validation passes with expense entity."""
        parsed = parse_idl(VALID_IDL)
        is_valid, missing = parsed.validate_for_finance_pilot()

        assert is_valid is True
        assert len(missing) == 0

    def test_finance_pilot_validation_fail(self):
        """Test finance-pilot validation fails without expense entity."""
        parsed = parse_idl(IDL_NO_EXPENSE)
        is_valid, missing = parsed.validate_for_finance_pilot()

        assert is_valid is False
        assert "expense entity" in missing

    def test_approval_keyword_detection_en(self):
        """Test approval keyword detection in English."""
        idl = json.dumps({
            "entities": [{"type": "expense", "name": "Expense"}],
            "usecases": [
                {
                    "name": "Submit",
                    "description": "This must be approved by a manager",
                }
            ],
        })
        parsed = parse_idl(idl)

        assert parsed.usecases[0].has_approval is True

    def test_approval_keyword_detection_pt(self):
        """Test approval keyword detection in Portuguese."""
        idl = json.dumps({
            "entities": [{"type": "expense", "name": "Expense"}],
            "usecases": [
                {
                    "name": "Submeter",
                    "description": "Deve ser aprovado pelo gerente",
                }
            ],
        })
        parsed = parse_idl(idl)

        assert parsed.usecases[0].has_approval is True

    def test_sod_keyword_detection_en(self):
        """Test SoD keyword detection in English."""
        idl = json.dumps({
            "entities": [{"type": "expense", "name": "Expense"}],
            "usecases": [
                {
                    "name": "Submit",
                    "description": "Employee cannot approve their own expense",
                }
            ],
        })
        parsed = parse_idl(idl)

        assert parsed.usecases[0].has_sod is True

    def test_sod_keyword_detection_pt(self):
        """Test SoD keyword detection in Portuguese."""
        idl = json.dumps({
            "entities": [{"type": "expense", "name": "Expense"}],
            "usecases": [
                {
                    "name": "Submeter",
                    "description": "Funcionario nao pode aprovar sua propria despesa",
                }
            ],
        })
        parsed = parse_idl(idl)

        assert parsed.usecases[0].has_sod is True
