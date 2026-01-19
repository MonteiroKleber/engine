"""Verification logic for Legacy Bridge.

Provides functions to verify asset integrity and detect drift.
"""

from dataclasses import dataclass
from typing import List, Optional

from engine.core.data_root import get_institution_root
from engine.legacy_bridge.connectors.file_connector import FileConnector, FileConnectorError
from engine.legacy_bridge.models import LegacyAsset
from engine.legacy_bridge.registry import LegacyBridgeRegistry


@dataclass
class VerifyResult:
    """Result of asset verification."""

    asset_id: str
    name: str
    status: str  # "MATCH" | "DRIFT_DETECTED" | "MISSING" | "ERROR"
    expected_sha256: str
    observed_sha256: str
    drift_detected: bool
    drift_type: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self):
        """Convert to dict."""
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "status": self.status,
            "expected_sha256": self.expected_sha256,
            "observed_sha256": self.observed_sha256,
            "drift_detected": self.drift_detected,
            "drift_type": self.drift_type,
            "error": self.error,
        }


@dataclass
class VerifyAllResult:
    """Result of verify-all operation."""

    total: int
    ok: int
    drift_detected: int
    missing: int
    errors: int
    results: List[VerifyResult]


def verify_asset(
    institution_id: str,
    asset_id: str,
    dept_id: Optional[str] = None,
    actor_id: str = "system",
) -> VerifyResult:
    """Verify a single asset for drift.

    Computes current hash and compares with last known hash.

    Args:
        institution_id: Institution UUID.
        asset_id: Asset identifier.
        dept_id: Optional department ID.
        actor_id: Actor performing verification.

    Returns:
        VerifyResult with verification outcome.
    """
    registry = LegacyBridgeRegistry(institution_id, dept_id)
    asset = registry.get_asset(asset_id)

    if not asset:
        return VerifyResult(
            asset_id=asset_id,
            name="<unknown>",
            status="ERROR",
            expected_sha256="",
            observed_sha256="",
            drift_detected=False,
            error=f"Asset not found: {asset_id}",
        )

    # Get expected hash from last snapshot
    last_snapshot = registry.get_last_snapshot(asset_id)
    expected_sha256 = last_snapshot.content_sha256 if last_snapshot else asset.content_sha256

    # Compute current hash
    # For dept mode, use dept root as base path
    if dept_id:
        base_path = get_institution_root(institution_id) / "depts" / dept_id
    else:
        base_path = get_institution_root(institution_id)
    connector = FileConnector(base_path)

    try:
        observed_sha256 = connector.compute_hash(asset.source_location)
        stats = connector.get_stats(asset.source_location)
    except FileConnectorError as e:
        # Asset is missing/inaccessible
        registry.record_missing(asset_id, str(e), actor_id)
        return VerifyResult(
            asset_id=asset_id,
            name=asset.name,
            status="MISSING",
            expected_sha256=expected_sha256,
            observed_sha256="",
            drift_detected=True,
            drift_type="missing",
            error=str(e),
        )

    # Compare hashes
    drift_detected = observed_sha256 != expected_sha256
    drift_type = None

    if drift_detected:
        # Determine drift type
        if stats["size_bytes"] != (last_snapshot.content_size_bytes if last_snapshot else asset.content_size_bytes):
            drift_type = "content_changed"  # Size changed implies content changed
        else:
            drift_type = "content_changed"  # Hash different, same size

    # Record verification
    registry.record_verification(
        asset_id=asset_id,
        observed_sha256=observed_sha256,
        observed_size=stats["size_bytes"],
        observed_lines=stats.get("line_count"),
        drift_detected=drift_detected,
        drift_type=drift_type,
        actor_id=actor_id,
    )

    return VerifyResult(
        asset_id=asset_id,
        name=asset.name,
        status="DRIFT_DETECTED" if drift_detected else "MATCH",
        expected_sha256=expected_sha256,
        observed_sha256=observed_sha256,
        drift_detected=drift_detected,
        drift_type=drift_type,
    )


def verify_all_assets(
    institution_id: str,
    dept_id: Optional[str] = None,
    actor_id: str = "system",
) -> VerifyAllResult:
    """Verify all assets for an institution.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.
        actor_id: Actor performing verification.

    Returns:
        VerifyAllResult with summary and individual results.
    """
    registry = LegacyBridgeRegistry(institution_id, dept_id)
    assets = registry.list_assets()

    results: List[VerifyResult] = []
    ok = 0
    drift_detected = 0
    missing = 0
    errors = 0

    for asset_summary in assets:
        asset_id = asset_summary["asset_id"]
        result = verify_asset(institution_id, asset_id, dept_id, actor_id)
        results.append(result)

        if result.status == "MATCH":
            ok += 1
        elif result.status == "DRIFT_DETECTED":
            drift_detected += 1
        elif result.status == "MISSING":
            missing += 1
        else:
            errors += 1

    return VerifyAllResult(
        total=len(assets),
        ok=ok,
        drift_detected=drift_detected,
        missing=missing,
        errors=errors,
        results=results,
    )
