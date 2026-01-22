"""Actor Context - deterministic context derived from request headers.

Supports two authentication modes via ENGINE_AUTH_MODE:
- dev: Accept X-Actor-Id and X-Actor-Roles headers (legacy, for development)
- strict: Require X-Actor-Token, resolve actor/roles from registry (production)

GAP 4: Adds on_behalf_of delegation chain and is_agent flag for governed agents.
"""

import os
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"


class AuthMode(Enum):
    """Authentication mode for actor identity."""

    DEV = "dev"  # Accept headers (legacy, development)
    STRICT = "strict"  # Require token (production)


def get_auth_mode() -> AuthMode:
    """Get authentication mode from ENGINE_AUTH_MODE env var.

    Returns:
        AuthMode.DEV if not set or "dev", AuthMode.STRICT if "strict".
    """
    mode = os.environ.get("ENGINE_AUTH_MODE", "dev").lower()
    if mode == "strict":
        return AuthMode.STRICT
    return AuthMode.DEV


@dataclass
class ActorContext:
    """Actor context for a request.

    In dev mode, derived from headers:
    - X-Actor-Id: <uuid> (required)
    - X-Actor-Roles: role1,role2 (optional)
    - X-Tenant-Id: <uuid> (optional, defaults to DEFAULT_TENANT_ID)
    - X-On-Behalf-Of: <uuid> (optional, only for agents)

    In strict mode, derived from token:
    - X-Actor-Token: <token> (required, resolves actor_id and roles from registry)
    - X-Tenant-Id: <uuid> (optional)
    - X-On-Behalf-Of: <uuid> (optional, only for agents)

    GAP 4: Adds delegation chain (on_behalf_of) and agent identification (is_agent).
    """

    actor_id: str
    roles: List[str] = field(default_factory=list)
    tenant_id: str = DEFAULT_TENANT_ID
    identity_verified: bool = False  # True if resolved from token registry
    is_agent: bool = False  # True if actor is registered as an agent (GAP 4)
    on_behalf_of: Optional[str] = None  # Delegation chain: actor this agent acts for (GAP 4)

    def has_role(self, role: str) -> bool:
        """Check if actor has a specific role."""
        return role in self.roles

    def can_delegate(self) -> bool:
        """Check if this actor can use on_behalf_of delegation.

        GAP 4: Only verified agents can delegate.
        In strict mode: requires is_agent=True from registry.
        In dev mode: allows delegation but marks as unverified.
        """
        return self.is_agent


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
