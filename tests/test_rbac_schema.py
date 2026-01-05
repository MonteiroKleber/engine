"""Testes para o schema RBAC."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, ValidationError, validate


@pytest.fixture
def rbac_schema():
    """Carrega o schema RBAC."""
    schema_path = Path(__file__).parent.parent / "schemas" / "rbac.schema.json"
    with open(schema_path) as f:
        return json.load(f)


@pytest.fixture
def valid_rbac():
    """Retorna um RBAC válido para testes."""
    return {
        "roles": ["authenticated", "admin"],
        "permissions": [
            {
                "operation_id": "listUsers",
                "required_role": "authenticated",
            },
            {
                "operation_id": "createUser",
                "required_role": "admin",
            },
            {
                "operation_id": "deleteUser",
                "required_role": "admin",
                "description": "Permite deletar usuários",
            },
        ],
    }


class TestRBACSchemaLoading:
    """Testes de carregamento do schema RBAC."""

    def test_rbac_schema_loads_without_error(self, rbac_schema):
        """Schema RBAC deve carregar sem erro."""
        assert rbac_schema is not None
        assert "$schema" in rbac_schema

    def test_rbac_schema_has_required_properties(self, rbac_schema):
        """Schema deve definir roles e permissions como obrigatórios."""
        assert "required" in rbac_schema
        assert "roles" in rbac_schema["required"]
        assert "permissions" in rbac_schema["required"]

    def test_rbac_schema_is_valid_json_schema(self, rbac_schema):
        """Schema deve ser um JSON Schema válido."""
        Draft7Validator.check_schema(rbac_schema)


class TestRBACValidation:
    """Testes de validação de documentos RBAC."""

    def test_valid_rbac_passes_validation(self, rbac_schema, valid_rbac):
        """RBAC válido deve passar validação."""
        validate(instance=valid_rbac, schema=rbac_schema)

    def test_rbac_without_roles_fails(self, rbac_schema):
        """RBAC sem roles deve falhar."""
        invalid = {
            "permissions": [
                {"operation_id": "listUsers", "required_role": "authenticated"}
            ]
        }
        with pytest.raises(ValidationError) as exc:
            validate(instance=invalid, schema=rbac_schema)
        assert "roles" in str(exc.value)

    def test_rbac_without_permissions_fails(self, rbac_schema):
        """RBAC sem permissions deve falhar."""
        invalid = {
            "roles": ["authenticated"]
        }
        with pytest.raises(ValidationError) as exc:
            validate(instance=invalid, schema=rbac_schema)
        assert "permissions" in str(exc.value)

    def test_rbac_with_empty_roles_fails(self, rbac_schema):
        """RBAC com roles vazio deve falhar."""
        invalid = {
            "roles": [],
            "permissions": []
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=rbac_schema)

    def test_rbac_permission_without_operation_id_fails(self, rbac_schema):
        """Permission sem operation_id deve falhar."""
        invalid = {
            "roles": ["authenticated"],
            "permissions": [
                {"required_role": "authenticated"}
            ]
        }
        with pytest.raises(ValidationError) as exc:
            validate(instance=invalid, schema=rbac_schema)
        assert "operation_id" in str(exc.value)

    def test_rbac_permission_without_required_role_fails(self, rbac_schema):
        """Permission sem required_role deve falhar."""
        invalid = {
            "roles": ["authenticated"],
            "permissions": [
                {"operation_id": "listUsers"}
            ]
        }
        with pytest.raises(ValidationError) as exc:
            validate(instance=invalid, schema=rbac_schema)
        assert "required_role" in str(exc.value)

    def test_rbac_with_duplicate_roles_fails(self, rbac_schema):
        """RBAC com roles duplicadas deve falhar."""
        invalid = {
            "roles": ["authenticated", "authenticated"],
            "permissions": []
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=rbac_schema)

    def test_rbac_with_empty_operation_id_fails(self, rbac_schema):
        """Permission com operation_id vazio deve falhar."""
        invalid = {
            "roles": ["authenticated"],
            "permissions": [
                {"operation_id": "", "required_role": "authenticated"}
            ]
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=rbac_schema)

    def test_rbac_with_empty_required_role_fails(self, rbac_schema):
        """Permission com required_role vazio deve falhar."""
        invalid = {
            "roles": ["authenticated"],
            "permissions": [
                {"operation_id": "listUsers", "required_role": ""}
            ]
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=rbac_schema)

    def test_rbac_with_optional_description_passes(self, rbac_schema):
        """Permission com description opcional deve passar."""
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
        validate(instance=valid, schema=rbac_schema)

    def test_rbac_with_meta_passes(self, rbac_schema):
        """RBAC com meta opcional deve passar."""
        valid = {
            "roles": ["authenticated"],
            "permissions": [],
            "meta": {
                "version": "1.0.0",
                "project_name": "Test Project"
            }
        }
        validate(instance=valid, schema=rbac_schema)

    def test_rbac_rejects_additional_properties_in_permission(self, rbac_schema):
        """Permission com propriedades extras deve falhar."""
        invalid = {
            "roles": ["authenticated"],
            "permissions": [
                {
                    "operation_id": "listUsers",
                    "required_role": "authenticated",
                    "extra_field": "not allowed"
                }
            ]
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=rbac_schema)


class TestRBACMinimalValid:
    """Testes de RBAC mínimo válido."""

    def test_minimal_rbac_with_one_role(self, rbac_schema):
        """RBAC mínimo com uma role e sem permissions deve passar."""
        minimal = {
            "roles": ["authenticated"],
            "permissions": []
        }
        validate(instance=minimal, schema=rbac_schema)

    def test_minimal_rbac_with_one_permission(self, rbac_schema):
        """RBAC mínimo com uma role e uma permission deve passar."""
        minimal = {
            "roles": ["authenticated"],
            "permissions": [
                {"operation_id": "ping", "required_role": "authenticated"}
            ]
        }
        validate(instance=minimal, schema=rbac_schema)
