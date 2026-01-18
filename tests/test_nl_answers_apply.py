"""Tests for NL Answers Apply (Fase 5.6)."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.nl.extractors.deterministic import DeterministicExtractor
from engine.nl.draft_generator import generate_draft
from engine.nl.gap_detector import detect_gaps
from engine.nl.answer_apply import apply_answers
from engine.nl.schemas.answers_v1 import AnswersV1, Answer, Gap


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_sir():
    """Create a sample SIR for testing."""
    extractor = DeterministicExtractor()
    text = "Managers must approve expenses created by analysts."
    return extractor.extract(text)


@pytest.fixture
def sample_draft(sample_sir):
    """Create a sample draft for testing."""
    return generate_draft(sample_sir)


@pytest.fixture
def sample_gaps(sample_sir, sample_draft):
    """Create sample gaps for testing."""
    return detect_gaps(sample_sir, sample_draft)


class TestApplyAnswers:
    """Tests for answer application logic."""

    def test_apply_answers_returns_tuple(self, sample_draft, sample_gaps):
        """apply_answers should return (draft, remaining_gaps)."""
        answers = AnswersV1()
        result = apply_answers(sample_draft, sample_gaps, answers)

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_apply_answers_empty_answers(self, sample_draft, sample_gaps):
        """Empty answers should leave all gaps remaining."""
        answers = AnswersV1()
        updated_draft, remaining_gaps = apply_answers(sample_draft, sample_gaps, answers)

        # All gaps should remain
        assert len(remaining_gaps) == len(sample_gaps)

    def test_apply_answers_reduces_gaps(self, sample_draft, sample_gaps):
        """Answering questions should reduce remaining gaps."""
        if not sample_gaps:
            pytest.skip("No gaps to test")

        # Find a gap with questions
        gap_with_questions = None
        for gap in sample_gaps:
            if gap.questions:
                gap_with_questions = gap
                break

        if not gap_with_questions:
            pytest.skip("No gaps with questions")

        # Answer all questions for this gap
        answers_list = []
        for question in gap_with_questions.questions:
            value = question.default_value
            if value is None:
                if question.question_type == "boolean":
                    value = True
                elif question.question_type == "number":
                    value = 1
                elif question.question_type == "text":
                    value = "test"
                elif question.question_type == "choice":
                    value = question.options[0] if question.options else "default"
            answers_list.append(Answer(question_id=question.question_id, value=value))

        answers = AnswersV1(answers=answers_list)
        updated_draft, remaining_gaps = apply_answers(sample_draft, sample_gaps, answers)

        # Should have fewer remaining gaps
        assert len(remaining_gaps) < len(sample_gaps)

    def test_apply_answers_unknown_question_raises(self, sample_draft, sample_gaps):
        """Unknown question ID should raise error."""
        answers = AnswersV1(answers=[
            Answer(question_id="q-unknown", value=True)
        ])

        with pytest.raises(ValueError, match="Question not found"):
            apply_answers(sample_draft, sample_gaps, answers)

    def test_apply_answers_deterministic(self, sample_draft, sample_gaps):
        """Answer application should be deterministic."""
        answers = AnswersV1()

        result1 = apply_answers(sample_draft, sample_gaps, answers)
        result2 = apply_answers(sample_draft, sample_gaps, answers)

        import json
        json1 = json.dumps(result1[0], sort_keys=True)
        json2 = json.dumps(result2[0], sort_keys=True)
        assert json1 == json2


class TestApplyAnswersToSections:
    """Tests for answer application to specific sections."""

    def test_apply_auth_answer(self, sample_draft, sample_gaps):
        """Auth method answer should be applied."""
        # Find auth gap
        auth_gap = None
        for gap in sample_gaps:
            if gap.gap_type == "auth":
                auth_gap = gap
                break

        if not auth_gap or not auth_gap.questions:
            pytest.skip("No auth gap with questions")

        # Answer auth method
        auth_question = auth_gap.questions[0]
        answers = AnswersV1(answers=[
            Answer(question_id=auth_question.question_id, value="jwt")
        ])

        updated_draft, _ = apply_answers(sample_draft, [auth_gap], answers)

        assert "auth" in updated_draft
        assert updated_draft["auth"]["method"] == "jwt"

    def test_apply_sod_answer(self, sample_draft, sample_gaps):
        """SoD answer should be applied."""
        # Find SoD gap
        sod_gap = None
        for gap in sample_gaps:
            if gap.gap_type == "sod":
                sod_gap = gap
                break

        if not sod_gap or not sod_gap.questions:
            pytest.skip("No SoD gap with questions")

        # Answer SoD question
        sod_question = sod_gap.questions[0]
        answers = AnswersV1(answers=[
            Answer(question_id=sod_question.question_id, value=True)
        ])

        updated_draft, _ = apply_answers(sample_draft, [sod_gap], answers)

        assert "sod" in updated_draft
        assert len(updated_draft["sod"]["rules"]) > 0


class TestAnswersApplyEndpoint:
    """Tests for POST /nl/answers/apply endpoint."""

    def test_apply_endpoint_success(self, client):
        """Should apply answers successfully."""
        # Build pipeline
        sir_response = client.post(
            "/nl/compile/sir",
            json={"text": "Managers must approve expenses."},
        )
        sir = sir_response.json()["sir"]

        draft_response = client.post(
            "/nl/compile/draft",
            json={"sir": sir},
        )
        draft = draft_response.json()["draft"]

        gaps_response = client.post(
            "/nl/gaps",
            json={"sir": sir, "draft": draft},
        )
        gaps = gaps_response.json()["gaps"]["gaps"]

        # Apply empty answers
        response = client.post(
            "/nl/answers/apply",
            json={
                "draft": draft,
                "gaps": gaps,
                "answers": [],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "draft" in data
        assert "remaining_gaps" in data

    def test_apply_endpoint_with_answers(self, client):
        """Should apply answers and update draft."""
        sir_response = client.post(
            "/nl/compile/sir",
            json={"text": "Managers must approve expenses."},
        )
        sir = sir_response.json()["sir"]

        draft_response = client.post(
            "/nl/compile/draft",
            json={"sir": sir},
        )
        draft = draft_response.json()["draft"]

        gaps_response = client.post(
            "/nl/gaps",
            json={"sir": sir, "draft": draft},
        )
        gaps = gaps_response.json()["gaps"]["gaps"]

        if not gaps:
            pytest.skip("No gaps to apply answers to")

        # Find a question to answer
        question_id = None
        for gap in gaps:
            if gap.get("questions"):
                question_id = gap["questions"][0]["question_id"]
                break

        if not question_id:
            pytest.skip("No questions in gaps")

        response = client.post(
            "/nl/answers/apply",
            json={
                "draft": draft,
                "gaps": gaps,
                "answers": [{"question_id": question_id, "value": True}],
            },
        )

        assert response.status_code == 200

    def test_apply_endpoint_invalid_question(self, client):
        """Invalid question ID should return error."""
        sir_response = client.post(
            "/nl/compile/sir",
            json={"text": "Managers must approve expenses."},
        )
        sir = sir_response.json()["sir"]

        draft_response = client.post(
            "/nl/compile/draft",
            json={"sir": sir},
        )
        draft = draft_response.json()["draft"]

        gaps_response = client.post(
            "/nl/gaps",
            json={"sir": sir, "draft": draft},
        )
        gaps = gaps_response.json()["gaps"]["gaps"]

        response = client.post(
            "/nl/answers/apply",
            json={
                "draft": draft,
                "gaps": gaps,
                "answers": [{"question_id": "q-invalid", "value": True}],
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "NL_QUESTION_NOT_FOUND"
