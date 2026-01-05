"""IDL - Institutional Definition Language.

Este modulo contem:
- Parser para linguagem IDL v1
- Canonizacao deterministica
- Persistencia com Contract Gate
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

__all__ = [
    # Schema
    "IDL_SCHEMA_VERSION",
    # Document
    "IDLDocument",
    # Parser
    "IDLParser",
    # Hashing
    "compute_content_hash_sha256",
    "extract_hashable_payload_from_canonical",
    "HASHABLE_FIELDS",
    # Store
    "IDLStore",
]
