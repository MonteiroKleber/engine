"""Tests for GET /approvals/pending endpoint (Hotfix 4.x)."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy
from engine.core.approvals import set_approvals_policy
from engine.core.ledger import set_ledger, get_ledger
from engine.core.institutions import reset_registry
from engine.core.institution_context import DEFAULT_INSTITUTION_ID
from engine.loader.load_bundle import load_bundle
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    """Create a temporary ledger path."""
    return tmp_path / "audit_ledger.jsonl"


@pytest.fixture(autouse=True)
def reset_state(ledger_path: Path, monkeypatch, tmp_path: Path):
    """Reset all state before each test."""
    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_ledger(None)

    # Set ledger path env
    monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

    # Set admin token for tests (works only for DEFAULT institution)
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")

    # Set up institutions storage
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    reset_registry()

    yield

    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_ledger(None)
    reset_registry()


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
    rbac_hash = create_rbac_json(bundle_path, [
        {"name": "analyst", "permissions": ["expense.create", "expense.read"]},
        {"name": "manager", "permissions": ["expense.create", "expense.read", "expense.approve"]},
    ])

    approvals_hash = create_approvals_json(bundle_path, [
        {
            "rule_name": "expense.create",
            "trigger": {"api": "POST /finance/expenses"},
            "approver_roles": ["manager"],
            "quorum": 1,
        }
    ])

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


class TestListPendingApprovals:
    """Tests for GET /approvals/pending endpoint.

    Note: These tests use DEFAULT_INSTITUTION_ID with X-Admin-Token
    because X-Admin-Token only works for the default institution.
    Per-institution auth uses X-Admin-Key which requires setup.
    """

    def test_list_pending_with_one_approval(self, tmp_path: Path, ledger_path: Path):
        """Should list one pending approval after creating an expense."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        # Create approval request as analyst (uses DEFAULT institution implicitly)
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "test expense"},
        )

        assert response.status_code == 202
        approval_id = response.json()["approval_id"]

        # List pending approvals for DEFAULT institution
        response = client.get(
            "/approvals/pending",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": DEFAULT_INSTITUTION_ID,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] >= 1
        assert len(data["approvals"]) >= 1

        # Find our approval in the list
        our_approval = next(
            (a for a in data["approvals"] if a["approval_id"] == approval_id),
            None
        )
        assert our_approval is not None, f"Approval {approval_id} not found in pending list"

        # Verify required fields
        assert "created_at" in our_approval
        assert our_approval["case_id"] == approval_id
        assert our_approval["step"] == "APPROVAL:expense.create"
        assert our_approval["requested_by"] == analyst_id
        assert "analyst" in our_approval["requested_by_roles"]

    def test_pending_excludes_decided_approvals(self, tmp_path: Path, ledger_path: Path):
        """After deciding, approval should not appear in pending list."""
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
        assert response.status_code == 202
        approval_id = response.json()["approval_id"]

        # Verify it appears in pending
        response = client.get(
            "/approvals/pending",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": DEFAULT_INSTITUTION_ID,
            },
        )
        assert response.status_code == 200
        pending_ids = [a["approval_id"] for a in response.json()["approvals"]]
        assert approval_id in pending_ids

        # Decide as manager
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )
        assert response.status_code == 200

        # Verify it no longer appears in pending
        response = client.get(
            "/approvals/pending",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": DEFAULT_INSTITUTION_ID,
            },
        )
        assert response.status_code == 200
        pending_ids = [a["approval_id"] for a in response.json()["approvals"]]
        assert approval_id not in pending_ids, "Decided approval should not appear in pending"

    def test_pending_requires_admin_auth(self, tmp_path: Path, ledger_path: Path):
        """GET /approvals/pending should require admin auth."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)

        # Try without admin token
        response = client.get(
            "/approvals/pending",
            headers={
                "X-Institution-Id": DEFAULT_INSTITUTION_ID,
            },
        )

        assert response.status_code == 401

    def test_pending_requires_institution_id(self, tmp_path: Path, ledger_path: Path):
        """GET /approvals/pending should require X-Institution-Id header."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)

        # Try without institution ID
        response = client.get(
            "/approvals/pending",
            headers={
                "X-Admin-Token": "test-admin-token",
            },
        )

        assert response.status_code == 400

    def test_pending_invalid_admin_token_fails(self, tmp_path: Path, ledger_path: Path):
        """GET /approvals/pending with invalid admin token should fail."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)

        response = client.get(
            "/approvals/pending",
            headers={
                "X-Admin-Token": "wrong-token",
                "X-Institution-Id": DEFAULT_INSTITUTION_ID,
            },
        )

        assert response.status_code == 401

    def test_pending_respects_limit(self, tmp_path: Path, ledger_path: Path):
        """GET /approvals/pending should respect limit parameter."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        # Create 5 approval requests
        for i in range(5):
            response = client.post(
                "/finance/expenses",
                headers={
                    "X-Actor-Id": analyst_id,
                    "X-Actor-Roles": "analyst",
                },
                json={"amount": 100 + i},
            )
            assert response.status_code == 202

        # Get with limit=2
        response = client.get(
            "/approvals/pending?limit=2",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": DEFAULT_INSTITUTION_ID,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["approvals"]) == 2
        assert data["total"] == 5  # Total is 5, but only 2 returned

    def test_pending_returns_empty_list_when_none(self, tmp_path: Path, ledger_path: Path):
        """GET /approvals/pending should return empty list when no pending approvals."""
        create_bundle_with_approvals(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)

        response = client.get(
            "/approvals/pending",
            headers={
                "X-Admin-Token": "test-admin-token",
                "X-Institution-Id": DEFAULT_INSTITUTION_ID,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["approvals"] == []
        assert data["total"] == 0
