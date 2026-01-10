"""E2E tests for Engine + Legacy Bundle integration.

These tests run real scenarios WITHOUT MOCKS, using subprocess to call legacy CLI.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from orchestrator.engine import Engine
from observability.legacy_gate import validate_legacy_bundle


def run_legacy_intake(output_dir: Path, project: str = "e2e_test") -> bool:
    """Run legacy intake CLI to generate bundle."""
    result = subprocess.run(
        [
            sys.executable, "-m", "legacy.cli",
            "intake",
            "--project", project,
            "--out", str(output_dir),
        ],
        capture_output=True,
        text=True,
        cwd="/home/bazari/legacy",
    )
    return result.returncode == 0


class TestE2EHappyPath:
    """Test Scenario 1: Happy Path - valid bundle, Engine succeeds."""

    def test_valid_bundle_engine_succeeds(self):
        """[e2e] Valid bundle -> Engine runs without blocking."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "bundle"

            # Generate bundle via legacy intake
            success = run_legacy_intake(bundle_dir)
            assert success, "Legacy intake failed"

            # Verify files exist
            assert (bundle_dir / "legacy_inventory.v1.json").exists()
            assert (bundle_dir / "human_process.v1.json").exists()
            assert (bundle_dir / "legacy_contracts.v1.json").exists()

            # Validate via legacy_gate
            result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
            assert result.provided is True
            assert result.ok is True

            # Run Engine
            engine = Engine()
            run_result = engine.run(
                project="e2e_happy_path",
                raw_input="Crie uma tabela de teste",
                legacy_bundle={"bundle_path": str(bundle_dir)},
            )

            # Legacy gate should NOT block (pipeline may fail later due to no LLM)
            assert run_result.final_status != "legacy_contract_gate_failed"


class TestE2ETamperDetection:
    """Test Scenario 2: Tamper - modify inventory without updating ledger."""

    def test_tampered_bundle_engine_blocks(self):
        """[e2e] Tampered bundle -> Engine blocks with LEGACY_CONTRACT_GATE_FAILED."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "bundle"

            # Generate valid bundle
            success = run_legacy_intake(bundle_dir)
            assert success, "Legacy intake failed"

            # Tamper with inventory (but DON'T update ledger)
            inventory_path = bundle_dir / "legacy_inventory.v1.json"
            with open(inventory_path) as f:
                inventory = json.load(f)

            # Change content and update hash in file
            inventory["source"] = "TAMPERED_SOURCE"

            # Import from legacy repo
            sys.path.insert(0, "/home/bazari/legacy")
            from legacy.hash_utils import compute_content_hash_sha256
            inventory["content_hash_sha256"] = compute_content_hash_sha256(inventory)

            with open(inventory_path, "w") as f:
                json.dump(inventory, f)

            # Validate - should fail due to ledger mismatch
            result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
            assert result.ok is False
            assert len(result.legacy_contract_gate_errors) > 0

            # Run Engine - should block
            engine = Engine()
            run_result = engine.run(
                project="e2e_tamper",
                raw_input="Crie uma tabela de teste",
                legacy_bundle={"bundle_path": str(bundle_dir)},
            )

            assert run_result.success is False
            assert run_result.final_status == "legacy_contract_gate_failed"


class TestE2ESchemaInvalid:
    """Test Scenario 3: Schema Invalid - corrupt schema_version."""

    def test_invalid_schema_engine_blocks(self):
        """[e2e] Invalid schema_version -> Engine blocks."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "bundle"

            # Generate valid bundle
            success = run_legacy_intake(bundle_dir)
            assert success, "Legacy intake failed"

            # Corrupt schema_version
            inventory_path = bundle_dir / "legacy_inventory.v1.json"
            with open(inventory_path) as f:
                inventory = json.load(f)

            inventory["schema_version"] = "INVALID_VERSION"

            with open(inventory_path, "w") as f:
                json.dump(inventory, f)

            # Validate - should fail
            result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
            assert result.ok is False
            assert result.legacy_schema_ok is False

            # Run Engine - should block with legacy_schema_invalid
            engine = Engine()
            run_result = engine.run(
                project="e2e_schema_invalid",
                raw_input="Crie uma tabela de teste",
                legacy_bundle={"bundle_path": str(bundle_dir)},
            )

            assert run_result.success is False
            assert run_result.final_status == "legacy_schema_invalid"
            assert result.schema_invalid is True


class TestBlockedReasonMapping:
    """Test blocked_reason mapping for legacy failures."""

    def test_legacy_schema_invalid_sets_correct_blocked_reason(self):
        """[blocked_reason] Schema invalid -> LEGACY_SCHEMA_INVALID."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "bundle"

            # Generate valid bundle
            success = run_legacy_intake(bundle_dir)
            assert success, "Legacy intake failed"

            # Corrupt schema_version
            inventory_path = bundle_dir / "legacy_inventory.v1.json"
            with open(inventory_path) as f:
                inventory = json.load(f)
            inventory["schema_version"] = "INVALID_VERSION"
            with open(inventory_path, "w") as f:
                json.dump(inventory, f)

            # Validate
            result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
            assert result.ok is False
            assert result.schema_invalid is True
            assert any("Schema version" in e for e in result.legacy_contract_gate_errors)

            # Run Engine
            engine = Engine()
            run_result = engine.run(
                project="test_schema_blocked_reason",
                raw_input="Crie uma tabela",
                legacy_bundle={"bundle_path": str(bundle_dir)},
            )

            assert run_result.success is False
            assert run_result.final_status == "legacy_schema_invalid"

    def test_legacy_tamper_keeps_contract_gate_failed_blocked_reason(self):
        """[blocked_reason] Tamper/integrity -> LEGACY_CONTRACT_GATE_FAILED."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "bundle"

            # Generate valid bundle
            success = run_legacy_intake(bundle_dir)
            assert success, "Legacy intake failed"

            # Tamper (change content, update file hash, but not ledger)
            inventory_path = bundle_dir / "legacy_inventory.v1.json"
            with open(inventory_path) as f:
                inventory = json.load(f)
            inventory["source"] = "TAMPERED"

            sys.path.insert(0, "/home/bazari/legacy")
            from legacy.hash_utils import compute_content_hash_sha256
            inventory["content_hash_sha256"] = compute_content_hash_sha256(inventory)

            with open(inventory_path, "w") as f:
                json.dump(inventory, f)

            # Validate
            result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
            assert result.ok is False
            assert result.schema_invalid is False  # Schema is OK, just tampered
            assert any("hash mismatch" in e.lower() for e in result.legacy_contract_gate_errors)

            # Run Engine
            engine = Engine()
            run_result = engine.run(
                project="test_tamper_blocked_reason",
                raw_input="Crie uma tabela",
                legacy_bundle={"bundle_path": str(bundle_dir)},
            )

            assert run_result.success is False
            assert run_result.final_status == "legacy_contract_gate_failed"


class TestErrorPrefixes:
    """Test error message prefixes for enterprise log triaging."""

    def test_legacy_schema_invalid_error_is_prefixed_schema(self):
        """[prefix] Schema invalid errors start with SCHEMA:."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "bundle"

            # Generate valid bundle
            success = run_legacy_intake(bundle_dir)
            assert success, "Legacy intake failed"

            # Corrupt schema_version
            inventory_path = bundle_dir / "legacy_inventory.v1.json"
            with open(inventory_path) as f:
                inventory = json.load(f)
            inventory["schema_version"] = "INVALID_VERSION"
            with open(inventory_path, "w") as f:
                json.dump(inventory, f)

            # Validate
            result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
            assert result.ok is False
            assert result.schema_invalid is True
            # At least one error starts with SCHEMA:
            assert any(e.startswith("SCHEMA: ") for e in result.legacy_contract_gate_errors)

    def test_legacy_tamper_error_is_prefixed_integrity(self):
        """[prefix] Tamper/integrity errors start with INTEGRITY:."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "bundle"

            # Generate valid bundle
            success = run_legacy_intake(bundle_dir)
            assert success, "Legacy intake failed"

            # Tamper (change content, update file hash, but not ledger)
            inventory_path = bundle_dir / "legacy_inventory.v1.json"
            with open(inventory_path) as f:
                inventory = json.load(f)
            inventory["source"] = "TAMPERED"

            sys.path.insert(0, "/home/bazari/legacy")
            from legacy.hash_utils import compute_content_hash_sha256
            inventory["content_hash_sha256"] = compute_content_hash_sha256(inventory)

            with open(inventory_path, "w") as f:
                json.dump(inventory, f)

            # Validate
            result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
            assert result.ok is False
            assert result.schema_invalid is False
            # At least one error starts with INTEGRITY:
            assert any(e.startswith("INTEGRITY: ") for e in result.legacy_contract_gate_errors)


class TestErrorCodes:
    """Test error_codes field for machine-readable error classification."""

    def test_schema_invalid_error_code_is_legacy_schema_invalid(self):
        """[error_code] Schema invalid -> LEGACY_SCHEMA_INVALID."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "bundle"

            # Generate valid bundle
            success = run_legacy_intake(bundle_dir)
            assert success, "Legacy intake failed"

            # Corrupt schema_version
            inventory_path = bundle_dir / "legacy_inventory.v1.json"
            with open(inventory_path) as f:
                inventory = json.load(f)
            inventory["schema_version"] = "INVALID_VERSION"
            with open(inventory_path, "w") as f:
                json.dump(inventory, f)

            # Validate
            result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
            assert result.ok is False
            # Verify 1:1 pairing
            assert len(result.error_codes) == len(result.legacy_contract_gate_errors)
            # First error should be SCHEMA prefixed and have correct code
            assert result.legacy_contract_gate_errors[0].startswith("SCHEMA: ")
            assert result.error_codes[0] == "LEGACY_SCHEMA_INVALID"

    def test_tamper_error_code_is_legacy_integrity_failed(self):
        """[error_code] Tamper/integrity -> LEGACY_INTEGRITY_FAILED."""
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "bundle"

            # Generate valid bundle
            success = run_legacy_intake(bundle_dir)
            assert success, "Legacy intake failed"

            # Tamper (change content, update file hash, but not ledger)
            inventory_path = bundle_dir / "legacy_inventory.v1.json"
            with open(inventory_path) as f:
                inventory = json.load(f)
            inventory["source"] = "TAMPERED"

            sys.path.insert(0, "/home/bazari/legacy")
            from legacy.hash_utils import compute_content_hash_sha256
            inventory["content_hash_sha256"] = compute_content_hash_sha256(inventory)

            with open(inventory_path, "w") as f:
                json.dump(inventory, f)

            # Validate
            result = validate_legacy_bundle({"bundle_path": str(bundle_dir)})
            assert result.ok is False
            # Verify 1:1 pairing
            assert len(result.error_codes) == len(result.legacy_contract_gate_errors)
            # First error should be INTEGRITY prefixed and have correct code
            assert result.legacy_contract_gate_errors[0].startswith("INTEGRITY: ")
            assert result.error_codes[0] == "LEGACY_INTEGRITY_FAILED"
