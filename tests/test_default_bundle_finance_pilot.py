"""Tests for the default finance-pilot bundle.

Per MVP decision (2026-01-17): policies.json, mandates.json, autonomy.json are mandatory.
The default bundle bundles/finance-pilot must include these contracts to load without SAFE_MODE.
"""

import json
import os
import shutil
import tempfile
import pytest
from pathlib import Path

from engine.loader.load_bundle import load_bundle
from engine.core.runtime_state import runtime_state
from engine.core.errors import BUNDLE_CONTRACT_MISSING


# Path to the default finance-pilot bundle
DEFAULT_BUNDLE_PATH = Path(__file__).parent.parent / "bundles" / "finance-pilot"


class TestDefaultBundleLoadsWithoutSafeMode:
    """Test that the default finance-pilot bundle loads without SAFE_MODE."""

    def setup_method(self):
        """Clear safe mode before each test."""
        runtime_state.set_active()

    def teardown_method(self):
        """Clear safe mode after each test."""
        runtime_state.set_active()

    def test_default_bundle_exists(self):
        """Verify the default bundle directory exists."""
        assert DEFAULT_BUNDLE_PATH.exists(), \
            f"Default bundle not found at {DEFAULT_BUNDLE_PATH}"
        assert DEFAULT_BUNDLE_PATH.is_dir(), \
            f"Default bundle path is not a directory: {DEFAULT_BUNDLE_PATH}"

    def test_default_bundle_has_manifest(self):
        """Verify the default bundle has a manifest."""
        manifest_path = DEFAULT_BUNDLE_PATH / "bundle.manifest.json"
        assert manifest_path.exists(), "bundle.manifest.json not found"

    def test_default_bundle_has_institutional_contracts(self):
        """Verify the default bundle has all three institutional contracts."""
        policies_path = DEFAULT_BUNDLE_PATH / "policies.json"
        mandates_path = DEFAULT_BUNDLE_PATH / "mandates.json"
        autonomy_path = DEFAULT_BUNDLE_PATH / "autonomy.json"

        assert policies_path.exists(), "policies.json not found in default bundle"
        assert mandates_path.exists(), "mandates.json not found in default bundle"
        assert autonomy_path.exists(), "autonomy.json not found in default bundle"

    def test_policies_json_schema_valid(self):
        """Verify policies.json has valid schema."""
        with open(DEFAULT_BUNDLE_PATH / "policies.json") as f:
            policies = json.load(f)

        assert "policy_schema_version" in policies, "Missing policy_schema_version"
        assert policies["policy_schema_version"] == "1.1", "Expected schema version 1.1"
        assert "policies" in policies, "Missing policies array"
        assert isinstance(policies["policies"], list), "policies must be an array"

    def test_mandates_json_schema_valid(self):
        """Verify mandates.json has valid schema with pilot mandates."""
        with open(DEFAULT_BUNDLE_PATH / "mandates.json") as f:
            mandates = json.load(f)

        assert "mandate_schema_version" in mandates, "Missing mandate_schema_version"
        assert mandates["mandate_schema_version"] == "1.0", "Expected schema version 1.0"
        assert "mandates" in mandates, "Missing mandates array"
        assert isinstance(mandates["mandates"], list), "mandates must be an array"

        # Per canonical semantics, mandates must have rules covering pilot endpoints
        # Otherwise operations will be denied with MANDATE_DENIED
        assert len(mandates["mandates"]) >= 2, \
            "Default bundle must have mandates for pilot (expense create + approval decide)"

        # Verify expense creation mandate exists
        expense_mandate = next(
            (m for m in mandates["mandates"]
             if m.get("endpoint_sig") == "POST /finance/expenses" and m.get("phase") == "pre"),
            None
        )
        assert expense_mandate is not None, \
            "Must have mandate for POST /finance/expenses phase=pre"

        # Verify approval decision mandate exists
        approval_mandate = next(
            (m for m in mandates["mandates"]
             if m.get("endpoint_sig") == "POST /approvals/{approval_id}/decide" and m.get("phase") == "post"),
            None
        )
        assert approval_mandate is not None, \
            "Must have mandate for POST /approvals/{approval_id}/decide phase=post"

    def test_autonomy_json_schema_valid(self):
        """Verify autonomy.json has valid schema with pilot rules."""
        with open(DEFAULT_BUNDLE_PATH / "autonomy.json") as f:
            autonomy = json.load(f)

        assert "autonomy_schema_version" in autonomy, "Missing autonomy_schema_version"
        assert autonomy["autonomy_schema_version"] == "1.0", "Expected schema version 1.0"
        assert "current_level" in autonomy, "Missing current_level"
        assert autonomy["current_level"] == 0, "Expected current_level 0 (L0 = full human oversight)"
        assert "rules" in autonomy, "Missing rules array"
        assert isinstance(autonomy["rules"], list), "rules must be an array"

        # Per canonical semantics, autonomy must have rules covering pilot endpoints
        # Otherwise operations will be denied with AUTONOMY_INSUFFICIENT
        assert len(autonomy["rules"]) >= 2, \
            "Default bundle must have autonomy rules for pilot (expense create + approval decide)"

        # Verify expense creation rule exists
        expense_rule = next(
            (r for r in autonomy["rules"]
             if r.get("endpoint_sig") == "POST /finance/expenses" and r.get("phase") == "pre"),
            None
        )
        assert expense_rule is not None, \
            "Must have autonomy rule for POST /finance/expenses phase=pre"

        # Verify approval decision rule exists
        approval_rule = next(
            (r for r in autonomy["rules"]
             if r.get("endpoint_sig") == "POST /approvals/{approval_id}/decide" and r.get("phase") == "post"),
            None
        )
        assert approval_rule is not None, \
            "Must have autonomy rule for POST /approvals/{approval_id}/decide phase=post"

    def test_manifest_marks_institutional_contracts_required(self):
        """Verify manifest marks all institutional contracts as required=true."""
        with open(DEFAULT_BUNDLE_PATH / "bundle.manifest.json") as f:
            manifest = json.load(f)

        institutional = {"policies.json", "mandates.json", "autonomy.json"}
        found = set()

        for contract in manifest["contracts"]:
            if contract["file"] in institutional:
                found.add(contract["file"])
                assert contract["required"] is True, \
                    f"{contract['file']} must be marked required=true"

        assert found == institutional, \
            f"All institutional contracts should be in manifest, missing: {institutional - found}"

    def test_default_bundle_loads_active(self):
        """Test that loading the default bundle does NOT trigger SAFE_MODE."""
        os.environ["ENGINE_BUNDLE_PATH"] = str(DEFAULT_BUNDLE_PATH)

        try:
            load_bundle()

            assert not runtime_state.is_safe_mode(), \
                f"Default bundle should load ACTIVE, got SAFE_MODE: {runtime_state.reason_code}"
        finally:
            os.environ.pop("ENGINE_BUNDLE_PATH", None)


class TestDefaultBundleMissingContractsTriggerSafeMode:
    """Test that removing institutional contracts from default bundle triggers SAFE_MODE."""

    def setup_method(self):
        """Clear safe mode before each test."""
        runtime_state.set_active()

    def teardown_method(self):
        """Clear safe mode after each test."""
        runtime_state.set_active()

    def _create_bundle_copy_without_contract(self, contract_to_remove: str) -> Path:
        """Create a temporary copy of the default bundle with one contract removed.

        Args:
            contract_to_remove: Name of contract file to remove.

        Returns:
            Path to the temporary bundle directory.
        """
        tmpdir = tempfile.mkdtemp()
        bundle_copy = Path(tmpdir) / "finance-pilot"
        shutil.copytree(DEFAULT_BUNDLE_PATH, bundle_copy)

        # Remove the contract file
        contract_path = bundle_copy / contract_to_remove
        if contract_path.exists():
            contract_path.unlink()

        return bundle_copy

    def test_missing_policies_json_triggers_safe_mode(self):
        """Removing policies.json from default bundle triggers SAFE_MODE."""
        bundle_copy = self._create_bundle_copy_without_contract("policies.json")

        os.environ["ENGINE_BUNDLE_PATH"] = str(bundle_copy)

        try:
            load_bundle()

            assert runtime_state.is_safe_mode(), \
                "Should be in SAFE_MODE when policies.json is missing"
            assert runtime_state.reason_code == BUNDLE_CONTRACT_MISSING, \
                f"Expected BUNDLE_CONTRACT_MISSING, got: {runtime_state.reason_code}"
        finally:
            os.environ.pop("ENGINE_BUNDLE_PATH", None)
            shutil.rmtree(bundle_copy.parent)

    def test_missing_mandates_json_triggers_safe_mode(self):
        """Removing mandates.json from default bundle triggers SAFE_MODE."""
        bundle_copy = self._create_bundle_copy_without_contract("mandates.json")

        os.environ["ENGINE_BUNDLE_PATH"] = str(bundle_copy)

        try:
            load_bundle()

            assert runtime_state.is_safe_mode(), \
                "Should be in SAFE_MODE when mandates.json is missing"
            assert runtime_state.reason_code == BUNDLE_CONTRACT_MISSING, \
                f"Expected BUNDLE_CONTRACT_MISSING, got: {runtime_state.reason_code}"
        finally:
            os.environ.pop("ENGINE_BUNDLE_PATH", None)
            shutil.rmtree(bundle_copy.parent)

    def test_missing_autonomy_json_triggers_safe_mode(self):
        """Removing autonomy.json from default bundle triggers SAFE_MODE."""
        bundle_copy = self._create_bundle_copy_without_contract("autonomy.json")

        os.environ["ENGINE_BUNDLE_PATH"] = str(bundle_copy)

        try:
            load_bundle()

            assert runtime_state.is_safe_mode(), \
                "Should be in SAFE_MODE when autonomy.json is missing"
            assert runtime_state.reason_code == BUNDLE_CONTRACT_MISSING, \
                f"Expected BUNDLE_CONTRACT_MISSING, got: {runtime_state.reason_code}"
        finally:
            os.environ.pop("ENGINE_BUNDLE_PATH", None)
            shutil.rmtree(bundle_copy.parent)


class TestDefaultBundleHashIntegrity:
    """Test that default bundle hashes are correct."""

    def test_policies_json_hash_matches_manifest(self):
        """Verify policies.json hash in manifest matches file content."""
        import hashlib

        with open(DEFAULT_BUNDLE_PATH / "policies.json", "rb") as f:
            content = f.read()
        computed_hash = hashlib.sha256(content).hexdigest()

        with open(DEFAULT_BUNDLE_PATH / "bundle.manifest.json") as f:
            manifest = json.load(f)

        policies_entry = next(
            c for c in manifest["contracts"] if c["file"] == "policies.json"
        )
        manifest_hash = policies_entry["sha256"].replace("SHA256:", "")

        assert computed_hash == manifest_hash, \
            f"Hash mismatch for policies.json: computed={computed_hash}, manifest={manifest_hash}"

    def test_mandates_json_hash_matches_manifest(self):
        """Verify mandates.json hash in manifest matches file content."""
        import hashlib

        with open(DEFAULT_BUNDLE_PATH / "mandates.json", "rb") as f:
            content = f.read()
        computed_hash = hashlib.sha256(content).hexdigest()

        with open(DEFAULT_BUNDLE_PATH / "bundle.manifest.json") as f:
            manifest = json.load(f)

        mandates_entry = next(
            c for c in manifest["contracts"] if c["file"] == "mandates.json"
        )
        manifest_hash = mandates_entry["sha256"].replace("SHA256:", "")

        assert computed_hash == manifest_hash, \
            f"Hash mismatch for mandates.json: computed={computed_hash}, manifest={manifest_hash}"

    def test_autonomy_json_hash_matches_manifest(self):
        """Verify autonomy.json hash in manifest matches file content."""
        import hashlib

        with open(DEFAULT_BUNDLE_PATH / "autonomy.json", "rb") as f:
            content = f.read()
        computed_hash = hashlib.sha256(content).hexdigest()

        with open(DEFAULT_BUNDLE_PATH / "bundle.manifest.json") as f:
            manifest = json.load(f)

        autonomy_entry = next(
            c for c in manifest["contracts"] if c["file"] == "autonomy.json"
        )
        manifest_hash = autonomy_entry["sha256"].replace("SHA256:", "")

        assert computed_hash == manifest_hash, \
            f"Hash mismatch for autonomy.json: computed={computed_hash}, manifest={manifest_hash}"
