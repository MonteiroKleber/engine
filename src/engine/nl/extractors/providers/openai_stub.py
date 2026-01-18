"""OpenAI LLM Provider stub.

This is a stub implementation that does not make actual API calls.
For production use, replace with actual OpenAI SDK integration.
"""

import os
from typing import Optional, Any

from .base import (
    BaseLLMProvider,
    LLMResponse,
    LLMError,
    LLM_PROVIDER_ERROR,
)


class OpenAILLMProvider(BaseLLMProvider):
    """OpenAI LLM provider stub.

    This stub raises an error indicating OpenAI is not configured.
    For production, implement actual API calls.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        timeout_ms: int = 8000,
        api_key: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(model, timeout_ms, **kwargs)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def default_model(self) -> str:
        return "gpt-4o-mini"

    def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        """Send completion request to OpenAI.

        This stub implementation raises an error.
        Replace with actual OpenAI SDK calls for production.

        Args:
            prompt: User prompt.
            system: Optional system prompt.

        Returns:
            LLMResponse with completion.

        Raises:
            LLMError: Always raises in stub.
        """
        if not self.api_key:
            raise LLMError(
                code=LLM_PROVIDER_ERROR,
                message="OpenAI API key not configured. Set OPENAI_API_KEY environment variable.",
                details={"provider": "openai"},
            )

        # Stub: In production, implement actual OpenAI API call
        # Example with openai SDK:
        # from openai import OpenAI
        # client = OpenAI(api_key=self.api_key)
        # response = client.chat.completions.create(
        #     model=self.model,
        #     messages=[
        #         {"role": "system", "content": system} if system else None,
        #         {"role": "user", "content": prompt}
        #     ],
        #     timeout=self.timeout_ms / 1000,
        # )
        # return LLMResponse(
        #     content=response.choices[0].message.content,
        #     model=response.model,
        #     usage=response.usage.model_dump(),
        # )

        raise LLMError(
            code=LLM_PROVIDER_ERROR,
            message="OpenAI provider is a stub. Implement actual API calls for production.",
            details={"provider": "openai", "model": self.model},
        )
