"""Impact Gate - Pre-patch deterministic impact analysis.

This module provides a deterministic gate that analyzes the impact of a
proposed change BEFORE the patch engine runs. It ensures changes stay
within the approved scope defined in the Change Request.

Key rules:
- Target-to-paths mapping is explicit and deterministic
- Forbidden paths are always blocked (security)
- Scope limits prevent overly broad changes
- All decisions are reproducible given the same input

Error prefixes:
- IMPACT: for gate-level errors

blocked_reason values:
- IMPACT_OUT_OF_SCOPE: Path doesn't match target's allowed prefixes
- IMPACT_TOO_BROAD: Too many files or directories affected
- IMPACT_FORBIDDEN_PATH: Path is forbidden (security)
- IMPACT_GATE_BLOCKED: Generic gate block (for runlog)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


# =============================================================================
# Constants
# =============================================================================


class ImpactBlockedReason(str, Enum):
    """Reasons for impact gate blocking."""

    OUT_OF_SCOPE = "IMPACT_OUT_OF_SCOPE"
    TOO_BROAD = "IMPACT_TOO_BROAD"
    FORBIDDEN_PATH = "IMPACT_FORBIDDEN_PATH"


# Target to allowed path prefixes mapping
# This is explicit and deterministic - adjust for actual repo structure
TARGET_PATH_MAPPING: Dict[str, List[str]] = {
    "frontend": ["apps/web/", "frontend/", "ui/", "src/components/", "src/pages/"],
    "backend": ["services/", "backend/", "api/", "src/api/", "src/services/"],
    "db": ["db/", "migrations/", "database/", "sql/"],
    "api": ["openapi/", "contracts/", "api/specs/", "swagger/"],
    "rbac": ["rbac/", "authz/", "auth/", "permissions/"],
    "infra": ["deploy/", "docker/", "k8s/", "terraform/", "infrastructure/"],
    "docs": ["docs/", "documentation/", "README", "CHANGELOG"],
}

# Forbidden path patterns (security)
FORBIDDEN_PATTERNS: List[str] = [
    ".git/",
    "secrets/",
    ".env",
    ".secrets",
    "credentials/",
    "private_keys/",
]

# Scope limits (configurable constants)
MAX_AFFECTED_FILES = 25
MAX_UNIQUE_TOP_DIRS = 4


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class ImpactMetrics:
    """Metrics about the impact of a change."""

    affected_files: int
    unique_top_dirs: int
    top_dirs: List[str] = field(default_factory=list)


@dataclass
class ImpactGateResult:
    """Result of an impact gate check."""

    allowed: bool
    blocked_reason: Optional[ImpactBlockedReason]
    errors: List[str]
    error_codes: List[str]
    metrics: ImpactMetrics

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "allowed": self.allowed,
            "blocked_reason": self.blocked_reason.value if self.blocked_reason else None,
            "errors": self.errors,
            "error_codes": self.error_codes,
            "metrics": {
                "affected_files": self.metrics.affected_files,
                "unique_top_dirs": self.metrics.unique_top_dirs,
                "top_dirs": self.metrics.top_dirs,
            },
        }


# =============================================================================
# Exceptions
# =============================================================================


class ImpactGateError(Exception):
    """Exception raised when impact gate check fails.

    Error messages are prefixed with "IMPACT: " following project conventions.
    """

    def __init__(self, message: str, error_code: str = "IMPACT_GATE_BLOCKED"):
        self.message = message
        self.error_code = error_code
        super().__init__(f"IMPACT: {message}")


# =============================================================================
# Helper Functions
# =============================================================================


def _normalize_path(path: str) -> str:
    """Normalize a path for consistent comparison.

    Args:
        path: Path to normalize

    Returns:
        Normalized path (forward slashes, no leading slash)
    """
    # Replace backslashes with forward slashes
    normalized = path.replace("\\", "/")

    # Remove leading slash
    if normalized.startswith("/"):
        normalized = normalized[1:]

    return normalized


def _get_top_dir(path: str) -> str:
    """Get the top-level directory from a path.

    Args:
        path: Normalized path

    Returns:
        Top-level directory name
    """
    parts = path.split("/")
    return parts[0] if parts else ""


def _check_path_traversal(path: str) -> bool:
    """Check if a path contains path traversal attempts.

    Args:
        path: Path to check

    Returns:
        True if path contains ".." (traversal attempt)
    """
    return ".." in path


def _check_forbidden_path(path: str) -> Optional[str]:
    """Check if a path matches any forbidden pattern.

    Args:
        path: Normalized path to check

    Returns:
        Matched forbidden pattern, or None if allowed
    """
    normalized = path.lower()

    for pattern in FORBIDDEN_PATTERNS:
        pattern_lower = pattern.lower()
        if pattern_lower in normalized:
            return pattern

    return None


def _check_path_in_scope(path: str, target: str) -> bool:
    """Check if a path is within the allowed scope for a target.

    Args:
        path: Normalized path to check
        target: Target area from CR (frontend, backend, etc.)

    Returns:
        True if path is in scope for the target
    """
    allowed_prefixes = TARGET_PATH_MAPPING.get(target, [])

    if not allowed_prefixes:
        # Unknown target - no paths allowed
        return False

    path_lower = path.lower()

    for prefix in allowed_prefixes:
        prefix_lower = prefix.lower()
        if path_lower.startswith(prefix_lower):
            return True

    return False


def _compute_metrics(paths: List[str]) -> ImpactMetrics:
    """Compute impact metrics from a list of paths.

    Args:
        paths: List of normalized paths

    Returns:
        ImpactMetrics with computed values
    """
    top_dirs: Set[str] = set()

    for path in paths:
        top_dir = _get_top_dir(path)
        if top_dir:
            top_dirs.add(top_dir)

    sorted_dirs = sorted(top_dirs)

    return ImpactMetrics(
        affected_files=len(paths),
        unique_top_dirs=len(top_dirs),
        top_dirs=sorted_dirs,
    )


# =============================================================================
# Impact Gate
# =============================================================================


class ImpactGate:
    """Deterministic gate for pre-patch impact analysis.

    Analyzes the impact of a proposed change and decides whether
    to allow or block based on:
    - Target scope (paths must match target's allowed prefixes)
    - Breadth limits (max files, max directories)
    - Security (forbidden paths)
    """

    def __init__(
        self,
        max_affected_files: int = MAX_AFFECTED_FILES,
        max_unique_top_dirs: int = MAX_UNIQUE_TOP_DIRS,
    ):
        """Initialize the impact gate.

        Args:
            max_affected_files: Maximum number of affected files allowed
            max_unique_top_dirs: Maximum number of unique top directories
        """
        self.max_affected_files = max_affected_files
        self.max_unique_top_dirs = max_unique_top_dirs

    def check(
        self,
        cr: dict,
        affected_paths: List[str],
        patch_manifest: Optional[dict] = None,
    ) -> ImpactGateResult:
        """Check if the proposed change is allowed.

        Args:
            cr: Change request dict (canonical)
            affected_paths: List of paths that will be affected
            patch_manifest: Optional patch manifest (for future use)

        Returns:
            ImpactGateResult with decision and details
        """
        errors: List[str] = []
        error_codes: List[str] = []

        # Get target from CR
        target = cr.get("scope", {}).get("target", "")

        # Normalize all paths
        normalized_paths = [_normalize_path(p) for p in affected_paths]

        # Remove empty paths
        normalized_paths = [p for p in normalized_paths if p]

        # Sort for deterministic processing
        normalized_paths = sorted(normalized_paths)

        # Compute metrics
        metrics = _compute_metrics(normalized_paths)

        # Check 1: Forbidden paths (security - checked first)
        for path in normalized_paths:
            # Check path traversal
            if _check_path_traversal(path):
                errors.append(f"IMPACT: Forbidden path traversal detected: {path}")
                error_codes.append(ImpactBlockedReason.FORBIDDEN_PATH.value)

            # Check forbidden patterns
            forbidden_match = _check_forbidden_path(path)
            if forbidden_match:
                errors.append(
                    f"IMPACT: Forbidden path pattern '{forbidden_match}' in: {path}"
                )
                error_codes.append(ImpactBlockedReason.FORBIDDEN_PATH.value)

        if errors:
            return ImpactGateResult(
                allowed=False,
                blocked_reason=ImpactBlockedReason.FORBIDDEN_PATH,
                errors=errors,
                error_codes=error_codes,
                metrics=metrics,
            )

        # Check 2: Scope limits (too broad)
        if metrics.affected_files > self.max_affected_files:
            errors.append(
                f"IMPACT: Too many affected files: {metrics.affected_files} "
                f"(max: {self.max_affected_files})"
            )
            error_codes.append(ImpactBlockedReason.TOO_BROAD.value)

        if metrics.unique_top_dirs > self.max_unique_top_dirs:
            errors.append(
                f"IMPACT: Too many top-level directories: {metrics.unique_top_dirs} "
                f"(max: {self.max_unique_top_dirs})"
            )
            error_codes.append(ImpactBlockedReason.TOO_BROAD.value)

        if errors:
            return ImpactGateResult(
                allowed=False,
                blocked_reason=ImpactBlockedReason.TOO_BROAD,
                errors=errors,
                error_codes=error_codes,
                metrics=metrics,
            )

        # Check 3: Target scope (out of scope)
        out_of_scope_paths: List[str] = []
        for path in normalized_paths:
            if not _check_path_in_scope(path, target):
                out_of_scope_paths.append(path)

        if out_of_scope_paths:
            allowed_prefixes = TARGET_PATH_MAPPING.get(target, [])
            for path in out_of_scope_paths:
                errors.append(
                    f"IMPACT: Path '{path}' not in scope for target '{target}'. "
                    f"Allowed prefixes: {allowed_prefixes}"
                )
                error_codes.append(ImpactBlockedReason.OUT_OF_SCOPE.value)

            return ImpactGateResult(
                allowed=False,
                blocked_reason=ImpactBlockedReason.OUT_OF_SCOPE,
                errors=errors,
                error_codes=error_codes,
                metrics=metrics,
            )

        # All checks passed
        return ImpactGateResult(
            allowed=True,
            blocked_reason=None,
            errors=[],
            error_codes=[],
            metrics=metrics,
        )

    def require_allowed(
        self,
        cr: dict,
        affected_paths: List[str],
        patch_manifest: Optional[dict] = None,
    ) -> ImpactGateResult:
        """Require that the change is allowed, raising on failure.

        Args:
            cr: Change request dict (canonical)
            affected_paths: List of paths that will be affected
            patch_manifest: Optional patch manifest

        Returns:
            ImpactGateResult (only if allowed)

        Raises:
            ImpactGateError: If the change is blocked
        """
        result = self.check(cr, affected_paths, patch_manifest)

        if not result.allowed:
            error_msg = "; ".join(result.errors) if result.errors else "Impact gate blocked"
            raise ImpactGateError(
                error_msg,
                error_code=result.blocked_reason.value if result.blocked_reason else "IMPACT_GATE_BLOCKED",
            )

        return result


# =============================================================================
# Convenience Functions
# =============================================================================


def check_impact(
    cr: dict,
    affected_paths: List[str],
    patch_manifest: Optional[dict] = None,
    max_affected_files: int = MAX_AFFECTED_FILES,
    max_unique_top_dirs: int = MAX_UNIQUE_TOP_DIRS,
) -> ImpactGateResult:
    """Check the impact of a proposed change.

    Convenience function for one-off checks.

    Args:
        cr: Change request dict (canonical)
        affected_paths: List of paths that will be affected
        patch_manifest: Optional patch manifest
        max_affected_files: Maximum number of affected files
        max_unique_top_dirs: Maximum number of unique top directories

    Returns:
        ImpactGateResult with decision and details
    """
    gate = ImpactGate(
        max_affected_files=max_affected_files,
        max_unique_top_dirs=max_unique_top_dirs,
    )
    return gate.check(cr, affected_paths, patch_manifest)


def derive_affected_paths_from_manifest(patch_manifest: dict) -> List[str]:
    """Derive affected paths from a patch manifest.

    Args:
        patch_manifest: Patch manifest dict

    Returns:
        List of affected paths
    """
    paths: List[str] = []

    # Extract from files list if present
    files = patch_manifest.get("files", [])
    for file_entry in files:
        if isinstance(file_entry, str):
            paths.append(file_entry)
        elif isinstance(file_entry, dict):
            path = file_entry.get("path") or file_entry.get("file")
            if path:
                paths.append(path)

    # Extract from patches list if present
    patches = patch_manifest.get("patches", [])
    for patch in patches:
        if isinstance(patch, dict):
            path = patch.get("path") or patch.get("file")
            if path:
                paths.append(path)

    # Remove duplicates while preserving order
    seen: Set[str] = set()
    unique_paths: List[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)

    return unique_paths


def get_target_allowed_prefixes(target: str) -> List[str]:
    """Get the allowed path prefixes for a target.

    Args:
        target: Target area (frontend, backend, etc.)

    Returns:
        List of allowed path prefixes
    """
    return TARGET_PATH_MAPPING.get(target, [])


def is_path_allowed_for_target(path: str, target: str) -> bool:
    """Check if a path is allowed for a specific target.

    Args:
        path: Path to check
        target: Target area

    Returns:
        True if path is allowed for target
    """
    normalized = _normalize_path(path)
    return _check_path_in_scope(normalized, target)
