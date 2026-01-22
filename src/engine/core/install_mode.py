"""Install Mode - production vs development mode configuration.

Supports two installation modes via ENGINE_INSTALL_MODE:
- dev: Development mode with relaxed constraints (default)
- prod: Production mode with strict security enforcement

GAP 3: In prod mode, critical writes without approval rules are denied.
"""

import os
from enum import Enum


class InstallMode(Enum):
    """Installation mode for the engine."""

    DEV = "dev"  # Development mode (relaxed, for testing)
    PROD = "prod"  # Production mode (strict enforcement)


def get_install_mode() -> InstallMode:
    """Get installation mode from ENGINE_INSTALL_MODE env var.

    Returns:
        InstallMode.DEV if not set or "dev", InstallMode.PROD if "prod".
    """
    mode = os.environ.get("ENGINE_INSTALL_MODE", "dev").lower()
    if mode == "prod":
        return InstallMode.PROD
    return InstallMode.DEV


def is_prod_mode() -> bool:
    """Check if running in production mode.

    Returns:
        True if ENGINE_INSTALL_MODE=prod.
    """
    return get_install_mode() == InstallMode.PROD


def is_dev_mode() -> bool:
    """Check if running in development mode.

    Returns:
        True if ENGINE_INSTALL_MODE is not set or is "dev".
    """
    return get_install_mode() == InstallMode.DEV
