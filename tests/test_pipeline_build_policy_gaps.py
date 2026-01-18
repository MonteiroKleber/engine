"""Tests for Pipeline Build policy gaps hardening.

Tests that /pipeline/build returns policy_gaps and answers_template when NEEDS_ANSWERS.

Per normative specification:
- Cannot invent content in answers_template (values must be null)
- Policy gaps classified ONLY by prefix: policy_ref.startswith("GAP_POLICY_")
"""

import pytest
from pathlib import Path

from engine.pipeline.orchestrator import build_pipeline, STATUS_NEEDS_ANSWERS
from engine.nl.gap_detector import (
    GAP_POLICY_ID_MISSING,
    GAP_POLICY_ENDPOINT_INVALID,
    GAP_POLICY_FIELD_PATH_INVALID,
    GAP_POLICY_PHASE_INVALID,
    GAP_POLICY_RULE_TYPE_INVALID,
    GAP_POLICY_VALUE_MISSING,
)


# Text with invalid POLICY marker that will generate policy gaps
TEXT_WITH_POLICY_GAPS = """
Employees create expenses.
Managers must approve expenses.
POLICY: test-policy pre POST /invalid/endpoint numeric_max amount 100
"""

# Text with valid POLICY marker (no policy gaps, but has approval gaps)
TEXT_WITH_VALID_POLICY = """
Employees create expenses.
Employees also create reports.
Managers must approve expenses.
POLICY: expense-max pre POST /finance/expenses numeric_max amount 100
"""

# Text without POLICY markers (has approval/SoD gaps, but no policy gaps)
TEXT_WITHOUT_POLICY = """
Employees create expenses.
Employees also create reports.
Managers must approve expenses.
"""


class TestBuildPolicyGapsInResponse:
    """Test that policy_gaps is included in NEEDS_ANSWERS response."""

    def test_policy_gaps_included_when_present(self, tmp_path):
        """Build with policy gaps should include policy_gaps in response."""
        result = build_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.policy_gaps is not None
        assert len(result.policy_gaps) > 0

        # Verify all items in policy_gaps have policy_ref starting with GAP_POLICY_
        for gap in result.policy_gaps:
            assert "policy_ref" in gap
            assert gap["policy_ref"].startswith("GAP_POLICY_")

    def test_policy_gaps_contains_endpoint_invalid(self, tmp_path):
        """Invalid endpoint should be captured in policy_gaps."""
        result = build_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.policy_gaps is not None

        # Should contain GAP_POLICY_ENDPOINT_INVALID
        policy_refs = [g.get("policy_ref") for g in result.policy_gaps]
        assert GAP_POLICY_ENDPOINT_INVALID in policy_refs

    def test_policy_gaps_empty_when_no_policy_gaps(self, tmp_path):
        """Build without policy gaps should have empty policy_gaps list."""
        result = build_pipeline(
            text=TEXT_WITHOUT_POLICY,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.policy_gaps is not None
        assert len(result.policy_gaps) == 0

        # But should still have regular gaps
        assert result.gaps is not None
        assert len(result.gaps) > 0


class TestBuildAnswersTemplateInResponse:
    """Test that answers_template is included in NEEDS_ANSWERS response."""

    def test_answers_template_included(self, tmp_path):
        """NEEDS_ANSWERS should include answers_template."""
        result = build_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.answers_template is not None
        assert "version" in result.answers_template
        assert result.answers_template["version"] == "1.0"
        assert "answers" in result.answers_template

    def test_answers_template_values_are_null(self, tmp_path):
        """answers_template values must be null (not invented)."""
        result = build_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.answers_template is not None

        # All values in answers_template must be null
        for answer in result.answers_template.get("answers", []):
            assert "question_id" in answer
            assert "value" in answer
            assert answer["value"] is None, "Template values must be null, not invented"

    def test_answers_template_matches_gaps_questions(self, tmp_path):
        """answers_template should have question_ids matching gap questions."""
        result = build_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.gaps is not None
        assert result.answers_template is not None

        # Collect all question_ids from gaps
        gap_question_ids = set()
        for gap in result.gaps:
            for question in gap.get("questions", []):
                gap_question_ids.add(question["question_id"])

        # Collect all question_ids from answers_template
        template_question_ids = set(
            a["question_id"] for a in result.answers_template.get("answers", [])
        )

        # Template should match gaps
        assert template_question_ids == gap_question_ids


class TestBuildPolicyGapsSerialization:
    """Test policy_gaps and answers_template serialization via to_dict."""

    def test_to_dict_includes_policy_gaps(self, tmp_path):
        """to_dict should include policy_gaps when NEEDS_ANSWERS."""
        result = build_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        d = result.to_dict()

        assert d["status"] == STATUS_NEEDS_ANSWERS
        assert "policy_gaps" in d
        assert "answers_template" in d

    def test_to_dict_policy_gaps_structure(self, tmp_path):
        """to_dict policy_gaps should have correct structure."""
        result = build_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        d = result.to_dict()

        assert "policy_gaps" in d
        for gap in d["policy_gaps"]:
            assert "gap_key" in gap
            assert "gap_type" in gap
            assert gap["gap_type"] == "runtime_policy"
            assert "policy_ref" in gap
            assert gap["policy_ref"].startswith("GAP_POLICY_")


class TestBuildPolicyGapsViaAPI:
    """Test policy_gaps and answers_template via API endpoint."""

    def test_api_returns_policy_gaps(self, tmp_path, monkeypatch):
        """API should return policy_gaps in NEEDS_ANSWERS response."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        response = client.post(
            "/pipeline/build",
            json={
                "text": TEXT_WITH_POLICY_GAPS,
                "bundle_name": "test-bundle",
                "answers": None,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == STATUS_NEEDS_ANSWERS
        assert "policy_gaps" in data
        assert "answers_template" in data

    def test_api_answers_template_values_null(self, tmp_path, monkeypatch):
        """API answers_template values must be null."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        response = client.post(
            "/pipeline/build",
            json={
                "text": TEXT_WITH_POLICY_GAPS,
                "bundle_name": "test-bundle",
                "answers": None,
            },
        )

        assert response.status_code == 200
        data = response.json()

        for answer in data.get("answers_template", {}).get("answers", []):
            assert answer["value"] is None


class TestBuildAfterApplyAnswersStillHasGaps:
    """Test that policy_gaps/answers_template are returned after apply_answers."""

    def test_partial_answers_returns_policy_gaps(self, tmp_path):
        """After partial answers, should still return policy_gaps and template."""
        # First run to get gaps
        result1 = build_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result1.status == STATUS_NEEDS_ANSWERS
        assert result1.gaps is not None

        # Get first non-policy gap question for partial answer
        first_gap = result1.gaps[0]
        first_question = first_gap["questions"][0]

        partial_answers = [
            {"question_id": first_question["question_id"], "value": True}
        ]

        # Second run with partial answers
        result2 = build_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=partial_answers,
            bundles_root=str(tmp_path),
        )

        # If still NEEDS_ANSWERS, should have policy_gaps and answers_template
        if result2.status == STATUS_NEEDS_ANSWERS:
            assert result2.policy_gaps is not None
            assert result2.answers_template is not None
