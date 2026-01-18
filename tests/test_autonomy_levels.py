"""Tests for AXIOM Autonomy Levels (Phase 8.0.1).

Tests:
1. Schema validation (version, phases, endpoint_sig allowlist, levels range)
2. Default allow-all when file missing
3. API integration:
   - Deny on POST /finance/expenses when required_level > current_level
   - Deny on POST /approvals/{approval_id}/decide similarly
   - Verify ledger contains AUTONOMY_EVALUATED events with correct step and decision
4. Multi-dept tests where finance/hr have different autonomy.json behavior
"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.actor_context import ActorContext
from engine.core.errors import (
    AUTONOMY_INVALID,
    AUTONOMY_INSUFFICIENT,
    AUTONOMY_ENDPOINT_UNKNOWN,
    AUTONOMY_LEVEL_INVALID,
)
from engine.core.autonomy import (
    parse_autonomy_data,
    load_autonomy_from_file,
    evaluate_autonomy,
    emit_autonomy_evaluated,
    set_autonomy_for_dept,
    get_autonomy_for_dept,
    reset_all_autonomy,
    AutonomySchemaError,
    AutonomyDef,
    AutonomyRule,
    AutonomyEvalResult,
    DEFAULT_CURRENT_LEVEL,
    DEFAULT_REQUIRED_LEVEL,
)
from engine.core.ledger import init_ledger, set_ledger, get_ledger
from engine.loader.load_bundle import load_bundle
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


@pytest.fixture(autouse=True)
def reset_state():
    """Reset runtime state and autonomy before each test."""
    runtime_state.set_active()
    reset_all_autonomy()
    set_ledger(None)
    yield
    runtime_state.set_active()
    reset_all_autonomy()
    set_ledger(None)


class TestAutonomySchemaValidation:
    """Test autonomy schema parsing and validation."""

    def test_parse_valid_autonomy_v1_0(self):
        """Parse a valid autonomy v1.0 schema."""
        data = {
            "autonomy_schema_version": "1.0",
            "current_level": 3,
            "rules": [
                {
                    "rule_id": "rule-001",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 2,
                }
            ],
        }
        autonomy_def = parse_autonomy_data(data)
        assert autonomy_def.current_level == 3
        assert len(autonomy_def.rules) == 1
        rule = autonomy_def.rules[0]
        assert rule.rule_id == "rule-001"
        assert rule.endpoint_sig == "POST /finance/expenses"
        assert rule.phase == "pre"
        assert rule.required_level == 2

    def test_parse_minimal_autonomy(self):
        """Parse minimal autonomy with defaults."""
        data = {
            "autonomy_schema_version": "1.0",
        }
        autonomy_def = parse_autonomy_data(data)
        assert autonomy_def.current_level == DEFAULT_CURRENT_LEVEL
        assert len(autonomy_def.rules) == 0

    def test_parse_invalid_schema_version(self):
        """Reject invalid schema version."""
        data = {
            "autonomy_schema_version": "2.0",
            "current_level": 3,
        }
        with pytest.raises(AutonomySchemaError) as exc_info:
            parse_autonomy_data(data)
        assert exc_info.value.code == AUTONOMY_INVALID
        assert "2.0" in exc_info.value.message

    def test_parse_invalid_phase(self):
        """Reject invalid phase value."""
        data = {
            "autonomy_schema_version": "1.0",
            "rules": [
                {
                    "rule_id": "rule-001",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "invalid",
                    "required_level": 2,
                }
            ],
        }
        with pytest.raises(AutonomySchemaError) as exc_info:
            parse_autonomy_data(data)
        assert exc_info.value.code == AUTONOMY_INVALID
        assert "phase" in exc_info.value.message

    def test_parse_invalid_endpoint_sig(self):
        """Reject unknown endpoint_sig."""
        data = {
            "autonomy_schema_version": "1.0",
            "rules": [
                {
                    "rule_id": "rule-001",
                    "endpoint_sig": "GET /unknown/endpoint",
                    "phase": "pre",
                    "required_level": 2,
                }
            ],
        }
        with pytest.raises(AutonomySchemaError) as exc_info:
            parse_autonomy_data(data)
        assert exc_info.value.code == AUTONOMY_ENDPOINT_UNKNOWN
        assert "endpoint_sig" in exc_info.value.message

    def test_parse_level_too_low(self):
        """Reject level below 0."""
        data = {
            "autonomy_schema_version": "1.0",
            "current_level": -1,
        }
        with pytest.raises(AutonomySchemaError) as exc_info:
            parse_autonomy_data(data)
        assert exc_info.value.code == AUTONOMY_LEVEL_INVALID
        assert "-1" in exc_info.value.message

    def test_parse_level_too_high(self):
        """Reject level above 4."""
        data = {
            "autonomy_schema_version": "1.0",
            "current_level": 5,
        }
        with pytest.raises(AutonomySchemaError) as exc_info:
            parse_autonomy_data(data)
        assert exc_info.value.code == AUTONOMY_LEVEL_INVALID
        assert "5" in exc_info.value.message

    def test_parse_level_not_integer(self):
        """Reject non-integer level."""
        data = {
            "autonomy_schema_version": "1.0",
            "current_level": "high",
        }
        with pytest.raises(AutonomySchemaError) as exc_info:
            parse_autonomy_data(data)
        assert exc_info.value.code == AUTONOMY_LEVEL_INVALID

    def test_parse_missing_rule_id(self):
        """Reject rule without rule_id."""
        data = {
            "autonomy_schema_version": "1.0",
            "rules": [
                {
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 2,
                }
            ],
        }
        with pytest.raises(AutonomySchemaError) as exc_info:
            parse_autonomy_data(data)
        assert exc_info.value.code == AUTONOMY_INVALID
        assert "rule_id" in exc_info.value.message

    def test_parse_missing_required_level(self):
        """Reject rule without required_level."""
        data = {
            "autonomy_schema_version": "1.0",
            "rules": [
                {
                    "rule_id": "rule-001",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                }
            ],
        }
        with pytest.raises(AutonomySchemaError) as exc_info:
            parse_autonomy_data(data)
        assert exc_info.value.code == AUTONOMY_INVALID
        assert "required_level" in exc_info.value.message


class TestAutonomyEvaluation:
    """Test autonomy evaluation logic."""

    def test_no_autonomy_allows_request(self):
        """No autonomy defined = allow by default with L4."""
        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result.decision == "allow"
        assert result.current_level == DEFAULT_CURRENT_LEVEL
        assert result.required_level == DEFAULT_REQUIRED_LEVEL
        assert result.rule_id is None

    def test_autonomy_allows_when_level_sufficient(self):
        """Autonomy allows when current_level >= required_level."""
        autonomy_def = AutonomyDef(
            current_level=3,
            rules=[
                AutonomyRule(
                    rule_id="rule-001",
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
        assert result.current_level == 3
        assert result.required_level == 2
        assert result.rule_id == "rule-001"

    def test_autonomy_allows_when_level_equal(self):
        """Autonomy allows when current_level == required_level."""
        autonomy_def = AutonomyDef(
            current_level=2,
            rules=[
                AutonomyRule(
                    rule_id="rule-001",
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

    def test_autonomy_denies_when_level_insufficient(self):
        """Autonomy denies when current_level < required_level."""
        autonomy_def = AutonomyDef(
            current_level=1,
            rules=[
                AutonomyRule(
                    rule_id="rule-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=3,
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
        assert result.current_level == 1
        assert result.required_level == 3
        assert result.rule_id == "rule-001"
        assert "below required level" in result.reason

    def test_autonomy_no_matching_rule_denies(self):
        """No matching rule = deny per canonical semantics.

        Canonical semantics: If autonomy.json exists but no rule is
        applicable to (endpoint_sig, phase), deny with AUTONOMY_INSUFFICIENT.
        """
        autonomy_def = AutonomyDef(
            current_level=2,
            rules=[
                AutonomyRule(
                    rule_id="rule-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="post",  # Different phase
                    required_level=3,
                )
            ],
        )
        set_autonomy_for_dept(None, autonomy_def)

        result = evaluate_autonomy(
            phase="pre",  # Different phase than rule - no match
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result.decision == "deny"
        assert result.current_level == 2
        assert result.rule_id is None
        assert "No autonomy rule applicable" in result.reason

    def test_autonomy_first_matching_rule_wins(self):
        """First matching rule in file order is used."""
        autonomy_def = AutonomyDef(
            current_level=2,
            rules=[
                AutonomyRule(
                    rule_id="rule-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=1,  # This should match first
                ),
                AutonomyRule(
                    rule_id="rule-002",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=4,  # This would deny but shouldn't be reached
                ),
            ],
        )
        set_autonomy_for_dept(None, autonomy_def)

        result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert result.decision == "allow"
        assert result.rule_id == "rule-001"


class TestAutonomyLoaderSingleMode:
    """Test autonomy loading in single-department mode."""

    def test_load_valid_autonomy_single_mode(self, tmp_path):
        """Load valid autonomy.json in single mode."""
        # Create minimal bundle
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')

        autonomy_data = {
            "autonomy_schema_version": "1.0",
            "current_level": 2,
            "rules": [
                {
                    "rule_id": "test-rule",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 1,
                }
            ],
        }
        (tmp_path / "autonomy.json").write_text(json.dumps(autonomy_data))

        result = load_bundle(tmp_path)
        assert result is not None
        assert runtime_state.is_active()

        autonomy_def = get_autonomy_for_dept(None)
        assert autonomy_def is not None
        assert autonomy_def.current_level == 2
        assert len(autonomy_def.rules) == 1
        assert autonomy_def.rules[0].rule_id == "test-rule"

    def test_safe_mode_on_invalid_autonomy_json(self, tmp_path):
        """Enter SAFE_MODE on invalid JSON in autonomy.json."""
        # Create minimal bundle
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')
        (tmp_path / "autonomy.json").write_text("{invalid json}")

        result = load_bundle(tmp_path)
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == AUTONOMY_INVALID

    def test_safe_mode_on_invalid_autonomy_schema(self, tmp_path):
        """Enter SAFE_MODE on invalid autonomy schema."""
        # Create minimal bundle
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')

        # Invalid schema version
        autonomy_data = {
            "autonomy_schema_version": "99.0",
        }
        (tmp_path / "autonomy.json").write_text(json.dumps(autonomy_data))

        result = load_bundle(tmp_path)
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == AUTONOMY_INVALID

    def test_no_autonomy_file_is_ok(self, tmp_path):
        """Bundle without autonomy.json is valid (allow-all default)."""
        # Create minimal bundle
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')

        result = load_bundle(tmp_path)
        assert result is not None
        assert runtime_state.is_active()
        assert get_autonomy_for_dept(None) is None

        # Verify allow-all behavior
        eval_result = evaluate_autonomy(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
        )
        assert eval_result.decision == "allow"


class TestAutonomyLoaderMultiMode:
    """Test autonomy loading in multi-department mode."""

    def test_load_valid_autonomy_multi_mode(self, tmp_path):
        """Load valid autonomy.json per department in multi mode."""
        # Create multi-dept bundle structure
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')
        (tmp_path / "contracts.json").write_text('{"version": "1.0", "contracts": []}')

        # Create department
        dept_path = tmp_path / "departments" / "finance"
        dept_path.mkdir(parents=True)

        # Required artifacts
        (dept_path / "rbac.json").write_text('{"version": "1.0", "roles": []}')
        (dept_path / "approvals.json").write_text('{"version": "1.0", "rules": []}')
        (dept_path / "workflows.json").write_text('{"version": "1.0", "workflows": []}')
        (dept_path / "sod.json").write_text('{"version": "1.0", "rules": []}')
        (dept_path / "invariants.json").write_text('{"version": "1.0", "invariants": []}')
        (dept_path / "openapi.yaml").write_text("openapi: '3.0.0'\ninfo:\n  title: Test\n  version: '1.0'\npaths: {}")

        # Autonomy for department
        autonomy_data = {
            "autonomy_schema_version": "1.0",
            "current_level": 2,
            "rules": [
                {
                    "rule_id": "dept-rule",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 1,
                }
            ],
        }
        (dept_path / "autonomy.json").write_text(json.dumps(autonomy_data))

        result = load_bundle(tmp_path)
        assert result is not None
        assert runtime_state.is_active()

        autonomy_def = get_autonomy_for_dept("finance")
        assert autonomy_def is not None
        assert autonomy_def.current_level == 2
        assert autonomy_def.rules[0].rule_id == "dept-rule"


class TestAutonomyLedgerEvents:
    """Test AUTONOMY_EVALUATED ledger events."""

    def test_emit_autonomy_evaluated_allows(self, tmp_path):
        """Emit AUTONOMY_EVALUATED event on allow."""
        ledger = init_ledger(tmp_path / "ledger.jsonl")
        ledger.set_bundle_hashes("abc123", "def456")

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

        result = AutonomyEvalResult(
            decision="allow",
            current_level=3,
            required_level=2,
            rule_id="rule-001",
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
        assert event.step == "AXIOM_AUTONOMY:pre:POST /finance/expenses"
        assert event.payload["decision"] == "allow"
        assert event.payload["current_level"] == 3
        assert event.payload["required_level"] == 2
        assert event.payload["rule_id"] == "rule-001"

    def test_emit_autonomy_evaluated_denies(self, tmp_path):
        """Emit AUTONOMY_EVALUATED event on deny."""
        ledger = init_ledger(tmp_path / "ledger.jsonl")
        ledger.set_bundle_hashes("abc123", "def456")

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

        result = AutonomyEvalResult(
            decision="deny",
            current_level=1,
            required_level=3,
            rule_id="rule-001",
            reason="Autonomy level 1 is below required level 3",
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
        assert event.payload["reason"] is not None


class TestAutonomyApiEnforcement:
    """Test autonomy enforcement via API endpoints."""

    def _create_bundle_with_autonomy(self, tmp_path, autonomy_data, roles):
        """Helper to create a bundle with RBAC and autonomy."""
        # Create RBAC
        rbac_data = {
            "version": "1.0.0",
            "name": "rbac",
            "roles": roles,
        }
        rbac_path = tmp_path / "rbac.json"
        with open(rbac_path, "w", encoding="utf-8") as f:
            json.dump(rbac_data, f)
        rbac_hash = compute_sha256(rbac_path)

        # Create autonomy
        if autonomy_data:
            autonomy_path = tmp_path / "autonomy.json"
            with open(autonomy_path, "w", encoding="utf-8") as f:
                json.dump(autonomy_data, f)

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
            ],
        }
        manifest_path = tmp_path / "bundle.manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f)

    def test_finance_autonomy_allows(self, tmp_path, monkeypatch):
        """POST /finance/expenses allows when autonomy level sufficient."""
        autonomy_data = {
            "autonomy_schema_version": "1.0",
            "current_level": 3,
            "rules": [
                {
                    "rule_id": "expense-rule",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 2,
                }
            ],
        }
        roles = [{"name": "employee", "permissions": ["expense.create"]}]
        self._create_bundle_with_autonomy(tmp_path, autonomy_data, roles)

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
            json={"amount": 500, "description": "Test expense"},
        )

        # Should succeed (200 or 202)
        assert response.status_code in (200, 202)

    def test_finance_autonomy_denies_insufficient_level(self, tmp_path, monkeypatch):
        """POST /finance/expenses denies when autonomy level insufficient."""
        autonomy_data = {
            "autonomy_schema_version": "1.0",
            "current_level": 1,  # Too low
            "rules": [
                {
                    "rule_id": "expense-rule",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 3,  # Requires L3
                }
            ],
        }
        roles = [{"name": "employee", "permissions": ["expense.create"]}]
        self._create_bundle_with_autonomy(tmp_path, autonomy_data, roles)

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
            json={"amount": 500, "description": "Test expense"},
        )

        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.json()}"
        data = response.json()
        assert data["code"] == AUTONOMY_INSUFFICIENT
        assert data["current_level"] == 1
        assert data["required_level"] == 3

    def test_finance_autonomy_ledger_event_emitted(self, tmp_path, monkeypatch):
        """Verify AUTONOMY_EVALUATED ledger event is emitted."""
        autonomy_data = {
            "autonomy_schema_version": "1.0",
            "current_level": 3,
            "rules": [
                {
                    "rule_id": "expense-rule",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 2,
                }
            ],
        }
        roles = [{"name": "employee", "permissions": ["expense.create"]}]
        self._create_bundle_with_autonomy(tmp_path, autonomy_data, roles)

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
            json={"amount": 500, "description": "Test expense"},
        )

        assert response.status_code in (200, 202)

        # Check ledger for AUTONOMY_EVALUATED event
        ledger = get_ledger()
        events = ledger.get_all_events()
        autonomy_events = [e for e in events if e.event_type == "AUTONOMY_EVALUATED"]
        assert len(autonomy_events) >= 1

        event = autonomy_events[0]
        assert event.step == "AXIOM_AUTONOMY:pre:POST /finance/expenses"
        assert event.payload["decision"] == "allow"
        assert event.payload["rule_id"] == "expense-rule"


class TestMultiDeptAutonomy:
    """Test multi-department autonomy behavior."""

    def test_different_autonomy_per_dept(self, tmp_path, monkeypatch):
        """Finance and HR have different autonomy levels."""
        # Create multi-dept bundle structure
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')
        (tmp_path / "contracts.json").write_text('{"version": "1.0", "contracts": []}')

        # Create finance department with L3
        finance_path = tmp_path / "departments" / "finance"
        finance_path.mkdir(parents=True)
        (finance_path / "rbac.json").write_text('{"version": "1.0", "roles": []}')
        (finance_path / "approvals.json").write_text('{"version": "1.0", "rules": []}')
        (finance_path / "workflows.json").write_text('{"version": "1.0", "workflows": []}')
        (finance_path / "sod.json").write_text('{"version": "1.0", "rules": []}')
        (finance_path / "invariants.json").write_text('{"version": "1.0", "invariants": []}')
        (finance_path / "openapi.yaml").write_text("openapi: '3.0.0'\ninfo:\n  title: Finance\n  version: '1.0'\npaths: {}")
        finance_autonomy = {
            "autonomy_schema_version": "1.0",
            "current_level": 3,
            "rules": [
                {
                    "rule_id": "finance-expense",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 2,
                }
            ],
        }
        (finance_path / "autonomy.json").write_text(json.dumps(finance_autonomy))

        # Create HR department with L1
        hr_path = tmp_path / "departments" / "hr"
        hr_path.mkdir(parents=True)
        (hr_path / "rbac.json").write_text('{"version": "1.0", "roles": []}')
        (hr_path / "approvals.json").write_text('{"version": "1.0", "rules": []}')
        (hr_path / "workflows.json").write_text('{"version": "1.0", "workflows": []}')
        (hr_path / "sod.json").write_text('{"version": "1.0", "rules": []}')
        (hr_path / "invariants.json").write_text('{"version": "1.0", "invariants": []}')
        (hr_path / "openapi.yaml").write_text("openapi: '3.0.0'\ninfo:\n  title: HR\n  version: '1.0'\npaths: {}")
        hr_autonomy = {
            "autonomy_schema_version": "1.0",
            "current_level": 1,  # Lower level
            "rules": [
                {
                    "rule_id": "hr-expense",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 2,
                }
            ],
        }
        (hr_path / "autonomy.json").write_text(json.dumps(hr_autonomy))

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))

        load_bundle(tmp_path)

        # Verify finance has L3 (allows)
        finance_autonomy_def = get_autonomy_for_dept("finance")
        assert finance_autonomy_def.current_level == 3
        finance_result = evaluate_autonomy(
            phase="pre",
            dept_id="finance",
            endpoint_sig="POST /finance/expenses",
        )
        assert finance_result.decision == "allow"

        # Verify HR has L1 (denies)
        hr_autonomy_def = get_autonomy_for_dept("hr")
        assert hr_autonomy_def.current_level == 1
        hr_result = evaluate_autonomy(
            phase="pre",
            dept_id="hr",
            endpoint_sig="POST /finance/expenses",
        )
        assert hr_result.decision == "deny"


class TestAutonomyLevelBoundaries:
    """Test autonomy level boundary conditions."""

    def test_level_0_blocks_all_requiring_above_0(self):
        """L0 blocks any rule requiring L1+."""
        autonomy_def = AutonomyDef(
            current_level=0,
            rules=[
                AutonomyRule(
                    rule_id="rule-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=1,
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

    def test_level_4_allows_all(self):
        """L4 allows any rule requiring up to L4."""
        autonomy_def = AutonomyDef(
            current_level=4,
            rules=[
                AutonomyRule(
                    rule_id="rule-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=4,
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

    def test_required_level_0_always_allows(self):
        """Required L0 is allowed by any current level."""
        autonomy_def = AutonomyDef(
            current_level=0,
            rules=[
                AutonomyRule(
                    rule_id="rule-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=0,
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
