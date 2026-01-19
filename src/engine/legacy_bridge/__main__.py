"""CLI entry point for Legacy Bridge.

Usage:
    python -m engine.legacy_bridge register --institution ... --asset-id ... --path ...
    python -m engine.legacy_bridge verify --institution ... --asset-id ...
    python -m engine.legacy_bridge list --institution ...
    python -m engine.legacy_bridge verify-all --institution ...
"""

import argparse
import sys
from typing import Optional

from engine.legacy_bridge.models import SourceFormat, SourceType
from engine.legacy_bridge.registry import LegacyBridgeRegistry, RegistryError
from engine.legacy_bridge.verify import verify_asset, verify_all_assets


def cmd_register(args: argparse.Namespace) -> int:
    """Register a new legacy asset."""
    try:
        registry = LegacyBridgeRegistry(args.institution, args.dept)
        asset = registry.register(
            asset_id=args.asset_id,
            name=args.name or args.asset_id,
            source_location=args.path,
            source_format=args.format,
            source_type=args.type,
            description=args.description,
            actor_id=args.actor or "system",
        )

        print(f"Asset registered: asset_id={asset.asset_id}")
        print(f"SHA256: {asset.content_sha256}")
        print(f"Size: {asset.content_size_bytes} bytes")
        if asset.schema_metadata:
            print(f"Schema: {asset.schema_metadata}")
        print(f"Ledger event: LEGACY_ASSET_REGISTERED")
        return 0

    except RegistryError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify a single asset."""
    try:
        result = verify_asset(
            institution_id=args.institution,
            asset_id=args.asset_id,
            dept_id=args.dept,
            actor_id=args.actor or "system",
        )

        print(f"Asset verified: {result.name}")
        print(f"Status: {result.status}")
        print(f"Expected: {result.expected_sha256}")
        print(f"Observed: {result.observed_sha256}")

        if result.drift_detected:
            print(f"Drift type: {result.drift_type}")
            print(f"Ledger event: LEGACY_DRIFT_DETECTED")
            return 1
        elif result.status == "MISSING":
            print(f"Error: {result.error}")
            print(f"Ledger event: LEGACY_ASSET_MISSING")
            return 1
        elif result.status == "ERROR":
            print(f"Error: {result.error}")
            return 1
        else:
            print(f"Ledger event: LEGACY_ASSET_VERIFIED")
            return 0

    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List all assets."""
    try:
        registry = LegacyBridgeRegistry(args.institution, args.dept)
        assets = registry.list_assets()

        if not assets:
            print(f"No assets registered for institution {args.institution}")
            return 0

        print(f"Assets for institution {args.institution}:")
        for i, asset in enumerate(assets, 1):
            status = asset.get("status", "unknown")
            name = asset.get("name", asset["asset_id"])
            sha256 = asset.get("last_sha256", "")
            last_verified = asset.get("last_verified_at", "never")
            drift_count = asset.get("drift_count", 0)

            print(f"\n  {i}. {name} ({status})")
            print(f"     Asset ID: {asset['asset_id']}")
            print(f"     SHA256: {sha256}")
            print(f"     Last verified: {last_verified}")
            if drift_count > 0:
                print(f"     Drift count: {drift_count}")

        return 0

    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def cmd_verify_all(args: argparse.Namespace) -> int:
    """Verify all assets."""
    try:
        result = verify_all_assets(
            institution_id=args.institution,
            dept_id=args.dept,
            actor_id=args.actor or "system",
        )

        if result.total == 0:
            print(f"No assets to verify for institution {args.institution}")
            return 0

        print(f"Verifying {result.total} assets...")
        for r in result.results:
            status_symbol = "✓" if r.status == "MATCH" else "✗"
            print(f"  {r.name}: {r.status} {status_symbol}")

        print(f"\nSummary:")
        print(f"  {result.ok} assets OK")
        print(f"  {result.drift_detected} drift detected")
        print(f"  {result.missing} missing")
        if result.errors > 0:
            print(f"  {result.errors} errors")

        print(f"\nLedger events emitted: {result.total}")

        return 0 if result.drift_detected == 0 and result.missing == 0 else 1

    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m engine.legacy_bridge",
        description="Legacy Bridge - Read-only governance of legacy assets",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Register command
    register_parser = subparsers.add_parser(
        "register",
        help="Register a new legacy asset",
    )
    register_parser.add_argument(
        "--institution",
        required=True,
        help="Institution UUID",
    )
    register_parser.add_argument(
        "--dept",
        help="Department ID (for multi-dept mode)",
    )
    register_parser.add_argument(
        "--asset-id",
        required=True,
        help="Stable identifier for the asset",
    )
    register_parser.add_argument(
        "--name",
        help="Human-readable name (defaults to asset-id)",
    )
    register_parser.add_argument(
        "--path",
        required=True,
        help="Relative path to the asset file",
    )
    register_parser.add_argument(
        "--format",
        choices=[f.value for f in SourceFormat],
        default=SourceFormat.RAW.value,
        help="Source format (csv, json, xml, raw)",
    )
    register_parser.add_argument(
        "--type",
        choices=[t.value for t in SourceType],
        default=SourceType.FILE.value,
        help="Source type (file, http, dump)",
    )
    register_parser.add_argument(
        "--description",
        help="Optional description",
    )
    register_parser.add_argument(
        "--actor",
        help="Actor ID (defaults to 'system')",
    )
    register_parser.set_defaults(func=cmd_register)

    # Verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify a single asset for drift",
    )
    verify_parser.add_argument(
        "--institution",
        required=True,
        help="Institution UUID",
    )
    verify_parser.add_argument(
        "--dept",
        help="Department ID (for multi-dept mode)",
    )
    verify_parser.add_argument(
        "--asset-id",
        required=True,
        help="Asset identifier to verify",
    )
    verify_parser.add_argument(
        "--actor",
        help="Actor ID (defaults to 'system')",
    )
    verify_parser.set_defaults(func=cmd_verify)

    # List command
    list_parser = subparsers.add_parser(
        "list",
        help="List all registered assets",
    )
    list_parser.add_argument(
        "--institution",
        required=True,
        help="Institution UUID",
    )
    list_parser.add_argument(
        "--dept",
        help="Department ID (for multi-dept mode)",
    )
    list_parser.set_defaults(func=cmd_list)

    # Verify-all command
    verify_all_parser = subparsers.add_parser(
        "verify-all",
        help="Verify all assets for drift",
    )
    verify_all_parser.add_argument(
        "--institution",
        required=True,
        help="Institution UUID",
    )
    verify_all_parser.add_argument(
        "--dept",
        help="Department ID (for multi-dept mode)",
    )
    verify_all_parser.add_argument(
        "--actor",
        help="Actor ID (defaults to 'system')",
    )
    verify_all_parser.set_defaults(func=cmd_verify_all)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
