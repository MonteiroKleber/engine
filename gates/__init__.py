"""Gates module - Pre-execution gates for governed changes.

This module provides:
- Impact Gate: Pre-patch deterministic impact analysis
"""

from .impact_gate import (
    # Constants
    TARGET_PATH_MAPPING,
    FORBIDDEN_PATTERNS,
    MAX_AFFECTED_FILES,
    MAX_UNIQUE_TOP_DIRS,
    # Enums
    ImpactBlockedReason,
    # Result types
    ImpactMetrics,
    ImpactGateResult,
    # Exceptions
    ImpactGateError,
    # Gate class
    ImpactGate,
    # Convenience functions
    check_impact,
    derive_affected_paths_from_manifest,
    get_target_allowed_prefixes,
    is_path_allowed_for_target,
)

__all__ = [
    # Constants
    "TARGET_PATH_MAPPING",
    "FORBIDDEN_PATTERNS",
    "MAX_AFFECTED_FILES",
    "MAX_UNIQUE_TOP_DIRS",
    # Enums
    "ImpactBlockedReason",
    # Result types
    "ImpactMetrics",
    "ImpactGateResult",
    # Exceptions
    "ImpactGateError",
    # Gate class
    "ImpactGate",
    # Convenience functions
    "check_impact",
    "derive_affected_paths_from_manifest",
    "get_target_allowed_prefixes",
    "is_path_allowed_for_target",
]
