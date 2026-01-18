"""Base LLM Provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


# Error codes for LLM operations
LLM_TIMEOUT = "LLM_TIMEOUT"
LLM_INVALID_JSON = "LLM_INVALID_JSON"
LLM_SCHEMA_INVALID = "LLM_SCHEMA_INVALID"
LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
LLM_EMPTY_RESPONSE = "LLM_EMPTY_RESPONSE"
LLM_RATE_LIMITED = "LLM_RATE_LIMITED"


@dataclass
class LLMResponse:
    """Response from LLM provider."""

    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class LLMError(Exception):
    """Error from LLM provider."""

    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        model: Optional[str] = None,
        timeout_ms: int = 8000,
        **kwargs: Any,
    ):
        """Initialize provider.

        Args:
            model: Model identifier.
            timeout_ms: Timeout in milliseconds.
            **kwargs: Additional provider-specific options.
        """
        self.model = model or self.default_model()
        self.timeout_ms = timeout_ms
        self.options = kwargs

    @abstractmethod
    def default_model(self) -> str:
        """Return default model for this provider."""
        pass

    @abstractmethod
    def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        """Send completion request to LLM.

        Args:
            prompt: User prompt.
            system: Optional system prompt.

        Returns:
            LLMResponse with completion.

        Raises:
            LLMError: On provider errors.
        """
        pass

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return self.__class__.__name__.replace("LLMProvider", "").lower()
