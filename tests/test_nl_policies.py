"""Tests for NL Pipeline Policies Support (v1.1 Runtime Policies).

Tests for:
- Extractor with POLICY marker extraction
- Draft generator policy output
- Gap detector policy validation gaps
- Answer apply for policy gaps
- Finalizer policy validation
"""

import pytest
from typing import Dict, Any, List

from engine.nl.extractors.deterministic import DeterministicExtractor
from engine.nl.schemas.sir_v1 import SIRv1, RuntimePolicy, Extraction
from engine.nl.draft_generator import generate_draft
from engine.nl.gap_detector import (
    detect_gaps,
    GAP_POLICY_ID_MISSING,
    GAP_POLICY_ENDPOINT_INVALID,
    GAP_POLICY_FIELD_PATH_INVALID,
    GAP_POLICY_PHASE_INVALID,
    GAP_POLICY_RULE_TYPE_INVALID,
    GAP_POLICY_VALUE_MISSING,
)
from engine.nl.schemas.answers_v1 import AnswersV1, Answer, Gap, Question
from engine.nl.answer_apply import apply_answers
from engine.nl.finalizer import finalize, NLPolicyValidationError
from engine.nl.errors import NL_POLICY_INVALID


class TestExtractorPolicyMarker:
    """Tests for POLICY marker extraction in DeterministicExtractor."""

    def test_no_policy_marker_extracts_no_runtime_policies(self):
        """Text without POLICY marker should NOT extract runtime policies."""
        extractor = DeterministicExtractor()
        text = """
        All expenses must be approved by a manager.
        Maximum expense amount is $100.
        """
        sir = extractor.extract(text)

        # Should NOT have runtime_policies (no explicit POLICY marker)
        assert sir.extraction.runtime_policies == []
        assert sir.extraction.dept_runtime_policies == {}

    def test_extract_single_policy_marker(self):
        """Should extract policy from explicit POLICY marker."""
        extractor = DeterministicExtractor()
        text = """
        POLICY: expense-max-100 pre POST /finance/expenses numeric_max amount 100
        """
        sir = extractor.extract(text)

        assert len(sir.extraction.runtime_policies) == 1
        policy = sir.extraction.runtime_policies[0]
        assert policy.policy_id == "expense-max-100"
        assert policy.phase == "pre"
        assert policy.endpoint_sig == "POST /finance/expenses"
        assert policy.rule_type == "numeric_max"
        assert policy.field_path == "amount"
        assert policy.value == 100

    def test_extract_multiple_policy_markers(self):
        """Should extract multiple policies from multiple POLICY markers."""
        extractor = DeterministicExtractor()
        text = """
        POLICY: expense-max-100 pre POST /finance/expenses numeric_max amount 100
        POLICY: expense-min-1 pre POST /finance/expenses numeric_min amount 1
        POLICY: desc-required pre POST /finance/expenses required_field description
        """
        sir = extractor.extract(text)

        assert len(sir.extraction.runtime_policies) == 3
        policy_ids = {p.policy_id for p in sir.extraction.runtime_policies}
        assert policy_ids == {"expense-max-100", "expense-min-1", "desc-required"}

    def test_extract_policy_with_message(self):
        """Should extract policy with custom message."""
        extractor = DeterministicExtractor()
        text = """
        POLICY: expense-max-100 pre POST /finance/expenses numeric_max amount 100 "Amount cannot exceed 100"
        """
        sir = extractor.extract(text)

        assert len(sir.extraction.runtime_policies) == 1
        policy = sir.extraction.runtime_policies[0]
        assert policy.value == 100
        assert policy.message == "Amount cannot exceed 100"

    def test_extract_policy_string_max_len(self):
        """Should extract string_max_len policy."""
        extractor = DeterministicExtractor()
        text = """
        POLICY: desc-len-280 pre POST /finance/expenses string_max_len description 280
        """
        sir = extractor.extract(text)

        assert len(sir.extraction.runtime_policies) == 1
        policy = sir.extraction.runtime_policies[0]
        assert policy.rule_type == "string_max_len"
        assert policy.field_path == "description"
        assert policy.value == 280

    def test_extract_policy_required_field(self):
        """Should extract required_field policy (no value needed)."""
        extractor = DeterministicExtractor()
        text = """
        POLICY: amount-required pre POST /finance/expenses required_field amount
        """
        sir = extractor.extract(text)

        assert len(sir.extraction.runtime_policies) == 1
        policy = sir.extraction.runtime_policies[0]
        assert policy.rule_type == "required_field"
        assert policy.field_path == "amount"
        assert policy.value is None

    def test_extract_dept_policy_marker(self):
        """Should extract dept-prefixed policy for multi-dept mode."""
        extractor = DeterministicExtractor()
        text = """
        POLICY[finance]: fin-max-500 pre POST /finance/expenses numeric_max amount 500
        POLICY[hr]: hr-max-100 pre POST /finance/expenses numeric_max amount 100
        """
        sir = extractor.extract(text)

        assert len(sir.extraction.runtime_policies) == 0  # No single-mode policies
        assert "finance" in sir.extraction.dept_runtime_policies
        assert "hr" in sir.extraction.dept_runtime_policies
        assert len(sir.extraction.dept_runtime_policies["finance"]) == 1
        assert len(sir.extraction.dept_runtime_policies["hr"]) == 1

        fin_policy = sir.extraction.dept_runtime_policies["finance"][0]
        assert fin_policy.policy_id == "fin-max-500"
        assert fin_policy.value == 500

    def test_extract_mixed_single_and_dept_policies(self):
        """Should handle both single-mode and multi-dept policies."""
        extractor = DeterministicExtractor()
        text = """
        POLICY: global-max pre POST /finance/expenses numeric_max amount 1000
        POLICY[finance]: fin-max pre POST /finance/expenses numeric_max amount 500
        """
        sir = extractor.extract(text)

        assert len(sir.extraction.runtime_policies) == 1
        assert sir.extraction.runtime_policies[0].policy_id == "global-max"

        assert len(sir.extraction.dept_runtime_policies) == 1
        assert sir.extraction.dept_runtime_policies["finance"][0].policy_id == "fin-max"

    def test_policy_marker_case_insensitive(self):
        """POLICY marker should be case-insensitive."""
        extractor = DeterministicExtractor()
        text = """
        policy: expense-max post POST /finance/expenses numeric_max amount 100
        """
        sir = extractor.extract(text)

        assert len(sir.extraction.runtime_policies) == 1
        policy = sir.extraction.runtime_policies[0]
        assert policy.policy_id == "expense-max"
        assert policy.phase == "post"

    def test_invalid_policy_marker_ignored(self):
        """Malformed POLICY markers should be ignored (not extracted)."""
        extractor = DeterministicExtractor()
        text = """
        POLICY: only-id
        POLICY: missing-parts pre
        Regular text with expense and manager keywords.
        """
        sir = extractor.extract(text)

        # Invalid markers should be ignored
        assert len(sir.extraction.runtime_policies) == 0


class TestDraftGeneratorPolicies:
    """Tests for draft generator policy output."""

    def test_draft_includes_runtime_policies(self):
        """Draft should include extracted runtime policies."""
        sir = SIRv1(
            extraction=Extraction(
                runtime_policies=[
                    RuntimePolicy(
                        policy_id="expense-max-100",
                        phase="pre",
                        endpoint_sig="POST /finance/expenses",
                        rule_type="numeric_max",
                        field_path="amount",
                        value=100,
                    ),
                ],
                # Need at least one policy for draft to be valid
                policies=[],
            )
        )
        # Add a fake policy so generate_draft doesn't fail
        from engine.nl.schemas.sir_v1 import Policy
        sir.extraction.policies.append(Policy(
            policy_key="policy-approval-001",
            policy_type="approval",
            description="Test policy",
        ))

        draft = generate_draft(sir)

        assert "policies" in draft
        assert len(draft["policies"]) == 1
        assert draft["policies"][0]["policy_id"] == "expense-max-100"
        assert draft["policies"][0]["value"] == 100

    def test_draft_includes_dept_runtime_policies(self):
        """Draft should include dept runtime policies for multi-dept mode."""
        sir = SIRv1(
            extraction=Extraction(
                dept_runtime_policies={
                    "finance": [
                        RuntimePolicy(
                            policy_id="fin-max",
                            phase="pre",
                            endpoint_sig="POST /finance/expenses",
                            rule_type="numeric_max",
                            field_path="amount",
                            value=500,
                        ),
                    ],
                },
                policies=[],
            )
        )
        # Add a fake policy so generate_draft doesn't fail
        from engine.nl.schemas.sir_v1 import Policy
        sir.extraction.policies.append(Policy(
            policy_key="policy-approval-001",
            policy_type="approval",
            description="Test policy",
        ))

        draft = generate_draft(sir)

        assert "dept_policies" in draft
        assert "finance" in draft["dept_policies"]
        assert len(draft["dept_policies"]["finance"]) == 1


class TestGapDetectorPolicies:
    """Tests for gap detector policy validation."""

    def test_valid_policy_no_gaps(self):
        """Valid policy should not generate gaps."""
        sir = SIRv1(
            extraction=Extraction(
                runtime_policies=[
                    RuntimePolicy(
                        policy_id="expense-max-100",
                        phase="pre",
                        endpoint_sig="POST /finance/expenses",
                        rule_type="numeric_max",
                        field_path="amount",
                        value=100,
                    ),
                ],
            )
        )
        draft = {"policies": []}

        gaps = detect_gaps(sir, draft)

        # Filter only runtime_policy gaps
        policy_gaps = [g for g in gaps if g.gap_type == "runtime_policy"]
        assert len(policy_gaps) == 0

    def test_invalid_endpoint_creates_gap(self):
        """Invalid endpoint_sig should create GAP_POLICY_ENDPOINT_INVALID."""
        sir = SIRv1(
            extraction=Extraction(
                runtime_policies=[
                    RuntimePolicy(
                        policy_id="test-policy",
                        phase="pre",
                        endpoint_sig="POST /invalid/endpoint",  # Invalid
                        rule_type="numeric_max",
                        field_path="amount",
                        value=100,
                    ),
                ],
            )
        )
        draft = {}

        gaps = detect_gaps(sir, draft)

        policy_gaps = [g for g in gaps if g.gap_type == "runtime_policy"]
        assert len(policy_gaps) == 1
        assert policy_gaps[0].policy_ref == GAP_POLICY_ENDPOINT_INVALID

    def test_invalid_phase_creates_gap(self):
        """Invalid phase should create GAP_POLICY_PHASE_INVALID."""
        sir = SIRv1(
            extraction=Extraction(
                runtime_policies=[
                    RuntimePolicy(
                        policy_id="test-policy",
                        phase="invalid",  # Invalid
                        endpoint_sig="POST /finance/expenses",
                        rule_type="numeric_max",
                        field_path="amount",
                        value=100,
                    ),
                ],
            )
        )
        draft = {}

        gaps = detect_gaps(sir, draft)

        policy_gaps = [g for g in gaps if g.gap_type == "runtime_policy"]
        endpoint_gaps = [g for g in policy_gaps if g.policy_ref == GAP_POLICY_PHASE_INVALID]
        assert len(endpoint_gaps) == 1

    def test_invalid_rule_type_creates_gap(self):
        """Invalid rule_type should create GAP_POLICY_RULE_TYPE_INVALID."""
        sir = SIRv1(
            extraction=Extraction(
                runtime_policies=[
                    RuntimePolicy(
                        policy_id="test-policy",
                        phase="pre",
                        endpoint_sig="POST /finance/expenses",
                        rule_type="invalid_rule",  # Invalid
                        field_path="amount",
                        value=100,
                    ),
                ],
            )
        )
        draft = {}

        gaps = detect_gaps(sir, draft)

        policy_gaps = [g for g in gaps if g.gap_type == "runtime_policy"]
        rule_gaps = [g for g in policy_gaps if g.policy_ref == GAP_POLICY_RULE_TYPE_INVALID]
        assert len(rule_gaps) == 1

    def test_invalid_field_path_creates_gap(self):
        """Invalid field_path should create GAP_POLICY_FIELD_PATH_INVALID."""
        sir = SIRv1(
            extraction=Extraction(
                runtime_policies=[
                    RuntimePolicy(
                        policy_id="test-policy",
                        phase="pre",
                        endpoint_sig="POST /finance/expenses",
                        rule_type="numeric_max",
                        field_path="..invalid",  # Invalid
                        value=100,
                    ),
                ],
            )
        )
        draft = {}

        gaps = detect_gaps(sir, draft)

        policy_gaps = [g for g in gaps if g.gap_type == "runtime_policy"]
        field_gaps = [g for g in policy_gaps if g.policy_ref == GAP_POLICY_FIELD_PATH_INVALID]
        assert len(field_gaps) == 1

    def test_missing_value_creates_gap(self):
        """Missing value for numeric rules should create GAP_POLICY_VALUE_MISSING."""
        sir = SIRv1(
            extraction=Extraction(
                runtime_policies=[
                    RuntimePolicy(
                        policy_id="test-policy",
                        phase="pre",
                        endpoint_sig="POST /finance/expenses",
                        rule_type="numeric_max",
                        field_path="amount",
                        value=None,  # Missing value
                    ),
                ],
            )
        )
        draft = {}

        gaps = detect_gaps(sir, draft)

        policy_gaps = [g for g in gaps if g.gap_type == "runtime_policy"]
        value_gaps = [g for g in policy_gaps if g.policy_ref == GAP_POLICY_VALUE_MISSING]
        assert len(value_gaps) == 1

    def test_required_field_no_value_gap(self):
        """required_field rule type should NOT require a value."""
        sir = SIRv1(
            extraction=Extraction(
                runtime_policies=[
                    RuntimePolicy(
                        policy_id="test-policy",
                        phase="pre",
                        endpoint_sig="POST /finance/expenses",
                        rule_type="required_field",
                        field_path="amount",
                        value=None,  # No value needed
                    ),
                ],
            )
        )
        draft = {}

        gaps = detect_gaps(sir, draft)

        policy_gaps = [g for g in gaps if g.gap_type == "runtime_policy"]
        assert len(policy_gaps) == 0


class TestAnswerApplyPolicies:
    """Tests for answer_apply handling of policy gaps."""

    def test_apply_endpoint_answer(self):
        """Should apply endpoint_sig answer to draft."""
        draft = {
            "policies": [
                {
                    "policy_id": "test-policy",
                    "phase": "pre",
                    "endpoint_sig": "invalid",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 100,
                }
            ]
        }
        gap = Gap(
            gap_key="gap-policy-000-endpoint",
            gap_type="runtime_policy",
            severity="required",
            description="Invalid endpoint",
            policy_ref=GAP_POLICY_ENDPOINT_INVALID,
            questions=[
                Question(
                    question_id="q-test",
                    gap_key="gap-policy-000-endpoint",
                    policy_key=GAP_POLICY_ENDPOINT_INVALID,
                    step="endpoint_sig",
                    question_text="Select endpoint",
                    question_type="choice",
                )
            ],
        )
        answers = AnswersV1(answers=[
            Answer(question_id="q-test", value="POST /finance/expenses")
        ])

        updated_draft, remaining = apply_answers(draft, [gap], answers)

        assert updated_draft["policies"][0]["endpoint_sig"] == "POST /finance/expenses"
        assert len(remaining) == 0


class TestFinalizerPolicies:
    """Tests for finalizer policy validation."""

    def test_finalize_valid_policy(self):
        """Valid policy should finalize successfully."""
        draft = {
            "version": "1.0",
            "name": "test",
            "rbac": {"version": "1.0", "name": "rbac", "roles": []},
            "policies": [
                {
                    "policy_id": "expense-max-100",
                    "phase": "pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 100,
                }
            ],
        }

        final = finalize(draft, [])

        assert "policies" in final
        assert final["policies"][0]["policy_id"] == "expense-max-100"

    def test_finalize_invalid_policy_raises_error(self):
        """Invalid policy should raise NLPolicyValidationError."""
        draft = {
            "version": "1.0",
            "name": "test",
            "rbac": {"version": "1.0", "name": "rbac", "roles": []},
            "policies": [
                {
                    "policy_id": "test-policy",
                    "phase": "invalid",  # Invalid phase
                    "endpoint_sig": "POST /finance/expenses",
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 100,
                }
            ],
        }

        with pytest.raises(NLPolicyValidationError) as exc_info:
            finalize(draft, [])

        assert exc_info.value.code == NL_POLICY_INVALID
        assert len(exc_info.value.details) == 1
        assert exc_info.value.details[0]["code"] == "PHASE_INVALID"

    def test_finalize_multiple_policy_errors(self):
        """Multiple invalid policies should report all errors."""
        draft = {
            "version": "1.0",
            "name": "test",
            "rbac": {"version": "1.0", "name": "rbac", "roles": []},
            "policies": [
                {
                    "policy_id": "test-1",
                    "phase": "invalid",  # Invalid
                    "endpoint_sig": "POST /invalid",  # Invalid
                    "rule_type": "numeric_max",
                    "field_path": "amount",
                    "value": 100,
                },
                {
                    "policy_id": "test-2",
                    "phase": "pre",
                    "endpoint_sig": "POST /finance/expenses",
                    "rule_type": "bad_rule",  # Invalid
                    "field_path": "..bad",  # Invalid
                    "value": 100,
                },
            ],
        }

        with pytest.raises(NLPolicyValidationError) as exc_info:
            finalize(draft, [])

        # Should have errors for both policies
        assert len(exc_info.value.details) >= 4

    def test_finalize_dept_policies_validation(self):
        """Dept policies should also be validated."""
        draft = {
            "version": "1.0",
            "name": "test",
            "rbac": {"version": "1.0", "name": "rbac", "roles": []},
            "dept_policies": {
                "finance": [
                    {
                        "policy_id": "fin-policy",
                        "phase": "invalid",  # Invalid
                        "endpoint_sig": "POST /finance/expenses",
                        "rule_type": "numeric_max",
                        "field_path": "amount",
                        "value": 100,
                    }
                ],
            },
        }

        with pytest.raises(NLPolicyValidationError) as exc_info:
            finalize(draft, [])

        assert exc_info.value.code == NL_POLICY_INVALID
        # Error should mention dept:finance
        assert any("dept:finance" in e.get("message", "") for e in exc_info.value.details)


class TestEndToEndPolicyFlow:
    """End-to-end tests for the complete policy extraction flow."""

    def test_full_flow_valid_policy(self):
        """Complete flow: extract -> draft -> gaps -> finalize (valid policy)."""
        # Step 1: Extract
        extractor = DeterministicExtractor()
        text = """
        Expenses must be approved by a manager.
        POLICY: expense-max-100 pre POST /finance/expenses numeric_max amount 100
        """
        sir = extractor.extract(text)

        assert len(sir.extraction.runtime_policies) == 1

        # Step 2: Generate draft
        draft = generate_draft(sir)

        assert "policies" in draft
        assert len(draft["policies"]) == 1

        # Step 3: Detect gaps (should be none for valid policy)
        gaps = detect_gaps(sir, draft)
        policy_gaps = [g for g in gaps if g.gap_type == "runtime_policy"]
        assert len(policy_gaps) == 0

        # Step 4: Finalize
        final = finalize(draft, gaps, allow_gaps=True)

        assert "policies" in final
        assert final["policies"][0]["policy_id"] == "expense-max-100"

    def test_full_flow_invalid_policy_with_gap_resolution(self):
        """Flow with invalid policy that gets fixed via gap answers."""
        # Create SIR with invalid policy
        sir = SIRv1(
            extraction=Extraction(
                runtime_policies=[
                    RuntimePolicy(
                        policy_id="test-policy",
                        phase="pre",
                        endpoint_sig="POST /invalid/endpoint",  # Invalid
                        rule_type="numeric_max",
                        field_path="amount",
                        value=100,
                    ),
                ],
                policies=[],
            )
        )
        # Add fake policy for draft generation
        from engine.nl.schemas.sir_v1 import Policy
        sir.extraction.policies.append(Policy(
            policy_key="policy-approval-001",
            policy_type="approval",
            description="Test policy",
        ))

        # Generate draft
        draft = generate_draft(sir)

        # Detect gaps
        gaps = detect_gaps(sir, draft)
        policy_gaps = [g for g in gaps if g.gap_type == "runtime_policy"]
        assert len(policy_gaps) == 1
        assert policy_gaps[0].policy_ref == GAP_POLICY_ENDPOINT_INVALID

        # Apply answer to fix the endpoint
        answers = AnswersV1(answers=[
            Answer(
                question_id=policy_gaps[0].questions[0].question_id,
                value="POST /finance/expenses"
            )
        ])
        updated_draft, remaining = apply_answers(draft, policy_gaps, answers)

        # The draft should now have the corrected endpoint
        assert updated_draft["policies"][0]["endpoint_sig"] == "POST /finance/expenses"

    def test_no_policy_without_marker(self):
        """Text describing limits but without POLICY marker should NOT create runtime policy."""
        extractor = DeterministicExtractor()
        text = """
        All expenses have a maximum limit of $100.
        The manager must approve expenses over $50.
        """
        sir = extractor.extract(text)

        # Should NOT have runtime_policies
        assert len(sir.extraction.runtime_policies) == 0
        # But may have regular policies (approval, invariant)
        assert len(sir.extraction.policies) >= 0  # May have detected policies from keywords


class TestSIRSerialization:
    """Tests for SIR serialization with runtime policies."""

    def test_runtime_policy_to_dict(self):
        """RuntimePolicy should serialize correctly."""
        policy = RuntimePolicy(
            policy_id="test",
            phase="pre",
            endpoint_sig="POST /finance/expenses",
            rule_type="numeric_max",
            field_path="amount",
            value=100,
            message="Max is 100",
        )

        d = policy.to_dict()

        assert d["policy_id"] == "test"
        assert d["phase"] == "pre"
        assert d["value"] == 100
        assert d["message"] == "Max is 100"

    def test_runtime_policy_from_dict(self):
        """RuntimePolicy should deserialize correctly."""
        d = {
            "policy_id": "test",
            "phase": "post",
            "endpoint_sig": "POST /approvals/{approval_id}/decide",
            "rule_type": "required_field",
            "field_path": "decision",
        }

        policy = RuntimePolicy.from_dict(d)

        assert policy.policy_id == "test"
        assert policy.phase == "post"
        assert policy.value is None

    def test_extraction_with_runtime_policies_roundtrip(self):
        """Extraction with runtime policies should roundtrip through dict."""
        extraction = Extraction(
            runtime_policies=[
                RuntimePolicy(
                    policy_id="test",
                    phase="pre",
                    endpoint_sig="POST /finance/expenses",
                    rule_type="numeric_max",
                    field_path="amount",
                    value=100,
                ),
            ],
            dept_runtime_policies={
                "finance": [
                    RuntimePolicy(
                        policy_id="fin-test",
                        phase="post",
                        endpoint_sig="POST /approvals/{approval_id}/decide",
                        rule_type="required_field",
                        field_path="decision",
                    ),
                ],
            },
        )

        d = extraction.to_dict()
        restored = Extraction.from_dict(d)

        assert len(restored.runtime_policies) == 1
        assert restored.runtime_policies[0].policy_id == "test"
        assert len(restored.dept_runtime_policies) == 1
        assert "finance" in restored.dept_runtime_policies
