"""Legacy Bridge Registry - Append-only asset registry with ledger integration.

This module manages the registration and tracking of legacy assets,
with all operations recorded to the audit ledger.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.core.data_root import get_institution_root
from engine.core.ledger import get_ledger_for_institution
from engine.legacy_bridge.models import (
    AssetStatus,
    LegacyAsset,
    LegacyAssetSnapshot,
    SourceFormat,
    SourceType,
)
from engine.legacy_bridge.connectors.file_connector import FileConnector, FileConnectorError


# Ledger event types for Legacy Bridge
LEGACY_ASSET_REGISTERED = "LEGACY_ASSET_REGISTERED"
LEGACY_ASSET_VERIFIED = "LEGACY_ASSET_VERIFIED"
LEGACY_DRIFT_DETECTED = "LEGACY_DRIFT_DETECTED"
LEGACY_ASSET_MISSING = "LEGACY_ASSET_MISSING"
LEGACY_ASSET_ARCHIVED = "LEGACY_ASSET_ARCHIVED"


class RegistryError(Exception):
    """Error in registry operations."""

    pass


class LegacyBridgeRegistry:
    """Registry for legacy assets.

    Manages:
    - assets_registry.jsonl: Append-only registration log
    - snapshots.jsonl: Append-only snapshot history
    - state.json: Current state for fast lookup
    """

    def __init__(self, institution_id: str, dept_id: Optional[str] = None) -> None:
        """Initialize registry for an institution.

        Args:
            institution_id: Institution UUID.
            dept_id: Optional department ID for multi-dept mode.
        """
        self._institution_id = institution_id
        self._dept_id = dept_id
        self._lock = threading.Lock()

        # Resolve paths
        inst_root = get_institution_root(institution_id)
        if dept_id:
            self._bridge_root = inst_root / "depts" / dept_id / "legacy_bridge"
        else:
            self._bridge_root = inst_root / "legacy_bridge"

        self._registry_path = self._bridge_root / "assets_registry.jsonl"
        self._snapshots_path = self._bridge_root / "snapshots.jsonl"
        self._state_path = self._bridge_root / "state.json"

        # In-memory state cache
        self._state: Dict[str, Any] = {"schema_version": "1.0", "assets": {}}
        self._load_state()

    def _ensure_dir(self) -> None:
        """Ensure bridge directory exists."""
        self._bridge_root.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> None:
        """Load state from state.json if exists."""
        if self._state_path.exists():
            try:
                with open(self._state_path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, IOError):
                # Start fresh on error
                self._state = {"schema_version": "1.0", "assets": {}}

    def _save_state(self) -> None:
        """Save current state to state.json."""
        self._ensure_dir()
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _append_to_registry(self, asset: LegacyAsset) -> None:
        """Append asset to registry JSONL."""
        self._ensure_dir()
        with open(self._registry_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asset.to_dict(), sort_keys=True) + "\n")

    def _append_snapshot(self, snapshot: LegacyAssetSnapshot) -> None:
        """Append snapshot to snapshots JSONL."""
        self._ensure_dir()
        with open(self._snapshots_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot.to_dict(), sort_keys=True) + "\n")

    def _emit_ledger_event(
        self,
        event_type: str,
        asset_id: str,
        step: str,
        payload: Dict[str, Any],
        actor_id: str = "system",
    ) -> None:
        """Emit event to audit ledger."""
        ledger = get_ledger_for_institution(self._institution_id)
        ledger.append(
            event_type=event_type,
            tenant_id=self._institution_id,
            actor_id=actor_id,
            actor_roles=["system"] if actor_id == "system" else [],
            case_id=asset_id,
            step=step,
            payload=payload,
            dept_id=self._dept_id,
        )

    def _validate_source_location(self, source_location: str) -> None:
        """Validate source location is safe.

        Args:
            source_location: Path to validate.

        Raises:
            RegistryError: If path is absolute or contains traversal.
        """
        if Path(source_location).is_absolute():
            raise RegistryError(
                f"source_location must be relative, got absolute: {source_location}"
            )
        if ".." in source_location:
            raise RegistryError(
                f"source_location cannot contain '..': {source_location}"
            )

    def register(
        self,
        asset_id: str,
        name: str,
        source_location: str,
        source_format: str = SourceFormat.RAW.value,
        source_type: str = SourceType.FILE.value,
        description: Optional[str] = None,
        actor_id: str = "system",
    ) -> LegacyAsset:
        """Register a new legacy asset.

        Args:
            asset_id: Stable identifier for the asset.
            name: Human-readable name.
            source_location: Relative path to the asset.
            source_format: Format (csv, json, raw).
            source_type: Source type (file, http, dump).
            description: Optional description.
            actor_id: Actor registering the asset.

        Returns:
            Registered LegacyAsset.

        Raises:
            RegistryError: If asset already exists or source is invalid.
        """
        with self._lock:
            # Check if asset already exists
            if asset_id in self._state.get("assets", {}):
                raise RegistryError(f"Asset already exists: {asset_id}")

            # Validate source location
            self._validate_source_location(source_location)

            # Get connector and read stats/hash
            # For dept mode, use dept root as base path
            if self._dept_id:
                base_path = get_institution_root(self._institution_id) / "depts" / self._dept_id
            else:
                base_path = get_institution_root(self._institution_id)
            connector = FileConnector(base_path)

            try:
                content_sha256 = connector.compute_hash(source_location)
                stats = connector.get_stats(source_location)
                schema_metadata = connector.extract_schema(source_location, source_format)
            except FileConnectorError as e:
                raise RegistryError(f"Failed to access source: {e}")

            # Create asset
            now = datetime.now(timezone.utc).isoformat()
            asset = LegacyAsset(
                asset_id=asset_id,
                name=name,
                description=description,
                source_type=source_type,
                source_location=source_location,
                source_format=source_format,
                schema_version="1.0",
                schema_metadata=schema_metadata,
                content_sha256=content_sha256,
                content_size_bytes=stats["size_bytes"],
                content_line_count=stats.get("line_count"),
                registered_at=now,
                last_verified_at=now,
                last_snapshot_at=now,
                institution_id=self._institution_id,
                dept_id=self._dept_id,
                registered_by=actor_id,
                status=AssetStatus.ACTIVE.value,
            )

            # Append to registry
            self._append_to_registry(asset)

            # Create initial snapshot
            snapshot = LegacyAssetSnapshot(
                snapshot_id=str(uuid.uuid4()),
                asset_id=asset_id,
                snapshot_at=now,
                content_sha256=content_sha256,
                content_size_bytes=stats["size_bytes"],
                content_line_count=stats.get("line_count"),
                verified_by=actor_id,
            )
            self._append_snapshot(snapshot)

            # Update state
            self._state["assets"][asset_id] = {
                "name": name,
                "status": AssetStatus.ACTIVE.value,
                "last_sha256": content_sha256,
                "last_verified_at": now,
                "drift_count": 0,
            }
            self._save_state()

            # Emit ledger event
            self._emit_ledger_event(
                event_type=LEGACY_ASSET_REGISTERED,
                asset_id=asset_id,
                step="LEGACY_BRIDGE:asset.register",
                payload={
                    "asset_id": asset_id,
                    "name": name,
                    "source_type": source_type,
                    "source_location": source_location,
                    "source_format": source_format,
                    "content_sha256": content_sha256,
                    "content_size_bytes": stats["size_bytes"],
                    "schema_metadata": schema_metadata,
                },
                actor_id=actor_id,
            )

            return asset

    def get_asset(self, asset_id: str) -> Optional[LegacyAsset]:
        """Get asset by ID.

        Args:
            asset_id: Asset identifier.

        Returns:
            LegacyAsset if found, None otherwise.
        """
        # Read from registry to get full asset
        if not self._registry_path.exists():
            return None

        with open(self._registry_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if d.get("asset_id") == asset_id:
                        asset = LegacyAsset.from_dict(d)
                        # Update status from state
                        state_entry = self._state.get("assets", {}).get(asset_id)
                        if state_entry:
                            asset.status = state_entry.get("status", asset.status)
                            asset.last_verified_at = state_entry.get(
                                "last_verified_at", asset.last_verified_at
                            )
                        return asset
                except (json.JSONDecodeError, KeyError):
                    continue
        return None

    def list_assets(self) -> List[Dict[str, Any]]:
        """List all assets with current status.

        Returns:
            List of asset summaries from state.
        """
        return [
            {"asset_id": aid, **info}
            for aid, info in self._state.get("assets", {}).items()
        ]

    def get_last_snapshot(self, asset_id: str) -> Optional[LegacyAssetSnapshot]:
        """Get most recent snapshot for asset.

        Args:
            asset_id: Asset identifier.

        Returns:
            Most recent LegacyAssetSnapshot, or None.
        """
        if not self._snapshots_path.exists():
            return None

        last_snapshot = None
        with open(self._snapshots_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if d.get("asset_id") == asset_id:
                        last_snapshot = LegacyAssetSnapshot.from_dict(d)
                except (json.JSONDecodeError, KeyError):
                    continue
        return last_snapshot

    def record_verification(
        self,
        asset_id: str,
        observed_sha256: str,
        observed_size: int,
        observed_lines: Optional[int],
        drift_detected: bool,
        drift_type: Optional[str] = None,
        actor_id: str = "system",
    ) -> LegacyAssetSnapshot:
        """Record a verification result.

        Args:
            asset_id: Asset identifier.
            observed_sha256: Current hash of content.
            observed_size: Current size in bytes.
            observed_lines: Current line count.
            drift_detected: Whether drift was detected.
            drift_type: Type of drift if detected.
            actor_id: Actor performing verification.

        Returns:
            Created snapshot.
        """
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()

            # Get previous snapshot
            prev_snapshot = self.get_last_snapshot(asset_id)
            prev_snapshot_id = prev_snapshot.snapshot_id if prev_snapshot else None
            prev_sha256 = prev_snapshot.content_sha256 if prev_snapshot else None

            # Create snapshot
            snapshot = LegacyAssetSnapshot(
                snapshot_id=str(uuid.uuid4()),
                asset_id=asset_id,
                snapshot_at=now,
                content_sha256=observed_sha256,
                content_size_bytes=observed_size,
                content_line_count=observed_lines,
                prev_snapshot_id=prev_snapshot_id,
                prev_content_sha256=prev_sha256,
                drift_detected=drift_detected,
                drift_type=drift_type,
                verified_by=actor_id,
            )
            self._append_snapshot(snapshot)

            # Update state
            asset_state = self._state.get("assets", {}).get(asset_id, {})
            asset_state["last_sha256"] = observed_sha256
            asset_state["last_verified_at"] = now

            if drift_detected:
                asset_state["status"] = AssetStatus.DRIFT_DETECTED.value
                asset_state["drift_count"] = asset_state.get("drift_count", 0) + 1

            self._state["assets"][asset_id] = asset_state
            self._save_state()

            # Emit ledger event
            expected_sha256 = prev_sha256 or observed_sha256
            if drift_detected:
                self._emit_ledger_event(
                    event_type=LEGACY_DRIFT_DETECTED,
                    asset_id=asset_id,
                    step="LEGACY_BRIDGE:drift.detected",
                    payload={
                        "asset_id": asset_id,
                        "snapshot_id": snapshot.snapshot_id,
                        "expected_sha256": expected_sha256,
                        "observed_sha256": observed_sha256,
                        "drift_type": drift_type,
                        "expected_size_bytes": prev_snapshot.content_size_bytes if prev_snapshot else observed_size,
                        "observed_size_bytes": observed_size,
                        "detection_method": "on_demand_verify",
                    },
                    actor_id=actor_id,
                )
            else:
                self._emit_ledger_event(
                    event_type=LEGACY_ASSET_VERIFIED,
                    asset_id=asset_id,
                    step="LEGACY_BRIDGE:asset.verify",
                    payload={
                        "asset_id": asset_id,
                        "snapshot_id": snapshot.snapshot_id,
                        "expected_sha256": expected_sha256,
                        "observed_sha256": observed_sha256,
                        "drift_detected": False,
                        "verification_result": "MATCH",
                    },
                    actor_id=actor_id,
                )

            return snapshot

    def record_missing(
        self,
        asset_id: str,
        error: str,
        actor_id: str = "system",
    ) -> None:
        """Record that an asset is missing/inaccessible.

        Args:
            asset_id: Asset identifier.
            error: Error message.
            actor_id: Actor performing verification.
        """
        with self._lock:
            asset = self.get_asset(asset_id)
            if not asset:
                return

            now = datetime.now(timezone.utc).isoformat()

            # Create missing snapshot
            snapshot = LegacyAssetSnapshot(
                snapshot_id=str(uuid.uuid4()),
                asset_id=asset_id,
                snapshot_at=now,
                content_sha256="",
                content_size_bytes=0,
                drift_detected=True,
                drift_type="missing",
                verified_by=actor_id,
            )
            self._append_snapshot(snapshot)

            # Update state
            asset_state = self._state.get("assets", {}).get(asset_id, {})
            asset_state["status"] = AssetStatus.DRIFT_DETECTED.value
            asset_state["last_verified_at"] = now
            asset_state["drift_count"] = asset_state.get("drift_count", 0) + 1
            self._state["assets"][asset_id] = asset_state
            self._save_state()

            # Emit ledger event
            self._emit_ledger_event(
                event_type=LEGACY_ASSET_MISSING,
                asset_id=asset_id,
                step="LEGACY_BRIDGE:asset.missing",
                payload={
                    "asset_id": asset_id,
                    "source_type": asset.source_type,
                    "source_location": asset.source_location,
                    "last_known_sha256": asset.content_sha256,
                    "error": error,
                },
                actor_id=actor_id,
            )
