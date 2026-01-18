"""NL Extractors."""

import os
from typing import Union

from .base import BaseExtractor
from .deterministic import DeterministicExtractor
from .llm_adapter import LLMExtractor


def get_extractor() -> Union[DeterministicExtractor, LLMExtractor]:
    """Get configured extractor based on environment.

    Uses ENGINE_NL_EXTRACTOR env var:
    - "deterministic" (default): Use deterministic keyword-based extractor
    - "llm": Use LLM extractor with fallback to deterministic

    Returns:
        Configured extractor instance.
    """
    extractor_type = os.environ.get("ENGINE_NL_EXTRACTOR", "deterministic").lower()

    if extractor_type == "llm":
        return LLMExtractor()
    else:
        return DeterministicExtractor()


__all__ = [
    "BaseExtractor",
    "DeterministicExtractor",
    "LLMExtractor",
    "get_extractor",
]
