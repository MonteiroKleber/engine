"""Validador de SRS com Gate e Question Generator."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema


# Mapeamento de campos para perguntas
FIELD_QUESTIONS: Dict[str, str] = {
    "id": "Qual deve ser o identificador único do SRS?",
    "title": "Qual é o título do sistema/projeto?",
    "requirements": "Quais são os requisitos funcionais do sistema?",
    "requirements.id": "Qual é o ID do requisito?",
    "requirements.description": "Qual é a descrição do requisito?",
    "requirements.priority": "Qual é a prioridade do requisito (high/medium/low)?",
    "version": "Qual é a versão do documento SRS?",
}


@dataclass
class ValidationReport:
    """Relatório estruturado de validação."""

    ok: bool
    errors: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "ok": self.ok,
            "errors": self.errors,
            "missing_fields": self.missing_fields,
            "questions": self.questions,
        }


class SRSValidator:
    """Valida documentos SRS contra o schema com Gate e Question Generator."""

    def __init__(self, max_questions_per_round: int = 7) -> None:
        schema_path = Path(__file__).parent.parent / "schemas" / "srs.schema.json"
        with open(schema_path) as f:
            self.schema = json.load(f)
        self.max_questions = max_questions_per_round

    def _extract_missing_fields(self, error: jsonschema.ValidationError) -> List[str]:
        """Extrai campos faltantes de um erro de validação."""
        missing = []

        if error.validator == "required":
            # Erro de campo obrigatório faltando
            for field in error.validator_value:
                if field not in error.instance:
                    path = ".".join(str(p) for p in error.absolute_path)
                    full_path = f"{path}.{field}" if path else field
                    missing.append(full_path)
        elif error.validator == "type":
            # Tipo errado
            path = ".".join(str(p) for p in error.absolute_path)
            if path:
                missing.append(path)

        return missing

    def _collect_all_errors(
        self, srs: Dict[str, Any]
    ) -> tuple[List[str], List[str]]:
        """Coleta todos os erros de validação."""
        errors = []
        missing_fields = []

        validator = jsonschema.Draft7Validator(self.schema)
        for error in validator.iter_errors(srs):
            errors.append(error.message)
            missing_fields.extend(self._extract_missing_fields(error))

        return errors, list(set(missing_fields))

    def _generate_questions(self, missing_fields: List[str]) -> List[str]:
        """Gera perguntas para campos faltantes."""
        questions = []

        for field in missing_fields:
            # Tentar match exato
            if field in FIELD_QUESTIONS:
                questions.append(FIELD_QUESTIONS[field])
            else:
                # Tentar match parcial (ex: requirements.0.id -> requirements.id)
                simplified = ".".join(
                    p for p in field.split(".") if not p.isdigit()
                )
                if simplified in FIELD_QUESTIONS:
                    questions.append(FIELD_QUESTIONS[simplified])
                else:
                    # Gerar pergunta genérica
                    questions.append(f"Qual é o valor para o campo '{field}'?")

        # Remover duplicatas mantendo ordem
        seen = set()
        unique_questions = []
        for q in questions:
            if q not in seen:
                seen.add(q)
                unique_questions.append(q)

        return unique_questions[: self.max_questions]

    def validate(self, srs: Dict[str, Any]) -> ValidationReport:
        """Valida um documento SRS e retorna relatório estruturado.

        Args:
            srs: Documento SRS a validar

        Returns:
            ValidationReport com ok, errors, missing_fields e questions
        """
        errors, missing_fields = self._collect_all_errors(srs)

        if not errors:
            return ValidationReport(ok=True)

        questions = self._generate_questions(missing_fields)

        return ValidationReport(
            ok=False,
            errors=errors,
            missing_fields=missing_fields,
            questions=questions,
        )


class SRSValidatorGate:
    """Gate que bloqueia pipeline se SRS inválido."""

    def __init__(
        self,
        validator: Optional[SRSValidator] = None,
        max_questions_per_round: int = 7,
    ) -> None:
        self.validator = validator or SRSValidator(max_questions_per_round)

    def check(self, srs: Dict[str, Any]) -> ValidationReport:
        """Verifica se SRS pode passar pelo gate.

        Args:
            srs: Documento SRS a validar

        Returns:
            ValidationReport indicando se pode passar
        """
        return self.validator.validate(srs)

    def can_proceed(self, srs: Dict[str, Any]) -> bool:
        """Verifica se SRS é válido e pode seguir no pipeline.

        Args:
            srs: Documento SRS a validar

        Returns:
            True se válido (pode versionar), False se inválido (bloqueado)
        """
        report = self.check(srs)
        return report.ok

    def process(
        self, srs: Dict[str, Any]
    ) -> tuple[bool, Optional[Dict[str, Any]], Optional[List[str]]]:
        """Processa SRS pelo gate.

        Args:
            srs: Documento SRS a validar

        Returns:
            Tuple de (can_proceed, srs_if_valid, questions_if_invalid)
        """
        report = self.check(srs)

        if report.ok:
            # Válido → permite versionar SRS
            return True, srs, None
        else:
            # Inválido → bloqueia pipeline e retorna perguntas
            return False, None, report.questions
