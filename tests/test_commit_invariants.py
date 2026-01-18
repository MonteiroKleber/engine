"""Tests for Commit + Invariants (Etapa 3.6)."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy
from engine.core.approvals import set_approvals_policy
from engine.core.sod import set_sod_policy
from engine.core.invariants import set_invariants_policy
from engine.core.state_store import set_state_store, get_state_store, STATUS_PENDING_APPROVAL, STATUS_COMMITTED, STATUS_REJECTED
from engine.core.ledger import set_ledger, get_ledger
from engine.loader.load_bundle import load_bundle
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    """Create a temporary ledger path."""
    return tmp_path / "audit_ledger.jsonl"


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    """Create a temporary state store path."""
    return tmp_path / "state_store.json"


@pytest.fixture(autouse=True)
def reset_state(ledger_path: Path, state_path: Path, monkeypatch):
    """Reset all state before each test."""
    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_sod_policy(None)
    set_invariants_policy(None)
    set_state_store(None)
    set_ledger(None)

    # Set paths via env
    monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))
    monkeypatch.setenv("ENGINE_STATE_PATH", str(state_path))

    yield

    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_sod_policy(None)
    set_invariants_policy(None)
    set_state_store(None)
    set_ledger(None)


def create_rbac_json(bundle_path: Path, roles: list) -> str:
    """Create rbac.json and return its SHA-256 hash."""
    rbac_data = {
        "version": "1.0.0",
        "name": "rbac",
        "roles": roles,
    }
    rbac_path = bundle_path / "rbac.json"
    with open(rbac_path, "w", encoding="utf-8") as f:
        json.dump(rbac_data, f)
    return compute_sha256(rbac_path)


def create_approvals_json(bundle_path: Path, rules: list) -> str:
    """Create approvals.json and return its SHA-256 hash."""
    approvals_data = {
        "version": "1.0.0",
        "name": "approvals",
        "rules": rules,
    }
    approvals_path = bundle_path / "approvals.json"
    with open(approvals_path, "w", encoding="utf-8") as f:
        json.dump(approvals_data, f)
    return compute_sha256(approvals_path)


def create_sod_json(bundle_path: Path, rules: list) -> str:
    """Create sod.json and return its SHA-256 hash."""
    sod_data = {
        "version": "1.0.0",
        "name": "sod",
        "rules": rules,
    }
    sod_path = bundle_path / "sod.json"
    with open(sod_path, "w", encoding="utf-8") as f:
        json.dump(sod_data, f)
    return compute_sha256(sod_path)


def create_invariants_json(bundle_path: Path, expense_schema: dict) -> str:
    """Create invariants.json and return its SHA-256 hash."""
    invariants_data = {
        "version": "1.0.0",
        "name": "invariants",
        "expense": expense_schema,
    }
    invariants_path = bundle_path / "invariants.json"
    with open(invariants_path, "w", encoding="utf-8") as f:
        json.dump(invariants_data, f)
    return compute_sha256(invariants_path)


def create_bundle_with_invariants(bundle_path: Path, expense_schema: dict) -> None:
    """Create a bundle with RBAC, approvals, SoD, and invariants."""
    # Create RBAC
    rbac_hash = create_rbac_json(bundle_path, [
        {"name": "analyst", "permissions": ["expense.create", "expense.read"]},
        {"name": "manager", "permissions": ["expense.create", "expense.read", "expense.approve"]},
    ])

    # Create approvals rule
    approvals_hash = create_approvals_json(bundle_path, [
        {
            "rule_name": "expense.create",
            "trigger": {"api": "POST /finance/expenses"},
            "approver_roles": ["manager"],
            "quorum": 1,
        }
    ])

    # Create SoD rules (no self-approval for now to simplify tests)
    sod_hash = create_sod_json(bundle_path, [])

    # Create invariants
    invariants_hash = create_invariants_json(bundle_path, expense_schema)

    # Create manifest
    manifest = {
        "name": "test-bundle",
        "version": "1.0.0",
        "contracts": [
            {
                "file": "rbac.json",
                "sha256": f"SHA256:{rbac_hash}",
                "required": True,
            },
            {
                "file": "approvals.json",
                "sha256": f"SHA256:{approvals_hash}",
                "required": True,
            },
            {
                "file": "sod.json",
                "sha256": f"SHA256:{sod_hash}",
                "required": True,
            },
            {
                "file": "invariants.json",
                "sha256": f"SHA256:{invariants_hash}",
                "required": True,
            },
        ],
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


class TestCreateExpenseWithStateStore:
    """Test POST /finance/expenses creates state store entry."""

    def test_create_expense_returns_202_with_expense_id(self, tmp_path: Path):
        """Create expense should return 202 with expense_id and approval_id."""
        expense_schema = {
            "amount": {"min": 0.01, "max": 1000000000},
            "description": {"max_len": 280, "required": False},
        }
        create_bundle_with_invariants(tmp_path, expense_schema)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "test expense"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending_approval"
        assert "expense_id" in data
        assert "approval_id" in data
        assert data["step"] == "APPROVAL:expense.create"

        # Verify state store contains expense
        state_store = get_state_store()
        expense = state_store.get_expense(data["expense_id"])
        assert expense is not None
        assert expense.status == STATUS_PENDING_APPROVAL
        assert expense.approval_id == data["approval_id"]

        # Verify approval_index mapping
        expense_by_approval = state_store.get_expense_by_approval_id(data["approval_id"])
        assert expense_by_approval is not None
        assert expense_by_approval.expense_id == data["expense_id"]


class TestApproveWithValidAmount:
    """Test approve with valid amount commits successfully."""

    def test_approve_valid_expense_commits(self, tmp_path: Path):
        """Approve expense with valid amount should commit and emit CASE_COMMITTED."""
        expense_schema = {
            "amount": {"min": 0.01, "max": 1000000000},
            "description": {"max_len": 280, "required": False},
        }
        create_bundle_with_invariants(tmp_path, expense_schema)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # Create expense
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "valid expense"},
        )

        assert response.status_code == 202
        expense_id = response.json()["expense_id"]
        approval_id = response.json()["approval_id"]

        # Approve as manager
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "decided"
        assert data["decision"] == "approve"
        assert data["case_status"] == STATUS_COMMITTED
        assert data["expense_id"] == expense_id

        # Verify state store updated
        state_store = get_state_store()
        expense = state_store.get_expense(expense_id)
        assert expense.status == STATUS_COMMITTED

        # Verify CASE_COMMITTED event in ledger
        ledger = get_ledger()
        events = ledger.get_all_events()
        committed_events = [e for e in events if e.event_type == "CASE_COMMITTED"]
        assert len(committed_events) == 1

        event = committed_events[0]
        assert event.case_id == expense_id
        assert event.step == "CASE:expense.commit"
        assert event.payload["name"] == "CASE:expense.commit"


class TestApproveWithInvalidAmount:
    """Test approve with invalid amount returns 422 INVARIANT_VIOLATION."""

    def test_approve_zero_amount_returns_422(self, tmp_path: Path):
        """Approve expense with amount=0 should return 422 and no events emitted."""
        expense_schema = {
            "amount": {"min": 0.01, "max": 1000000000},
            "description": {"max_len": 280, "required": False},
        }
        create_bundle_with_invariants(tmp_path, expense_schema)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # Create expense with amount=0
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 0, "description": "invalid expense"},
        )

        assert response.status_code == 202
        expense_id = response.json()["expense_id"]
        approval_id = response.json()["approval_id"]

        # Try to approve - should fail invariant check
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "INVARIANT_VIOLATION"
        assert len(data["violations"]) > 0

        # Verify NO CASE_COMMITTED event
        ledger = get_ledger()
        events = ledger.get_all_events()
        committed_events = [e for e in events if e.event_type == "CASE_COMMITTED"]
        assert len(committed_events) == 0

        # Verify NO APPROVAL_DECIDED event (for this approval)
        decided_events = [e for e in events if e.event_type == "APPROVAL_DECIDED" and e.case_id == approval_id]
        assert len(decided_events) == 0

        # Verify state store still PENDING_APPROVAL
        state_store = get_state_store()
        expense = state_store.get_expense(expense_id)
        assert expense.status == STATUS_PENDING_APPROVAL


class TestRejectExpense:
    """Test reject expense returns REJECTED status."""

    def test_reject_expense_returns_rejected(self, tmp_path: Path):
        """Reject expense should update status and emit CASE_REJECTED."""
        expense_schema = {
            "amount": {"min": 0.01, "max": 1000000000},
            "description": {"max_len": 280, "required": False},
        }
        create_bundle_with_invariants(tmp_path, expense_schema)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # Create expense
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "expense to reject"},
        )

        assert response.status_code == 202
        expense_id = response.json()["expense_id"]
        approval_id = response.json()["approval_id"]

        # Reject as manager
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "reject", "reason": "Not approved"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "decided"
        assert data["decision"] == "reject"
        assert data["case_status"] == STATUS_REJECTED
        assert data["expense_id"] == expense_id

        # Verify state store updated
        state_store = get_state_store()
        expense = state_store.get_expense(expense_id)
        assert expense.status == STATUS_REJECTED

        # Verify CASE_REJECTED event in ledger
        ledger = get_ledger()
        events = ledger.get_all_events()
        rejected_events = [e for e in events if e.event_type == "CASE_REJECTED"]
        assert len(rejected_events) == 1

        event = rejected_events[0]
        assert event.case_id == expense_id
        assert event.step == "CASE:expense.reject"
        assert event.payload["name"] == "CASE:expense.reject"

        # Verify APPROVAL_DECIDED also emitted
        decided_events = [e for e in events if e.event_type == "APPROVAL_DECIDED"]
        assert len(decided_events) == 1
