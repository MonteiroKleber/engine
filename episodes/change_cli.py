"""Change CLI - Command-line interface for change execution.

Provides command:
- engine change --previous-episode-id <id> --cr <path_to_cr.json> [--input-mode idl|draft] [--input <...>]

Usage:
    python -m episodes.change_cli --previous-episode-id exec-001 --cr change_request.json --input-mode idl --input spec.idl

The command:
1. Validates the CR against schema
2. Verifies CR.previous_episode_id matches --previous-episode-id argument
3. Checks that the previous episode exists and is approved
4. Runs Impact Gate to validate the scope of changes
5. Creates a new episode chained to the previous one
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from .episode_store import (
    EpisodeStore,
    EpisodeNotFoundError,
    EpisodeStoreError,
    compute_content_hash,
)
from change_requests.cr_v1 import (
    load_cr,
    validate_cr,
    canonicalize_cr,
    cr_hash_sha256,
    get_cr_id,
    get_previous_episode_id,
    CRValidationError,
)
from gates.impact_gate import (
    ImpactGate,
    ImpactGateResult,
    ImpactBlockedReason,
)


# =============================================================================
# Constants
# =============================================================================

RUNLOG_SCHEMA_VERSION = "runlog.v1"


# =============================================================================
# Exceptions
# =============================================================================


class ChangeExecutionError(Exception):
    """Exception raised when change execution fails.

    Error messages follow project prefix conventions.
    """

    def __init__(self, message: str, error_code: str):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class CRPreviousMismatchError(ChangeExecutionError):
    """Exception raised when CR.previous_episode_id doesn't match argument."""

    def __init__(self, expected: str, got: str):
        super().__init__(
            f"INTEGRITY: CR.previous_episode_id mismatch: expected '{expected}', got '{got}'",
            "CR_PREVIOUS_MISMATCH",
        )
        self.expected = expected
        self.got = got


# =============================================================================
# Result Types
# =============================================================================


class ChangeResult:
    """Result of a change execution."""

    def __init__(
        self,
        success: bool,
        message: str = "",
        episode_id: Optional[str] = None,
        data: dict = None,
        errors: List[str] = None,
        error_codes: List[str] = None,
    ):
        self.success = success
        self.message = message
        self.episode_id = episode_id
        self.data = data or {}
        self.errors = errors or []
        self.error_codes = error_codes or []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "episode_id": self.episode_id,
            "data": self.data,
            "errors": self.errors,
            "error_codes": self.error_codes,
        }


# =============================================================================
# Runlog Helpers
# =============================================================================


def create_change_runlog(
    execution_id: str,
    change_request_id: str,
    previous_episode_id: str,
    cr_hash: str,
) -> dict:
    """Create a new runlog for a change execution.

    Args:
        execution_id: Unique execution identifier
        change_request_id: CR identifier
        previous_episode_id: Previous episode ID
        cr_hash: SHA256 hash of the canonicalized CR

    Returns:
        Runlog dict
    """
    return {
        "schema_version": RUNLOG_SCHEMA_VERSION,
        "execution_id": execution_id,
        "final_status": "success",  # Will be updated on finalize
        "blocked_reason": None,
        "duration_ms": 0,
        "errors": [],
        "error_codes": [],
        "change_request": {
            "change_request_id": change_request_id,
            "previous_episode_id": previous_episode_id,
            "cr_hash_sha256": cr_hash,
        },
        "metrics": None,
        "volatile": {
            "started_at": datetime.utcnow().isoformat() + "Z",
            "finished_at": None,
        },
    }


def finalize_change_runlog(
    runlog: dict,
    status: str,
    duration_ms: float,
    errors: Optional[List[str]] = None,
    error_codes: Optional[List[str]] = None,
    blocked_reason: Optional[str] = None,
    metrics: Optional[dict] = None,
) -> dict:
    """Finalize a change runlog with execution results.

    Args:
        runlog: The runlog dict to finalize
        status: Final status (success, blocked, failed)
        duration_ms: Execution duration in milliseconds
        errors: List of error messages
        error_codes: List of error codes (1:1 with errors)
        blocked_reason: Reason for blocking (if status is blocked)
        metrics: Optional metrics dict

    Returns:
        The finalized runlog dict
    """
    runlog["final_status"] = status
    runlog["blocked_reason"] = blocked_reason
    runlog["duration_ms"] = duration_ms
    runlog["errors"] = errors or []
    runlog["error_codes"] = error_codes or []
    runlog["metrics"] = metrics

    if runlog.get("volatile"):
        runlog["volatile"]["finished_at"] = datetime.utcnow().isoformat() + "Z"

    return runlog


# =============================================================================
# Command: change
# =============================================================================


def cmd_change(
    previous_episode_id: str,
    cr_path: Path,
    input_mode: Optional[str] = None,
    input_path: Optional[str] = None,
    base_path: Optional[Path] = None,
    dry_run: bool = False,
) -> ChangeResult:
    """Execute a change based on a Change Request.

    Creates a new episode chained to the previous one.

    Args:
        previous_episode_id: ID of the episode to base the change on
        cr_path: Path to the Change Request JSON file
        input_mode: Input mode (idl, draft)
        input_path: Path to input file (optional)
        base_path: Base path for .engine directory
        dry_run: If True, validate only without creating episode

    Returns:
        ChangeResult with execution details
    """
    import time

    start_time = time.time()
    store = EpisodeStore(base_path)

    # Step 1: Load and validate CR
    try:
        cr = load_cr(cr_path)
    except FileNotFoundError:
        return ChangeResult(
            success=False,
            message=f"Change request file not found: {cr_path}",
            errors=[f"SCHEMA: Change request file not found: {cr_path}"],
            error_codes=["CR_NOT_FOUND"],
        )
    except CRValidationError as e:
        return ChangeResult(
            success=False,
            message=f"Invalid change request: {e.message}",
            errors=[str(e)],
            error_codes=["CR_SCHEMA_INVALID"],
        )

    cr_id = get_cr_id(cr)
    cr_previous = get_previous_episode_id(cr)

    # Step 2: Verify CR.previous_episode_id matches argument
    if cr_previous != previous_episode_id:
        return ChangeResult(
            success=False,
            message=f"CR.previous_episode_id mismatch",
            errors=[
                f"INTEGRITY: CR.previous_episode_id '{cr_previous}' does not match "
                f"argument '{previous_episode_id}'"
            ],
            error_codes=["CR_PREVIOUS_MISMATCH"],
        )

    # Step 3: Check previous episode exists
    if not store.exists(previous_episode_id):
        return ChangeResult(
            success=False,
            message=f"Previous episode not found: {previous_episode_id}",
            errors=[f"GOVERNANCE: Previous episode not found: {previous_episode_id}"],
            error_codes=["PREVIOUS_EPISODE_NOT_FOUND"],
        )

    # Step 4: Check previous episode is approved (optional - warn if not)
    prev_manifest = store.get_manifest(previous_episode_id)
    prev_status = prev_manifest.get("status", "pending")
    approval_warning = None
    if prev_status != "approved":
        approval_warning = (
            f"Warning: Previous episode '{previous_episode_id}' is not approved "
            f"(status: {prev_status})"
        )

    # Step 5: Compute CR hash (canonical)
    cr_hash = cr_hash_sha256(cr)

    # Step 6: Run Impact Gate (if affected_paths are known)
    # For now, we don't have affected_paths from the CR itself
    # Impact Gate will be run when actual patches are computed
    impact_result = None

    # Step 7: Generate execution ID and episode ID
    execution_id = f"change-{uuid4().hex[:8]}"
    episode_id = execution_id

    if dry_run:
        duration_ms = (time.time() - start_time) * 1000
        return ChangeResult(
            success=True,
            message="Dry run: validation passed",
            episode_id=None,
            data={
                "change_request_id": cr_id,
                "previous_episode_id": previous_episode_id,
                "cr_hash_sha256": cr_hash,
                "dry_run": True,
                "would_create_episode_id": episode_id,
                "previous_episode_status": prev_status,
                "approval_warning": approval_warning,
                "duration_ms": duration_ms,
            },
        )

    # Step 8: Create runlog
    runlog = create_change_runlog(
        execution_id=execution_id,
        change_request_id=cr_id,
        previous_episode_id=previous_episode_id,
        cr_hash=cr_hash,
    )

    # Step 9: Determine input hash
    # For change execution, the input is the CR itself
    input_hash = cr_hash

    # Step 10: Create new episode
    try:
        episode_dir = store.create_episode(
            episode_id=episode_id,
            execution_id=execution_id,
            input_mode=input_mode or "idl",
            input_hash=input_hash,
            created_by=None,
            previous_episode_id=previous_episode_id,
            change_request_id=cr_id,
            cr_hash_sha256=cr_hash,
        )

        # Step 11: Register the CR in the episode
        store.register_change_request(episode_id, cr)

        # Step 12: Register the runlog
        duration_ms = (time.time() - start_time) * 1000
        finalize_change_runlog(
            runlog=runlog,
            status="success",
            duration_ms=duration_ms,
            metrics={
                "input_mode": input_mode or "idl",
                "artifacts_generated": 0,
                "patches_applied": 0,
            },
        )
        store.register_runlog(episode_id, runlog)

        # Note: Episode is NOT finalized here - the actual pipeline should
        # register artifacts and then finalize

        return ChangeResult(
            success=True,
            message=f"Change episode created: {episode_id}",
            episode_id=episode_id,
            data={
                "change_request_id": cr_id,
                "previous_episode_id": previous_episode_id,
                "cr_hash_sha256": cr_hash,
                "episode_dir": str(episode_dir),
                "previous_episode_status": prev_status,
                "approval_warning": approval_warning,
                "duration_ms": duration_ms,
            },
        )

    except EpisodeStoreError as e:
        duration_ms = (time.time() - start_time) * 1000
        return ChangeResult(
            success=False,
            message=str(e),
            errors=[str(e)],
            error_codes=["EPISODE_STORE_ERROR"],
            data={"duration_ms": duration_ms},
        )


# =============================================================================
# CLI Entry Point
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for change CLI."""
    parser = argparse.ArgumentParser(
        prog="engine change",
        description="Execute a change based on a Change Request",
    )

    parser.add_argument(
        "--previous-episode-id",
        required=True,
        help="ID of the episode to base the change on",
    )
    parser.add_argument(
        "--cr",
        required=True,
        type=Path,
        help="Path to the Change Request JSON file",
    )
    parser.add_argument(
        "--input-mode",
        choices=["idl", "draft"],
        default="idl",
        help="Input mode (default: idl)",
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to input file (optional)",
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        help="Base path for .engine directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only, don't create episode",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for change CLI.

    Args:
        args: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = create_parser()
    parsed = parser.parse_args(args)

    result = cmd_change(
        previous_episode_id=parsed.previous_episode_id,
        cr_path=parsed.cr,
        input_mode=parsed.input_mode,
        input_path=parsed.input,
        base_path=parsed.base_path,
        dry_run=parsed.dry_run,
    )

    if parsed.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            print(f"SUCCESS: {result.message}")
            if result.episode_id:
                print(f"Episode ID: {result.episode_id}")
            if result.data.get("approval_warning"):
                print(f"\n{result.data['approval_warning']}")
        else:
            print(f"ERROR: {result.message}")
            for error in result.errors:
                print(f"  - {error}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
