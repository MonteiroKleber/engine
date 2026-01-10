"""Test that flags is ALWAYS present in RunLog.

Validates:
1) flags is always present (dict)
2) flags contains all 7 required keys
3) All flag values are bool
"""

import pytest
import tempfile
from unittest.mock import patch

from orchestrator.engine import Engine
from observability.contract_record import ContractRecord


class TestRunLogFlagsAlwaysPresent:
    """Test flags is always present in RunLog."""

    # Required flag keys (mirror of telemetry)
    REQUIRED_FLAGS = [
        "srs_ok",
        "ir_ok",
        "policy_ok",
        "contracts_ok",
        "plan_ok",
        "build_ok",
        "release_ok",
    ]

    def test_flags_present_on_success(self):
        """[RunLog] flags present with all keys on success."""
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
            result = engine.run("test_flags_success", input_text)

            assert result.success is True

            assert len(written_logs) >= 1
            last_log = written_logs[-1]

            # flags assertions
            assert "flags" in last_log, "RunLog should ALWAYS include 'flags'"
            assert isinstance(last_log["flags"], dict), "flags should be a dict"

            # All required keys present
            for key in self.REQUIRED_FLAGS:
                assert key in last_log["flags"], \
                    f"flags should include '{key}'"
                assert isinstance(last_log["flags"][key], bool), \
                    f"flags['{key}'] should be bool, got {type(last_log['flags'][key])}"

    def test_flags_present_on_contract_gate_fail(self):
        """[RunLog] flags present with all keys on contract gate failure."""
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
                result = engine.run("test_flags_fail", input_text)

            assert result.success is False
            assert result.final_status == "contract_gate_failed"

            assert len(written_logs) >= 1
            last_log = written_logs[-1]

            # flags present even on failure
            assert "flags" in last_log, "RunLog should ALWAYS include 'flags'"
            assert isinstance(last_log["flags"], dict)

            # All required keys present
            for key in self.REQUIRED_FLAGS:
                assert key in last_log["flags"], \
                    f"flags should include '{key}' even on failure"
                assert isinstance(last_log["flags"][key], bool), \
                    f"flags['{key}'] should be bool"

            # contracts_ok should be False when contract gate failed
            assert last_log["flags"]["contracts_ok"] is False, \
                "contracts_ok should be False when contract gate failed"
