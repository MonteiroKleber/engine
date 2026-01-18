"""Dev Runs Registry - Append-only JSONL for tracking sandbox builds."""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.core.data_root import resolve_namespaced_path


# Event types
EVENT_DEV_RUN_CREATED = "DEV_RUN_CREATED"
EVENT_DEV_RUN_EXPORTED = "DEV_RUN_EXPORTED"
EVENT_DEV_RUN_DELETED = "DEV_RUN_DELETED"

# Error codes
DEV_RUNS_REGISTRY_UNAVAILABLE = "DEV_RUNS_REGISTRY_UNAVAILABLE"

# Default relative path for registry file
DEFAULT_REGISTRY_REL_PATH = "dev_runs_registry.jsonl"


def get_registry_path() -> Path:
    """Get registry file path from ENV or default (legacy, no institution)."""
    path_str = os.environ.get("ENGINE_DEV_RUNS_REGISTRY_PATH", "var/dev_runs_registry.jsonl")
    return Path(path_str)


def get_registry_path_for_institution(institution_id: str) -> Path:
    """Get registry file path for a specific institution.

    Uses ENV ENGINE_DEV_RUNS_REGISTRY_PATH with namespacing rules:
    - If None: use institution_root/dev_runs_registry.jsonl
    - If absolute: use absolute path
    - If relative: use institution_root/<relative>

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to registry file.
    """
    env_value = os.environ.get("ENGINE_DEV_RUNS_REGISTRY_PATH")
    return resolve_namespaced_path(institution_id, env_value, DEFAULT_REGISTRY_REL_PATH)


def get_dev_runs_dir_for_institution(institution_id: str) -> Path:
    """Get dev-runs directory path for a specific institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to dev-runs directory: institution_root/dev-runs/
    """
    # dev-runs dir is always under institution root, no ENV override
    return resolve_namespaced_path(institution_id, None, "dev-runs")


@dataclass
class RegistryEvent:
    """A single registry event."""

    event_type: str
    run_id: str
    bundle_name: str
    timestamp: str
    bundle_path: Optional[str] = None
    zip_path: Optional[str] = None
    zip_sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "event_type": self.event_type,
            "run_id": self.run_id,
            "bundle_name": self.bundle_name,
            "timestamp": self.timestamp,
        }
        if self.bundle_path:
            result["bundle_path"] = self.bundle_path
        if self.zip_path:
            result["zip_path"] = self.zip_path
        if self.zip_sha256:
            result["zip_sha256"] = self.zip_sha256
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistryEvent":
        """Create from dictionary."""
        return cls(
            event_type=data["event_type"],
            run_id=data["run_id"],
            bundle_name=data["bundle_name"],
            timestamp=data["timestamp"],
            bundle_path=data.get("bundle_path"),
            zip_path=data.get("zip_path"),
            zip_sha256=data.get("zip_sha256"),
        )


@dataclass
class DevRunInfo:
    """Aggregated info about a dev run."""

    run_id: str
    bundle_name: str
    created_at: str
    bundle_path: Optional[str] = None
    has_zip: bool = False
    zip_path: Optional[str] = None
    zip_sha256: Optional[str] = None
    deleted: bool = False
    deleted_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "run_id": self.run_id,
            "bundle_name": self.bundle_name,
            "created_at": self.created_at,
        }
        if self.bundle_path:
            result["bundle_path"] = self.bundle_path
        result["has_zip"] = self.has_zip
        if self.zip_path:
            result["zip_path"] = self.zip_path
        if self.zip_sha256:
            result["zip_sha256"] = self.zip_sha256
        result["deleted"] = self.deleted
        if self.deleted_at:
            result["deleted_at"] = self.deleted_at
        return result


class DevRunsRegistry:
    """Append-only registry for dev runs."""

    def __init__(
        self,
        registry_path: Optional[Path] = None,
        institution_id: Optional[str] = None,
    ):
        """Initialize registry.

        Args:
            registry_path: Path to registry file. If provided, takes precedence.
            institution_id: Institution UUID for namespacing. Ignored if path is set.
        """
        if registry_path is not None:
            # Explicit path takes precedence
            self.path = registry_path
        elif institution_id is not None:
            # Use institution-namespaced path
            self.path = get_registry_path_for_institution(institution_id)
        else:
            # Legacy path resolution
            self.path = get_registry_path()
        self._institution_id = institution_id

    def _ensure_parent_dir(self) -> None:
        """Ensure parent directory exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _now_iso(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def append_event(self, event: RegistryEvent) -> None:
        """Append an event to the registry.

        Args:
            event: The event to append.

        Raises:
            IOError: If write fails.
        """
        self._ensure_parent_dir()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    def emit_created(
        self,
        run_id: str,
        bundle_name: str,
        bundle_path: str,
    ) -> RegistryEvent:
        """Emit DEV_RUN_CREATED event.

        Args:
            run_id: UUID of the run.
            bundle_name: Name of the bundle.
            bundle_path: Path to the bundle directory.

        Returns:
            The created event.
        """
        event = RegistryEvent(
            event_type=EVENT_DEV_RUN_CREATED,
            run_id=run_id,
            bundle_name=bundle_name,
            timestamp=self._now_iso(),
            bundle_path=bundle_path,
        )
        self.append_event(event)
        return event

    def emit_exported(
        self,
        run_id: str,
        bundle_name: str,
        zip_path: str,
        zip_sha256: str,
    ) -> RegistryEvent:
        """Emit DEV_RUN_EXPORTED event.

        Args:
            run_id: UUID of the run.
            bundle_name: Name of the bundle.
            zip_path: Path to the ZIP file.
            zip_sha256: SHA256 hash of the ZIP.

        Returns:
            The created event.
        """
        event = RegistryEvent(
            event_type=EVENT_DEV_RUN_EXPORTED,
            run_id=run_id,
            bundle_name=bundle_name,
            timestamp=self._now_iso(),
            zip_path=zip_path,
            zip_sha256=zip_sha256,
        )
        self.append_event(event)
        return event

    def emit_deleted(
        self,
        run_id: str,
        bundle_name: str,
    ) -> RegistryEvent:
        """Emit DEV_RUN_DELETED event.

        Args:
            run_id: UUID of the run.
            bundle_name: Name of the bundle.

        Returns:
            The created event.
        """
        event = RegistryEvent(
            event_type=EVENT_DEV_RUN_DELETED,
            run_id=run_id,
            bundle_name=bundle_name,
            timestamp=self._now_iso(),
        )
        self.append_event(event)
        return event

    def read_events(self) -> List[RegistryEvent]:
        """Read all events from registry.

        Returns:
            List of events in order.
        """
        if not self.path.exists():
            return []

        events = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    events.append(RegistryEvent.from_dict(data))
        return events

    def aggregate_runs(self) -> Dict[str, DevRunInfo]:
        """Aggregate events into run info by run_id.

        Returns:
            Dict mapping run_id to DevRunInfo.
        """
        events = self.read_events()
        runs: Dict[str, DevRunInfo] = {}

        for event in events:
            if event.event_type == EVENT_DEV_RUN_CREATED:
                runs[event.run_id] = DevRunInfo(
                    run_id=event.run_id,
                    bundle_name=event.bundle_name,
                    created_at=event.timestamp,
                    bundle_path=event.bundle_path,
                )
            elif event.event_type == EVENT_DEV_RUN_EXPORTED:
                if event.run_id in runs:
                    runs[event.run_id].has_zip = True
                    runs[event.run_id].zip_path = event.zip_path
                    runs[event.run_id].zip_sha256 = event.zip_sha256
            elif event.event_type == EVENT_DEV_RUN_DELETED:
                if event.run_id in runs:
                    runs[event.run_id].deleted = True
                    runs[event.run_id].deleted_at = event.timestamp

        return runs

    def list_active_runs(self, limit: int = 50) -> List[DevRunInfo]:
        """List active (non-deleted) runs, newest first.

        Args:
            limit: Maximum number of runs to return (max 200).

        Returns:
            List of DevRunInfo for active runs.
        """
        limit = min(limit, 200)
        runs = self.aggregate_runs()

        # Filter to non-deleted runs
        active = [r for r in runs.values() if not r.deleted]

        # Sort by created_at descending (newest first)
        active.sort(key=lambda r: r.created_at, reverse=True)

        return active[:limit]


# Module-level singleton for convenience (legacy, no institution)
_registry: Optional[DevRunsRegistry] = None

# Per-institution registries: institution_id -> DevRunsRegistry
_institution_registries: Dict[str, DevRunsRegistry] = {}


def get_registry(institution_id: Optional[str] = None) -> DevRunsRegistry:
    """Get or create the registry for an institution.

    Args:
        institution_id: Institution UUID, or None for legacy singleton.

    Returns:
        DevRunsRegistry instance.
    """
    global _registry

    if institution_id is None:
        # Legacy behavior: return global singleton
        if _registry is None:
            _registry = DevRunsRegistry()
        return _registry

    # Institution-specific registry
    if institution_id not in _institution_registries:
        _institution_registries[institution_id] = DevRunsRegistry(
            institution_id=institution_id
        )
    return _institution_registries[institution_id]


def reset_registry() -> None:
    """Reset the registry singleton (for testing)."""
    global _registry
    _registry = None


def reset_institution_registries() -> None:
    """Reset all institution registries (for testing)."""
    global _institution_registries
    _institution_registries = {}


def reset_all_registries() -> None:
    """Reset all registries including legacy singleton (for testing)."""
    reset_registry()
    reset_institution_registries()
