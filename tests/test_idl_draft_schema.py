"""Testes para IDL Draft Schema Validator - GATE 1.

GATE 1: Validação Estrutural do Draft
- Rejeita: JSON inválido, schema_version errado, IDs duplicados, tipos errados
- Aceita: campos unknown, campos opcionais ausentes, assumptions, open_questions
"""

import pytest
from idl.idl_draft_schema import (
    DraftSchemaValidator,
    DraftValidationResult,
    DraftValidationError,
)


class TestGate1SchemaVersion:
    """Testes de schema_version."""

    def test_valid_schema_version(self):
        """Schema version correto passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_missing_schema_version(self):
        """Schema version ausente falha."""
        data = {"project": "test"}
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False
        assert any("schema_version" in e.location for e in result.errors)

    def test_wrong_schema_version(self):
        """Schema version errado falha."""
        data = {
            "schema_version": "idl.v1",  # errado - deve ser idl_draft.v1
            "project": "test",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False
        assert any("INVALID_SCHEMA_VERSION" in e.error_type for e in result.errors)

    def test_invalid_schema_version_type(self):
        """Schema version não-string falha."""
        data = {
            "schema_version": 123,
            "project": "test",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False


class TestGate1ProjectField:
    """Testes do campo project."""

    def test_valid_project(self):
        """Project válido passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "meu_projeto",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_missing_project(self):
        """Project ausente falha."""
        data = {"schema_version": "idl_draft.v1"}
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False
        assert any("project" in e.location for e in result.errors)

    def test_empty_project(self):
        """Project vazio é aceito (validação de conteúdo é no compilador)."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        # GATE 1 valida estrutura, não conteúdo - project vazio é válido estruturalmente
        assert result.valid is True

    def test_project_invalid_type(self):
        """Project não-string falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": 123,
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False


class TestGate1SourceField:
    """Testes do campo source."""

    def test_valid_source_natural_text(self):
        """Source natural_text passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "source": "natural_text",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_valid_source_wizard(self):
        """Source wizard passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "source": "wizard",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_valid_source_imported(self):
        """Source imported passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "source": "imported",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_missing_source_uses_default(self):
        """Source ausente usa default."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_invalid_source(self):
        """Source inválido falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "source": "invalido",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False


class TestGate1Actors:
    """Testes de actors."""

    def test_empty_actors_ok(self):
        """Lista vazia de actors é válida."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "actors": [],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_valid_actor(self):
        """Actor válido passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "actors": [
                {"id": "admin", "role": "administrator", "permissions": ["read", "write"]}
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_actor_with_unknown_role(self):
        """Actor com role unknown passa em GATE 1."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "actors": [
                {"id": "user", "role": "unknown", "permissions": []}
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True  # GATE 1 aceita unknown

    def test_actor_missing_id(self):
        """Actor sem id falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "actors": [
                {"role": "admin", "permissions": []}
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False

    def test_duplicate_actor_ids(self):
        """IDs de actor duplicados falham."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "actors": [
                {"id": "admin", "role": "administrator"},
                {"id": "admin", "role": "other"},  # duplicado
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False
        assert any("DUPLICATE" in e.error_type for e in result.errors)

    def test_actors_not_list(self):
        """Actors não-lista falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "actors": "not_a_list",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False


class TestGate1Entities:
    """Testes de entities."""

    def test_empty_entities_ok(self):
        """Lista vazia de entities é válida."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "entities": [],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_valid_entity(self):
        """Entity válida passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "entities": [
                {
                    "id": "User",
                    "fields": [
                        {"name": "id", "type": "string", "required": True},
                        {"name": "email", "type": "string", "required": True},
                    ]
                }
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_entity_with_unknown_field_type(self):
        """Entity com field type unknown passa em GATE 1."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "entities": [
                {
                    "id": "User",
                    "fields": [
                        {"name": "data", "type": "unknown", "required": True},
                    ]
                }
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True  # GATE 1 aceita unknown

    def test_entity_with_unknown_required(self):
        """Entity com required unknown passa em GATE 1."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "entities": [
                {
                    "id": "User",
                    "fields": [
                        {"name": "data", "type": "string", "required": "unknown"},
                    ]
                }
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True  # GATE 1 aceita unknown

    def test_entity_missing_id(self):
        """Entity sem id falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "entities": [
                {"fields": []}
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False

    def test_duplicate_entity_ids(self):
        """IDs de entity duplicados falham."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "entities": [
                {"id": "User", "fields": []},
                {"id": "User", "fields": []},  # duplicado
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False
        assert any("DUPLICATE" in e.error_type for e in result.errors)

    def test_field_missing_name(self):
        """Field sem name falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "entities": [
                {
                    "id": "User",
                    "fields": [
                        {"type": "string", "required": True},  # sem name
                    ]
                }
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False


class TestGate1UseCases:
    """Testes de use_cases."""

    def test_empty_use_cases_ok(self):
        """Lista vazia de use_cases é válida."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "use_cases": [],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_valid_use_case(self):
        """Use case válido passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "use_cases": [
                {
                    "id": "UC001",
                    "actor": "admin",
                    "flow": [
                        {"step": 1, "action": "Open page"},
                        {"step": 2, "action": "Click button"},
                    ]
                }
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_use_case_with_unknown_actor(self):
        """Use case com actor unknown passa em GATE 1."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "use_cases": [
                {
                    "id": "UC001",
                    "actor": "unknown",
                    "flow": []
                }
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True  # GATE 1 aceita unknown

    def test_use_case_missing_id(self):
        """Use case sem id falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "use_cases": [
                {"actor": "admin", "flow": []}
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False

    def test_duplicate_use_case_ids(self):
        """IDs de use_case duplicados falham."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "use_cases": [
                {"id": "UC001", "actor": "admin", "flow": []},
                {"id": "UC001", "actor": "user", "flow": []},  # duplicado
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False
        assert any("DUPLICATE" in e.error_type for e in result.errors)


class TestGate1Integrations:
    """Testes de integrations."""

    def test_empty_integrations_ok(self):
        """Lista vazia de integrations é válida."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "integrations": [],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_valid_integration(self):
        """Integration válida passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "integrations": [
                {"system": "PaymentAPI", "type": "api"}
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_integration_with_unknown_type(self):
        """Integration com type unknown passa em GATE 1."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "integrations": [
                {"system": "ExternalService", "type": "unknown"}
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True  # GATE 1 aceita unknown

    def test_integration_missing_system(self):
        """Integration sem system falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "integrations": [
                {"type": "api"}
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False

    def test_duplicate_integration_systems(self):
        """Systems duplicados são permitidos (GATE 1 não valida duplicatas de integration)."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "integrations": [
                {"system": "PaymentAPI", "type": "api"},
                {"system": "PaymentAPI", "type": "db"},  # mesmo system, tipos diferentes
            ],
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        # Integrations podem ter mesmo system - GATE 1 não valida duplicatas aqui
        assert result.valid is True


class TestGate1NonFunctional:
    """Testes de non_functional."""

    def test_missing_non_functional_ok(self):
        """non_functional ausente é válido."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_valid_non_functional(self):
        """non_functional válido passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "non_functional": {
                "performance": "response < 200ms",
                "security": "HTTPS required",
            }
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_non_functional_with_unknown(self):
        """non_functional com unknown passa em GATE 1."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "non_functional": {
                "performance": "unknown",
                "security": "unknown",
            }
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True  # GATE 1 aceita unknown


class TestGate1AssumptionsAndQuestions:
    """Testes de assumptions e open_questions."""

    def test_valid_assumptions(self):
        """Assumptions lista de strings passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "assumptions": [
                "Users will have valid email",
                "System has internet access",
            ]
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_valid_open_questions(self):
        """Open_questions lista de strings passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "open_questions": [
                "Should we support multiple languages?",
                "What is the expected load?",
            ]
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_assumptions_not_list_fails(self):
        """Assumptions não-lista falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "assumptions": "not a list",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False

    def test_open_questions_not_list_fails(self):
        """Open_questions não-lista falha."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "test",
            "open_questions": {"question": "value"},
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is False


class TestGate1CompleteDocument:
    """Testes de documento completo."""

    def test_complete_valid_document(self):
        """Documento completo válido passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "ecommerce",
            "source": "wizard",
            "actors": [
                {"id": "customer", "role": "buyer", "permissions": ["browse", "purchase"]},
                {"id": "admin", "role": "administrator", "permissions": ["manage"]},
            ],
            "entities": [
                {
                    "id": "Product",
                    "fields": [
                        {"name": "id", "type": "string", "required": True},
                        {"name": "name", "type": "string", "required": True},
                        {"name": "price", "type": "decimal", "required": True},
                    ]
                },
                {
                    "id": "Order",
                    "fields": [
                        {"name": "id", "type": "string", "required": True},
                        {"name": "total", "type": "decimal", "required": True},
                    ]
                }
            ],
            "use_cases": [
                {
                    "id": "UC001_BrowseProducts",
                    "actor": "customer",
                    "flow": [
                        {"step": 1, "action": "Customer opens product catalog"},
                        {"step": 2, "action": "System displays products"},
                    ]
                }
            ],
            "integrations": [
                {"system": "PaymentGateway", "type": "api"},
                {"system": "InventoryDB", "type": "db"},
            ],
            "non_functional": {
                "performance": "p99 < 500ms",
                "security": "PCI-DSS compliant",
            },
            "assumptions": [
                "Payment gateway is available 99.9%",
            ],
            "open_questions": [
                "Support for multiple currencies?",
            ]
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True

    def test_minimal_valid_document(self):
        """Documento mínimo válido passa."""
        data = {
            "schema_version": "idl_draft.v1",
            "project": "minimal",
        }
        validator = DraftSchemaValidator()
        result = validator.validate(data)
        assert result.valid is True


class TestValidationResultFormat:
    """Testes do formato do resultado de validação."""

    def test_result_to_dict_success(self):
        """Resultado de sucesso serializa corretamente."""
        result = DraftValidationResult(valid=True, errors=[])
        d = result.to_dict()
        assert d["valid"] is True
        assert d["errors"] == []

    def test_result_to_dict_with_errors(self):
        """Resultado com erros serializa corretamente."""
        errors = [
            DraftValidationError(
                error_type="TEST_ERROR",
                message="Test reason",
                location="test.location",
            )
        ]
        result = DraftValidationResult(valid=False, errors=errors)
        d = result.to_dict()
        assert d["valid"] is False
        assert len(d["errors"]) == 1
        assert d["errors"][0]["error_type"] == "TEST_ERROR"
        assert d["errors"][0]["message"] == "Test reason"
        assert d["errors"][0]["location"] == "test.location"
