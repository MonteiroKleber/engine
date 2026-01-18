"""Tests for X-Request-Id header (Fase 4.3)."""

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
from engine.core.state_store import set_state_store
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


def create_bundle(bundle_path: Path) -> None:
    """Create a full bundle with RBAC, approvals, SoD, and invariants."""
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

    # Create SoD rules (empty for these tests)
    sod_hash = create_sod_json(bundle_path, [])

    # Create invariants
    invariants_hash = create_invariants_json(bundle_path, {
        "amount": {"min": 0.01, "max": 1000000000},
        "description": {"max_len": 280, "required": False},
    })

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


class TestRequestIdGenerated:
    """Test that X-Request-Id is generated when not provided."""

    def test_no_header_generates_uuid_and_propagates_to_ledger(self, tmp_path: Path):
        """Request without X-Request-Id should generate UUID and include in ledger events."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        # Make request without X-Request-Id
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "test expense"},
        )

        assert response.status_code == 202

        # Response should have X-Request-Id header with valid UUID
        response_request_id = response.headers.get("X-Request-Id")
        assert response_request_id is not None

        # Validate it's a valid UUID
        parsed_uuid = uuid.UUID(response_request_id)
        assert str(parsed_uuid) == response_request_id

        # Verify ledger events have this request_id
        ledger = get_ledger()
        events = ledger.get_all_events()
        assert len(events) > 0

        for event in events:
            assert event.request_id == response_request_id


class TestRequestIdEchoed:
    """Test that X-Request-Id is echoed when provided."""

    def test_valid_header_echoed_and_propagates_to_ledger(self, tmp_path: Path):
        """Request with valid X-Request-Id should echo it and include in ledger events."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        provided_request_id = str(uuid.uuid4())

        # Make request with X-Request-Id
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
                "X-Request-Id": provided_request_id,
            },
            json={"amount": 100, "description": "test expense"},
        )

        assert response.status_code == 202

        # Response should echo the same X-Request-Id
        response_request_id = response.headers.get("X-Request-Id")
        assert response_request_id == provided_request_id

        # Verify ledger events have this request_id
        ledger = get_ledger()
        events = ledger.get_all_events()
        assert len(events) > 0

        for event in events:
            assert event.request_id == provided_request_id


class TestRequestIdInvalid:
    """Test that invalid X-Request-Id returns 400."""

    def test_invalid_header_returns_400_request_id_invalid(self, tmp_path: Path):
        """Request with invalid X-Request-Id should return 400 and not emit events."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        # Make request with invalid X-Request-Id (not a UUID)
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
                "X-Request-Id": "not-a-valid-uuid",
            },
            json={"amount": 100, "description": "test expense"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "REQUEST_ID_INVALID"
        assert data["message"] == "Invalid X-Request-Id"

        # Verify NO ledger events emitted
        ledger = get_ledger()
        events = ledger.get_all_events()
        assert len(events) == 0

    def test_empty_header_returns_400(self, tmp_path: Path):
        """Request with empty X-Request-Id should return 400."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        # Make request with empty X-Request-Id
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
                "X-Request-Id": "",
            },
            json={"amount": 100, "description": "test expense"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "REQUEST_ID_INVALID"

    def test_partial_uuid_returns_400(self, tmp_path: Path):
        """Request with partial UUID should return 400."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        # Make request with partial UUID
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
                "X-Request-Id": "12345678-1234-1234-1234",  # Missing last section
            },
            json={"amount": 100, "description": "test expense"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "REQUEST_ID_INVALID"
