"""Tests for SoD enforcement MVP (Etapa 3.5)."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy
from engine.core.approvals import set_approvals_policy
from engine.core.sod import set_sod_policy
from engine.core.ledger import set_ledger, get_ledger
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
    set_sod_policy(None)
    set_ledger(None)

    # Set ledger path env
    monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

    yield

    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_sod_policy(None)
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


def create_bundle_with_sod(bundle_path: Path, sod_rules: list) -> None:
    """Create a bundle with RBAC, approvals, and SoD config."""
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

    # Create SoD rules
    sod_hash = create_sod_json(bundle_path, sod_rules)

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
        ],
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


class TestSelfApprovalBlocked:
    """Test self-approval is blocked with SOD_VIOLATION."""

    def test_self_approval_returns_409_sod_violation(self, tmp_path: Path, ledger_path: Path):
        """Requester cannot approve their own request."""
        # Create bundle with SoD rule
        create_bundle_with_sod(tmp_path, [
            {
                "rule_name": "expense.create.requester_not_approver",
                "case_step": "APPROVAL:expense.create",
                "constraint": "REQUESTER_NEQ_DECIDER",
            }
        ])
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # Create approval request as analyst with manager role (can both create and approve)
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst,manager",  # Has both roles
            },
            json={"amount": 100, "description": "test expense"},
        )

        assert response.status_code == 202
        approval_id = response.json()["approval_id"]

        # Try to self-approve - should be blocked by SoD
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": actor_id,  # Same actor trying to approve
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "SOD_VIOLATION"
        assert data["message"] == "Separation of duties violation"

        # Verify NO APPROVAL_DECIDED event was created
        ledger = get_ledger()
        events = ledger.get_all_events()
        decided_events = [e for e in events if e.event_type == "APPROVAL_DECIDED"]
        assert len(decided_events) == 0


class TestDifferentActorApprovalAllowed:
    """Test approval by different actor is allowed."""

    def test_different_actor_approval_returns_200(self, tmp_path: Path, ledger_path: Path):
        """Different actor can approve the request."""
        # Create bundle with SoD rule
        create_bundle_with_sod(tmp_path, [
            {
                "rule_name": "expense.create.requester_not_approver",
                "case_step": "APPROVAL:expense.create",
                "constraint": "REQUESTER_NEQ_DECIDER",
            }
        ])
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

        # Approve as different manager
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,  # Different actor
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve", "reason": "Looks good"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "decided"
        assert data["decision"] == "approve"

        # Verify APPROVAL_DECIDED event was created
        ledger = get_ledger()
        events = ledger.get_all_events()
        decided_events = [e for e in events if e.event_type == "APPROVAL_DECIDED"]
        assert len(decided_events) == 1

        event = decided_events[0]
        assert event.case_id == approval_id
        assert event.actor_id == manager_id
        assert event.payload["decision"] == "approve"


class TestInvalidConstraint:
    """Test invalid constraint returns SOD_RULE_INVALID."""

    def test_invalid_constraint_returns_500(self, tmp_path: Path, ledger_path: Path):
        """Invalid constraint in sod.json should return 500 SOD_RULE_INVALID."""
        # Create bundle with invalid SoD constraint
        create_bundle_with_sod(tmp_path, [
            {
                "rule_name": "expense.create.invalid",
                "case_step": "APPROVAL:expense.create",
                "constraint": "INVALID_CONSTRAINT",  # Invalid constraint
            }
        ])
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

        assert response.status_code == 202
        approval_id = response.json()["approval_id"]

        # Try to approve - should fail with SOD_RULE_INVALID
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        assert response.status_code == 500
        data = response.json()
        assert data["code"] == "SOD_RULE_INVALID"
        assert "INVALID_CONSTRAINT" in data["message"]


class TestNoSodRules:
    """Test approval works when no SoD rules exist."""

    def test_approval_allowed_without_sod_rules(self, tmp_path: Path, ledger_path: Path):
        """Approval should work when no SoD rules exist for the step."""
        # Create bundle with empty SoD rules
        create_bundle_with_sod(tmp_path, [])
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # Create approval request
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst,manager",
            },
            json={"amount": 100},
        )

        assert response.status_code == 202
        approval_id = response.json()["approval_id"]

        # Self-approve should work (no SoD rules)
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "decided"
