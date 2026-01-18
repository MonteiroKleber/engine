"""RBAC - Role-Based Access Control gate."""

from typing import Any, Dict, List, Optional, Set

from .actor_context import ActorContext


class RBACPolicy:
    """RBAC policy loaded from rbac.json contract."""

    def __init__(self, rbac_data: Dict[str, Any]) -> None:
        """Initialize RBAC policy from contract data.

        Args:
            rbac_data: Parsed rbac.json content.
        """
        self._role_permissions: Dict[str, Set[str]] = {}
        self._load_roles(rbac_data)

    def _load_roles(self, rbac_data: Dict[str, Any]) -> None:
        """Load roles and their permissions from rbac data."""
        roles = rbac_data.get("roles", [])
        for role in roles:
            role_name = role.get("name")
            permissions = role.get("permissions", [])
            if role_name:
                self._role_permissions[role_name] = set(permissions)

    def get_permissions_for_roles(self, roles: List[str]) -> Set[str]:
        """Get all permissions for a list of roles.

        Args:
            roles: List of role names.

        Returns:
            Set of all permissions granted by those roles.
        """
        permissions: Set[str] = set()
        for role in roles:
            if role in self._role_permissions:
                permissions.update(self._role_permissions[role])
        return permissions

    def has_permission(self, roles: List[str], permission: str) -> bool:
        """Check if any of the roles grant a specific permission.

        Args:
            roles: List of role names.
            permission: Permission to check.

        Returns:
            True if permission is granted, False otherwise.
        """
        permissions = self.get_permissions_for_roles(roles)
        return permission in permissions


# Global RBAC policy (set by loader)
_rbac_policy: Optional[RBACPolicy] = None


def set_rbac_policy(policy: Optional[RBACPolicy]) -> None:
    """Set the global RBAC policy."""
    global _rbac_policy
    _rbac_policy = policy


def get_rbac_policy() -> Optional[RBACPolicy]:
    """Get the global RBAC policy."""
    return _rbac_policy


def gate_rbac(permission: str, actor_context: ActorContext) -> bool:
    """Check if actor has permission via RBAC.

    Args:
        permission: Permission to check.
        actor_context: Actor context with roles.

    Returns:
        True if allowed, False if denied.
    """
    policy = get_rbac_policy()
    if policy is None:
        # No policy loaded - deny by default
        return False

    return policy.has_permission(actor_context.roles, permission)
