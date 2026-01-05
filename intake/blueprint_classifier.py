"""Classificador de blueprints (determinístico inicial)."""

from typing import Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class BlueprintCandidate:
    """Candidato a blueprint."""
    blueprint_id: str
    score: float


@dataclass
class ClassificationResult:
    """Resultado da classificação de blueprint."""
    mode: str
    confidence: float
    candidates: List[BlueprintCandidate]
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "mode": self.mode,
            "confidence": self.confidence,
            "candidates": [
                {"blueprint_id": c.blueprint_id, "score": c.score}
                for c in self.candidates
            ],
            "reasons": self.reasons,
        }

    @property
    def selected_blueprint(self) -> str:
        """Retorna o blueprint selecionado (maior score)."""
        if not self.candidates:
            return "generic"
        return max(self.candidates, key=lambda c: c.score).blueprint_id


class BlueprintClassifier:
    """Classifica requisitos em tipos de blueprint.

    Versão v1: Sempre retorna blueprint genérico (determinístico).
    """

    def __init__(self, confidence_threshold: float = 0.85) -> None:
        self.confidence_threshold = confidence_threshold
        self._enabled = False  # Classificador desabilitado na v1

    def classify(self, normalized_input: Dict[str, Any]) -> ClassificationResult:
        """Classifica entrada normalizada em tipo de blueprint.

        Na v1, sempre retorna blueprint genérico com modo FORCED_GENERIC.

        Args:
            normalized_input: Resultado do Normalizer

        Returns:
            ClassificationResult com blueprint genérico
        """
        return ClassificationResult(
            mode="FORCED_GENERIC",
            confidence=0.0,
            candidates=[
                BlueprintCandidate(blueprint_id="generic", score=1.0)
            ],
            reasons=["classifier_not_enabled_v1"],
        )
