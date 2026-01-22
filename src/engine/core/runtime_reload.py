"""Runtime Reload - Hot-swap registry without process restart.

This module provides:
- ActiveRuntimeSnapshot per institution
- reload_active_runtime() for governed hot-swap after pin/rollback
- RUNTIME_RELOADED ledger events for observability

The reload is triggered explicitly by EGE (pin accept, rollback) - not by polling.

Limitation (accepted in 6.6):
- FastAPI routes registered at startup are not removed/re-registered.
- Hot-swap ensures consistency for already-registered routes.
- New routes (new paths/methods) may require restart.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .errors import (
    RUNTIME_RELOAD_FAILED,
    RUNTIME_RELOAD_BUNDLE_MISSING,
)


@dataclass
class ActiveRuntimeSnapshot:
    """Snapshot of active runtime state for an institution.

    Represents the currently loaded bundle/registry in memory.
    Used to verify consistency and for observability.
    """

    institution_id: str
    active_release_id: Optional[str]
    bundle_path: str
    manifest_hash: str
    operations_hash: Optional[str]
    loaded_at: str
    reload_reason: Optional[str] = None  # "boot", "pin_applied", "rollback", "manual"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


# Global snapshots per institution
# Key: institution_id (or "_default" for single-institution mode)
_active_snapshots: Dict[str, ActiveRuntimeSnapshot] = {}

DEFAULT_INSTITUTION_KEY = "_default"


def get_active_snapshot(institution_id: Optional[str] = None) -> Optional[ActiveRuntimeSnapshot]:
    """Get active runtime snapshot for an institution.

    Args:
        institution_id: Institution UUID, or None for default.

    Returns:
        ActiveRuntimeSnapshot if exists, None otherwise.
    """
    key = institution_id or DEFAULT_INSTITUTION_KEY
    return _active_snapshots.get(key)


def set_active_snapshot(snapshot: ActiveRuntimeSnapshot) -> None:
    """Set active runtime snapshot for an institution.

    Args:
        snapshot: Snapshot to set.
    """
    key = snapshot.institution_id or DEFAULT_INSTITUTION_KEY
    _active_snapshots[key] = snapshot


def clear_active_snapshot(institution_id: Optional[str] = None) -> None:
    """Clear active runtime snapshot for an institution.

    Args:
        institution_id: Institution UUID, or None for default.
    """
    key = institution_id or DEFAULT_INSTITUTION_KEY
    _active_snapshots.pop(key, None)


def reset_all_snapshots() -> None:
    """Clear all snapshots (for testing)."""
    _active_snapshots.clear()


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        file_path: Path to file.

    Returns:
        SHA256 hex digest.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _compute_operations_hash(operations_data: Dict[str, Any]) -> str:
    """Compute hash of operations data.

    Args:
        operations_data: Operations dict (from operations.json).

    Returns:
        SHA256 hex digest of canonical JSON.
    """
    canonical = json.dumps(operations_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _emit_runtime_reloaded_event(
    institution_id: str,
    snapshot: ActiveRuntimeSnapshot,
    reason: str,
) -> None:
    """Emit RUNTIME_RELOADED event to ledger.

    Args:
        institution_id: Institution UUID.
        snapshot: The new active snapshot.
        reason: Reason for reload.
    """
    try:
        from .ledger import get_ledger_for_institution

        ledger = get_ledger_for_institution(institution_id)
        ledger.append(
            event_type="RUNTIME_RELOADED",
            tenant_id=institution_id,
            actor_id="SYSTEM",
            actor_roles=["system"],
            case_id=institution_id,
            step="runtime:reload",
            payload={
                "active_release_id": snapshot.active_release_id,
                "manifest_hash": snapshot.manifest_hash,
                "operations_hash": snapshot.operations_hash,
                "bundle_path": snapshot.bundle_path,
                "reason": reason,
                "loaded_at": snapshot.loaded_at,
            },
        )
    except Exception:
        # Don't fail reload on ledger write errors
        pass


def create_snapshot_from_bundle(
    institution_id: Optional[str],
    bundle_path: Path,
    reason: str = "boot",
) -> Tuple[Optional[ActiveRuntimeSnapshot], Optional[str], Optional[str]]:
    """Create ActiveRuntimeSnapshot from a bundle path.

    Args:
        institution_id: Institution UUID (or None for single-institution).
        bundle_path: Path to the bundle directory.
        reason: Reason for creating snapshot ("boot", "pin_applied", "rollback").

    Returns:
        Tuple of (snapshot, error_code, error_message).
        On success: (ActiveRuntimeSnapshot, None, None)
        On failure: (None, error_code, error_message)
    """
    if not bundle_path.exists():
        return None, RUNTIME_RELOAD_BUNDLE_MISSING, f"Bundle path does not exist: {bundle_path}"

    manifest_path = bundle_path / "bundle.manifest.json"
    if not manifest_path.exists():
        return None, RUNTIME_RELOAD_BUNDLE_MISSING, f"Manifest not found: {manifest_path}"

    # Compute manifest hash
    try:
        manifest_hash = _compute_file_hash(manifest_path)
    except OSError as e:
        return None, RUNTIME_RELOAD_FAILED, f"Failed to read manifest: {e}"

    # Try to get release_id from path
    # Path structure: .../releases/YYYYMMDD-HHMMSS/bundle-name
    active_release_id = None
    try:
        if bundle_path.parent.parent.name == "releases":
            active_release_id = bundle_path.parent.name
    except Exception:
        pass

    # Compute operations hash if operations.json exists
    operations_hash = None
    operations_path = bundle_path / "operations.json"
    if operations_path.exists():
        try:
            with open(operations_path, "r", encoding="utf-8") as f:
                ops_data = json.load(f)
            operations_hash = _compute_operations_hash(ops_data)
        except Exception:
            pass

    # For multi-dept bundles, check departments/*/operations.json
    depts_path = bundle_path / "departments"
    if depts_path.exists() and depts_path.is_dir():
        # Compute combined hash of all dept operations
        dept_ops_hashes = []
        for dept_dir in sorted(depts_path.iterdir()):
            if dept_dir.is_dir():
                dept_ops_path = dept_dir / "operations.json"
                if dept_ops_path.exists():
                    try:
                        with open(dept_ops_path, "r", encoding="utf-8") as f:
                            dept_ops_data = json.load(f)
                        dept_ops_hashes.append(_compute_operations_hash(dept_ops_data))
                    except Exception:
                        pass
        if dept_ops_hashes:
            combined = ":".join(dept_ops_hashes)
            operations_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()

    snapshot = ActiveRuntimeSnapshot(
        institution_id=institution_id or DEFAULT_INSTITUTION_KEY,
        active_release_id=active_release_id,
        bundle_path=str(bundle_path),
        manifest_hash=manifest_hash,
        operations_hash=operations_hash,
        loaded_at=_now_iso(),
        reload_reason=reason,
    )

    return snapshot, None, None


def reload_active_runtime(
    institution_id: Optional[str],
    reason: str,
    bundle_path: Optional[Path] = None,
    app: Optional[Any] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Reload runtime state for an institution.

    This is the main entry point for governed hot-swap.
    Called after pin accept or governed rollback.

    Steps:
    1. Determine bundle path (from CURRENT symlink or provided)
    2. Load operations from bundle into registry
    3. Update ActiveRuntimeSnapshot
    4. Invalidate OpenAPI cache
    5. Emit RUNTIME_RELOADED event

    Args:
        institution_id: Institution UUID (or None for single-institution).
        reason: Reason for reload ("pin_applied", "rollback", "manual", "boot").
        bundle_path: Optional explicit bundle path. If None, uses CURRENT symlink.
        app: Optional FastAPI app instance for cache invalidation.

    Returns:
        Tuple of (success, error_code, error_message).
    """
    from .operations import (
        set_operations,
        load_operations_from_file,
        OperationsSchemaError,
    )
    from ..loader.load_bundle import get_bundle_path, get_bundle_context

    # Step 1: Determine bundle path
    if bundle_path is None:
        # Use ENGINE_BUNDLE_PATH or CURRENT symlink
        if institution_id:
            # For institution-specific, check CURRENT symlink
            try:
                from ..ise.release import get_bundles_root_for_institution
                bundles_root = get_bundles_root_for_institution(institution_id)
                current_link = bundles_root / "CURRENT"
                if current_link.exists() and current_link.is_symlink():
                    bundle_path = current_link.resolve()
                else:
                    # Fall back to ENV path
                    bundle_path = get_bundle_path()
            except Exception:
                bundle_path = get_bundle_path()
        else:
            bundle_path = get_bundle_path()

    if not bundle_path.exists():
        return False, RUNTIME_RELOAD_BUNDLE_MISSING, f"Bundle path does not exist: {bundle_path}"

    # Step 2: Create snapshot
    snapshot, error_code, error_message = create_snapshot_from_bundle(
        institution_id=institution_id,
        bundle_path=bundle_path,
        reason=reason,
    )

    if snapshot is None:
        return False, error_code, error_message

    # Step 3: Load operations from bundle
    # Check if single-dept or multi-dept
    depts_path = bundle_path / "departments"
    if depts_path.exists() and depts_path.is_dir():
        # Multi-dept bundle
        for dept_dir in depts_path.iterdir():
            if dept_dir.is_dir():
                dept_id = dept_dir.name
                ops_path = dept_dir / "operations.json"
                if ops_path.exists():
                    try:
                        ops_def = load_operations_from_file(ops_path)
                        if ops_def:
                            set_operations(dept_id, ops_def)
                    except OperationsSchemaError:
                        # Log but continue - partial reload is better than none
                        pass
    else:
        # Single-dept bundle
        ops_path = bundle_path / "operations.json"
        if ops_path.exists():
            try:
                ops_def = load_operations_from_file(ops_path)
                if ops_def:
                    set_operations(None, ops_def)
            except OperationsSchemaError as e:
                return False, RUNTIME_RELOAD_FAILED, f"Failed to load operations: {e}"

    # Step 4: Update snapshot
    set_active_snapshot(snapshot)

    # Step 5: Invalidate OpenAPI cache
    if app is not None:
        app.openapi_schema = None
    else:
        # Try to get app from server module
        try:
            from ..api.server import app as server_app
            server_app.openapi_schema = None
        except ImportError:
            pass

    # Step 6: Emit ledger event
    if institution_id:
        _emit_runtime_reloaded_event(institution_id, snapshot, reason)

    return True, None, None


def reload_on_boot(
    bundle_path: Optional[Path] = None,
    institution_id: Optional[str] = None,
    app: Optional[Any] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Initialize runtime snapshot on boot.

    Called during lifespan startup after load_bundle().

    Args:
        bundle_path: Path to the loaded bundle. If None, uses get_bundle_path().
        institution_id: Institution UUID (or None for single-institution).
        app: Optional FastAPI app instance.

    Returns:
        Tuple of (success, error_code, error_message).
    """
    if bundle_path is None:
        from ..loader.load_bundle import get_bundle_path
        bundle_path = get_bundle_path()

    snapshot, error_code, error_message = create_snapshot_from_bundle(
        institution_id=institution_id,
        bundle_path=bundle_path,
        reason="boot",
    )

    if snapshot is None:
        return False, error_code, error_message

    set_active_snapshot(snapshot)

    # Don't emit ledger event on boot - only on hot-swap
    return True, None, None
