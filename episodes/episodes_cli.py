"""Episodes CLI - Command-line interface for episode and approval operations.

Provides commands:
- engine approve --episode-id <id> --decision approve --reason "..." --approver-name "..." --role "..."
- engine episodes show --episode-id <id>
- engine episodes list [--status pending|approved|rejected]
- engine change --previous-episode-id <id> --cr <path_to_cr.json> [--input-mode idl|draft] [--dry-run]
- engine auditpack --episode-id <id> --out <path.zip> [--include-artifacts]

Usage:
    python -m episodes.episodes_cli approve --episode-id exec-001 --decision approve --reason "Looks good" --approver-name "John" --role "Admin"
    python -m episodes.episodes_cli show --episode-id exec-001
    python -m episodes.episodes_cli list --status pending
    python -m episodes.episodes_cli change --previous-episode-id exec-001 --cr change_request.json --dry-run
    python -m episodes.episodes_cli auditpack --episode-id exec-001 --out audit.zip
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
    EPISODES_DIR,
)
from .approval_gate import (
    ApprovalGate,
    GateResult,
    GateCheckResult,
)
from approvals.approval_v1 import (
    create_approval,
    APPROVAL_SCHEMA_VERSION,
    ApprovalValidationError,
)
from .change_cli import cmd_change as change_cmd_change, ChangeResult
from auditpack.auditpack_cli import cmd_auditpack, AuditPackCLIResult


# =============================================================================
# Result Types
# =============================================================================


class CLIResult:
    """Result of a CLI operation."""

    def __init__(
        self,
        success: bool,
        message: str = "",
        data: dict = None,
        errors: List[str] = None,
        error_codes: List[str] = None,
    ):
        self.success = success
        self.message = message
        self.data = data or {}
        self.errors = errors or []
        self.error_codes = error_codes or []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "errors": self.errors,
            "error_codes": self.error_codes,
        }


# =============================================================================
# Helper: Episode Summary
# =============================================================================


def get_episode_summary(store: EpisodeStore, episode_id: str) -> dict:
    """Get a summary of an episode for display before approval.

    Args:
        store: Episode store instance
        episode_id: Episode identifier

    Returns:
        Dictionary with episode summary
    """
    manifest = store.get_manifest(episode_id)
    episode_dir = store._get_episode_dir(episode_id)

    summary = {
        "episode_id": episode_id,
        "status": manifest.get("status", "unknown"),
        "input_mode": manifest.get("inputs", {}).get("input_mode", "unknown"),
        "created_at": manifest.get("created_at", "unknown"),
    }

    # Get contract info
    contracts = manifest.get("contracts", {})
    summary["contracts"] = {
        "srs": contracts.get("srs_hash_sha256") is not None,
        "ir": contracts.get("ir_hash_sha256") is not None,
        "openapi": contracts.get("openapi_hash_sha256") is not None,
        "plan": contracts.get("plan_hash_sha256") is not None,
        "idl": contracts.get("idl_hash_sha256") is not None,
    }

    # Get links (for change episodes)
    links = manifest.get("links", {})
    summary["previous_episode"] = links.get("previous_episode_id")
    summary["change_request_id"] = links.get("change_request_id")

    # Try to extract metrics from runlog if available
    runlog_path = episode_dir / "runlog.json"
    if runlog_path.exists():
        try:
            import json
            with open(runlog_path) as f:
                runlog = json.load(f)

            # Extract counts from different possible locations
            result = runlog.get("result", {})
            counts = runlog.get("counts", {})

            summary["metrics"] = {
                "entities_count": result.get("entities_count") or counts.get("entities_count", 0),
                "operations_count": result.get("operations_count") or counts.get("operations_count", 0),
                "requirements_count": result.get("requirements_count") or counts.get("requirements_count", 0),
                "tasks_count": result.get("tasks_count") or counts.get("tasks_count", 0),
            }
        except Exception:
            summary["metrics"] = None
    else:
        summary["metrics"] = None

    # Get hashes for display
    summary["hashes"] = {
        "input": manifest.get("inputs", {}).get("input_hash_sha256", "")[:30] + "..." if manifest.get("inputs", {}).get("input_hash_sha256") else None,
        "root": manifest.get("integrity", {}).get("episode_root_hash_sha256", "")[:30] + "..." if manifest.get("integrity", {}).get("episode_root_hash_sha256") else None,
    }

    return summary


def format_episode_summary(summary: dict) -> str:
    """Format episode summary for display.

    Args:
        summary: Episode summary dictionary

    Returns:
        Formatted string for display
    """
    lines = [
        "=" * 60,
        "EPISODE SUMMARY (Review before approval)",
        "=" * 60,
        "",
        f"Episode ID: {summary['episode_id']}",
        f"Status: {summary['status']}",
        f"Input Mode: {summary['input_mode']}",
        f"Created At: {summary['created_at']}",
    ]

    if summary.get("previous_episode"):
        lines.append(f"Previous Episode: {summary['previous_episode']}")
    if summary.get("change_request_id"):
        lines.append(f"Change Request: {summary['change_request_id']}")

    lines.append("")
    lines.append("Contracts:")
    contracts = summary.get("contracts", {})
    for name, present in contracts.items():
        status = "present" if present else "not present"
        lines.append(f"  - {name.upper()}: {status}")

    if summary.get("metrics"):
        lines.append("")
        lines.append("Metrics:")
        metrics = summary["metrics"]
        if metrics.get("entities_count"):
            lines.append(f"  - Entities: {metrics['entities_count']}")
        if metrics.get("operations_count"):
            lines.append(f"  - Operations: {metrics['operations_count']}")
        if metrics.get("requirements_count"):
            lines.append(f"  - Requirements: {metrics['requirements_count']}")
        if metrics.get("tasks_count"):
            lines.append(f"  - Tasks: {metrics['tasks_count']}")

    lines.append("")
    lines.append("Hashes:")
    if summary.get("hashes", {}).get("input"):
        lines.append(f"  - Input: {summary['hashes']['input']}")
    if summary.get("hashes", {}).get("root"):
        lines.append(f"  - Root: {summary['hashes']['root']}")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


# =============================================================================
# Approver Defaults
# =============================================================================


def load_approver_defaults(base_path: Optional[Path] = None) -> Optional[dict]:
    """Load approver defaults from .engine/approver.json if it exists.

    Args:
        base_path: Base path for .engine directory

    Returns:
        Dict with approver defaults or None if file doesn't exist
    """
    if base_path:
        defaults_path = base_path / ".engine" / "approver.json"
    else:
        defaults_path = Path(".engine") / "approver.json"

    if not defaults_path.exists():
        return None

    try:
        with open(defaults_path) as f:
            data = json.load(f)
        return data.get("approver", {})
    except (json.JSONDecodeError, IOError):
        return None


# =============================================================================
# Command: approve
# =============================================================================


def cmd_approve(
    episode_id: str,
    decision: str,
    reason: str,
    approver_name: str,
    role: str,
    org: Optional[str] = None,
    base_path: Optional[Path] = None,
) -> CLIResult:
    """Add an approval to an episode.

    Creates approvals/approval.json inside the episode directory.

    Args:
        episode_id: Episode identifier
        decision: Decision (approve or reject)
        reason: Justification for the decision
        approver_name: Name of the approver
        role: Role of the approver
        org: Optional organization
        base_path: Base path for .engine directory

    Returns:
        CLIResult with approval details
    """
    store = EpisodeStore(base_path)

    # Check episode exists
    if not store.exists(episode_id):
        return CLIResult(
            success=False,
            message=f"Episode not found: {episode_id}",
            errors=[f"GOVERNANCE: Episode not found: {episode_id}"],
            error_codes=["EPISODE_NOT_FOUND"],
        )

    # Generate approval ID
    approval_id = f"appr-{uuid4().hex[:8]}"

    try:
        # Create approval using the approval.v1 module
        approval = create_approval(
            approval_id=approval_id,
            episode_id=episode_id,
            approver_name=approver_name,
            approver_role=role,
            decision=decision,
            reason=reason,
            scope_what="release",  # Episodes are for releases
            approver_org=org,
            signatures=[{"scheme": "manual"}],  # Manual approval
        )

        # Add volatile timestamp
        approval["volatile"] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        # Add approval to episode
        updated_manifest = store.add_approval(episode_id, approval)

        # Check gate status after approval
        gate = ApprovalGate(store)
        gate_result = gate.check_episode(episode_id)

        return CLIResult(
            success=True,
            message=f"Approval added: {approval_id}",
            data={
                "approval_id": approval_id,
                "episode_id": episode_id,
                "decision": decision,
                "approver": approver_name,
                "role": role,
                "episode_status": updated_manifest.get("status"),
                "gate_status": gate_result.result.value,
                "can_proceed": gate_result.can_proceed,
            },
        )

    except ApprovalValidationError as e:
        return CLIResult(
            success=False,
            message=f"Invalid approval: {e.message}",
            errors=[str(e)],
            error_codes=["APPROVAL_INVALID"],
        )
    except EpisodeStoreError as e:
        return CLIResult(
            success=False,
            message=str(e),
            errors=[str(e)],
            error_codes=["EPISODE_STORE_ERROR"],
        )


# =============================================================================
# Command: show
# =============================================================================


def cmd_show(
    episode_id: str,
    base_path: Optional[Path] = None,
) -> CLIResult:
    """Show episode details including paths and hashes.

    Args:
        episode_id: Episode identifier
        base_path: Base path for .engine directory

    Returns:
        CLIResult with episode details
    """
    store = EpisodeStore(base_path)

    try:
        manifest = store.get_manifest(episode_id)

        # Check gate status
        gate = ApprovalGate(store)
        gate_result = gate.check_episode(episode_id)

        # Build paths info
        episode_dir = store._get_episode_dir(episode_id)
        paths = {
            "episode_dir": str(episode_dir),
            "manifest": str(store._get_manifest_path(episode_id)),
            "runlog": str(store._get_runlog_path(episode_id)),
            "approval": str(store._get_approval_path(episode_id)),
            "input_dir": str(store._get_input_dir(episode_id)),
            "contracts_dir": str(store._get_contracts_dir(episode_id)),
            "artifacts_dir": str(store._get_artifacts_dir(episode_id)),
        }

        # Extract key hashes
        hashes = {
            "input": manifest.get("inputs", {}).get("input_hash_sha256"),
            "episode_root": manifest.get("integrity", {}).get("episode_root_hash_sha256"),
            "contracts": manifest.get("contracts", {}),
            "outputs": manifest.get("outputs", {}),
        }

        return CLIResult(
            success=True,
            message=f"Episode: {episode_id}",
            data={
                "episode_id": episode_id,
                "execution_id": manifest.get("execution_id"),
                "status": manifest.get("status"),
                "created_at": manifest.get("created_at"),
                "created_by": manifest.get("created_by"),
                "input_mode": manifest.get("inputs", {}).get("input_mode"),
                "paths": paths,
                "hashes": hashes,
                "links": manifest.get("links", {}),
                "approval_status": manifest.get("approval_status"),
                "gate": {
                    "status": gate_result.result.value,
                    "can_proceed": gate_result.can_proceed,
                    "blocked_reason": gate_result.blocked_reason,
                },
                "is_finalized": manifest.get("integrity", {}).get("episode_root_hash_sha256") != "sha256:" + "0" * 64,
            },
        )

    except EpisodeNotFoundError as e:
        return CLIResult(
            success=False,
            message=str(e),
            errors=[str(e)],
            error_codes=["EPISODE_NOT_FOUND"],
        )


# =============================================================================
# Command: list
# =============================================================================


def cmd_list(
    status: Optional[str] = None,
    base_path: Optional[Path] = None,
) -> CLIResult:
    """List episodes with optional filtering.

    Args:
        status: Filter by status (pending, approved, rejected, released)
        base_path: Base path for .engine directory

    Returns:
        CLIResult with list of episodes
    """
    store = EpisodeStore(base_path)

    episodes = store.list_episodes(status=status)

    return CLIResult(
        success=True,
        message=f"Found {len(episodes)} episode(s)",
        data={
            "episodes": episodes,
            "count": len(episodes),
            "filter": {"status": status},
        },
    )


# =============================================================================
# Command: gate-check
# =============================================================================


def cmd_gate_check(
    episode_id: str,
    base_path: Optional[Path] = None,
) -> CLIResult:
    """Check if an episode can proceed (gate check).

    Args:
        episode_id: Episode identifier
        base_path: Base path for .engine directory

    Returns:
        CLIResult with gate check result
    """
    store = EpisodeStore(base_path)
    gate = ApprovalGate(store)

    gate_result = gate.check_episode(episode_id)

    return CLIResult(
        success=gate_result.can_proceed,
        message=f"Gate check: {gate_result.result.value}",
        data={
            "episode_id": episode_id,
            "result": gate_result.result.value,
            "can_proceed": gate_result.can_proceed,
            "has_approval": gate_result.has_approval,
            "decision": gate_result.decision,
            "blocked_reason": gate_result.blocked_reason,
        },
        errors=gate_result.errors if gate_result.errors else None,
        error_codes=[gate_result.blocked_reason] if gate_result.blocked_reason else None,
    )


# =============================================================================
# Command: verify
# =============================================================================


def cmd_verify(
    episode_id: str,
    base_path: Optional[Path] = None,
) -> CLIResult:
    """Verify the integrity of an episode.

    Args:
        episode_id: Episode identifier
        base_path: Base path for .engine directory

    Returns:
        CLIResult with verification result
    """
    store = EpisodeStore(base_path)

    try:
        is_valid, info_msg = store.verify_integrity(episode_id)

        if is_valid:
            if info_msg == "approval_added":
                # Special case: approval was added after finalization
                # This is EXPECTED behavior, not an error
                return CLIResult(
                    success=True,
                    message=f"Episode {episode_id} integrity verified (approval added after finalization - this is expected)",
                    data={
                        "episode_id": episode_id,
                        "integrity_valid": True,
                        "approval_added_after_finalization": True,
                        "note": "The root hash differs because an approval file was added. "
                               "This is normal append-only behavior. All original artifacts are intact.",
                    },
                )
            else:
                return CLIResult(
                    success=True,
                    message=f"Episode {episode_id} integrity verified",
                    data={
                        "episode_id": episode_id,
                        "integrity_valid": True,
                    },
                )
        else:
            return CLIResult(
                success=False,
                message=f"Episode {episode_id} integrity check failed: {info_msg}",
                data={
                    "episode_id": episode_id,
                    "integrity_valid": False,
                },
                errors=[info_msg],
                error_codes=["INTEGRITY_ERROR"],
            )

    except EpisodeNotFoundError as e:
        return CLIResult(
            success=False,
            message=str(e),
            errors=[str(e)],
            error_codes=["EPISODE_NOT_FOUND"],
        )


# =============================================================================
# CLI Entry Point
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for episodes CLI."""
    parser = argparse.ArgumentParser(
        prog="engine",
        description="Engine CLI for episode and approval management",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # approve command
    approve_parser = subparsers.add_parser("approve", help="Add an approval to an episode")
    approve_parser.add_argument("--episode-id", required=True, help="Episode ID to approve")
    approve_parser.add_argument(
        "--decision",
        required=True,
        choices=["approve", "reject"],
        help="Decision (approve or reject)",
    )
    approve_parser.add_argument("--reason", required=True, help="Approval reason")
    approve_parser.add_argument(
        "--approver-name",
        help="Approver name (optional if .engine/approver.json exists)",
    )
    approve_parser.add_argument(
        "--role",
        help="Approver role (optional if .engine/approver.json exists)",
    )
    approve_parser.add_argument("--org", help="Approver organization")
    approve_parser.add_argument("--base-path", type=Path, help="Base path for .engine directory")
    approve_parser.add_argument(
        "--show-summary",
        action="store_true",
        help="Show episode summary before approval (contracts, hashes, metrics)",
    )

    # episodes subcommand
    episodes_parser = subparsers.add_parser("episodes", help="Episode management commands")
    episodes_subparsers = episodes_parser.add_subparsers(dest="episodes_command", help="Episodes sub-command")

    # episodes show
    show_parser = episodes_subparsers.add_parser("show", help="Show episode details")
    show_parser.add_argument("--episode-id", required=True, help="Episode ID to show")
    show_parser.add_argument("--base-path", type=Path, help="Base path for .engine directory")

    # episodes list
    list_parser = episodes_subparsers.add_parser("list", help="List episodes")
    list_parser.add_argument(
        "--status",
        choices=["pending", "approved", "rejected", "released"],
        help="Filter by status",
    )
    list_parser.add_argument("--base-path", type=Path, help="Base path for .engine directory")

    # episodes gate-check
    gate_parser = episodes_subparsers.add_parser("gate-check", help="Check if episode can proceed")
    gate_parser.add_argument("--episode-id", required=True, help="Episode ID to check")
    gate_parser.add_argument("--base-path", type=Path, help="Base path for .engine directory")

    # episodes verify
    verify_parser = episodes_subparsers.add_parser("verify", help="Verify episode integrity")
    verify_parser.add_argument("--episode-id", required=True, help="Episode ID to verify")
    verify_parser.add_argument("--base-path", type=Path, help="Base path for .engine directory")

    # change command
    change_parser = subparsers.add_parser("change", help="Execute a change based on a Change Request")
    change_parser.add_argument(
        "--previous-episode-id",
        required=True,
        help="ID of the episode to base the change on",
    )
    change_parser.add_argument(
        "--cr",
        required=True,
        type=Path,
        help="Path to the Change Request JSON file",
    )
    change_parser.add_argument(
        "--input-mode",
        choices=["idl", "draft"],
        default="idl",
        help="Input mode (default: idl)",
    )
    change_parser.add_argument(
        "--input",
        type=str,
        help="Path to input file (optional)",
    )
    change_parser.add_argument(
        "--base-path",
        type=Path,
        help="Base path for .engine directory",
    )
    change_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only, don't create episode",
    )

    # auditpack command
    auditpack_parser = subparsers.add_parser("auditpack", help="Generate an auditable ZIP package from an episode")
    auditpack_parser.add_argument(
        "--episode-id",
        required=True,
        help="Episode ID to package",
    )
    auditpack_parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output path for the ZIP file",
    )
    auditpack_parser.add_argument(
        "--include-artifacts",
        action="store_true",
        help="Include artifacts in the package",
    )
    auditpack_parser.add_argument(
        "--base-path",
        type=Path,
        help="Base path for .engine directory",
    )

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for episodes CLI.

    Args:
        args: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = create_parser()
    parsed = parser.parse_args(args)

    if parsed.command is None:
        parser.print_help()
        return 1

    result: CLIResult

    if parsed.command == "approve":
        base_path = getattr(parsed, "base_path", None)

        # Load approver defaults if available
        defaults = load_approver_defaults(base_path)

        # Get approver info from args or defaults
        approver_name = getattr(parsed, "approver_name", None)
        role = getattr(parsed, "role", None)
        org = getattr(parsed, "org", None)

        if defaults:
            if not approver_name:
                approver_name = defaults.get("display_name")
            if not role:
                role = defaults.get("role")
            if not org:
                org = defaults.get("org")

        # Validate required fields
        if not approver_name:
            print("Error: --approver-name is required (or set in .engine/approver.json)")
            return 1
        if not role:
            print("Error: --role is required (or set in .engine/approver.json)")
            return 1

        # Show summary before approval if requested
        if getattr(parsed, "show_summary", False):
            store_root = str(base_path / ".engine") if base_path else ".engine"
            store = EpisodeStore(store_root)
            summary = get_episode_summary(store, parsed.episode_id)
            if summary:
                print("=" * 60)
                print("RESUMO DO EPISÓDIO ANTES DA APROVAÇÃO")
                print("=" * 60)
                print(format_episode_summary(summary))
                print("=" * 60)
                print()

        result = cmd_approve(
            episode_id=parsed.episode_id,
            decision=parsed.decision,
            reason=parsed.reason,
            approver_name=approver_name,
            role=role,
            org=org,
            base_path=base_path,
        )

    elif parsed.command == "episodes":
        if parsed.episodes_command is None:
            parser.parse_args(["episodes", "--help"])
            return 1

        if parsed.episodes_command == "show":
            result = cmd_show(
                episode_id=parsed.episode_id,
                base_path=getattr(parsed, "base_path", None),
            )

        elif parsed.episodes_command == "list":
            result = cmd_list(
                status=getattr(parsed, "status", None),
                base_path=getattr(parsed, "base_path", None),
            )

        elif parsed.episodes_command == "gate-check":
            result = cmd_gate_check(
                episode_id=parsed.episode_id,
                base_path=getattr(parsed, "base_path", None),
            )

        elif parsed.episodes_command == "verify":
            result = cmd_verify(
                episode_id=parsed.episode_id,
                base_path=getattr(parsed, "base_path", None),
            )

        else:
            parser.parse_args(["episodes", "--help"])
            return 1

    elif parsed.command == "change":
        change_result = change_cmd_change(
            previous_episode_id=parsed.previous_episode_id,
            cr_path=parsed.cr,
            input_mode=parsed.input_mode,
            input_path=getattr(parsed, "input", None),
            base_path=getattr(parsed, "base_path", None),
            dry_run=getattr(parsed, "dry_run", False),
        )
        print(json.dumps(change_result.to_dict(), indent=2))
        return 0 if change_result.success else 1

    elif parsed.command == "auditpack":
        auditpack_result = cmd_auditpack(
            episode_id=parsed.episode_id,
            out_zip=parsed.out,
            include_artifacts=getattr(parsed, "include_artifacts", False),
            base_path=getattr(parsed, "base_path", None),
        )
        print(json.dumps(auditpack_result.to_dict(), indent=2))
        return 0 if auditpack_result.success else 1

    else:
        parser.print_help()
        return 1

    # Output result
    print(json.dumps(result.to_dict(), indent=2))

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
