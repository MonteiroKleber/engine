"""Tests for ISE contract ledger."""

import json
import pytest

from engine.ise.manifest import sha256_str
from engine.ise.contract_ledger import (
    generate_contract_ledger,
    generate_contract_ledger_json,
)


class TestContractLedger:
    """Test contract ledger generation."""

    def test_ledger_structure(self):
        """Test ledger has required fields."""
        contracts = {
            "rbac.json": sha256_str('{"version": "1.0"}'),
            "workflows.json": sha256_str('{"version": "1.0"}'),
        }

        ledger = generate_contract_ledger(
            bundle_name="test-bundle",
            version="1.0.0",
            contracts=contracts,
            manifest_hash="abc123",
            idl_source='{"system": "test"}',
        )

        assert ledger["ledger_version"] == "1.0"
        assert "ledger_id" in ledger
        assert ledger["bundle_name"] == "test-bundle"
        assert ledger["bundle_version"] == "1.0.0"
        assert ledger["manifest_hash"] == "abc123"
        assert "idl_hash" in ledger
        assert "created_at" in ledger
        assert "contracts" in ledger
        assert "audit_trail" in ledger

    def test_ledger_contracts_list(self):
        """Test ledger contains all contracts."""
        contracts = {
            "rbac.json": "hash1",
            "workflows.json": "hash2",
        }

        ledger = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts=contracts,
            manifest_hash="abc",
            idl_source="{}",
        )

        contract_names = {c["contract_name"] for c in ledger["contracts"]}
        assert "rbac.json" in contract_names
        assert "workflows.json" in contract_names

    def test_ledger_contract_status(self):
        """Test all contracts have active status."""
        contracts = {"rbac.json": "hash1"}

        ledger = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts=contracts,
            manifest_hash="abc",
            idl_source="{}",
        )

        for contract in ledger["contracts"]:
            assert contract["status"] == "active"

    def test_ledger_audit_trail(self):
        """Test ledger has initial audit entry."""
        ledger = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts={"rbac.json": "hash1"},
            manifest_hash="abc",
            idl_source="{}",
        )

        assert len(ledger["audit_trail"]) >= 1
        first_entry = ledger["audit_trail"][0]
        assert first_entry["event"] == "bundle_compiled"
        assert "timestamp" in first_entry
        assert "details" in first_entry

    def test_ledger_idl_hash(self):
        """Test ledger contains IDL hash."""
        idl = '{"system": "test", "version": "1.0.0"}'

        ledger = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts={},
            manifest_hash="abc",
            idl_source=idl,
        )

        expected_hash = sha256_str(idl)
        assert ledger["idl_hash"] == expected_hash

    def test_ledger_id_deterministic(self):
        """Test ledger ID is deterministic."""
        ledger1 = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts={},
            manifest_hash="abc123",
            idl_source="{}",
        )
        ledger2 = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts={},
            manifest_hash="abc123",
            idl_source="{}",
        )

        assert ledger1["ledger_id"] == ledger2["ledger_id"]

    def test_ledger_id_changes_with_content(self):
        """Test ledger ID changes when content changes."""
        ledger1 = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts={},
            manifest_hash="abc123",
            idl_source="{}",
        )
        ledger2 = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts={},
            manifest_hash="xyz789",  # Different manifest hash
            idl_source="{}",
        )

        assert ledger1["ledger_id"] != ledger2["ledger_id"]

    def test_generate_contract_ledger_json(self):
        """Test JSON ledger generation."""
        ledger_json = generate_contract_ledger_json(
            bundle_name="test",
            version="1.0",
            contracts={"rbac.json": "hash1"},
            manifest_hash="abc",
            idl_source="{}",
        )

        # Should be valid JSON
        ledger = json.loads(ledger_json)
        assert ledger["bundle_name"] == "test"


class TestLedgerIntegrity:
    """Test ledger integrity features."""

    def test_contracts_sorted_by_name(self):
        """Test contracts are sorted alphabetically."""
        contracts = {
            "z_contract.json": "hash_z",
            "a_contract.json": "hash_a",
            "m_contract.json": "hash_m",
        }

        ledger = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts=contracts,
            manifest_hash="abc",
            idl_source="{}",
        )

        names = [c["contract_name"] for c in ledger["contracts"]]
        assert names == sorted(names)

    def test_ledger_id_length(self):
        """Test ledger ID is 16 characters."""
        ledger = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts={},
            manifest_hash="abc",
            idl_source="{}",
        )

        assert len(ledger["ledger_id"]) == 16

    def test_audit_trail_has_contract_count(self):
        """Test audit trail includes contract count."""
        contracts = {
            "rbac.json": "hash1",
            "workflows.json": "hash2",
            "approvals.json": "hash3",
        }

        ledger = generate_contract_ledger(
            bundle_name="test",
            version="1.0",
            contracts=contracts,
            manifest_hash="abc",
            idl_source="{}",
        )

        first_entry = ledger["audit_trail"][0]
        assert first_entry["details"]["contract_count"] == 3
