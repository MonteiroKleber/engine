"""Normalização de entrada de requisitos (determinístico, sem LLM)."""

import re
from typing import Dict, Any, List


MAX_INPUT_SIZE = 20_000


class Normalizer:
    """Normaliza entrada de texto para formato padrão.

    Operações (determinísticas):
    - trim (remove espaços início/fim)
    - remover espaços duplicados
    - limitar tamanho (20k chars)
    - separar linhas em bullets
    """

    def __init__(self, max_size: int = MAX_INPUT_SIZE) -> None:
        self.max_size = max_size

    def _trim(self, text: str) -> str:
        """Remove espaços em branco do início e fim."""
        return text.strip()

    def _remove_duplicate_spaces(self, text: str) -> str:
        """Remove espaços duplicados, mantendo apenas um."""
        return re.sub(r" +", " ", text)

    def _limit_size(self, text: str) -> str:
        """Limita o tamanho do texto ao máximo permitido."""
        if len(text) <= self.max_size:
            return text
        return text[: self.max_size]

    def _split_into_bullets(self, text: str) -> List[str]:
        """Separa texto em bullets por linha."""
        lines = text.split("\n")
        bullets = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                bullets.append(stripped)
        return bullets

    def normalize(self, raw_input: str) -> Dict[str, Any]:
        """Normaliza entrada bruta.

        Args:
            raw_input: Texto bruto de entrada

        Returns:
            Dicionário com:
            - original: texto original
            - normalized: texto normalizado
            - bullets: lista de linhas como bullets
            - truncated: se foi truncado
            - language: idioma padrão
        """
        # Guardar original
        original = raw_input

        # Pipeline de normalização
        text = self._trim(raw_input)
        text = self._remove_duplicate_spaces(text)

        # Verificar se vai truncar
        truncated = len(text) > self.max_size
        text = self._limit_size(text)

        # Separar em bullets
        bullets = self._split_into_bullets(text)

        return {
            "original": original,
            "normalized": text,
            "bullets": bullets,
            "truncated": truncated,
            "language": "pt-BR",
        }
