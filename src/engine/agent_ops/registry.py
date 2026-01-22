"""Agent registry - append-only JSONL storage for agent metadata.

Stores metadata about agents (actor_id, name, roles, scopes).
The registry is informational - actual permissions come from mandates.

Etapa 4.6: Agent Ops / Observability minima
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from engine.core.data_root import get_institution_root


REGISTRY_FILENAME = "agents_registry.jsonl"


@dataclass
class AgentEntry:
    """Agent metadata entry.

    Attributes:
        actor_id: The actor_id used in ledger events (canonical identifier).
        name: Display name for the agent.
        roles: List of roles the agent should have.
        dept_ids: List of department IDs the agent can access.
        created_at: ISO timestamp when registered.
        created_by: Actor ID of who registered the agent.
        description: Optional description.
    """

    actor_id: str
    name: str
    roles: List[str] = field(default_factory=list)
    dept_ids: List[str] = field(default_factory=list)
    created_at: str = ""
    created_by: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentEntry":
        """Create from dict."""
        return cls(
            actor_id=d.get("actor_id", ""),
            name=d.get("name", ""),
            roles=d.get("roles", []),
            dept_ids=d.get("dept_ids", []),
            created_at=d.get("created_at", ""),
            created_by=d.get("created_by", ""),
            description=d.get("description", ""),
        )


def _get_registry_path(institution_id: str) -> Path:
    """Get path to agent registry for an institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to agents_registry.jsonl file.
    """
    root = get_institution_root(institution_id)
    return root / REGISTRY_FILENAME


def get_agent_registry(
    institution_id: str,
    dept_id: Optional[str] = None,
) -> List[AgentEntry]:
    """Get all registered agents for an institution.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID to filter by.

    Returns:
        List of AgentEntry, deduplicated by actor_id (last entry wins).
    """
    path = _get_registry_path(institution_id)

    if not path.exists():
        return []

    # Load all entries (append-only, so later entries override earlier)
    entries_by_actor: dict[str, AgentEntry] = {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    entry = AgentEntry.from_dict(d)
                    entries_by_actor[entry.actor_id] = entry
                except (json.JSONDecodeError, KeyError):
                    continue
    except IOError:
        return []

    agents = list(entries_by_actor.values())

    # Filter by dept_id if specified
    if dept_id is not None:
        agents = [a for a in agents if dept_id in a.dept_ids]

    return agents


def get_agent_by_actor_id(
    institution_id: str,
    actor_id: str,
) -> Optional[AgentEntry]:
    """Get a specific agent by actor_id.

    Args:
        institution_id: Institution UUID.
        actor_id: Actor ID to find.

    Returns:
        AgentEntry if found, None otherwise.
    """
    agents = get_agent_registry(institution_id)
    for agent in agents:
        if agent.actor_id == actor_id:
            return agent
    return None


def register_agent(
    institution_id: str,
    actor_id: str,
    name: str,
    roles: List[str],
    dept_ids: List[str],
    registered_by: str,
    description: str = "",
) -> AgentEntry:
    """Register a new agent (append to registry).

    Args:
        institution_id: Institution UUID.
        actor_id: Actor ID for the agent.
        name: Display name.
        roles: List of roles.
        dept_ids: List of department IDs.
        registered_by: Actor ID of who is registering.
        description: Optional description.

    Returns:
        Created AgentEntry.
    """
    entry = AgentEntry(
        actor_id=actor_id,
        name=name,
        roles=roles,
        dept_ids=dept_ids,
        created_at=datetime.now(timezone.utc).isoformat(),
        created_by=registered_by,
        description=description,
    )

    path = _get_registry_path(institution_id)

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Append to file
    with open(path, "a", encoding="utf-8") as f:
        line = json.dumps(entry.to_dict(), sort_keys=True)
        f.write(line + "\n")

    return entry


def actor_exists_in_registry(
    institution_id: str,
    actor_id: str,
) -> bool:
    """Check if an actor is registered.

    Args:
        institution_id: Institution UUID.
        actor_id: Actor ID to check.

    Returns:
        True if actor is in registry.
    """
    return get_agent_by_actor_id(institution_id, actor_id) is not None
