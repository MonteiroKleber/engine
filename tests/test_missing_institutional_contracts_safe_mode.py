"""Tests for missing institutional contracts → SAFE_MODE.

Per MVP decision (2026-01-17): policies.json, mandates.json, autonomy.json are mandatory.
If any is missing from the bundle, the loader should enter SAFE_MODE.
"""

import json
import os
import tempfile
import shutil
import pytest
from pathlib import Path

from engine.ise.compiler import compile_bundle
from engine.loader.load_bundle import load_bundle
from engine.core.runtime_state import runtime_state
from engine.core.errors import BUNDLE_CONTRACT_MISSING


# Minimal valid IDL for finance-pilot MVP
MINIMAL_IDL = json.dumps({
    "idl_version": "1.0",
    "system_name": "Test System",
    "version": "1.0.0",
    "actors": [
        {
            "name": "Employee",
            "permissions": [
                {"resource": "expense", "actions": ["create"]}
            ]
        },
        {
            "name": "Manager",
            "permissions": [
                {"resource": "expense", "actions": ["read", "approve"]}
            ]
        }
    ],
    "entities": [
        {
            "name": "expense",
            "fields": [
                {"name": "amount", "type": "decimal"},
                {"name": "description", "type": "string"}
            ]
        }
    ],
    "usecases": [
        {
            "name": "create_expense",
            "actor": "Employee",
            "steps": ["Submit expense for approval"]
        }
    ]
})


class TestMissingInstitutionalContractsSafeMode:
    """Test that missing institutional contracts trigger SAFE_MODE."""

    def setup_method(self):
        """Clear safe mode before each test."""
        runtime_state.set_active()

    def teardown_method(self):
        """Clear safe mode after each test."""
        runtime_state.set_active()

    def _create_bundle_and_remove_contract(self, tmpdir: str, contract_to_remove: str) -> Path:
        """Helper to create a bundle and remove a specific contract.

        Args:
            tmpdir: Temporary directory for bundle.
            contract_to_remove: Name of contract file to delete.

        Returns:
            Path to the bundle directory.
        """
        result = compile_bundle(
            idl=MINIMAL_IDL,
            bundle_name="test-bundle",
            output_dir=tmpdir,
            validate_finance_pilot=True,
        )

        assert result.success, f"Compilation failed: {result.error_message}"

        bundle_path = Path(tmpdir) / "test-bundle"

        # Verify contract exists before removing
        contract_path = bundle_path / contract_to_remove
        assert contract_path.exists(), f"{contract_to_remove} should exist before removal"

        # Remove the contract
        contract_path.unlink()

        # Verify it's gone
        assert not contract_path.exists(), f"{contract_to_remove} should be removed"

        return bundle_path

    def test_missing_policies_json_triggers_safe_mode(self):
        """Test that missing policies.json causes SAFE_MODE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = self._create_bundle_and_remove_contract(tmpdir, "policies.json")

            os.environ["ENGINE_BUNDLE_PATH"] = str(bundle_path)

            try:
                load_bundle()

                assert runtime_state.is_safe_mode(), "Should be in SAFE_MODE when policies.json is missing"

                assert runtime_state.reason_code == BUNDLE_CONTRACT_MISSING, \
                    f"Reason code should be BUNDLE_CONTRACT_MISSING, got: {runtime_state.reason_code}"
            finally:
                os.environ.pop("ENGINE_BUNDLE_PATH", None)

    def test_missing_mandates_json_triggers_safe_mode(self):
        """Test that missing mandates.json causes SAFE_MODE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = self._create_bundle_and_remove_contract(tmpdir, "mandates.json")

            os.environ["ENGINE_BUNDLE_PATH"] = str(bundle_path)

            try:
                load_bundle()

                assert runtime_state.is_safe_mode(), "Should be in SAFE_MODE when mandates.json is missing"

                assert runtime_state.reason_code == BUNDLE_CONTRACT_MISSING, \
                    f"Reason code should be BUNDLE_CONTRACT_MISSING, got: {runtime_state.reason_code}"
            finally:
                os.environ.pop("ENGINE_BUNDLE_PATH", None)

    def test_missing_autonomy_json_triggers_safe_mode(self):
        """Test that missing autonomy.json causes SAFE_MODE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = self._create_bundle_and_remove_contract(tmpdir, "autonomy.json")

            os.environ["ENGINE_BUNDLE_PATH"] = str(bundle_path)

            try:
                load_bundle()

                assert runtime_state.is_safe_mode(), "Should be in SAFE_MODE when autonomy.json is missing"

                assert runtime_state.reason_code == BUNDLE_CONTRACT_MISSING, \
                    f"Reason code should be BUNDLE_CONTRACT_MISSING, got: {runtime_state.reason_code}"
            finally:
                os.environ.pop("ENGINE_BUNDLE_PATH", None)

    def test_complete_bundle_does_not_trigger_safe_mode(self):
        """Test that a complete bundle (with all contracts) loads without SAFE_MODE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_bundle(
                idl=MINIMAL_IDL,
                bundle_name="test-bundle",
                output_dir=tmpdir,
                validate_finance_pilot=True,
            )

            assert result.success

            bundle_path = Path(tmpdir) / "test-bundle"
            os.environ["ENGINE_BUNDLE_PATH"] = str(bundle_path)

            try:
                load_bundle()

                assert not runtime_state.is_safe_mode(), \
                    f"Should NOT be in SAFE_MODE for complete bundle: {runtime_state.reason_code}"
            finally:
                os.environ.pop("ENGINE_BUNDLE_PATH", None)

    def test_missing_rbac_json_triggers_safe_mode(self):
        """Test that missing rbac.json (also required) causes SAFE_MODE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = self._create_bundle_and_remove_contract(tmpdir, "rbac.json")

            os.environ["ENGINE_BUNDLE_PATH"] = str(bundle_path)

            try:
                load_bundle()

                assert runtime_state.is_safe_mode(), "Should be in SAFE_MODE when rbac.json is missing"
            finally:
                os.environ.pop("ENGINE_BUNDLE_PATH", None)


class TestManifestRequiredFlag:
    """Test that manifest correctly marks contracts as required."""

    def setup_method(self):
        """Clear safe mode before each test."""
        runtime_state.set_active()

    def teardown_method(self):
        """Clear safe mode after each test."""
        runtime_state.set_active()

    def test_institutional_contracts_have_required_true(self):
        """Test that all three institutional contracts are marked required=true."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_bundle(
                idl=MINIMAL_IDL,
                bundle_name="test-bundle",
                output_dir=tmpdir,
                validate_finance_pilot=True,
            )

            assert result.success

            manifest_path = Path(tmpdir) / "test-bundle" / "bundle.manifest.json"
            with open(manifest_path) as f:
                manifest = json.load(f)

            institutional = {"policies.json", "mandates.json", "autonomy.json"}
            found = set()

            for contract in manifest["contracts"]:
                if contract["file"] in institutional:
                    found.add(contract["file"])
                    assert contract["required"] is True, \
                        f"{contract['file']} must have required=true"

            assert found == institutional, \
                f"All institutional contracts should be in manifest, missing: {institutional - found}"

    def test_openapi_yaml_not_required(self):
        """Test that openapi.yaml is marked as optional (required=false)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = compile_bundle(
                idl=MINIMAL_IDL,
                bundle_name="test-bundle",
                output_dir=tmpdir,
                validate_finance_pilot=True,
            )

            assert result.success

            manifest_path = Path(tmpdir) / "test-bundle" / "bundle.manifest.json"
            with open(manifest_path) as f:
                manifest = json.load(f)

            for contract in manifest["contracts"]:
                if contract["file"] == "openapi.yaml":
                    assert contract["required"] is False, \
                        "openapi.yaml should be marked as optional (required=false)"
                    return

            # openapi.yaml should be in manifest
            pytest.fail("openapi.yaml should be in manifest")
