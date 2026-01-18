"""Tests for Mandate Engine (Phase 7.6).

Tests:
1. Loader: mandates.json loading (single/multi mode), SAFE_MODE on invalid
2. Core: Parse mandates v1.0, match by endpoint_sig + phase
3. Validation: Actor roles, validity window (ISO8601 UTC), limits
4. Enforcement: mandate_pre in finance.py, mandate_post in approvals.py
5. Ledger: MANDATE_EVALUATED events
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.actor_context import ActorContext
from engine.core.errors import (
    MANDATE_INVALID,
    MANDATE_DENIED,
    MANDATE_EXPIRED,
    MANDATE_ROLE_MISMATCH,
)
from engine.core.mandates import (
    parse_mandates_data,
    load_mandates_from_file,
    evaluate_mandates,
    emit_mandate_decision,
    set_mandates,
    get_mandates,
    clear_all_mandates,
    MandateSchemaError,
    MandateDef,
    Mandate,
)
from engine.loader.load_bundle import load_bundle
from engine.api.server import app


@pytest.fixture(autouse=True)
def reset_state():
    """Reset runtime state and mandates before each test."""
    runtime_state.set_active()
    clear_all_mandates()
    yield
    runtime_state.set_active()
    clear_all_mandates()


class TestMandateParsing:
    """Test mandate parsing from JSON."""

    def test_parse_valid_mandate_v1_0(self):
        """Parse a valid mandate v1.0 schema."""
        data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "mandate-001",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["employee", "manager"],
                    "limits": [
                        {
                            "rule_type": "numeric_max",
                            "field_path": "amount",
                            "value": 1000,
                            "message": "Amount exceeds mandate limit",
                        }
                    ],
                    "message": "Expense mandate",
                }
            ],
        }
        mandate_def = parse_mandates_data(data)
        assert len(mandate_def.mandates) == 1
        mandate = mandate_def.mandates[0]
        assert mandate.mandate_id == "mandate-001"
        assert mandate.endpoint_sig == "POST /finance/expenses"
        assert mandate.phase == "pre"
        assert mandate.allowed_roles == ["employee", "manager"]
        assert len(mandate.limits) == 1
        assert mandate.limits[0].rule_type == "numeric_max"
        assert mandate.limits[0].field_path == "amount"
        assert mandate.limits[0].value == 1000

    def test_parse_mandate_with_validity_window(self):
        """Parse mandate with valid_from/valid_until."""
        now = datetime.now(timezone.utc)
        valid_from = (now - timedelta(hours=1)).isoformat()
        valid_until = (now + timedelta(hours=1)).isoformat()

        data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "mandate-time",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["employee"],
                    "valid_from": valid_from,
                    "valid_until": valid_until,
                }
            ],
        }
        mandate_def = parse_mandates_data(data)
        mandate = mandate_def.mandates[0]
        assert mandate.valid_from is not None
        assert mandate.valid_until is not None

    def test_parse_invalid_schema_version(self):
        """Reject invalid schema version."""
        data = {
            "mandate_schema_version": "2.0",
            "mandates": [],
        }
        with pytest.raises(MandateSchemaError) as exc_info:
            parse_mandates_data(data)
        assert exc_info.value.code == MANDATE_INVALID
        assert "2.0" in exc_info.value.message

    def test_parse_missing_mandate_id(self):
        """Reject mandate without mandate_id."""
        data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": [],
                }
            ],
        }
        with pytest.raises(MandateSchemaError) as exc_info:
            parse_mandates_data(data)
        assert exc_info.value.code == MANDATE_INVALID
        assert "mandate_id" in exc_info.value.message

    def test_parse_invalid_endpoint_sig(self):
        """Reject unknown endpoint_sig."""
        data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "mandate-001",
                    "endpoint_sig": "GET /unknown/endpoint",
                    "phase": "pre",
                    "allowed_roles": [],
                }
            ],
        }
        with pytest.raises(MandateSchemaError) as exc_info:
            parse_mandates_data(data)
        assert exc_info.value.code == MANDATE_INVALID
        assert "endpoint_sig" in exc_info.value.message

    def test_parse_invalid_phase(self):
        """Reject invalid phase value."""
        data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "mandate-001",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "invalid",
                    "allowed_roles": [],
                }
            ],
        }
        with pytest.raises(MandateSchemaError) as exc_info:
            parse_mandates_data(data)
        assert exc_info.value.code == MANDATE_INVALID
        assert "phase" in exc_info.value.message

    def test_parse_invalid_rule_type(self):
        """Reject invalid rule_type in limits."""
        data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "mandate-001",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": [],
                    "limits": [
                        {
                            "rule_type": "invalid_type",
                            "field_path": "amount",
                            "value": 100,
                        }
                    ],
                }
            ],
        }
        with pytest.raises(MandateSchemaError) as exc_info:
            parse_mandates_data(data)
        assert exc_info.value.code == MANDATE_INVALID
        assert "rule_type" in exc_info.value.message


class TestMandateEvaluation:
    """Test mandate evaluation logic."""

    def test_no_mandate_allows_request(self):
        """No mandates defined = allow by default."""
        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={"amount": 100},
        )
        assert result.allow is True
        assert result.mandate_id is None

    def test_mandate_allows_matching_request(self):
        """Mandate matches and allows request."""
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                )
            ]
        )
        set_mandates(None, mandate_def)

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={},
        )
        assert result.allow is True
        assert result.mandate_id == "mandate-001"

    def test_mandate_denies_wrong_role(self):
        """Mandate denies actor with wrong role."""
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["manager"],
                )
            ]
        )
        set_mandates(None, mandate_def)

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],  # Not manager
        )
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={},
        )
        assert result.allow is False
        assert result.mandate_id == "mandate-001"
        assert len(result.violations) == 1
        assert result.violations[0].code == MANDATE_ROLE_MISMATCH

    def test_mandate_denies_expired(self):
        """Mandate denies expired request."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    valid_until=past,
                )
            ]
        )
        set_mandates(None, mandate_def)

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={},
        )
        assert result.allow is False
        assert result.violations[0].code == MANDATE_EXPIRED

    def test_mandate_denies_not_yet_active(self):
        """Mandate denies not-yet-active request."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    valid_from=future,
                )
            ]
        )
        set_mandates(None, mandate_def)

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={},
        )
        assert result.allow is False
        assert result.violations[0].code == MANDATE_EXPIRED

    def test_mandate_limit_numeric_max_allows(self):
        """Mandate with numeric_max allows within limit."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
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

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={"amount": 500},
        )
        assert result.allow is True

    def test_mandate_limit_numeric_max_denies(self):
        """Mandate with numeric_max denies exceeding limit."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
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

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )
        result = evaluate_mandates(
            phase="pre",
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={"amount": 1500},
        )
        assert result.allow is False
        assert result.violations[0].code == MANDATE_DENIED
        assert result.violations[0].rule_type == "numeric_max"

    def test_mandate_no_match_denies(self):
        """No matching mandate = deny per canonical semantics.

        Canonical semantics: If mandates.json exists but no mandate is
        applicable to (endpoint_sig, phase), deny with MANDATE_DENIED.
        "Nenhuma execução fora de mandato" - no execution outside of mandate.
        """
        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="post",  # Different phase
                    allowed_roles=["employee"],
                )
            ]
        )
        set_mandates(None, mandate_def)

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )
        result = evaluate_mandates(
            phase="pre",  # Different phase than mandate - no match
            dept_id=None,
            endpoint_sig="POST /finance/expenses",
            actor=actor,
            payload={},
        )
        assert result.allow is False
        assert result.mandate_id is None
        assert len(result.violations) == 1
        assert result.violations[0].code == MANDATE_DENIED
        assert "No mandate applicable" in result.violations[0].message


class TestMandateLoaderSingleMode:
    """Test mandate loading in single-department mode."""

    def test_load_valid_mandates_single_mode(self, tmp_path):
        """Load valid mandates.json in single mode."""
        # Create minimal bundle
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')

        mandates_data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "test-mandate",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["employee"],
                }
            ],
        }
        (tmp_path / "mandates.json").write_text(json.dumps(mandates_data))

        result = load_bundle(tmp_path)
        assert result is not None
        assert runtime_state.is_active()

        mandate_def = get_mandates(None)
        assert mandate_def is not None
        assert len(mandate_def.mandates) == 1
        assert mandate_def.mandates[0].mandate_id == "test-mandate"

    def test_safe_mode_on_invalid_mandates_json(self, tmp_path):
        """Enter SAFE_MODE on invalid JSON in mandates.json."""
        # Create minimal bundle
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')
        (tmp_path / "mandates.json").write_text("{invalid json}")

        result = load_bundle(tmp_path)
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == MANDATE_INVALID

    def test_safe_mode_on_invalid_mandate_schema(self, tmp_path):
        """Enter SAFE_MODE on invalid mandate schema."""
        # Create minimal bundle
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')

        # Invalid schema version
        mandates_data = {
            "mandate_schema_version": "99.0",
            "mandates": [],
        }
        (tmp_path / "mandates.json").write_text(json.dumps(mandates_data))

        result = load_bundle(tmp_path)
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == MANDATE_INVALID

    def test_no_mandates_file_is_ok(self, tmp_path):
        """Bundle without mandates.json is valid (mandates are optional)."""
        # Create minimal bundle
        (tmp_path / "bundle.manifest.json").write_text('{"name": "test", "contracts": []}')

        result = load_bundle(tmp_path)
        assert result is not None
        assert runtime_state.is_active()
        assert get_mandates(None) is None


class TestMandateLoaderMultiMode:
    """Test mandate loading in multi-department mode."""

    def test_load_valid_mandates_multi_mode(self, tmp_path):
        """Load valid mandates.json per department in multi mode."""
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

        # Mandates for department
        mandates_data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "dept-mandate",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["dept-employee"],
                }
            ],
        }
        (dept_path / "mandates.json").write_text(json.dumps(mandates_data))

        result = load_bundle(tmp_path)
        assert result is not None
        assert runtime_state.is_active()

        mandate_def = get_mandates("finance")
        assert mandate_def is not None
        assert mandate_def.mandates[0].mandate_id == "dept-mandate"


class TestMandateLedgerEvents:
    """Test MANDATE_EVALUATED ledger events."""

    def test_emit_mandate_decision_allows(self, tmp_path):
        """Emit MANDATE_EVALUATED event on allow."""
        from engine.core.ledger import init_ledger, get_ledger
        from engine.core.mandates import MandateEvalResult

        ledger = init_ledger(tmp_path / "ledger.jsonl")
        ledger.set_bundle_hashes("abc123", "def456")

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

        result = MandateEvalResult(allow=True, mandate_id="mandate-001")

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
        assert event.step == "MANDATE_GATE:pre:POST /finance/expenses"
        assert event.payload["allow"] is True
        assert event.payload["mandate_id"] == "mandate-001"

    def test_emit_mandate_decision_denies(self, tmp_path):
        """Emit MANDATE_EVALUATED event on deny."""
        from engine.core.ledger import init_ledger
        from engine.core.mandates import MandateEvalResult, MandateViolation

        ledger = init_ledger(tmp_path / "ledger.jsonl")
        ledger.set_bundle_hashes("abc123", "def456")

        actor = ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

        result = MandateEvalResult(
            allow=False,
            mandate_id="mandate-001",
            violations=[
                MandateViolation(
                    mandate_id="mandate-001",
                    code=MANDATE_ROLE_MISMATCH,
                    rule_type=None,
                    field_path=None,
                    message="Role mismatch",
                )
            ],
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
        assert event.payload["violations"][0]["code"] == MANDATE_ROLE_MISMATCH


class TestMandateApiEnforcement:
    """Test mandate enforcement via API endpoints."""

    def _create_bundle_with_mandate(self, tmp_path, mandates_data, roles):
        """Helper to create a bundle with RBAC and mandates."""
        from engine.loader.verify_hashes import compute_sha256

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

        # Create mandates
        mandates_path = tmp_path / "mandates.json"
        with open(mandates_path, "w", encoding="utf-8") as f:
            json.dump(mandates_data, f)

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

    def test_finance_mandate_pre_allows(self, tmp_path, monkeypatch):
        """POST /finance/expenses allows when mandate permits."""
        import uuid

        mandates_data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "expense-mandate",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["employee"],
                    "limits": [
                        {
                            "rule_type": "numeric_max",
                            "field_path": "amount",
                            "value": 1000,
                        }
                    ],
                }
            ],
        }
        roles = [{"name": "employee", "permissions": ["expense.create"]}]
        self._create_bundle_with_mandate(tmp_path, mandates_data, roles)

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

    def test_finance_mandate_pre_denies_limit_exceeded(self, tmp_path, monkeypatch):
        """POST /finance/expenses denies when mandate limit exceeded."""
        import uuid

        mandates_data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "expense-mandate",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["employee"],
                    "limits": [
                        {
                            "rule_type": "numeric_max",
                            "field_path": "amount",
                            "value": 1000,
                        }
                    ],
                }
            ],
        }
        roles = [{"name": "employee", "permissions": ["expense.create"]}]
        self._create_bundle_with_mandate(tmp_path, mandates_data, roles)

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
            json={"amount": 2000, "description": "Too expensive"},  # Exceeds limit
        )

        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.json()}"
        data = response.json()
        # Response is the HTTPException detail dict directly
        assert data["code"] == MANDATE_DENIED
        assert data["mandate_id"] == "expense-mandate"

    def test_finance_mandate_pre_denies_wrong_role(self, tmp_path, monkeypatch):
        """POST /finance/expenses denies when actor role doesn't match mandate."""
        import uuid

        mandates_data = {
            "mandate_schema_version": "1.0",
            "mandates": [
                {
                    "mandate_id": "expense-mandate",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["employee"],  # No intern
                }
            ],
        }
        roles = [
            {"name": "employee", "permissions": ["expense.create"]},
            {"name": "intern", "permissions": ["expense.create"]},
        ]
        self._create_bundle_with_mandate(tmp_path, mandates_data, roles)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))

        load_bundle(tmp_path)

        client = TestClient(app, raise_server_exceptions=False)
        actor_id = str(uuid.uuid4())
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "intern",  # Not allowed by mandate
            },
            json={"amount": 100},
        )

        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.json()}"
        data = response.json()
        # Response is the HTTPException detail dict directly
        assert data["code"] == MANDATE_DENIED


class TestMandateLimitRuleTypes:
    """Test all mandate limit rule types."""

    @pytest.fixture
    def actor(self):
        """Create test actor."""
        return ActorContext(
            tenant_id="tenant-1",
            actor_id="actor-1",
            roles=["employee"],
        )

    def test_numeric_min_allows(self, actor):
        """numeric_min allows value at or above minimum."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    limits=[
                        MandateLimit(
                            rule_type="numeric_min",
                            field_path="amount",
                            field_path_tokens=["amount"],
                            value=100,
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
            payload={"amount": 150},
        )
        assert result.allow is True

    def test_numeric_min_denies(self, actor):
        """numeric_min denies value below minimum."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    limits=[
                        MandateLimit(
                            rule_type="numeric_min",
                            field_path="amount",
                            field_path_tokens=["amount"],
                            value=100,
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
            payload={"amount": 50},
        )
        assert result.allow is False
        assert result.violations[0].rule_type == "numeric_min"

    def test_string_max_len_allows(self, actor):
        """string_max_len allows string within length."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    limits=[
                        MandateLimit(
                            rule_type="string_max_len",
                            field_path="description",
                            field_path_tokens=["description"],
                            value=100,
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
            payload={"description": "Short text"},
        )
        assert result.allow is True

    def test_string_max_len_denies(self, actor):
        """string_max_len denies string exceeding length."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    limits=[
                        MandateLimit(
                            rule_type="string_max_len",
                            field_path="description",
                            field_path_tokens=["description"],
                            value=10,
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
            payload={"description": "This is a very long description"},
        )
        assert result.allow is False
        assert result.violations[0].rule_type == "string_max_len"

    def test_required_field_allows(self, actor):
        """required_field allows when field present."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    limits=[
                        MandateLimit(
                            rule_type="required_field",
                            field_path="category",
                            field_path_tokens=["category"],
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
            payload={"category": "travel"},
        )
        assert result.allow is True

    def test_required_field_denies(self, actor):
        """required_field denies when field missing."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    limits=[
                        MandateLimit(
                            rule_type="required_field",
                            field_path="category",
                            field_path_tokens=["category"],
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
            payload={},  # Missing category
        )
        assert result.allow is False
        assert result.violations[0].rule_type == "required_field"

    def test_enum_allowlist_allows(self, actor):
        """enum_allowlist allows value in list."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    limits=[
                        MandateLimit(
                            rule_type="enum_allowlist",
                            field_path="category",
                            field_path_tokens=["category"],
                            value=["travel", "meals", "supplies"],
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
            payload={"category": "travel"},
        )
        assert result.allow is True

    def test_enum_allowlist_denies(self, actor):
        """enum_allowlist denies value not in list."""
        from engine.core.mandates import MandateLimit

        mandate_def = MandateDef(
            mandates=[
                Mandate(
                    mandate_id="mandate-001",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    allowed_roles=["employee"],
                    limits=[
                        MandateLimit(
                            rule_type="enum_allowlist",
                            field_path="category",
                            field_path_tokens=["category"],
                            value=["travel", "meals", "supplies"],
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
            payload={"category": "entertainment"},  # Not in list
        )
        assert result.allow is False
        assert result.violations[0].rule_type == "enum_allowlist"
