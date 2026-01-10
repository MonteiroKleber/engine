"""AuditPack CLI - Command-line interface for generating audit packages.

Provides command:
- engine auditpack --episode-id <id> --out <path.zip> [--include-artifacts true|false]

Usage:
    python -m auditpack.auditpack_cli --episode-id exec-001 --out audit.zip
    python -m auditpack.auditpack_cli --episode-id exec-001 --out audit.zip --include-artifacts
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from episodes.episode_store import (
    EpisodeStore,
    EpisodeNotFoundError,
)
from .auditpack import (
    build_auditpack,
    AuditPackError,
    AuditPackSecurityError,
    AuditPackValidationError,
)


# =============================================================================
# Result Types
# =============================================================================


class AuditPackCLIResult:
    """Result of an auditpack CLI operation."""

    def __init__(
        self,
        success: bool,
        message: str = "",
        out_zip: Optional[str] = None,
        data: dict = None,
        errors: List[str] = None,
        error_codes: List[str] = None,
    ):
        self.success = success
        self.message = message
        self.out_zip = out_zip
        self.data = data or {}
        self.errors = errors or []
        self.error_codes = error_codes or []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "out_zip": self.out_zip,
            "data": self.data,
            "errors": self.errors,
            "error_codes": self.error_codes,
        }


# =============================================================================
# Command: auditpack
# =============================================================================


def cmd_auditpack(
    episode_id: str,
    out_zip: Path,
    include_artifacts: bool = False,
    base_path: Optional[Path] = None,
) -> AuditPackCLIResult:
    """Generate an auditpack ZIP for an episode.

    Args:
        episode_id: Episode identifier
        out_zip: Output path for the ZIP file
        include_artifacts: Whether to include artifacts
        base_path: Base path for .engine directory

    Returns:
        AuditPackCLIResult with operation details
    """
    store = EpisodeStore(base_path)

    # Check episode exists
    if not store.exists(episode_id):
        return AuditPackCLIResult(
            success=False,
            message=f"Episode not found: {episode_id}",
            errors=[f"GOVERNANCE: Episode not found: {episode_id}"],
            error_codes=["EPISODE_NOT_FOUND"],
        )

    # Get episode directory
    episode_dir = store._get_episode_dir(episode_id)

    try:
        result = build_auditpack(
            episode_dir=episode_dir,
            out_zip=out_zip,
            include_artifacts=include_artifacts,
        )

        return AuditPackCLIResult(
            success=True,
            message=f"AuditPack created: {out_zip}",
            out_zip=str(out_zip),
            data={
                "episode_id": result["episode_id"],
                "root_hash": result["root_hash"],
                "source_root_hash": result["source_root_hash"],
                "total_files": result["total_files"],
                "include_artifacts": result["include_artifacts"],
                "stats": result["index"].get("stats", {}),
            },
        )

    except AuditPackSecurityError as e:
        return AuditPackCLIResult(
            success=False,
            message=str(e),
            errors=[str(e)],
            error_codes=["AUDITPACK_SECURITY_BLOCKED"],
        )

    except AuditPackValidationError as e:
        return AuditPackCLIResult(
            success=False,
            message=str(e),
            errors=[str(e)],
            error_codes=["AUDITPACK_VALIDATION_ERROR"],
        )

    except AuditPackError as e:
        return AuditPackCLIResult(
            success=False,
            message=str(e),
            errors=[str(e)],
            error_codes=[e.error_code],
        )

    except Exception as e:
        return AuditPackCLIResult(
            success=False,
            message=f"Unexpected error: {e}",
            errors=[str(e)],
            error_codes=["AUDITPACK_ERROR"],
        )


# =============================================================================
# CLI Entry Point
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for auditpack CLI."""
    parser = argparse.ArgumentParser(
        prog="engine auditpack",
        description="Generate an auditable ZIP package from an episode",
    )

    parser.add_argument(
        "--episode-id",
        required=True,
        help="Episode ID to package",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output path for the ZIP file",
    )
    parser.add_argument(
        "--include-artifacts",
        action="store_true",
        help="Include artifacts in the package",
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        help="Base path for .engine directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for auditpack CLI.

    Args:
        args: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = create_parser()
    parsed = parser.parse_args(args)

    result = cmd_auditpack(
        episode_id=parsed.episode_id,
        out_zip=parsed.out,
        include_artifacts=parsed.include_artifacts,
        base_path=parsed.base_path,
    )

    if parsed.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            print(f"SUCCESS: {result.message}")
            print(f"  Episode: {result.data.get('episode_id')}")
            print(f"  Root Hash: {result.data.get('root_hash')}")
            print(f"  Total Files: {result.data.get('total_files')}")
            if result.data.get("include_artifacts"):
                print("  Artifacts: Included")
        else:
            print(f"ERROR: {result.message}")
            for error in result.errors:
                print(f"  - {error}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
