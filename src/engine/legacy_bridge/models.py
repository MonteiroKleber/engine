"""Data models for Legacy Bridge.

This module defines the core data structures for legacy asset governance:
- LegacyAsset: Represents a governed legacy artifact
- LegacyAssetSnapshot: Point-in-time integrity snapshot
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SourceType(str, Enum):
    """Type of legacy asset source."""

    FILE = "file"
    HTTP = "http"
    DUMP = "dump"


class SourceFormat(str, Enum):
    """Format of legacy asset content."""

    CSV = "csv"
    JSON = "json"
    XML = "xml"
    RAW = "raw"


class AssetStatus(str, Enum):
    """Status of a legacy asset."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DRIFT_DETECTED = "drift_detected"


@dataclass
class LegacyAsset:
    """Legacy asset under governance.

    A LegacyAsset represents an artifact from a legacy system that is
    being monitored for integrity without modifying the source.
    """

    # Identification
    asset_id: str  # Stable string identifier (user-provided)
    name: str  # Human-readable name
    description: Optional[str] = None

    # Source Information
    source_type: str = SourceType.FILE.value  # "file" | "http" | "dump"
    source_location: str = ""  # Relative path (no absolute, no ..)
    source_format: str = SourceFormat.RAW.value  # "csv" | "json" | "xml" | "raw"

    # Schema/Metadata (extracted)
    schema_version: str = "1.0"
    schema_metadata: Dict[str, Any] = field(default_factory=dict)

    # Integrity
    content_sha256: str = ""  # "SHA256:<hex>" format
    content_size_bytes: int = 0
    content_line_count: Optional[int] = None

    # Timestamps (ISO8601 UTC)
    registered_at: str = ""
    last_verified_at: Optional[str] = None
    last_snapshot_at: Optional[str] = None

    # Governance
    institution_id: str = ""
    dept_id: Optional[str] = None  # Department for multi-dept (Etapa 2.5)
    registered_by: str = "system"
    status: str = AssetStatus.ACTIVE.value

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "description": self.description,
            "source_type": self.source_type,
            "source_location": self.source_location,
            "source_format": self.source_format,
            "schema_version": self.schema_version,
            "schema_metadata": self.schema_metadata,
            "content_sha256": self.content_sha256,
            "content_size_bytes": self.content_size_bytes,
            "content_line_count": self.content_line_count,
            "registered_at": self.registered_at,
            "last_verified_at": self.last_verified_at,
            "last_snapshot_at": self.last_snapshot_at,
            "institution_id": self.institution_id,
            "dept_id": self.dept_id,
            "registered_by": self.registered_by,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LegacyAsset":
        """Create from storage dict."""
        return cls(
            asset_id=d.get("asset_id", ""),
            name=d.get("name", ""),
            description=d.get("description"),
            source_type=d.get("source_type", SourceType.FILE.value),
            source_location=d.get("source_location", ""),
            source_format=d.get("source_format", SourceFormat.RAW.value),
            schema_version=d.get("schema_version", "1.0"),
            schema_metadata=d.get("schema_metadata", {}),
            content_sha256=d.get("content_sha256", ""),
            content_size_bytes=d.get("content_size_bytes", 0),
            content_line_count=d.get("content_line_count"),
            registered_at=d.get("registered_at", ""),
            last_verified_at=d.get("last_verified_at"),
            last_snapshot_at=d.get("last_snapshot_at"),
            institution_id=d.get("institution_id", ""),
            dept_id=d.get("dept_id"),
            registered_by=d.get("registered_by", "system"),
            status=d.get("status", AssetStatus.ACTIVE.value),
        )


@dataclass
class LegacyAssetSnapshot:
    """Point-in-time snapshot of legacy asset.

    Used to track integrity over time and detect drift.
    """

    snapshot_id: str  # UUID of snapshot
    asset_id: str  # FK to LegacyAsset
    snapshot_at: str  # ISO8601 UTC

    # Content integrity at snapshot time
    content_sha256: str
    content_size_bytes: int
    content_line_count: Optional[int] = None

    # Previous snapshot for diff
    prev_snapshot_id: Optional[str] = None
    prev_content_sha256: Optional[str] = None

    # Drift detection
    drift_detected: bool = False
    drift_type: Optional[str] = None  # "content_changed" | "size_changed" | "missing"

    # Actor/context
    verified_by: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "snapshot_id": self.snapshot_id,
            "asset_id": self.asset_id,
            "snapshot_at": self.snapshot_at,
            "content_sha256": self.content_sha256,
            "content_size_bytes": self.content_size_bytes,
            "content_line_count": self.content_line_count,
            "prev_snapshot_id": self.prev_snapshot_id,
            "prev_content_sha256": self.prev_content_sha256,
            "drift_detected": self.drift_detected,
            "drift_type": self.drift_type,
            "verified_by": self.verified_by,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LegacyAssetSnapshot":
        """Create from storage dict."""
        return cls(
            snapshot_id=d.get("snapshot_id", ""),
            asset_id=d.get("asset_id", ""),
            snapshot_at=d.get("snapshot_at", ""),
            content_sha256=d.get("content_sha256", ""),
            content_size_bytes=d.get("content_size_bytes", 0),
            content_line_count=d.get("content_line_count"),
            prev_snapshot_id=d.get("prev_snapshot_id"),
            prev_content_sha256=d.get("prev_content_sha256"),
            drift_detected=d.get("drift_detected", False),
            drift_type=d.get("drift_type"),
            verified_by=d.get("verified_by", "system"),
        )
