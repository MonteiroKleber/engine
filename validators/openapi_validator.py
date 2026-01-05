"""Validador de OpenAPI (OAS)."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


# Métodos HTTP válidos para OpenAPI
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


@dataclass
class ValidationReport:
    """Relatório de validação do OpenAPI."""

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


class OpenAPIValidator:
    """Valida OpenAPI contra regras mínimas obrigatórias.

    Regras:
    1. OpenAPI deve ter 'openapi' e 'paths'
    2. Proibir 'paths' vazio
    3. Todo método em paths deve ter 'operationId' e 'responses'
    4. Proibir path vazio
    5. Proibir operação sem 'tags'
    """

    def _check_required_fields(self, oas: Dict[str, Any]) -> tuple[List[str], List[str]]:
        """Verifica campos obrigatórios de nível superior."""
        errors = []
        missing = []

        if "openapi" not in oas:
            errors.append("Campo 'openapi' é obrigatório")
            missing.append("openapi")

        if "paths" not in oas:
            errors.append("Campo 'paths' é obrigatório")
            missing.append("paths")

        return errors, missing

    def _check_paths_not_empty(self, oas: Dict[str, Any]) -> List[str]:
        """Verifica se paths não está vazio."""
        errors = []
        paths = oas.get("paths", {})

        if not paths:
            errors.append("'paths' não pode estar vazio")

        return errors

    def _check_path_not_empty(self, path: str, path_item: Dict[str, Any]) -> List[str]:
        """Verifica se um path item não está vazio (tem pelo menos um método)."""
        errors = []

        methods = [m for m in path_item.keys() if m.lower() in HTTP_METHODS]
        if not methods:
            errors.append(f"Path '{path}' não tem nenhum método HTTP definido")

        return errors

    def _check_operation_required_fields(
        self, path: str, method: str, operation: Dict[str, Any]
    ) -> tuple[List[str], List[str]]:
        """Verifica campos obrigatórios em uma operação."""
        errors = []
        missing = []

        # operationId obrigatório
        if "operationId" not in operation:
            errors.append(f"Operação {method.upper()} {path} não tem 'operationId'")
            missing.append(f"paths.{path}.{method}.operationId")

        # responses obrigatório
        if "responses" not in operation:
            errors.append(f"Operação {method.upper()} {path} não tem 'responses'")
            missing.append(f"paths.{path}.{method}.responses")

        # tags obrigatório
        if "tags" not in operation or not operation.get("tags"):
            errors.append(f"Operação {method.upper()} {path} não tem 'tags'")
            missing.append(f"paths.{path}.{method}.tags")

        return errors, missing

    def validate(self, oas: Dict[str, Any]) -> ValidationReport:
        """Valida um documento OpenAPI.

        Args:
            oas: Documento OpenAPI (como dict)

        Returns:
            ValidationReport com ok, errors e missing_fields
        """
        errors: List[str] = []
        missing_fields: List[str] = []

        # 1. Verificar campos obrigatórios de nível superior
        req_errors, req_missing = self._check_required_fields(oas)
        errors.extend(req_errors)
        missing_fields.extend(req_missing)

        # Se faltam campos obrigatórios, retorna imediatamente
        if errors:
            return ValidationReport(
                ok=False,
                errors=errors,
                missing_fields=missing_fields,
            )

        # 2. Verificar se paths não está vazio
        errors.extend(self._check_paths_not_empty(oas))

        if errors:
            return ValidationReport(
                ok=False,
                errors=errors,
                missing_fields=missing_fields,
            )

        # 3. Validar cada path e suas operações
        paths = oas.get("paths", {})
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                errors.append(f"Path '{path}' deve ser um objeto")
                continue

            # Verificar se path tem pelo menos um método
            errors.extend(self._check_path_not_empty(path, path_item))

            # Verificar cada método no path
            for method, operation in path_item.items():
                if method.lower() not in HTTP_METHODS:
                    continue  # Ignora campos como 'parameters', 'summary', etc.

                if not isinstance(operation, dict):
                    errors.append(f"Operação {method.upper()} {path} deve ser um objeto")
                    continue

                op_errors, op_missing = self._check_operation_required_fields(
                    path, method, operation
                )
                errors.extend(op_errors)
                missing_fields.extend(op_missing)

        if errors:
            return ValidationReport(
                ok=False,
                errors=errors,
                missing_fields=list(set(missing_fields)),
            )

        return ValidationReport(ok=True)


def validate_openapi(oas: Dict[str, Any]) -> ValidationReport:
    """Função de conveniência para validar OpenAPI.

    Args:
        oas: Documento OpenAPI (como dict)

    Returns:
        ValidationReport com ok, errors e missing_fields
    """
    validator = OpenAPIValidator()
    return validator.validate(oas)
