"""Tests for LLM Mock Provider (Fase 5.7)."""

import json
import os
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from engine.api.server import app
from engine.nl.extractors.providers.mock import MockLLMProvider
from engine.nl.extractors.providers.base import LLMError, LLM_PROVIDER_ERROR
from engine.nl.extractors.llm_adapter import LLMExtractor


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


class TestMockLLMProvider:
    """Tests for MockLLMProvider."""

    def test_default_response_generates_valid_sir(self):
        """Default response should generate valid SIR-like structure."""
        provider = MockLLMProvider()
        response = provider.complete("Managers must approve expenses.")

        data = json.loads(response.content)
        assert "extraction" in data
        assert "actors" in data["extraction"]
        assert "entities" in data["extraction"]
        assert "policies" in data["extraction"]

    def test_mock_response_can_be_set(self):
        """Should be able to set custom mock response."""
        custom_response = json.dumps({
            "extraction": {
                "actors": [{"actor_key": "actor-custom", "name": "Custom", "roles": ["custom"]}],
                "entities": [],
                "policies": [],
                "workflows": [],
            }
        })
        MockLLMProvider.set_mock_response(custom_response)

        provider = MockLLMProvider()
        response = provider.complete("Any text")

        assert response.content == custom_response

    def test_mock_error_can_be_set(self):
        """Should be able to set mock error."""
        error = LLMError(code=LLM_PROVIDER_ERROR, message="Test error")
        MockLLMProvider.set_mock_error(error)

        provider = MockLLMProvider()
        with pytest.raises(LLMError) as exc_info:
            provider.complete("Any text")

        assert exc_info.value.code == LLM_PROVIDER_ERROR

    def test_mock_callback_can_be_set(self):
        """Should be able to set dynamic callback."""
        def callback(prompt):
            return json.dumps({"extraction": {"actors": [], "entities": [], "policies": [], "workflows": []}, "from_callback": True})

        MockLLMProvider.set_mock_callback(callback)

        provider = MockLLMProvider()
        response = provider.complete("Test prompt")
        data = json.loads(response.content)

        assert data.get("from_callback") is True

    def test_provider_name(self):
        """Provider name should be 'mock'."""
        provider = MockLLMProvider()
        assert provider.provider_name == "mock"

    def test_default_model(self):
        """Default model should be set."""
        provider = MockLLMProvider()
        assert provider.model == "mock-model-v1"

    def test_custom_model(self):
        """Should accept custom model."""
        provider = MockLLMProvider(model="custom-model")
        assert provider.model == "custom-model"


class TestLLMExtractor:
    """Tests for LLMExtractor with mock provider."""

    def test_extract_with_llm_success(self):
        """LLM extraction should succeed with valid response."""
        # Set up valid mock response
        valid_response = json.dumps({
            "extraction": {
                "actors": [
                    {"actor_key": "actor-manager", "name": "Manager", "roles": ["manager"]}
                ],
                "entities": [
                    {"entity_key": "entity-expense", "name": "Expense", "entity_type": "expense"}
                ],
                "policies": [
                    {
                        "policy_key": "policy-approval-001",
                        "policy_type": "approval",
                        "description": "Approval required",
                        "actor_refs": ["actor-manager"],
                        "entity_refs": ["entity-expense"],
                        "conditions": {},
                    }
                ],
                "workflows": [],
            }
        })
        MockLLMProvider.set_mock_response(valid_response)

        extractor = LLMExtractor(provider=MockLLMProvider())
        sir = extractor.extract("Managers must approve expenses.")

        assert extractor.extractor_used == "llm"
        assert extractor.last_error_code is None
        assert len(sir.extraction.actors) == 1
        assert sir.extraction.actors[0].actor_key == "actor-manager"

    def test_extractor_used_is_llm_on_success(self):
        """extractor_used should be 'llm' on successful extraction."""
        extractor = LLMExtractor(provider=MockLLMProvider())
        extractor.extract("Managers must approve expenses.")

        assert extractor.extractor_used == "llm"


class TestLLMEndpointWithMock:
    """Tests for /nl/compile/sir endpoint with LLM extractor."""

    def test_endpoint_with_llm_extractor(self, client):
        """Endpoint should use LLM extractor when configured."""
        # Set up valid mock response
        valid_response = json.dumps({
            "extraction": {
                "actors": [
                    {"actor_key": "actor-manager", "name": "Manager", "roles": ["manager"]}
                ],
                "entities": [
                    {"entity_key": "entity-expense", "name": "Expense", "entity_type": "expense"}
                ],
                "policies": [
                    {
                        "policy_key": "policy-approval-001",
                        "policy_type": "approval",
                        "description": "Approval required",
                        "actor_refs": [],
                        "entity_refs": [],
                        "conditions": {},
                    }
                ],
                "workflows": [],
            }
        })
        MockLLMProvider.set_mock_response(valid_response)

        with patch.dict(os.environ, {"ENGINE_NL_EXTRACTOR": "llm", "ENGINE_NL_LLM_PROVIDER": "mock"}):
            response = client.post(
                "/nl/compile/sir",
                json={"text": "Managers must approve expenses."},
            )

        assert response.status_code == 200
        data = response.json()
        assert "sir" in data
        assert data["sir"].get("meta", {}).get("extractor_used") == "llm"

    def test_endpoint_returns_extractor_used_metadata(self, client):
        """Endpoint should include extractor_used in metadata."""
        with patch.dict(os.environ, {"ENGINE_NL_EXTRACTOR": "llm", "ENGINE_NL_LLM_PROVIDER": "mock"}):
            response = client.post(
                "/nl/compile/sir",
                json={"text": "Managers must approve expenses."},
            )

        assert response.status_code == 200
        data = response.json()
        assert "meta" in data["sir"]
        assert "extractor_used" in data["sir"]["meta"]
