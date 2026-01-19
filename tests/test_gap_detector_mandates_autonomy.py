"""Tests for IDL v1.1 mandate/autonomy gap detection.

Covers:
- Gaps generated when mandates/autonomy faltam para endpoints mutáveis do Finance
- No gaps when mandates/autonomy are properly defined
- Gap detection only for IDL v1.1 (not v1.0)
"""

import pytest

from engine.nl.gap_detector import (
    detect_gaps,
    _detect_mandate_gaps,
    _detect_autonomy_gaps,
    GAP_MANDATE_MISSING,
    GAP_AUTONOMY_MISSING,
    FINANCE_MUTATING_ENDPOINTS,
)
from engine.nl.schemas.sir_v1 import SIRv1, Extraction


# =============================================================================
# Test fixtures
# =============================================================================


def _make_minimal_sir() -> SIRv1:
    """Create minimal SIR for testing."""
    return SIRv1(
        version="1.0",
        extraction=Extraction(
            entities=[],
            actors=[],
            policies=[],
            runtime_policies=[],
            dept_runtime_policies={},
        ),
    )


def _make_idl_v11_without_mandates_autonomy() -> dict:
    """Create IDL v1.1 draft without mandates/autonomy."""
    return {
        "idl_version": "1.1",
        "system": "finance-pilot",
        "version": "1.0.0",
        "entities": [{"name": "Expense", "entity_type": "expense"}],
        "rbac": {"roles": [{"name": "analyst", "permissions": []}]},
        "approvals": {"rules": []},
        "sod": {"rules": []},
        # No mandates or autonomy defined
    }


def _make_idl_v11_with_complete_mandates_autonomy() -> dict:
    """Create IDL v1.1 draft with complete mandates/autonomy coverage."""
    return {
        "idl_version": "1.1",
        "system": "finance-pilot",
        "version": "1.0.0",
        "entities": [{"name": "Expense", "entity_type": "expense"}],
        "rbac": {"roles": [{"name": "analyst", "permissions": []}]},
        "mandates": [
            {
                "mandate_id": "expense-create-pre",
                "endpoint_sig": "POST /finance/expenses",
                "phase": "pre",
                "allowed_roles": ["analyst"],
            },
            {
                "mandate_id": "approval-decide-pre",
                "endpoint_sig": "POST /approvals/{approval_id}/decide",
                "phase": "pre",
                "allowed_roles": ["manager"],
            },
        ],
        "autonomy": {
            "current_level": 0,
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
                    "required_level": 0,
                },
            ],
        },
    }


def _make_idl_v10_legacy() -> dict:
    """Create IDL v1.0 draft (legacy)."""
    return {
        "idl_version": "1.0",
        "system": "legacy-system",
        "version": "1.0.0",
        "entities": [{"name": "Expense", "entity_type": "expense"}],
        "rbac": {"roles": [{"name": "analyst", "permissions": []}]},
    }


# =============================================================================
# Mandate Gap Detection Tests
# =============================================================================


class TestMandateGapDetection:
    """Test _detect_mandate_gaps function."""

    def test_detect_missing_mandates(self):
        """Gaps generated when mandates are missing."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()

        gaps = _detect_mandate_gaps(sir, draft)

        # Should have gaps for both Finance mutating endpoints
        assert len(gaps) == len(FINANCE_MUTATING_ENDPOINTS)

        gap_keys = [g.gap_key for g in gaps]
        assert any("expense" in k for k in gap_keys)
        assert any("approval" in k for k in gap_keys)

        for gap in gaps:
            assert gap.gap_type == "mandate"
            assert gap.severity == "required"
            assert gap.policy_ref == GAP_MANDATE_MISSING
            assert len(gap.questions) > 0

    def test_no_gaps_when_mandates_complete(self):
        """No gaps when all required mandates are defined."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_with_complete_mandates_autonomy()

        gaps = _detect_mandate_gaps(sir, draft)

        assert len(gaps) == 0

    def test_partial_mandate_coverage(self):
        """Gaps only for uncovered endpoints."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()
        # Add only one mandate
        draft["mandates"] = [
            {
                "mandate_id": "expense-create-pre",
                "endpoint_sig": "POST /finance/expenses",
                "phase": "pre",
                "allowed_roles": ["analyst"],
            }
        ]

        gaps = _detect_mandate_gaps(sir, draft)

        # Should have gap only for approval endpoint
        assert len(gaps) == 1
        assert "approval" in gaps[0].gap_key

    def test_mandate_questions_structure(self):
        """Gap questions have correct structure."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()

        gaps = _detect_mandate_gaps(sir, draft)

        gap = gaps[0]
        questions = gap.questions

        # Should ask about roles and amount limit
        question_steps = [q.step for q in questions]
        assert "allowed_roles" in question_steps
        assert "amount_limit" in question_steps

    def test_multi_dept_mandates_detected(self):
        """dept_mandates coverage is also detected."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()
        draft["dept_mandates"] = {
            "finance": [
                {
                    "mandate_id": "expense-create-pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "allowed_roles": ["analyst"],
                },
                {
                    "mandate_id": "approval-decide-pre",
                    "endpoint_sig": "POST /approvals/{approval_id}/decide",
                    "phase": "pre",
                    "allowed_roles": ["manager"],
                },
            ]
        }

        gaps = _detect_mandate_gaps(sir, draft)

        # All endpoints covered via dept_mandates
        assert len(gaps) == 0


# =============================================================================
# Autonomy Gap Detection Tests
# =============================================================================


class TestAutonomyGapDetection:
    """Test _detect_autonomy_gaps function."""

    def test_detect_missing_autonomy_rules(self):
        """Gaps generated when autonomy rules are missing."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()

        gaps = _detect_autonomy_gaps(sir, draft)

        # Should have gaps for both Finance mutating endpoints
        assert len(gaps) == len(FINANCE_MUTATING_ENDPOINTS)

        for gap in gaps:
            assert gap.gap_type == "autonomy"
            assert gap.severity == "required"
            assert gap.policy_ref == GAP_AUTONOMY_MISSING

    def test_no_gaps_when_autonomy_complete(self):
        """No gaps when all required autonomy rules are defined."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_with_complete_mandates_autonomy()

        gaps = _detect_autonomy_gaps(sir, draft)

        assert len(gaps) == 0

    def test_partial_autonomy_coverage(self):
        """Gaps only for uncovered endpoints."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()
        draft["autonomy"] = {
            "current_level": 0,
            "rules": [
                {
                    "rule_id": "expense-create-pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "phase": "pre",
                    "required_level": 0,
                }
            ],
        }

        gaps = _detect_autonomy_gaps(sir, draft)

        # Should have gap only for approval endpoint
        assert len(gaps) == 1
        assert "approval" in gaps[0].gap_key

    def test_autonomy_questions_structure(self):
        """Gap questions have correct structure."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()

        gaps = _detect_autonomy_gaps(sir, draft)

        gap = gaps[0]
        questions = gap.questions

        # Should ask about required level
        assert len(questions) >= 1
        assert questions[0].step == "required_level"
        assert questions[0].question_type == "choice"

    def test_multi_dept_autonomy_detected(self):
        """dept_autonomy coverage is also detected."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()
        draft["dept_autonomy"] = {
            "finance": {
                "current_level": 0,
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
                        "required_level": 0,
                    },
                ],
            }
        }

        gaps = _detect_autonomy_gaps(sir, draft)

        # All endpoints covered via dept_autonomy
        assert len(gaps) == 0


# =============================================================================
# Integration with detect_gaps
# =============================================================================


class TestDetectGapsIntegration:
    """Test mandate/autonomy detection integrated in main detect_gaps."""

    def test_v11_mandate_autonomy_gaps_detected(self):
        """IDL v1.1 without mandates/autonomy generates gaps."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()

        all_gaps = detect_gaps(sir, draft)

        mandate_gaps = [g for g in all_gaps if g.gap_type == "mandate"]
        autonomy_gaps = [g for g in all_gaps if g.gap_type == "autonomy"]

        assert len(mandate_gaps) > 0
        assert len(autonomy_gaps) > 0

    def test_v10_no_mandate_autonomy_gaps(self):
        """IDL v1.0 does NOT generate mandate/autonomy gaps."""
        sir = _make_minimal_sir()
        draft = _make_idl_v10_legacy()

        all_gaps = detect_gaps(sir, draft)

        mandate_gaps = [g for g in all_gaps if g.gap_type == "mandate"]
        autonomy_gaps = [g for g in all_gaps if g.gap_type == "autonomy"]

        # v1.0 should NOT check for mandate/autonomy
        assert len(mandate_gaps) == 0
        assert len(autonomy_gaps) == 0

    def test_complete_v11_no_mandate_autonomy_gaps(self):
        """IDL v1.1 with complete coverage has no mandate/autonomy gaps."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_with_complete_mandates_autonomy()

        all_gaps = detect_gaps(sir, draft)

        mandate_gaps = [g for g in all_gaps if g.gap_type == "mandate"]
        autonomy_gaps = [g for g in all_gaps if g.gap_type == "autonomy"]

        assert len(mandate_gaps) == 0
        assert len(autonomy_gaps) == 0

    def test_gaps_sorted_by_gap_key(self):
        """All gaps are sorted by gap_key for determinism."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()

        all_gaps = detect_gaps(sir, draft)

        gap_keys = [g.gap_key for g in all_gaps]
        assert gap_keys == sorted(gap_keys)


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases in gap detection."""

    def test_empty_mandates_list_generates_gaps(self):
        """IDL v1.1 with empty mandates list generates gaps."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()
        draft["mandates"] = []

        gaps = _detect_mandate_gaps(sir, draft)

        assert len(gaps) == len(FINANCE_MUTATING_ENDPOINTS)

    def test_empty_autonomy_rules_generates_gaps(self):
        """IDL v1.1 with empty autonomy rules generates gaps."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()
        draft["autonomy"] = {"current_level": 0, "rules": []}

        gaps = _detect_autonomy_gaps(sir, draft)

        assert len(gaps) == len(FINANCE_MUTATING_ENDPOINTS)

    def test_post_phase_not_required(self):
        """Post phase is not required for gap detection."""
        sir = _make_minimal_sir()
        draft = _make_idl_v11_without_mandates_autonomy()
        # Add only pre phase mandates
        draft["mandates"] = [
            {
                "mandate_id": "expense-create-pre",
                "endpoint_sig": "POST /finance/expenses",
                "phase": "pre",
                "allowed_roles": ["analyst"],
            },
            {
                "mandate_id": "approval-decide-pre",
                "endpoint_sig": "POST /approvals/{approval_id}/decide",
                "phase": "pre",
                "allowed_roles": ["manager"],
            },
        ]

        gaps = _detect_mandate_gaps(sir, draft)

        # No gaps - pre phase is sufficient
        assert len(gaps) == 0

    def test_null_idl_version_treated_as_v10(self):
        """IDL without idl_version treated as v1.0 (no gaps)."""
        sir = _make_minimal_sir()
        draft = {
            "system": "no-version",
            "version": "1.0.0",
            "entities": [{"name": "Expense", "entity_type": "expense"}],
        }

        all_gaps = detect_gaps(sir, draft)

        mandate_gaps = [g for g in all_gaps if g.gap_type == "mandate"]
        autonomy_gaps = [g for g in all_gaps if g.gap_type == "autonomy"]

        assert len(mandate_gaps) == 0
        assert len(autonomy_gaps) == 0
