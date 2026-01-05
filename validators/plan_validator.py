"""Validador de PLAN (Implementation Plan)."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import jsonschema


@dataclass
class ValidationReport:
    """Relatório de validação do PLAN."""

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


class PlanValidator:
    """Valida PLAN contra o schema e regras internas.

    Validações:
    1. JSON Schema com schemas/plan.schema.json
    2. Regras internas obrigatórias:
       - order deve ser 1..N sem buraco (sequência contígua)
       - id únicos (sem duplicatas)
       - files não vazio (já coberto pelo schema minItems: 1)
       - acceptance não vazio (já coberto pelo schema minItems: 1)
    """

    def __init__(self) -> None:
        schema_path = Path(__file__).parent.parent / "schemas" / "plan.schema.json"
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

    def _validate_unique_ids(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """Verifica se todos os task ids são únicos."""
        errors = []
        seen_ids: Dict[str, int] = {}

        for idx, task in enumerate(tasks):
            task_id = task.get("id")
            if task_id:
                if task_id in seen_ids:
                    errors.append(
                        f"Duplicate task id '{task_id}' found at index {idx} "
                        f"(first occurrence at index {seen_ids[task_id]})"
                    )
                else:
                    seen_ids[task_id] = idx

        return errors

    def _validate_order_sequence(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """Verifica se orders formam sequência 1..N sem buracos."""
        errors = []

        if not tasks:
            return errors

        orders = []
        for task in tasks:
            order = task.get("order")
            if isinstance(order, int):
                orders.append(order)

        if not orders:
            return errors

        orders_sorted = sorted(orders)
        expected = list(range(1, len(orders) + 1))

        if orders_sorted != expected:
            # Identificar problemas específicos
            missing = set(expected) - set(orders_sorted)
            duplicates = [o for o in orders_sorted if orders_sorted.count(o) > 1]
            out_of_range = [o for o in orders_sorted if o < 1 or o > len(orders)]

            if missing:
                errors.append(
                    f"Order sequence has gaps: missing orders {sorted(missing)}"
                )
            if duplicates:
                unique_dups = sorted(set(duplicates))
                errors.append(
                    f"Order sequence has duplicates: {unique_dups}"
                )
            if out_of_range:
                errors.append(
                    f"Order values out of range (expected 1..{len(orders)}): {sorted(set(out_of_range))}"
                )

        return errors

    def validate(self, plan: Dict[str, Any]) -> ValidationReport:
        """Valida um PLAN e retorna relatório.

        Executa:
        1. Validação contra JSON Schema
        2. Validação de IDs únicos
        3. Validação de sequência de orders (1..N sem buracos)

        Args:
            plan: Documento PLAN a validar

        Returns:
            ValidationReport com ok, errors e missing_fields
        """
        errors: List[str] = []
        missing_fields: List[str] = []

        # 1. Validação de schema
        validator = jsonschema.Draft7Validator(self.schema)
        for error in validator.iter_errors(plan):
            errors.append(error.message)
            missing_fields.extend(self._extract_missing_fields(error))

        # Se schema falhou, retorna sem validações adicionais
        if errors:
            return ValidationReport(
                ok=False,
                errors=errors,
                missing_fields=list(set(missing_fields)),
            )

        # 2. Validações internas (só se schema passou)
        tasks = plan.get("tasks", [])

        # 2a. IDs únicos
        errors.extend(self._validate_unique_ids(tasks))

        # 2b. Order sequence 1..N sem buracos
        errors.extend(self._validate_order_sequence(tasks))

        if not errors:
            return ValidationReport(ok=True)

        return ValidationReport(
            ok=False,
            errors=errors,
            missing_fields=list(set(missing_fields)),
        )


def validate_plan(plan: Dict[str, Any]) -> ValidationReport:
    """Função de conveniência para validar PLAN.

    Args:
        plan: Documento PLAN a validar

    Returns:
        ValidationReport com ok, errors e missing_fields
    """
    validator = PlanValidator()
    return validator.validate(plan)
