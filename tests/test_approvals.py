"""Tests for Approvals MVP (Etapa 3.4)."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy, RBACPolicy
from engine.core.approvals import set_approvals_policy, ApprovalsPolicy
from engine.core.ledger import set_ledger, init_ledger, AuditLedger, get_ledger
from engine.core.actor_context import DEFAULT_TENANT_ID
from engine.loader.load_bundle import load_bundle
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    """Create a temporary ledger path."""
    return tmp_path / "audit_ledger.jsonl"


@pytest.fixture(autouse=True)
def reset_state(ledger_path: Path, monkeypatch):
    """Reset all state before each test."""
    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_ledger(None)

    # Set ledger path env
    monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

    yield

    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
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


def create_bundle_with_approvals(bundle_path: Path) -> None:
    """Create a bundle with RBAC and approvals config."""
    # Create RBAC with analyst (expense.create) and manager (approver)
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
        ],
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


class TestExpenseCreatesApprovalRequest:
    """Test POST /finance/expenses returns 202 with APPROVAL_REQUESTED event."""

    def test_expense_returns_202_with_approval_pending(self, tmp_path: Path, ledger_path: Path):
        """POST /finance/expenses should return 202 and emit APPROVAL_REQUESTED."""
        # Setup bundle
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # POST expense as analyst (has expense.create permission)
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "test expense"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending_approval"
        assert "approval_id" in data
        assert data["step"] == "APPROVAL:expense.create"

        # Verify APPROVAL_REQUESTED event in ledger
        ledger = get_ledger()
        events = ledger.get_all_events()

        approval_events = [e for e in events if e.event_type == "APPROVAL_REQUESTED"]
        assert len(approval_events) == 1

        event = approval_events[0]
        assert event.case_id == data["approval_id"]
        assert event.step == "APPROVAL:expense.create"
        assert event.actor_id == actor_id
        assert event.payload["decision"] is None
        assert event.payload["name"] == "APPROVAL:expense.create"
        assert event.payload["requested_by"] == actor_id
        assert event.payload["required_roles"] == ["manager"]


class TestDecideWithoutRole:
    """Test decide without required role returns 403."""

    def test_decide_without_manager_role_returns_403(self, tmp_path: Path, ledger_path: Path):
        """Actor without manager role should get 403 APPROVAL_FORBIDDEN."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        # Create approval request as analyst
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )
        assert response.status_code == 202
        approval_id = response.json()["approval_id"]

        # Try to decide as analyst (not manager)
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"decision": "approve"},
        )

        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "APPROVAL_FORBIDDEN"


class TestDecideWithManagerRole:
    """Test decide with manager role returns 200."""

    def test_decide_with_manager_role_returns_200(self, tmp_path: Path, ledger_path: Path):
        """Manager can approve and APPROVAL_DECIDED event is emitted."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # Create approval request as analyst
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )
        assert response.status_code == 202
        approval_id = response.json()["approval_id"]

        # Decide as manager
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve", "reason": "Approved for Q1 budget"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "decided"
        assert data["approval_id"] == approval_id
        assert data["decision"] == "approve"

        # Verify APPROVAL_DECIDED event in ledger
        ledger = get_ledger()
        events = ledger.get_all_events()

        decided_events = [e for e in events if e.event_type == "APPROVAL_DECIDED"]
        assert len(decided_events) == 1

        event = decided_events[0]
        assert event.case_id == approval_id
        assert event.step == "APPROVAL:expense.create"
        assert event.actor_id == manager_id
        assert event.payload["decision"] == "approve"
        assert event.payload["decided_by"] == manager_id
        assert event.payload["reason"] == "Approved for Q1 budget"

    def test_reject_approval(self, tmp_path: Path, ledger_path: Path):
        """Manager can reject an approval."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # Create approval request
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )
        approval_id = response.json()["approval_id"]

        # Reject as manager
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "reject", "reason": "Over budget"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "reject"


class TestReDecide:
    """Test re-decide returns 409."""

    def test_re_decide_returns_409(self, tmp_path: Path, ledger_path: Path):
        """Cannot decide on already decided approval."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # Create approval request
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )
        approval_id = response.json()["approval_id"]

        # First decision - approve
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )
        assert response.status_code == 200

        # Second decision - should fail
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "reject"},
        )

        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "APPROVAL_ALREADY_DECIDED"


class TestDecideNonexistentApproval:
    """Test decide on nonexistent approval returns 404."""

    def test_decide_nonexistent_returns_404(self, tmp_path: Path, ledger_path: Path):
        """Cannot decide on approval that doesn't exist."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        manager_id = str(uuid.uuid4())
        fake_approval_id = str(uuid.uuid4())

        response = client.post(
            f"/approvals/{fake_approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "APPROVAL_NOT_FOUND"


class TestHistoryTracking:
    """Test history(approval_id, step) tracks actors/count/last_actor/last_at."""

    def test_history_tracks_approval_events(self, tmp_path: Path, ledger_path: Path):
        """History should track all events for an approval."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # Create approval request
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )
        approval_id = response.json()["approval_id"]
        step = "APPROVAL:expense.create"

        # Check history after request
        ledger = get_ledger()
        history1 = ledger.history(approval_id, step)

        assert history1.count == 1
        assert analyst_id in history1.actors
        assert history1.last_actor == analyst_id
        assert history1.last_at is not None

        # Decide as manager
        client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        # Check history after decision
        history2 = ledger.history(approval_id, step)

        assert history2.count == 2
        assert analyst_id in history2.actors
        assert manager_id in history2.actors
        assert len(history2.actors) == 2
        assert history2.last_actor == manager_id


class TestInvalidDecision:
    """Test invalid decision value returns 400."""

    def test_invalid_decision_value_returns_400(self, tmp_path: Path, ledger_path: Path):
        """Decision must be 'approve' or 'reject'."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # Create approval request
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )
        approval_id = response.json()["approval_id"]

        # Try invalid decision
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "maybe"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "APPROVAL_DECISION_INVALID"


class TestPayloadSha256:
    """Test payload_sha256 is computed correctly."""

    def test_payload_sha256_in_event(self, tmp_path: Path, ledger_path: Path):
        """APPROVAL_REQUESTED should include payload_sha256."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # POST with specific payload
        payload = {"amount": 100, "description": "test"}
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json=payload,
        )

        assert response.status_code == 202

        # Check payload_sha256 in event
        ledger = get_ledger()
        events = ledger.get_all_events()
        approval_events = [e for e in events if e.event_type == "APPROVAL_REQUESTED"]

        assert len(approval_events) == 1
        event = approval_events[0]
        assert "payload_sha256" in event.payload
        assert len(event.payload["payload_sha256"]) == 64  # SHA256 hex length
