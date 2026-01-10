"""Tests for RunLog consistency and Contract Gate blocking.

Polish tests for:
1) ContractLedger failure blocks run() correctly
2) RunLog always includes contracts and patch_manifest_path
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from orchestrator.engine import Engine, RunResult
from observability.contract_record import ContractRecord, ContractLedger
from observability.telemetry import BlockedReason


class TestContractGateBlocksRun:
    """Test that ContractLedger failure blocks run() correctly."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create engine with temp store."""
        return Engine(store_root=str(tmp_path / "store"))

    @pytest.fixture
    def minimal_input(self):
        """Minimal valid input for pipeline."""
        return "Quero um sistema de cadastro de clientes com nome e email."

    def test_contract_gate_failure_blocks_pipeline(self, engine, minimal_input, tmp_path):
        """[ContractGate] When contract_gate_ok=False, pipeline is blocked."""
        # Track run logs written
        written_logs = []
        original_write = engine.store.write_run_log

        def capture_write(exec_id, payload, project=None):
            written_logs.append(payload)
            return original_write(exec_id, payload, project=project)

        # Patch _create_contract_record to force failure on 'srs' kind
        original_create = engine._create_contract_record

        def failing_contract_record(kind, path, is_yaml=False):
            if kind == "srs":
                return ContractRecord(
                    kind=kind,
                    path=path,
                    contract_gate_ok=False,
                    contract_gate_error="Simulated hash mismatch",
                )
            return original_create(kind, path, is_yaml)

        with patch.object(engine.store, "write_run_log", capture_write), \
             patch.object(engine, "_create_contract_record", failing_contract_record):
            result = engine.run("test_gate_fail", minimal_input)

        # Assertions
        assert result.success is False
        assert result.final_status == "contract_gate_failed"
        assert "Contract ledger validation failed" in result.errors

        # Check RunLog
        assert len(written_logs) >= 1
        last_log = written_logs[-1]

        assert last_log["final_status"] == "contract_gate_failed"
        assert "contracts" in last_log
        assert "contract_gate_errors" in last_log
        assert len(last_log["contract_gate_errors"]) >= 1

        # Check error details
        srs_error = next(
            (e for e in last_log["contract_gate_errors"] if e["kind"] == "srs"),
            None
        )
        assert srs_error is not None
        assert srs_error["error"] == "Simulated hash mismatch"


class TestRunLogConsistency:
    """Test that RunLog always includes contracts and patch_manifest_path."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create engine with temp store."""
        return Engine(store_root=str(tmp_path / "store"))

    def test_runlog_has_contracts_on_srs_blocked(self, engine, tmp_path):
        """[RunLog] Early return (SRS blocked) still has contracts field."""
        written_logs = []
        original_write = engine.store.write_run_log

        def capture_write(exec_id, payload, project=None):
            written_logs.append(payload)
            return original_write(exec_id, payload, project=project)

        # Force SRS validation to fail
        with patch.object(engine.store, "write_run_log", capture_write), \
             patch.object(engine.srs_validator_gate, "process") as mock_validate:
            mock_validate.return_value = (False, None, ["Question 1?"])
            result = engine.run("test_srs_blocked", "input text")

        assert result.success is False
        assert result.srs_validation_ok is False

        # Check RunLog
        assert len(written_logs) >= 1
        last_log = written_logs[-1]

        # contracts must be present (even if empty)
        assert "contracts" in last_log
        assert isinstance(last_log["contracts"], dict)

        # patch_manifest_path must be present (None for early return)
        assert "patch_manifest_path" in last_log

        # contract_gate_errors must be present (empty for non-gate failure)
        assert "contract_gate_errors" in last_log
        assert isinstance(last_log["contract_gate_errors"], list)

    def test_runlog_has_contracts_on_success(self, engine, tmp_path):
        """[RunLog] Successful run has contracts field populated."""
        written_logs = []
        original_write = engine.store.write_run_log

        def capture_write(exec_id, payload, project=None):
            written_logs.append(payload)
            return original_write(exec_id, payload, project=project)

        # Create a minimal successful mock scenario
        with patch.object(engine.store, "write_run_log", capture_write), \
             patch.object(engine.normalizer, "normalize") as mock_norm, \
             patch.object(engine.classifier, "classify") as mock_classify, \
             patch.object(engine.analyst, "generate_srs") as mock_srs, \
             patch.object(engine.srs_validator_gate, "process") as mock_validate_srs, \
             patch.object(engine.domain_modeler, "generate_ir") as mock_ir, \
             patch("orchestrator.engine.validate_ir") as mock_validate_ir, \
             patch.object(engine.policy_validator, "validate") as mock_policy, \
             patch.object(engine.contracts_agent, "generate_contracts") as mock_contracts, \
             patch("orchestrator.engine.validate_openapi") as mock_validate_oas, \
             patch("orchestrator.engine.validate_rbac") as mock_validate_rbac, \
             patch.object(engine.policy_validator, "validate_contracts") as mock_policy_contracts, \
             patch.object(engine.planner_agent, "generate_plan") as mock_plan, \
             patch("orchestrator.engine.validate_plan") as mock_validate_plan, \
             patch.object(engine.policy_validator, "validate_plan") as mock_policy_plan:

            # Setup mocks
            mock_norm.return_value = {"normalized": "test input", "raw": "test input"}
            mock_classify.return_value = Mock(selected_blueprint="generic")
            mock_srs.return_value = {
                "project": {"title": "Test", "version": "1.0"},
                "requirements": [{"id": "REQ-001", "type": "functional", "description": "Test", "priority": "high"}],
            }
            mock_validate_srs.return_value = (True, mock_srs.return_value, [])
            mock_ir.return_value = {
                "meta": {"project": "test", "version": "v1"},
                "domain": {"entities": []},
                "srs_traceability": [],
            }
            mock_validate_ir.return_value = Mock(ok=True, errors=[])
            mock_policy.return_value = (True, [])
            mock_contracts.return_value = (
                "openapi: '3.0.0'\ninfo:\n  title: Test\n  version: '1.0'\npaths: {}",
                {"roles": [], "permissions": []},
            )
            mock_validate_oas.return_value = Mock(ok=True, errors=[])
            mock_validate_rbac.return_value = Mock(ok=True, errors=[])
            mock_policy_contracts.return_value = (True, [])
            mock_plan.return_value = {"meta": {"project": "test", "version": "v1"}, "tasks": []}
            mock_validate_plan.return_value = Mock(ok=True, errors=[])
            mock_policy_plan.return_value = (True, [])

            result = engine.run("test_success", "test input")

        assert result.success is True

        # Check RunLog
        assert len(written_logs) >= 1
        last_log = written_logs[-1]

        # contracts must be present and populated
        assert "contracts" in last_log
        assert isinstance(last_log["contracts"], dict)

        # patch_manifest_path must be present
        assert "patch_manifest_path" in last_log

        # contract_gate_errors must be empty on success
        assert "contract_gate_errors" in last_log
        assert last_log["contract_gate_errors"] == []


class TestBlockedReasonConstant:
    """Test that CONTRACT_GATE_FAILED constant exists and is used."""

    def test_contract_gate_failed_constant_exists(self):
        """[BlockedReason] CONTRACT_GATE_FAILED constant is defined."""
        assert hasattr(BlockedReason, "CONTRACT_GATE_FAILED")
        assert BlockedReason.CONTRACT_GATE_FAILED == "CONTRACT_GATE_FAILED"
