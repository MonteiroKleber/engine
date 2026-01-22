"""Agent Requests Registry - Append-only storage for agent auto-solicitations.

When an agent is denied access to a governed operation, an AgentRequest is
created to track the solicitation. This enables:
- Audit trail of all agent requests
- Admin visibility into pending requests
- Future: approval workflows for agent requests

GAP 4: Agents as governed actors - auto-solicitation on deny.
"""

import json
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.core.data_root import get_institution_root
from engine.core.ledger import get_ledger_for_institution


# Storage paths
AGENT_REQUESTS_DIR = "agent_requests"
AGENT_REQUESTS_REGISTRY_FILE = "requests.jsonl"
AGENT_REQUESTS_STATE_FILE = "state.json"

# Ledger event type
AGENT_REQUEST_CREATED = "AGENT_REQUEST_CREATED"


@dataclass
class AgentRequest:
    """An agent's auto-solicitation when denied access.

    Created automatically when an agent is denied a governed operation.
    Stored in append-only registry for audit and admin visibility.
    """

    request_id: str  # UUID
    created_at: str  # ISO 8601
    institution_id: str  # Institution UUID
    dept_id: Optional[str]  # Department ID (optional)
    agent_actor_id: str  # The agent's actor ID
    on_behalf_of: Optional[str]  # Who the agent was acting for (if any)
    endpoint_sig: str  # e.g., "POST /bridge/write/increase_limit"
    action_type: str  # e.g., "increase_limit"
    deny_code: str  # e.g., "MANDATE_DENIED", "AUTONOMY_INSUFFICIENT"
    deny_details: Dict[str, Any]  # Structured denial info
    status: str = "pending"  # "pending", "resolved", "expired"
    resolved_at: Optional[str] = None  # When resolved
    resolved_by: Optional[str] = None  # Who resolved it

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentRequest":
        """Create from dictionary."""
        return cls(
            request_id=data["request_id"],
            created_at=data["created_at"],
            institution_id=data["institution_id"],
            dept_id=data.get("dept_id"),
            agent_actor_id=data["agent_actor_id"],
            on_behalf_of=data.get("on_behalf_of"),
            endpoint_sig=data["endpoint_sig"],
            action_type=data["action_type"],
            deny_code=data["deny_code"],
            deny_details=data.get("deny_details", {}),
            status=data.get("status", "pending"),
            resolved_at=data.get("resolved_at"),
            resolved_by=data.get("resolved_by"),
        )


def _now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AgentRequestsRegistry:
    """Registry for agent requests with append-only storage.

    Manages:
    - requests.jsonl: Append-only request log
    - state.json: Current state for fast lookup

    Per-institution isolation with optional dept_id filtering.
    """

    def __init__(self, institution_id: str, dept_id: Optional[str] = None) -> None:
        """Initialize registry for an institution.

        Args:
            institution_id: Institution UUID.
            dept_id: Optional department ID for multi-dept mode.
        """
        self._institution_id = institution_id
        self._dept_id = dept_id
        self._lock = threading.Lock()

        # Resolve paths
        inst_root = get_institution_root(institution_id)
        if dept_id:
            self._requests_root = inst_root / "depts" / dept_id / AGENT_REQUESTS_DIR
        else:
            self._requests_root = inst_root / AGENT_REQUESTS_DIR

        self._registry_path = self._requests_root / AGENT_REQUESTS_REGISTRY_FILE
        self._state_path = self._requests_root / AGENT_REQUESTS_STATE_FILE

        # In-memory state cache
        self._state: Dict[str, Any] = {"schema_version": "1.0", "requests": {}}
        self._load_state()

    def _ensure_dir(self) -> None:
        """Ensure requests directory exists."""
        self._requests_root.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> None:
        """Load state from state.json if exists."""
        if self._state_path.exists():
            try:
                with open(self._state_path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._state = {"schema_version": "1.0", "requests": {}}

    def _save_state(self) -> None:
        """Save current state to state.json."""
        self._ensure_dir()
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _append_request(self, request: AgentRequest) -> None:
        """Append request to JSONL registry."""
        self._ensure_dir()
        with open(self._registry_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(request.to_dict(), sort_keys=True) + "\n")

    def _emit_request_created(self, request: AgentRequest) -> None:
        """Emit AGENT_REQUEST_CREATED event to ledger."""
        ledger = get_ledger_for_institution(self._institution_id)
        ledger.append(
            event_type=AGENT_REQUEST_CREATED,
            tenant_id=self._institution_id,
            actor_id=request.agent_actor_id,
            actor_roles=[],  # Agent roles not stored in request
            case_id=request.request_id,
            step=f"AGENT_REQUEST:{request.action_type}",
            payload={
                "request_id": request.request_id,
                "agent_actor_id": request.agent_actor_id,
                "on_behalf_of": request.on_behalf_of,
                "endpoint_sig": request.endpoint_sig,
                "action_type": request.action_type,
                "deny_code": request.deny_code,
            },
            dept_id=self._dept_id,
        )

    def create_request(
        self,
        agent_actor_id: str,
        on_behalf_of: Optional[str],
        endpoint_sig: str,
        action_type: str,
        deny_code: str,
        deny_details: Optional[Dict[str, Any]] = None,
    ) -> AgentRequest:
        """Create a new agent request (auto-solicitation).

        Called when an agent is denied a governed operation.

        Args:
            agent_actor_id: The agent's actor ID.
            on_behalf_of: Who the agent was acting for (if any).
            endpoint_sig: Endpoint signature (e.g., "POST /bridge/write/increase_limit").
            action_type: Action type (e.g., "increase_limit").
            deny_code: Denial reason code.
            deny_details: Additional denial details.

        Returns:
            The created AgentRequest.
        """
        with self._lock:
            request_id = str(uuid.uuid4())

            request = AgentRequest(
                request_id=request_id,
                created_at=_now_iso(),
                institution_id=self._institution_id,
                dept_id=self._dept_id,
                agent_actor_id=agent_actor_id,
                on_behalf_of=on_behalf_of,
                endpoint_sig=endpoint_sig,
                action_type=action_type,
                deny_code=deny_code,
                deny_details=deny_details or {},
                status="pending",
            )

            # Persist
            self._append_request(request)
            self._state.setdefault("requests", {})[request_id] = request.to_dict()
            self._save_state()

            # Emit to ledger
            self._emit_request_created(request)

            return request

    def get_request(self, request_id: str) -> Optional[AgentRequest]:
        """Get a request by ID.

        Args:
            request_id: Request UUID.

        Returns:
            AgentRequest if found, None otherwise.
        """
        data = self._state.get("requests", {}).get(request_id)
        if data:
            return AgentRequest.from_dict(data)
        return None

    def list_requests(
        self,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AgentRequest]:
        """List requests with optional filtering.

        Args:
            status: Filter by status ("pending", "resolved", "expired").
            agent_id: Filter by agent actor ID.
            limit: Maximum number of results.

        Returns:
            List of AgentRequest objects.
        """
        requests = []
        for data in self._state.get("requests", {}).values():
            if status and data.get("status") != status:
                continue
            if agent_id and data.get("agent_actor_id") != agent_id:
                continue
            requests.append(AgentRequest.from_dict(data))
            if len(requests) >= limit:
                break

        # Sort by created_at descending
        requests.sort(key=lambda r: r.created_at, reverse=True)
        return requests

    def resolve_request(
        self,
        request_id: str,
        resolved_by: str,
        status: str = "resolved",
    ) -> Optional[AgentRequest]:
        """Resolve a pending request.

        Args:
            request_id: Request UUID.
            resolved_by: Actor ID who resolved it.
            status: New status ("resolved" or "expired").

        Returns:
            Updated AgentRequest if found, None otherwise.
        """
        with self._lock:
            data = self._state.get("requests", {}).get(request_id)
            if not data:
                return None

            request = AgentRequest.from_dict(data)
            if request.status != "pending":
                return request  # Already resolved

            request.status = status
            request.resolved_at = _now_iso()
            request.resolved_by = resolved_by

            # Persist
            self._append_request(request)  # Append updated state
            self._state["requests"][request_id] = request.to_dict()
            self._save_state()

            return request


def get_agent_requests_registry(
    institution_id: str,
    dept_id: Optional[str] = None,
) -> AgentRequestsRegistry:
    """Get an agent requests registry for an institution.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        AgentRequestsRegistry instance.
    """
    return AgentRequestsRegistry(institution_id, dept_id)
