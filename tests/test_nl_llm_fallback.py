"""Tests for LLM Fallback to Deterministic (Fase 5.7)."""

import json
import os
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from engine.api.server import app
from engine.nl.extractors.providers.mock import MockLLMProvider
from engine.nl.extractors.providers.base import (
    LLMError,
    LLM_TIMEOUT,
    LLM_INVALID_JSON,
    LLM_SCHEMA_INVALID,
    LLM_PROVIDER_ERROR,
)
from engine.nl.extractors.llm_adapter import LLMExtractor
from engine.nl.llm_validate import validate_llm_extraction


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_mock():
    """Reset mock provider before and after each test."""
    MockLLMProvider.reset_mock()
    yield
    MockLLMProvider.reset_mock()


class TestLLMValidation:
    """Tests for LLM response validation."""

    def test_validate_empty_response(self):
        """Empty response should fail validation."""
        is_valid, data, error_code = validate_llm_extraction("")
        assert is_valid is False
        assert error_code == "LLM_EMPTY_RESPONSE"

    def test_validate_invalid_json(self):
        """Invalid JSON should fail validation."""
        is_valid, data, error_code = validate_llm_extraction("not valid json {")
        assert is_valid is False
        assert error_code == "LLM_INVALID_JSON"

    def test_validate_missing_extraction_key(self):
        """Missing 'extraction' key should fail validation."""
        is_valid, data, error_code = validate_llm_extraction('{"other": "data"}')
        assert is_valid is False
        assert error_code == "LLM_SCHEMA_INVALID"

    def test_validate_invalid_actor_key(self):
        """Invalid actor_key format should fail validation."""
        response = json.dumps({
            "extraction": {
                "actors": [{"actor_key": "invalid-format", "name": "Test", "roles": []}],
                "entities": [],
                "policies": [],
                "workflows": [],
            }
        })
        is_valid, data, error_code = validate_llm_extraction(response)
        assert is_valid is False
        assert error_code == "LLM_SCHEMA_INVALID"

    def test_validate_invalid_policy_type(self):
        """Invalid policy_type should fail validation."""
        response = json.dumps({
            "extraction": {
                "actors": [],
                "entities": [],
                "policies": [
                    {
                        "policy_key": "policy-test-001",
                        "policy_type": "invalid_type",
                        "description": "Test",
                    }
                ],
                "workflows": [],
            }
        })
        is_valid, data, error_code = validate_llm_extraction(response)
        assert is_valid is False
        assert error_code == "LLM_SCHEMA_INVALID"

    def test_validate_valid_response(self):
        """Valid response should pass validation."""
        response = json.dumps({
            "extraction": {
                "actors": [{"actor_key": "actor-manager", "name": "Manager", "roles": ["manager"]}],
                "entities": [{"entity_key": "entity-expense", "name": "Expense", "entity_type": "expense"}],
                "policies": [
                    {
                        "policy_key": "policy-approval-001",
                        "policy_type": "approval",
                        "description": "Approval required",
                    }
                ],
                "workflows": [],
            }
        })
        is_valid, data, error_code = validate_llm_extraction(response)
        assert is_valid is True
        assert data is not None
        assert error_code is None

    def test_validate_markdown_wrapped_json(self):
        """Should handle markdown-wrapped JSON."""
        response = """```json
{
    "extraction": {
        "actors": [],
        "entities": [],
        "policies": [],
        "workflows": []
    }
}
```"""
        is_valid, data, error_code = validate_llm_extraction(response)
        assert is_valid is True


class TestLLMFallbackToDetermanistic:
    """Tests for fallback behavior when LLM fails."""

    def test_fallback_on_invalid_json(self):
        """Should fallback to deterministic on invalid JSON."""
        MockLLMProvider.set_mock_response("not valid json {{{")

        extractor = LLMExtractor(provider=MockLLMProvider())
        sir = extractor.extract("Managers must approve expenses.")

        assert extractor.extractor_used == "deterministic_fallback"
        assert extractor.last_error_code == LLM_INVALID_JSON

    def test_fallback_on_schema_invalid(self):
        """Should fallback to deterministic on invalid schema."""
        invalid_schema = json.dumps({"wrong": "schema"})
        MockLLMProvider.set_mock_response(invalid_schema)

        extractor = LLMExtractor(provider=MockLLMProvider())
        sir = extractor.extract("Managers must approve expenses.")

        assert extractor.extractor_used == "deterministic_fallback"
        assert extractor.last_error_code == LLM_SCHEMA_INVALID

    def test_fallback_on_provider_error(self):
        """Should fallback to deterministic on provider error."""
        MockLLMProvider.set_mock_error(
            LLMError(code=LLM_PROVIDER_ERROR, message="Provider failed")
        )

        extractor = LLMExtractor(provider=MockLLMProvider())
        sir = extractor.extract("Managers must approve expenses.")

        assert extractor.extractor_used == "deterministic_fallback"
        assert extractor.last_error_code == LLM_PROVIDER_ERROR

    def test_fallback_on_timeout(self):
        """Should fallback to deterministic on timeout."""
        MockLLMProvider.set_mock_error(
            LLMError(code=LLM_TIMEOUT, message="Request timed out")
        )

        extractor = LLMExtractor(provider=MockLLMProvider())
        sir = extractor.extract("Managers must approve expenses.")

        assert extractor.extractor_used == "deterministic_fallback"
        assert extractor.last_error_code == LLM_TIMEOUT

    def test_fallback_produces_valid_sir(self):
        """Fallback should produce valid SIR with policies."""
        MockLLMProvider.set_mock_response("invalid json")

        extractor = LLMExtractor(provider=MockLLMProvider())
        sir = extractor.extract("Managers must approve expenses.")

        # Should have extracted data from deterministic
        assert len(sir.extraction.actors) > 0
        assert len(sir.extraction.policies) > 0

    def test_fallback_on_exception(self):
        """Should fallback on any exception."""
        def raise_exception(prompt):
            raise RuntimeError("Unexpected error")

        MockLLMProvider.set_mock_callback(raise_exception)

        extractor = LLMExtractor(provider=MockLLMProvider())
        sir = extractor.extract("Managers must approve expenses.")

        assert extractor.extractor_used == "deterministic_fallback"


class TestLLMFallbackEndpoint:
    """Tests for fallback behavior in API endpoint."""

    def test_endpoint_fallback_on_invalid_json(self, client):
        """Endpoint should fallback and return valid SIR on invalid JSON."""
        MockLLMProvider.set_mock_response("not valid json")

        with patch.dict(os.environ, {"ENGINE_NL_EXTRACTOR": "llm", "ENGINE_NL_LLM_PROVIDER": "mock"}):
            response = client.post(
                "/nl/compile/sir",
                json={"text": "Managers must approve expenses."},
            )

        assert response.status_code == 200
        data = response.json()
        assert "sir" in data
        assert data["sir"]["meta"]["extractor_used"] == "deterministic_fallback"
        assert data["sir"]["meta"]["llm_error_code"] == LLM_INVALID_JSON

    def test_endpoint_fallback_on_schema_error(self, client):
        """Endpoint should fallback on schema validation error."""
        MockLLMProvider.set_mock_response('{"wrong": "schema"}')

        with patch.dict(os.environ, {"ENGINE_NL_EXTRACTOR": "llm", "ENGINE_NL_LLM_PROVIDER": "mock"}):
            response = client.post(
                "/nl/compile/sir",
                json={"text": "Managers must approve expenses."},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["sir"]["meta"]["extractor_used"] == "deterministic_fallback"
        assert data["sir"]["meta"]["llm_error_code"] == LLM_SCHEMA_INVALID

    def test_endpoint_fallback_on_provider_error(self, client):
        """Endpoint should fallback on provider error."""
        MockLLMProvider.set_mock_error(
            LLMError(code=LLM_PROVIDER_ERROR, message="Provider error")
        )

        with patch.dict(os.environ, {"ENGINE_NL_EXTRACTOR": "llm", "ENGINE_NL_LLM_PROVIDER": "mock"}):
            response = client.post(
                "/nl/compile/sir",
                json={"text": "Managers must approve expenses."},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["sir"]["meta"]["extractor_used"] == "deterministic_fallback"
        assert data["sir"]["meta"]["llm_error_code"] == LLM_PROVIDER_ERROR

    def test_endpoint_still_returns_valid_extraction_on_fallback(self, client):
        """Fallback should still return valid extraction with roles/entities."""
        MockLLMProvider.set_mock_error(
            LLMError(code=LLM_TIMEOUT, message="Timeout")
        )

        with patch.dict(os.environ, {"ENGINE_NL_EXTRACTOR": "llm", "ENGINE_NL_LLM_PROVIDER": "mock"}):
            response = client.post(
                "/nl/compile/sir",
                json={"text": "Managers must approve expenses created by analysts."},
            )

        assert response.status_code == 200
        data = response.json()

        # Should have extracted actors and policies from deterministic fallback
        sir = data["sir"]
        assert len(sir["extraction"]["actors"]) >= 2  # manager, analyst
        assert len(sir["extraction"]["policies"]) >= 1  # approval policy

    def test_deterministic_mode_no_fallback_metadata(self, client):
        """Deterministic mode should not include fallback metadata."""
        with patch.dict(os.environ, {"ENGINE_NL_EXTRACTOR": "deterministic"}):
            response = client.post(
                "/nl/compile/sir",
                json={"text": "Managers must approve expenses."},
            )

        assert response.status_code == 200
        data = response.json()
        # No meta field in deterministic mode
        assert "meta" not in data["sir"]
