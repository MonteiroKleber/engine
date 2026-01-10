"""AuditPack module - Generate auditable ZIP packages from episodes.

This module provides functionality to create reproducible, verifiable
audit packages from episode directories.
"""

from .auditpack import (
    # Constants
    AUDITPACK_INDEX_SCHEMA_VERSION,
    FORBIDDEN_PATTERNS,
    # Exceptions
    AuditPackError,
    AuditPackSecurityError,
    AuditPackValidationError,
    # Core functions
    build_auditpack,
    compute_auditpack_index,
    compute_root_hash,
    verify_no_secrets,
    validate_auditpack_index,
    # Helper functions
    generate_readme_audit,
    generate_sha256sums,
)

__all__ = [
    # Constants
    "AUDITPACK_INDEX_SCHEMA_VERSION",
    "FORBIDDEN_PATTERNS",
    # Exceptions
    "AuditPackError",
    "AuditPackSecurityError",
    "AuditPackValidationError",
    # Core functions
    "build_auditpack",
    "compute_auditpack_index",
    "compute_root_hash",
    "verify_no_secrets",
    "validate_auditpack_index",
    # Helper functions
    "generate_readme_audit",
    "generate_sha256sums",
]
