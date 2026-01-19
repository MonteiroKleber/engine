"""
CLI entry point for IDL DSL v1.2.2 parser.

Usage:
    python -m engine.idl_dsl finance.idl -o ir.json
    python -m engine.idl_dsl finance.idl --stdout
    python -m engine.idl_dsl finance.idl --validate
"""

import argparse
import sys
import json
from pathlib import Path

from .lexer import Lexer
from .parser import Parser
from .ircs_emit import IRCSEmitter
from .errors import IDLError


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m engine.idl_dsl",
        description="IDL DSL v1.2.2 to IRCS v1 converter",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input IDL DSL file (.idl)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output IRCS v1 JSON file",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON to stdout instead of file",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Only validate, don't emit",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (default: 2)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress info messages",
    )

    args = parser.parse_args()

    # Read input file
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    try:
        source = args.input.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading input file: {e}", file=sys.stderr)
        return 1

    # Parse and emit
    try:
        tokens = Lexer(source).tokenize()
        if not args.quiet:
            print(f"Lexer: {len(tokens)} tokens", file=sys.stderr)

        ast = Parser(tokens, source).parse()
        if not args.quiet:
            print("Parser: OK", file=sys.stderr)

        if args.validate:
            print("Validation: OK")
            return 0

        emitter = IRCSEmitter(ast, source)
        ir = emitter.emit()

        if not args.quiet:
            print(f"Emitter: source_idl_sha256={ir['source_idl_sha256'][:16]}...", file=sys.stderr)

        json_output = json.dumps(ir, indent=args.indent, sort_keys=True, ensure_ascii=False)

        if args.stdout:
            print(json_output)
        elif args.output:
            args.output.write_text(json_output, encoding="utf-8")
            if not args.quiet:
                print(f"Written: {args.output}", file=sys.stderr)
        else:
            # Default output name
            output_path = args.input.with_suffix(".ir.json")
            output_path.write_text(json_output, encoding="utf-8")
            if not args.quiet:
                print(f"Written: {output_path}", file=sys.stderr)

        return 0

    except IDLError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Internal error: {e}", file=sys.stderr)
        if not args.quiet:
            import traceback
            traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
