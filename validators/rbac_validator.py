"""Validador de RBAC (Role-Based Access Control)."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import jsonschema


@dataclass
class ValidationReport:
    """Relatório de validação do RBAC."""

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


class RBACValidator:
    """Valida RBAC contra o schema e regras adicionais.

    Regras:
    1. Validar com jsonschema usando schemas/rbac.schema.json
    2. roles deve conter no mínimo 'authenticated'
    3. permissions[*].operation_id deve ser único (sem duplicados)
    """

    def __init__(self) -> None:
        schema_path = Path(__file__).parent.parent / "schemas" / "rbac.schema.json"
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

        return missing

    def _check_authenticated_role(self, rbac: Dict[str, Any]) -> List[str]:
        """Verifica se 'authenticated' está presente em roles."""
        errors = []
        roles = rbac.get("roles", [])

        if "authenticated" not in roles:
            errors.append("roles deve conter 'authenticated'")

        return errors

    def _check_unique_operation_ids(self, rbac: Dict[str, Any]) -> List[str]:
        """Verifica se operation_ids são únicos."""
        errors = []
        permissions = rbac.get("permissions", [])

        operation_ids = [p.get("operation_id") for p in permissions if p.get("operation_id")]
        duplicates = [op_id for op_id in set(operation_ids) if operation_ids.count(op_id) > 1]

        for dup in duplicates:
            errors.append(f"operation_id '{dup}' está duplicado em permissions")

        return errors

    def validate(self, rbac: Dict[str, Any]) -> ValidationReport:
        """Valida um RBAC e retorna relatório.

        Args:
            rbac: Documento RBAC a validar

        Returns:
            ValidationReport com ok, errors e missing_fields
        """
        errors: List[str] = []
        missing_fields: List[str] = []

        # 1. Validação com JSON Schema
        validator = jsonschema.Draft7Validator(self.schema)
        for error in validator.iter_errors(rbac):
            errors.append(error.message)
            missing_fields.extend(self._extract_missing_fields(error))

        # Se falhou schema, retorna imediatamente
        if errors:
            return ValidationReport(
                ok=False,
                errors=errors,
                missing_fields=list(set(missing_fields)),
            )

        # 2. Validar regra: roles deve conter 'authenticated'
        errors.extend(self._check_authenticated_role(rbac))

        # 3. Validar regra: operation_id deve ser único
        errors.extend(self._check_unique_operation_ids(rbac))

        if errors:
            return ValidationReport(
                ok=False,
                errors=errors,
                missing_fields=[],
            )

        return ValidationReport(ok=True)


def validate_rbac(rbac: Dict[str, Any]) -> ValidationReport:
    """Função de conveniência para validar RBAC.

    Args:
        rbac: Documento RBAC a validar

    Returns:
        ValidationReport com ok, errors e missing_fields
    """
    validator = RBACValidator()
    return validator.validate(rbac)
