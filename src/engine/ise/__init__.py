"""ISE (IDL to Structured Executable) Compiler."""

from .compiler import (
    compile_bundle,
    compile_bundle_to_memory,
    compile_from_ircs,
    compile_from_ircs_file,
    CompileResult,
)
from .idl_parser import parse_idl, ParsedIDL
from .manifest import generate_manifest, sha256_str
from .contract_ledger import generate_contract_ledger
from .ircs_adapter import ircs_to_parsed_idl, load_ircs_from_file, IRCSAdapterError
from . import errors

__all__ = [
    # Legacy compilation (JSON-IDL ad-hoc)
    "compile_bundle",
    "compile_bundle_to_memory",
    # IRCS v1 compilation (canonical path)
    "compile_from_ircs",
    "compile_from_ircs_file",
    "ircs_to_parsed_idl",
    "load_ircs_from_file",
    "IRCSAdapterError",
    # Common
    "CompileResult",
    "parse_idl",
    "ParsedIDL",
    "generate_manifest",
    "generate_contract_ledger",
    "sha256_str",
    "errors",
]
