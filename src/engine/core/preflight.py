"""Preflight checks for secure engine startup.

This module validates environment configuration at startup:
- Multi-tenant path isolation (Etapa 2.6)
- Console session secret (Etapa 4.1)
- Production mode security requirements (GAP 5)
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from engine.core.errors import (
    PATH_MISCONFIG_ABSOLUTE_LEDGER,
    PATH_MISCONFIG_ABSOLUTE_STATE_STORE,
    CONSOLE_SESSION_SECRET_MISSING,
    PREFLIGHT_ADMIN_TOKEN_MISSING,
    PREFLIGHT_AUTH_MODE_INSECURE,
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


def check_console_session_secret() -> PreflightResult:
    """Check that console session secret is configured.

    This is required for browser-based auth (Etapa 4.1).

    Returns:
        PreflightResult with ok=True if configured.
    """
    from engine.console.session import check_session_secret_configured

    ok, error_message = check_session_secret_configured()
    if not ok:
        return PreflightResult(
            ok=False,
            code=CONSOLE_SESSION_SECRET_MISSING,
            message=error_message,
            details=[error_message],
        )
    return PreflightResult(ok=True)


def check_prod_mode_requirements() -> PreflightResult:
    """Check production mode security requirements.

    GAP 5: In ENGINE_INSTALL_MODE=prod, enforce:
    - ENGINE_ISE_ADMIN_TOKEN must be set (admin API authentication)
    - ENGINE_AUTH_MODE must be 'strict' (identity verification via tokens)

    In dev mode, these checks are skipped for backward compatibility.

    Returns:
        PreflightResult with ok=True if requirements met or dev mode.
    """
    from engine.core.install_mode import is_prod_mode

    if not is_prod_mode():
        # Dev mode - skip production security checks
        return PreflightResult(ok=True)

    # Check 1: Admin token must be set in prod mode
    admin_token = os.environ.get("ENGINE_ISE_ADMIN_TOKEN")
    if not admin_token:
        return PreflightResult(
            ok=False,
            code=PREFLIGHT_ADMIN_TOKEN_MISSING,
            message=(
                "Production mode (ENGINE_INSTALL_MODE=prod) requires "
                "ENGINE_ISE_ADMIN_TOKEN to be set. This token is used for "
                "admin API authentication (/admin/* endpoints). "
                "Generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            ),
            details=[
                "ENGINE_ISE_ADMIN_TOKEN is not set",
                "Admin APIs would be inaccessible without authentication",
            ],
        )

    # Check 2: Auth mode must be strict in prod mode
    auth_mode = os.environ.get("ENGINE_AUTH_MODE", "dev").lower()
    if auth_mode != "strict":
        return PreflightResult(
            ok=False,
            code=PREFLIGHT_AUTH_MODE_INSECURE,
            message=(
                f"Production mode (ENGINE_INSTALL_MODE=prod) requires "
                f"ENGINE_AUTH_MODE=strict. Current value: '{auth_mode}'. "
                "Strict mode ensures actor identity is verified via tokens, "
                "preventing identity spoofing through headers."
            ),
            details=[
                f"ENGINE_AUTH_MODE is '{auth_mode}', expected 'strict'",
                "Dev mode allows unverified identity headers (X-Actor-Id)",
                "Set ENGINE_AUTH_MODE=strict for production security",
            ],
        )

    return PreflightResult(ok=True)


def run_preflight_checks() -> PreflightResult:
    """Run all preflight checks.

    This should be called at startup to validate configuration.
    Checks run in order:
    1. Path isolation (multi-tenant mode)
    2. Console session secret
    3. Production mode requirements (GAP 5)

    Returns:
        PreflightResult with ok=True if all checks pass.
    """
    # Check 1: Path isolation in multi-tenant mode
    multi_tenant_active = is_multi_tenant_mode_active()
    path_check = check_path_isolation(require_multi_tenant=multi_tenant_active)

    if not path_check.ok:
        return path_check

    # Check 2: Console session secret (Etapa 4.1)
    session_check = check_console_session_secret()
    if not session_check.ok:
        return session_check

    # Check 3: Production mode requirements (GAP 5)
    prod_check = check_prod_mode_requirements()
    if not prod_check.ok:
        return prod_check

    # All checks passed
    return PreflightResult(ok=True)
