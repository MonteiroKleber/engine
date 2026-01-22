"""Tests for Agent Ops read model and console pages.

Etapa 4.6: Agent Ops / Observability minima

Tests cover:
- Read model functions (list_events_by_actor, list_denied_events)
- Agent registry (CRUD)
- Console routes (auth, render, filters)
- Multi-tenant isolation
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.runtime_state import runtime_state, RuntimeMode
from engine.core.ledger import (
    AuditLedger,
    LedgerEvent,
    reset_institution_ledgers,
    get_ledger_for_institution,
)
from engine.agent_ops import (
    list_events_by_actor,
    list_denied_events,
    get_agent_registry,
    register_agent,
    get_agent_by_actor_id,
    is_denied_event,
    get_gate_for_event,
    GATE_EVENT_TYPES,
)
from engine.agent_ops.read_model import get_actor_stats, list_unique_actors


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    # Set temp paths
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("ENGINE_CONSOLE_SESSION_SECRET", "a" * 32)

    # Reset global state
    reset_registry()
    reset_institution_ledgers()

    # Ensure runtime is ACTIVE
    runtime_state.mode = RuntimeMode.ACTIVE
    runtime_state.reason_code = None
    runtime_state.details = []

    yield

    reset_registry()
    reset_institution_ledgers()
    runtime_state.mode = RuntimeMode.ACTIVE


@pytest.fixture
def institution_with_events(tmp_path, monkeypatch):
    """Create institution with ledger events for testing."""
    institution_id = "inst-001"

    # IMPORTANT: Set data root to tmp_path so get_institution_root finds our test dirs
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path))

    # Reset ledger cache to pick up new data root
    reset_institution_ledgers()

    # Setup institution directory
    inst_dir = tmp_path / "institutions" / institution_id
    inst_dir.mkdir(parents=True)

    # Create ledger via get_ledger_for_institution to use the global cache
    ledger = get_ledger_for_institution(institution_id)
    ledger.set_bundle_hashes("manifest-hash", "contract-hash")

    # Add test events
    # Event 1: RBAC allowed
    ledger.append(
        event_type="RBAC_DECISION",
        tenant_id="tenant-1",
        actor_id="actor-alice",
        actor_roles=["admin"],
        case_id="case-1",
        step="Approve",
        payload={"allowed": True, "reason": "Role match"},
        dept_id="finance",
    )

    # Event 2: RBAC denied
    ledger.append(
        event_type="RBAC_DECISION",
        tenant_id="tenant-1",
        actor_id="actor-bob",
        actor_roles=["viewer"],
        case_id="case-2",
        step="Approve",
        payload={"allowed": False, "reason": "Insufficient role"},
        dept_id="finance",
    )

    # Event 3: MANDATE_EVALUATED denied
    ledger.append(
        event_type="MANDATE_EVALUATED",
        tenant_id="tenant-1",
        actor_id="actor-bob",
        actor_roles=["viewer"],
        case_id="case-3",
        step="Submit",
        payload={"allowed": False, "code": "MANDATE_DENIED"},
        dept_id="hr",
    )

    # Event 4: SOD_VIOLATION (always denied)
    ledger.append(
        event_type="SOD_VIOLATION",
        tenant_id="tenant-1",
        actor_id="actor-alice",
        actor_roles=["admin"],
        case_id="case-4",
        step="Approve",
        payload={"rule": "NoSelfApproval"},
        dept_id="finance",
    )

    # Event 5: POLICY_PRE_DECISION allowed
    ledger.append(
        event_type="POLICY_PRE_DECISION",
        tenant_id="tenant-1",
        actor_id="actor-alice",
        actor_roles=["admin"],
        case_id="case-5",
        step="Create",
        payload={"allowed": True},
        dept_id="finance",
    )

    return institution_id


# ============================================================
# Read Model Tests
# ============================================================


class TestIsDeniedEvent:
    """Tests for is_denied_event function."""

    def test_rbac_denied(self):
        """RBAC_DECISION with allowed=False is denied."""
        event = LedgerEvent(
            event_type="RBAC_DECISION",
            tenant_id="t",
            actor_id="a",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={"allowed": False},
            bundle_manifest_sha256="",
            contract_ledger_sha256="",
            engine_version="",
        )
        assert is_denied_event(event) is True

    def test_rbac_allowed(self):
        """RBAC_DECISION with allowed=True is not denied."""
        event = LedgerEvent(
            event_type="RBAC_DECISION",
            tenant_id="t",
            actor_id="a",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={"allowed": True},
            bundle_manifest_sha256="",
            contract_ledger_sha256="",
            engine_version="",
        )
        assert is_denied_event(event) is False

    def test_sod_violation_always_denied(self):
        """SOD_VIOLATION is always a denial."""
        event = LedgerEvent(
            event_type="SOD_VIOLATION",
            tenant_id="t",
            actor_id="a",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={},
            bundle_manifest_sha256="",
            contract_ledger_sha256="",
            engine_version="",
        )
        assert is_denied_event(event) is True

    def test_mandate_denied(self):
        """MANDATE_EVALUATED with allowed=False is denied."""
        event = LedgerEvent(
            event_type="MANDATE_EVALUATED",
            tenant_id="t",
            actor_id="a",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={"allowed": False, "code": "MANDATE_DENIED"},
            bundle_manifest_sha256="",
            contract_ledger_sha256="",
            engine_version="",
        )
        assert is_denied_event(event) is True

    def test_unknown_event_type_not_denied(self):
        """Unknown event types are not denials."""
        event = LedgerEvent(
            event_type="SOME_OTHER_EVENT",
            tenant_id="t",
            actor_id="a",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={},
            bundle_manifest_sha256="",
            contract_ledger_sha256="",
            engine_version="",
        )
        assert is_denied_event(event) is False


class TestGetGateForEvent:
    """Tests for get_gate_for_event function."""

    def test_rbac_decision_returns_rbac(self):
        """RBAC_DECISION maps to 'rbac' gate."""
        event = LedgerEvent(
            event_type="RBAC_DECISION",
            tenant_id="t", actor_id="a", actor_roles=[], case_id="c",
            step="s", payload={}, bundle_manifest_sha256="",
            contract_ledger_sha256="", engine_version="",
        )
        assert get_gate_for_event(event) == "rbac"

    def test_sod_violation_returns_sod(self):
        """SOD_VIOLATION maps to 'sod' gate."""
        event = LedgerEvent(
            event_type="SOD_VIOLATION",
            tenant_id="t", actor_id="a", actor_roles=[], case_id="c",
            step="s", payload={}, bundle_manifest_sha256="",
            contract_ledger_sha256="", engine_version="",
        )
        assert get_gate_for_event(event) == "sod"

    def test_unknown_event_returns_none(self):
        """Unknown event type returns None."""
        event = LedgerEvent(
            event_type="UNKNOWN_TYPE",
            tenant_id="t", actor_id="a", actor_roles=[], case_id="c",
            step="s", payload={}, bundle_manifest_sha256="",
            contract_ledger_sha256="", engine_version="",
        )
        assert get_gate_for_event(event) is None


class TestListEventsByActor:
    """Tests for list_events_by_actor function."""

    def test_filters_by_actor_id(self, institution_with_events):
        """Events are filtered by actor_id."""
        events = list_events_by_actor(institution_with_events, "actor-alice")

        assert len(events) == 3
        for e in events:
            assert e.actor_id == "actor-alice"

    def test_returns_empty_for_unknown_actor(self, institution_with_events):
        """Returns empty list for unknown actor."""
        events = list_events_by_actor(institution_with_events, "unknown-actor")

        assert len(events) == 0

    def test_respects_limit(self, institution_with_events):
        """Limit parameter is respected."""
        events = list_events_by_actor(institution_with_events, "actor-alice", limit=2)

        assert len(events) == 2

    def test_filters_by_dept_id(self, institution_with_events):
        """Events can be filtered by dept_id."""
        events = list_events_by_actor(
            institution_with_events, "actor-bob", dept_id="finance"
        )

        assert len(events) == 1
        assert events[0].dept_id == "finance"

    def test_returns_most_recent_first(self, institution_with_events):
        """Events are ordered by seq descending."""
        events = list_events_by_actor(institution_with_events, "actor-alice")

        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs, reverse=True)


class TestListDeniedEvents:
    """Tests for list_denied_events function."""

    def test_returns_only_denied(self, institution_with_events):
        """Only denied events are returned."""
        events = list_denied_events(institution_with_events)

        # Should have 3 denied events (bob rbac, bob mandate, alice sod)
        assert len(events) == 3
        for e in events:
            assert is_denied_event(e)

    def test_filters_by_gate(self, institution_with_events):
        """Events can be filtered by gate."""
        events = list_denied_events(institution_with_events, gate="sod")

        assert len(events) == 1
        assert events[0].event_type == "SOD_VIOLATION"

    def test_filters_by_actor_id(self, institution_with_events):
        """Events can be filtered by actor_id."""
        events = list_denied_events(institution_with_events, actor_id="actor-bob")

        assert len(events) == 2
        for e in events:
            assert e.actor_id == "actor-bob"

    def test_filters_by_dept_id(self, institution_with_events):
        """Events can be filtered by dept_id."""
        events = list_denied_events(institution_with_events, dept_id="hr")

        assert len(events) == 1
        assert events[0].dept_id == "hr"

    def test_invalid_gate_raises_error(self, institution_with_events):
        """Invalid gate raises ValueError."""
        with pytest.raises(ValueError) as exc:
            list_denied_events(institution_with_events, gate="invalid")

        assert "Invalid gate" in str(exc.value)

    def test_respects_limit(self, institution_with_events):
        """Limit parameter is respected."""
        events = list_denied_events(institution_with_events, limit=2)

        assert len(events) == 2


class TestGetActorStats:
    """Tests for get_actor_stats function."""

    def test_returns_correct_counts(self, institution_with_events):
        """Stats include correct event counts."""
        stats = get_actor_stats(institution_with_events, "actor-alice")

        assert stats["total_events"] == 3
        assert stats["denied_count"] == 1  # SOD_VIOLATION
        assert stats["last_active"] is not None

    def test_returns_zeros_for_unknown_actor(self, institution_with_events):
        """Unknown actor returns zeros."""
        stats = get_actor_stats(institution_with_events, "unknown")

        assert stats["total_events"] == 0
        assert stats["denied_count"] == 0
        assert stats["last_active"] is None


class TestListUniqueActors:
    """Tests for list_unique_actors function."""

    def test_returns_unique_actor_ids(self, institution_with_events):
        """Returns list of unique actor IDs."""
        actors = list_unique_actors(institution_with_events)

        assert set(actors) == {"actor-alice", "actor-bob"}

    def test_filters_by_dept_id(self, institution_with_events):
        """Can filter by dept_id."""
        actors = list_unique_actors(institution_with_events, dept_id="hr")

        assert actors == ["actor-bob"]


# ============================================================
# Registry Tests
# ============================================================


class TestAgentRegistry:
    """Tests for agent registry functions."""

    def test_register_and_get(self, tmp_path, monkeypatch):
        """Can register and retrieve an agent."""
        institution_id = "inst-reg"
        inst_dir = tmp_path / "institutions" / institution_id
        inst_dir.mkdir(parents=True)

        agent = register_agent(
            institution_id=institution_id,
            actor_id="bot-test",
            name="Test Bot",
            roles=["processor"],
            dept_ids=["finance"],
            registered_by="admin",
            description="A test bot",
        )

        assert agent.actor_id == "bot-test"
        assert agent.name == "Test Bot"
        assert agent.created_at != ""

        # Retrieve
        retrieved = get_agent_by_actor_id(institution_id, "bot-test")
        assert retrieved is not None
        assert retrieved.actor_id == "bot-test"
        assert retrieved.name == "Test Bot"

    def test_get_registry_empty(self, tmp_path, monkeypatch):
        """Empty registry returns empty list."""
        institution_id = "inst-empty"
        agents = get_agent_registry(institution_id)

        assert agents == []

    def test_get_agent_not_found(self, tmp_path, monkeypatch):
        """Unknown actor returns None."""
        institution_id = "inst-notfound"
        agent = get_agent_by_actor_id(institution_id, "unknown")

        assert agent is None

    def test_registry_filters_by_dept(self, tmp_path, monkeypatch):
        """Registry can filter by dept_id."""
        institution_id = "inst-dept"
        inst_dir = tmp_path / "institutions" / institution_id
        inst_dir.mkdir(parents=True)

        register_agent(institution_id, "bot-a", "Bot A", [], ["finance"], "admin")
        register_agent(institution_id, "bot-b", "Bot B", [], ["hr"], "admin")

        # All agents
        all_agents = get_agent_registry(institution_id)
        assert len(all_agents) == 2

        # Filter by dept
        finance_agents = get_agent_registry(institution_id, dept_id="finance")
        assert len(finance_agents) == 1
        assert finance_agents[0].actor_id == "bot-a"


# ============================================================
# Console Routes Tests
# ============================================================


class TestConsoleAgentsAuth:
    """Test console agents page authentication."""

    def test_agents_without_token_returns_401(self):
        """GET /console/agents without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/agents?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_denied_without_token_returns_401(self):
        """GET /console/denied without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/denied?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"


class TestConsoleAgentsPage:
    """Test console agents page rendering."""

    def test_agents_requires_institution_id(self):
        """GET /console/agents without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/agents",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_agents_returns_html(self):
        """GET /console/agents returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/agents?institution_id=test-inst",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Agents" in response.text

    def test_agents_shows_empty_state(self):
        """GET /console/agents shows empty state when no agents."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/agents?institution_id=test-inst",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "No actors found" in response.text


class TestConsoleAgentDetailPage:
    """Test console agent detail page."""

    def test_agent_detail_unknown_returns_404(self):
        """GET /console/agents/{actor_id} for unknown actor returns 404."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/agents/unknown-actor?institution_id=test-inst",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "AGENT_NOT_FOUND"


class TestConsoleDeniedPage:
    """Test console denied page rendering."""

    def test_denied_requires_institution_id(self):
        """GET /console/denied without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/denied",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_denied_returns_html(self):
        """GET /console/denied returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/denied?institution_id=test-inst",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Denied Attempts" in response.text

    def test_denied_invalid_gate_returns_400(self):
        """GET /console/denied with invalid gate returns 400."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/denied?institution_id=test-inst&gate=invalid",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "INVALID_GATE"

    def test_denied_shows_gate_legend(self):
        """GET /console/denied shows gate type explanations."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/denied?institution_id=test-inst",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Role-based access control" in response.text
        assert "Separation of duties" in response.text


# ============================================================
# Isolation Tests (DoD requirement)
# ============================================================


class TestMultiTenantIsolation:
    """Tests for multi-tenant isolation.

    DoD requirement: "Testes cobrindo isolamento (duas instituições, dois depts)."
    """

    def test_isolation_events_by_institution(self, tmp_path, monkeypatch):
        """Events from institution A are not visible to institution B."""
        # Set data root to tmp_path
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path))
        reset_institution_ledgers()

        # Create institution A with events
        inst_a = "inst-a"
        inst_a_dir = tmp_path / "institutions" / inst_a
        inst_a_dir.mkdir(parents=True)

        ledger_a = get_ledger_for_institution(inst_a)
        ledger_a.set_bundle_hashes("a", "a")
        ledger_a.append(
            event_type="RBAC_DECISION",
            tenant_id="t",
            actor_id="actor-from-a",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={"allowed": False},
        )

        # Create institution B with different events
        inst_b = "inst-b"
        inst_b_dir = tmp_path / "institutions" / inst_b
        inst_b_dir.mkdir(parents=True)

        ledger_b = get_ledger_for_institution(inst_b)
        ledger_b.set_bundle_hashes("b", "b")
        ledger_b.append(
            event_type="RBAC_DECISION",
            tenant_id="t",
            actor_id="actor-from-b",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={"allowed": False},
        )

        # Query institution A - should only see A's events
        events_a = list_denied_events(inst_a)
        assert len(events_a) == 1
        assert events_a[0].actor_id == "actor-from-a"

        # Query institution B - should only see B's events
        events_b = list_denied_events(inst_b)
        assert len(events_b) == 1
        assert events_b[0].actor_id == "actor-from-b"

    def test_isolation_events_by_dept(self, tmp_path, monkeypatch):
        """Events from dept A are not visible when filtering by dept B."""
        # Set data root to tmp_path
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path))
        reset_institution_ledgers()

        inst_id = "inst-dept-test"
        inst_dir = tmp_path / "institutions" / inst_id
        inst_dir.mkdir(parents=True)

        ledger = get_ledger_for_institution(inst_id)
        ledger.set_bundle_hashes("x", "x")

        # Event in finance dept
        ledger.append(
            event_type="RBAC_DECISION",
            tenant_id="t",
            actor_id="actor-1",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={"allowed": False},
            dept_id="finance",
        )

        # Event in hr dept
        ledger.append(
            event_type="RBAC_DECISION",
            tenant_id="t",
            actor_id="actor-2",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={"allowed": False},
            dept_id="hr",
        )

        # Query finance dept only
        finance_events = list_denied_events(inst_id, dept_id="finance")
        assert len(finance_events) == 1
        assert finance_events[0].dept_id == "finance"

        # Query hr dept only
        hr_events = list_denied_events(inst_id, dept_id="hr")
        assert len(hr_events) == 1
        assert hr_events[0].dept_id == "hr"

    def test_isolation_registry_by_institution(self, tmp_path, monkeypatch):
        """Agent registry from institution A is not visible to institution B."""
        # Set data root to tmp_path
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path))

        # Create agent in institution A
        inst_a = "inst-reg-a"
        inst_a_dir = tmp_path / "institutions" / inst_a
        inst_a_dir.mkdir(parents=True)
        register_agent(inst_a, "bot-a", "Bot A", [], [], "admin")

        # Create agent in institution B
        inst_b = "inst-reg-b"
        inst_b_dir = tmp_path / "institutions" / inst_b
        inst_b_dir.mkdir(parents=True)
        register_agent(inst_b, "bot-b", "Bot B", [], [], "admin")

        # Query A - should only see A's agent
        agents_a = get_agent_registry(inst_a)
        assert len(agents_a) == 1
        assert agents_a[0].actor_id == "bot-a"

        # Query B - should only see B's agent
        agents_b = get_agent_registry(inst_b)
        assert len(agents_b) == 1
        assert agents_b[0].actor_id == "bot-b"

        # Cross-lookup should fail
        assert get_agent_by_actor_id(inst_a, "bot-b") is None
        assert get_agent_by_actor_id(inst_b, "bot-a") is None

    def test_isolation_unique_actors_by_dept(self, tmp_path, monkeypatch):
        """list_unique_actors respects dept filter."""
        # Set data root to tmp_path
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path))
        reset_institution_ledgers()

        inst_id = "inst-actors"
        inst_dir = tmp_path / "institutions" / inst_id
        inst_dir.mkdir(parents=True)

        ledger = get_ledger_for_institution(inst_id)
        ledger.set_bundle_hashes("x", "x")

        # Actor in finance
        ledger.append(
            event_type="RBAC_DECISION",
            tenant_id="t",
            actor_id="finance-actor",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={},
            dept_id="finance",
        )

        # Actor in hr
        ledger.append(
            event_type="RBAC_DECISION",
            tenant_id="t",
            actor_id="hr-actor",
            actor_roles=[],
            case_id="c",
            step="s",
            payload={},
            dept_id="hr",
        )

        # All actors
        all_actors = list_unique_actors(inst_id)
        assert set(all_actors) == {"finance-actor", "hr-actor"}

        # Finance only
        finance_actors = list_unique_actors(inst_id, dept_id="finance")
        assert finance_actors == ["finance-actor"]

        # HR only
        hr_actors = list_unique_actors(inst_id, dept_id="hr")
        assert hr_actors == ["hr-actor"]
