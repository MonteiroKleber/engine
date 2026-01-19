"""Preflight checks for multi-tenant path isolation.

This module validates that environment configuration doesn't break
multi-tenant isolation when require_institution_header_for_runtime is active.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from engine.core.errors import (
    PATH_MISCONFIG_ABSOLUTE_LEDGER,
    PATH_MISCONFIG_ABSOLUTE_STATE_STORE,
)


@dataclass
class PreflightResult:
    """Result of preflight check."""

    ok: bool
    code: Optional[str] = None
    message: Optional[str] = None
    details: Optional[List[str]] = None


# Critical ENV variables that must NOT be absolute paths in multi-tenant mode
CRITICAL_PATH_ENVS = {
    "ENGINE_LEDGER_PATH": PATH_MISCONFIG_ABSOLUTE_LEDGER,
    "ENGINE_STATE_STORE_DIR": PATH_MISCONFIG_ABSOLUTE_STATE_STORE,
}


def check_path_isolation(require_multi_tenant: bool = False) -> PreflightResult:
    """Check that critical path ENVs don't break multi-tenant isolation.

    When multi-tenant mode is active (require_institution_header_for_runtime=true
    for any registered institution), absolute paths for ledger and state store
    would cause all institutions to share the same storage, breaking isolation.

    Args:
        require_multi_tenant: If True, enforces that critical paths are not absolute.
                              This should be True when any institution has
                              require_institution_header_for_runtime=true.

    Returns:
        PreflightResult with ok=True if safe, or ok=False with error details.
    """
    if not require_multi_tenant:
        # Not in multi-tenant mode - allow any configuration
        return PreflightResult(ok=True)

    violations = []

    for env_name, error_code in CRITICAL_PATH_ENVS.items():
        env_value = os.environ.get(env_name)
        if env_value is not None and Path(env_value).is_absolute():
            violations.append(
                f"{env_name}={env_value} is absolute; "
                f"this bypasses institution namespace and breaks multi-tenant isolation"
            )

    if violations:
        # Return first violation as primary error
        first_env = list(CRITICAL_PATH_ENVS.keys())[0]
        for env_name, error_code in CRITICAL_PATH_ENVS.items():
            env_value = os.environ.get(env_name)
            if env_value is not None and Path(env_value).is_absolute():
                return PreflightResult(
                    ok=False,
                    code=error_code,
                    message=(
                        f"Multi-tenant mode requires namespaced paths. "
                        f"{env_name} cannot be an absolute path when "
                        f"require_institution_header_for_runtime=true."
                    ),
                    details=violations,
                )

    return PreflightResult(ok=True)


def is_multi_tenant_mode_active() -> bool:
    """Check if multi-tenant mode is active.

    Multi-tenant mode is considered active when ANY registered institution
    has require_institution_header_for_runtime=true in its config.

    This is a startup-time check that scans existing institution configs.

    Returns:
        True if any institution requires institutional isolation.
    """
    from engine.core.institutions import get_registry
    from engine.core.institution_config import get_effective_config

    try:
        registry = get_registry()
        institutions = registry.list_institutions(limit=1000)  # Reasonable limit
        for inst in institutions:
            try:
                config = get_effective_config(inst.institution_id)
                if config.flags.require_institution_header_for_runtime:
                    return True
            except Exception:
                # Skip institutions with config errors
                continue
        return False
    except Exception:
        # If we can't read institutions, assume not multi-tenant
        return False


def run_preflight_checks() -> PreflightResult:
    """Run all preflight checks.

    This should be called at startup to validate configuration.

    Returns:
        PreflightResult with ok=True if all checks pass.
    """
    # Check 1: Path isolation in multi-tenant mode
    multi_tenant_active = is_multi_tenant_mode_active()
    path_check = check_path_isolation(require_multi_tenant=multi_tenant_active)

    if not path_check.ok:
        return path_check

    # All checks passed
    return PreflightResult(ok=True)
