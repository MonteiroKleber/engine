"""Read model for agent observability - ledger queries.

Provides functions to query the ledger by actor_id and filter denied events.
Uses get_all_events() + in-memory filtering (no database).

Etapa 4.6: Agent Ops / Observability minima
"""

from typing import Dict, List, Optional, Set

from engine.core.ledger import LedgerEvent, get_ledger_for_institution


# Mapping of gate names to event types
# Used to filter denied events by gate
GATE_EVENT_TYPES: Dict[str, Set[str]] = {
    "rbac": {"RBAC_DECISION"},
    "policy": {"POLICY_PRE_DECISION", "POLICY_POST_DECISION"},
    "mandate": {"MANDATE_EVALUATED"},
    "autonomy": {"AUTONOMY_EVALUATED"},
    "sod": {"SOD_VIOLATION"},
}

# All gates for validation
VALID_GATES = set(GATE_EVENT_TYPES.keys())


def is_denied_event(event: LedgerEvent) -> bool:
    """Check if an event represents a denied attempt.

    Deterministic detection based on event_type + payload.allowed field:
    - RBAC_DECISION with payload.allowed == False
    - POLICY_PRE_DECISION with payload.allowed == False
    - POLICY_POST_DECISION with payload.allowed == False
    - MANDATE_EVALUATED with payload.allowed == False
    - AUTONOMY_EVALUATED with payload.allowed == False
    - SOD_VIOLATION (always denied)

    Args:
        event: Ledger event to check.

    Returns:
        True if event represents a denial.
    """
    event_type = event.event_type

    # SOD_VIOLATION is always a denial
    if event_type == "SOD_VIOLATION":
        return True

    # Check events that have payload.allowed field
    decision_types = {
        "RBAC_DECISION",
        "POLICY_PRE_DECISION",
        "POLICY_POST_DECISION",
        "MANDATE_EVALUATED",
        "AUTONOMY_EVALUATED",
    }

    if event_type in decision_types:
        # Denied if allowed is explicitly False
        return event.payload.get("allowed") is False

    return False


def get_gate_for_event(event: LedgerEvent) -> Optional[str]:
    """Get the gate name for an event type.

    Args:
        event: Ledger event.

    Returns:
        Gate name (rbac, policy, mandate, autonomy, sod) or None.
    """
    event_type = event.event_type

    for gate, types in GATE_EVENT_TYPES.items():
        if event_type in types:
            return gate

    return None


def list_events_by_actor(
    institution_id: str,
    actor_id: str,
    limit: int = 50,
    dept_id: Optional[str] = None,
) -> List[LedgerEvent]:
    """List events for a specific actor.

    Args:
        institution_id: Institution UUID.
        actor_id: Actor identifier to filter by.
        limit: Maximum number of events to return (default 50).
        dept_id: Optional department ID to filter by.

    Returns:
        List of LedgerEvent, most recent first (by seq descending).
    """
    ledger = get_ledger_for_institution(institution_id)
    all_events = ledger.get_all_events()

    # Filter by actor_id
    filtered = [e for e in all_events if e.actor_id == actor_id]

    # Optionally filter by dept_id
    if dept_id is not None:
        filtered = [e for e in filtered if e.dept_id == dept_id]

    # Sort by seq descending (most recent first)
    filtered.sort(key=lambda e: e.seq, reverse=True)

    # Apply limit
    return filtered[:limit]


def list_denied_events(
    institution_id: str,
    gate: Optional[str] = None,
    dept_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    limit: int = 100,
) -> List[LedgerEvent]:
    """List denied events (attempts that were blocked).

    Args:
        institution_id: Institution UUID.
        gate: Optional gate to filter by (rbac, policy, mandate, autonomy, sod).
        dept_id: Optional department ID to filter by.
        actor_id: Optional actor ID to filter by.
        limit: Maximum number of events to return (default 100).

    Returns:
        List of denied LedgerEvent, most recent first.

    Raises:
        ValueError: If gate is invalid.
    """
    # Validate gate
    if gate is not None and gate not in VALID_GATES:
        raise ValueError(f"Invalid gate '{gate}'. Valid gates: {sorted(VALID_GATES)}")

    ledger = get_ledger_for_institution(institution_id)
    all_events = ledger.get_all_events()

    # Get event types for gate filter
    if gate is not None:
        allowed_types = GATE_EVENT_TYPES[gate]
    else:
        # All denial-capable event types
        allowed_types = set()
        for types in GATE_EVENT_TYPES.values():
            allowed_types |= types

    # Filter events
    filtered = []
    for event in all_events:
        # Filter by event type first (cheap check)
        if event.event_type not in allowed_types:
            continue

        # Filter by dept_id if specified
        if dept_id is not None and event.dept_id != dept_id:
            continue

        # Filter by actor_id if specified
        if actor_id is not None and event.actor_id != actor_id:
            continue

        # Check if it's a denied event
        if is_denied_event(event):
            filtered.append(event)

    # Sort by seq descending (most recent first)
    filtered.sort(key=lambda e: e.seq, reverse=True)

    # Apply limit
    return filtered[:limit]


def get_actor_stats(
    institution_id: str,
    actor_id: str,
    dept_id: Optional[str] = None,
) -> Dict[str, any]:
    """Get statistics for an actor.

    Args:
        institution_id: Institution UUID.
        actor_id: Actor identifier.
        dept_id: Optional department ID to filter by.

    Returns:
        Dict with total_events, denied_count, last_active timestamp.
    """
    ledger = get_ledger_for_institution(institution_id)
    all_events = ledger.get_all_events()

    # Filter by actor_id
    actor_events = [e for e in all_events if e.actor_id == actor_id]

    # Optionally filter by dept_id
    if dept_id is not None:
        actor_events = [e for e in actor_events if e.dept_id == dept_id]

    if not actor_events:
        return {
            "total_events": 0,
            "denied_count": 0,
            "last_active": None,
        }

    # Count denied events
    denied_count = sum(1 for e in actor_events if is_denied_event(e))

    # Find last active timestamp
    actor_events.sort(key=lambda e: e.seq, reverse=True)
    last_active = actor_events[0].timestamp if actor_events else None

    return {
        "total_events": len(actor_events),
        "denied_count": denied_count,
        "last_active": last_active,
    }


def list_unique_actors(
    institution_id: str,
    dept_id: Optional[str] = None,
) -> List[str]:
    """List all unique actor_ids that appear in the ledger.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID to filter by.

    Returns:
        List of unique actor_id strings.
    """
    ledger = get_ledger_for_institution(institution_id)
    all_events = ledger.get_all_events()

    # Optionally filter by dept_id
    if dept_id is not None:
        all_events = [e for e in all_events if e.dept_id == dept_id]

    # Collect unique actor_ids
    actors = set()
    for event in all_events:
        if event.actor_id:
            actors.add(event.actor_id)

    return sorted(actors)
