"""CLI entry point for offline proof verification.

Usage:
    python -m engine.proof verify <bundle_path>
    python -m engine.proof verify <bundle_path> --json
"""

import argparse
import json
import sys
from pathlib import Path

from .verify import verify_bundle_offline


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m engine.proof",
        description="Offline bundle proof verification",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify bundle integrity offline",
    )
    verify_parser.add_argument(
        "bundle_path",
        type=Path,
        help="Path to the bundle directory",
    )
    verify_parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON (for CI/automation)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "verify":
        return _cmd_verify(args.bundle_path, json_output=args.json)

    return 1


def _cmd_verify(bundle_path: Path, json_output: bool = False) -> int:
    """Execute verify command.

    Args:
        bundle_path: Path to the bundle directory.
        json_output: If True, output JSON report.

    Returns:
        Exit code (0 for PASS, 1 for FAIL).
    """
    result = verify_bundle_offline(bundle_path)

    if json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.passed:
            print("PASS: Bundle integrity verified")
            print(f"  Bundle: {result.bundle_name}")
            print(f"  Version: {result.bundle_version}")
            print(f"  Source IDL SHA256: {result.source_idl_sha256}")
            print(f"  Contracts verified: {result.contracts_verified}")
            print(f"  Manifest hash: {result.manifest_hash}")
        else:
            print(f"FAIL: {result.error_code}")
            print(f"  {result.error_message}")
            if result.details:
                for key, value in result.details.items():
                    print(f"  {key}: {value}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
