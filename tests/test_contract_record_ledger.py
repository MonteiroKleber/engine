"""Tests for ContractRecord and ContractLedger.

Validates:
1) ContractRecord creation and serialization
2) ContractLedger add/get operations
3) to_dict() format for RunLog integration
4) Contract gate status tracking
"""

import pytest
from datetime import datetime

from observability.contract_record import ContractRecord, ContractLedger


class TestContractRecord:
    """Tests for ContractRecord dataclass."""

    def test_contract_record_defaults(self):
        """[ContractRecord] Default values are correct."""
        record = ContractRecord(kind="srs")

        assert record.kind == "srs"
        assert record.path is None
        assert record.schema_version is None
        assert record.content_hash_sha256 is None
        assert record.contract_gate_ok is True
        assert record.contract_gate_error == ""
        assert record.computed_at is not None

    def test_contract_record_full(self):
        """[ContractRecord] All fields can be set."""
        record = ContractRecord(
            kind="ir",
            path="/path/to/ir.json",
            schema_version="ir.v1",
            content_hash_sha256="abc123",
            contract_gate_ok=True,
            contract_gate_error="",
        )

        assert record.kind == "ir"
        assert record.path == "/path/to/ir.json"
        assert record.schema_version == "ir.v1"
        assert record.content_hash_sha256 == "abc123"
        assert record.contract_gate_ok is True

    def test_contract_record_failed_gate(self):
        """[ContractRecord] Failed gate is tracked."""
        record = ContractRecord(
            kind="oas",
            path="/path/to/oas.yaml",
            contract_gate_ok=False,
            contract_gate_error="Hash mismatch",
        )

        assert record.contract_gate_ok is False
        assert record.contract_gate_error == "Hash mismatch"

    def test_contract_record_to_dict(self):
        """[ContractRecord] to_dict() produces correct format."""
        record = ContractRecord(
            kind="rbac",
            path="/path/to/rbac.json",
            schema_version="rbac.v1",
            content_hash_sha256="def456",
            contract_gate_ok=True,
        )

        d = record.to_dict()

        assert d["kind"] == "rbac"
        assert d["path"] == "/path/to/rbac.json"
        assert d["schema_version"] == "rbac.v1"
        assert d["content_hash_sha256"] == "def456"
        assert d["contract_gate_ok"] is True
        assert "computed_at" in d

    def test_contract_record_to_dict_without_optionals(self):
        """[ContractRecord] to_dict() handles None values."""
        record = ContractRecord(kind="plan")

        d = record.to_dict()

        assert d["kind"] == "plan"
        assert d["path"] is None
        assert d["schema_version"] is None
        assert d["content_hash_sha256"] is None


class TestContractLedger:
    """Tests for ContractLedger collection."""

    def test_ledger_empty(self):
        """[ContractLedger] Empty ledger returns empty dict."""
        ledger = ContractLedger()

        assert ledger.to_dict() == {}

    def test_ledger_add_single(self):
        """[ContractLedger] Add single record."""
        ledger = ContractLedger()
        record = ContractRecord(
            kind="srs",
            path="/path/to/srs.json",
            content_hash_sha256="hash123",
        )

        ledger.add(record)

        assert ledger.get("srs") == record

    def test_ledger_add_multiple(self):
        """[ContractLedger] Add multiple records."""
        ledger = ContractLedger()

        srs_record = ContractRecord(kind="srs", path="/srs.json")
        ir_record = ContractRecord(kind="ir", path="/ir.json")

        ledger.add(srs_record)
        ledger.add(ir_record)

        assert ledger.get("srs") == srs_record
        assert ledger.get("ir") == ir_record

    def test_ledger_get_missing(self):
        """[ContractLedger] Get non-existent returns None."""
        ledger = ContractLedger()

        assert ledger.get("nonexistent") is None

    def test_ledger_to_dict(self):
        """[ContractLedger] to_dict() includes all records."""
        ledger = ContractLedger()

        ledger.add(ContractRecord(kind="srs", path="/srs.json", content_hash_sha256="h1"))
        ledger.add(ContractRecord(kind="ir", path="/ir.json", content_hash_sha256="h2"))

        d = ledger.to_dict()

        assert "srs" in d
        assert "ir" in d
        assert d["srs"]["content_hash_sha256"] == "h1"
        assert d["ir"]["content_hash_sha256"] == "h2"

    def test_ledger_all_ok_true(self):
        """[ContractLedger] all_ok() returns True when all gates pass."""
        ledger = ContractLedger()

        ledger.add(ContractRecord(kind="srs", contract_gate_ok=True))
        ledger.add(ContractRecord(kind="ir", contract_gate_ok=True))

        assert ledger.all_ok() is True

    def test_ledger_all_ok_false(self):
        """[ContractLedger] all_ok() returns False when any gate fails."""
        ledger = ContractLedger()

        ledger.add(ContractRecord(kind="srs", contract_gate_ok=True))
        ledger.add(ContractRecord(kind="ir", contract_gate_ok=False, contract_gate_error="Failed"))

        assert ledger.all_ok() is False

    def test_ledger_all_ok_empty(self):
        """[ContractLedger] all_ok() returns True for empty ledger."""
        ledger = ContractLedger()

        assert ledger.all_ok() is True

    def test_ledger_get_errors(self):
        """[ContractLedger] get_errors() returns only failed records."""
        ledger = ContractLedger()

        ledger.add(ContractRecord(kind="srs", contract_gate_ok=True))
        ledger.add(ContractRecord(kind="ir", contract_gate_ok=False, contract_gate_error="Error 1"))
        ledger.add(ContractRecord(kind="oas", contract_gate_ok=False, contract_gate_error="Error 2"))

        errors = ledger.get_errors()

        assert len(errors) == 2
        assert any(r.kind == "ir" for r in errors)
        assert any(r.kind == "oas" for r in errors)


class TestContractRecordFromDict:
    """Tests for ContractRecord.from_dict() deserialization."""

    def test_from_dict_full(self):
        """[ContractRecord] from_dict() reconstructs full record."""
        data = {
            "kind": "plan",
            "path": "/path/to/plan.json",
            "schema_version": "plan.v1",
            "content_hash_sha256": "abcdef123456",
            "contract_gate_ok": True,
            "contract_gate_error": "",
            "computed_at": "2026-01-05T10:00:00",
        }

        record = ContractRecord.from_dict(data)

        assert record.kind == "plan"
        assert record.path == "/path/to/plan.json"
        assert record.schema_version == "plan.v1"
        assert record.content_hash_sha256 == "abcdef123456"
        assert record.contract_gate_ok is True

    def test_from_dict_minimal(self):
        """[ContractRecord] from_dict() handles minimal data."""
        data = {"kind": "srs"}

        record = ContractRecord.from_dict(data)

        assert record.kind == "srs"
        assert record.path is None

    def test_from_dict_empty(self):
        """[ContractRecord] from_dict() handles empty dict."""
        data = {}

        record = ContractRecord.from_dict(data)

        assert record.kind == "unknown"


class TestContractLedgerFromDict:
    """Tests for ContractLedger.from_dict() deserialization."""

    def test_from_dict_full(self):
        """[ContractLedger] from_dict() reconstructs ledger."""
        data = {
            "srs": {
                "kind": "srs",
                "path": "/srs.json",
                "content_hash_sha256": "h1",
                "contract_gate_ok": True,
            },
            "ir": {
                "kind": "ir",
                "path": "/ir.json",
                "content_hash_sha256": "h2",
                "contract_gate_ok": True,
            },
        }

        ledger = ContractLedger.from_dict(data)

        assert ledger.get("srs") is not None
        assert ledger.get("ir") is not None
        assert ledger.get("srs").content_hash_sha256 == "h1"

    def test_from_dict_empty(self):
        """[ContractLedger] from_dict() handles empty dict."""
        ledger = ContractLedger.from_dict({})

        assert ledger.to_dict() == {}
