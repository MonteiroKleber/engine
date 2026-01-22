"""Legacy Bridge - Governance of legacy system assets.

This module provides monitoring, drift detection, and governed writes for
legacy system artifacts.

Key components:
- LegacyAsset: Model for a governed legacy artifact
- LegacyAssetSnapshot: Point-in-time snapshot for drift detection
- FileConnector: Read-only connector for local files (CSV/JSON)
- Registry: Append-only asset registry with ledger integration

Write Mode (Etapa 4.3):
- LegacyWriteAction: Model for governed write action
- OutboxConnector: Write connector for outbox files
- LegacyWriteRegistry: Governed write with mandate/autonomy/policy gates

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

# Write mode (Etapa 4.3)
from engine.legacy_bridge.write_models import (
    LegacyWriteAction,
    ActionStatus,
    ACTION_SCHEMAS,
    validate_action_params,
    compute_intent_sha256,
)
from engine.legacy_bridge.connectors.outbox_connector import (
    OutboxConnector,
    OutboxWriteResult,
)
from engine.legacy_bridge.write_registry import (
    LegacyWriteRegistry,
    WriteResult,
    LEGACY_WRITE_INTENT_CREATED,
    LEGACY_WRITE_ALLOWED,
    LEGACY_WRITE_DENIED,
    LEGACY_WRITE_ENQUEUED,
    LEGACY_WRITE_ACKED,
)

__all__ = [
    # Read mode
    "LegacyAsset",
    "LegacyAssetSnapshot",
    "AssetStatus",
    "SourceFormat",
    "SourceType",
    "LegacyBridgeRegistry",
    "FileConnector",
    "verify_asset",
    "verify_all_assets",
    # Write mode (Etapa 4.3)
    "LegacyWriteAction",
    "ActionStatus",
    "ACTION_SCHEMAS",
    "validate_action_params",
    "compute_intent_sha256",
    "OutboxConnector",
    "OutboxWriteResult",
    "LegacyWriteRegistry",
    "WriteResult",
    "LEGACY_WRITE_INTENT_CREATED",
    "LEGACY_WRITE_ALLOWED",
    "LEGACY_WRITE_DENIED",
    "LEGACY_WRITE_ENQUEUED",
    "LEGACY_WRITE_ACKED",
]
