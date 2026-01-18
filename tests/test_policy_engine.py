"""Tests for Policy Engine MVP."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy, RBACPolicy
from engine.core.approvals import set_approvals_policy, ApprovalsPolicy
from engine.core.ledger import set_ledger, init_ledger, get_ledger
from engine.core.policy import (
    PolicyRule,
    PolicyDef,
    PolicyViolation,
    PolicyEvalResult,
    PolicySchemaError,
    set_policies,
    get_policies,
    clear_all_policies,
    evaluate_policies,
    load_policies_from_file,
    parse_policies_data,
    validate_endpoint_sig,
    validate_field_path,
    ALLOWED_ENDPOINT_SIGS,
)
from engine.core.errors import POLICY_ENDPOINT_UNKNOWN, POLICY_PATH_INVALID
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
    clear_all_policies()

    # Set ledger path env
    monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

    yield

    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_ledger(None)
    clear_all_policies()


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


def create_policies_json(bundle_path: Path, policies: list) -> str:
    """Create policies.json and return its SHA-256 hash."""
    policies_data = {
        "version": "1.0.0",
        "policies": policies,
    }
    policies_path = bundle_path / "policies.json"
    with open(policies_path, "w", encoding="utf-8") as f:
        json.dump(policies_data, f)
    return compute_sha256(policies_path)


def create_bundle_with_policies(
    bundle_path: Path,
    policies: list = None,
    approvals_rules: list = None,
) -> None:
    """Create a bundle with RBAC, approvals, and policies config."""
    # Create RBAC with analyst (expense.create) and manager (approver)
    rbac_hash = create_rbac_json(bundle_path, [
        {"name": "analyst", "permissions": ["expense.create", "expense.read"]},
        {"name": "manager", "permissions": ["expense.create", "expense.read", "expense.approve"]},
    ])

    # Create approvals rule (default if not specified)
    if approvals_rules is None:
        approvals_rules = [
            {
                "rule_name": "expense.create",
                "trigger": {"api": "POST /finance/expenses"},
                "approver_roles": ["manager"],
                "quorum": 1,
            }
        ]
    approvals_hash = create_approvals_json(bundle_path, approvals_rules)

    # Create policies
    contracts = [
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
    ]

    if policies is not None:
        policies_hash = create_policies_json(bundle_path, policies)
        contracts.append({
            "file": "policies.json",
            "sha256": f"SHA256:{policies_hash}",
            "required": False,  # policies.json is optional
        })

    # Create manifest
    manifest = {
        "name": "test-bundle",
        "version": "1.0.0",
        "contracts": contracts,
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


class TestPolicyRuleUnit:
    """Unit tests for PolicyRule evaluation."""

    def test_numeric_max_allows_under_threshold(self):
        """numeric_max should allow values under threshold."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="max-100",
                rule_type="numeric_max",
                field_path="amount",
                field_path_tokens=["amount"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=100,
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 50},
        )

        assert result.allow is True
        assert len(result.violations) == 0

    def test_numeric_max_denies_over_threshold(self):
        """numeric_max should deny values over threshold."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="max-100",
                rule_type="numeric_max",
                field_path="amount",
                field_path_tokens=["amount"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=100,
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 150},
        )

        assert result.allow is False
        assert len(result.violations) == 1
        assert result.violations[0].policy_id == "max-100"
        assert result.violations[0].actual_value == 150
        assert result.violations[0].threshold_value == 100

    def test_numeric_min_denies_under_threshold(self):
        """numeric_min should deny values under threshold."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="min-10",
                rule_type="numeric_min",
                field_path="amount",
                field_path_tokens=["amount"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=10,
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 5},
        )

        assert result.allow is False
        assert result.violations[0].policy_id == "min-10"

    def test_string_max_len_denies_long_strings(self):
        """string_max_len should deny strings over limit."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="desc-max-10",
                rule_type="string_max_len",
                field_path="description",
                field_path_tokens=["description"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=10,
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"description": "This is a very long description"},
        )

        assert result.allow is False

    def test_required_field_denies_missing(self):
        """required_field should deny when field is missing."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="require-amount",
                rule_type="required_field",
                field_path="amount",
                field_path_tokens=["amount"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"description": "Test"},
        )

        assert result.allow is False
        assert result.violations[0].policy_id == "require-amount"

    def test_enum_allowlist_allows_valid_value(self):
        """enum_allowlist should allow values in list."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="category-allowlist",
                rule_type="enum_allowlist",
                field_path="category",
                field_path_tokens=["category"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=["travel", "office", "meals"],
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"category": "travel"},
        )

        assert result.allow is True

    def test_enum_allowlist_denies_invalid_value(self):
        """enum_allowlist should deny values not in list."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="category-allowlist",
                rule_type="enum_allowlist",
                field_path="category",
                field_path_tokens=["category"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=["travel", "office", "meals"],
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"category": "gambling"},
        )

        assert result.allow is False

    def test_endpoint_sig_exact_match(self):
        """Policies should only apply to exact endpoint match (v1.1)."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="max-100",
                rule_type="numeric_max",
                field_path="amount",
                field_path_tokens=["amount"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=100,
            )
        ])
        set_policies(None, policy_def)

        # Should apply to matching endpoint
        result1 = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 150},
        )
        assert result1.allow is False

        # Should NOT apply to different endpoint (no wildcards)
        result2 = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /approvals/{approval_id}/decide",
            payload={"amount": 150},
        )
        assert result2.allow is True

    def test_phase_filtering(self):
        """Policies should only apply to matching phase."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="max-100",
                rule_type="numeric_max",
                field_path="amount",
                field_path_tokens=["amount"],
                phase="post",  # Only applies to post
                endpoint_sig="POST /finance/expenses",
                value=100,
            )
        ])
        set_policies(None, policy_def)

        # Should NOT apply to pre phase
        result1 = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 150},
        )
        assert result1.allow is True

        # Should apply to post phase
        result2 = evaluate_policies(
            phase="post",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 150},
        )
        assert result2.allow is False


class TestPolicyPreEnforcement:
    """Tests for policy pre-enforcement in /finance/expenses."""

    def test_policy_pre_blocks_amount_over_max(self, tmp_path: Path, ledger_path: Path):
        """Policy pre should block expense with amount > max."""
        create_bundle_with_policies(
            tmp_path,
            policies=[
                {
                    "policy_id": "expense-max-100",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 100,
                    "message": "Expense amount cannot exceed 100",
                }
            ],
        )
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # Try to create expense with amount > 100
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 150, "description": "test expense"},
        )

        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "POLICY_DENIED"
        assert "violations" in data
        assert "Expense amount cannot exceed 100" in data["violations"][0]

    def test_policy_pre_allows_amount_under_max(self, tmp_path: Path, ledger_path: Path):
        """Policy pre should allow expense with amount <= max."""
        create_bundle_with_policies(
            tmp_path,
            policies=[
                {
                    "policy_id": "expense-max-100",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 100,
                }
            ],
        )
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # Create expense with amount <= 100
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 50, "description": "test expense"},
        )

        # Should succeed (202 pending_approval due to approvals config)
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending_approval"

    def test_policy_pre_emits_ledger_event_on_deny(self, tmp_path: Path, ledger_path: Path):
        """POLICY_PRE_DECISION should be emitted when policy denies."""
        create_bundle_with_policies(
            tmp_path,
            policies=[
                {
                    "policy_id": "expense-max-100",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 100,
                }
            ],
        )
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 150},
        )

        assert response.status_code == 403

        # Check ledger event
        ledger = get_ledger()
        events = ledger.get_all_events()

        policy_events = [e for e in events if e.event_type == "POLICY_PRE_DECISION"]
        assert len(policy_events) == 1

        event = policy_events[0]
        assert event.step == "POLICY_GATE:pre:POST /finance/expenses"
        assert event.payload["allow"] is False
        assert "expense-max-100" in event.payload["matched_policies"]
        assert len(event.payload["violations"]) == 1

    def test_policy_pre_emits_ledger_event_on_allow(self, tmp_path: Path, ledger_path: Path):
        """POLICY_PRE_DECISION should be emitted when policy allows."""
        create_bundle_with_policies(
            tmp_path,
            policies=[
                {
                    "policy_id": "expense-max-100",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 100,
                }
            ],
        )
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 50},
        )

        assert response.status_code == 202

        # Check ledger event
        ledger = get_ledger()
        events = ledger.get_all_events()

        policy_events = [e for e in events if e.event_type == "POLICY_PRE_DECISION"]
        assert len(policy_events) == 1

        event = policy_events[0]
        assert event.payload["allow"] is True
        assert len(event.payload["violations"]) == 0


class TestNoPoliciesAllowsAll:
    """Test that no policies.json allows all requests."""

    def test_no_policies_allows_any_amount(self, tmp_path: Path, ledger_path: Path):
        """Without policies.json, any amount should be allowed."""
        create_bundle_with_policies(tmp_path, policies=None)  # No policies
        load_bundle(tmp_path)

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # Create expense with very large amount
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 1000000, "description": "big expense"},
        )

        # Should succeed (202 pending_approval)
        assert response.status_code == 202


class TestInvalidPoliciesJson:
    """Test handling of invalid policies.json."""

    def test_invalid_policy_schema_enters_safe_mode(self, tmp_path: Path, ledger_path: Path, monkeypatch):
        """Invalid policy schema in policies.json should trigger SAFE_MODE."""
        # Create valid RBAC and approvals
        create_bundle_with_policies(tmp_path, policies=None)

        # Create policies.json with valid JSON but missing required policy_id field
        policies_path = tmp_path / "policies.json"
        with open(policies_path, "w", encoding="utf-8") as f:
            json.dump({
                "policies": [
                    {
                        # Missing policy_id - will cause KeyError when parsing
                        "rule_type": "numeric_max",
                        "field_path": "amount",
                    }
                ]
            }, f)

        # Load bundle - should enter safe mode because policy schema is invalid
        load_bundle(tmp_path)

        # Check that safe mode was entered
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == "POLICY_INVALID"

    def test_policies_json_not_in_manifest_still_loads(self, tmp_path: Path, ledger_path: Path):
        """policies.json not in manifest should still be loaded if it exists."""
        # Create bundle without policies in manifest
        create_bundle_with_policies(tmp_path, policies=None)

        # Add valid policies.json (not in manifest) with v1.1 schema
        policies_path = tmp_path / "policies.json"
        with open(policies_path, "w", encoding="utf-8") as f:
            json.dump({
                "policy_schema_version": "1.1",
                "policies": [
                    {
                        "policy_id": "test-policy",
                        "rule_type": "numeric_max",
                        "field_path": "amount",
                        "endpoint_sig": "POST /finance/expenses",
                        "value": 100,
                    }
                ]
            }, f)

        # Load bundle
        load_bundle(tmp_path)

        # Policies should be loaded
        policy_def = get_policies(None)
        assert policy_def is not None
        assert len(policy_def.policies) == 1
        assert policy_def.policies[0].policy_id == "test-policy"


class TestMultiDeptPolicies:
    """Tests for multi-department policy enforcement."""

    def create_multi_dept_bundle(
        self,
        bundle_path: Path,
        finance_policies: list = None,
        hr_policies: list = None,
    ) -> None:
        """Create a multi-dept bundle with per-department policies."""
        # Create departments directory
        depts_path = bundle_path / "departments"
        depts_path.mkdir()

        # Create finance department
        finance_path = depts_path / "finance"
        finance_path.mkdir()
        self._create_dept_artifacts(finance_path, finance_policies)

        # Create HR department
        hr_path = depts_path / "hr"
        hr_path.mkdir()
        self._create_dept_artifacts(hr_path, hr_policies)

        # Create contracts.json
        contracts_data = {
            "contracts": [
                {
                    "contract_id": "budget-request",
                    "provider_dept": "finance",
                    "consumers": ["hr"],
                }
            ]
        }
        with open(bundle_path / "contracts.json", "w", encoding="utf-8") as f:
            json.dump(contracts_data, f)

        # Create manifest
        manifest = {
            "name": "multi-dept-test",
            "version": "1.0.0",
            "mode": "multi",
            "departments": ["finance", "hr"],
            "contracts": {},
        }
        with open(bundle_path / "bundle.manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

    def _create_dept_artifacts(self, dept_path: Path, policies: list = None) -> None:
        """Create required artifacts for a department."""
        # Create rbac.json
        rbac_data = {
            "version": "1.0.0",
            "roles": [
                {"name": "analyst", "permissions": ["expense.create", "expense.read"]},
                {"name": "manager", "permissions": ["expense.create", "expense.read", "expense.approve"]},
            ],
        }
        with open(dept_path / "rbac.json", "w", encoding="utf-8") as f:
            json.dump(rbac_data, f)

        # Create approvals.json
        approvals_data = {
            "version": "1.0.0",
            "rules": [],
        }
        with open(dept_path / "approvals.json", "w", encoding="utf-8") as f:
            json.dump(approvals_data, f)

        # Create workflows.json
        with open(dept_path / "workflows.json", "w", encoding="utf-8") as f:
            json.dump({"workflows": []}, f)

        # Create sod.json
        with open(dept_path / "sod.json", "w", encoding="utf-8") as f:
            json.dump({"rules": []}, f)

        # Create invariants.json
        with open(dept_path / "invariants.json", "w", encoding="utf-8") as f:
            json.dump({"invariants": []}, f)

        # Create openapi.yaml
        with open(dept_path / "openapi.yaml", "w", encoding="utf-8") as f:
            f.write("openapi: 3.0.0\ninfo:\n  title: Test\n  version: 1.0.0\npaths: {}\n")

        # Create policies.json if provided
        if policies is not None:
            policies_data = {
                "version": "1.0.0",
                "policies": policies,
            }
            with open(dept_path / "policies.json", "w", encoding="utf-8") as f:
                json.dump(policies_data, f)

    def test_multi_dept_loads_policies_per_dept(self, tmp_path: Path, ledger_path: Path):
        """Multi-dept bundle should load separate policies per department."""
        self.create_multi_dept_bundle(
            tmp_path,
            finance_policies=[
                {
                    "policy_id": "finance-max-100",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 100,
                }
            ],
            hr_policies=[
                {
                    "policy_id": "hr-max-10",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 10,
                }
            ],
        )
        load_bundle(tmp_path)

        # Check finance policies loaded
        finance_policies = get_policies("finance")
        assert finance_policies is not None
        assert len(finance_policies.policies) == 1
        assert finance_policies.policies[0].value == 100

        # Check HR policies loaded
        hr_policies = get_policies("hr")
        assert hr_policies is not None
        assert len(hr_policies.policies) == 1
        assert hr_policies.policies[0].value == 10

    def test_multi_dept_evaluates_correct_dept_policies(self, tmp_path: Path, ledger_path: Path):
        """evaluate_policies should use correct dept's policies."""
        self.create_multi_dept_bundle(
            tmp_path,
            finance_policies=[
                {
                    "policy_id": "finance-max-100",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 100,
                }
            ],
            hr_policies=[
                {
                    "policy_id": "hr-max-10",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 10,
                }
            ],
        )
        load_bundle(tmp_path)

        # Finance allows 50 (under 100)
        result_finance = evaluate_policies(
            phase="pre",
            dept_id="finance",
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 50},
        )
        assert result_finance.allow is True

        # HR denies 50 (over 10)
        result_hr = evaluate_policies(
            phase="pre",
            dept_id="hr",
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 50},
        )
        assert result_hr.allow is False
        assert result_hr.violations[0].policy_id == "hr-max-10"

    def test_multi_dept_missing_policies_allows_all(self, tmp_path: Path, ledger_path: Path):
        """Dept without policies.json should allow all."""
        self.create_multi_dept_bundle(
            tmp_path,
            finance_policies=[
                {
                    "policy_id": "finance-max-100",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "phase": "pre",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 100,
                }
            ],
            hr_policies=None,  # No policies for HR
        )
        load_bundle(tmp_path)

        # HR should allow any amount
        result_hr = evaluate_policies(
            phase="pre",
            dept_id="hr",
            endpoint_sig="POST /finance/expenses",
            payload={"amount": 1000000},
        )
        assert result_hr.allow is True


class TestPolicyFileLoading:
    """Tests for loading policies from files."""

    def test_load_policies_from_file_success(self, tmp_path: Path):
        """load_policies_from_file should parse valid JSON (v1.1)."""
        policies_data = {
            "policy_schema_version": "1.1",
            "policies": [
                {
                    "policy_id": "test-policy",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "endpoint_sig": "POST /finance/expenses",
                    "value": 100,
                }
            ]
        }
        policies_path = tmp_path / "policies.json"
        with open(policies_path, "w", encoding="utf-8") as f:
            json.dump(policies_data, f)

        result = load_policies_from_file(policies_path)

        assert result is not None
        assert len(result.policies) == 1
        assert result.policies[0].policy_id == "test-policy"

    def test_load_policies_from_file_not_found(self, tmp_path: Path):
        """load_policies_from_file should return None for missing file."""
        result = load_policies_from_file(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_policies_from_file_invalid_json(self, tmp_path: Path):
        """load_policies_from_file should return None for invalid JSON."""
        policies_path = tmp_path / "policies.json"
        with open(policies_path, "w", encoding="utf-8") as f:
            f.write("{invalid")

        result = load_policies_from_file(policies_path)
        assert result is None

    def test_parse_policies_data_defaults(self):
        """parse_policies_data should use defaults for optional fields (v1.1)."""
        data = {
            "policy_schema_version": "1.1",
            "policies": [
                {
                    "policy_id": "test",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "endpoint_sig": "POST /finance/expenses",  # Required in v1.1
                }
            ]
        }
        result = parse_policies_data(data)

        assert result.policies[0].phase == "pre"  # Default
        assert result.policies[0].endpoint_sig == "POST /finance/expenses"
        assert result.policies[0].value is None
        assert result.policies[0].message == ""


class TestPolicySchemaV11:
    """Tests for Policy Schema v1.1 validation."""

    def test_v11_valid_endpoint_sig_allowed(self):
        """v1.1 with valid endpoint_sig should work."""
        data = {
            "policy_schema_version": "1.1",
            "policies": [
                {
                    "policy_id": "test",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "endpoint_sig": "POST /finance/expenses",
                    "value": 100,
                }
            ]
        }
        result = parse_policies_data(data)
        assert len(result.policies) == 1
        assert result.policies[0].endpoint_sig == "POST /finance/expenses"

    def test_v11_approvals_endpoint_allowed(self):
        """v1.1 with approvals endpoint_sig should work."""
        data = {
            "policy_schema_version": "1.1",
            "policies": [
                {
                    "policy_id": "test",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "endpoint_sig": "POST /approvals/{approval_id}/decide",
                    "value": 100,
                }
            ]
        }
        result = parse_policies_data(data)
        assert result.policies[0].endpoint_sig == "POST /approvals/{approval_id}/decide"

    def test_v11_unknown_endpoint_raises_error(self):
        """v1.1 with unknown endpoint_sig should raise POLICY_ENDPOINT_UNKNOWN."""
        data = {
            "policy_schema_version": "1.1",
            "policies": [
                {
                    "policy_id": "test",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "endpoint_sig": "POST /unknown/endpoint",
                    "value": 100,
                }
            ]
        }
        with pytest.raises(PolicySchemaError) as exc_info:
            parse_policies_data(data)
        assert exc_info.value.code == POLICY_ENDPOINT_UNKNOWN

    def test_v11_missing_endpoint_sig_raises_error(self):
        """v1.1 without endpoint_sig should raise POLICY_INVALID."""
        data = {
            "policy_schema_version": "1.1",
            "policies": [
                {
                    "policy_id": "test",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 100,
                }
            ]
        }
        with pytest.raises(PolicySchemaError) as exc_info:
            parse_policies_data(data)
        assert exc_info.value.code == "POLICY_INVALID"

    def test_v11_rejects_endpoint_pattern(self):
        """v1.1 with endpoint_pattern should raise POLICY_INVALID."""
        data = {
            "policy_schema_version": "1.1",
            "policies": [
                {
                    "policy_id": "test",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "endpoint_pattern": "POST /finance/expenses",  # Not allowed in v1.1
                    "value": 100,
                }
            ]
        }
        with pytest.raises(PolicySchemaError) as exc_info:
            parse_policies_data(data)
        assert exc_info.value.code == "POLICY_INVALID"


class TestPolicyLegacyBackwardCompat:
    """Tests for legacy schema backward compatibility."""

    def test_legacy_exact_endpoint_allowed(self):
        """Legacy schema with exact endpoint match should work."""
        data = {
            "policies": [
                {
                    "policy_id": "test",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "endpoint_pattern": "POST /finance/expenses",
                    "value": 100,
                }
            ]
        }
        result = parse_policies_data(data)
        assert result.policies[0].endpoint_sig == "POST /finance/expenses"

    def test_legacy_wildcard_pattern_enters_safe_mode(self, tmp_path: Path, ledger_path: Path, monkeypatch):
        """Legacy with wildcard endpoint_pattern should enter SAFE_MODE."""
        # Create a policies.json with wildcard (invalid in v1.1)
        policies_data = {
            "policies": [
                {
                    "policy_id": "test",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "endpoint_pattern": "POST /finance/*",  # Wildcard - not allowed
                    "value": 100,
                }
            ]
        }
        policies_path = tmp_path / "policies.json"
        with open(policies_path, "w", encoding="utf-8") as f:
            json.dump(policies_data, f)

        # load_policies_from_file returns None for invalid schema
        result = load_policies_from_file(policies_path)
        assert result is None

    def test_legacy_missing_endpoint_pattern_raises_error(self):
        """Legacy without endpoint_pattern should raise POLICY_INVALID."""
        data = {
            "policies": [
                {
                    "policy_id": "test",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 100,
                }
            ]
        }
        with pytest.raises(PolicySchemaError) as exc_info:
            parse_policies_data(data)
        assert exc_info.value.code == "POLICY_INVALID"


class TestFieldPathValidation:
    """Tests for field_path validation."""

    def test_valid_simple_field_path(self):
        """Simple field path should be valid."""
        tokens = validate_field_path("amount")
        assert tokens == ["amount"]

    def test_valid_nested_field_path(self):
        """Nested field path should be valid."""
        tokens = validate_field_path("payload.amount")
        assert tokens == ["payload", "amount"]

    def test_valid_underscore_field_path(self):
        """Field path with underscore should be valid."""
        tokens = validate_field_path("user_name")
        assert tokens == ["user_name"]

    def test_invalid_consecutive_dots(self):
        """Field path with .. should be invalid."""
        with pytest.raises(PolicySchemaError) as exc_info:
            validate_field_path("a..b")
        assert exc_info.value.code == POLICY_PATH_INVALID

    def test_invalid_leading_dot(self):
        """Field path starting with . should be invalid."""
        with pytest.raises(PolicySchemaError) as exc_info:
            validate_field_path(".amount")
        assert exc_info.value.code == POLICY_PATH_INVALID

    def test_invalid_trailing_dot(self):
        """Field path ending with . should be invalid."""
        with pytest.raises(PolicySchemaError) as exc_info:
            validate_field_path("amount.")
        assert exc_info.value.code == POLICY_PATH_INVALID

    def test_invalid_slash_in_path(self):
        """Field path with / should be invalid."""
        with pytest.raises(PolicySchemaError) as exc_info:
            validate_field_path("a/b")
        assert exc_info.value.code == POLICY_PATH_INVALID

    def test_invalid_brackets_in_path(self):
        """Field path with [] should be invalid (v1.1 doesn't support indices)."""
        with pytest.raises(PolicySchemaError) as exc_info:
            validate_field_path("items[0]")
        assert exc_info.value.code == POLICY_PATH_INVALID

    def test_empty_field_path(self):
        """Empty field path should be invalid."""
        with pytest.raises(PolicySchemaError) as exc_info:
            validate_field_path("")
        assert exc_info.value.code == POLICY_PATH_INVALID


class TestEndpointSigValidation:
    """Tests for endpoint_sig validation."""

    def test_allowed_endpoints(self):
        """Verify allowed endpoint signatures."""
        assert "POST /finance/expenses" in ALLOWED_ENDPOINT_SIGS
        assert "POST /approvals/{approval_id}/decide" in ALLOWED_ENDPOINT_SIGS

    def test_validate_allowed_endpoint(self):
        """validate_endpoint_sig should pass for allowed endpoints."""
        validate_endpoint_sig("POST /finance/expenses")  # Should not raise
        validate_endpoint_sig("POST /approvals/{approval_id}/decide")  # Should not raise

    def test_validate_unknown_endpoint(self):
        """validate_endpoint_sig should raise for unknown endpoints."""
        with pytest.raises(PolicySchemaError) as exc_info:
            validate_endpoint_sig("GET /finance/expenses")
        assert exc_info.value.code == POLICY_ENDPOINT_UNKNOWN

    def test_validate_wildcard_rejected(self):
        """validate_endpoint_sig should reject wildcards."""
        with pytest.raises(PolicySchemaError) as exc_info:
            validate_endpoint_sig("*")
        assert exc_info.value.code == POLICY_ENDPOINT_UNKNOWN


class TestFieldMissingBehavior:
    """Tests for field missing = violation behavior (v1.1 hardening)."""

    def test_numeric_max_field_missing_denies(self):
        """numeric_max with missing field should deny (v1.1)."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="max-100",
                rule_type="numeric_max",
                field_path="amount",
                field_path_tokens=["amount"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=100,
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={},  # No amount field
        )

        assert result.allow is False
        assert "missing" in result.violations[0].message.lower()

    def test_numeric_min_field_missing_denies(self):
        """numeric_min with missing field should deny (v1.1)."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="min-10",
                rule_type="numeric_min",
                field_path="amount",
                field_path_tokens=["amount"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=10,
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={},
        )

        assert result.allow is False

    def test_string_max_len_field_missing_denies(self):
        """string_max_len with missing field should deny (v1.1)."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="desc-max-100",
                rule_type="string_max_len",
                field_path="description",
                field_path_tokens=["description"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=100,
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={},
        )

        assert result.allow is False

    def test_enum_allowlist_field_missing_denies(self):
        """enum_allowlist with missing field should deny (v1.1)."""
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="category-check",
                rule_type="enum_allowlist",
                field_path="category",
                field_path_tokens=["category"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=["travel", "office"],
            )
        ])
        set_policies(None, policy_def)

        result = evaluate_policies(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            payload={},
        )

        assert result.allow is False
