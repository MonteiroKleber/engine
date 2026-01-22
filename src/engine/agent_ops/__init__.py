"""Agent Ops - Read model and registry for agent observability.

Etapa 4.6: Agent Ops / Observability minima

Provides:
- Read model for querying ledger by actor_id and denied attempts
- Agent registry (append-only JSONL)
"""

from engine.agent_ops.read_model import (
    list_events_by_actor,
    list_denied_events,
    is_denied_event,
    get_gate_for_event,
    GATE_EVENT_TYPES,
)
from engine.agent_ops.registry import (
    AgentEntry,
    get_agent_registry,
    register_agent,
    get_agent_by_actor_id,
)

__all__ = [
    "list_events_by_actor",
    "list_denied_events",
    "is_denied_event",
    "get_gate_for_event",
    "GATE_EVENT_TYPES",
    "AgentEntry",
    "get_agent_registry",
    "register_agent",
    "get_agent_by_actor_id",
]
