"""Test that duration_ms and counts are ALWAYS present in RunLog.

Validates:
1) duration_ms is always present (number >= 0)
2) counts is always present (dict with all required keys)
3) All count keys exist even on early failure paths
"""

import pytest
import tempfile
from unittest.mock import patch

from orchestrator.engine import Engine
from observability.contract_record import ContractRecord


class TestRunLogCountsDurationAlwaysPresent:
    """Test duration_ms and counts are always present in RunLog."""

    def test_duration_ms_and_counts_present_on_success(self):
        """[RunLog] duration_ms and counts present on success."""
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
            engine.run("test_counts_success", input_text)

            assert len(written_logs) >= 1
            last_log = written_logs[-1]

            # duration_ms assertions
            assert "duration_ms" in last_log, "RunLog should ALWAYS include 'duration_ms'"
            assert isinstance(last_log["duration_ms"], (int, float)), \
                f"duration_ms should be a number, got {type(last_log['duration_ms'])}"
            assert last_log["duration_ms"] >= 0, "duration_ms should be >= 0"

            # counts assertions
            assert "counts" in last_log, "RunLog should ALWAYS include 'counts'"
            assert isinstance(last_log["counts"], dict), "counts should be a dict"

            # All required keys present
            required_keys = [
                "requirements_count",
                "entities_count",
                "operations_count",
                "tasks_count",
                "patch_count",
            ]
            for key in required_keys:
                assert key in last_log["counts"], \
                    f"counts should include '{key}'"
                assert isinstance(last_log["counts"][key], int), \
                    f"counts['{key}'] should be int"

    def test_duration_ms_and_counts_present_on_contract_gate_fail(self):
        """[RunLog] duration_ms and counts present on contract gate failure."""
        with tempfile.TemporaryDirectory() as tmp_store:
            engine = Engine(store_root=tmp_store)

            written_logs = []
            original_write = engine.store.write_run_log

            def capture_write(exec_id, payload, project=None):
                written_logs.append(payload)
                return original_write(exec_id, payload, project=project)

            original_create = engine._create_contract_record

            def failing_contract_record(kind, path, is_yaml=False):
                if kind == "ir":
                    return ContractRecord(
                        kind=kind,
                        path=path,
                        contract_gate_ok=False,
                        contract_gate_error="Hash mismatch",
                    )
                return original_create(kind, path, is_yaml)

            input_text = "Cadastro de produtos. Entidade produto (id, nome). Criar produto."

            with patch.object(engine.store, "write_run_log", capture_write), \
                 patch.object(engine, "_create_contract_record", failing_contract_record):
                result = engine.run("test_counts_fail", input_text)

            assert result.success is False

            assert len(written_logs) >= 1
            last_log = written_logs[-1]

            # duration_ms present even on failure
            assert "duration_ms" in last_log
            assert isinstance(last_log["duration_ms"], (int, float))

            # counts present even on failure
            assert "counts" in last_log
            assert isinstance(last_log["counts"], dict)

            # All keys present (values may be 0)
            required_keys = [
                "requirements_count",
                "entities_count",
                "operations_count",
                "tasks_count",
                "patch_count",
            ]
            for key in required_keys:
                assert key in last_log["counts"], \
                    f"counts should include '{key}' even on failure"
