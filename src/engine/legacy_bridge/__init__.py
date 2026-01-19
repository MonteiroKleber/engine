"""Legacy Bridge - Read-only governance of legacy system assets.

This module provides read-only monitoring and drift detection for
legacy system artifacts without modifying the source systems.

Key components:
- LegacyAsset: Model for a governed legacy artifact
- LegacyAssetSnapshot: Point-in-time snapshot for drift detection
- FileConnector: Read-only connector for local files (CSV/JSON)
- Registry: Append-only asset registry with ledger integration

Usage:
    python -m engine.legacy_bridge register --institution ... --asset-id ... --path ...
    python -m engine.legacy_bridge verify --institution ... --asset-id ...
"""

from engine.legacy_bridge.models import (
    LegacyAsset,
    LegacyAssetSnapshot,
    AssetStatus,
    SourceFormat,
    SourceType,
)
from engine.legacy_bridge.registry import LegacyBridgeRegistry
from engine.legacy_bridge.connectors.file_connector import FileConnector
from engine.legacy_bridge.verify import verify_asset, verify_all_assets

__all__ = [
    "LegacyAsset",
    "LegacyAssetSnapshot",
    "AssetStatus",
    "SourceFormat",
    "SourceType",
    "LegacyBridgeRegistry",
    "FileConnector",
    "verify_asset",
    "verify_all_assets",
]
