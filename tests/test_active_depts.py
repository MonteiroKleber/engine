"""Tests for active_depts module (Etapa 5.1 - Multi-Dept Activation Model).

Tests cover:
- Storage: active_depts.json per institution
- Fallback: If file doesn't exist, all bundle depts are considered active
- Events: DEPT_ACTIVATED, DEPT_DEACTIVATED emitted to ledger
- Determinism: Array always sorted alphabetically by dept_id
- Isolation: 2 institutions × 2 depts
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from engine.core.active_depts import (
    ActiveDeptEntry,
    ActiveDeptsState,
    ACTIVE_DEPTS_SCHEMA_VERSION,
    get_active_depts_path,
    get_active_depts_state,
    get_active_depts,
    get_installed_depts,
    is_dept_active,
    is_dept_installed,
    activate_dept,
    deactivate_dept,
    get_depts_summary,
    get_cached_active_depts,
    invalidate_active_depts_cache,
    reset_active_depts_cache,
)
from engine.core.errors import (
    DEPT_NOT_INSTALLED,
    DEPT_NOT_ACTIVE,
    DEPT_ALREADY_ACTIVE,
    DEPT_ALREADY_INACTIVE,
    CANNOT_DEACTIVATE_LAST_DEPT,
)


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset cache before and after each test."""
    reset_active_depts_cache()
    yield
    reset_active_depts_cache()


@pytest.fixture
def institution_root(tmp_path, monkeypatch):
    """Set up a temp institution root."""
    data_root = tmp_path / "data"
    inst_id = "test-inst-001"
    inst_root = data_root / "institutions" / inst_id
    inst_root.mkdir(parents=True)

    # Patch get_institution_root to return our temp path
    monkeypatch.setattr(
        "engine.core.active_depts.get_institution_root",
        lambda i: inst_root if i == inst_id else data_root / "institutions" / i,
    )

    return inst_root, inst_id


@pytest.fixture
def mock_bundle_context():
    """Create a mock bundle context for multi-dept mode."""
    ctx = MagicMock()
    ctx.mode = "multi"
    ctx.departments = {"finance": MagicMock(), "support": MagicMock(), "hr": MagicMock()}
    return ctx


@pytest.fixture
def mock_bundle(monkeypatch, mock_bundle_context):
    """Mock the bundle context loader."""
    # Must import the actual module, not the package
    import sys
    # Direct import of the module file
    lb_module = sys.modules.get("engine.loader.load_bundle")
    if lb_module is None:
        from engine.loader import load_bundle as _
        lb_module = sys.modules["engine.loader.load_bundle"]

    original = lb_module.get_bundle_context
    lb_module.get_bundle_context = lambda: mock_bundle_context
    yield mock_bundle_context
    lb_module.get_bundle_context = original


@pytest.fixture
def mock_emit_event(monkeypatch):
    """Mock event emission to ledger."""
    import engine.core.active_depts as ad_module

    events = []
    def mock_emit(inst, event_type, dept_id, actor_id, extra=None):
        events.append({
            "institution_id": inst,
            "event_type": event_type,
            "dept_id": dept_id,
            "actor_id": actor_id,
            "extra": extra,
        })

    monkeypatch.setattr(ad_module, "_emit_dept_event", mock_emit)
    return events


class TestActiveDeptEntry:
    """Test ActiveDeptEntry dataclass."""

    def test_to_dict(self):
        """Convert entry to dictionary."""
        entry = ActiveDeptEntry(
            dept_id="finance",
            activated_at="2026-01-20T18:00:00+00:00",
            activated_by="actor-001",
            source_bundle="multi-pilot",
            pinned_contract_sha256="SHA256:abc123",
        )
        d = entry.to_dict()
        assert d["dept_id"] == "finance"
        assert d["activated_at"] == "2026-01-20T18:00:00+00:00"
        assert d["activated_by"] == "actor-001"
        assert d["source_bundle"] == "multi-pilot"
        assert d["pinned_contract_sha256"] == "SHA256:abc123"

    def test_from_dict(self):
        """Create entry from dictionary."""
        d = {
            "dept_id": "support",
            "activated_at": "2026-01-20T19:00:00+00:00",
            "activated_by": "actor-002",
            "source_bundle": "multi-pilot",
        }
        entry = ActiveDeptEntry.from_dict(d)
        assert entry.dept_id == "support"
        assert entry.activated_at == "2026-01-20T19:00:00+00:00"
        assert entry.activated_by == "actor-002"
        assert entry.source_bundle == "multi-pilot"
        assert entry.pinned_contract_sha256 is None


class TestActiveDeptsState:
    """Test ActiveDeptsState dataclass."""

    def test_to_dict_sorted(self):
        """to_dict should sort entries by dept_id."""
        state = ActiveDeptsState(
            schema_version="1.0",
            updated_at="2026-01-20T18:00:00+00:00",
            updated_by="actor-001",
            active_depts=[
                ActiveDeptEntry(
                    dept_id="support",
                    activated_at="2026-01-20T18:00:00+00:00",
                    activated_by="actor-001",
                    source_bundle="bundle-1",
                ),
                ActiveDeptEntry(
                    dept_id="finance",
                    activated_at="2026-01-20T17:00:00+00:00",
                    activated_by="actor-001",
                    source_bundle="bundle-1",
                ),
            ],
        )
        d = state.to_dict()
        # Should be sorted: finance before support
        assert d["active_depts"][0]["dept_id"] == "finance"
        assert d["active_depts"][1]["dept_id"] == "support"


class TestGetActiveDepts:
    """Test get_active_depts and fallback behavior."""

    def test_no_file_returns_bundle_depts(self, institution_root, mock_bundle):
        """When no active_depts.json exists, fallback to bundle depts."""
        inst_root, inst_id = institution_root

        depts = get_active_depts(inst_id)
        # Should return all bundle depts, sorted
        assert depts == ["finance", "hr", "support"]

    def test_file_exists_uses_file(self, institution_root):
        """When active_depts.json exists, use it."""
        inst_root, inst_id = institution_root

        # Create active_depts.json with only finance and support active
        state = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-001",
            "active_depts": [
                {
                    "dept_id": "finance",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
                {
                    "dept_id": "support",
                    "activated_at": "2026-01-20T17:30:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
            ],
        }
        (inst_root / "active_depts.json").write_text(json.dumps(state))

        depts = get_active_depts(inst_id)
        assert depts == ["finance", "support"]  # hr not included

    def test_is_dept_active(self, institution_root):
        """Test is_dept_active function."""
        inst_root, inst_id = institution_root

        state = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-001",
            "active_depts": [
                {
                    "dept_id": "finance",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
            ],
        }
        (inst_root / "active_depts.json").write_text(json.dumps(state))

        assert is_dept_active(inst_id, "finance") is True
        assert is_dept_active(inst_id, "support") is False


class TestActivateDept:
    """Test activate_dept function."""

    def test_activate_creates_file_on_first_call(
        self, institution_root, mock_bundle, mock_emit_event
    ):
        """First activation creates active_depts.json with all installed depts."""
        inst_root, inst_id = institution_root

        # Set up bundle symlink for _get_current_bundle_name
        bundles_dir = inst_root / "bundles"
        bundles_dir.mkdir()
        bundle_dir = bundles_dir / "multi-pilot"
        bundle_dir.mkdir()
        (bundles_dir / "CURRENT").symlink_to(bundle_dir)

        success, error_code, error_msg = activate_dept(
            institution_id=inst_id,
            dept_id="finance",
            actor_id="actor-001",
        )

        assert success is True
        assert error_code is None

        # File should now exist
        path = inst_root / "active_depts.json"
        assert path.exists()

        # All installed depts should be in the file
        data = json.loads(path.read_text())
        dept_ids = [d["dept_id"] for d in data["active_depts"]]
        assert sorted(dept_ids) == ["finance", "hr", "support"]

        # Event should be emitted
        assert len(mock_emit_event) == 1
        assert mock_emit_event[0]["event_type"] == "DEPT_ACTIVATED"

    def test_activate_dept_not_installed(self, institution_root, mock_bundle):
        """Cannot activate dept not installed in bundle."""
        inst_root, inst_id = institution_root

        success, error_code, error_msg = activate_dept(
            institution_id=inst_id,
            dept_id="unknown-dept",
            actor_id="actor-001",
        )

        assert success is False
        assert error_code == DEPT_NOT_INSTALLED
        assert "not installed" in error_msg.lower()

    def test_activate_already_active(self, institution_root, mock_bundle):
        """Cannot activate dept that is already active."""
        inst_root, inst_id = institution_root

        # Create file with finance already active
        state = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-001",
            "active_depts": [
                {
                    "dept_id": "finance",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
            ],
        }
        (inst_root / "active_depts.json").write_text(json.dumps(state))

        success, error_code, error_msg = activate_dept(
            institution_id=inst_id,
            dept_id="finance",
            actor_id="actor-001",
        )

        assert success is False
        assert error_code == DEPT_ALREADY_ACTIVE


class TestDeactivateDept:
    """Test deactivate_dept function."""

    def test_deactivate_removes_from_file(
        self, institution_root, mock_bundle, mock_emit_event
    ):
        """Deactivating a dept removes it from active_depts.json."""
        inst_root, inst_id = institution_root

        # Set up bundle symlink
        bundles_dir = inst_root / "bundles"
        bundles_dir.mkdir()
        bundle_dir = bundles_dir / "multi-pilot"
        bundle_dir.mkdir()
        (bundles_dir / "CURRENT").symlink_to(bundle_dir)

        # Create file with finance and support active
        state = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-001",
            "active_depts": [
                {
                    "dept_id": "finance",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
                {
                    "dept_id": "support",
                    "activated_at": "2026-01-20T17:30:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
            ],
        }
        (inst_root / "active_depts.json").write_text(json.dumps(state))

        success, error_code, error_msg = deactivate_dept(
            institution_id=inst_id,
            dept_id="finance",
            actor_id="actor-001",
            reason="Test deactivation",
        )

        assert success is True

        # finance should no longer be active
        depts = get_active_depts(inst_id)
        assert "finance" not in depts
        assert "support" in depts

        # Event should be emitted
        assert len(mock_emit_event) == 1
        assert mock_emit_event[0]["event_type"] == "DEPT_DEACTIVATED"

    def test_cannot_deactivate_last_dept(self, institution_root, mock_bundle):
        """Cannot deactivate the last active dept."""
        inst_root, inst_id = institution_root

        # Create file with only finance active
        state = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-001",
            "active_depts": [
                {
                    "dept_id": "finance",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
            ],
        }
        (inst_root / "active_depts.json").write_text(json.dumps(state))

        success, error_code, error_msg = deactivate_dept(
            institution_id=inst_id,
            dept_id="finance",
            actor_id="actor-001",
        )

        assert success is False
        assert error_code == CANNOT_DEACTIVATE_LAST_DEPT

    def test_deactivate_not_active(self, institution_root, mock_bundle):
        """Cannot deactivate dept that is not active."""
        inst_root, inst_id = institution_root

        # Create file with only finance active
        state = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-001",
            "active_depts": [
                {
                    "dept_id": "finance",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
            ],
        }
        (inst_root / "active_depts.json").write_text(json.dumps(state))

        success, error_code, error_msg = deactivate_dept(
            institution_id=inst_id,
            dept_id="support",
            actor_id="actor-001",
        )

        assert success is False
        assert error_code == DEPT_ALREADY_INACTIVE


class TestDeptsSummary:
    """Test get_depts_summary function."""

    def test_summary_with_file(self, institution_root, mock_bundle):
        """Summary shows installed, active, and inactive depts."""
        inst_root, inst_id = institution_root

        # Create file with finance and support active (hr inactive)
        state = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-001",
            "active_depts": [
                {
                    "dept_id": "finance",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
                {
                    "dept_id": "support",
                    "activated_at": "2026-01-20T17:30:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
            ],
        }
        (inst_root / "active_depts.json").write_text(json.dumps(state))

        summary = get_depts_summary(inst_id)

        assert summary["installed"] == ["finance", "hr", "support"]
        assert summary["active"] == ["finance", "support"]
        assert summary["inactive"] == ["hr"]


class TestCache:
    """Test caching behavior."""

    def test_cache_invalidation(self, institution_root, mock_bundle):
        """Cache should be invalidated on request."""
        inst_root, inst_id = institution_root

        # Create file
        state = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-001",
            "active_depts": [
                {
                    "dept_id": "finance",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "multi-pilot",
                },
            ],
        }
        (inst_root / "active_depts.json").write_text(json.dumps(state))

        # Get cached value
        depts1 = get_cached_active_depts(inst_id)
        assert depts1 == ["finance"]

        # Update file directly
        state["active_depts"].append({
            "dept_id": "support",
            "activated_at": "2026-01-20T18:30:00+00:00",
            "activated_by": "actor-001",
            "source_bundle": "multi-pilot",
        })
        (inst_root / "active_depts.json").write_text(json.dumps(state))

        # Cache should still return old value
        depts2 = get_cached_active_depts(inst_id)
        assert depts2 == ["finance"]

        # After invalidation, should return new value
        invalidate_active_depts_cache(inst_id)
        depts3 = get_cached_active_depts(inst_id)
        assert depts3 == ["finance", "support"]


class TestMultiInstitutionIsolation:
    """Test isolation between institutions."""

    def test_two_institutions_isolated(self, tmp_path, monkeypatch):
        """Two institutions should have independent active depts."""
        data_root = tmp_path / "data"

        inst1_id = "inst-001"
        inst2_id = "inst-002"

        inst1_root = data_root / "institutions" / inst1_id
        inst2_root = data_root / "institutions" / inst2_id
        inst1_root.mkdir(parents=True)
        inst2_root.mkdir(parents=True)

        def mock_get_root(i):
            if i == inst1_id:
                return inst1_root
            return inst2_root

        monkeypatch.setattr(
            "engine.core.active_depts.get_institution_root",
            mock_get_root,
        )

        # Inst1: only finance active
        state1 = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-001",
            "active_depts": [
                {
                    "dept_id": "finance",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-001",
                    "source_bundle": "bundle-1",
                },
            ],
        }
        (inst1_root / "active_depts.json").write_text(json.dumps(state1))

        # Inst2: only support active
        state2 = {
            "schema_version": "1.0",
            "updated_at": "2026-01-20T18:00:00+00:00",
            "updated_by": "actor-002",
            "active_depts": [
                {
                    "dept_id": "support",
                    "activated_at": "2026-01-20T17:00:00+00:00",
                    "activated_by": "actor-002",
                    "source_bundle": "bundle-2",
                },
            ],
        }
        (inst2_root / "active_depts.json").write_text(json.dumps(state2))

        # Verify isolation
        depts1 = get_active_depts(inst1_id)
        depts2 = get_active_depts(inst2_id)

        assert depts1 == ["finance"]
        assert depts2 == ["support"]

        # Cross-checks
        assert is_dept_active(inst1_id, "finance") is True
        assert is_dept_active(inst1_id, "support") is False
        assert is_dept_active(inst2_id, "finance") is False
        assert is_dept_active(inst2_id, "support") is True
