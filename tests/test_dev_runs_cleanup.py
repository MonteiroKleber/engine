"""Tests for Dev Runs Cleanup."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from engine.pipeline.registry import (
    DevRunsRegistry,
    RegistryEvent,
    DevRunInfo,
    EVENT_DEV_RUN_CREATED,
    EVENT_DEV_RUN_DELETED,
    reset_registry,
)
from engine.pipeline.cleanup import (
    cleanup_dev_runs,
    determine_runs_to_delete,
    CleanupResult,
    DEV_RUNS_CLEANUP_FAILED,
)


@pytest.fixture
def registry_path(tmp_path):
    """Create a temporary registry path."""
    return tmp_path / "var" / "dev_runs_registry.jsonl"


@pytest.fixture
def registry(registry_path):
    """Create a fresh registry for testing."""
    reset_registry()
    return DevRunsRegistry(registry_path)


@pytest.fixture
def bundles_root(tmp_path):
    """Create bundles root directory."""
    root = tmp_path / "bundles"
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_run_with_timestamp(registry, run_id: str, bundle_name: str, timestamp: str, bundle_path: str):
    """Helper to create a run with specific timestamp."""
    event = RegistryEvent(
        event_type=EVENT_DEV_RUN_CREATED,
        run_id=run_id,
        bundle_name=bundle_name,
        timestamp=timestamp,
        bundle_path=bundle_path,
    )
    registry.append_event(event)


def create_run_dir(bundles_root: Path, run_id: str, bundle_name: str) -> Path:
    """Helper to create run directory structure."""
    run_dir = bundles_root / "dev-runs" / run_id / bundle_name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text("{}")
    return run_dir.parent


class TestDetermineRunsToDelete:
    """Test determine_runs_to_delete function."""

    def test_no_runs_returns_empty(self):
        """No runs should return empty list."""
        to_delete, ttl_count, max_count = determine_runs_to_delete(
            [], ttl_hours=24, max_runs=200
        )

        assert to_delete == []
        assert ttl_count == 0
        assert max_count == 0

    def test_ttl_expired_runs_deleted(self):
        """Runs older than TTL should be marked for deletion."""
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(hours=25)).isoformat()
        new_time = now.isoformat()

        runs = [
            DevRunInfo("run-old", "bundle-old", old_time),
            DevRunInfo("run-new", "bundle-new", new_time),
        ]

        to_delete, ttl_count, max_count = determine_runs_to_delete(
            runs, ttl_hours=24, max_runs=200
        )

        assert len(to_delete) == 1
        assert to_delete[0].run_id == "run-old"
        assert ttl_count == 1
        assert max_count == 0

    def test_max_runs_exceeded_deletes_oldest(self):
        """When over max_runs, delete oldest (after TTL)."""
        now = datetime.now(timezone.utc)

        # Create 5 runs, all within TTL
        runs = []
        for i in range(5):
            ts = (now - timedelta(hours=i)).isoformat()
            runs.append(DevRunInfo(f"run-{i}", f"bundle-{i}", ts))

        # Max 3 runs - should delete 2 oldest
        to_delete, ttl_count, max_count = determine_runs_to_delete(
            runs, ttl_hours=24, max_runs=3
        )

        assert len(to_delete) == 2
        assert ttl_count == 0
        assert max_count == 2
        # Should delete run-4 and run-3 (oldest)
        deleted_ids = [r.run_id for r in to_delete]
        assert "run-4" in deleted_ids
        assert "run-3" in deleted_ids

    def test_ttl_and_max_combined(self):
        """Both TTL and max_runs should be applied."""
        now = datetime.now(timezone.utc)

        runs = [
            # Old run (TTL expired)
            DevRunInfo("run-old", "bundle-old", (now - timedelta(hours=30)).isoformat()),
            # Recent runs
            DevRunInfo("run-1", "bundle-1", (now - timedelta(hours=5)).isoformat()),
            DevRunInfo("run-2", "bundle-2", (now - timedelta(hours=4)).isoformat()),
            DevRunInfo("run-3", "bundle-3", (now - timedelta(hours=3)).isoformat()),
            DevRunInfo("run-4", "bundle-4", (now - timedelta(hours=2)).isoformat()),
        ]

        # TTL=24h, max=2 runs
        to_delete, ttl_count, max_count = determine_runs_to_delete(
            runs, ttl_hours=24, max_runs=2
        )

        # Should delete: run-old (TTL), run-1 and run-2 (max exceeded)
        assert ttl_count == 1
        assert max_count == 2
        assert len(to_delete) == 3

    def test_deterministic_order(self):
        """Deletion order should be deterministic."""
        now = datetime.now(timezone.utc)

        runs = [
            DevRunInfo("run-a", "bundle-a", (now - timedelta(hours=3)).isoformat()),
            DevRunInfo("run-b", "bundle-b", (now - timedelta(hours=2)).isoformat()),
            DevRunInfo("run-c", "bundle-c", (now - timedelta(hours=1)).isoformat()),
        ]

        # Run multiple times - order should be same
        results = []
        for _ in range(3):
            to_delete, _, _ = determine_runs_to_delete(runs, ttl_hours=24, max_runs=1)
            results.append([r.run_id for r in to_delete])

        assert all(r == results[0] for r in results)


class TestCleanupDevRuns:
    """Test cleanup_dev_runs function."""

    def test_dry_run_does_not_delete(self, registry, bundles_root):
        """dry_run=True should not actually delete."""
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(hours=30)).isoformat()

        create_run_with_timestamp(
            registry, "run-old", "bundle-old", old_time,
            str(bundles_root / "dev-runs" / "run-old" / "bundle-old")
        )
        run_dir = create_run_dir(bundles_root, "run-old", "bundle-old")

        result = cleanup_dev_runs(
            dry_run=True,
            registry=registry,
            ttl_hours=24,
            max_runs=200,
            bundles_root=str(bundles_root),
        )

        assert result.success is True
        assert result.dry_run is True
        assert "run-old" in result.deleted_run_ids
        # Directory should still exist
        assert run_dir.exists()

    def test_real_cleanup_deletes_directory(self, registry, bundles_root):
        """dry_run=False should delete directory and emit event."""
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(hours=30)).isoformat()

        create_run_with_timestamp(
            registry, "run-old", "bundle-old", old_time,
            str(bundles_root / "dev-runs" / "run-old" / "bundle-old")
        )
        run_dir = create_run_dir(bundles_root, "run-old", "bundle-old")

        result = cleanup_dev_runs(
            dry_run=False,
            registry=registry,
            ttl_hours=24,
            max_runs=200,
            bundles_root=str(bundles_root),
        )

        assert result.success is True
        assert result.dry_run is False
        assert "run-old" in result.deleted_run_ids
        # Directory should be deleted
        assert not run_dir.exists()

    def test_real_cleanup_emits_deleted_event(self, registry, bundles_root, registry_path):
        """Real cleanup should emit DEV_RUN_DELETED event."""
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(hours=30)).isoformat()

        create_run_with_timestamp(
            registry, "run-old", "bundle-old", old_time,
            str(bundles_root / "dev-runs" / "run-old" / "bundle-old")
        )
        create_run_dir(bundles_root, "run-old", "bundle-old")

        cleanup_dev_runs(
            dry_run=False,
            registry=registry,
            ttl_hours=24,
            max_runs=200,
            bundles_root=str(bundles_root),
        )

        # Check registry has DELETE event
        events = registry.read_events()
        deleted_events = [e for e in events if e.event_type == EVENT_DEV_RUN_DELETED]
        assert len(deleted_events) == 1
        assert deleted_events[0].run_id == "run-old"

    def test_cleanup_respects_already_deleted(self, registry, bundles_root):
        """Cleanup should skip already-deleted runs."""
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(hours=30)).isoformat()

        # Create and then delete a run
        create_run_with_timestamp(
            registry, "run-old", "bundle-old", old_time,
            str(bundles_root / "dev-runs" / "run-old" / "bundle-old")
        )
        registry.emit_deleted("run-old", "bundle-old")

        result = cleanup_dev_runs(
            dry_run=False,
            registry=registry,
            ttl_hours=24,
            max_runs=200,
            bundles_root=str(bundles_root),
        )

        # Should not attempt to delete again
        assert result.success is True
        assert "run-old" not in result.deleted_run_ids

    def test_cleanup_handles_missing_directory(self, registry, bundles_root):
        """Cleanup should handle missing directories gracefully."""
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(hours=30)).isoformat()

        # Create run in registry but don't create directory
        create_run_with_timestamp(
            registry, "run-old", "bundle-old", old_time,
            str(bundles_root / "dev-runs" / "run-old" / "bundle-old")
        )

        result = cleanup_dev_runs(
            dry_run=False,
            registry=registry,
            ttl_hours=24,
            max_runs=200,
            bundles_root=str(bundles_root),
        )

        # Should succeed even if directory doesn't exist
        assert result.success is True
        assert "run-old" in result.deleted_run_ids
        # No paths deleted since directory didn't exist
        assert len(result.deleted_paths) == 0

    def test_cleanup_multiple_runs(self, registry, bundles_root):
        """Cleanup should handle multiple runs correctly."""
        now = datetime.now(timezone.utc)

        # Create 5 runs, 2 expired, 3 recent
        for i in range(2):
            ts = (now - timedelta(hours=30 + i)).isoformat()
            create_run_with_timestamp(
                registry, f"run-old-{i}", f"bundle-{i}", ts,
                str(bundles_root / "dev-runs" / f"run-old-{i}" / f"bundle-{i}")
            )
            create_run_dir(bundles_root, f"run-old-{i}", f"bundle-{i}")

        for i in range(3):
            ts = (now - timedelta(hours=i)).isoformat()
            create_run_with_timestamp(
                registry, f"run-new-{i}", f"bundle-new-{i}", ts,
                str(bundles_root / "dev-runs" / f"run-new-{i}" / f"bundle-new-{i}")
            )
            create_run_dir(bundles_root, f"run-new-{i}", f"bundle-new-{i}")

        result = cleanup_dev_runs(
            dry_run=False,
            registry=registry,
            ttl_hours=24,
            max_runs=200,
            bundles_root=str(bundles_root),
        )

        assert result.success is True
        assert result.ttl_expired_count == 2
        assert len(result.deleted_run_ids) == 2


class TestCleanupResult:
    """Test CleanupResult dataclass."""

    def test_to_dict_success(self):
        """Successful result should serialize correctly."""
        result = CleanupResult(
            success=True,
            dry_run=False,
            deleted_run_ids=["run-1", "run-2"],
            deleted_paths=["/path/1", "/path/2"],
            ttl_expired_count=1,
            max_runs_exceeded_count=1,
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["dry_run"] is False
        assert d["deleted_run_ids"] == ["run-1", "run-2"]
        assert d["deleted_paths"] == ["/path/1", "/path/2"]
        assert d["ttl_expired_count"] == 1
        assert d["max_runs_exceeded_count"] == 1
        assert "error" not in d

    def test_to_dict_error(self):
        """Error result should include error info."""
        result = CleanupResult(
            success=False,
            dry_run=False,
            error_code=DEV_RUNS_CLEANUP_FAILED,
            error_message="Something went wrong",
        )

        d = result.to_dict()

        assert d["success"] is False
        assert "error" in d
        assert d["error"]["code"] == DEV_RUNS_CLEANUP_FAILED
        assert d["error"]["message"] == "Something went wrong"


class TestCleanupViaAPI:
    """Test cleanup via API endpoint."""

    def test_api_cleanup_requires_auth(self, tmp_path, monkeypatch):
        """Cleanup endpoint should require admin token."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        reset_registry()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))
        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/pipeline/build/cleanup",
            json={"dry_run": True},
        )

        assert response.status_code == 401

    def test_api_cleanup_dry_run(self, tmp_path, monkeypatch):
        """API cleanup dry_run should work with valid token."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        reset_registry()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))
        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/pipeline/build/cleanup",
            json={"dry_run": True},
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["dry_run"] is True

    def test_api_cleanup_real(self, tmp_path, monkeypatch):
        """API cleanup real should work with valid token."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        reset_registry()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))
        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/pipeline/build/cleanup",
            json={"dry_run": False},
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["dry_run"] is False
