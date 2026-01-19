"""CLI entry point for ISE compiler.

Usage:
    python -m engine.ise compile-ircs path/to/ir.json -o out_bundle_dir
    python -m engine.ise compile-ircs path/to/ir.json --bundle-name my-bundle
"""

import argparse
import sys
import json
from pathlib import Path

from .compiler import compile_from_ircs_file, compile_from_ircs
from .ircs_adapter import load_ircs_from_file, IRCSAdapterError


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m engine.ise",
        description="ISE Compiler - IRCS v1 to Bundle",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # compile-ircs subcommand
    compile_parser = subparsers.add_parser(
        "compile-ircs",
        help="Compile IRCS v1 JSON to executable bundle",
    )
    compile_parser.add_argument(
        "input",
        type=Path,
        help="Input IRCS v1 JSON file (ir.json)",
    )
    compile_parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("bundles"),
        help="Output directory for bundle (default: bundles/)",
    )
    compile_parser.add_argument(
        "--bundle-name",
        type=str,
        default=None,
        help="Bundle name (default: derived from IRCS v1 system name)",
    )
    compile_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress info messages",
    )

    args = parser.parse_args()

    if args.command == "compile-ircs":
        return _cmd_compile_ircs(args)
    else:
        parser.print_help()
        return 1


def _cmd_compile_ircs(args) -> int:
    """Handle compile-ircs command."""
    input_path = args.input
    output_dir = args.output_dir
    bundle_name = args.bundle_name
    quiet = args.quiet

    # Validate input exists
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    # Load IRCS v1
    try:
        ir = load_ircs_from_file(str(input_path))
    except IRCSAdapterError as e:
        print(f"Error: {e.message}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading IRCS v1: {e}", file=sys.stderr)
        return 1

    if not quiet:
        ir_version = ir.get("ir_version", "unknown")
        source_version = ir.get("source_idl_version", "unknown")
        print(f"Loaded IRCS: ir_version={ir_version}, source={source_version}", file=sys.stderr)

    # Derive bundle name if not provided
    if not bundle_name:
        system = ir.get("system", {})
        bundle_name = system.get("id") or system.get("name") or "ircs-bundle"
        # Sanitize for filesystem
        bundle_name = bundle_name.lower().replace(" ", "-")

    if not quiet:
        print(f"Bundle name: {bundle_name}", file=sys.stderr)

    # Compile
    result = compile_from_ircs(ir, bundle_name, str(output_dir))

    if not result.success:
        print(f"Error: {result.error_message}", file=sys.stderr)
        if result.error_code:
            print(f"Code: {result.error_code}", file=sys.stderr)
        return 1

    if not quiet:
        print(f"Compiled: {result.bundle_path}", file=sys.stderr)
        print(f"Contracts: {len(result.contracts)}", file=sys.stderr)
        print(f"Bundle hash: {result.bundle_hash[:16]}...", file=sys.stderr)

    # Output bundle path for scripting
    print(result.bundle_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
