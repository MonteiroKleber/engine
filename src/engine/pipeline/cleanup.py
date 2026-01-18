"""Dev Runs Cleanup - TTL and MAX_RUNS enforcement."""

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import (
    DevRunsRegistry,
    DevRunInfo,
    get_registry,
    get_dev_runs_dir_for_institution,
    DEV_RUNS_REGISTRY_UNAVAILABLE,
)


# Error codes
DEV_RUNS_CLEANUP_FAILED = "DEV_RUNS_CLEANUP_FAILED"


# --- Boot helpers ---


def parse_bool_env(name: str, default: str = "0") -> bool:
    """Parse boolean from ENV variable.

    Args:
        name: Environment variable name.
        default: Default value if not set ("0" or "1").

    Returns:
        True if value is "1", False otherwise.
    """
    return os.environ.get(name, default) == "1"


def should_cleanup_on_boot() -> bool:
    """Check if cleanup should run on boot.

    Returns:
        True if ENGINE_DEV_RUNS_CLEANUP_ON_BOOT is "1".
    """
    return parse_bool_env("ENGINE_DEV_RUNS_CLEANUP_ON_BOOT", "0")


def is_dry_run_on_boot() -> bool:
    """Check if cleanup on boot should be dry run.

    Returns:
        True if ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT is "1".
    """
    return parse_bool_env("ENGINE_DEV_RUNS_CLEANUP_DRY_RUN_ON_BOOT", "0")


def get_ttl_hours() -> int:
    """Get TTL in hours from ENV or default."""
    return int(os.environ.get("ENGINE_DEV_RUNS_TTL_HOURS", "24"))


def get_max_runs() -> int:
    """Get max runs from ENV or default."""
    return int(os.environ.get("ENGINE_DEV_RUNS_MAX_RUNS", "200"))


@dataclass
class CleanupResult:
    """Result of cleanup operation."""

    success: bool
    dry_run: bool
    deleted_run_ids: List[str] = field(default_factory=list)
    deleted_paths: List[str] = field(default_factory=list)
    ttl_expired_count: int = 0
    max_runs_exceeded_count: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "success": self.success,
            "dry_run": self.dry_run,
            "deleted_run_ids": self.deleted_run_ids,
            "deleted_paths": self.deleted_paths,
            "ttl_expired_count": self.ttl_expired_count,
            "max_runs_exceeded_count": self.max_runs_exceeded_count,
        }
        if self.error_code:
            result["error"] = {
                "code": self.error_code,
                "message": self.error_message,
            }
        return result


def _parse_iso_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    # Handle both 'Z' suffix and '+00:00' format
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _is_ttl_expired(run: DevRunInfo, ttl_hours: int) -> bool:
    """Check if a run has exceeded TTL.

    Args:
        run: The run info.
        ttl_hours: TTL in hours.

    Returns:
        True if TTL expired.
    """
    created = _parse_iso_timestamp(run.created_at)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    return created < cutoff


def determine_runs_to_delete(
    runs: List[DevRunInfo],
    ttl_hours: Optional[int] = None,
    max_runs: Optional[int] = None,
) -> tuple[List[DevRunInfo], int, int]:
    """Determine which runs should be deleted.

    Deletion order (deterministic):
    1. TTL expired runs (oldest first)
    2. If still over max_runs, delete oldest until under limit

    Args:
        runs: List of active (non-deleted) runs.
        ttl_hours: TTL in hours (uses ENV/default if None).
        max_runs: Max runs allowed (uses ENV/default if None).

    Returns:
        Tuple of (runs_to_delete, ttl_expired_count, max_runs_exceeded_count).
    """
    ttl = ttl_hours if ttl_hours is not None else get_ttl_hours()
    max_r = max_runs if max_runs is not None else get_max_runs()

    to_delete: List[DevRunInfo] = []
    ttl_count = 0
    max_count = 0

    # Sort by created_at ascending (oldest first)
    sorted_runs = sorted(runs, key=lambda r: r.created_at)

    # Step 1: Find TTL expired runs
    for run in sorted_runs:
        if _is_ttl_expired(run, ttl):
            to_delete.append(run)
            ttl_count += 1

    # Remaining runs after TTL deletion
    remaining = [r for r in sorted_runs if r not in to_delete]

    # Step 2: If still over max_runs, delete oldest
    if len(remaining) > max_r:
        excess = len(remaining) - max_r
        for run in remaining[:excess]:
            to_delete.append(run)
            max_count += 1

    return to_delete, ttl_count, max_count


def cleanup_dev_runs(
    dry_run: bool = False,
    registry: Optional[DevRunsRegistry] = None,
    ttl_hours: Optional[int] = None,
    max_runs: Optional[int] = None,
    bundles_root: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> CleanupResult:
    """Execute cleanup of dev runs.

    Args:
        dry_run: If True, simulate deletion without actually deleting.
        registry: Registry to use (uses singleton if None).
        ttl_hours: TTL in hours (uses ENV/default if None).
        max_runs: Max runs allowed (uses ENV/default if None).
        bundles_root: Root directory for bundles (uses ENV/default if None). Ignored if institution_id is set.
        institution_id: Institution UUID for namespaced storage. If set, uses institution-specific paths.

    Returns:
        CleanupResult with deleted run IDs and paths.
    """
    reg = registry or get_registry(institution_id=institution_id)

    # Determine dev-runs directory
    if institution_id is not None:
        dev_runs_dir = get_dev_runs_dir_for_institution(institution_id)
    else:
        root = bundles_root or os.environ.get("ENGINE_PROD_BUNDLES_ROOT", "bundles")
        dev_runs_dir = Path(root) / "dev-runs"

    try:
        # Get active runs
        runs_dict = reg.aggregate_runs()
        active_runs = [r for r in runs_dict.values() if not r.deleted]

        # Determine what to delete
        to_delete, ttl_count, max_count = determine_runs_to_delete(
            active_runs, ttl_hours, max_runs
        )

        deleted_ids: List[str] = []
        deleted_paths: List[str] = []

        for run in to_delete:
            run_dir = dev_runs_dir / run.run_id

            if not dry_run:
                # Delete the directory if it exists
                if run_dir.exists():
                    shutil.rmtree(run_dir)
                    deleted_paths.append(str(run_dir))

                # Emit deletion event
                reg.emit_deleted(run.run_id, run.bundle_name)
            else:
                # In dry run, just record what would be deleted
                if run_dir.exists():
                    deleted_paths.append(str(run_dir))

            deleted_ids.append(run.run_id)

        return CleanupResult(
            success=True,
            dry_run=dry_run,
            deleted_run_ids=deleted_ids,
            deleted_paths=deleted_paths,
            ttl_expired_count=ttl_count,
            max_runs_exceeded_count=max_count,
        )

    except Exception as e:
        return CleanupResult(
            success=False,
            dry_run=dry_run,
            error_code=DEV_RUNS_CLEANUP_FAILED,
            error_message=str(e),
        )
