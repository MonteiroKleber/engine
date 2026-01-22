"""Tests for Runtime Reload - Hot-swap registry (Etapa 6.6).

Tests:
- ActiveRuntimeSnapshot creation from bundle
- reload_active_runtime() updates registry and snapshot
- Dynamic lookup in IDL handler after reload
- OpenAPI cache invalidation after reload
- RUNTIME_RELOADED ledger events
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.core.runtime_reload import (
    ActiveRuntimeSnapshot,
    get_active_snapshot,
    set_active_snapshot,
    clear_active_snapshot,
    reset_all_snapshots,
    create_snapshot_from_bundle,
    reload_active_runtime,
    reload_on_boot,
)
from engine.core.operations import (
    get_operations,
    set_operations,
    reset_all_operations,
    get_operation_by_endpoint_sig,
    OperationsDef,
    Operation,
)
from engine.core.errors import (
    RUNTIME_RELOAD_BUNDLE_MISSING,
    RUNTIME_RELOAD_FAILED,
    RUNTIME_OPERATION_NOT_FOUND,
)
from engine.core.ledger import AuditLedger, set_ledger


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path / "bundles" / "finance-pilot"))

    # Set up ledger
    ledger_path = tmp_path / "audit_ledger.jsonl"
    ledger = AuditLedger(ledger_path)
    set_ledger(ledger)

    # Reset global state
    reset_all_snapshots()
    reset_all_operations()

    yield

    reset_all_snapshots()
    reset_all_operations()
    set_ledger(None)


@pytest.fixture
def bundle_v1(tmp_path):
    """Create a v1 bundle for testing."""
    bundle_dir = tmp_path / "bundles" / "releases" / "20260101-120000" / "finance-pilot"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest
    manifest = {
        "name": "finance-pilot",
        "version": "1.0.0",
        "created_at": "2026-01-01T12:00:00Z",
        "contracts": [],
    }
    manifest_path = bundle_dir / "bundle.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Create operations with required schema version
    operations = {
        "operations_schema_version": "1.0",
        "operations": [
            {
                "operation_id": "create_expense",
                "path": "/finance/expenses",
                "method": "POST",
                "endpoint_sig": "POST /finance/expenses",
                "permission": "expense.create",
                "scope": "tenant",
                "idempotency": "required",
                "errors": [400, 401, 403],
                "bind": {"kind": "create", "entity": "Expense"},
            },
        ],
    }
    ops_path = bundle_dir / "operations.json"
    ops_path.write_text(json.dumps(operations, indent=2))

    return {
        "bundle_path": bundle_dir,
        "release_id": "20260101-120000",
        "manifest_path": manifest_path,
        "ops_path": ops_path,
    }


@pytest.fixture
def bundle_v2(tmp_path):
    """Create a v2 bundle with different operations."""
    bundle_dir = tmp_path / "bundles" / "releases" / "20260115-140000" / "finance-pilot"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest
    manifest = {
        "name": "finance-pilot",
        "version": "2.0.0",
        "created_at": "2026-01-15T14:00:00Z",
        "contracts": [],
    }
    manifest_path = bundle_dir / "bundle.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Create operations with additional operation
    operations = {
        "operations_schema_version": "1.0",
        "operations": [
            {
                "operation_id": "create_expense",
                "path": "/finance/expenses",
                "method": "POST",
                "endpoint_sig": "POST /finance/expenses",
                "permission": "expense.create",
                "scope": "tenant",
                "idempotency": "required",
                "errors": [400, 401, 403],
                "bind": {"kind": "create", "entity": "Expense"},
            },
            {
                "operation_id": "list_expenses",
                "path": "/finance/expenses",
                "method": "GET",
                "endpoint_sig": "GET /finance/expenses",
                "permission": "expense.read",
                "scope": "tenant",
                "idempotency": "none",
                "errors": [400, 401, 403],
                "bind": {"kind": "read", "entity": "Expense"},
            },
        ],
    }
    ops_path = bundle_dir / "operations.json"
    ops_path.write_text(json.dumps(operations, indent=2))

    return {
        "bundle_path": bundle_dir,
        "release_id": "20260115-140000",
        "manifest_path": manifest_path,
        "ops_path": ops_path,
    }


class TestActiveRuntimeSnapshot:
    """Tests for ActiveRuntimeSnapshot management."""

    def test_set_and_get_snapshot(self):
        """Should store and retrieve snapshot."""
        snapshot = ActiveRuntimeSnapshot(
            institution_id="test-inst",
            active_release_id="20260101-120000",
            bundle_path="/path/to/bundle",
            manifest_hash="abc123",
            operations_hash="def456",
            loaded_at="2026-01-21T10:00:00Z",
            reload_reason="boot",
        )

        set_active_snapshot(snapshot)
        retrieved = get_active_snapshot("test-inst")

        assert retrieved is not None
        assert retrieved.institution_id == "test-inst"
        assert retrieved.active_release_id == "20260101-120000"
        assert retrieved.manifest_hash == "abc123"
        assert retrieved.reload_reason == "boot"

    def test_get_snapshot_returns_none_when_not_set(self):
        """Should return None for non-existent snapshot."""
        snapshot = get_active_snapshot("non-existent")
        assert snapshot is None

    def test_clear_snapshot(self):
        """Should clear snapshot."""
        snapshot = ActiveRuntimeSnapshot(
            institution_id="test-inst",
            active_release_id="20260101-120000",
            bundle_path="/path",
            manifest_hash="abc",
            operations_hash="def",
            loaded_at="2026-01-21T10:00:00Z",
        )
        set_active_snapshot(snapshot)

        clear_active_snapshot("test-inst")
        assert get_active_snapshot("test-inst") is None

    def test_to_dict(self):
        """Should convert snapshot to dict."""
        snapshot = ActiveRuntimeSnapshot(
            institution_id="test-inst",
            active_release_id="20260101-120000",
            bundle_path="/path/to/bundle",
            manifest_hash="abc123",
            operations_hash="def456",
            loaded_at="2026-01-21T10:00:00Z",
            reload_reason="pin_applied",
        )

        d = snapshot.to_dict()
        assert d["institution_id"] == "test-inst"
        assert d["active_release_id"] == "20260101-120000"
        assert d["reload_reason"] == "pin_applied"


class TestCreateSnapshotFromBundle:
    """Tests for create_snapshot_from_bundle()."""

    def test_creates_snapshot_from_valid_bundle(self, bundle_v1):
        """Should create snapshot from valid bundle."""
        snapshot, error_code, error_msg = create_snapshot_from_bundle(
            institution_id="test-inst",
            bundle_path=bundle_v1["bundle_path"],
            reason="boot",
        )

        assert error_code is None
        assert error_msg is None
        assert snapshot is not None
        assert snapshot.institution_id == "test-inst"
        assert snapshot.active_release_id == "20260101-120000"
        assert snapshot.manifest_hash is not None
        assert snapshot.operations_hash is not None
        assert snapshot.reload_reason == "boot"

    def test_returns_error_for_missing_bundle(self, tmp_path):
        """Should return error for non-existent bundle."""
        snapshot, error_code, error_msg = create_snapshot_from_bundle(
            institution_id="test-inst",
            bundle_path=tmp_path / "non-existent",
            reason="boot",
        )

        assert snapshot is None
        assert error_code == RUNTIME_RELOAD_BUNDLE_MISSING
        assert "does not exist" in error_msg

    def test_returns_error_for_missing_manifest(self, tmp_path):
        """Should return error when manifest is missing."""
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir(parents=True)

        snapshot, error_code, error_msg = create_snapshot_from_bundle(
            institution_id="test-inst",
            bundle_path=bundle_dir,
            reason="boot",
        )

        assert snapshot is None
        assert error_code == RUNTIME_RELOAD_BUNDLE_MISSING
        assert "Manifest" in error_msg


class TestReloadActiveRuntime:
    """Tests for reload_active_runtime() - main hot-swap function."""

    def test_reload_updates_operations_registry(self, bundle_v1, bundle_v2, monkeypatch):
        """Should update operations registry after reload."""
        # Start with v1
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_v1["bundle_path"]))

        success, error_code, error_msg = reload_active_runtime(
            institution_id=None,
            reason="boot",
            bundle_path=bundle_v1["bundle_path"],
        )

        assert success is True, f"Failed to reload v1: {error_code} - {error_msg}"
        ops = get_operations(None)
        assert ops is not None
        assert len(ops.operations) == 1
        assert ops.operations[0].operation_id == "create_expense"

        # Now reload with v2
        success, error_code, error_msg = reload_active_runtime(
            institution_id=None,
            reason="pin_applied",
            bundle_path=bundle_v2["bundle_path"],
        )

        assert success is True, f"Failed to reload v2: {error_code} - {error_msg}"
        ops = get_operations(None)
        assert ops is not None
        assert len(ops.operations) == 2  # v2 has 2 operations

    def test_reload_updates_snapshot(self, bundle_v1, bundle_v2):
        """Should update ActiveRuntimeSnapshot after reload."""
        # Reload v1
        reload_active_runtime(
            institution_id="test-inst",
            reason="boot",
            bundle_path=bundle_v1["bundle_path"],
        )

        snapshot1 = get_active_snapshot("test-inst")
        assert snapshot1 is not None
        hash1 = snapshot1.manifest_hash

        # Reload v2
        reload_active_runtime(
            institution_id="test-inst",
            reason="pin_applied",
            bundle_path=bundle_v2["bundle_path"],
        )

        snapshot2 = get_active_snapshot("test-inst")
        assert snapshot2 is not None
        assert snapshot2.manifest_hash != hash1  # Different bundle -> different hash
        assert snapshot2.reload_reason == "pin_applied"

    def test_reload_invalidates_openapi_cache(self, bundle_v1):
        """Should invalidate OpenAPI cache after reload."""
        # Create mock app
        mock_app = MagicMock()
        mock_app.openapi_schema = {"paths": {}}

        success, _, _ = reload_active_runtime(
            institution_id=None,
            reason="pin_applied",
            bundle_path=bundle_v1["bundle_path"],
            app=mock_app,
        )

        assert success is True
        assert mock_app.openapi_schema is None

    def test_reload_returns_error_for_missing_bundle(self, tmp_path):
        """Should return error for non-existent bundle."""
        success, error_code, error_msg = reload_active_runtime(
            institution_id=None,
            reason="pin_applied",
            bundle_path=tmp_path / "non-existent",
        )

        assert success is False
        assert error_code == RUNTIME_RELOAD_BUNDLE_MISSING


class TestReloadOnBoot:
    """Tests for reload_on_boot() - boot-time initialization."""

    def test_initializes_snapshot_on_boot(self, bundle_v1, monkeypatch):
        """Should initialize snapshot on boot."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_v1["bundle_path"]))

        success, error_code, error_msg = reload_on_boot(
            bundle_path=bundle_v1["bundle_path"],
            institution_id="test-inst",
        )

        assert success is True
        snapshot = get_active_snapshot("test-inst")
        assert snapshot is not None
        assert snapshot.reload_reason == "boot"

    def test_boot_without_explicit_path_uses_env(self, bundle_v1, monkeypatch):
        """Should use ENGINE_BUNDLE_PATH when bundle_path not provided."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_v1["bundle_path"]))

        success, error_code, error_msg = reload_on_boot()

        assert success is True
        snapshot = get_active_snapshot(None)
        assert snapshot is not None


class TestDynamicLookupIntegration:
    """Tests for dynamic lookup after hot-swap."""

    def test_handler_sees_updated_operation_after_reload(self, bundle_v1, bundle_v2):
        """Handler should resolve operation from current registry after reload."""

        # Load v1
        reload_active_runtime(
            institution_id=None,
            reason="boot",
            bundle_path=bundle_v1["bundle_path"],
        )

        # Lookup operation
        op = get_operation_by_endpoint_sig(None, "POST /finance/expenses")
        assert op is not None
        assert op.operation_id == "create_expense"

        # GET /finance/expenses should NOT exist in v1
        op_get = get_operation_by_endpoint_sig(None, "GET /finance/expenses")
        assert op_get is None

        # Reload v2
        reload_active_runtime(
            institution_id=None,
            reason="pin_applied",
            bundle_path=bundle_v2["bundle_path"],
        )

        # Now GET /finance/expenses SHOULD exist
        op_get = get_operation_by_endpoint_sig(None, "GET /finance/expenses")
        assert op_get is not None
        assert op_get.operation_id == "list_expenses"


class TestRuntimeReloadedLedgerEvent:
    """Tests for RUNTIME_RELOADED ledger events."""

    def test_emits_runtime_reloaded_event(self, bundle_v1, tmp_path, monkeypatch):
        """Should emit RUNTIME_RELOADED event on reload."""
        institution_id = "test-inst-events"

        # Set up institution-specific ledger
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))

        # Reload with institution_id
        success, _, _ = reload_active_runtime(
            institution_id=institution_id,
            reason="pin_applied",
            bundle_path=bundle_v1["bundle_path"],
        )

        assert success is True

        # Check ledger for event
        from engine.core.ledger import get_ledger_for_institution
        ledger = get_ledger_for_institution(institution_id)

        events = []
        if ledger._path.exists():
            with open(ledger._path, "r") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))

        # Find RUNTIME_RELOADED event
        reload_events = [e for e in events if e.get("event_type") == "RUNTIME_RELOADED"]
        assert len(reload_events) >= 1

        event = reload_events[-1]
        assert event["payload"]["reason"] == "pin_applied"
        assert "manifest_hash" in event["payload"]
        assert "operations_hash" in event["payload"]

    def test_no_event_on_boot(self, bundle_v1, tmp_path, monkeypatch):
        """Should NOT emit event on boot (only on hot-swap)."""
        institution_id = "test-inst-boot"
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))

        # Use reload_on_boot (not reload_active_runtime)
        success, _, _ = reload_on_boot(
            bundle_path=bundle_v1["bundle_path"],
            institution_id=institution_id,
        )

        assert success is True

        # Check ledger - should have no RUNTIME_RELOADED events
        from engine.core.ledger import get_ledger_for_institution
        ledger = get_ledger_for_institution(institution_id)

        events = []
        if ledger._path.exists():
            with open(ledger._path, "r") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))

        reload_events = [e for e in events if e.get("event_type") == "RUNTIME_RELOADED"]
        assert len(reload_events) == 0


class TestMultiDeptBundle:
    """Tests for multi-dept bundle reload."""

    def test_reload_multi_dept_bundle(self, tmp_path):
        """Should reload operations for each department."""
        bundle_dir = tmp_path / "bundles" / "releases" / "20260120-100000" / "multi-pilot"
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # Create manifest
        manifest = {
            "name": "multi-pilot",
            "version": "1.0.0",
            "mode": "multi",
            "created_at": "2026-01-20T10:00:00Z",
        }
        (bundle_dir / "bundle.manifest.json").write_text(json.dumps(manifest, indent=2))

        # Create departments
        for dept_id in ["finance", "support"]:
            dept_dir = bundle_dir / "departments" / dept_id
            dept_dir.mkdir(parents=True, exist_ok=True)

            operations = {
                "operations_schema_version": "1.0",
                "dept_id": dept_id,
                "operations": [
                    {
                        "operation_id": f"{dept_id}_create",
                        "path": f"/{dept_id}/items",
                        "method": "POST",
                        "endpoint_sig": f"POST /{dept_id}/items",
                        "permission": f"{dept_id}.create",
                        "scope": "tenant",
                        "idempotency": "required",
                        "errors": [400, 401, 403],
                        "bind": {"kind": "create", "entity": "Item"},
                    },
                ],
            }
            (dept_dir / "operations.json").write_text(json.dumps(operations, indent=2))

        # Reload
        success, error_code, error_msg = reload_active_runtime(
            institution_id=None,
            reason="boot",
            bundle_path=bundle_dir,
        )

        assert success is True

        # Check both depts have operations loaded
        finance_ops = get_operations("finance")
        assert finance_ops is not None
        assert len(finance_ops.operations) == 1
        assert finance_ops.operations[0].operation_id == "finance_create"

        support_ops = get_operations("support")
        assert support_ops is not None
        assert len(support_ops.operations) == 1
        assert support_ops.operations[0].operation_id == "support_create"


class TestBundleSwapScenario:
    """End-to-end tests simulating bundle swap scenario."""

    def test_bundle_swap_updates_all_state(self, bundle_v1, bundle_v2):
        """Simulating: Deploy v1 -> Pin v1 -> Deploy v2 -> Pin v2 (swap)."""
        institution_id = "test-inst-swap"

        # Step 1: Boot with v1
        reload_active_runtime(
            institution_id=institution_id,
            reason="boot",
            bundle_path=bundle_v1["bundle_path"],
        )

        snapshot_v1 = get_active_snapshot(institution_id)
        ops_v1 = get_operations(None)

        assert snapshot_v1.active_release_id == "20260101-120000"
        assert len(ops_v1.operations) == 1

        # Step 2: Swap to v2 (simulating pin_applied)
        reload_active_runtime(
            institution_id=institution_id,
            reason="pin_applied",
            bundle_path=bundle_v2["bundle_path"],
        )

        snapshot_v2 = get_active_snapshot(institution_id)
        ops_v2 = get_operations(None)

        # Verify state changed
        assert snapshot_v2.active_release_id == "20260115-140000"
        assert snapshot_v2.manifest_hash != snapshot_v1.manifest_hash
        assert len(ops_v2.operations) == 2  # v2 has additional operation

    def test_rollback_restores_previous_state(self, bundle_v1, bundle_v2):
        """Simulating: v1 active -> v2 deployed -> v2 fails -> rollback to v1."""
        institution_id = "test-inst-rollback"

        # Boot with v1
        reload_active_runtime(
            institution_id=institution_id,
            reason="boot",
            bundle_path=bundle_v1["bundle_path"],
        )

        snapshot_v1 = get_active_snapshot(institution_id)

        # Failed deploy of v2 - rollback to v1
        reload_active_runtime(
            institution_id=institution_id,
            reason="rollback",
            bundle_path=bundle_v1["bundle_path"],  # Rollback to v1
        )

        snapshot_after_rollback = get_active_snapshot(institution_id)

        # Should be back to v1
        assert snapshot_after_rollback.active_release_id == snapshot_v1.active_release_id
        assert snapshot_after_rollback.reload_reason == "rollback"
