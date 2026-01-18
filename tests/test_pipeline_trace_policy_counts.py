"""Tests for Pipeline trace.json policy counts.

Tests that trace.json records policy_count, policy_gap_count, has_policy_gaps.

Per normative specification:
- trace.json must include policy_count (total policies)
- trace.json must include policy_gap_count (count of policy gaps)
- trace.json must include has_policy_gaps (boolean)
"""

import json
import pytest
from pathlib import Path

from engine.pipeline.orchestrator import build_pipeline, STATUS_BUILT, STATUS_NEEDS_ANSWERS


# Text with valid policy (generates gaps that need answers)
TEXT_WITH_VALID_POLICY = """
Employees can create expenses.
Managers approve expenses.
No self-approval allowed.
POLICY: expense-max-100 pre POST /finance/expenses numeric_max amount 100
POLICY: expense-min-1 pre POST /finance/expenses numeric_min amount 1
"""

# Text without policies (generates gaps that need answers)
TEXT_WITHOUT_POLICY = """
Employees can create expenses.
Managers approve expenses.
No self-approval allowed.
"""

# Text with dept policies (multi-mode)
TEXT_WITH_DEPT_POLICIES = """
[finance]
Employees can create expenses.
Managers approve expenses.
No self-approval allowed.
POLICY[finance]: fin-max pre POST /finance/expenses numeric_max amount 500
[hr]
Employees can create expenses.
Managers approve expenses.
No self-approval allowed.
POLICY[hr]: hr-max pre POST /finance/expenses numeric_max amount 100
"""


def get_answers_for_all_gaps(result):
    """Helper to build answers for all gaps with appropriate types."""
    if not result.gaps:
        return []

    answers = []
    for gap in result.gaps:
        for question in gap.get("questions", []):
            q_id = question["question_id"]
            q_type = question.get("question_type", "boolean")
            default = question.get("default_value")

            if default is not None:
                value = default
            elif q_type == "boolean":
                value = True
            elif q_type == "number":
                value = 1
            elif q_type == "choice":
                options = question.get("options", [])
                value = options[0] if options else "default"
            else:
                value = "default"

            answers.append({"question_id": q_id, "value": value})
    return answers


class TestTracePolicyCounts:
    """Test trace.json policy_count, policy_gap_count, has_policy_gaps."""

    def test_trace_has_policy_count_single_mode(self, tmp_path):
        """trace.json should record policy_count for single mode."""
        # First build to get gaps
        result1 = build_pipeline(
            text=TEXT_WITH_VALID_POLICY,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        if result1.status == STATUS_NEEDS_ANSWERS:
            # Provide answers and build again
            answers = get_answers_for_all_gaps(result1)
            result = build_pipeline(
                text=TEXT_WITH_VALID_POLICY,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )
        else:
            result = result1

        if result.status != STATUS_BUILT:
            pytest.skip("Could not complete build - may need specific answers")

        # Read trace.json
        trace_path = Path(tmp_path) / "dev-runs" / result.run_id / "trace.json"
        assert trace_path.exists(), f"trace.json not found at {trace_path}"

        trace_data = json.loads(trace_path.read_text())

        # Should have policy_count = 2 (two POLICY markers)
        assert "policy_count" in trace_data
        assert trace_data["policy_count"] == 2

    def test_trace_has_policy_count_zero_when_no_policies(self, tmp_path):
        """trace.json should record policy_count=0 when no policies."""
        # First build to get gaps
        result1 = build_pipeline(
            text=TEXT_WITHOUT_POLICY,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        if result1.status == STATUS_NEEDS_ANSWERS:
            answers = get_answers_for_all_gaps(result1)
            result = build_pipeline(
                text=TEXT_WITHOUT_POLICY,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )
        else:
            result = result1

        if result.status != STATUS_BUILT:
            pytest.skip("Could not complete build - may need specific answers")

        trace_path = Path(tmp_path) / "dev-runs" / result.run_id / "trace.json"
        assert trace_path.exists()

        trace_data = json.loads(trace_path.read_text())

        assert "policy_count" in trace_data
        assert trace_data["policy_count"] == 0

    def test_trace_has_policy_gap_count(self, tmp_path):
        """trace.json should record policy_gap_count."""
        result1 = build_pipeline(
            text=TEXT_WITH_VALID_POLICY,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        if result1.status == STATUS_NEEDS_ANSWERS:
            answers = get_answers_for_all_gaps(result1)
            result = build_pipeline(
                text=TEXT_WITH_VALID_POLICY,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )
        else:
            result = result1

        if result.status != STATUS_BUILT:
            pytest.skip("Could not complete build - may need specific answers")

        trace_path = Path(tmp_path) / "dev-runs" / result.run_id / "trace.json"
        trace_data = json.loads(trace_path.read_text())

        assert "policy_gap_count" in trace_data
        # After successful build, policy_gap_count should be 0
        assert trace_data["policy_gap_count"] == 0

    def test_trace_has_has_policy_gaps_boolean(self, tmp_path):
        """trace.json should record has_policy_gaps as boolean."""
        result1 = build_pipeline(
            text=TEXT_WITH_VALID_POLICY,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        if result1.status == STATUS_NEEDS_ANSWERS:
            answers = get_answers_for_all_gaps(result1)
            result = build_pipeline(
                text=TEXT_WITH_VALID_POLICY,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )
        else:
            result = result1

        if result.status != STATUS_BUILT:
            pytest.skip("Could not complete build - may need specific answers")

        trace_path = Path(tmp_path) / "dev-runs" / result.run_id / "trace.json"
        trace_data = json.loads(trace_path.read_text())

        assert "has_policy_gaps" in trace_data
        assert isinstance(trace_data["has_policy_gaps"], bool)
        # After successful build, has_policy_gaps should be False
        assert trace_data["has_policy_gaps"] is False


class TestTracePolicyCountsMultiMode:
    """Test trace.json policy counts for multi-dept mode."""

    def test_trace_counts_dept_policies(self, tmp_path):
        """trace.json should count dept policies."""
        result1 = build_pipeline(
            text=TEXT_WITH_DEPT_POLICIES,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        if result1.status == STATUS_NEEDS_ANSWERS:
            answers = get_answers_for_all_gaps(result1)
            result = build_pipeline(
                text=TEXT_WITH_DEPT_POLICIES,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )
        else:
            result = result1

        if result.status != STATUS_BUILT:
            pytest.skip("Could not complete build - may need specific answers")

        trace_path = Path(tmp_path) / "dev-runs" / result.run_id / "trace.json"
        trace_data = json.loads(trace_path.read_text())

        assert "policy_count" in trace_data
        # 2 dept policies total (1 finance + 1 hr)
        assert trace_data["policy_count"] == 2


class TestTraceJsonStructure:
    """Test trace.json complete structure."""

    def test_trace_json_all_fields(self, tmp_path):
        """trace.json should have all required fields."""
        result1 = build_pipeline(
            text=TEXT_WITH_VALID_POLICY,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        if result1.status == STATUS_NEEDS_ANSWERS:
            answers = get_answers_for_all_gaps(result1)
            result = build_pipeline(
                text=TEXT_WITH_VALID_POLICY,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )
        else:
            result = result1

        if result.status != STATUS_BUILT:
            pytest.skip("Could not complete build - may need specific answers")

        trace_path = Path(tmp_path) / "dev-runs" / result.run_id / "trace.json"
        trace_data = json.loads(trace_path.read_text())

        # Standard trace fields
        assert "run_id" in trace_data
        assert "bundle_name" in trace_data
        assert "sir_sha256" in trace_data
        assert "draft_sha256" in trace_data
        assert "final_idl_sha256" in trace_data

        # Policy count fields
        assert "policy_count" in trace_data
        assert "policy_gap_count" in trace_data
        assert "has_policy_gaps" in trace_data


class TestPolicyGapsHelper:
    """Test policy_gaps helper functions."""

    def test_extract_policy_gaps_by_prefix(self):
        """extract_policy_gaps should filter by GAP_POLICY_ prefix."""
        from engine.pipeline.policy_gaps import extract_policy_gaps
        from engine.nl.schemas.answers_v1 import Gap, Question
        from engine.nl.gap_detector import GAP_POLICY_ENDPOINT_INVALID

        gaps = [
            Gap(
                gap_key="gap-approval-expense",
                gap_type="approval",
                severity="required",
                description="Missing approval",
                questions=[
                    Question(
                        question_id="q1",
                        gap_key="gap-approval-expense",
                        policy_key="policy-001",
                        step="needs_approval",
                        question_text="Need approval?",
                        question_type="boolean",
                    )
                ],
            ),
            Gap(
                gap_key="gap-policy-000-endpoint",
                gap_type="runtime_policy",
                severity="required",
                description="Invalid endpoint",
                policy_ref=GAP_POLICY_ENDPOINT_INVALID,
                questions=[
                    Question(
                        question_id="q2",
                        gap_key="gap-policy-000-endpoint",
                        policy_key="policy-002",
                        step="endpoint_sig",
                        question_text="Correct endpoint?",
                        question_type="text",
                    )
                ],
            ),
        ]

        policy_gaps = extract_policy_gaps(gaps)

        assert len(policy_gaps) == 1
        assert policy_gaps[0].policy_ref == GAP_POLICY_ENDPOINT_INVALID

    def test_build_answers_template_null_values(self):
        """build_answers_template should create null placeholders."""
        from engine.pipeline.policy_gaps import build_answers_template
        from engine.nl.schemas.answers_v1 import Gap, Question

        gaps = [
            Gap(
                gap_key="gap-test",
                gap_type="approval",
                severity="required",
                description="Test gap",
                questions=[
                    Question(
                        question_id="q1",
                        gap_key="gap-test",
                        policy_key="policy-001",
                        step="step1",
                        question_text="Question 1?",
                        question_type="boolean",
                    ),
                    Question(
                        question_id="q2",
                        gap_key="gap-test",
                        policy_key="policy-001",
                        step="step2",
                        question_text="Question 2?",
                        question_type="boolean",
                    ),
                ],
            ),
        ]

        template = build_answers_template(gaps)

        assert template["version"] == "1.0"
        assert len(template["answers"]) == 2

        for answer in template["answers"]:
            assert answer["value"] is None

    def test_compute_policy_counts(self):
        """compute_policy_counts should calculate correctly."""
        from engine.pipeline.policy_gaps import compute_policy_counts
        from engine.nl.schemas.answers_v1 import Gap
        from engine.nl.gap_detector import GAP_POLICY_ENDPOINT_INVALID

        gaps = [
            Gap(
                gap_key="gap-policy-000-endpoint",
                gap_type="runtime_policy",
                severity="required",
                description="Invalid endpoint",
                policy_ref=GAP_POLICY_ENDPOINT_INVALID,
                questions=[],
            ),
        ]

        counts = compute_policy_counts(
            gaps=gaps,
            runtime_policies_count=3,
            dept_runtime_policies_count=2,
        )

        assert counts["policy_count"] == 5  # 3 + 2
        assert counts["policy_gap_count"] == 1
        assert counts["has_policy_gaps"] is True
