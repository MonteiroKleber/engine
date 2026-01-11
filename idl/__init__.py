"""IDL - Institutional Definition Language.

Este modulo contem:
- Parser para linguagem IDL v1
- Canonizacao deterministica
- Persistencia com Contract Gate
- IDL Draft v1 (pre-canonico)
- Draft → IDL Compiler
"""

from .idl_v1 import (
    IDL_SCHEMA_VERSION,
    IDLDocument,
    IDLParser,
    compute_content_hash_sha256,
    extract_hashable_payload_from_canonical,
    HASHABLE_FIELDS,
)
from .idl_store import (
    IDLStore,
)
from .idl_draft_v1 import (
    IDL_DRAFT_SCHEMA_VERSION,
    IDLDraftV1,
    DraftSource,
    DraftActor,
    DraftEntity,
    DraftField,
    DraftUseCase,
    DraftFlowStep,
    DraftIntegration,
    DraftNonFunctional,
    is_unknown,
    UNKNOWN,
)
from .idl_draft_schema import (
    DraftSchemaValidator,
    DraftValidationResult,
    DraftValidationError,
)
from .idl_compile import (
    DraftToIDLCompiler,
    CompileResult,
    CompileBlockingError,
    DraftNotCompileableError,
    compile_draft_to_idl,
    compile_draft_to_idl_or_raise,
)
from .idl_to_ir import (
    idl_to_ir,
    IDLToIRError,
)

__all__ = [
    # IDL v1 Schema
    "IDL_SCHEMA_VERSION",
    # IDL Document
    "IDLDocument",
    # IDL Parser
    "IDLParser",
    # Hashing
    "compute_content_hash_sha256",
    "extract_hashable_payload_from_canonical",
    "HASHABLE_FIELDS",
    # Store
    "IDLStore",
    # IDL Draft v1
    "IDL_DRAFT_SCHEMA_VERSION",
    "IDLDraftV1",
    "DraftSource",
    "DraftActor",
    "DraftEntity",
    "DraftField",
    "DraftUseCase",
    "DraftFlowStep",
    "DraftIntegration",
    "DraftNonFunctional",
    "is_unknown",
    "UNKNOWN",
    # Draft Schema Validator
    "DraftSchemaValidator",
    "DraftValidationResult",
    "DraftValidationError",
    # Draft Compiler
    "DraftToIDLCompiler",
    "CompileResult",
    "CompileBlockingError",
    "DraftNotCompileableError",
    "compile_draft_to_idl",
    "compile_draft_to_idl_or_raise",
    # IDL to IR Converter
    "idl_to_ir",
    "IDLToIRError",
]
