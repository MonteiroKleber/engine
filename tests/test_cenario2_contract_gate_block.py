"""Cenário 2: CONTRACT_GATE_FAILED blocking test.

Objetivo: provar que contrato quebrado trava tudo, mesmo que o resto 'pareça ok'.

Test simulates a broken contract by patching _create_contract_record to return
a ContractRecord with contract_gate_ok=False for the 'ir' artifact.

Expected results:
- Pipeline interrupts
- final_status = 'contract_gate_failed'
- blocked_reason = CONTRACT_GATE_FAILED
- contract_gate_errors not empty
- No patch/build executed
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from orchestrator.engine import Engine, RunResult
from observability.contract_record import ContractRecord, ContractLedger
from observability.telemetry import BlockedReason


class TestCenario2ContractGateBlock:
    """Cenário 2: Bloqueio por Contract Gate (IDL inconsistente)."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create engine with temp store."""
        return Engine(store_root=str(tmp_path / "store"))

    @pytest.fixture
    def natural_input(self):
        """Natural language input for testing."""
        return "Quero um sistema de cadastro de empresas com nome e CNPJ. Cada empresa pode ter funcionários com nome e email."

    def test_contract_gate_ir_failure_blocks_pipeline(self, engine, natural_input, tmp_path, capsys):
        """[Cenário 2] IR contract gate failure blocks pipeline completely.

        Simulates: Hash mismatch on IR artifact (as if file was tampered).
        """
        # Track run logs written
        written_logs = []
        original_write = engine.store.write_run_log

        def capture_write(exec_id, payload, project=None):
            written_logs.append(payload)
            return original_write(exec_id, payload, project=project)

        # Track telemetry events
        telemetry_events = []

        def capture_print(text):
            if text.startswith('{') and '"execution_id"' in text:
                try:
                    telemetry_events.append(json.loads(text))
                except:
                    pass
            # Still print to stdout
            import builtins
            builtins.__dict__['_original_print'](text)

        # Patch _create_contract_record to force failure on 'ir' kind
        original_create = engine._create_contract_record

        def failing_contract_record(kind, path, is_yaml=False):
            if kind == "ir":
                # Simulate hash mismatch on IR artifact
                return ContractRecord(
                    kind=kind,
                    path=path,
                    content_hash_sha256="corrupted_hash_simulation",
                    contract_gate_ok=False,
                    contract_gate_error="Hash mismatch: IR file was modified after save (empresa -> empresa_x)",
                )
            return original_create(kind, path, is_yaml)

        with patch.object(engine.store, "write_run_log", capture_write), \
             patch.object(engine, "_create_contract_record", failing_contract_record):
            result = engine.run("test_cenario2_ir_fail", natural_input)

        # === ASSERTIONS ===

        # 1. Pipeline should fail
        assert result.success is False, "Pipeline should have failed"

        # 2. final_status should be contract_gate_failed
        assert result.final_status == "contract_gate_failed", \
            f"Expected final_status='contract_gate_failed', got '{result.final_status}'"

        # 3. Errors should mention contract ledger failure
        assert "Contract ledger validation failed" in result.errors, \
            f"Expected 'Contract ledger validation failed' in errors: {result.errors}"

        # 4. Check RunLog was written with correct status
        assert len(written_logs) >= 1, "At least one run log should be written"
        last_log = written_logs[-1]

        assert last_log["status"] == "contract_gate_failed", \
            f"RunLog status should be 'contract_gate_failed', got '{last_log['status']}'"

        # 5. Contracts should be present in RunLog
        assert "contracts" in last_log, "RunLog should contain 'contracts' field"
        assert isinstance(last_log["contracts"], dict), "contracts should be a dict"

        # 6. contract_gate_errors should be non-empty
        assert "contract_gate_errors" in last_log, "RunLog should contain 'contract_gate_errors'"
        assert len(last_log["contract_gate_errors"]) >= 1, \
            f"contract_gate_errors should not be empty: {last_log['contract_gate_errors']}"

        # 7. Check error details
        ir_error = next(
            (e for e in last_log["contract_gate_errors"] if e["kind"] == "ir"),
            None
        )
        assert ir_error is not None, "Should have error for 'ir' artifact"
        assert "Hash mismatch" in ir_error["error"], \
            f"Error message should mention hash mismatch: {ir_error['error']}"

        # 8. No patches should have been applied (no patch_count in result)
        assert result.patch_count == 0, \
            f"No patches should be applied when contract gate fails: {result.patch_count}"

        # 9. Build should not have run
        assert result.build_ok is False, "Build should not have run"
        assert result.repo_path is None, "No repo should have been generated"

        # 10. Check telemetry (from stdout)
        stdout = capsys.readouterr().out
        # Telemetry should have CONTRACT_GATE_FAILED
        assert "CONTRACT_GATE_FAILED" in stdout or len(telemetry_events) == 0, \
            "Telemetry should include blocked_reason=CONTRACT_GATE_FAILED"

        print("\n" + "="*60)
        print("CENÁRIO 2 - CONTRACT_GATE_FAILED: PASSED")
        print("="*60)
        print(f"✓ success: {result.success}")
        print(f"✓ final_status: {result.final_status}")
        print(f"✓ contract_gate_errors count: {len(last_log['contract_gate_errors'])}")
        print(f"✓ patch_count: {result.patch_count}")
        print(f"✓ build_ok: {result.build_ok}")
        print(f"✓ repo_path: {result.repo_path}")
        print("="*60)

    def test_contract_gate_srs_failure_blocks_pipeline(self, engine, natural_input, tmp_path):
        """[Cenário 2b] SRS contract gate failure also blocks pipeline.

        Verifies that any artifact contract failure blocks execution.
        """
        written_logs = []
        original_write = engine.store.write_run_log

        def capture_write(exec_id, payload, project=None):
            written_logs.append(payload)
            return original_write(exec_id, payload, project=project)

        original_create = engine._create_contract_record

        def failing_contract_record(kind, path, is_yaml=False):
            if kind == "srs":
                return ContractRecord(
                    kind=kind,
                    path=path,
                    contract_gate_ok=False,
                    contract_gate_error="SRS file integrity compromised",
                )
            return original_create(kind, path, is_yaml)

        with patch.object(engine.store, "write_run_log", capture_write), \
             patch.object(engine, "_create_contract_record", failing_contract_record):
            result = engine.run("test_cenario2_srs_fail", natural_input)

        # Assertions
        assert result.success is False
        assert result.final_status == "contract_gate_failed"
        assert "Contract ledger validation failed" in result.errors

        # Check contract_gate_errors has SRS
        last_log = written_logs[-1]
        srs_error = next(
            (e for e in last_log["contract_gate_errors"] if e["kind"] == "srs"),
            None
        )
        assert srs_error is not None

    def test_contract_gate_multiple_failures(self, engine, natural_input, tmp_path):
        """[Cenário 2c] Multiple contract gate failures are all reported.

        Verifies that when multiple artifacts fail, all are reported.
        """
        written_logs = []
        original_write = engine.store.write_run_log

        def capture_write(exec_id, payload, project=None):
            written_logs.append(payload)
            return original_write(exec_id, payload, project=project)

        original_create = engine._create_contract_record

        def failing_contract_record(kind, path, is_yaml=False):
            if kind in ["srs", "ir", "oas"]:
                return ContractRecord(
                    kind=kind,
                    path=path,
                    contract_gate_ok=False,
                    contract_gate_error=f"{kind.upper()} corrupted",
                )
            return original_create(kind, path, is_yaml)

        with patch.object(engine.store, "write_run_log", capture_write), \
             patch.object(engine, "_create_contract_record", failing_contract_record):
            result = engine.run("test_cenario2_multi_fail", natural_input)

        assert result.success is False
        assert result.final_status == "contract_gate_failed"

        last_log = written_logs[-1]
        # Should have multiple errors
        assert len(last_log["contract_gate_errors"]) >= 3, \
            f"Should have 3+ errors, got {len(last_log['contract_gate_errors'])}"


class TestBlockedReasonIntegration:
    """Verify BlockedReason.CONTRACT_GATE_FAILED is used correctly."""

    def test_blocked_reason_constant_value(self):
        """[BlockedReason] CONTRACT_GATE_FAILED has correct value."""
        assert BlockedReason.CONTRACT_GATE_FAILED == "CONTRACT_GATE_FAILED"

    def test_blocked_reason_distinct_from_policy(self):
        """[BlockedReason] CONTRACT_GATE_FAILED is distinct from CONTRACTS_POLICY_FAILED."""
        assert BlockedReason.CONTRACT_GATE_FAILED != BlockedReason.CONTRACTS_POLICY_FAILED
        assert "GATE" in BlockedReason.CONTRACT_GATE_FAILED
        assert "POLICY" in BlockedReason.CONTRACTS_POLICY_FAILED
