"""Change Requests module - Governed changes over generated systems.

This module provides:
- IDL Change Request v1: Schema and validation for change requests
"""

from .cr_v1 import (
    # Constants
    CR_SCHEMA_VERSION,
    # Exceptions
    CRValidationError,
    # Core functions
    load_cr,
    validate_cr,
    canonicalize_cr,
    cr_hash_sha256,
    # Helper functions
    create_cr,
    get_cr_id,
    get_previous_episode_id,
    get_risk_level,
    get_target,
    get_entities_affected,
    get_usecases_affected,
)

__all__ = [
    # Constants
    "CR_SCHEMA_VERSION",
    # Exceptions
    "CRValidationError",
    # Core functions
    "load_cr",
    "validate_cr",
    "canonicalize_cr",
    "cr_hash_sha256",
    # Helper functions
    "create_cr",
    "get_cr_id",
    "get_previous_episode_id",
    "get_risk_level",
    "get_target",
    "get_entities_affected",
    "get_usecases_affected",
]
