"""Tests for NL Finalize (Fase 5.6)."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.nl.extractors.deterministic import DeterministicExtractor
from engine.nl.draft_generator import generate_draft
from engine.nl.gap_detector import detect_gaps
from engine.nl.answer_apply import apply_answers
from engine.nl.finalizer import finalize, validate_final
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


class TestFinalize:
    """Tests for finalization logic."""

    def test_finalize_returns_dict(self, sample_draft, sample_gaps):
        """finalize should return a dict."""
        # Filter out required gaps or allow gaps
        result = finalize(sample_draft, sample_gaps, allow_gaps=True)
        assert isinstance(result, dict)

    def test_finalize_has_version(self, sample_draft):
        """Final IDL should have version."""
        result = finalize(sample_draft, [], allow_gaps=False)
        assert "version" in result

    def test_finalize_has_name(self, sample_draft):
        """Final IDL should have name."""
        result = finalize(sample_draft, [], allow_gaps=False)
        assert "name" in result
        assert "draft" not in result["name"]  # Should remove 'draft-' prefix

    def test_finalize_removes_generated_from(self, sample_draft):
        """Final IDL should not have 'generated_from'."""
        result = finalize(sample_draft, [], allow_gaps=False)
        assert "generated_from" not in result

    def test_finalize_with_required_gaps_raises(self, sample_draft, sample_gaps):
        """Should raise if there are required gaps and allow_gaps is False."""
        required_gaps = [g for g in sample_gaps if g.severity == "required"]
        if not required_gaps:
            pytest.skip("No required gaps to test")

        with pytest.raises(ValueError, match="required gaps"):
            finalize(sample_draft, required_gaps, allow_gaps=False)

    def test_finalize_with_required_gaps_allowed(self, sample_draft, sample_gaps):
        """Should succeed with allow_gaps=True."""
        required_gaps = [g for g in sample_gaps if g.severity == "required"]

        if not required_gaps:
            pytest.skip("No required gaps to test")

        result = finalize(sample_draft, required_gaps, allow_gaps=True)
        assert "_warnings" in result

    def test_finalize_adds_warnings_for_remaining_gaps(self, sample_draft, sample_gaps):
        """Remaining gaps should be added as warnings."""
        result = finalize(sample_draft, sample_gaps, allow_gaps=True)

        if sample_gaps:
            assert "_warnings" in result
            assert len(result["_warnings"]) == len(sample_gaps)

    def test_finalize_deterministic(self, sample_draft):
        """Finalization should be deterministic."""
        result1 = finalize(sample_draft, [], allow_gaps=False)
        result2 = finalize(sample_draft, [], allow_gaps=False)

        import json
        json1 = json.dumps(result1, sort_keys=True)
        json2 = json.dumps(result2, sort_keys=True)
        assert json1 == json2


class TestValidateFinal:
    """Tests for final IDL validation."""

    def test_validate_valid_idl(self, sample_draft):
        """Valid IDL should pass validation."""
        idl = finalize(sample_draft, [], allow_gaps=False)
        valid, errors = validate_final(idl)

        assert valid is True
        assert len(errors) == 0

    def test_validate_missing_version(self):
        """Missing version should fail validation."""
        idl = {"name": "test", "rbac": {"roles": [{"name": "admin", "permissions": []}]}}
        valid, errors = validate_final(idl)

        assert valid is False
        assert any("version" in e for e in errors)

    def test_validate_missing_name(self):
        """Missing name should fail validation."""
        idl = {"version": "1.0", "rbac": {"roles": [{"name": "admin", "permissions": []}]}}
        valid, errors = validate_final(idl)

        assert valid is False
        assert any("name" in e for e in errors)

    def test_validate_empty_roles(self):
        """Empty roles should fail validation."""
        idl = {"version": "1.0", "name": "test", "rbac": {"roles": []}}
        valid, errors = validate_final(idl)

        assert valid is False
        assert any("roles" in e.lower() for e in errors)

    def test_validate_with_required_warnings(self):
        """Required warnings should be treated as errors."""
        idl = {
            "version": "1.0",
            "name": "test",
            "rbac": {"roles": [{"name": "admin", "permissions": []}]},
            "_warnings": [
                {"gap_key": "gap-1", "severity": "required", "description": "Test gap"}
            ],
        }
        valid, errors = validate_final(idl)

        assert valid is False
        assert any("required gap" in e.lower() for e in errors)


class TestFinalizeEndpoint:
    """Tests for POST /nl/finalize endpoint."""

    def test_finalize_endpoint_success(self, client):
        """Should finalize draft successfully."""
        sir_response = client.post(
            "/nl/compile/sir",
            json={"text": "Managers must approve expenses created by analysts."},
        )
        sir = sir_response.json()["sir"]

        draft_response = client.post(
            "/nl/compile/draft",
            json={"sir": sir},
        )
        draft = draft_response.json()["draft"]

        response = client.post(
            "/nl/finalize",
            json={
                "draft": draft,
                "remaining_gaps": [],
                "allow_gaps": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "idl" in data
        assert "valid" in data
        assert data["valid"] is True

    def test_finalize_endpoint_with_gaps_not_allowed(self, client):
        """Should fail with required gaps when allow_gaps is False."""
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

        # Filter to required gaps only
        required_gaps = [g for g in gaps if g.get("severity") == "required"]

        if not required_gaps:
            pytest.skip("No required gaps to test")

        response = client.post(
            "/nl/finalize",
            json={
                "draft": draft,
                "remaining_gaps": required_gaps,
                "allow_gaps": False,
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["detail"]["code"] == "NL_GAPS_REMAINING"

    def test_finalize_endpoint_with_gaps_allowed(self, client):
        """Should succeed with gaps when allow_gaps is True."""
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
            "/nl/finalize",
            json={
                "draft": draft,
                "remaining_gaps": gaps,
                "allow_gaps": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "idl" in data

        # Should have warnings if there were gaps
        if gaps:
            assert "_warnings" in data["idl"]


class TestFullPipeline:
    """End-to-end pipeline tests."""

    def test_full_pipeline_english(self, client):
        """Full pipeline with English text."""
        # 1. Compile to SIR
        sir_response = client.post(
            "/nl/compile/sir",
            json={"text": "Managers must approve all expenses. Users cannot approve their own expenses."},
        )
        assert sir_response.status_code == 200
        sir = sir_response.json()["sir"]

        # 2. Generate draft
        draft_response = client.post(
            "/nl/compile/draft",
            json={"sir": sir},
        )
        assert draft_response.status_code == 200
        draft = draft_response.json()["draft"]

        # 3. Detect gaps
        gaps_response = client.post(
            "/nl/gaps",
            json={"sir": sir, "draft": draft},
        )
        assert gaps_response.status_code == 200
        gaps = gaps_response.json()["gaps"]["gaps"]

        # 4. Apply answers (empty)
        apply_response = client.post(
            "/nl/answers/apply",
            json={"draft": draft, "gaps": gaps, "answers": []},
        )
        assert apply_response.status_code == 200

        # 5. Finalize (with allow_gaps)
        finalize_response = client.post(
            "/nl/finalize",
            json={
                "draft": apply_response.json()["draft"],
                "remaining_gaps": apply_response.json()["remaining_gaps"],
                "allow_gaps": True,
            },
        )
        assert finalize_response.status_code == 200

        idl = finalize_response.json()["idl"]
        assert "rbac" in idl
        assert "version" in idl

    def test_full_pipeline_portuguese(self, client):
        """Full pipeline with Portuguese text."""
        # 1. Compile to SIR
        sir_response = client.post(
            "/nl/compile/sir",
            json={
                "text": "Gerentes devem aprovar todas as despesas. Usuários não podem aprovar suas próprias despesas.",
                "language": "pt",
            },
        )
        assert sir_response.status_code == 200
        sir = sir_response.json()["sir"]
        assert sir["source"]["language"] == "pt"

        # 2. Generate draft
        draft_response = client.post(
            "/nl/compile/draft",
            json={"sir": sir},
        )
        assert draft_response.status_code == 200
        draft = draft_response.json()["draft"]

        # Should have detected manager role (translated from gerente)
        role_names = [r["name"] for r in draft.get("rbac", {}).get("roles", [])]
        assert "manager" in role_names
