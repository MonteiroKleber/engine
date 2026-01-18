"""LLM Adapter Extractor with fallback to deterministic."""

import os
from typing import Optional, Dict, Any

from engine.nl.schemas.sir_v1 import (
    SIRv1,
    Source,
    Segment,
    Extraction,
    Actor,
    Entity,
    Policy,
    Workflow,
    WorkflowStep,
)
from engine.nl.extractors.base import BaseExtractor
from engine.nl.extractors.deterministic import DeterministicExtractor
from engine.nl.extractors.providers.base import (
    BaseLLMProvider,
    LLMError,
    LLM_TIMEOUT,
    LLM_INVALID_JSON,
    LLM_SCHEMA_INVALID,
    LLM_PROVIDER_ERROR,
    LLM_EMPTY_RESPONSE,
)
from engine.nl.extractors.providers.mock import MockLLMProvider
from engine.nl.extractors.providers.openai_stub import OpenAILLMProvider
from engine.nl.llm_prompt import SYSTEM_PROMPT, build_extraction_prompt
from engine.nl.llm_validate import validate_llm_extraction, normalize_llm_extraction


def get_llm_provider() -> BaseLLMProvider:
    """Get configured LLM provider based on environment.

    Returns:
        Configured LLM provider instance.
    """
    provider_name = os.environ.get("ENGINE_NL_LLM_PROVIDER", "mock").lower()
    timeout_ms = int(os.environ.get("ENGINE_NL_LLM_TIMEOUT_MS", "8000"))
    model = os.environ.get("ENGINE_NL_LLM_MODEL")

    if provider_name == "openai":
        return OpenAILLMProvider(model=model, timeout_ms=timeout_ms)
    else:
        return MockLLMProvider(model=model, timeout_ms=timeout_ms)


class LLMExtractor(BaseExtractor):
    """LLM-based extractor with automatic fallback to deterministic."""

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        """Initialize LLM extractor.

        Args:
            provider: LLM provider to use. If None, uses environment config.
        """
        self.provider = provider or get_llm_provider()
        self.deterministic = DeterministicExtractor()
        self._last_error_code: Optional[str] = None
        self._extractor_used: str = "llm"

    @property
    def last_error_code(self) -> Optional[str]:
        """Return last error code if fallback was used."""
        return self._last_error_code

    @property
    def extractor_used(self) -> str:
        """Return which extractor was used for last extraction."""
        return self._extractor_used

    def detect_language(self, text: str) -> str:
        """Detect language using deterministic extractor.

        Args:
            text: Text to analyze.

        Returns:
            Language code ("en" or "pt").
        """
        return self.deterministic.detect_language(text)

    def extract(self, text: str, language: Optional[str] = None) -> SIRv1:
        """Extract structured information using LLM with fallback.

        Args:
            text: Source text to extract from.
            language: Optional language hint.

        Returns:
            SIRv1 with extracted entities and metadata.
        """
        if not text or not text.strip():
            raise ValueError("Empty input text")

        # Detect language if not provided
        if language is None:
            language = self.deterministic.detect_language(text)

        # Reset state
        self._last_error_code = None
        self._extractor_used = "llm"

        # Try LLM extraction
        try:
            sir = self._extract_with_llm(text, language)
            return sir
        except Exception as e:
            # Fallback to deterministic
            return self._fallback_to_deterministic(text, language, e)

    def _extract_with_llm(self, text: str, language: str) -> SIRv1:
        """Extract using LLM provider.

        Args:
            text: Source text.
            language: Text language.

        Returns:
            SIRv1 from LLM extraction.

        Raises:
            LLMError: On LLM failures.
            ValueError: On validation failures.
        """
        # Build prompt
        prompt = build_extraction_prompt(text, language)

        # Call LLM
        try:
            response = self.provider.complete(prompt, system=SYSTEM_PROMPT)
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(
                code=LLM_PROVIDER_ERROR,
                message=f"Provider error: {e}",
            )

        # Validate response
        is_valid, data, error_code = validate_llm_extraction(response.content)
        if not is_valid:
            raise LLMError(
                code=error_code or LLM_SCHEMA_INVALID,
                message=f"Invalid LLM response: {error_code}",
                details={"raw_response": response.content[:500]},
            )

        # Normalize extraction
        normalized = normalize_llm_extraction(data)

        # Build SIR
        return self._build_sir_from_llm(text, language, normalized)

    def _build_sir_from_llm(
        self,
        text: str,
        language: str,
        data: Dict[str, Any],
    ) -> SIRv1:
        """Build SIRv1 from LLM extraction data.

        Args:
            text: Original text.
            language: Text language.
            data: Normalized extraction data.

        Returns:
            SIRv1 instance.
        """
        extraction_data = data["extraction"]

        # Build source with segments
        segments = [
            Segment(
                segment_key="seg-000",
                text=text,
                start_char=0,
                end_char=len(text),
            )
        ]
        source = Source(language=language, segments=segments)

        # Build actors
        actors = []
        for actor_data in extraction_data.get("actors", []):
            actors.append(Actor(
                actor_key=actor_data["actor_key"],
                name=actor_data["name"],
                roles=actor_data.get("roles", []),
                source_segment=actor_data.get("source_segment"),
            ))

        # Build entities
        entities = []
        for entity_data in extraction_data.get("entities", []):
            entities.append(Entity(
                entity_key=entity_data["entity_key"],
                name=entity_data["name"],
                entity_type=entity_data["entity_type"],
                attributes=entity_data.get("attributes", {}),
                source_segment=entity_data.get("source_segment"),
            ))

        # Build policies
        policies = []
        for policy_data in extraction_data.get("policies", []):
            policies.append(Policy(
                policy_key=policy_data["policy_key"],
                policy_type=policy_data["policy_type"],
                description=policy_data["description"],
                actor_refs=policy_data.get("actor_refs", []),
                entity_refs=policy_data.get("entity_refs", []),
                conditions=policy_data.get("conditions", {}),
                source_segment=policy_data.get("source_segment"),
            ))

        # Build workflows
        workflows = []
        for workflow_data in extraction_data.get("workflows", []):
            steps = []
            for step_data in workflow_data.get("steps", []):
                steps.append(WorkflowStep(
                    step_key=step_data["step_key"],
                    action=step_data["action"],
                    actor_ref=step_data.get("actor_ref"),
                    entity_ref=step_data.get("entity_ref"),
                    conditions=step_data.get("conditions", {}),
                ))
            workflows.append(Workflow(
                workflow_key=workflow_data["workflow_key"],
                name=workflow_data["name"],
                steps=steps,
                source_segment=workflow_data.get("source_segment"),
            ))

        extraction = Extraction(
            actors=actors,
            entities=entities,
            policies=policies,
            workflows=workflows,
        )

        return SIRv1(
            version="1.0",
            source=source,
            extraction=extraction,
        )

    def _fallback_to_deterministic(
        self,
        text: str,
        language: str,
        error: Exception,
    ) -> SIRv1:
        """Fall back to deterministic extraction.

        Args:
            text: Source text.
            language: Text language.
            error: The error that caused fallback.

        Returns:
            SIRv1 from deterministic extraction.
        """
        # Record error
        if isinstance(error, LLMError):
            self._last_error_code = error.code
        else:
            self._last_error_code = LLM_PROVIDER_ERROR

        self._extractor_used = "deterministic_fallback"

        # Use deterministic extractor
        return self.deterministic.extract(text, language)
