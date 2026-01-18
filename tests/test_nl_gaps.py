"""Tests for NL Gap Detection (Fase 5.6)."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.nl.extractors.deterministic import DeterministicExtractor
from engine.nl.draft_generator import generate_draft
from engine.nl.gap_detector import detect_gaps, gaps_to_dict
from engine.nl.schemas.answers_v1 import generate_question_id


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


class TestGapDetection:
    """Tests for gap detection logic."""

    def test_detect_gaps_returns_list(self, sample_sir, sample_draft):
        """detect_gaps should return a list."""
        gaps = detect_gaps(sample_sir, sample_draft)
        assert isinstance(gaps, list)

    def test_gaps_sorted_by_gap_key(self, sample_sir, sample_draft):
        """Gaps should be sorted by gap_key."""
        gaps = detect_gaps(sample_sir, sample_draft)
        gap_keys = [g.gap_key for g in gaps]
        assert gap_keys == sorted(gap_keys)

    def test_gap_has_required_fields(self, sample_sir, sample_draft):
        """Each gap should have required fields."""
        gaps = detect_gaps(sample_sir, sample_draft)

        for gap in gaps:
            assert gap.gap_key
            assert gap.gap_type in ["approval", "sod", "identity", "auth", "invariant", "workflow"]
            assert gap.severity in ["required", "recommended", "optional"]
            assert gap.description

    def test_gap_questions_have_required_fields(self, sample_sir, sample_draft):
        """Gap questions should have required fields."""
        gaps = detect_gaps(sample_sir, sample_draft)

        for gap in gaps:
            for question in gap.questions:
                assert question.question_id
                assert question.gap_key == gap.gap_key
                assert question.step
                assert question.question_text
                assert question.question_type in ["choice", "text", "number", "boolean"]

    def test_question_id_deterministic(self):
        """Question ID generation should be deterministic."""
        id1 = generate_question_id("gap-1", "policy-1", "step-1")
        id2 = generate_question_id("gap-1", "policy-1", "step-1")
        assert id1 == id2
        assert id1.startswith("q-")

    def test_question_id_unique_per_inputs(self):
        """Different inputs should produce different question IDs."""
        id1 = generate_question_id("gap-1", "policy-1", "step-1")
        id2 = generate_question_id("gap-2", "policy-1", "step-1")
        id3 = generate_question_id("gap-1", "policy-2", "step-1")
        id4 = generate_question_id("gap-1", "policy-1", "step-2")

        assert id1 != id2
        assert id1 != id3
        assert id1 != id4


class TestGapTypes:
    """Tests for specific gap types."""

    def test_detect_auth_gap(self, sample_sir, sample_draft):
        """Should detect auth gap when no auth method specified."""
        # Remove auth from draft
        draft = dict(sample_draft)
        draft.pop("auth", None)

        gaps = detect_gaps(sample_sir, draft)
        auth_gaps = [g for g in gaps if g.gap_type == "auth"]

        assert len(auth_gaps) >= 1
        auth_gap = auth_gaps[0]
        assert auth_gap.severity == "optional"

    def test_detect_sod_gap(self, sample_sir):
        """Should detect SoD gap when no SoD rules specified."""
        # Create draft without SoD
        draft = generate_draft(sample_sir)
        draft.pop("sod", None)

        gaps = detect_gaps(sample_sir, draft)
        sod_gaps = [g for g in gaps if g.gap_type == "sod"]

        assert len(sod_gaps) >= 1


class TestGapsToDict:
    """Tests for gaps serialization."""

    def test_gaps_to_dict_format(self, sample_sir, sample_draft):
        """gaps_to_dict should return correct format."""
        gaps = detect_gaps(sample_sir, sample_draft)
        result = gaps_to_dict(gaps)

        assert "version" in result
        assert "gaps" in result
        assert isinstance(result["gaps"], list)

    def test_gaps_to_dict_sorted(self, sample_sir, sample_draft):
        """Gaps in dict should be sorted by gap_key."""
        gaps = detect_gaps(sample_sir, sample_draft)
        result = gaps_to_dict(gaps)

        gap_keys = [g["gap_key"] for g in result["gaps"]]
        assert gap_keys == sorted(gap_keys)


class TestGapsEndpoint:
    """Tests for POST /nl/gaps endpoint."""

    def test_gaps_endpoint_success(self, client):
        """Should detect gaps in draft."""
        # First get SIR
        sir_response = client.post(
            "/nl/compile/sir",
            json={"text": "Managers must approve expenses."},
        )
        sir = sir_response.json()["sir"]

        # Then get draft
        draft_response = client.post(
            "/nl/compile/draft",
            json={"sir": sir},
        )
        draft = draft_response.json()["draft"]

        # Then detect gaps
        response = client.post(
            "/nl/gaps",
            json={"sir": sir, "draft": draft},
        )

        assert response.status_code == 200
        data = response.json()
        assert "gaps" in data
        assert "version" in data["gaps"]

    def test_gaps_endpoint_invalid_sir(self, client):
        """Invalid SIR should return error."""
        response = client.post(
            "/nl/gaps",
            json={
                "sir": "not a dict",
                "draft": {"version": "1.0"},
            },
        )

        assert response.status_code == 422

    def test_gaps_endpoint_returns_questions(self, client):
        """Gaps should include questions."""
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

        # Remove auth to ensure we get a gap
        draft.pop("auth", None)

        response = client.post(
            "/nl/gaps",
            json={"sir": sir, "draft": draft},
        )

        data = response.json()
        gaps = data["gaps"]["gaps"]

        # At least one gap should have questions
        has_questions = any(len(g.get("questions", [])) > 0 for g in gaps)
        assert has_questions
