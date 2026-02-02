"""Tests for ISE policies.json v1.1 emission."""

import json
import pytest
from pathlib import Path

from engine.ise import compile_bundle_to_memory, parse_idl, errors
from engine.ise.compiler import compile_bundle
from engine.ise.emit.policies_emit import (
    validate_policies_v11,
    emit_policies_v11,
    emit_policies_json,
    validate_field_path,
    ISEPolicyValidationError,
    ALLOWED_PHASES,
    ALLOWED_RULE_TYPES,
)
from engine.ise.idl_parser import IDLPolicy


# Base IDL for finance-pilot (expense entity required)
BASE_IDL = {
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
        {"role": "employee", "permissions": [{"resource": "expense", "actions": ["create"]}]},
        {"role": "manager", "permissions": [{"resource": "expense", "actions": ["approve"]}]},
    ],
}


class TestPolicyEmissionSingle:
    """Tests for single-mode policy emission."""

    def test_single_idl_with_policies_generates_policies_json(self):
        """Single IDL with policies generates bundle_root/policies.json with schema_version 1.1."""
        idl = {
            **BASE_IDL,
            "policies": [
                {
                    "policy_id": "max-expense",
                    "phase": "pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 10000,
                    "message": "Amount exceeds limit",
                }
            ],
        }

        result = compile_bundle_to_memory(
            idl=json.dumps(idl),
            bundle_name="test-bundle",
        )

        assert result["success"] is True
        assert "policies.json" in result["contracts"]

        # Verify policies.json content
        policies = json.loads(result["contracts"]["policies.json"])
        assert policies["policy_schema_version"] == "1.1"
        assert len(policies["policies"]) == 1
        assert policies["policies"][0]["policy_id"] == "max-expense"
        assert policies["policies"][0]["endpoint_sig"] == "POST /finance/expenses"

    def test_single_idl_without_policies_creates_empty_policies_json(self):
        """Single IDL without policies STILL creates policies.json (required contract).

        Per MVP decision (2026-01-17): policies.json is always emitted as a required
        institutional contract. When no policies in IDL, policies.json has empty array.
        """
        result = compile_bundle_to_memory(
            idl=json.dumps(BASE_IDL),
            bundle_name="test-bundle",
        )

        assert result["success"] is True
        assert "policies.json" in result["contracts"]

        # Verify it has empty policies array
        policies_data = json.loads(result["contracts"]["policies.json"])
        assert policies_data["policy_schema_version"] == "1.1"
        assert policies_data["policies"] == []


class TestPolicyEmissionMulti:
    """Tests for multi-mode policy emission."""

    def test_multi_idl_with_dept_policies_generates_per_dept_policies_json(self, tmp_path: Path):
        """Multi IDL with dept_policies generates policies.json per dept correctly."""
        idl = {
            "system": "multi-dept-system",
            "version": "1.0.0",
            "departments": [
                {"dept_id": "finance", "name": "Finance Department"},
                {"dept_id": "hr", "name": "HR Department"},
            ],
            "entities": [
                {"type": "expense", "name": "Expense"},
            ],
            "actors": [
                {"role": "employee", "permissions": []},
            ],
            "dept_policies": {
                "finance": [
                    {
                        "policy_id": "finance-max",
                        "phase": "pre",
                        "endpoint_sig": "POST /finance/expenses",
                        "rule_type": "numeric_max",
                        "field_path": "amount",
                        "value": 5000,
                    }
                ],
                # HR has no policies
            },
        }

        result = compile_bundle(
            idl=json.dumps(idl),
            bundle_name="test-multi",
            output_dir=str(tmp_path),
            validate_finance_pilot=False,  # Skip finance-pilot validation for multi
        )

        assert result.success is True
        assert result.mode == "multi"

        # Finance should have policies.json with policies
        finance_policies_path = tmp_path / "test-multi" / "departments" / "finance" / "policies.json"
        assert finance_policies_path.exists()
        with open(finance_policies_path) as f:
            finance_policies = json.load(f)
        assert finance_policies["policy_schema_version"] == "1.1"
        assert len(finance_policies["policies"]) == 1
        assert finance_policies["policies"][0]["policy_id"] == "finance-max"

        # HR should also have policies.json (required contract), but with empty policies
        hr_policies_path = tmp_path / "test-multi" / "departments" / "hr" / "policies.json"
        assert hr_policies_path.exists()
        with open(hr_policies_path) as f:
            hr_policies = json.load(f)
        assert hr_policies["policies"] == []

    def test_multi_idl_without_dept_policies_creates_empty_policies_json(self, tmp_path: Path):
        """Multi IDL without dept_policies still creates policies.json with empty array.

        Per MVP decision (2026-01-17): policies.json is always emitted.
        """
        idl = {
            "system": "multi-dept-system",
            "version": "1.0.0",
            "departments": [
                {"dept_id": "finance", "name": "Finance Department"},
            ],
            "entities": [
                {"type": "expense", "name": "Expense"},
            ],
            "actors": [
                {"role": "employee", "permissions": []},
            ],
        }

        result = compile_bundle(
            idl=json.dumps(idl),
            bundle_name="test-multi-no-policies",
            output_dir=str(tmp_path),
            validate_finance_pilot=False,
        )

        assert result.success is True
        assert result.mode == "multi"

        # policies.json should exist with empty policies array
        finance_policies_path = tmp_path / "test-multi-no-policies" / "departments" / "finance" / "policies.json"
        assert finance_policies_path.exists()
        with open(finance_policies_path) as f:
            policies_data = json.load(f)
        assert policies_data["policies"] == []


class TestPolicyValidationEndpointSig:
    """Tests for endpoint_sig validation."""

    def test_any_endpoint_sig_allowed(self):
        """Any endpoint_sig should be accepted (Engine neutral, no allowlist)."""
        # Engine is neutral - any endpoint_sig from IDL is allowed
        policy = IDLPolicy(
            policy_id="test",
            phase="pre",
            endpoint_sig="POST /custom/endpoint",
            rule_type="numeric_max",
            field_path="amount",
            value=100,
        )
        # Should not raise - Engine accepts any endpoint_sig
        validate_policies_v11([policy])


class TestPolicyValidationFieldPath:
    """Tests for field_path validation."""

    def test_invalid_field_path_consecutive_dots(self):
        """Policy with field_path containing .. returns ISE_POLICY_INVALID error."""
        idl = {
            **BASE_IDL,
            "policies": [
                {
                    "policy_id": "bad-path-dots",
                    "phase": "pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "rule_type": "numeric_max",
                    "field_path": "a..b",  # Invalid - consecutive dots
                    "value": 100,
                }
            ],
        }

        result = compile_bundle_to_memory(
            idl=json.dumps(idl),
            bundle_name="test-bundle",
        )

        assert result["success"] is False
        assert result["error_code"] == errors.ISE_POLICY_INVALID

    def test_invalid_field_path_slash(self):
        """Policy with field_path containing / returns ISE_POLICY_INVALID error."""
        idl = {
            **BASE_IDL,
            "policies": [
                {
                    "policy_id": "bad-path-slash",
                    "phase": "pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "rule_type": "numeric_max",
                    "field_path": "a/b",  # Invalid - slash
                    "value": 100,
                }
            ],
        }

        result = compile_bundle_to_memory(
            idl=json.dumps(idl),
            bundle_name="test-bundle",
        )

        assert result["success"] is False
        assert result["error_code"] == errors.ISE_POLICY_INVALID

    def test_invalid_field_path_leading_dot(self):
        """Policy with field_path starting with . returns ISE_POLICY_INVALID error."""
        idl = {
            **BASE_IDL,
            "policies": [
                {
                    "policy_id": "bad-path-leading",
                    "phase": "pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "rule_type": "numeric_max",
                    "field_path": ".amount",  # Invalid - leading dot
                    "value": 100,
                }
            ],
        }

        result = compile_bundle_to_memory(
            idl=json.dumps(idl),
            bundle_name="test-bundle",
        )

        assert result["success"] is False
        assert result["error_code"] == errors.ISE_POLICY_INVALID

    def test_valid_field_paths(self):
        """Valid field_path values should pass validation."""
        valid_paths = ["amount", "payload.amount", "user_name", "data.nested.value"]
        for path in valid_paths:
            assert validate_field_path(path) is True

    def test_invalid_field_paths(self):
        """Invalid field_path values should fail validation."""
        invalid_paths = ["", ".a", "a.", "a..b", "a/b", "items[0]", "a b", "a@b"]
        for path in invalid_paths:
            assert validate_field_path(path) is False


class TestPolicyValidationPhaseRuleType:
    """Tests for phase and rule_type validation."""

    def test_invalid_phase_raises_error(self):
        """Policy with invalid phase raises validation error."""
        policy = IDLPolicy(
            policy_id="test",
            phase="invalid",  # Invalid
            endpoint_sig="POST /finance/expenses",
            rule_type="numeric_max",
            field_path="amount",
            value=100,
        )
        with pytest.raises(ISEPolicyValidationError) as exc_info:
            validate_policies_v11([policy])
        assert exc_info.value.code == errors.ISE_POLICY_INVALID
        assert any(d["code"] == "PHASE_INVALID" for d in exc_info.value.details)

    def test_invalid_rule_type_raises_error(self):
        """Policy with invalid rule_type raises validation error."""
        policy = IDLPolicy(
            policy_id="test",
            phase="pre",
            endpoint_sig="POST /finance/expenses",
            rule_type="unknown_rule",  # Invalid
            field_path="amount",
            value=100,
        )
        with pytest.raises(ISEPolicyValidationError) as exc_info:
            validate_policies_v11([policy])
        assert exc_info.value.code == errors.ISE_POLICY_INVALID
        assert any(d["code"] == "RULE_TYPE_INVALID" for d in exc_info.value.details)


class TestManifestIncludesPolicies:
    """Tests for manifest including policies.json."""

    def test_manifest_includes_policies_json_when_present(self):
        """Manifest includes policies.json entry when policies exist."""
        idl = {
            **BASE_IDL,
            "policies": [
                {
                    "policy_id": "test-policy",
                    "phase": "pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 1000,
                }
            ],
        }

        result = compile_bundle_to_memory(
            idl=json.dumps(idl),
            bundle_name="test-bundle",
        )

        assert result["success"] is True

        # Check manifest (loader-compatible format: contracts is array of objects)
        manifest = json.loads(result["contracts"]["bundle.manifest.json"])
        contract_files = [c["file"] for c in manifest["contracts"]]
        assert "policies.json" in contract_files

        # Find policies.json entry and verify hash format (SHA256:...)
        policies_entry = next(c for c in manifest["contracts"] if c["file"] == "policies.json")
        assert policies_entry["sha256"].startswith("SHA256:")
        # Hash part should be 64 chars
        hash_part = policies_entry["sha256"].replace("SHA256:", "")
        assert len(hash_part) == 64

        # Check SHA256s map
        assert "policies.json" in result["sha256s"]
        assert len(result["sha256s"]["policies.json"]) == 64


class TestContractLedgerIncludesPolicies:
    """Tests for contract_ledger including policies.json."""

    def test_contract_ledger_includes_policies_entry(self):
        """Contract ledger includes policies.json entry with path and sha256."""
        idl = {
            **BASE_IDL,
            "policies": [
                {
                    "policy_id": "ledger-test-policy",
                    "phase": "post",
                    "endpoint_sig": "POST /approvals/{approval_id}/decide",
                    "rule_type": "required_field",
                    "field_path": "reason",
                }
            ],
        }

        result = compile_bundle_to_memory(
            idl=json.dumps(idl),
            bundle_name="test-bundle",
        )

        assert result["success"] is True

        # Check contract_ledger
        ledger = json.loads(result["contracts"]["contract_ledger.json"])
        policies_entries = [c for c in ledger["contracts"] if c["contract_name"] == "policies.json"]
        assert len(policies_entries) == 1
        assert "content_hash" in policies_entries[0]
        assert len(policies_entries[0]["content_hash"]) == 64


class TestPoliciesV11Schema:
    """Tests for policies.json v1.1 schema correctness."""

    def test_emit_policies_v11_schema_structure(self):
        """emit_policies_v11 returns correct v1.1 schema structure."""
        policies = [
            IDLPolicy(
                policy_id="test-1",
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                rule_type="numeric_max",
                field_path="amount",
                value=500,
                message="Max 500",
            ),
            IDLPolicy(
                policy_id="test-2",
                phase="post",
                endpoint_sig="POST /approvals/{approval_id}/decide",
                rule_type="required_field",
                field_path="reason",
            ),
        ]

        result = emit_policies_v11(policies)

        assert result["policy_schema_version"] == "1.1"
        assert len(result["policies"]) == 2

        # Check first policy has all expected fields
        p1 = result["policies"][0]
        assert p1["policy_id"] == "test-1"
        assert p1["phase"] == "pre"
        assert p1["endpoint_sig"] == "POST /finance/expenses"
        assert p1["rule_type"] == "numeric_max"
        assert p1["field_path"] == "amount"
        assert p1["value"] == 500
        assert p1["message"] == "Max 500"

        # Check second policy (no value, no message)
        p2 = result["policies"][1]
        assert p2["policy_id"] == "test-2"
        assert "value" not in p2  # value is None, should not be included
        assert "message" not in p2  # message is None, should not be included

    def test_all_rule_types_valid(self):
        """All allowed rule_types should pass validation."""
        for rule_type in ALLOWED_RULE_TYPES:
            policy = IDLPolicy(
                policy_id=f"test-{rule_type}",
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                rule_type=rule_type,
                field_path="amount",
                value=100 if rule_type in ("numeric_max", "numeric_min", "string_max_len") else ["a", "b"],
            )
            # Should not raise
            validate_policies_v11([policy])


class TestBundleWritePolicies:
    """Tests for writing policies.json to disk in bundles."""

    def test_compile_bundle_writes_policies_json(self, tmp_path: Path):
        """compile_bundle writes policies.json to disk."""
        idl = {
            **BASE_IDL,
            "policies": [
                {
                    "policy_id": "disk-test",
                    "phase": "pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 999,
                }
            ],
        }

        result = compile_bundle(
            idl=json.dumps(idl),
            bundle_name="test-disk-bundle",
            output_dir=str(tmp_path),
        )

        assert result.success is True

        # Check policies.json was written
        policies_path = tmp_path / "test-disk-bundle" / "policies.json"
        assert policies_path.exists()

        # Verify content
        with open(policies_path) as f:
            policies = json.load(f)
        assert policies["policy_schema_version"] == "1.1"
        assert len(policies["policies"]) == 1


class TestMultiplePolicyErrors:
    """Tests for multiple validation errors in one policy set."""

    def test_multiple_errors_reported(self):
        """Multiple policy errors should all be reported in details."""
        policies = [
            IDLPolicy(
                policy_id="bad-1",
                phase="invalid",  # Error 1
                endpoint_sig="POST /unknown",  # Engine neutral - accepts any endpoint
                rule_type="bad_type",  # Error 2
                field_path="a..b",  # Error 3
            ),
        ]

        with pytest.raises(ISEPolicyValidationError) as exc_info:
            validate_policies_v11(policies)

        # Should have 3 errors (endpoint_sig is not validated since Engine is neutral)
        assert len(exc_info.value.details) == 3

        # Check error codes present
        error_codes = {d["code"] for d in exc_info.value.details}
        assert "FIELD_PATH_INVALID" in error_codes
        assert "PHASE_INVALID" in error_codes
        assert "RULE_TYPE_INVALID" in error_codes
