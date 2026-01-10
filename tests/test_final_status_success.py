"""Test that final_status is explicitly 'success' on happy path.

Validates:
1) RunResult.final_status == 'success' on successful run
2) RunLog always includes 'final_status' field
3) RunLog.final_status == 'success' on successful run
"""

import pytest
import tempfile
from orchestrator.engine import Engine


class TestFinalStatusSuccess:
    """Test final_status is 'success' on happy path."""

    def test_run_success_has_final_status_success(self):
        """[FinalStatus] Engine.run() sets final_status='success' on success."""
        with tempfile.TemporaryDirectory() as tmp_store:
            engine = Engine(store_root=tmp_store)

            # Capture run logs
            written_logs = []
            original_write = engine.store.write_run_log

            def capture_write(exec_id, payload, project=None):
                written_logs.append(payload)
                return original_write(exec_id, payload, project=project)

            engine.store.write_run_log = capture_write

            # Run with valid input (comprehensive enough for all validations)
            input_text = """Sistema de cadastro de empresas.

Entidade empresa (id, nome, cnpj).
Entidade usuario (id, nome, email).

Caso de uso: usuario cria empresa.
Caso de uso: usuario lista empresas.
"""
            result = engine.run("test_final_status", input_text)

            # Assertions on RunResult
            assert result.success is True, "Run should succeed"
            assert result.final_status == "success", \
                f"RunResult.final_status should be 'success', got '{result.final_status}'"

            # Assertions on RunLog
            assert len(written_logs) >= 1, "At least one run log should be written"
            last_log = written_logs[-1]

            assert "final_status" in last_log, "RunLog should always include 'final_status'"
            assert last_log["final_status"] == "success", \
                f"RunLog.final_status should be 'success', got '{last_log['final_status']}'"

    def test_runlog_always_has_final_status(self):
        """[FinalStatus] RunLog always includes final_status field."""
        with tempfile.TemporaryDirectory() as tmp_store:
            engine = Engine(store_root=tmp_store)

            written_logs = []
            original_write = engine.store.write_run_log

            def capture_write(exec_id, payload, project=None):
                written_logs.append(payload)
                return original_write(exec_id, payload, project=project)

            engine.store.write_run_log = capture_write

            # Run with valid input
            input_text = """Sistema de cadastro.

Entidade cliente (id, nome, email).

Caso de uso: criar cliente.
"""
            engine.run("test_final_status_present", input_text)

            # Check all logs have final_status
            for i, log in enumerate(written_logs):
                assert "final_status" in log, \
                    f"RunLog #{i} should have 'final_status' field"
                assert isinstance(log["final_status"], str), \
                    f"RunLog #{i} final_status should be a string"
                assert log["final_status"], \
                    f"RunLog #{i} final_status should not be empty"
