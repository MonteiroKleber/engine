"""Tests for Dev Runs Registry."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from engine.pipeline.registry import (
    DevRunsRegistry,
    RegistryEvent,
    DevRunInfo,
    EVENT_DEV_RUN_CREATED,
    EVENT_DEV_RUN_EXPORTED,
    EVENT_DEV_RUN_DELETED,
    get_registry,
    reset_registry,
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


class TestRegistryEvent:
    """Test RegistryEvent dataclass."""

    def test_to_dict_created_event(self):
        """Created event should serialize correctly."""
        event = RegistryEvent(
            event_type=EVENT_DEV_RUN_CREATED,
            run_id="run-123",
            bundle_name="my-bundle",
            timestamp="2024-01-15T10:00:00+00:00",
            bundle_path="/bundles/dev-runs/run-123/my-bundle",
        )

        d = event.to_dict()

        assert d["event_type"] == EVENT_DEV_RUN_CREATED
        assert d["run_id"] == "run-123"
        assert d["bundle_name"] == "my-bundle"
        assert d["timestamp"] == "2024-01-15T10:00:00+00:00"
        assert d["bundle_path"] == "/bundles/dev-runs/run-123/my-bundle"
        assert "zip_path" not in d
        assert "zip_sha256" not in d

    def test_to_dict_exported_event(self):
        """Exported event should include zip info."""
        event = RegistryEvent(
            event_type=EVENT_DEV_RUN_EXPORTED,
            run_id="run-123",
            bundle_name="my-bundle",
            timestamp="2024-01-15T11:00:00+00:00",
            zip_path="/bundles/dev-runs/run-123/exports/my-bundle.zip",
            zip_sha256="abc123",
        )

        d = event.to_dict()

        assert d["event_type"] == EVENT_DEV_RUN_EXPORTED
        assert d["zip_path"] == "/bundles/dev-runs/run-123/exports/my-bundle.zip"
        assert d["zip_sha256"] == "abc123"

    def test_from_dict_roundtrip(self):
        """Event should survive to_dict/from_dict roundtrip."""
        original = RegistryEvent(
            event_type=EVENT_DEV_RUN_CREATED,
            run_id="run-456",
            bundle_name="test-bundle",
            timestamp="2024-01-15T12:00:00+00:00",
            bundle_path="/path/to/bundle",
        )

        d = original.to_dict()
        restored = RegistryEvent.from_dict(d)

        assert restored.event_type == original.event_type
        assert restored.run_id == original.run_id
        assert restored.bundle_name == original.bundle_name
        assert restored.timestamp == original.timestamp
        assert restored.bundle_path == original.bundle_path


class TestDevRunInfo:
    """Test DevRunInfo dataclass."""

    def test_to_dict_basic(self):
        """Basic run info should serialize correctly."""
        info = DevRunInfo(
            run_id="run-123",
            bundle_name="my-bundle",
            created_at="2024-01-15T10:00:00+00:00",
        )

        d = info.to_dict()

        assert d["run_id"] == "run-123"
        assert d["bundle_name"] == "my-bundle"
        assert d["created_at"] == "2024-01-15T10:00:00+00:00"
        assert d["has_zip"] is False
        assert d["deleted"] is False

    def test_to_dict_with_zip(self):
        """Run info with zip should include zip fields."""
        info = DevRunInfo(
            run_id="run-123",
            bundle_name="my-bundle",
            created_at="2024-01-15T10:00:00+00:00",
            has_zip=True,
            zip_path="/path/to/zip",
            zip_sha256="abc123",
        )

        d = info.to_dict()

        assert d["has_zip"] is True
        assert d["zip_path"] == "/path/to/zip"
        assert d["zip_sha256"] == "abc123"


class TestDevRunsRegistry:
    """Test DevRunsRegistry class."""

    def test_emit_created_writes_to_file(self, registry, registry_path):
        """emit_created should write event to JSONL file."""
        registry.emit_created(
            run_id="run-001",
            bundle_name="test-bundle",
            bundle_path="/path/to/bundle",
        )

        assert registry_path.exists()
        lines = registry_path.read_text().strip().split("\n")
        assert len(lines) == 1

        event = json.loads(lines[0])
        assert event["event_type"] == EVENT_DEV_RUN_CREATED
        assert event["run_id"] == "run-001"
        assert event["bundle_name"] == "test-bundle"
        assert event["bundle_path"] == "/path/to/bundle"
        assert "timestamp" in event

    def test_emit_exported_writes_to_file(self, registry, registry_path):
        """emit_exported should write event to JSONL file."""
        registry.emit_exported(
            run_id="run-001",
            bundle_name="test-bundle",
            zip_path="/path/to/zip",
            zip_sha256="abc123",
        )

        lines = registry_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["event_type"] == EVENT_DEV_RUN_EXPORTED
        assert event["zip_path"] == "/path/to/zip"
        assert event["zip_sha256"] == "abc123"

    def test_emit_deleted_writes_to_file(self, registry, registry_path):
        """emit_deleted should write event to JSONL file."""
        registry.emit_deleted(
            run_id="run-001",
            bundle_name="test-bundle",
        )

        lines = registry_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["event_type"] == EVENT_DEV_RUN_DELETED

    def test_append_only_multiple_events(self, registry, registry_path):
        """Registry should append multiple events."""
        registry.emit_created("run-001", "bundle-1", "/path/1")
        registry.emit_created("run-002", "bundle-2", "/path/2")
        registry.emit_exported("run-001", "bundle-1", "/zip/1", "hash1")

        lines = registry_path.read_text().strip().split("\n")
        assert len(lines) == 3

        events = [json.loads(line) for line in lines]
        assert events[0]["event_type"] == EVENT_DEV_RUN_CREATED
        assert events[1]["event_type"] == EVENT_DEV_RUN_CREATED
        assert events[2]["event_type"] == EVENT_DEV_RUN_EXPORTED

    def test_read_events_empty_file(self, registry, registry_path):
        """read_events should return empty list for non-existent file."""
        events = registry.read_events()
        assert events == []

    def test_read_events_returns_all_events(self, registry):
        """read_events should return all events in order."""
        registry.emit_created("run-001", "bundle-1", "/path/1")
        registry.emit_created("run-002", "bundle-2", "/path/2")
        registry.emit_exported("run-001", "bundle-1", "/zip/1", "hash1")

        events = registry.read_events()

        assert len(events) == 3
        assert events[0].event_type == EVENT_DEV_RUN_CREATED
        assert events[0].run_id == "run-001"
        assert events[1].run_id == "run-002"
        assert events[2].event_type == EVENT_DEV_RUN_EXPORTED


class TestAggregateRuns:
    """Test aggregate_runs method."""

    def test_aggregate_single_created(self, registry):
        """Single created event should produce one run."""
        registry.emit_created("run-001", "bundle-1", "/path/1")

        runs = registry.aggregate_runs()

        assert len(runs) == 1
        assert "run-001" in runs
        assert runs["run-001"].bundle_name == "bundle-1"
        assert runs["run-001"].bundle_path == "/path/1"
        assert not runs["run-001"].has_zip
        assert not runs["run-001"].deleted

    def test_aggregate_created_plus_exported(self, registry):
        """Created + exported should show has_zip=True."""
        registry.emit_created("run-001", "bundle-1", "/path/1")
        registry.emit_exported("run-001", "bundle-1", "/zip/1", "hash123")

        runs = registry.aggregate_runs()

        assert runs["run-001"].has_zip is True
        assert runs["run-001"].zip_path == "/zip/1"
        assert runs["run-001"].zip_sha256 == "hash123"

    def test_aggregate_created_plus_deleted(self, registry):
        """Created + deleted should show deleted=True."""
        registry.emit_created("run-001", "bundle-1", "/path/1")
        registry.emit_deleted("run-001", "bundle-1")

        runs = registry.aggregate_runs()

        assert runs["run-001"].deleted is True
        assert runs["run-001"].deleted_at is not None

    def test_aggregate_multiple_runs(self, registry):
        """Multiple runs should be aggregated separately."""
        registry.emit_created("run-001", "bundle-1", "/path/1")
        registry.emit_created("run-002", "bundle-2", "/path/2")
        registry.emit_exported("run-001", "bundle-1", "/zip/1", "hash1")
        registry.emit_deleted("run-002", "bundle-2")

        runs = registry.aggregate_runs()

        assert len(runs) == 2
        assert runs["run-001"].has_zip is True
        assert runs["run-001"].deleted is False
        assert runs["run-002"].has_zip is False
        assert runs["run-002"].deleted is True


class TestListActiveRuns:
    """Test list_active_runs method."""

    def test_list_active_excludes_deleted(self, registry):
        """list_active_runs should exclude deleted runs."""
        registry.emit_created("run-001", "bundle-1", "/path/1")
        registry.emit_created("run-002", "bundle-2", "/path/2")
        registry.emit_deleted("run-001", "bundle-1")

        active = registry.list_active_runs()

        assert len(active) == 1
        assert active[0].run_id == "run-002"

    def test_list_active_sorted_newest_first(self, registry):
        """list_active_runs should return newest first."""
        # Create with explicit timestamps via direct event append
        event1 = RegistryEvent(
            event_type=EVENT_DEV_RUN_CREATED,
            run_id="run-001",
            bundle_name="bundle-1",
            timestamp="2024-01-15T10:00:00+00:00",
            bundle_path="/path/1",
        )
        event2 = RegistryEvent(
            event_type=EVENT_DEV_RUN_CREATED,
            run_id="run-002",
            bundle_name="bundle-2",
            timestamp="2024-01-15T12:00:00+00:00",  # Later
            bundle_path="/path/2",
        )
        event3 = RegistryEvent(
            event_type=EVENT_DEV_RUN_CREATED,
            run_id="run-003",
            bundle_name="bundle-3",
            timestamp="2024-01-15T11:00:00+00:00",  # Middle
            bundle_path="/path/3",
        )

        registry.append_event(event1)
        registry.append_event(event2)
        registry.append_event(event3)

        active = registry.list_active_runs()

        assert len(active) == 3
        assert active[0].run_id == "run-002"  # Newest
        assert active[1].run_id == "run-003"  # Middle
        assert active[2].run_id == "run-001"  # Oldest

    def test_list_active_respects_limit(self, registry):
        """list_active_runs should respect limit parameter."""
        for i in range(10):
            registry.emit_created(f"run-{i:03d}", f"bundle-{i}", f"/path/{i}")

        active = registry.list_active_runs(limit=3)

        assert len(active) == 3

    def test_list_active_max_limit_200(self, registry):
        """list_active_runs should cap limit at 200."""
        for i in range(5):
            registry.emit_created(f"run-{i:03d}", f"bundle-{i}", f"/path/{i}")

        # Even if we ask for more, it should cap internally
        active = registry.list_active_runs(limit=500)

        # We only have 5, so we get 5
        assert len(active) == 5


class TestRegistrySingleton:
    """Test get_registry singleton."""

    def test_get_registry_returns_same_instance(self, monkeypatch, tmp_path):
        """get_registry should return same instance."""
        reset_registry()
        reg_path = tmp_path / "registry.jsonl"
        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(reg_path))

        reg1 = get_registry()
        reg2 = get_registry()

        assert reg1 is reg2

    def test_reset_registry_clears_singleton(self, monkeypatch, tmp_path):
        """reset_registry should clear singleton."""
        reset_registry()
        reg_path = tmp_path / "registry.jsonl"
        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(reg_path))

        reg1 = get_registry()
        reset_registry()
        reg2 = get_registry()

        # After reset, we get a new instance
        assert reg1 is not reg2
