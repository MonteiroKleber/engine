"""Run Detail - Load trace and artifacts for a dev run."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .registry import get_registry, DevRunInfo


# Error codes
DEV_RUN_NOT_FOUND = "DEV_RUN_NOT_FOUND"
DEV_RUN_TRACE_NOT_FOUND = "DEV_RUN_TRACE_NOT_FOUND"
DEV_RUN_IDL_NOT_FOUND = "DEV_RUN_IDL_NOT_FOUND"


@dataclass
class TraceInfo:
    """Trace information for a run."""

    run_id: str
    bundle_name: str
    sir_sha256: str
    draft_sha256: str
    final_idl_sha256: str
    bundle_manifest_sha256: str
    contract_ledger_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "bundle_name": self.bundle_name,
            "sir_sha256": self.sir_sha256,
            "draft_sha256": self.draft_sha256,
            "final_idl_sha256": self.final_idl_sha256,
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "contract_ledger_sha256": self.contract_ledger_sha256,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceInfo":
        """Create from dictionary."""
        return cls(
            run_id=data["run_id"],
            bundle_name=data["bundle_name"],
            sir_sha256=data["sir_sha256"],
            draft_sha256=data["draft_sha256"],
            final_idl_sha256=data["final_idl_sha256"],
            bundle_manifest_sha256=data["bundle_manifest_sha256"],
            contract_ledger_sha256=data["contract_ledger_sha256"],
        )


@dataclass
class RunDetailResult:
    """Result of loading run detail."""

    success: bool
    run_id: Optional[str] = None
    bundle_name: Optional[str] = None
    created_at: Optional[str] = None
    bundle_path: Optional[str] = None
    has_zip: bool = False
    zip_path: Optional[str] = None
    zip_sha256: Optional[str] = None
    deleted: bool = False
    deleted_at: Optional[str] = None
    trace: Optional[TraceInfo] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        if not self.success:
            return {
                "success": False,
                "error": {
                    "code": self.error_code,
                    "message": self.error_message,
                },
            }

        result = {
            "success": True,
            "run_id": self.run_id,
            "bundle_name": self.bundle_name,
            "created_at": self.created_at,
            "has_zip": self.has_zip,
            "deleted": self.deleted,
        }

        if self.bundle_path:
            result["bundle_path"] = self.bundle_path
        if self.zip_path:
            result["zip_path"] = self.zip_path
        if self.zip_sha256:
            result["zip_sha256"] = self.zip_sha256
        if self.deleted_at:
            result["deleted_at"] = self.deleted_at
        if self.trace:
            result["trace"] = self.trace.to_dict()

        return result


def get_run_dir(run_id: str, bundles_root: Optional[str] = None) -> Path:
    """Get the run directory path."""
    root = bundles_root or os.environ.get("ENGINE_PROD_BUNDLES_ROOT", "bundles")
    return Path(root) / "dev-runs" / run_id


def load_trace(run_id: str, bundles_root: Optional[str] = None) -> Optional[TraceInfo]:
    """Load trace.json for a run.

    Args:
        run_id: UUID of the run.
        bundles_root: Root directory for bundles.

    Returns:
        TraceInfo if found, None otherwise.
    """
    run_dir = get_run_dir(run_id, bundles_root)
    trace_path = run_dir / "trace.json"

    if not trace_path.exists():
        return None

    with open(trace_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return TraceInfo.from_dict(data)


def load_idl_final(run_id: str, bundles_root: Optional[str] = None) -> Optional[str]:
    """Load idl_final.idl for a run.

    Args:
        run_id: UUID of the run.
        bundles_root: Root directory for bundles.

    Returns:
        IDL content if found, None otherwise.
    """
    run_dir = get_run_dir(run_id, bundles_root)
    idl_path = run_dir / "idl_final.idl"

    if not idl_path.exists():
        return None

    return idl_path.read_text(encoding="utf-8")


def get_run_detail(
    run_id: str,
    bundles_root: Optional[str] = None,
) -> RunDetailResult:
    """Get detailed information about a run.

    Combines registry info with trace.json data.

    Args:
        run_id: UUID of the run.
        bundles_root: Root directory for bundles.

    Returns:
        RunDetailResult with full run information.
    """
    # Get registry info
    registry = get_registry()
    runs = registry.aggregate_runs()

    if run_id not in runs:
        return RunDetailResult(
            success=False,
            error_code=DEV_RUN_NOT_FOUND,
            error_message=f"Run {run_id} not found in registry",
        )

    run_info: DevRunInfo = runs[run_id]

    # Load trace
    trace = load_trace(run_id, bundles_root)
    if trace is None:
        return RunDetailResult(
            success=False,
            error_code=DEV_RUN_TRACE_NOT_FOUND,
            error_message=f"Trace not found for run {run_id}",
        )

    return RunDetailResult(
        success=True,
        run_id=run_info.run_id,
        bundle_name=run_info.bundle_name,
        created_at=run_info.created_at,
        bundle_path=run_info.bundle_path,
        has_zip=run_info.has_zip,
        zip_path=run_info.zip_path,
        zip_sha256=run_info.zip_sha256,
        deleted=run_info.deleted,
        deleted_at=run_info.deleted_at,
        trace=trace,
    )
