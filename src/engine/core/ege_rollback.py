"""EGE Rollback - Governed automatic rollback for failed deploys.

Implements:
- Rollback to last pinned release on deploy failure
- SAFE_MODE if no pinned release exists
- Deterministic events for audit trail

Spec: docs/specs/fase-2/02-4-rollback-governed/spec.md
"""

import json
import os
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.core.data_root import get_institution_root
from engine.core.errors import (
    EGE_ROLLBACK_NO_PINNED_RELEASE,
    EGE_ROLLBACK_PINNED_RELEASE_MISSING,
    EGE_ROLLBACK_SYMLINK_FAILED,
    EGE_ROLLBACK_BLOCKED_FROZEN,
    EGE_ROLLBACK_BLOCKED_EMERGENCY,
)
from engine.core.institution_config import (
    get_effective_config,
    HASH_PREFIX,
)
from engine.core.ledger import get_ledger_for_institution
from engine.core.runtime_state import runtime_state
from engine.ise.release import get_bundles_root_for_institution
from engine.core.runtime_reload import reload_active_runtime


# Rollback state file name
ROLLBACK_STATE_FILE = "ege_rollback_state.json"


@dataclass
class RollbackResult:
    """Result of a rollback operation."""

    success: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    rolled_back_to: Optional[str] = None  # release_id
    previous_release: Optional[str] = None  # release_id that failed
    safe_mode_activated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


def _now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _emit_rollback_event(
    institution_id: str,
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    """Emit ledger event for rollback operation.

    Args:
        institution_id: Institution UUID.
        event_type: Event type (EGE_ROLLBACK_STARTED, etc).
        payload: Event payload.
    """
    try:
        ledger = get_ledger_for_institution(institution_id)

        step_map = {
            "EGE_ROLLBACK_STARTED": "EGE:rollback.start",
            "EGE_ROLLBACK_COMPLETED": "EGE:rollback.complete",
            "EGE_ROLLBACK_FAILED": "EGE:rollback.fail",
        }
        step = step_map.get(event_type, "EGE:rollback.unknown")

        ledger.append(
            event_type=event_type,
            tenant_id=institution_id,
            actor_id="SYSTEM",
            actor_roles=["system"],
            case_id=institution_id,
            step=step,
            payload=payload,
        )
    except Exception:
        # Don't fail rollback on ledger write errors
        pass


def get_pinned_release_path(institution_id: str) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
    """Get path to the pinned release for an institution.

    Uses pinned_release_id from config to locate the release directory.
    Falls back to hash matching if pinned_release_id is not set.

    Args:
        institution_id: Institution UUID.

    Returns:
        Tuple of (release_path, error_code, error_message).
        On success: (Path, None, None)
        On failure: (None, error_code, error_message)
    """
    config = get_effective_config(institution_id)

    # Check if we have a pinned release
    if config.pinned_release_id is None and config.pinned_bundle_manifest_sha256 is None:
        return None, EGE_ROLLBACK_NO_PINNED_RELEASE, "No pinned release configured"

    bundles_root = get_bundles_root_for_institution(institution_id)
    releases_dir = bundles_root / "releases"

    # If we have pinned_release_id, use it directly
    if config.pinned_release_id:
        # Find the bundle directory inside the release
        release_dir = releases_dir / config.pinned_release_id
        if not release_dir.exists():
            return None, EGE_ROLLBACK_PINNED_RELEASE_MISSING, f"Pinned release {config.pinned_release_id} not found"

        # Find the bundle inside (e.g., finance-pilot)
        bundle_dirs = [d for d in release_dir.iterdir() if d.is_dir()]
        if not bundle_dirs:
            return None, EGE_ROLLBACK_PINNED_RELEASE_MISSING, f"No bundle in release {config.pinned_release_id}"

        # Return the first bundle directory
        return bundle_dirs[0], None, None

    # Fallback: find release by matching manifest hash
    if not releases_dir.exists():
        return None, EGE_ROLLBACK_PINNED_RELEASE_MISSING, "No releases directory"

    expected_hash = config.pinned_bundle_manifest_sha256
    if expected_hash and expected_hash.startswith(HASH_PREFIX):
        expected_hash = expected_hash[len(HASH_PREFIX):]

    # Search releases for matching hash
    from engine.core.ege import compute_file_sha256

    for release_dir in sorted(releases_dir.iterdir(), reverse=True):
        if not release_dir.is_dir():
            continue

        # Find bundle inside release
        for bundle_dir in release_dir.iterdir():
            if not bundle_dir.is_dir():
                continue

            manifest_path = bundle_dir / "bundle.manifest.json"
            if manifest_path.exists():
                try:
                    computed_hash = compute_file_sha256(manifest_path)
                    # Normalize for comparison
                    computed_hex = computed_hash
                    if computed_hex.startswith(HASH_PREFIX):
                        computed_hex = computed_hex[len(HASH_PREFIX):]

                    if computed_hex == expected_hash:
                        return bundle_dir, None, None
                except OSError:
                    continue

    return None, EGE_ROLLBACK_PINNED_RELEASE_MISSING, "Could not find release matching pinned hash"


def check_rollback_blocked(institution_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Check if rollback is blocked by freeze/emergency.

    Args:
        institution_id: Institution UUID.

    Returns:
        Tuple of (is_blocked, error_code, error_message).
        If blocked: (True, error_code, error_message)
        If not blocked: (False, None, None)
    """
    config = get_effective_config(institution_id)

    # Check freeze mode
    if config.freeze_mode:
        return True, EGE_ROLLBACK_BLOCKED_FROZEN, "Rollback blocked: institution is frozen"

    # Check emergency stop (if blocking deploys, also block rollbacks)
    if config.emergency_stop.enabled:
        return True, EGE_ROLLBACK_BLOCKED_EMERGENCY, "Rollback blocked: emergency stop active"

    return False, None, None


def execute_governed_rollback(
    institution_id: str,
    failed_release_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> RollbackResult:
    """Execute governed rollback to pinned release.

    This is called when a deploy fails. It:
    1. Checks if rollback is blocked (freeze/emergency)
    2. Finds the pinned release path
    3. Updates CURRENT symlink to point to pinned release
    4. Emits audit events

    If no pinned release exists, activates SAFE_MODE.

    Args:
        institution_id: Institution UUID.
        failed_release_id: Release ID that failed (for audit trail).
        reason: Reason for rollback (for audit trail).

    Returns:
        RollbackResult with status and details.
    """
    # Emit start event
    _emit_rollback_event(
        institution_id=institution_id,
        event_type="EGE_ROLLBACK_STARTED",
        payload={
            "failed_release_id": failed_release_id,
            "reason": reason,
            "timestamp": _now_iso(),
        },
    )

    # Check if blocked
    is_blocked, error_code, error_message = check_rollback_blocked(institution_id)
    if is_blocked:
        _emit_rollback_event(
            institution_id=institution_id,
            event_type="EGE_ROLLBACK_FAILED",
            payload={
                "error_code": error_code,
                "error_message": error_message,
                "failed_release_id": failed_release_id,
                "timestamp": _now_iso(),
            },
        )
        return RollbackResult(
            success=False,
            error_code=error_code,
            error_message=error_message,
            previous_release=failed_release_id,
        )

    # Get pinned release path
    pinned_path, error_code, error_message = get_pinned_release_path(institution_id)

    if pinned_path is None:
        # No pinned release - activate SAFE_MODE
        runtime_state.set_safe_mode(
            reason_code=error_code or EGE_ROLLBACK_NO_PINNED_RELEASE,
            details=[error_message or "No pinned release to rollback to"],
        )

        _emit_rollback_event(
            institution_id=institution_id,
            event_type="EGE_ROLLBACK_FAILED",
            payload={
                "error_code": error_code,
                "error_message": error_message,
                "failed_release_id": failed_release_id,
                "safe_mode_activated": True,
                "timestamp": _now_iso(),
            },
        )

        return RollbackResult(
            success=False,
            error_code=error_code,
            error_message=error_message,
            previous_release=failed_release_id,
            safe_mode_activated=True,
        )

    # Get the release_id from the path
    # Path is like: .../releases/YYYYMMDD-HHMMSS/bundle-name
    # Parent is the release directory
    pinned_release_id = pinned_path.parent.name

    # Update CURRENT symlink
    bundles_root = get_bundles_root_for_institution(institution_id)
    current_link = bundles_root / "CURRENT"

    try:
        # Atomic symlink update
        # Create temp symlink then rename (atomic on POSIX)
        fd, temp_path = tempfile.mkstemp(dir=bundles_root, prefix=".CURRENT_")
        os.close(fd)
        os.unlink(temp_path)

        # Create new symlink at temp location
        os.symlink(pinned_path, temp_path)

        # Atomic rename
        os.replace(temp_path, current_link)

    except OSError as e:
        _emit_rollback_event(
            institution_id=institution_id,
            event_type="EGE_ROLLBACK_FAILED",
            payload={
                "error_code": EGE_ROLLBACK_SYMLINK_FAILED,
                "error_message": str(e),
                "failed_release_id": failed_release_id,
                "pinned_release_id": pinned_release_id,
                "timestamp": _now_iso(),
            },
        )

        return RollbackResult(
            success=False,
            error_code=EGE_ROLLBACK_SYMLINK_FAILED,
            error_message=f"Failed to update CURRENT symlink: {e}",
            previous_release=failed_release_id,
        )

    # Success - emit completed event
    _emit_rollback_event(
        institution_id=institution_id,
        event_type="EGE_ROLLBACK_COMPLETED",
        payload={
            "rolled_back_to": pinned_release_id,
            "pinned_path": str(pinned_path),
            "failed_release_id": failed_release_id,
            "reason": reason,
            "timestamp": _now_iso(),
        },
    )

    # Trigger runtime hot-swap (Etapa 6.6)
    # After successful rollback, reload the runtime to reflect the rolled-back bundle.
    # This updates the ActiveRuntimeSnapshot, operations registry, and invalidates OpenAPI cache.
    reload_active_runtime(
        institution_id=institution_id,
        reason="rollback",
        bundle_path=pinned_path,  # Use the known pinned path
    )

    return RollbackResult(
        success=True,
        rolled_back_to=pinned_release_id,
        previous_release=failed_release_id,
    )


def get_current_release_id(institution_id: str) -> Optional[str]:
    """Get the release ID currently active (from CURRENT symlink).

    Args:
        institution_id: Institution UUID.

    Returns:
        Release ID (YYYYMMDD-HHMMSS) or None if CURRENT doesn't exist.
    """
    bundles_root = get_bundles_root_for_institution(institution_id)
    current_link = bundles_root / "CURRENT"

    if not current_link.exists() or not current_link.is_symlink():
        return None

    try:
        resolved = current_link.resolve()
        # Path is like: .../releases/YYYYMMDD-HHMMSS/bundle-name
        return resolved.parent.name
    except OSError:
        return None


def list_releases(institution_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """List releases available for an institution.

    Args:
        institution_id: Institution UUID.
        limit: Maximum number of releases to return.

    Returns:
        List of dicts with release_id, bundle_name, is_current, is_pinned, has_trace.
    """
    bundles_root = get_bundles_root_for_institution(institution_id)
    releases_dir = bundles_root / "releases"

    if not releases_dir.exists():
        return []

    config = get_effective_config(institution_id)
    current_release = get_current_release_id(institution_id)
    pinned_release = config.pinned_release_id

    releases = []
    try:
        release_dirs = sorted(releases_dir.iterdir(), reverse=True)[:limit]
    except OSError:
        return []

    for release_dir in release_dirs:
        if not release_dir.is_dir():
            continue

        # Find bundle inside release
        try:
            for bundle_dir in release_dir.iterdir():
                if bundle_dir.is_dir():
                    # Check for trace
                    trace_path = bundle_dir / "trace.json"
                    has_trace = trace_path.exists()

                    releases.append({
                        "release_id": release_dir.name,
                        "bundle_name": bundle_dir.name,
                        "is_current": release_dir.name == current_release,
                        "is_pinned": release_dir.name == pinned_release,
                        "has_trace": has_trace,
                    })
                    break
        except OSError:
            continue

    return releases
