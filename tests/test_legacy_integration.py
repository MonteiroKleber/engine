"""Test LEGACY integration with Engine.

Validates:
1) legacy dict ALWAYS present in RunLog (even without legacy_bundle)
2) legacy happy path with valid artifacts
3) legacy contract gate failure blocks pipeline
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from orchestrator.engine import Engine
from observability.legacy_gate import compute_content_hash_sha256
from observability.telemetry import BlockedReason


class TestLegacyFieldsAlwaysPresent:
    """Test legacy dict is always present in RunLog."""

    def test_legacy_fields_always_present_on_success(self):
        """[Legacy] legacy dict present even without legacy_bundle."""
        with tempfile.TemporaryDirectory() as tmp_store:
            engine = Engine(store_root=tmp_store)

            written_logs = []
            original_write = engine.store.write_run_log

            def capture_write(exec_id, payload, project=None):
                written_logs.append(payload)
                return original_write(exec_id, payload, project=project)

            engine.store.write_run_log = capture_write

            input_text = """Sistema de cadastro de empresas.

Entidade empresa (id, nome, cnpj).
Entidade usuario (id, nome, email).

Caso de uso: usuario cria empresa.
Caso de uso: usuario lista empresas.
"""
            result = engine.run("test_legacy_always_present", input_text)

            assert result.success is True

            assert len(written_logs) >= 1
            last_log = written_logs[-1]

            # legacy dict ALWAYS present
            assert "legacy" in last_log, "RunLog should ALWAYS include 'legacy'"
            assert isinstance(last_log["legacy"], dict)

            # All required keys present
            legacy = last_log["legacy"]
            assert "provided" in legacy
            assert legacy["provided"] is False  # No legacy_bundle provided
            assert "inventory_path" in legacy
            assert legacy["inventory_path"] is None
            assert "human_process_path" in legacy
            assert legacy["human_process_path"] is None
            assert "legacy_runlog_path" in legacy
            assert legacy["legacy_runlog_path"] is None
            assert "legacy_schema_ok" in legacy
            assert legacy["legacy_schema_ok"] is None
            assert "legacy_contract_gate_ok" in legacy
            assert legacy["legacy_contract_gate_ok"] is None
            assert "legacy_contract_gate_errors" in legacy
            assert legacy["legacy_contract_gate_errors"] == []
            assert "legacy_hashes" in legacy
            assert legacy["legacy_hashes"] == {}


class TestLegacyHappyPath:
    """Test legacy happy path with valid artifacts."""

    def _create_valid_inventory(self, path: Path) -> None:
        """Create a valid legacy inventory artifact."""
        inventory = {
            "schema_version": "legacy_inventory.v1",
            "content_hash_sha256": "",
            "source": "SAP",
            "extracted_at": "2025-01-01T00:00:00Z",
            "confidence_level": "high",
            "systems": [{"name": "ERP", "description": "Main ERP", "technology": "Java"}],
        }
        inventory["content_hash_sha256"] = compute_content_hash_sha256(inventory)
        with open(path, "w") as f:
            json.dump(inventory, f)

    def _create_valid_human_process(self, path: Path) -> None:
        """Create a valid human process artifact."""
        process = {
            "schema_version": "human_process.v1",
            "content_hash_sha256": "",
            "process_name": "Finance Approval",
            "actors": ["finance-team"],
            "steps": [{"order": 1, "description": "Review request", "actor": "finance-team"}],
            "approvals": [],
            "assumptions": ["All requests are valid"],
            "extracted_at": "2025-01-01T00:00:00Z",
        }
        process["content_hash_sha256"] = compute_content_hash_sha256(process)
        with open(path, "w") as f:
            json.dump(process, f)

    def test_legacy_happy_path_gate_ok(self):
        """[Legacy] Valid legacy artifacts pass gate."""
        with tempfile.TemporaryDirectory() as tmp_store:
            with tempfile.TemporaryDirectory() as tmp_legacy:
                engine = Engine(store_root=tmp_store)

                # Create valid legacy artifacts
                inventory_path = Path(tmp_legacy) / "inventory.json"
                human_path = Path(tmp_legacy) / "human_process.json"
                self._create_valid_inventory(inventory_path)
                self._create_valid_human_process(human_path)

                written_logs = []
                original_write = engine.store.write_run_log

                def capture_write(exec_id, payload, project=None):
                    written_logs.append(payload)
                    return original_write(exec_id, payload, project=project)

                engine.store.write_run_log = capture_write

                input_text = """Sistema de cadastro de empresas.

Entidade empresa (id, nome, cnpj).
Entidade usuario (id, nome, email).

Caso de uso: usuario cria empresa.
Caso de uso: usuario lista empresas.
"""
                legacy_bundle = {
                    "inventory_path": str(inventory_path),
                    "human_process_path": str(human_path),
                }

                result = engine.run("test_legacy_ok", input_text, legacy_bundle=legacy_bundle)

                # Should succeed
                assert result.success is True
                assert result.final_status == "success"

                assert len(written_logs) >= 1
                last_log = written_logs[-1]

                # legacy dict present with valid values
                legacy = last_log["legacy"]
                assert legacy["provided"] is True
                assert legacy["inventory_path"] == str(inventory_path)
                assert legacy["human_process_path"] == str(human_path)
                assert legacy["legacy_schema_ok"] is True
                assert legacy["legacy_contract_gate_ok"] is True
                assert legacy["legacy_contract_gate_errors"] == []
                assert "inventory" in legacy["legacy_hashes"]
                assert "human_process" in legacy["legacy_hashes"]


class TestLegacyContractGateFailed:
    """Test legacy contract gate failure blocks pipeline."""

    def _create_valid_inventory(self, path: Path) -> None:
        """Create a valid legacy inventory artifact."""
        inventory = {
            "schema_version": "legacy_inventory.v1",
            "content_hash_sha256": "",
            "source": "SAP",
            "extracted_at": "2025-01-01T00:00:00Z",
            "confidence_level": "high",
            "systems": [{"name": "ERP"}],
        }
        inventory["content_hash_sha256"] = compute_content_hash_sha256(inventory)
        with open(path, "w") as f:
            json.dump(inventory, f)

    def _create_corrupted_human_process(self, path: Path) -> None:
        """Create a human process artifact with corrupted hash."""
        process = {
            "schema_version": "human_process.v1",
            "content_hash_sha256": "",
            "process_name": "Finance Approval",
            "actors": ["finance-team"],
            "steps": [{"order": 1, "description": "Review request", "actor": "finance-team"}],
            "approvals": [],
            "assumptions": ["All requests are valid"],
            "extracted_at": "2025-01-01T00:00:00Z",
        }
        # Compute hash first
        process["content_hash_sha256"] = compute_content_hash_sha256(process)
        # Then corrupt the content without updating hash
        process["process_name"] = "CORRUPTED"
        with open(path, "w") as f:
            json.dump(process, f)

    def test_legacy_contract_gate_failed_blocks(self):
        """[Legacy] Corrupted legacy artifact blocks pipeline."""
        with tempfile.TemporaryDirectory() as tmp_store:
            with tempfile.TemporaryDirectory() as tmp_legacy:
                engine = Engine(store_root=tmp_store)

                # Create one valid and one corrupted artifact
                inventory_path = Path(tmp_legacy) / "inventory.json"
                human_path = Path(tmp_legacy) / "human_process.json"
                self._create_valid_inventory(inventory_path)
                self._create_corrupted_human_process(human_path)

                written_logs = []
                original_write = engine.store.write_run_log

                def capture_write(exec_id, payload, project=None):
                    written_logs.append(payload)
                    return original_write(exec_id, payload, project=project)

                engine.store.write_run_log = capture_write

                input_text = """Sistema de cadastro de empresas.

Entidade empresa (id, nome, cnpj).

Caso de uso: criar empresa.
"""
                legacy_bundle = {
                    "inventory_path": str(inventory_path),
                    "human_process_path": str(human_path),
                }

                result = engine.run("test_legacy_fail", input_text, legacy_bundle=legacy_bundle)

                # Should fail
                assert result.success is False
                assert result.final_status == "legacy_contract_gate_failed"

                assert len(written_logs) >= 1
                last_log = written_logs[-1]

                # blocked_reason should be LEGACY_CONTRACT_GATE_FAILED
                assert last_log["blocked_reason"] == BlockedReason.LEGACY_CONTRACT_GATE_FAILED

                # legacy dict present with failure info
                legacy = last_log["legacy"]
                assert legacy["provided"] is True
                assert legacy["legacy_contract_gate_ok"] is False
                assert len(legacy["legacy_contract_gate_errors"]) > 0
                assert "Hash mismatch" in legacy["legacy_contract_gate_errors"][0]

                # Pipeline should not have progressed
                assert result.patch_count == 0
                assert result.build_ok is False
                assert result.srs_validation_ok is False  # Didn't even get to SRS
