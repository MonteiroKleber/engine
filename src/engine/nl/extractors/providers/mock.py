"""Mock LLM Provider for testing."""

import json
from typing import Optional, Dict, Any, Callable

from .base import (
    BaseLLMProvider,
    LLMResponse,
    LLMError,
    LLM_TIMEOUT,
    LLM_PROVIDER_ERROR,
)


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider for testing and development."""

    # Class-level mock response for testing
    _mock_response: Optional[str] = None
    _mock_error: Optional[LLMError] = None
    _mock_callback: Optional[Callable[[str], str]] = None

    def __init__(
        self,
        model: Optional[str] = None,
        timeout_ms: int = 8000,
        **kwargs: Any,
    ):
        super().__init__(model, timeout_ms, **kwargs)

    def default_model(self) -> str:
        return "mock-model-v1"

    @classmethod
    def set_mock_response(cls, response: str) -> None:
        """Set mock response for testing."""
        cls._mock_response = response
        cls._mock_error = None
        cls._mock_callback = None

    @classmethod
    def set_mock_error(cls, error: LLMError) -> None:
        """Set mock error for testing."""
        cls._mock_error = error
        cls._mock_response = None
        cls._mock_callback = None

    @classmethod
    def set_mock_callback(cls, callback: Callable[[str], str]) -> None:
        """Set mock callback for dynamic responses."""
        cls._mock_callback = callback
        cls._mock_response = None
        cls._mock_error = None

    @classmethod
    def reset_mock(cls) -> None:
        """Reset all mock state."""
        cls._mock_response = None
        cls._mock_error = None
        cls._mock_callback = None

    def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        """Return mock completion.

        Args:
            prompt: User prompt.
            system: Optional system prompt.

        Returns:
            LLMResponse with mock completion.

        Raises:
            LLMError: If mock error is set.
        """
        # Check for mock error
        if self._mock_error is not None:
            raise self._mock_error

        # Check for callback
        if MockLLMProvider._mock_callback is not None:
            content = MockLLMProvider._mock_callback(prompt)
            return LLMResponse(
                content=content,
                model=self.model,
                usage={"prompt_tokens": len(prompt) // 4, "completion_tokens": len(content) // 4},
            )

        # Check for mock response
        if self._mock_response is not None:
            return LLMResponse(
                content=self._mock_response,
                model=self.model,
                usage={"prompt_tokens": len(prompt) // 4, "completion_tokens": len(self._mock_response) // 4},
            )

        # Default: generate a valid SIR-like response based on prompt
        return LLMResponse(
            content=self._generate_default_response(prompt),
            model=self.model,
            usage={"prompt_tokens": len(prompt) // 4, "completion_tokens": 100},
        )

    def _generate_default_response(self, prompt: str) -> str:
        """Generate a default valid SIR extraction response."""
        prompt_lower = prompt.lower()

        # Detect roles
        actors = []
        if "manager" in prompt_lower or "gerente" in prompt_lower:
            actors.append({
                "actor_key": "actor-manager",
                "name": "Manager",
                "roles": ["manager"],
            })
        if "analyst" in prompt_lower or "analista" in prompt_lower:
            actors.append({
                "actor_key": "actor-analyst",
                "name": "Analyst",
                "roles": ["analyst"],
            })
        if not actors:
            actors.append({
                "actor_key": "actor-user",
                "name": "User",
                "roles": ["user"],
            })

        # Detect entities
        entities = []
        if "expense" in prompt_lower or "despesa" in prompt_lower:
            entities.append({
                "entity_key": "entity-expense",
                "name": "Expense",
                "entity_type": "expense",
            })
        if not entities:
            entities.append({
                "entity_key": "entity-resource",
                "name": "Resource",
                "entity_type": "resource",
            })

        # Detect policies
        policies = []
        if "approve" in prompt_lower or "aprovar" in prompt_lower:
            policies.append({
                "policy_key": "policy-approval-001",
                "policy_type": "approval",
                "description": "Approval policy detected by LLM",
                "actor_refs": [a["actor_key"] for a in actors[:2]],
                "entity_refs": [e["entity_key"] for e in entities[:1]],
                "conditions": {},
            })

        response = {
            "extraction": {
                "actors": actors,
                "entities": entities,
                "policies": policies,
                "workflows": [],
            }
        }

        return json.dumps(response)
