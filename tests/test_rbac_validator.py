"""Testes para o RBAC validator."""

import pytest

from validators.rbac_validator import RBACValidator, ValidationReport, validate_rbac


@pytest.fixture
def valid_rbac():
    """Retorna um RBAC válido para testes."""
    return {
        "roles": ["authenticated", "admin"],
        "permissions": [
            {"operation_id": "listUsers", "required_role": "authenticated"},
            {"operation_id": "createUser", "required_role": "admin"},
            {"operation_id": "deleteUser", "required_role": "admin"},
        ],
    }


class TestRBACValidatorBasic:
    """Testes básicos do RBACValidator."""

    def test_valid_rbac_passes(self, valid_rbac):
        """RBAC válido deve passar validação."""
        report = validate_rbac(valid_rbac)

        assert report.ok is True
        assert len(report.errors) == 0
        assert len(report.missing_fields) == 0

    def test_validate_rbac_returns_validation_report(self, valid_rbac):
        """validate_rbac deve retornar ValidationReport."""
        report = validate_rbac(valid_rbac)

        assert isinstance(report, ValidationReport)
        assert hasattr(report, "ok")
        assert hasattr(report, "errors")
        assert hasattr(report, "missing_fields")

    def test_validation_report_to_dict(self, valid_rbac):
        """ValidationReport deve ter método to_dict."""
        report = validate_rbac(valid_rbac)
        result = report.to_dict()

        assert isinstance(result, dict)
        assert "ok" in result
        assert "errors" in result
        assert "missing_fields" in result


class TestRBACSchemaValidation:
    """Testes de validação do schema JSON."""

    def test_rbac_without_roles_fails(self):
        """RBAC sem roles deve falhar."""
        invalid = {
            "permissions": []
        }
        report = validate_rbac(invalid)

        assert report.ok is False
        assert any("roles" in e for e in report.errors)

    def test_rbac_without_permissions_fails(self):
        """RBAC sem permissions deve falhar."""
        invalid = {
            "roles": ["authenticated"]
        }
        report = validate_rbac(invalid)

        assert report.ok is False
        assert any("permissions" in e for e in report.errors)

    def test_rbac_with_empty_roles_fails(self):
        """RBAC com roles vazio deve falhar schema."""
        invalid = {
            "roles": [],
            "permissions": []
        }
        report = validate_rbac(invalid)

        assert report.ok is False

    def test_rbac_permission_without_operation_id_fails(self):
        """Permission sem operation_id deve falhar."""
        invalid = {
            "roles": ["authenticated"],
            "permissions": [
                {"required_role": "authenticated"}
            ]
        }
        report = validate_rbac(invalid)

        assert report.ok is False
        assert any("operation_id" in e for e in report.errors)

    def test_rbac_permission_without_required_role_fails(self):
        """Permission sem required_role deve falhar."""
        invalid = {
            "roles": ["authenticated"],
            "permissions": [
                {"operation_id": "listUsers"}
            ]
        }
        report = validate_rbac(invalid)

        assert report.ok is False
        assert any("required_role" in e for e in report.errors)


class TestAuthenticatedRoleRequired:
    """Testes da regra: roles deve conter 'authenticated'."""

    def test_rbac_without_authenticated_role_fails(self):
        """RBAC sem role 'authenticated' deve falhar."""
        invalid = {
            "roles": ["admin", "user"],
            "permissions": []
        }
        report = validate_rbac(invalid)

        assert report.ok is False
        assert any("authenticated" in e for e in report.errors)

    def test_rbac_with_only_authenticated_passes(self):
        """RBAC com apenas 'authenticated' deve passar."""
        valid = {
            "roles": ["authenticated"],
            "permissions": []
        }
        report = validate_rbac(valid)

        assert report.ok is True

    def test_rbac_with_authenticated_and_others_passes(self):
        """RBAC com 'authenticated' e outras roles deve passar."""
        valid = {
            "roles": ["authenticated", "admin", "moderator"],
            "permissions": []
        }
        report = validate_rbac(valid)

        assert report.ok is True


class TestUniqueOperationIds:
    """Testes da regra: operation_id deve ser único."""

    def test_duplicate_operation_id_fails(self):
        """operation_id duplicado deve falhar."""
        invalid = {
            "roles": ["authenticated"],
            "permissions": [
                {"operation_id": "listUsers", "required_role": "authenticated"},
                {"operation_id": "listUsers", "required_role": "admin"},
            ]
        }
        report = validate_rbac(invalid)

        assert report.ok is False
        assert any("duplicado" in e or "listUsers" in e for e in report.errors)

    def test_multiple_duplicates_reported(self):
        """Múltiplos operation_ids duplicados devem ser reportados."""
        invalid = {
            "roles": ["authenticated"],
            "permissions": [
                {"operation_id": "op1", "required_role": "authenticated"},
                {"operation_id": "op1", "required_role": "admin"},
                {"operation_id": "op2", "required_role": "authenticated"},
                {"operation_id": "op2", "required_role": "admin"},
            ]
        }
        report = validate_rbac(invalid)

        assert report.ok is False
        # Deve ter erros para op1 e op2
        assert any("op1" in e for e in report.errors)
        assert any("op2" in e for e in report.errors)

    def test_unique_operation_ids_passes(self, valid_rbac):
        """operation_ids únicos devem passar."""
        report = validate_rbac(valid_rbac)

        assert report.ok is True

    def test_empty_permissions_passes(self):
        """Permissions vazio deve passar (sem duplicados)."""
        valid = {
            "roles": ["authenticated"],
            "permissions": []
        }
        report = validate_rbac(valid)

        assert report.ok is True


class TestRBACValidatorClass:
    """Testes da classe RBACValidator."""

    def test_validator_loads_schema(self):
        """RBACValidator deve carregar o schema."""
        validator = RBACValidator()

        assert validator.schema is not None
        assert "$schema" in validator.schema

    def test_validator_validate_method(self, valid_rbac):
        """Método validate deve funcionar."""
        validator = RBACValidator()
        report = validator.validate(valid_rbac)

        assert isinstance(report, ValidationReport)
        assert report.ok is True


class TestComplexRBACScenarios:
    """Testes de cenários complexos de RBAC."""

    def test_rbac_with_many_permissions(self):
        """RBAC com muitas permissions deve passar se válido."""
        valid = {
            "roles": ["authenticated", "admin", "moderator"],
            "permissions": [
                {"operation_id": f"operation_{i}", "required_role": "authenticated"}
                for i in range(50)
            ]
        }
        report = validate_rbac(valid)

        assert report.ok is True

    def test_rbac_with_description_in_permissions(self):
        """RBAC com description opcional deve passar."""
        valid = {
            "roles": ["authenticated"],
            "permissions": [
                {
                    "operation_id": "listUsers",
                    "required_role": "authenticated",
                    "description": "Lista todos os usuários"
                }
            ]
        }
        report = validate_rbac(valid)

        assert report.ok is True

    def test_rbac_with_meta(self):
        """RBAC com meta opcional deve passar."""
        valid = {
            "roles": ["authenticated"],
            "permissions": [],
            "meta": {
                "version": "1.0.0",
                "project_name": "Test"
            }
        }
        report = validate_rbac(valid)

        assert report.ok is True

    def test_combined_failures(self):
        """Múltiplas falhas devem ser reportadas."""
        # Falha schema primeiro (antes das regras adicionais)
        invalid = {
            "roles": [],  # Falha: minItems
            "permissions": []
        }
        report = validate_rbac(invalid)

        assert report.ok is False
        # Schema falha primeiro, então não chega às regras adicionais
        assert len(report.errors) >= 1
