"""Tests for Etapa 04 - Runtime Gates (Canonical Semantics).

These tests verify the canonical deny-by-default behavior for mandates and autonomy:

1. Mandate canonical semantics:
   - mandates.json absent → allow (no contract = allow)
   - mandates.json exists, mandate matches → evaluate mandate rules
   - mandates.json exists, no mandate matches → DENY (MANDATE_DENIED)

2. Autonomy canonical semantics:
   - autonomy.json absent → allow (no contract = allow)
   - autonomy.json exists, rule matches → evaluate autonomy level
   - autonomy.json exists, no rule matches → DENY (AUTONOMY_INSUFFICIENT)

3. End-to-end Finance flow with minimal valid contracts
4. Ledger event verification for allow/deny decisions
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.actor_context import ActorContext
from engine.core.errors import (
    MANDATE_DENIED,
    MANDATE_ROLE_MISMATCH,
    AUTONOMY_INSUFFICIENT,
)
from engine.core.mandates import (
    evaluate_mandates,
    set_mandates,
    get_mandates,
    clear_all_mandates,
    MandateDef,
    Mandate,
    MandateLimit,
)
from engine.core.autonomy import (
    evaluate_autonomy,
    set_autonomy_for_dept,
    get_autonomy_for_dept,
    reset_all_autonomy,
    AutonomyDef,
    AutonomyRule,
)
from engine.core.ledger import init_ledger, set_ledger, get_ledger
from engine.loader.load_bundle import load_bundle
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


@pytest.fixture(autouse=True)
def reset_state():
    """Reset runtime state before each test."""
    runtime_state.set_active()
    clear_all_mandates()
    reset_all_autonomy()
    set_ledger(None)
    yield
    runtime_state.set_active()
    clear_all_mandates()
    reset_all_autonomy()
    set_ledger(None)


class TestMandateCanonicalSemantics:
    """Test mandate canonical deny-by-default semantics.

    Per spec: "Nenhuma execução fora de mandato" - if mandates.json exists
    but no mandate is applicable to (endpoint_sig, phase) → deny (MANDATE_DENIED).
    """

    @pytest.fixture
    def actor(self):
        """Create test actor."""
        return ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

    def test_no_mandates_json_allows(self, actor):
        """No mandates.json loaded → allow (no contract = allow)."""
        # No mandates set (simulating no mandates.json file)
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={"amount": 100},
        )
        assert result.allow is True
        assert result.mandate_id is None

    def test_mandates_json_exists_no_match_denies(self, actor):
        """mandates.json exists, no mandate matches → DENY."""
        # Set mandates for a different endpoint/phase
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="other-mandate",
                    endpoint_sig="POST /approvals/{approval_id}/decide",  # Different endpoint
                    phase="post",
                    allowed_roles=["manager"],
                )
            ]
        )
        set_mandates(None, mandate_def)

        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={"amount": 100},
        )
        assert result.allow is False
        assert result.mandate_id is None
        assert len(result.violations) == 1
        assert result.violations[0].code == MANDATE_DENIED
        assert "No mandate applicable" in result.violations[0].message

    def test_mandates_json_exists_empty_list_denies(self, actor):
        """mandates.json exists with empty mandates list → DENY."""
        # Set empty mandates (simulating mandates.json with "mandates": [])
        mandate_def = MandateDef(mandates=[])
        set_mandates(None, mandate_def)

        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={"amount": 100},
        )
        assert result.allow is False
        assert len(result.violations) == 1
        assert result.violations[0].code == MANDATE_DENIED

    def test_mandates_json_exists_match_allows(self, actor):
        """mandates.json exists, mandate matches → evaluate and allow."""
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="expense-mandate",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    limits=[
                        MandateLimit(
                            rule_type="numeric_max",
                            field_path="amount",
                            field_path_tokens=["amount"],
                            value=1000,
                        )
                    ],
                )
            ]
        )
        set_mandates(None, mandate_def)

        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={"amount": 500},
        )
        assert result.allow is True
        assert result.mandate_id == "expense-mandate"

    def test_mandates_json_exists_match_wrong_phase_denies(self, actor):
        """mandates.json exists, mandate exists for endpoint but wrong phase → DENY."""
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="expense-mandate",
                    endpoint_sig="POST /finance/expenses",
                    phase="post",  # Only covers post phase
                    allowed_roles=["employee"],
                )
            ]
        )
        set_mandates(None, mandate_def)

        result = evaluate_mandates(
            phase="pre",  # Requesting pre phase - no mandate
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={"amount": 100},
        )
        assert result.allow is False
        assert result.violations[0].code == MANDATE_DENIED

    def test_mandates_json_both_phases_covered(self, actor):
        """mandates.json covers both pre and post phases → allow both."""
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="expense-pre",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                ),
                Mandate(
                    mandate_id="expense-post",
                    endpoint_sig="POST /finance/expenses",
                    phase="post",
                    allowed_roles=["employee"],
                ),
            ]
        )
        set_mandates(None, mandate_def)

        # Pre phase
        result_pre = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={},
        )
        assert result_pre.allow is True
        assert result_pre.mandate_id == "expense-pre"

        # Post phase
        result_post = evaluate_mandates(
            phase="post",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={},
        )
        assert result_post.allow is True
        assert result_post.mandate_id == "expense-post"


class TestAutonomyCanonicalSemantics:
    """Test autonomy canonical deny-by-default semantics.

    Per spec: If autonomy.json exists but no rule is applicable to
    (endpoint_sig, phase) → deny (AUTONOMY_INSUFFICIENT).
    """

    def test_no_autonomy_json_allows(self):
        """No autonomy.json loaded → allow (no contract = allow)."""
        # No autonomy set (simulating no autonomy.json file)
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result.decision == "allow"
        assert result.rule_id is None

    def test_autonomy_json_exists_no_match_denies(self):
        """autonomy.json exists, no rule matches → DENY."""
        # Set autonomy for a different endpoint/phase
        autonomy_def = AutonomyDef(
            current_level=3,
            rules=[
                AutonomyRule(
                    rule_id="other-rule",
                    endpoint_sig="POST /approvals/{approval_id}/decide",  # Different endpoint
                    phase="post",
                    required_level=2,
                )
            ],
        )
        set_autonomy_for_dept(None, autonomy_def)

        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result.decision == "deny"
        assert result.rule_id is None
        assert "No autonomy rule applicable" in result.reason

    def test_autonomy_json_exists_empty_rules_denies(self):
        """autonomy.json exists with empty rules → DENY."""
        # Set autonomy with no rules (simulating autonomy.json with "rules": [])
        autonomy_def = AutonomyDef(current_level=3, rules=[])
        set_autonomy_for_dept(None, autonomy_def)

        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result.decision == "deny"
        assert "No autonomy rule applicable" in result.reason

    def test_autonomy_json_exists_match_allows(self):
        """autonomy.json exists, rule matches, level sufficient → allow."""
        autonomy_def = AutonomyDef(
            current_level=3,
            rules=[
                AutonomyRule(
                    rule_id="expense-rule",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=2,
                )
            ],
        )
        set_autonomy_for_dept(None, autonomy_def)

        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result.decision == "allow"
        assert result.rule_id == "expense-rule"

    def test_autonomy_json_exists_match_wrong_phase_denies(self):
        """autonomy.json exists, rule exists for endpoint but wrong phase → DENY."""
        autonomy_def = AutonomyDef(
            current_level=3,
            rules=[
                AutonomyRule(
                    rule_id="expense-rule",
                    endpoint_sig="POST /finance/expenses",
                    phase="post",  # Only covers post phase
                    required_level=2,
                )
            ],
        )
        set_autonomy_for_dept(None, autonomy_def)

        result = evaluate_autonomy(
            phase="pre",  # Requesting pre phase - no rule
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result.decision == "deny"
        assert "No autonomy rule applicable" in result.reason

    def test_autonomy_json_both_phases_covered(self):
        """autonomy.json covers both pre and post phases → allow both."""
        autonomy_def = AutonomyDef(
            current_level=3,
            rules=[
                AutonomyRule(
                    rule_id="expense-pre",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=2,
                ),
                AutonomyRule(
                    rule_id="expense-post",
                    endpoint_sig="POST /finance/expenses",
                    phase="post",
                    required_level=2,
                ),
            ],
        )
        set_autonomy_for_dept(None, autonomy_def)

        # Pre phase
        result_pre = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result_pre.decision == "allow"
        assert result_pre.rule_id == "expense-pre"

        # Post phase
        result_post = evaluate_autonomy(
            phase="post",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result_post.decision == "allow"
        assert result_post.rule_id == "expense-post"


class TestFinanceEndToEndWithCanonicalSemantics:
    """End-to-end Finance flow tests with canonical mandate/autonomy semantics."""

    def _create_complete_bundle(
        self, tmp_path, mandates_data=None, autonomy_data=None, policies_data=None
    ):
        """Create a complete bundle with all required contracts."""
        # RBAC
        rbac_data = {
            "version": "1.0.0",
            "name": "rbac",
            "roles": [
                {"name": "employee", "permissions": ["expense.create"]},
                {"name": "manager", "permissions": ["expense.create", "approval.decide"]},
            ],
        }
        rbac_path = tmp_path / "rbac.json"
        with open(rbac_path, "w", encoding="utf-8") as f:
            json.dump(rbac_data, f)
        rbac_hash = compute_sha256(rbac_path)

        # Approvals
        approvals_data = {
            "version": "1.0",
            "rules": [
                {
                    "rule_id": "manager-approval",
                    "condition": {"field": "amount", "op": "gt", "value": 500},
                    "approvers": ["manager"],
                }
            ],
        }
        approvals_path = tmp_path / "approvals.json"
        with open(approvals_path, "w", encoding="utf-8") as f:
            json.dump(approvals_data, f)
        approvals_hash = compute_sha256(approvals_path)

        # Mandates (optional)
        if mandates_data:
            mandates_path = tmp_path / "mandates.json"
            with open(mandates_path, "w", encoding="utf-8") as f:
                json.dump(mandates_data, f)
            mandates_hash = compute_sha256(mandates_path)

        # Autonomy (optional)
        if autonomy_data:
            autonomy_path = tmp_path / "autonomy.json"
            with open(autonomy_path, "w", encoding="utf-8") as f:
                json.dump(autonomy_data, f)
            autonomy_hash = compute_sha256(autonomy_path)

        # Policies (optional)
        if policies_data:
            policies_path = tmp_path / "policies.json"
            with open(policies_path, "w", encoding="utf-8") as f:
                json.dump(policies_data, f)
            policies_hash = compute_sha256(policies_path)

        # Manifest
        contracts = [
            {"file": "rbac.json", "sha256": f"SHA256:{rbac_hash}", "required": True},
            {"file": "approvals.json", "sha256": f"SHA256:{approvals_hash}", "required": True},
        ]
        if mandates_data:
            contracts.append(
                {"file": "mandates.json", "sha256": f"SHA256:{mandates_hash}", "required": True}
            )
        if autonomy_data:
            contracts.append(
                {"file": "autonomy.json", "sha256": f"SHA256:{autonomy_hash}", "required": True}
            )
        if policies_data:
            contracts.append(
                {"file": "policies.json", "sha256": f"SHA256:{policies_hash}", "required": True}
            )

        manifest = {
            "name": "test-bundle",
            "version": "1.0.0",
            "contracts": contracts,
        }
        manifest_path = tmp_path / "bundle.manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f)

    def test_finance_no_mandates_no_autonomy_allows(self, tmp_path, monkeypatch):
        """Without mandates/autonomy contracts, operations are allowed."""
        self._create_complete_bundle(tmp_path)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))

        load_bundle(tmp_path)

        client = TestClient(app, raise_server_exceptions=False)
        actor_id = str(uuid.uuid4())
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "employee",
            },
            json={"amount": 100, "description": "Office supplies"},
        )

        # Should succeed
        assert response.status_code in (200, 202), f"Got {response.status_code}: {response.json()}"

    def test_finance_empty_mandates_denies(self, tmp_path, monkeypatch):
        """With empty mandates.json, POST /finance/expenses is denied."""
        mandates_data = {
            "mandate_schema_version": "1.0",
            "mandates": [],  # Empty - no mandate covers the endpoint
        }
        self._create_complete_bundle(tmp_path, mandates_data=mandates_data)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))

        load_bundle(tmp_path)

        client = TestClient(app, raise_server_exceptions=False)
        actor_id = str(uuid.uuid4())
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "employee",
            },
            json={"amount": 100, "description": "Office supplies"},
        )

        assert response.status_code == 403, f"Got {response.status_code}: {response.json()}"
        data = response.json()
        assert data["code"] == MANDATE_DENIED
        # Violation details may be in message or violations array
        violations_str = str(data.get("violations", []))
        assert "No mandate applicable" in violations_str or "No mandate applicable" in data.get("message", "")

    def test_finance_empty_autonomy_denies(self, tmp_path, monkeypatch):
        """With empty autonomy.json, POST /finance/expenses is denied."""
        autonomy_data = {
            "autonomy_schema_version": "1.0",
            "current_level": 3,
            "rules": [],  # Empty - no rule covers the endpoint
        }
        self._create_complete_bundle(tmp_path, autonomy_data=autonomy_data)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))

        load_bundle(tmp_path)

        client = TestClient(app, raise_server_exceptions=False)
        actor_id = str(uuid.uuid4())
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "employee",
            },
            json={"amount": 100, "description": "Office supplies"},
        )

        assert response.status_code == 403, f"Got {response.status_code}: {response.json()}"
        data = response.json()
        assert data["code"] == AUTONOMY_INSUFFICIENT

    def test_finance_with_valid_mandate_and_autonomy_allows(self, tmp_path, monkeypatch):
        """With valid mandate and autonomy covering the endpoint, operation succeeds."""
        mandates_data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "expense-mandate",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["employee", "manager"],
                    "limits": [
                        {
                            "rule_type": "numeric_max",
                            "field_path": "amount",
                            "value": 10000,
                        }
                    ],
                }
            ],
        }
        autonomy_data = {
            "autonomy_schema_version": "1.0",
            "current_level": 3,
            "rules": [
                {
                    "rule_id": "expense-autonomy",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 2,
                }
            ],
        }
        self._create_complete_bundle(
            tmp_path, mandates_data=mandates_data, autonomy_data=autonomy_data
        )

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))

        load_bundle(tmp_path)

        client = TestClient(app, raise_server_exceptions=False)
        actor_id = str(uuid.uuid4())
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "employee",
            },
            json={"amount": 500, "description": "Valid expense within limits"},
        )

        assert response.status_code in (200, 202), f"Got {response.status_code}: {response.json()}"


class TestLedgerEventsForGates:
    """Test that ledger events are correctly emitted for allow/deny decisions."""

    def test_mandate_deny_emits_ledger_event(self, tmp_path):
        """MANDATE_EVALUATED event emitted on deny."""
        ledger = init_ledger(tmp_path / "ledger.jsonl")
        ledger.set_bundle_hashes("abc123", "def456")

        from engine.core.mandates import emit_mandate_decision, MandateEvalResult, MandateViolation

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

        # Set up empty mandates to trigger deny
        mandate_def = MandateDef(mandates=[])
        set_mandates(None, mandate_def)

        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={},
        )

        emit_mandate_decision(
            phase="pre",
            endpoint_sig="POST /finance/expenses",
            dept_id=None,
            case_id="expense-123",
            actor=actor,
            result=result,
        )

        events = ledger.get_all_events()
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "MANDATE_EVALUATED"
        assert event.payload["allow"] is False
        assert len(event.payload["violations"]) == 1
        assert event.payload["violations"][0]["code"] == MANDATE_DENIED

    def test_autonomy_deny_emits_ledger_event(self, tmp_path):
        """AUTONOMY_EVALUATED event emitted on deny."""
        ledger = init_ledger(tmp_path / "ledger.jsonl")
        ledger.set_bundle_hashes("abc123", "def456")

        from engine.core.autonomy import emit_autonomy_evaluated

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

        # Set up empty autonomy to trigger deny
        autonomy_def = AutonomyDef(current_level=3, rules=[])
        set_autonomy_for_dept(None, autonomy_def)

        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )

        emit_autonomy_evaluated(
            tenant_id=actor.tenant_id,
            actor=actor,
            dept_id=None,
            phase="pre",
            endpoint_sig="POST /finance/expenses",
            case_id="expense-123",
            result=result,
        )

        events = ledger.get_all_events()
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "AUTONOMY_EVALUATED"
        assert event.payload["decision"] == "deny"
        assert "No autonomy rule applicable" in event.payload["reason"]

    def test_mandate_allow_emits_ledger_event(self, tmp_path):
        """MANDATE_EVALUATED event emitted on allow."""
        ledger = init_ledger(tmp_path / "ledger.jsonl")
        ledger.set_bundle_hashes("abc123", "def456")

        from engine.core.mandates import emit_mandate_decision

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

        # Set up mandate that matches
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="expense-mandate",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                )
            ]
        )
        set_mandates(None, mandate_def)

        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={},
        )

        emit_mandate_decision(
            phase="pre",
            endpoint_sig="POST /finance/expenses",
            dept_id=None,
            case_id="expense-123",
            actor=actor,
            result=result,
        )

        events = ledger.get_all_events()
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "MANDATE_EVALUATED"
        assert event.payload["allow"] is True
        assert event.payload["mandate_id"] == "expense-mandate"

    def test_autonomy_allow_emits_ledger_event(self, tmp_path):
        """AUTONOMY_EVALUATED event emitted on allow."""
        ledger = init_ledger(tmp_path / "ledger.jsonl")
        ledger.set_bundle_hashes("abc123", "def456")

        from engine.core.autonomy import emit_autonomy_evaluated

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

        # Set up autonomy with rule that matches
        autonomy_def = AutonomyDef(
            current_level=3,
            rules=[
                AutonomyRule(
                    rule_id="expense-rule",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=2,
                )
            ],
        )
        set_autonomy_for_dept(None, autonomy_def)

        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )

        emit_autonomy_evaluated(
            tenant_id=actor.tenant_id,
            actor=actor,
            dept_id=None,
            phase="pre",
            endpoint_sig="POST /finance/expenses",
            case_id="expense-123",
            result=result,
        )

        events = ledger.get_all_events()
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "AUTONOMY_EVALUATED"
        assert event.payload["decision"] == "allow"
        assert event.payload["rule_id"] == "expense-rule"


class TestDefaultBundleFinancePilotEndToEnd:
    """Test the default bundle (finance-pilot) with canonical mandate/autonomy semantics.

    These tests verify that the finance-pilot bundle:
    1. Loads as ACTIVE (not SAFE_MODE)
    2. POST /finance/expenses works with permitted roles (analyst, admin)
    3. POST /approvals/{approval_id}/decide works with permitted roles (manager, admin)
    4. Mandate role restrictions are enforced
    """

    @pytest.fixture
    def finance_pilot_bundle(self, tmp_path, monkeypatch):
        """Set up environment to use the real finance-pilot bundle."""
        import shutil
        from pathlib import Path

        # Copy finance-pilot bundle to tmp_path to avoid modifying original
        bundle_src = Path("/home/bazari/engine/bundles/finance-pilot")
        bundle_dst = tmp_path / "finance-pilot"
        shutil.copytree(bundle_src, bundle_dst)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_dst))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))

        return bundle_dst

    def test_finance_pilot_bundle_loads_active(self, finance_pilot_bundle):
        """Finance-pilot bundle should load as ACTIVE, not SAFE_MODE."""
        result = load_bundle(finance_pilot_bundle)

        assert result is not None, "Bundle should load successfully"
        assert runtime_state.is_active(), f"Should be ACTIVE, got SAFE_MODE: {runtime_state.reason_code}"

    def test_finance_pilot_create_expense_analyst(self, finance_pilot_bundle):
        """Analyst role can create expense via POST /finance/expenses."""
        load_bundle(finance_pilot_bundle)

        client = TestClient(app, raise_server_exceptions=False)
        actor_id = str(uuid.uuid4())
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "Office supplies"},
        )

        # Should succeed with 202 (approval requested) since approvals.json requires manager approval
        assert response.status_code == 202, f"Got {response.status_code}: {response.json()}"
        data = response.json()
        assert "approval_id" in data or "expense_id" in data

    def test_finance_pilot_create_expense_admin(self, finance_pilot_bundle):
        """Admin role can create expense via POST /finance/expenses."""
        load_bundle(finance_pilot_bundle)

        client = TestClient(app, raise_server_exceptions=False)
        actor_id = str(uuid.uuid4())
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "admin",
            },
            json={"amount": 500, "description": "Equipment purchase"},
        )

        # Should succeed with 202 (approval requested)
        assert response.status_code == 202, f"Got {response.status_code}: {response.json()}"

    def test_finance_pilot_create_expense_viewer_denied(self, finance_pilot_bundle):
        """Viewer role cannot create expense - mandate role mismatch."""
        load_bundle(finance_pilot_bundle)

        client = TestClient(app, raise_server_exceptions=False)
        actor_id = str(uuid.uuid4())
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "viewer",
            },
            json={"amount": 100, "description": "Test"},
        )

        # Should be denied - viewer not in mandate allowed_roles
        # Could be 403 from RBAC (no expense.create) or mandate
        assert response.status_code == 403, f"Got {response.status_code}: {response.json()}"

    def test_finance_pilot_create_expense_amount_limit(self, finance_pilot_bundle):
        """Expense amount exceeding mandate limit is denied."""
        load_bundle(finance_pilot_bundle)

        client = TestClient(app, raise_server_exceptions=False)
        actor_id = str(uuid.uuid4())
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 200000, "description": "Over limit"},  # Exceeds 100000 limit
        )

        # Should be denied by mandate limit
        assert response.status_code == 403, f"Got {response.status_code}: {response.json()}"
        data = response.json()
        assert data["code"] == MANDATE_DENIED

    def test_finance_pilot_approve_expense_manager(self, finance_pilot_bundle):
        """Manager role can approve expense via POST /approvals/{id}/decide."""
        load_bundle(finance_pilot_bundle)

        client = TestClient(app, raise_server_exceptions=False)

        # First create an expense that needs approval
        analyst_id = str(uuid.uuid4())
        create_response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 1000, "description": "Needs approval"},
        )
        assert create_response.status_code == 202, f"Create failed: {create_response.json()}"
        approval_id = create_response.json().get("approval_id")
        assert approval_id is not None, "Expected approval_id in response"

        # Now approve with manager
        manager_id = str(uuid.uuid4())
        approve_response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        assert approve_response.status_code == 200, f"Got {approve_response.status_code}: {approve_response.json()}"
        data = approve_response.json()
        # Response has case_status field with the approval outcome
        case_status = data.get("case_status", data.get("status", ""))
        assert case_status.upper() in ("COMMITTED",), f"Expected COMMITTED, got: {case_status}"

    def test_finance_pilot_reject_expense_manager(self, finance_pilot_bundle):
        """Manager role can reject expense via POST /approvals/{id}/decide."""
        load_bundle(finance_pilot_bundle)

        client = TestClient(app, raise_server_exceptions=False)

        # First create an expense that needs approval
        analyst_id = str(uuid.uuid4())
        create_response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 500, "description": "To be rejected"},
        )
        assert create_response.status_code == 202, f"Create failed: {create_response.json()}"
        approval_id = create_response.json().get("approval_id")

        # Now reject with manager
        manager_id = str(uuid.uuid4())
        reject_response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "reject"},
        )

        assert reject_response.status_code == 200, f"Got {reject_response.status_code}: {reject_response.json()}"
        data = reject_response.json()
        # Response has case_status field with the approval outcome
        case_status = data.get("case_status", data.get("status", ""))
        assert case_status.upper() in ("REJECTED",), f"Expected REJECTED, got: {case_status}"
