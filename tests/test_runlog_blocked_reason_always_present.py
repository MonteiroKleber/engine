"""Test that blocked_reason is ALWAYS present in RunLog.

Validates:
1) blocked_reason is present in RunLog on success (value: None)
2) blocked_reason is present in RunLog on failure (value: canonical constant)
"""

import pytest
import tempfile
from unittest.mock import patch

from orchestrator.engine import Engine
from observability.contract_record import ContractRecord
from observability.telemetry import BlockedReason


class TestBlockedReasonAlwaysPresent:
    """Test blocked_reason is always present in RunLog."""

    def test_blocked_reason_present_on_success(self):
        """[blocked_reason] Present and None on success."""
        with tempfile.TemporaryDirectory() as tmp_store:
            engine = Engine(store_root=tmp_store)

            # Capture run logs
            written_logs = []
            original_write = engine.store.write_run_log

            def capture_write(exec_id, payload, project=None):
                written_logs.append(payload)
                return original_write(exec_id, payload, project=project)

            engine.store.write_run_log = capture_write

            # Run with valid input
            input_text = """Sistema de cadastro de empresas.

Entidade empresa (id, nome, cnpj).
Entidade usuario (id, nome, email).

Caso de uso: usuario cria empresa.
Caso de uso: usuario lista empresas.
"""
            result = engine.run("test_blocked_reason_success", input_text)

            # Verify success
            assert result.success is True, "Run should succeed"

            # Verify blocked_reason in RunLog
            assert len(written_logs) >= 1
            last_log = written_logs[-1]

            assert "blocked_reason" in last_log, \
                "RunLog should ALWAYS include 'blocked_reason'"
            assert last_log["blocked_reason"] is None, \
                f"blocked_reason should be None on success, got {last_log['blocked_reason']!r}"

    def test_blocked_reason_present_on_contract_gate_failed(self):
        """[blocked_reason] Present and CONTRACT_GATE_FAILED on contract gate failure."""
        with tempfile.TemporaryDirectory() as tmp_store:
            engine = Engine(store_root=tmp_store)

            # Capture run logs
            written_logs = []
            original_write = engine.store.write_run_log

            def capture_write(exec_id, payload, project=None):
                written_logs.append(payload)
                return original_write(exec_id, payload, project=project)

            # Patch _create_contract_record to force IR failure
            original_create = engine._create_contract_record

            def failing_contract_record(kind, path, is_yaml=False):
                if kind == "ir":
                    return ContractRecord(
                        kind=kind,
                        path=path,
                        content_hash_sha256="corrupted_hash",
                        contract_gate_ok=False,
                        contract_gate_error="Hash mismatch",
                    )
                return original_create(kind, path, is_yaml)

            input_text = "Cadastro de produtos. Entidade produto (id, nome). Criar produto."

            with patch.object(engine.store, "write_run_log", capture_write), \
                 patch.object(engine, "_create_contract_record", failing_contract_record):
                result = engine.run("test_blocked_reason_fail", input_text)

            # Verify failure
            assert result.success is False
            assert result.final_status == "contract_gate_failed"

            # Verify blocked_reason in RunLog
            assert len(written_logs) >= 1
            last_log = written_logs[-1]

            assert "blocked_reason" in last_log, \
                "RunLog should ALWAYS include 'blocked_reason'"
            assert last_log["blocked_reason"] == BlockedReason.CONTRACT_GATE_FAILED, \
                f"blocked_reason should be CONTRACT_GATE_FAILED, got {last_log['blocked_reason']!r}"
