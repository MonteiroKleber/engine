"""Tests for interdepartmental contracts stub endpoints."""

import json
import os
import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from engine.api.server import app
from engine.loader.load_bundle import (
    _set_bundle_context,
    BundleContext,
    DeptContracts,
)
from engine.core.ledger import init_ledger, get_ledger
from engine.core.rbac import set_rbac_policy, RBACPolicy
from engine.core.contracts import (
    ContractCatalog,
    ContractDef,
    find_contract,
    validate_consumer,
    validate_provider,
    compute_payload_sha256,
)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def ledger_path(tmp_path: Path):
    """Set up temporary ledger path."""
    ledger_file = tmp_path / "ledger" / "audit.jsonl"
    old_env = os.environ.get("ENGINE_LEDGER_PATH")
    os.environ["ENGINE_LEDGER_PATH"] = str(ledger_file)
    yield ledger_file
    if old_env:
        os.environ["ENGINE_LEDGER_PATH"] = old_env
    else:
        os.environ.pop("ENGINE_LEDGER_PATH", None)


@pytest.fixture
def multi_mode_bundle_with_contracts(tmp_path: Path, ledger_path: Path):
    """Create a multi-department bundle with contracts.json."""
    # Create departments
    finance_dept = DeptContracts(
        name="finance",
        path=tmp_path / "departments" / "finance",
    )
    hr_dept = DeptContracts(
        name="hr",
        path=tmp_path / "departments" / "hr",
    )
    ops_dept = DeptContracts(
        name="ops",
        path=tmp_path / "departments" / "ops",
    )

    # Define contracts catalog
    contracts_catalog = {
        "contracts": [
            {
                "contract_id": "Finance.ExpenseApproval",
                "provider_dept": "finance",
                "consumers": ["hr", "ops"],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "approval_required": True,
            },
            {
                "contract_id": "HR.EmployeeVerification",
                "provider_dept": "hr",
                "consumers": ["finance"],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "approval_required": False,
            },
        ]
    }

    ctx = BundleContext(
        mode="multi",
        path=tmp_path,
        manifest={"version": "1.0.0"},
        departments={
            "finance": finance_dept,
            "hr": hr_dept,
            "ops": ops_dept,
        },
        contracts_catalog=contracts_catalog,
    )
    _set_bundle_context(ctx)

    # Initialize ledger
    ledger = init_ledger(ledger_path)
    ledger.set_bundle_hashes("test-manifest-hash", "test-contract-hash")

    yield ctx

    _set_bundle_context(None)


@pytest.fixture
def rbac_policy_allow_all():
    """Set RBAC policy that allows all."""
    policy = RBACPolicy({
        "roles": [
            {
                "name": "admin",
                "permissions": ["contract.invoke", "contract.decide"]
            }
        ]
    })
    set_rbac_policy(policy)
    yield
    set_rbac_policy(None)


class TestContractCatalog:
    """Tests for ContractCatalog class."""

    def test_load_contracts_from_data(self):
        """Should load contracts from catalog data."""
        data = {
            "contracts": [
                {
                    "contract_id": "Test.Contract",
                    "provider_dept": "provider",
                    "consumers": ["consumer1", "consumer2"],
                }
            ]
        }
        catalog = ContractCatalog(data)
        contract = catalog.find_contract("Test.Contract")
        assert contract is not None
        assert contract.provider_dept == "provider"
        assert "consumer1" in contract.consumers

    def test_find_nonexistent_contract(self):
        """Should return None for nonexistent contract."""
        catalog = ContractCatalog({"contracts": []})
        assert catalog.find_contract("NonExistent") is None


class TestContractValidation:
    """Tests for contract validation functions."""

    def test_validate_consumer_authorized(self):
        """Authorized consumer should pass validation."""
        contract = ContractDef(
            contract_id="Test",
            provider_dept="provider",
            consumers=["consumer1", "consumer2"],
        )
        assert validate_consumer(contract, "consumer1") is True
        assert validate_consumer(contract, "consumer2") is True

    def test_validate_consumer_unauthorized(self):
        """Unauthorized consumer should fail validation."""
        contract = ContractDef(
            contract_id="Test",
            provider_dept="provider",
            consumers=["consumer1"],
        )
        assert validate_consumer(contract, "unauthorized") is False

    def test_validate_provider_correct(self):
        """Correct provider should pass validation."""
        contract = ContractDef(
            contract_id="Test",
            provider_dept="provider",
            consumers=[],
        )
        assert validate_provider(contract, "provider") is True

    def test_validate_provider_incorrect(self):
        """Incorrect provider should fail validation."""
        contract = ContractDef(
            contract_id="Test",
            provider_dept="provider",
            consumers=[],
        )
        assert validate_provider(contract, "wrong") is False


class TestComputePayloadSha256:
    """Tests for payload hashing."""

    def test_hash_is_deterministic(self):
        """Same payload should produce same hash."""
        payload = {"key": "value", "number": 42}
        hash1 = compute_payload_sha256(payload)
        hash2 = compute_payload_sha256(payload)
        assert hash1 == hash2
        assert hash1.startswith("SHA256:")

    def test_different_payloads_different_hashes(self):
        """Different payloads should produce different hashes."""
        hash1 = compute_payload_sha256({"a": 1})
        hash2 = compute_payload_sha256({"a": 2})
        assert hash1 != hash2


class TestInvokeEndpoint:
    """Tests for POST /d/{consumer}/contracts/{contract_id}/invoke."""

    def test_invoke_by_authorized_consumer(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all, ledger_path
    ):
        """Authorized consumer can invoke contract, returns 202."""
        response = client.post(
            "/d/hr/contracts/Finance.ExpenseApproval/invoke",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"payload": {"expense_amount": 1000}},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"
        assert data["contract_id"] == "Finance.ExpenseApproval"
        assert data["provider_dept"] == "finance"
        assert data["consumer_dept"] == "hr"
        assert "case_id" in data
        assert data["payload_sha256"].startswith("SHA256:")

        # Verify CONTRACT_INVOKED event in ledger
        assert ledger_path.exists()
        with open(ledger_path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        invoke_events = [e for e in events if e["event_type"] == "CONTRACT_INVOKED"]
        assert len(invoke_events) == 1
        event = invoke_events[0]
        assert event["step"] == "CONTRACT:Finance.ExpenseApproval"
        assert event["payload"]["origin_dept"] == "hr"
        assert event["payload"]["target_dept"] == "finance"
        assert event["payload"]["status"] == "pending"

    def test_invoke_by_unauthorized_consumer(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all
    ):
        """Unauthorized consumer gets 403 CONTRACT_CONSUMER_FORBIDDEN."""
        # finance is not in consumers list for Finance.ExpenseApproval
        response = client.post(
            "/d/finance/contracts/Finance.ExpenseApproval/invoke",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"payload": {}},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "CONTRACT_CONSUMER_FORBIDDEN"

    def test_invoke_contract_not_found(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all
    ):
        """Nonexistent contract returns 404 CONTRACT_NOT_FOUND."""
        response = client.post(
            "/d/hr/contracts/NonExistent.Contract/invoke",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"payload": {}},
        )
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "CONTRACT_NOT_FOUND"

    def test_invoke_with_custom_case_id(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all
    ):
        """Custom case_id is preserved in response."""
        custom_case_id = "my-custom-case-123"
        response = client.post(
            "/d/hr/contracts/Finance.ExpenseApproval/invoke",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"case_id": custom_case_id, "payload": {}},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["case_id"] == custom_case_id


class TestDecideEndpoint:
    """Tests for POST /d/{provider}/contracts/{contract_id}/decide."""

    def test_decide_by_correct_provider(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all, ledger_path
    ):
        """Correct provider can decide, returns 200."""
        case_id = "test-case-for-decide"

        # First invoke
        client.post(
            "/d/hr/contracts/Finance.ExpenseApproval/invoke",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"case_id": case_id, "payload": {"amount": 500}},
        )

        # Then decide
        response = client.post(
            "/d/finance/contracts/Finance.ExpenseApproval/decide",
            headers={
                "X-Actor-Id": "660e8400-e29b-41d4-a716-446655440001",
                "X-Actor-Roles": "admin",
            },
            json={
                "case_id": case_id,
                "decision": "allow",
                "reason": "Budget approved",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "decided"
        assert data["case_id"] == case_id
        assert data["decision"] == "allow"

        # Verify CONTRACT_DECIDED event in ledger
        with open(ledger_path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        decide_events = [e for e in events if e["event_type"] == "CONTRACT_DECIDED"]
        assert len(decide_events) == 1
        event = decide_events[0]
        assert event["step"] == "CONTRACT:Finance.ExpenseApproval"
        assert event["payload"]["decision"] == "allow"
        assert event["payload"]["origin_dept"] == "hr"
        assert event["payload"]["target_dept"] == "finance"
        assert event["payload"]["reason"] == "Budget approved"

    def test_decide_provider_mismatch(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all
    ):
        """Wrong provider gets 409 CONTRACT_PROVIDER_MISMATCH."""
        # hr is not the provider of Finance.ExpenseApproval
        response = client.post(
            "/d/hr/contracts/Finance.ExpenseApproval/decide",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={
                "case_id": "some-case",
                "decision": "allow",
            },
        )
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "CONTRACT_PROVIDER_MISMATCH"

    def test_decide_invalid_decision(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all
    ):
        """Invalid decision gets 400 CONTRACT_DECISION_INVALID."""
        response = client.post(
            "/d/finance/contracts/Finance.ExpenseApproval/decide",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={
                "case_id": "some-case",
                "decision": "maybe",  # Invalid!
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "CONTRACT_DECISION_INVALID"

    def test_decide_missing_case_id(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all
    ):
        """Missing case_id gets 400 CONTRACT_CASE_ID_REQUIRED or validation error."""
        response = client.post(
            "/d/finance/contracts/Finance.ExpenseApproval/decide",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={
                "decision": "allow",
                # case_id missing
            },
        )
        # Pydantic will catch this first as validation error (422)
        assert response.status_code == 422

    def test_decide_contract_not_found(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all
    ):
        """Nonexistent contract returns 404 CONTRACT_NOT_FOUND."""
        response = client.post(
            "/d/finance/contracts/NonExistent.Contract/decide",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={
                "case_id": "some-case",
                "decision": "allow",
            },
        )
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "CONTRACT_NOT_FOUND"

    def test_decide_deny(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all, ledger_path
    ):
        """Decision 'deny' is valid and recorded."""
        case_id = "deny-test-case"

        # Invoke first
        client.post(
            "/d/ops/contracts/Finance.ExpenseApproval/invoke",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"case_id": case_id, "payload": {}},
        )

        # Decide deny
        response = client.post(
            "/d/finance/contracts/Finance.ExpenseApproval/decide",
            headers={
                "X-Actor-Id": "660e8400-e29b-41d4-a716-446655440001",
                "X-Actor-Roles": "admin",
            },
            json={
                "case_id": case_id,
                "decision": "deny",
                "reason": "Budget exceeded",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "deny"

        # Verify in ledger
        with open(ledger_path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        decide_events = [
            e for e in events
            if e["event_type"] == "CONTRACT_DECIDED" and e["case_id"] == case_id
        ]
        assert len(decide_events) == 1
        assert decide_events[0]["payload"]["decision"] == "deny"

    def test_decide_without_prior_invoke(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all, ledger_path
    ):
        """Decide without prior invoke still works, origin_dept is null."""
        case_id = "orphan-decide-case"

        response = client.post(
            "/d/finance/contracts/Finance.ExpenseApproval/decide",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={
                "case_id": case_id,
                "decision": "allow",
            },
        )
        assert response.status_code == 200

        # Verify in ledger - origin_dept should be null
        with open(ledger_path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        decide_events = [
            e for e in events
            if e["event_type"] == "CONTRACT_DECIDED" and e["case_id"] == case_id
        ]
        assert len(decide_events) == 1
        assert decide_events[0]["payload"]["origin_dept"] is None


class TestLedgerEvents:
    """Tests for ledger event structure."""

    def test_invoke_event_has_required_fields(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all, ledger_path
    ):
        """CONTRACT_INVOKED event has all required fields."""
        response = client.post(
            "/d/hr/contracts/Finance.ExpenseApproval/invoke",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"payload": {"test": "data"}},
        )
        assert response.status_code == 202
        case_id = response.json()["case_id"]

        with open(ledger_path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        invoke_event = next(
            e for e in events
            if e["event_type"] == "CONTRACT_INVOKED" and e["case_id"] == case_id
        )

        # Check required fields
        assert "hash" in invoke_event
        assert "prev_hash" in invoke_event
        assert "seq" in invoke_event
        assert "timestamp" in invoke_event
        assert invoke_event["step"] == "CONTRACT:Finance.ExpenseApproval"

        payload = invoke_event["payload"]
        assert payload["contract_id"] == "Finance.ExpenseApproval"
        assert payload["origin_dept"] == "hr"
        assert payload["target_dept"] == "finance"
        assert payload["request_payload_present"] is True
        assert payload["dependency_id"] is None
        assert payload["status"] == "pending"
        assert payload["payload_sha256"].startswith("SHA256:")

    def test_decide_event_has_decider_actor_id(
        self, client, multi_mode_bundle_with_contracts, rbac_policy_allow_all, ledger_path
    ):
        """CONTRACT_DECIDED event includes decider_actor_id."""
        case_id = "decider-test"
        decider_id = "660e8400-e29b-41d4-a716-446655440001"

        # Invoke
        client.post(
            "/d/hr/contracts/Finance.ExpenseApproval/invoke",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"case_id": case_id, "payload": {}},
        )

        # Decide
        client.post(
            "/d/finance/contracts/Finance.ExpenseApproval/decide",
            headers={
                "X-Actor-Id": decider_id,
                "X-Actor-Roles": "admin",
            },
            json={
                "case_id": case_id,
                "decision": "allow",
            },
        )

        with open(ledger_path, "r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        decide_event = next(
            e for e in events
            if e["event_type"] == "CONTRACT_DECIDED" and e["case_id"] == case_id
        )
        assert decide_event["payload"]["decider_actor_id"] == decider_id
