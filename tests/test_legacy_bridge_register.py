"""Tests for Legacy Bridge asset registration (Etapa 2.7).

These tests verify that:
1. Assets can be registered with valid parameters
2. Registration creates ledger events
3. Invalid paths (absolute, ..) are rejected
4. Duplicate asset IDs are rejected
"""

import json
import os
import pytest
from pathlib import Path

from engine.core.data_root import get_institution_root
from engine.core.ledger import reset_institution_ledgers, get_ledger_for_institution
from engine.legacy_bridge.models import LegacyAsset, SourceFormat, AssetStatus
from engine.legacy_bridge.registry import (
    LegacyBridgeRegistry,
    RegistryError,
    LEGACY_ASSET_REGISTERED,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    reset_institution_ledgers()
    yield
    reset_institution_ledgers()


@pytest.fixture
def institution_id() -> str:
    """Test institution ID."""
    return "test-inst-legacy-001"


@pytest.fixture
def test_csv_file(tmp_path, monkeypatch, institution_id) -> str:
    """Create a test CSV file in the institution root."""
    # Get institution root
    inst_root = get_institution_root(institution_id)
    inst_root.mkdir(parents=True, exist_ok=True)

    # Create test CSV
    csv_path = inst_root / "exports" / "expense_report.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("id,amount,date,description\n1,100.00,2024-01-15,Office supplies\n2,250.00,2024-01-16,Travel\n")

    return "exports/expense_report.csv"


@pytest.fixture
def test_json_file(tmp_path, monkeypatch, institution_id) -> str:
    """Create a test JSON file in the institution root."""
    inst_root = get_institution_root(institution_id)
    inst_root.mkdir(parents=True, exist_ok=True)

    json_path = inst_root / "exports" / "customers.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text('{"customers": [{"id": 1, "name": "Acme"}, {"id": 2, "name": "Corp"}]}')

    return "exports/customers.json"


class TestRegisterAsset:
    """Test asset registration."""

    def test_register_csv_asset_creates_record(self, institution_id, test_csv_file):
        """Registering a CSV asset creates a registry record."""
        registry = LegacyBridgeRegistry(institution_id)

        asset = registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location=test_csv_file,
            source_format=SourceFormat.CSV.value,
        )

        assert asset.asset_id == "expense-report-2024"
        assert asset.name == "Expense Report 2024"
        assert asset.source_location == test_csv_file
        assert asset.source_format == SourceFormat.CSV.value
        assert asset.content_sha256.startswith("SHA256:")
        assert asset.content_size_bytes > 0
        assert asset.status == AssetStatus.ACTIVE.value
        assert asset.institution_id == institution_id

    def test_register_csv_extracts_schema(self, institution_id, test_csv_file):
        """Registering a CSV asset extracts column headers."""
        registry = LegacyBridgeRegistry(institution_id)

        asset = registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location=test_csv_file,
            source_format=SourceFormat.CSV.value,
        )

        assert "columns" in asset.schema_metadata
        assert asset.schema_metadata["columns"] == ["id", "amount", "date", "description"]
        assert "row_count" in asset.schema_metadata
        assert asset.schema_metadata["row_count"] == 2

    def test_register_json_extracts_schema(self, institution_id, test_json_file):
        """Registering a JSON asset extracts top-level keys."""
        registry = LegacyBridgeRegistry(institution_id)

        asset = registry.register(
            asset_id="customers-export",
            name="Customers Export",
            source_location=test_json_file,
            source_format=SourceFormat.JSON.value,
        )

        assert "keys" in asset.schema_metadata
        assert "customers" in asset.schema_metadata["keys"]

    def test_register_creates_ledger_event(self, institution_id, test_csv_file):
        """Registering an asset emits LEGACY_ASSET_REGISTERED to ledger."""
        registry = LegacyBridgeRegistry(institution_id)

        asset = registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location=test_csv_file,
            source_format=SourceFormat.CSV.value,
        )

        # Check ledger
        ledger = get_ledger_for_institution(institution_id)
        events = ledger.get_all_events()

        assert len(events) >= 1
        register_event = [e for e in events if e.event_type == LEGACY_ASSET_REGISTERED]
        assert len(register_event) == 1

        event = register_event[0]
        assert event.case_id == "expense-report-2024"
        assert event.step == "LEGACY_BRIDGE:asset.register"
        assert event.payload["asset_id"] == "expense-report-2024"
        assert event.payload["name"] == "Expense Report 2024"
        assert "content_sha256" in event.payload

    def test_register_creates_initial_snapshot(self, institution_id, test_csv_file):
        """Registering an asset creates an initial snapshot."""
        registry = LegacyBridgeRegistry(institution_id)

        asset = registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location=test_csv_file,
            source_format=SourceFormat.CSV.value,
        )

        snapshot = registry.get_last_snapshot("expense-report-2024")
        assert snapshot is not None
        assert snapshot.asset_id == "expense-report-2024"
        assert snapshot.content_sha256 == asset.content_sha256
        assert snapshot.drift_detected is False

    def test_register_duplicate_asset_id_fails(self, institution_id, test_csv_file):
        """Registering an asset with existing ID fails."""
        registry = LegacyBridgeRegistry(institution_id)

        # First registration succeeds
        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location=test_csv_file,
            source_format=SourceFormat.CSV.value,
        )

        # Second registration fails
        with pytest.raises(RegistryError) as exc_info:
            registry.register(
                asset_id="expense-report-2024",
                name="Another Report",
                source_location=test_csv_file,
                source_format=SourceFormat.CSV.value,
            )

        assert "already exists" in str(exc_info.value).lower()

    def test_register_absolute_path_rejected(self, institution_id):
        """Registering with absolute path is rejected."""
        registry = LegacyBridgeRegistry(institution_id)

        with pytest.raises(RegistryError) as exc_info:
            registry.register(
                asset_id="invalid-asset",
                name="Invalid Asset",
                source_location="/etc/passwd",
                source_format=SourceFormat.RAW.value,
            )

        assert "absolute" in str(exc_info.value).lower()

    def test_register_path_traversal_rejected(self, institution_id):
        """Registering with path traversal (..) is rejected."""
        registry = LegacyBridgeRegistry(institution_id)

        with pytest.raises(RegistryError) as exc_info:
            registry.register(
                asset_id="invalid-asset",
                name="Invalid Asset",
                source_location="../../../etc/passwd",
                source_format=SourceFormat.RAW.value,
            )

        assert ".." in str(exc_info.value)

    def test_register_nonexistent_file_fails(self, institution_id):
        """Registering a non-existent file fails."""
        registry = LegacyBridgeRegistry(institution_id)

        with pytest.raises(RegistryError) as exc_info:
            registry.register(
                asset_id="missing-asset",
                name="Missing Asset",
                source_location="exports/nonexistent.csv",
                source_format=SourceFormat.CSV.value,
            )

        assert "not found" in str(exc_info.value).lower() or "access" in str(exc_info.value).lower()

    def test_register_with_dept_id(self, institution_id, tmp_path, monkeypatch):
        """Registering with dept_id creates asset in dept namespace."""
        # Create test file in dept directory
        inst_root = get_institution_root(institution_id)
        dept_dir = inst_root / "depts" / "finance" / "exports"
        dept_dir.mkdir(parents=True, exist_ok=True)
        (dept_dir / "budget.csv").write_text("category,amount\nIT,50000\n")

        registry = LegacyBridgeRegistry(institution_id, dept_id="finance")

        asset = registry.register(
            asset_id="budget-2024",
            name="Budget 2024",
            source_location="exports/budget.csv",
            source_format=SourceFormat.CSV.value,
        )

        assert asset.dept_id == "finance"

    def test_get_asset_returns_registered_asset(self, institution_id, test_csv_file):
        """get_asset returns a previously registered asset."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location=test_csv_file,
            source_format=SourceFormat.CSV.value,
        )

        asset = registry.get_asset("expense-report-2024")
        assert asset is not None
        assert asset.asset_id == "expense-report-2024"
        assert asset.name == "Expense Report 2024"

    def test_get_asset_returns_none_for_unknown(self, institution_id):
        """get_asset returns None for unknown asset."""
        registry = LegacyBridgeRegistry(institution_id)

        asset = registry.get_asset("nonexistent-asset")
        assert asset is None

    def test_list_assets_returns_registered_assets(self, institution_id, test_csv_file, test_json_file):
        """list_assets returns all registered assets."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location=test_csv_file,
            source_format=SourceFormat.CSV.value,
        )

        registry.register(
            asset_id="customers-export",
            name="Customers Export",
            source_location=test_json_file,
            source_format=SourceFormat.JSON.value,
        )

        assets = registry.list_assets()
        assert len(assets) == 2

        asset_ids = {a["asset_id"] for a in assets}
        assert "expense-report-2024" in asset_ids
        assert "customers-export" in asset_ids


class TestRegistryPersistence:
    """Test registry persistence across instances."""

    def test_registry_persists_across_instances(self, institution_id, test_csv_file):
        """Registry data persists across registry instances."""
        # First instance registers asset
        registry1 = LegacyBridgeRegistry(institution_id)
        registry1.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location=test_csv_file,
            source_format=SourceFormat.CSV.value,
        )

        # Second instance can see the asset
        registry2 = LegacyBridgeRegistry(institution_id)
        asset = registry2.get_asset("expense-report-2024")

        assert asset is not None
        assert asset.asset_id == "expense-report-2024"
