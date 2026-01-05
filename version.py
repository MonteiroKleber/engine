"""Version module - Identifies engine version at runtime.

Freeze Rules (v1.0.0):
- Schemas only change with version bump
- Templates are versioned
- Policies are immutable

This module reads the VERSION file and provides version info.
"""

from pathlib import Path
from typing import Dict, Any

# Version file location (relative to this module)
VERSION_FILE = Path(__file__).parent / "VERSION"

# Read version from file
def _read_version() -> str:
    """Read version from VERSION file."""
    try:
        return VERSION_FILE.read_text().strip()
    except FileNotFoundError:
        return "0.0.0-dev"


# Module-level version string
__version__ = _read_version()

# Semantic version components
VERSION_PARTS = __version__.split(".")
MAJOR = int(VERSION_PARTS[0]) if len(VERSION_PARTS) > 0 else 0
MINOR = int(VERSION_PARTS[1]) if len(VERSION_PARTS) > 1 else 0
PATCH = int(VERSION_PARTS[2].split("-")[0]) if len(VERSION_PARTS) > 2 else 0

# Version metadata
VERSION_INFO: Dict[str, Any] = {
    "version": __version__,
    "major": MAJOR,
    "minor": MINOR,
    "patch": PATCH,
    "name": "Bazari Engine",
    "codename": "Genesis",
    "release_date": "2026-01-03",
}

# Freeze status - components that are immutable in this version
FROZEN_COMPONENTS = {
    "schemas": True,      # Schemas only change with version bump
    "templates": True,    # Templates are versioned
    "policies": True,     # Policies are immutable
}


def get_version() -> str:
    """Get the current engine version string.

    Returns:
        Version string (e.g., "1.0.0")
    """
    return __version__


def get_version_info() -> Dict[str, Any]:
    """Get detailed version information.

    Returns:
        Dictionary with version details
    """
    return VERSION_INFO.copy()


def is_frozen(component: str) -> bool:
    """Check if a component is frozen in this version.

    Args:
        component: Component name ("schemas", "templates", "policies")

    Returns:
        True if component is frozen
    """
    return FROZEN_COMPONENTS.get(component, False)


def check_compatibility(required_version: str) -> bool:
    """Check if current version is compatible with required version.

    Uses semantic versioning: compatible if same major version
    and current minor >= required minor.

    Args:
        required_version: Required version string (e.g., "1.0.0")

    Returns:
        True if compatible
    """
    try:
        parts = required_version.split(".")
        req_major = int(parts[0])
        req_minor = int(parts[1]) if len(parts) > 1 else 0

        # Same major, current minor >= required minor
        return MAJOR == req_major and MINOR >= req_minor
    except (ValueError, IndexError):
        return False


def version_string() -> str:
    """Get formatted version string for display.

    Returns:
        Formatted string (e.g., "Bazari Engine v1.0.0 (Genesis)")
    """
    return f"{VERSION_INFO['name']} v{__version__} ({VERSION_INFO['codename']})"
