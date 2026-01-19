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


# Global RBAC policy (set by loader for single-mode)
_rbac_policy: Optional[RBACPolicy] = None

# Per-department RBAC policies (for multi-mode)
# Key: dept_id (or None for single mode)
_rbac_policies: Dict[Optional[str], RBACPolicy] = {}


def set_rbac_policy(policy: Optional[RBACPolicy], dept_id: Optional[str] = None) -> None:
    """Set RBAC policy for a department (or global for single mode).

    Args:
        policy: RBACPolicy instance, or None to clear.
        dept_id: Department ID, or None for single/global mode.
    """
    global _rbac_policy
    if dept_id is None:
        # Single mode - set global policy
        _rbac_policy = policy
    else:
        # Multi mode - set per-department policy
        if policy is None:
            _rbac_policies.pop(dept_id, None)
        else:
            _rbac_policies[dept_id] = policy


def get_rbac_policy(dept_id: Optional[str] = None) -> Optional[RBACPolicy]:
    """Get RBAC policy for a department (or global for single mode).

    Args:
        dept_id: Department ID, or None for single/global mode.

    Returns:
        RBACPolicy if found, None otherwise.
    """
    if dept_id is not None and dept_id in _rbac_policies:
        return _rbac_policies[dept_id]
    # Fall back to global policy
    return _rbac_policy


def reset_all_rbac() -> None:
    """Clear all RBAC policies (for testing)."""
    global _rbac_policy, _rbac_policies
    _rbac_policy = None
    _rbac_policies = {}


def gate_rbac(permission: str, actor_context: ActorContext, dept_id: Optional[str] = None) -> bool:
    """Check if actor has permission via RBAC.

    Args:
        permission: Permission to check.
        actor_context: Actor context with roles.
        dept_id: Department ID for per-dept policy lookup (optional).

    Returns:
        True if allowed, False if denied.
    """
    policy = get_rbac_policy(dept_id)
    if policy is None:
        # No policy loaded - deny by default
        return False

    return policy.has_permission(actor_context.roles, permission)
