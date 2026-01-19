"""Tests for Legacy Bridge asset verification (Etapa 2.7).

These tests verify that:
1. Unchanged assets verify successfully (MATCH)
2. Modified assets trigger drift detection
3. Missing assets are detected
4. Ledger events are emitted for all cases
"""

import json
import os
import pytest
from pathlib import Path

from engine.core.data_root import get_institution_root
from engine.core.ledger import reset_institution_ledgers, get_ledger_for_institution
from engine.legacy_bridge.models import SourceFormat, AssetStatus
from engine.legacy_bridge.registry import (
    LegacyBridgeRegistry,
    LEGACY_ASSET_VERIFIED,
    LEGACY_DRIFT_DETECTED,
    LEGACY_ASSET_MISSING,
)
from engine.legacy_bridge.verify import verify_asset, verify_all_assets


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
    return "test-inst-verify-001"


@pytest.fixture
def test_csv_file(tmp_path, monkeypatch, institution_id) -> Path:
    """Create a test CSV file and return its path object."""
    inst_root = get_institution_root(institution_id)
    inst_root.mkdir(parents=True, exist_ok=True)

    csv_path = inst_root / "exports" / "expense_report.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("id,amount,date,description\n1,100.00,2024-01-15,Office supplies\n2,250.00,2024-01-16,Travel\n")

    return csv_path


class TestVerifyUnchangedAsset:
    """Test verification of unchanged assets."""

    def test_verify_unchanged_asset_returns_match(self, institution_id, test_csv_file):
        """Verifying an unchanged asset returns MATCH status."""
        registry = LegacyBridgeRegistry(institution_id)

        # Register asset
        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        # Verify (no changes)
        result = verify_asset(institution_id, "expense-report-2024")

        assert result.status == "MATCH"
        assert result.drift_detected is False
        assert result.expected_sha256 == result.observed_sha256
        assert result.error is None

    def test_verify_unchanged_emits_verified_event(self, institution_id, test_csv_file):
        """Verifying an unchanged asset emits LEGACY_ASSET_VERIFIED."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        # Clear ledger events from registration
        ledger = get_ledger_for_institution(institution_id)
        initial_count = len(ledger.get_all_events())

        # Verify
        verify_asset(institution_id, "expense-report-2024")

        events = ledger.get_all_events()
        new_events = events[initial_count:]

        verified_events = [e for e in new_events if e.event_type == LEGACY_ASSET_VERIFIED]
        assert len(verified_events) == 1

        event = verified_events[0]
        assert event.payload["verification_result"] == "MATCH"
        assert event.payload["drift_detected"] is False


class TestVerifyModifiedAsset:
    """Test verification of modified assets."""

    def test_verify_modified_content_detects_drift(self, institution_id, test_csv_file):
        """Verifying a modified file detects content drift."""
        registry = LegacyBridgeRegistry(institution_id)

        # Register asset
        asset = registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        original_hash = asset.content_sha256

        # Modify the file (add 1 byte)
        test_csv_file.write_text(
            "id,amount,date,description\n1,100.00,2024-01-15,Office supplies\n2,250.00,2024-01-16,Travel!\n"
        )

        # Verify
        result = verify_asset(institution_id, "expense-report-2024")

        assert result.status == "DRIFT_DETECTED"
        assert result.drift_detected is True
        assert result.drift_type == "content_changed"
        assert result.expected_sha256 == original_hash
        assert result.observed_sha256 != original_hash

    def test_verify_modified_emits_drift_event(self, institution_id, test_csv_file):
        """Verifying a modified file emits LEGACY_DRIFT_DETECTED."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        # Clear ledger events from registration
        ledger = get_ledger_for_institution(institution_id)
        initial_count = len(ledger.get_all_events())

        # Modify the file
        test_csv_file.write_text("id,amount,date\n1,999.99,2024-01-15\n")

        # Verify
        verify_asset(institution_id, "expense-report-2024")

        events = ledger.get_all_events()
        new_events = events[initial_count:]

        drift_events = [e for e in new_events if e.event_type == LEGACY_DRIFT_DETECTED]
        assert len(drift_events) == 1

        event = drift_events[0]
        assert event.payload["drift_type"] == "content_changed"
        assert event.payload["expected_sha256"] != event.payload["observed_sha256"]

    def test_drift_updates_asset_status(self, institution_id, test_csv_file):
        """Drift detection updates asset status to drift_detected."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        # Modify the file
        test_csv_file.write_text("modified content\n")

        # Verify
        verify_asset(institution_id, "expense-report-2024")

        # Check asset status (create fresh registry to read updated state from disk)
        fresh_registry = LegacyBridgeRegistry(institution_id)
        assets = fresh_registry.list_assets()
        asset_state = next(a for a in assets if a["asset_id"] == "expense-report-2024")

        assert asset_state["status"] == AssetStatus.DRIFT_DETECTED.value
        assert asset_state["drift_count"] == 1

    def test_multiple_drifts_increment_count(self, institution_id, test_csv_file):
        """Multiple drifts increment the drift count."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        # First drift
        test_csv_file.write_text("modified content 1\n")
        verify_asset(institution_id, "expense-report-2024")

        # Second drift
        test_csv_file.write_text("modified content 2\n")
        verify_asset(institution_id, "expense-report-2024")

        # Check drift count (create fresh registry to read updated state from disk)
        fresh_registry = LegacyBridgeRegistry(institution_id)
        assets = fresh_registry.list_assets()
        asset_state = next(a for a in assets if a["asset_id"] == "expense-report-2024")

        assert asset_state["drift_count"] == 2


class TestVerifyMissingAsset:
    """Test verification of missing assets."""

    def test_verify_deleted_file_detects_missing(self, institution_id, test_csv_file):
        """Verifying a deleted file returns MISSING status."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        # Delete the file
        test_csv_file.unlink()

        # Verify
        result = verify_asset(institution_id, "expense-report-2024")

        assert result.status == "MISSING"
        assert result.drift_detected is True
        assert result.drift_type == "missing"
        assert result.error is not None

    def test_verify_missing_emits_missing_event(self, institution_id, test_csv_file):
        """Verifying a missing file emits LEGACY_ASSET_MISSING."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        # Clear ledger events from registration
        ledger = get_ledger_for_institution(institution_id)
        initial_count = len(ledger.get_all_events())

        # Delete the file
        test_csv_file.unlink()

        # Verify
        verify_asset(institution_id, "expense-report-2024")

        events = ledger.get_all_events()
        new_events = events[initial_count:]

        missing_events = [e for e in new_events if e.event_type == LEGACY_ASSET_MISSING]
        assert len(missing_events) == 1

        event = missing_events[0]
        assert "error" in event.payload
        assert event.payload["source_location"] == "exports/expense_report.csv"

    def test_verify_nonexistent_asset_returns_error(self, institution_id):
        """Verifying a non-existent asset returns ERROR status."""
        result = verify_asset(institution_id, "nonexistent-asset")

        assert result.status == "ERROR"
        assert "not found" in result.error.lower()


class TestVerifyAll:
    """Test verify-all functionality."""

    def test_verify_all_returns_summary(self, institution_id, tmp_path):
        """verify_all returns a summary of all assets."""
        # Create test files
        inst_root = get_institution_root(institution_id)
        exports_dir = inst_root / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        (exports_dir / "file1.csv").write_text("a,b,c\n1,2,3\n")
        (exports_dir / "file2.csv").write_text("x,y,z\n4,5,6\n")
        file3_path = exports_dir / "file3.csv"
        file3_path.write_text("p,q,r\n7,8,9\n")

        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="asset-1",
            name="Asset 1",
            source_location="exports/file1.csv",
            source_format=SourceFormat.CSV.value,
        )
        registry.register(
            asset_id="asset-2",
            name="Asset 2",
            source_location="exports/file2.csv",
            source_format=SourceFormat.CSV.value,
        )
        registry.register(
            asset_id="asset-3",
            name="Asset 3",
            source_location="exports/file3.csv",
            source_format=SourceFormat.CSV.value,
        )

        # Modify one, delete one
        (exports_dir / "file2.csv").write_text("MODIFIED\n")
        file3_path.unlink()

        # Verify all
        result = verify_all_assets(institution_id)

        assert result.total == 3
        assert result.ok == 1
        assert result.drift_detected == 1
        assert result.missing == 1
        assert len(result.results) == 3

    def test_verify_all_empty_registry(self, institution_id):
        """verify_all with no assets returns empty result."""
        result = verify_all_assets(institution_id)

        assert result.total == 0
        assert result.ok == 0
        assert result.drift_detected == 0
        assert result.missing == 0
        assert len(result.results) == 0


class TestSnapshotHistory:
    """Test snapshot history."""

    def test_verification_creates_new_snapshot(self, institution_id, test_csv_file):
        """Each verification creates a new snapshot."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        # Initial snapshot from registration
        snapshot1 = registry.get_last_snapshot("expense-report-2024")
        assert snapshot1 is not None

        # Verify (creates another snapshot)
        verify_asset(institution_id, "expense-report-2024")

        snapshot2 = registry.get_last_snapshot("expense-report-2024")
        assert snapshot2 is not None
        assert snapshot2.snapshot_id != snapshot1.snapshot_id
        assert snapshot2.prev_snapshot_id == snapshot1.snapshot_id

    def test_snapshot_links_to_previous(self, institution_id, test_csv_file):
        """Snapshots maintain links to previous snapshots."""
        registry = LegacyBridgeRegistry(institution_id)

        registry.register(
            asset_id="expense-report-2024",
            name="Expense Report 2024",
            source_location="exports/expense_report.csv",
            source_format=SourceFormat.CSV.value,
        )

        # Multiple verifications
        verify_asset(institution_id, "expense-report-2024")
        verify_asset(institution_id, "expense-report-2024")

        snapshot = registry.get_last_snapshot("expense-report-2024")
        assert snapshot.prev_snapshot_id is not None
        assert snapshot.prev_content_sha256 is not None
