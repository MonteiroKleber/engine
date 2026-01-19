"""Tests for IDL v1.1 mandate/autonomy emitters.

Covers:
- Emitters reflect IDL v1.1 (sem defaults silenciosos)
- v1.0 legacy behavior preserved
- Multi-dept emission works correctly
"""

import json
import pytest

from engine.ise.idl_parser import parse_idl
from engine.ise.emit.mandates_emit import emit_mandates, emit_mandates_json
from engine.ise.emit.autonomy_emit import emit_autonomy, emit_autonomy_json


# =============================================================================
# Test fixtures
# =============================================================================


def _make_idl_v11_with_mandates_autonomy() -> dict:
    """Create IDL v1.1 with mandates and autonomy."""
    return {
        "idl_version": "1.1",
        "system": "finance-pilot",
        "version": "1.0.0",
        "entities": [{"name": "Expense", "entity_type": "expense"}],
        "mandates": [
            {
                "mandate_id": "expense-create-pre",
                "endpoint_sig": "POST /finance/expenses",
                "phase": "pre",
                "allowed_roles": ["analyst", "admin"],
                "limits": [
                    {
                        "rule_type": "numeric_max",
                        "field_path": "amount",
                        "value": 100000,
                        "message": "Amount exceeds pilot limit",
                    }
                ],
                "message": "Expense creation mandate",
            },
            {
                "mandate_id": "approval-decide-pre",
                "endpoint_sig": "POST /approvals/{approval_id}/decide",
                "phase": "pre",
                "allowed_roles": ["manager"],
            },
        ],
        "autonomy": {
            "current_level": 1,
            "rules": [
                {
                    "rule_id": "expense-create-pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 0,
                },
                {
                    "rule_id": "approval-decide-pre",
                    "endpoint_sig": "POST /approvals/{approval_id}/decide",
                    "phase": "pre",
                    "required_level": 1,
                },
            ],
        },
    }


def _make_idl_v11_multi_dept() -> dict:
    """Create IDL v1.1 with dept_mandates and dept_autonomy."""
    return {
        "idl_version": "1.1",
        "system": "multi-dept",
        "version": "1.0.0",
        "departments": [{"dept_id": "finance"}, {"dept_id": "hr"}],
        "entities": [{"name": "Expense", "entity_type": "expense"}],
        "dept_mandates": {
            "finance": [
                {
                    "mandate_id": "finance-expense-pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["analyst"],
                }
            ],
            "hr": [
                {
                    "mandate_id": "hr-approval-pre",
                    "endpoint_sig": "POST /approvals/{approval_id}/decide",
                    "phase": "pre",
                    "allowed_roles": ["hr_manager"],
                }
            ],
        },
        "dept_autonomy": {
            "finance": {
                "current_level": 2,
                "rules": [
                    {
                        "rule_id": "finance-expense-pre",
                        "endpoint_sig": "POST /finance/expenses",
                        "phase": "pre",
                        "required_level": 2,
                    }
                ],
            },
            "hr": {
                "current_level": 0,
                "rules": [
                    {
                        "rule_id": "hr-approval-pre",
                        "endpoint_sig": "POST /approvals/{approval_id}/decide",
                        "phase": "pre",
                        "required_level": 0,
                    }
                ],
            },
        },
    }


def _make_idl_v10_legacy() -> dict:
    """Create IDL v1.0 (legacy)."""
    return {
        "idl_version": "1.0",
        "system": "legacy-system",
        "version": "1.0.0",
        "entities": [{"name": "Expense", "entity_type": "expense"}],
    }


# =============================================================================
# Mandates Emitter Tests
# =============================================================================


class TestMandatesEmitter:
    """Test mandates emitter."""

    def test_emit_mandates_from_idl_v11(self):
        """Emitter reflects exactly what's in IDL v1.1."""
        idl = _make_idl_v11_with_mandates_autonomy()
        parsed = parse_idl(idl)

        result = emit_mandates(parsed)

        assert result["mandate_schema_version"] == "1.0"
        assert len(result["mandates"]) == 2

        # Check first mandate
        m1 = result["mandates"][0]
        assert m1["mandate_id"] == "approval-decide-pre"  # Sorted alphabetically
        assert m1["endpoint_sig"] == "POST /approvals/{approval_id}/decide"
        assert m1["phase"] == "pre"
        assert m1["allowed_roles"] == ["manager"]

        # Check second mandate (with limits)
        m2 = result["mandates"][1]
        assert m2["mandate_id"] == "expense-create-pre"
        assert m2["message"] == "Expense creation mandate"
        assert len(m2["limits"]) == 1
        assert m2["limits"][0]["rule_type"] == "numeric_max"
        assert m2["limits"][0]["value"] == 100000

    def test_emit_mandates_v10_legacy_empty(self):
        """IDL v1.0 emits empty mandates (legacy behavior)."""
        idl = _make_idl_v10_legacy()
        parsed = parse_idl(idl)

        result = emit_mandates(parsed)

        assert result["mandate_schema_version"] == "1.0"
        assert result["mandates"] == []

    def test_emit_mandates_v11_no_mandates_defined(self):
        """IDL v1.1 without mandates emits empty list (explicit deny-all)."""
        idl = {
            "idl_version": "1.1",
            "system": "no-mandates",
            "version": "1.0.0",
            "entities": [{"name": "Expense", "entity_type": "expense"}],
        }
        parsed = parse_idl(idl)

        result = emit_mandates(parsed)

        assert result["mandate_schema_version"] == "1.0"
        assert result["mandates"] == []

    def test_emit_mandates_json_format(self):
        """emit_mandates_json returns valid JSON."""
        idl = _make_idl_v11_with_mandates_autonomy()
        parsed = parse_idl(idl)

        json_str = emit_mandates_json(parsed)
        result = json.loads(json_str)

        assert "mandate_schema_version" in result
        assert "mandates" in result

    def test_emit_mandates_multi_dept(self):
        """Multi-dept mode uses dept-specific mandates."""
        idl = _make_idl_v11_multi_dept()
        parsed = parse_idl(idl)

        # Finance dept
        finance_result = emit_mandates(parsed, dept_id="finance")
        assert len(finance_result["mandates"]) == 1
        assert finance_result["mandates"][0]["mandate_id"] == "finance-expense-pre"
        assert finance_result["mandates"][0]["allowed_roles"] == ["analyst"]

        # HR dept
        hr_result = emit_mandates(parsed, dept_id="hr")
        assert len(hr_result["mandates"]) == 1
        assert hr_result["mandates"][0]["mandate_id"] == "hr-approval-pre"
        assert hr_result["mandates"][0]["allowed_roles"] == ["hr_manager"]

    def test_emit_mandates_multi_dept_fallback_to_single(self):
        """Multi-dept with dept_id not found falls back to single mode."""
        idl = _make_idl_v11_with_mandates_autonomy()  # Has single-mode mandates
        parsed = parse_idl(idl)

        # Unknown dept_id should use single-mode mandates
        result = emit_mandates(parsed, dept_id="unknown")
        assert len(result["mandates"]) == 2  # From single mode


# =============================================================================
# Autonomy Emitter Tests
# =============================================================================


class TestAutonomyEmitter:
    """Test autonomy emitter."""

    def test_emit_autonomy_from_idl_v11(self):
        """Emitter reflects exactly what's in IDL v1.1."""
        idl = _make_idl_v11_with_mandates_autonomy()
        parsed = parse_idl(idl)

        result = emit_autonomy(parsed)

        assert result["autonomy_schema_version"] == "1.0"
        assert result["current_level"] == 1
        assert len(result["rules"]) == 2

        # Rules should be sorted by rule_id
        r1 = result["rules"][0]
        assert r1["rule_id"] == "approval-decide-pre"
        assert r1["required_level"] == 1

        r2 = result["rules"][1]
        assert r2["rule_id"] == "expense-create-pre"
        assert r2["required_level"] == 0

    def test_emit_autonomy_v10_legacy_defaults(self):
        """IDL v1.0 emits default autonomy (L0, empty rules)."""
        idl = _make_idl_v10_legacy()
        parsed = parse_idl(idl)

        result = emit_autonomy(parsed)

        assert result["autonomy_schema_version"] == "1.0"
        assert result["current_level"] == 0  # Most restrictive default
        assert result["rules"] == []

    def test_emit_autonomy_v11_no_autonomy_defined(self):
        """IDL v1.1 without autonomy emits defaults (explicit oversight-all)."""
        idl = {
            "idl_version": "1.1",
            "system": "no-autonomy",
            "version": "1.0.0",
            "entities": [{"name": "Expense", "entity_type": "expense"}],
        }
        parsed = parse_idl(idl)

        result = emit_autonomy(parsed)

        assert result["autonomy_schema_version"] == "1.0"
        assert result["current_level"] == 0  # Default to L0
        assert result["rules"] == []

    def test_emit_autonomy_json_format(self):
        """emit_autonomy_json returns valid JSON."""
        idl = _make_idl_v11_with_mandates_autonomy()
        parsed = parse_idl(idl)

        json_str = emit_autonomy_json(parsed)
        result = json.loads(json_str)

        assert "autonomy_schema_version" in result
        assert "current_level" in result
        assert "rules" in result

    def test_emit_autonomy_multi_dept(self):
        """Multi-dept mode uses dept-specific autonomy."""
        idl = _make_idl_v11_multi_dept()
        parsed = parse_idl(idl)

        # Finance dept
        finance_result = emit_autonomy(parsed, dept_id="finance")
        assert finance_result["current_level"] == 2
        assert len(finance_result["rules"]) == 1
        assert finance_result["rules"][0]["required_level"] == 2

        # HR dept
        hr_result = emit_autonomy(parsed, dept_id="hr")
        assert hr_result["current_level"] == 0
        assert len(hr_result["rules"]) == 1
        assert hr_result["rules"][0]["required_level"] == 0

    def test_emit_autonomy_multi_dept_fallback_to_single(self):
        """Multi-dept with dept_id not found falls back to single mode."""
        idl = _make_idl_v11_with_mandates_autonomy()  # Has single-mode autonomy
        parsed = parse_idl(idl)

        # Unknown dept_id should use single-mode autonomy
        result = emit_autonomy(parsed, dept_id="unknown")
        assert result["current_level"] == 1  # From single mode
        assert len(result["rules"]) == 2


# =============================================================================
# No Silent Defaults Tests
# =============================================================================


class TestNoSilentDefaults:
    """Verify no silent defaults are emitted for IDL v1.1."""

    def test_mandates_not_invented(self):
        """Emitter does not invent mandates for IDL v1.1."""
        idl = {
            "idl_version": "1.1",
            "system": "test",
            "version": "1.0.0",
            "entities": [{"name": "Expense", "entity_type": "expense"}],
            # No mandates defined - should NOT be invented
        }
        parsed = parse_idl(idl)

        result = emit_mandates(parsed)

        # Should emit empty list, not invented defaults
        assert result["mandates"] == []

    def test_autonomy_rules_not_invented(self):
        """Emitter does not invent autonomy rules for IDL v1.1."""
        idl = {
            "idl_version": "1.1",
            "system": "test",
            "version": "1.0.0",
            "entities": [{"name": "Expense", "entity_type": "expense"}],
            # No autonomy defined - should NOT be invented
        }
        parsed = parse_idl(idl)

        result = emit_autonomy(parsed)

        # Should emit empty rules, not invented defaults
        assert result["rules"] == []
        # current_level defaults to 0 (most restrictive) when not defined
        assert result["current_level"] == 0

    def test_emitters_faithful_to_idl(self):
        """Emitters output exactly matches IDL input."""
        idl = _make_idl_v11_with_mandates_autonomy()
        parsed = parse_idl(idl)

        mandates_result = emit_mandates(parsed)
        autonomy_result = emit_autonomy(parsed)

        # Count should match exactly
        assert len(mandates_result["mandates"]) == len(idl["mandates"])
        assert len(autonomy_result["rules"]) == len(idl["autonomy"]["rules"])
        assert autonomy_result["current_level"] == idl["autonomy"]["current_level"]
