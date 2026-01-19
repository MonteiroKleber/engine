"""Tests for IDL v1.1 mandates/autonomy parsing.

Covers:
- parse OK with mandates/autonomy válidos
- falha com endpoint_sig/phase inválidos
- falha com required_level fora do range
- duplicate mandate_id / rule_id detection
"""

import json
import pytest

from engine.ise.idl_parser import (
    parse_idl,
    IDLParseError,
    IDLMandate,
    IDLMandateLimit,
    IDLAutonomy,
    IDLAutonomyRule,
)
from engine.ise.errors import (
    ISE_MANDATE_INVALID,
    ISE_MANDATE_ENDPOINT_INVALID,
    ISE_MANDATE_PHASE_INVALID,
    ISE_MANDATE_RULE_TYPE_INVALID,
    ISE_MANDATE_ID_DUPLICATE,
    ISE_AUTONOMY_INVALID,
    ISE_AUTONOMY_LEVEL_INVALID,
    ISE_AUTONOMY_ENDPOINT_INVALID,
    ISE_AUTONOMY_PHASE_INVALID,
    ISE_AUTONOMY_RULE_ID_DUPLICATE,
)


# =============================================================================
# Test fixtures
# =============================================================================


def _make_valid_idl_v11_single() -> dict:
    """Create a valid IDL v1.1 with mandates/autonomy (single mode)."""
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
            }
        ],
        "autonomy": {
            "current_level": 0,
            "rules": [
                {
                    "rule_id": "expense-create-pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 0,
                }
            ],
        },
    }


def _make_valid_idl_v11_multi() -> dict:
    """Create a valid IDL v1.1 with dept_mandates/dept_autonomy (multi mode)."""
    return {
        "idl_version": "1.1",
        "system": "multi-dept-pilot",
        "version": "1.0.0",
        "departments": [{"dept_id": "finance"}],
        "entities": [{"name": "Expense", "entity_type": "expense"}],
        "dept_mandates": {
            "finance": [
                {
                    "mandate_id": "expense-create-pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["analyst"],
                }
            ]
        },
        "dept_autonomy": {
            "finance": {
                "current_level": 1,
                "rules": [
                    {
                        "rule_id": "expense-create-pre",
                        "endpoint_sig": "POST /finance/expenses",
                        "phase": "pre",
                        "required_level": 1,
                    }
                ],
            }
        },
    }


# =============================================================================
# IDL v1.1 Single Mode - Mandates
# =============================================================================


class TestMandatesParsing:
    """Test mandate parsing in IDL v1.1."""

    def test_parse_valid_mandates(self):
        """Parse valid mandates successfully."""
        idl = _make_valid_idl_v11_single()
        parsed = parse_idl(idl)

        assert parsed.idl_version == "1.1"
        assert len(parsed.mandates) == 1

        mandate = parsed.mandates[0]
        assert mandate.mandate_id == "expense-create-pre"
        assert mandate.endpoint_sig == "POST /finance/expenses"
        assert mandate.phase == "pre"
        assert mandate.allowed_roles == ["analyst", "admin"]
        assert mandate.message == "Expense creation mandate"

        assert len(mandate.limits) == 1
        limit = mandate.limits[0]
        assert limit.rule_type == "numeric_max"
        assert limit.field_path == "amount"
        assert limit.value == 100000

    def test_parse_mandate_without_limits(self):
        """Parse mandate without limits (limits are optional)."""
        idl = _make_valid_idl_v11_single()
        idl["mandates"][0].pop("limits")

        parsed = parse_idl(idl)
        assert len(parsed.mandates) == 1
        assert parsed.mandates[0].limits == []

    def test_reject_invalid_endpoint_sig(self):
        """Reject mandate with invalid endpoint_sig."""
        idl = _make_valid_idl_v11_single()
        idl["mandates"][0]["endpoint_sig"] = "GET /invalid/endpoint"

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_MANDATE_ENDPOINT_INVALID
        assert "invalid endpoint_sig" in exc_info.value.message

    def test_reject_invalid_phase(self):
        """Reject mandate with invalid phase."""
        idl = _make_valid_idl_v11_single()
        idl["mandates"][0]["phase"] = "invalid"

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_MANDATE_PHASE_INVALID
        assert "invalid phase" in exc_info.value.message

    def test_reject_invalid_rule_type(self):
        """Reject mandate with invalid limit rule_type."""
        idl = _make_valid_idl_v11_single()
        idl["mandates"][0]["limits"][0]["rule_type"] = "invalid_rule"

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_MANDATE_RULE_TYPE_INVALID
        assert "invalid rule_type" in exc_info.value.message

    def test_reject_missing_mandate_id(self):
        """Reject mandate without mandate_id."""
        idl = _make_valid_idl_v11_single()
        idl["mandates"][0].pop("mandate_id")

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_MANDATE_INVALID
        assert "missing mandate_id" in exc_info.value.message

    def test_reject_duplicate_mandate_id(self):
        """Reject duplicate mandate_id."""
        idl = _make_valid_idl_v11_single()
        # Add duplicate mandate
        idl["mandates"].append({
            "mandate_id": "expense-create-pre",  # Same ID
            "endpoint_sig": "POST /approvals/{approval_id}/decide",
            "phase": "pre",
            "allowed_roles": ["admin"],
        })

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_MANDATE_ID_DUPLICATE

    def test_allow_all_valid_rule_types(self):
        """All valid rule_types should be accepted."""
        valid_rule_types = ["numeric_max", "numeric_min", "string_max_len",
                           "required_field", "enum_allowlist"]

        for rule_type in valid_rule_types:
            idl = _make_valid_idl_v11_single()
            idl["mandates"][0]["limits"][0]["rule_type"] = rule_type

            parsed = parse_idl(idl)
            assert parsed.mandates[0].limits[0].rule_type == rule_type


# =============================================================================
# IDL v1.1 Single Mode - Autonomy
# =============================================================================


class TestAutonomyParsing:
    """Test autonomy parsing in IDL v1.1."""

    def test_parse_valid_autonomy(self):
        """Parse valid autonomy successfully."""
        idl = _make_valid_idl_v11_single()
        parsed = parse_idl(idl)

        assert parsed.autonomy is not None
        assert parsed.autonomy.current_level == 0
        assert len(parsed.autonomy.rules) == 1

        rule = parsed.autonomy.rules[0]
        assert rule.rule_id == "expense-create-pre"
        assert rule.endpoint_sig == "POST /finance/expenses"
        assert rule.phase == "pre"
        assert rule.required_level == 0

    def test_parse_autonomy_level_range(self):
        """Parse all valid autonomy levels (0-4)."""
        for level in range(5):
            idl = _make_valid_idl_v11_single()
            idl["autonomy"]["current_level"] = level
            idl["autonomy"]["rules"][0]["required_level"] = level

            parsed = parse_idl(idl)
            assert parsed.autonomy.current_level == level
            assert parsed.autonomy.rules[0].required_level == level

    def test_reject_invalid_current_level_negative(self):
        """Reject autonomy with negative current_level."""
        idl = _make_valid_idl_v11_single()
        idl["autonomy"]["current_level"] = -1

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_AUTONOMY_LEVEL_INVALID
        assert "out of range" in exc_info.value.message

    def test_reject_invalid_current_level_too_high(self):
        """Reject autonomy with current_level > 4."""
        idl = _make_valid_idl_v11_single()
        idl["autonomy"]["current_level"] = 5

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_AUTONOMY_LEVEL_INVALID
        assert "out of range" in exc_info.value.message

    def test_reject_invalid_required_level(self):
        """Reject autonomy rule with invalid required_level."""
        idl = _make_valid_idl_v11_single()
        idl["autonomy"]["rules"][0]["required_level"] = 10

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_AUTONOMY_LEVEL_INVALID

    def test_reject_invalid_autonomy_endpoint_sig(self):
        """Reject autonomy rule with invalid endpoint_sig."""
        idl = _make_valid_idl_v11_single()
        idl["autonomy"]["rules"][0]["endpoint_sig"] = "DELETE /invalid"

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_AUTONOMY_ENDPOINT_INVALID

    def test_reject_invalid_autonomy_phase(self):
        """Reject autonomy rule with invalid phase."""
        idl = _make_valid_idl_v11_single()
        idl["autonomy"]["rules"][0]["phase"] = "during"

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_AUTONOMY_PHASE_INVALID

    def test_reject_duplicate_rule_id(self):
        """Reject duplicate rule_id in autonomy rules."""
        idl = _make_valid_idl_v11_single()
        idl["autonomy"]["rules"].append({
            "rule_id": "expense-create-pre",  # Duplicate
            "endpoint_sig": "POST /approvals/{approval_id}/decide",
            "phase": "pre",
            "required_level": 0,
        })

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_AUTONOMY_RULE_ID_DUPLICATE

    def test_reject_missing_current_level(self):
        """Reject autonomy without current_level."""
        idl = _make_valid_idl_v11_single()
        idl["autonomy"].pop("current_level")

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_AUTONOMY_INVALID
        assert "missing current_level" in exc_info.value.message


# =============================================================================
# IDL v1.1 Multi-Dept Mode
# =============================================================================


class TestMultiDeptMandatesAutonomy:
    """Test dept_mandates/dept_autonomy parsing (multi mode)."""

    def test_parse_valid_dept_mandates(self):
        """Parse valid dept_mandates successfully."""
        idl = _make_valid_idl_v11_multi()
        parsed = parse_idl(idl)

        assert "finance" in parsed.dept_mandates
        assert len(parsed.dept_mandates["finance"]) == 1
        assert parsed.dept_mandates["finance"][0].mandate_id == "expense-create-pre"

    def test_parse_valid_dept_autonomy(self):
        """Parse valid dept_autonomy successfully."""
        idl = _make_valid_idl_v11_multi()
        parsed = parse_idl(idl)

        assert "finance" in parsed.dept_autonomy
        assert parsed.dept_autonomy["finance"].current_level == 1
        assert len(parsed.dept_autonomy["finance"].rules) == 1

    def test_reject_unknown_dept_in_dept_mandates(self):
        """Reject dept_mandates with unknown department."""
        idl = _make_valid_idl_v11_multi()
        idl["dept_mandates"]["unknown_dept"] = []

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert "unknown department" in exc_info.value.message

    def test_reject_unknown_dept_in_dept_autonomy(self):
        """Reject dept_autonomy with unknown department."""
        idl = _make_valid_idl_v11_multi()
        idl["dept_autonomy"]["unknown_dept"] = {"current_level": 0, "rules": []}

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert "unknown department" in exc_info.value.message

    def test_mandate_validation_per_dept(self):
        """Mandate validation errors should include dept context."""
        idl = _make_valid_idl_v11_multi()
        idl["dept_mandates"]["finance"][0]["endpoint_sig"] = "INVALID"

        with pytest.raises(IDLParseError) as exc_info:
            parse_idl(idl)

        assert exc_info.value.code == ISE_MANDATE_ENDPOINT_INVALID


# =============================================================================
# IDL v1.0 Legacy Compatibility
# =============================================================================


class TestLegacyCompatibility:
    """Test IDL v1.0 legacy behavior is preserved."""

    def test_v10_no_mandates_autonomy_parsed(self):
        """IDL v1.0 should not parse mandates/autonomy (even if present)."""
        idl = {
            "idl_version": "1.0",
            "system": "legacy-system",
            "version": "1.0.0",
            "entities": [{"name": "Expense", "entity_type": "expense"}],
            # These should be ignored for v1.0
            "mandates": [{"mandate_id": "test"}],
            "autonomy": {"current_level": 0},
        }

        parsed = parse_idl(idl)

        # v1.0 should not parse mandates/autonomy
        assert parsed.idl_version == "1.0"
        assert parsed.mandates == []
        assert parsed.autonomy is None

    def test_v10_default_idl_version(self):
        """IDL without idl_version defaults to 1.0."""
        idl = {
            "system": "no-version",
            "version": "1.0.0",
            "entities": [{"name": "Expense", "entity_type": "expense"}],
        }

        parsed = parse_idl(idl)
        assert parsed.idl_version == "1.0"


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_mandates_list(self):
        """IDL v1.1 with empty mandates list is valid."""
        idl = _make_valid_idl_v11_single()
        idl["mandates"] = []

        parsed = parse_idl(idl)
        assert parsed.mandates == []

    def test_empty_autonomy_rules(self):
        """IDL v1.1 with empty autonomy rules is valid."""
        idl = _make_valid_idl_v11_single()
        idl["autonomy"]["rules"] = []

        parsed = parse_idl(idl)
        assert parsed.autonomy.rules == []

    def test_mandate_without_message(self):
        """Mandate without message is valid."""
        idl = _make_valid_idl_v11_single()
        idl["mandates"][0].pop("message")

        parsed = parse_idl(idl)
        assert parsed.mandates[0].message is None

    def test_limit_without_value_for_required_field(self):
        """Limit with rule_type=required_field can omit value."""
        idl = _make_valid_idl_v11_single()
        idl["mandates"][0]["limits"] = [
            {
                "rule_type": "required_field",
                "field_path": "description",
            }
        ]

        parsed = parse_idl(idl)
        limit = parsed.mandates[0].limits[0]
        assert limit.rule_type == "required_field"
        assert limit.value is None

    def test_json_string_input(self):
        """Parser accepts JSON string input."""
        idl = _make_valid_idl_v11_single()
        idl_json = json.dumps(idl)

        parsed = parse_idl(idl_json)
        assert parsed.idl_version == "1.1"
        assert len(parsed.mandates) == 1
