"""Test that schema_version is ALWAYS present in RunLog.

Validates:
1) schema_version is always present (string)
2) schema_version == "runlog.v1"
3) Present on both success and failure paths
"""

import pytest
import tempfile
from unittest.mock import patch

from orchestrator.engine import Engine
from observability.contract_record import ContractRecord


class TestRunLogSchemaVersionAlwaysPresent:
    """Test schema_version is always present in RunLog."""

    def test_schema_version_present_on_success(self):
        """[RunLog] schema_version present and correct on success."""
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
            result = engine.run("test_schema_version_success", input_text)

            assert result.success is True

            assert len(written_logs) >= 1
            last_log = written_logs[-1]

            # schema_version assertions
            assert "schema_version" in last_log, \
                "RunLog should ALWAYS include 'schema_version'"
            assert isinstance(last_log["schema_version"], str), \
                f"schema_version should be a string, got {type(last_log['schema_version'])}"
            assert last_log["schema_version"] == "runlog.v1", \
                f"schema_version should be 'runlog.v1', got '{last_log['schema_version']}'"

    def test_schema_version_present_on_contract_gate_fail(self):
        """[RunLog] schema_version present and correct on contract gate failure."""
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
                result = engine.run("test_schema_version_fail", input_text)

            assert result.success is False

            assert len(written_logs) >= 1
            last_log = written_logs[-1]

            # schema_version present even on failure
            assert "schema_version" in last_log, \
                "RunLog should ALWAYS include 'schema_version' even on failure"
            assert isinstance(last_log["schema_version"], str)
            assert last_log["schema_version"] == "runlog.v1", \
                f"schema_version should be 'runlog.v1' even on failure, got '{last_log['schema_version']}'"
