"""Tests for NL SIR Compilation (Fase 5.6)."""

import json
import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.nl.extractors.deterministic import DeterministicExtractor
from engine.nl.schemas.sir_v1 import SIRv1
from engine.nl.canonical import canonical_json, normalize_roles, normalize_key


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestDeterministicExtractor:
    """Tests for the deterministic keyword extractor."""

    def test_detect_language_english(self):
        """English text should be detected as 'en'."""
        extractor = DeterministicExtractor()
        text = "The manager must approve all expenses created by analysts."
        assert extractor.detect_language(text) == "en"

    def test_detect_language_portuguese(self):
        """Portuguese text should be detected as 'pt'."""
        extractor = DeterministicExtractor()
        text = "O gerente deve aprovar todas as despesas criadas por analistas."
        assert extractor.detect_language(text) == "pt"

    def test_extract_roles_english(self):
        """Should extract roles from English text."""
        extractor = DeterministicExtractor()
        text = "Managers and analysts can create expenses."
        sir = extractor.extract(text)

        actor_roles = {a.roles[0] for a in sir.extraction.actors if a.roles}
        assert "manager" in actor_roles
        assert "analyst" in actor_roles

    def test_extract_roles_portuguese(self):
        """Should extract roles from Portuguese text and translate to English."""
        extractor = DeterministicExtractor()
        text = "Gerentes e analistas podem criar despesas."
        sir = extractor.extract(text)

        actor_roles = {a.roles[0] for a in sir.extraction.actors if a.roles}
        assert "manager" in actor_roles
        assert "analyst" in actor_roles

    def test_extract_entities(self):
        """Should extract entity types."""
        extractor = DeterministicExtractor()
        text = "All expenses must be approved by a manager."
        sir = extractor.extract(text)

        entity_types = {e.entity_type for e in sir.extraction.entities}
        assert "expense" in entity_types

    def test_extract_approval_policy(self):
        """Should detect approval policy indicators."""
        extractor = DeterministicExtractor()
        text = "Expenses must be approved by a manager before processing."
        sir = extractor.extract(text)

        policy_types = {p.policy_type for p in sir.extraction.policies}
        assert "approval" in policy_types

    def test_extract_sod_policy(self):
        """Should detect SoD policy indicators."""
        extractor = DeterministicExtractor()
        text = "Users cannot approve their own expenses."
        sir = extractor.extract(text)

        policy_types = {p.policy_type for p in sir.extraction.policies}
        assert "sod" in policy_types

    def test_extract_rbac_policy(self):
        """Should detect RBAC policy indicators."""
        extractor = DeterministicExtractor()
        text = "Only managers with the approve permission can authorize expenses."
        sir = extractor.extract(text)

        policy_types = {p.policy_type for p in sir.extraction.policies}
        assert "rbac" in policy_types

    def test_extract_invariant_policy(self):
        """Should detect invariant policy indicators."""
        extractor = DeterministicExtractor()
        text = "Expenses must be at least $10 and cannot exceed $100,000."
        sir = extractor.extract(text)

        policy_types = {p.policy_type for p in sir.extraction.policies}
        assert "invariant" in policy_types

    def test_segments_created(self):
        """Should create segments from sentences."""
        extractor = DeterministicExtractor()
        text = "First sentence. Second sentence. Third sentence."
        sir = extractor.extract(text)

        assert len(sir.source.segments) == 3
        assert sir.source.segments[0].text == "First sentence"
        assert sir.source.segments[1].text == "Second sentence"

    def test_empty_input_raises_error(self):
        """Empty input should raise ValueError."""
        extractor = DeterministicExtractor()
        with pytest.raises(ValueError, match="Empty input"):
            extractor.extract("")

    def test_unsupported_language_raises_error(self):
        """Unsupported language should raise ValueError."""
        extractor = DeterministicExtractor()
        with pytest.raises(ValueError, match="Unsupported language"):
            extractor.extract("Hello world", language="fr")


class TestSIRSchema:
    """Tests for SIR schema serialization."""

    def test_sir_to_dict_roundtrip(self):
        """SIR should serialize and deserialize correctly."""
        extractor = DeterministicExtractor()
        text = "Managers must approve expenses created by analysts."
        sir = extractor.extract(text)

        sir_dict = sir.to_dict()
        sir_restored = SIRv1.from_dict(sir_dict)

        assert sir_restored.version == sir.version
        assert sir_restored.source.language == sir.source.language
        assert len(sir_restored.extraction.actors) == len(sir.extraction.actors)

    def test_sir_canonical_json_deterministic(self):
        """Canonical JSON should be deterministic."""
        extractor = DeterministicExtractor()
        text = "Managers and analysts can create expenses."

        sir1 = extractor.extract(text)
        sir2 = extractor.extract(text)

        json1 = canonical_json(sir1)
        json2 = canonical_json(sir2)

        assert json1 == json2

    def test_roles_normalized(self):
        """Roles should be lowercase and sorted."""
        roles = ["Manager", "ANALYST", "admin"]
        normalized = normalize_roles(roles)

        assert normalized == ["admin", "analyst", "manager"]

    def test_key_normalized(self):
        """Keys should be normalized correctly."""
        assert normalize_key("Hello World") == "hello_world"
        assert normalize_key("test--key") == "test_key"
        assert normalize_key("  spaces  ") == "spaces"


class TestCompileSIREndpoint:
    """Tests for POST /nl/compile/sir endpoint."""

    def test_compile_sir_success(self, client):
        """Should compile text to SIR."""
        response = client.post(
            "/nl/compile/sir",
            json={"text": "Managers must approve expenses."},
        )

        assert response.status_code == 200
        data = response.json()
        assert "sir" in data
        assert data["sir"]["version"] == "1.0"

    def test_compile_sir_with_language(self, client):
        """Should accept language hint."""
        response = client.post(
            "/nl/compile/sir",
            json={
                "text": "Gerentes devem aprovar despesas.",
                "language": "pt",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sir"]["source"]["language"] == "pt"

    def test_compile_sir_empty_text(self, client):
        """Empty text should return error."""
        response = client.post(
            "/nl/compile/sir",
            json={"text": ""},
        )

        assert response.status_code == 422

    def test_compile_sir_invalid_language(self, client):
        """Invalid language should return error."""
        response = client.post(
            "/nl/compile/sir",
            json={"text": "Hello world", "language": "fr"},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "NL_INVALID_LANGUAGE"
