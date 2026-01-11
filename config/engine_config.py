"""Centralized engine configuration for multi-tenant SaaS execution.

This module provides path configuration that can be injected at runtime,
enabling the engine to run in arbitrary workspaces without hardcoded paths.

Usage:
    from config import get_config, set_config, EngineConfig

    # Set custom workspace for tenant
    set_config(EngineConfig(
        workspace_root="/work/tenant-123/project-456/exec-789",
        templates_root="/shared/templates"
    ))

    # Get current config
    config = get_config()
    output_dir = config.generated_root
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml


# Default paths (for backward compatibility in development)
_DEFAULT_GENERATED_ROOT = "/home/bazari/generated"
_DEFAULT_TEMPLATES_ROOT = "/home/bazari/templates"
_DEFAULT_ENGINE_ROOT = "/home/bazari/engine"
_DEFAULT_STORE_ROOT = "/home/bazari/engine/demo_store"


@dataclass
class EngineConfig:
    """Engine path configuration.

    All paths can be provided explicitly or resolved from environment variables.
    When workspace_root is set, generated_root defaults to workspace_root/generated.

    Attributes:
        workspace_root: Root directory for tenant workspace (e.g., /work/{tenant}/{project}/{exec_id})
        generated_root: Where generated projects are written
        templates_root: Where templates are read from
        engine_root: Engine source root (for blocked paths)
        store_root: Artifacts store root
    """

    workspace_root: Optional[str] = None
    generated_root: Optional[str] = None
    templates_root: Optional[str] = None
    engine_root: Optional[str] = None
    store_root: Optional[str] = None

    def __post_init__(self):
        """Resolve paths from environment or defaults."""
        # If workspace_root is set, derive other paths from it
        if self.workspace_root:
            workspace = Path(self.workspace_root)
            if self.generated_root is None:
                self.generated_root = str(workspace / "generated")
            if self.store_root is None:
                self.store_root = str(workspace / "store")
        else:
            # Fall back to environment variables or defaults
            if self.generated_root is None:
                self.generated_root = os.getenv(
                    "BAZARI_GENERATED_ROOT", _DEFAULT_GENERATED_ROOT
                )
            if self.store_root is None:
                self.store_root = os.getenv(
                    "BAZARI_STORE_ROOT", _DEFAULT_STORE_ROOT
                )

        # Templates and engine root are typically shared across tenants
        if self.templates_root is None:
            self.templates_root = os.getenv(
                "BAZARI_TEMPLATES_ROOT", _DEFAULT_TEMPLATES_ROOT
            )
        if self.engine_root is None:
            self.engine_root = os.getenv(
                "BAZARI_ENGINE_ROOT", _DEFAULT_ENGINE_ROOT
            )

    def get_blocked_paths(self) -> list:
        """Get list of paths that should be blocked from patch operations.

        Returns paths relative to the current configuration, not hardcoded absolutes.
        """
        blocked = []
        if self.engine_root:
            blocked.append(self.engine_root)
        if self.templates_root:
            blocked.append(self.templates_root)
        return blocked

    def get_allowed_paths(self) -> list:
        """Get list of paths allowed for patch operations."""
        allowed = []
        if self.generated_root:
            allowed.append(self.generated_root)
        if self.workspace_root:
            allowed.append(self.workspace_root)
        return allowed

    def is_path_allowed(self, path: str) -> bool:
        """Check if a path is within allowed workspace boundaries.

        Args:
            path: Absolute path to check

        Returns:
            True if path is within allowed boundaries
        """
        abs_path = os.path.abspath(path)

        # Check blocked paths first
        for blocked in self.get_blocked_paths():
            if blocked and abs_path.startswith(os.path.abspath(blocked)):
                return False

        # Check allowed paths
        for allowed in self.get_allowed_paths():
            if allowed and abs_path.startswith(os.path.abspath(allowed)):
                return True

        return False

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "EngineConfig":
        """Load configuration from YAML file.

        Args:
            yaml_path: Path to config/engine.yaml

        Returns:
            EngineConfig instance
        """
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}

        paths = data.get("paths", {})
        return cls(
            workspace_root=paths.get("workspace_root"),
            generated_root=paths.get("generated_root"),
            templates_root=paths.get("templates_root"),
            engine_root=paths.get("engine_root"),
            store_root=paths.get("store_root"),
        )

    @classmethod
    def for_tenant(
        cls,
        tenant_id: str,
        project_id: str,
        execution_id: str,
        base_path: str = "/work",
        templates_root: Optional[str] = None,
    ) -> "EngineConfig":
        """Create configuration for a specific tenant execution.

        Args:
            tenant_id: Tenant identifier
            project_id: Project identifier
            execution_id: Execution identifier
            base_path: Base path for all tenant workspaces
            templates_root: Shared templates root (optional)

        Returns:
            EngineConfig configured for the tenant
        """
        workspace = f"{base_path}/{tenant_id}/{project_id}/{execution_id}"
        return cls(
            workspace_root=workspace,
            templates_root=templates_root,
        )


# Global config instance (thread-local in production)
_current_config: Optional[EngineConfig] = None


def get_config() -> EngineConfig:
    """Get current engine configuration.

    Returns the current configuration, creating a default one if none exists.

    Returns:
        Current EngineConfig instance
    """
    global _current_config
    if _current_config is None:
        _current_config = EngineConfig()
    return _current_config


def set_config(config: EngineConfig) -> None:
    """Set the current engine configuration.

    Args:
        config: EngineConfig instance to use
    """
    global _current_config
    _current_config = config


def reset_config() -> None:
    """Reset configuration to default (for testing)."""
    global _current_config
    _current_config = None
