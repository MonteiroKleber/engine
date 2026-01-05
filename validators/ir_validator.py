"""Validador de IR (Intermediate Representation)."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import jsonschema


@dataclass
class ValidationReport:
    """Relatório de validação do IR."""

    ok: bool
    errors: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "ok": self.ok,
            "errors": self.errors,
            "missing_fields": self.missing_fields,
        }


class IRValidator:
    """Valida IR contra o schema."""

    def __init__(self) -> None:
        schema_path = Path(__file__).parent.parent / "schemas" / "ir.schema.json"
        with open(schema_path) as f:
            self.schema = json.load(f)

    def _extract_missing_fields(self, error: jsonschema.ValidationError) -> List[str]:
        """Extrai campos faltantes de um erro de validação."""
        missing = []

        if error.validator == "required":
            for field_name in error.validator_value:
                if field_name not in error.instance:
                    path = ".".join(str(p) for p in error.absolute_path)
                    full_path = f"{path}.{field_name}" if path else field_name
                    missing.append(full_path)
        elif error.validator == "minItems":
            path = ".".join(str(p) for p in error.absolute_path)
            if path:
                missing.append(f"{path} (requires at least {error.validator_value} item)")

        return missing

    def validate(self, ir: Dict[str, Any]) -> ValidationReport:
        """Valida um IR e retorna relatório.

        Args:
            ir: Documento IR a validar

        Returns:
            ValidationReport com ok, errors e missing_fields
        """
        errors: List[str] = []
        missing_fields: List[str] = []

        validator = jsonschema.Draft7Validator(self.schema)
        for error in validator.iter_errors(ir):
            errors.append(error.message)
            missing_fields.extend(self._extract_missing_fields(error))

        if not errors:
            return ValidationReport(ok=True)

        return ValidationReport(
            ok=False,
            errors=errors,
            missing_fields=list(set(missing_fields)),
        )


def validate_ir(ir: Dict[str, Any]) -> ValidationReport:
    """Função de conveniência para validar IR.

    Args:
        ir: Documento IR a validar

    Returns:
        ValidationReport com ok, errors e missing_fields
    """
    validator = IRValidator()
    return validator.validate(ir)
