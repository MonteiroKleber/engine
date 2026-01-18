"""Actor Context - deterministic context derived from request headers."""

import uuid
from dataclasses import dataclass, field
from typing import List, Optional


DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"


@dataclass
class ActorContext:
    """Actor context for a request.

    Derived deterministically from headers:
    - X-Actor-Id: <uuid> (required)
    - X-Actor-Roles: role1,role2 (optional)
    - X-Tenant-Id: <uuid> (optional, defaults to DEFAULT_TENANT_ID)
    """

    actor_id: str
    roles: List[str] = field(default_factory=list)
    tenant_id: str = DEFAULT_TENANT_ID

    def has_role(self, role: str) -> bool:
        """Check if actor has a specific role."""
        return role in self.roles


def is_valid_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def parse_actor_context(
    actor_id: Optional[str],
    actor_roles: Optional[str],
    tenant_id: Optional[str],
) -> tuple[Optional[ActorContext], Optional[str], Optional[str]]:
    """Parse actor context from header values.

    Args:
        actor_id: Value of X-Actor-Id header.
        actor_roles: Value of X-Actor-Roles header (comma-separated).
        tenant_id: Value of X-Tenant-Id header.

    Returns:
        Tuple of (ActorContext, error_code, error_message).
        If successful, error_code and error_message are None.
        If failed, ActorContext is None.
    """
    # Check if actor_id is present
    if not actor_id:
        return None, "ACTOR_MISSING", "Actor is required"

    # Check if actor_id is a valid UUID
    if not is_valid_uuid(actor_id):
        return None, "ACTOR_INVALID", "Actor is invalid"

    # Parse roles
    roles: List[str] = []
    if actor_roles:
        roles = [r.strip() for r in actor_roles.split(",") if r.strip()]

    # Validate tenant_id if provided
    # If absent → use default tenant
    # If present but invalid UUID → error TENANT_INVALID
    if tenant_id:
        if not is_valid_uuid(tenant_id):
            return None, "TENANT_INVALID", "Tenant is invalid"
        validated_tenant_id = tenant_id
    else:
        validated_tenant_id = DEFAULT_TENANT_ID

    context = ActorContext(
        actor_id=actor_id,
        roles=roles,
        tenant_id=validated_tenant_id,
    )

    return context, None, None
