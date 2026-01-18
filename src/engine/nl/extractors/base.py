"""Base extractor interface."""

from abc import ABC, abstractmethod
from typing import Optional

from engine.nl.schemas.sir_v1 import SIRv1


class BaseExtractor(ABC):
    """Base class for text extractors."""

    @abstractmethod
    def extract(self, text: str, language: Optional[str] = None) -> SIRv1:
        """Extract structured information from text.

        Args:
            text: Source text to extract from.
            language: Optional language hint (auto-detected if not provided).

        Returns:
            SIRv1 with extracted entities.

        Raises:
            ValueError: If extraction fails.
        """
        pass

    @abstractmethod
    def detect_language(self, text: str) -> str:
        """Detect the language of the text.

        Args:
            text: Text to analyze.

        Returns:
            Language code (e.g., "en", "pt").
        """
        pass
