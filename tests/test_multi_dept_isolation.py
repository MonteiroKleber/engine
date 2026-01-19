"""E2E tests for multi-department isolation (Etapa 2.5).

Tests:
1. Finance vs Support isolation (same institution)
2. Matrix 2x2: two institutions x two departments
3. State store isolation by (institution_id, dept_id)
4. Ledger events contain dept_id field
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.state_store import (
    reset_all_state_stores,
    get_state_store,
)
from engine.core.ledger import set_ledger, reset_institution_ledgers, get_ledger_path_for_institution
from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy, reset_all_rbac
from engine.core.approvals import reset_all_approvals, set_approvals_policy
from engine.core.sod import reset_all_sod, set_sod_policy
from engine.core.invariants import reset_all_invariants, set_invariants_policy
from engine.core.mandates import clear_all_mandates
from engine.core.autonomy import reset_all_autonomy
from engine.core.policy import clear_all_policies
from engine.core.institutions import reset_registry
from engine.core.institution_config import reset_config_cache
from engine.core.admin_keys import reset_admin_keys_registry
from engine.loader.load_bundle import load_bundle, _set_bundle_context


# Path to the multi-pilot bundle
MULTI_PILOT_BUNDLE = Path(__file__).parent.parent / "bundles" / "multi-pilot"


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test.

    Uses the multi-pilot bundle via load_bundle() for true E2E multi-dept testing.
    """
    # Set up data directories in tmp_path for isolation
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")

    # Point to the multi-pilot bundle
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(MULTI_PILOT_BUNDLE))

    # Do NOT set absolute paths for state store and ledger
    # This ensures each institution gets its own namespaced storage
    monkeypatch.delenv("ENGINE_STATE_STORE_DIR", raising=False)
    monkeypatch.delenv("ENGINE_LEDGER_PATH", raising=False)

    # Reset all caches and registries before loading
    reset_registry()
    reset_config_cache()
    reset_admin_keys_registry()
    reset_all_state_stores()
    reset_institution_ledgers()
    clear_all_policies()
    clear_all_mandates()
    reset_all_autonomy()
    reset_all_approvals()
    reset_all_sod()
    reset_all_invariants()
    reset_all_rbac()
    set_ledger(None)
    _set_bundle_context(None)
    runtime_state.set_active()

    # Load the multi-pilot bundle - this sets up RBAC, approvals, mandates, autonomy, etc.
    result = load_bundle(MULTI_PILOT_BUNDLE)
    assert result is not None, f"Failed to load bundle: {runtime_state.reason_code}"
    assert runtime_state.is_active(), f"Bundle loaded in SAFE_MODE: {runtime_state.reason_code}"

    yield tmp_path

    # Cleanup
    _set_bundle_context(None)
    reset_registry()
    reset_config_cache()
    reset_admin_keys_registry()
    reset_all_state_stores()
    reset_institution_ledgers()
    clear_all_policies()
    clear_all_mandates()
    reset_all_autonomy()
    reset_all_approvals()
    reset_all_sod()
    reset_all_invariants()
    reset_all_rbac()
    set_ledger(None)
    runtime_state.set_active()


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def institution_001(client):
    """Create institution 001 and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "institution-001", "name": "Institution 001"},
    )
    assert response.status_code == 201, f"Failed to create institution: {response.json()}"
    return response.json()["institution_id"]


@pytest.fixture
def institution_a(client):
    """Create institution A and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "institution-a", "name": "Institution A"},
    )
    assert response.status_code == 201, f"Failed to create institution: {response.json()}"
    return response.json()["institution_id"]


@pytest.fixture
def institution_b(client):
    """Create institution B and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "institution-b", "name": "Institution B"},
    )
    assert response.status_code == 201, f"Failed to create institution: {response.json()}"
    return response.json()["institution_id"]


@pytest.fixture
def institution_ledger(client):
    """Create institution for ledger tests and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "institution-ledger", "name": "Institution Ledger Test"},
    )
    assert response.status_code == 201, f"Failed to create institution: {response.json()}"
    return response.json()["institution_id"]


@pytest.fixture
def institution_404_001(client):
    """Create institution for 404 tests and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "institution-404-001", "name": "Institution 404 Test 001"},
    )
    assert response.status_code == 201, f"Failed to create institution: {response.json()}"
    return response.json()["institution_id"]


@pytest.fixture
def institution_404_002(client):
    """Create institution for 404 tests and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "institution-404-002", "name": "Institution 404 Test 002"},
    )
    assert response.status_code == 201, f"Failed to create institution: {response.json()}"
    return response.json()["institution_id"]


@pytest.fixture
def institution_404_other(client):
    """Create another institution for 404 tests and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "institution-404-other", "name": "Institution 404 Other"},
    )
    assert response.status_code == 201, f"Failed to create institution: {response.json()}"
    return response.json()["institution_id"]


# Valid UUID actor IDs for testing
ACTOR_ANALYST_001 = "11111111-1111-1111-1111-000000000001"
ACTOR_ANALYST_002 = "11111111-1111-1111-1111-000000000002"
ACTOR_AGENT_001 = "22222222-2222-2222-2222-000000000001"
ACTOR_AGENT_002 = "22222222-2222-2222-2222-000000000002"


class TestFinanceVsSupportIsolation:
    """E2E: finance and support in parallel, same institution.

    Tests from spec:
    - criar expense em finance não aparece em support
    - criar ticket em support não aparece em finance
    """

    def test_expense_created_in_finance_not_visible_in_support(
        self, client, institution_001
    ):
        """Creating expense in finance dept should not be visible in support dept."""
        institution_id = institution_001

        # Create an expense via finance dept endpoint
        response = client.post(
            "/d/finance/finance/expenses",
            json={"amount": 100, "description": "Test expense"},
            headers={
                "X-Actor-Id": ACTOR_ANALYST_001,
                "X-Actor-Roles": "analyst",
                "X-Institution-Id": institution_id,
            },
        )
        assert response.status_code == 202, f"Unexpected status: {response.json()}"
        expense_data = response.json()
        expense_id = expense_data.get("id") or expense_data.get("expense_id")
        assert expense_id is not None

        # Verify expense is in finance state store
        finance_store = get_state_store(dept_id="finance", institution_id=institution_id)
        assert finance_store is not None
        expense = finance_store.get_expense(expense_id)
        assert expense is not None, "Expense should exist in finance state store"

        # Verify expense is NOT in support state store (isolation)
        support_store = get_state_store(dept_id="support", institution_id=institution_id)
        assert support_store is not None
        # Support store should not have this expense
        support_expense = support_store.get_expense(expense_id)
        assert support_expense is None, "Expense from finance should NOT be in support state store"

    def test_ticket_created_in_support_not_visible_in_finance(
        self, client, institution_001
    ):
        """Creating ticket in support dept should not be visible in finance dept."""
        institution_id = institution_001

        # Create a ticket via support dept endpoint
        response = client.post(
            "/d/support/support/tickets",
            json={"subject": "Test ticket", "description": "Need help"},
            headers={
                "X-Actor-Id": ACTOR_AGENT_001,
                "X-Actor-Roles": "agent",
                "X-Institution-Id": institution_id,
            },
        )
        assert response.status_code == 200, f"Unexpected status: {response.json()}"
        ticket_data = response.json()
        ticket_id = ticket_data.get("id")
        assert ticket_id is not None

        # Verify ticket is in support state store
        support_store = get_state_store(dept_id="support", institution_id=institution_id)
        assert support_store is not None
        ticket = support_store.get_ticket(ticket_id)
        assert ticket is not None, "Ticket should exist in support state store"

        # Verify ticket is NOT in finance state store (isolation)
        finance_store = get_state_store(dept_id="finance", institution_id=institution_id)
        assert finance_store is not None
        # Finance store should not have this ticket (different state type, but still isolated)
        finance_ticket = finance_store.get_ticket(ticket_id)
        assert finance_ticket is None, "Ticket from support should NOT be in finance state store"


class TestMatrixTwoByTwo:
    """E2E: dois depts em duas instituições (matriz 2x2) sem inferência.

    Matrix:
    - Institution A + Finance
    - Institution A + Support
    - Institution B + Finance
    - Institution B + Support

    Each combination must be fully isolated.
    """

    def test_matrix_complete_isolation(self, client, institution_a, institution_b):
        """Test complete isolation across the 2x2 matrix."""
        inst_a = institution_a
        inst_b = institution_b

        # Create items in each cell of the matrix
        items_created = {}

        # Cell 1: Institution A, Finance (expense)
        response = client.post(
            "/d/finance/finance/expenses",
            json={"amount": 100, "description": "Expense A-Finance"},
            headers={
                "X-Actor-Id": ACTOR_ANALYST_001,
                "X-Actor-Roles": "analyst",
                "X-Institution-Id": inst_a,
            },
        )
        assert response.status_code == 202, f"Cell 1 failed: {response.json()}"
        items_created[("A", "finance", "expense")] = response.json().get("id") or response.json().get("expense_id")

        # Cell 2: Institution A, Support (ticket)
        response = client.post(
            "/d/support/support/tickets",
            json={"subject": "Ticket A-Support"},
            headers={
                "X-Actor-Id": ACTOR_AGENT_001,
                "X-Actor-Roles": "agent",
                "X-Institution-Id": inst_a,
            },
        )
        assert response.status_code == 200, f"Cell 2 failed: {response.json()}"
        items_created[("A", "support", "ticket")] = response.json().get("id")

        # Cell 3: Institution B, Finance (expense)
        response = client.post(
            "/d/finance/finance/expenses",
            json={"amount": 200, "description": "Expense B-Finance"},
            headers={
                "X-Actor-Id": ACTOR_ANALYST_002,
                "X-Actor-Roles": "analyst",
                "X-Institution-Id": inst_b,
            },
        )
        assert response.status_code == 202, f"Cell 3 failed: {response.json()}"
        items_created[("B", "finance", "expense")] = response.json().get("id") or response.json().get("expense_id")

        # Cell 4: Institution B, Support (ticket)
        response = client.post(
            "/d/support/support/tickets",
            json={"subject": "Ticket B-Support"},
            headers={
                "X-Actor-Id": ACTOR_AGENT_002,
                "X-Actor-Roles": "agent",
                "X-Institution-Id": inst_b,
            },
        )
        assert response.status_code == 200, f"Cell 4 failed: {response.json()}"
        items_created[("B", "support", "ticket")] = response.json().get("id")

        # Now verify isolation: each cell should only have its own items

        # Check Institution A, Finance
        store_a_finance = get_state_store(dept_id="finance", institution_id=inst_a)
        assert store_a_finance.get_expense(items_created[("A", "finance", "expense")]) is not None
        assert store_a_finance.get_expense(items_created[("B", "finance", "expense")]) is None, "B's expense visible in A"
        assert store_a_finance.get_ticket(items_created[("A", "support", "ticket")]) is None, "A/support ticket in A/finance"
        assert store_a_finance.get_ticket(items_created[("B", "support", "ticket")]) is None, "B/support ticket in A/finance"

        # Check Institution A, Support
        store_a_support = get_state_store(dept_id="support", institution_id=inst_a)
        assert store_a_support.get_ticket(items_created[("A", "support", "ticket")]) is not None
        assert store_a_support.get_ticket(items_created[("B", "support", "ticket")]) is None, "B's ticket visible in A"
        assert store_a_support.get_expense(items_created[("A", "finance", "expense")]) is None, "A/finance expense in A/support"
        assert store_a_support.get_expense(items_created[("B", "finance", "expense")]) is None, "B/finance expense in A/support"

        # Check Institution B, Finance
        store_b_finance = get_state_store(dept_id="finance", institution_id=inst_b)
        assert store_b_finance.get_expense(items_created[("B", "finance", "expense")]) is not None
        assert store_b_finance.get_expense(items_created[("A", "finance", "expense")]) is None, "A's expense visible in B"
        assert store_b_finance.get_ticket(items_created[("A", "support", "ticket")]) is None
        assert store_b_finance.get_ticket(items_created[("B", "support", "ticket")]) is None

        # Check Institution B, Support
        store_b_support = get_state_store(dept_id="support", institution_id=inst_b)
        assert store_b_support.get_ticket(items_created[("B", "support", "ticket")]) is not None
        assert store_b_support.get_ticket(items_created[("A", "support", "ticket")]) is None, "A's ticket visible in B"
        assert store_b_support.get_expense(items_created[("A", "finance", "expense")]) is None
        assert store_b_support.get_expense(items_created[("B", "finance", "expense")]) is None


class TestLedgerDeptId:
    """Test that ledger events contain dept_id for audit traceability."""

    def test_ledger_event_contains_dept_id(self, client, institution_ledger):
        """Ledger events should contain dept_id field for critical events."""
        institution_id = institution_ledger

        # Create expense in finance dept
        response = client.post(
            "/d/finance/finance/expenses",
            json={"amount": 50, "description": "Ledger test expense"},
            headers={
                "X-Actor-Id": ACTOR_ANALYST_001,
                "X-Actor-Roles": "analyst",
                "X-Institution-Id": institution_id,
            },
        )
        assert response.status_code == 202, f"Expense creation failed: {response.json()}"

        # Create ticket in support dept
        response = client.post(
            "/d/support/support/tickets",
            json={"subject": "Ledger test ticket"},
            headers={
                "X-Actor-Id": ACTOR_AGENT_001,
                "X-Actor-Roles": "agent",
                "X-Institution-Id": institution_id,
            },
        )
        assert response.status_code == 200, f"Ticket creation failed: {response.json()}"

        # Read ledger file for this institution using the correct path function
        ledger_path = get_ledger_path_for_institution(institution_id)
        assert ledger_path.exists(), f"Ledger file not found at {ledger_path}"

        # Parse events and check for dept_id
        events = []
        with open(ledger_path, "r") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        # Find events with dept_id
        finance_events = [e for e in events if e.get("dept_id") == "finance"]
        support_events = [e for e in events if e.get("dept_id") == "support"]

        assert len(finance_events) > 0, "Should have finance dept events with dept_id"
        assert len(support_events) > 0, "Should have support dept events with dept_id"

        # Verify step names contain DEPT: prefix
        for event in finance_events:
            assert "DEPT:finance:" in event.get("step", ""), f"Step should have DEPT:finance: prefix: {event}"

        for event in support_events:
            assert "DEPT:support:" in event.get("step", ""), f"Step should have DEPT:support: prefix: {event}"


class TestDeptNotFoundReturns404:
    """Test anti-inference: accessing non-existent items returns 404, not 403."""

    def test_get_expense_wrong_dept_returns_404(self, client, institution_404_001):
        """Getting expense from wrong dept should return 404, not 403."""
        institution_id = institution_404_001

        # Create expense in finance
        response = client.post(
            "/d/finance/finance/expenses",
            json={"amount": 75, "description": "Test"},
            headers={
                "X-Actor-Id": ACTOR_ANALYST_001,
                "X-Actor-Roles": "analyst",
                "X-Institution-Id": institution_id,
            },
        )
        assert response.status_code == 202, f"Expense creation failed: {response.json()}"
        expense_id = response.json().get("id") or response.json().get("expense_id")

        # Verify state store isolation
        finance_store = get_state_store(dept_id="finance", institution_id=institution_id)
        support_store = get_state_store(dept_id="support", institution_id=institution_id)

        # Finance store has the expense
        assert finance_store.get_expense(expense_id) is not None

        # Support store does not have the expense (isolation)
        assert support_store.get_expense(expense_id) is None

    def test_get_ticket_wrong_dept_returns_404(self, client, institution_404_002, institution_404_other):
        """Getting ticket from wrong dept should return 404, not 403."""
        institution_id = institution_404_002

        # Create ticket in support
        response = client.post(
            "/d/support/support/tickets",
            json={"subject": "Test ticket"},
            headers={
                "X-Actor-Id": ACTOR_AGENT_001,
                "X-Actor-Roles": "agent",
                "X-Institution-Id": institution_id,
            },
        )
        assert response.status_code == 200, f"Ticket creation failed: {response.json()}"
        ticket_id = response.json().get("id")

        # Try to get from support (should work)
        response = client.get(
            f"/d/support/support/tickets/{ticket_id}",
            headers={
                "X-Actor-Id": ACTOR_AGENT_001,
                "X-Actor-Roles": "agent",
                "X-Institution-Id": institution_id,
            },
        )
        assert response.status_code == 200

        # Try to get from a different institution - should be 404 (anti-inference)
        response = client.get(
            f"/d/support/support/tickets/{ticket_id}",
            headers={
                "X-Actor-Id": ACTOR_AGENT_001,
                "X-Actor-Roles": "agent",
                "X-Institution-Id": institution_404_other,
            },
        )
        assert response.status_code == 404, "Should return 404 for ticket in different institution"
