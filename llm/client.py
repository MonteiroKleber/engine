"""Cliente LLM com interface e mock."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMClientInterface(ABC):
    """Interface abstrata para cliente LLM."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """Gera uma completion."""
        pass

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """Gera resposta para chat."""
        pass


class MockLLMClient(LLMClientInterface):
    """Implementação mock do cliente LLM para testes."""

    def __init__(self) -> None:
        self.call_history: List[Dict[str, Any]] = []
        self.mock_responses: List[str] = []
        self._response_index = 0

    def set_mock_responses(self, responses: List[str]) -> None:
        """Define respostas mock."""
        self.mock_responses = responses
        self._response_index = 0

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """Gera uma completion mock."""
        self.call_history.append({
            "method": "complete",
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })

        if self.mock_responses:
            response = self.mock_responses[self._response_index % len(self.mock_responses)]
            self._response_index += 1
            return response

        return "Mock response for: " + prompt[:50]

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """Gera resposta mock para chat."""
        self.call_history.append({
            "method": "chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })

        if self.mock_responses:
            response = self.mock_responses[self._response_index % len(self.mock_responses)]
            self._response_index += 1
            return response

        last_message = messages[-1]["content"] if messages else ""
        return "Mock chat response for: " + last_message[:50]


def get_llm_client() -> LLMClientInterface:
    """Factory para obter cliente LLM.

    Retorna mock por padrão até SDK ser configurado.
    """
    return MockLLMClient()
