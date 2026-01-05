"""Testes para o OpenAPI validator."""

import pytest

from validators.openapi_validator import OpenAPIValidator, ValidationReport, validate_openapi


@pytest.fixture
def valid_openapi():
    """Retorna um OpenAPI válido mínimo."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Test API",
            "version": "1.0.0"
        },
        "paths": {
            "/users": {
                "get": {
                    "operationId": "listUsers",
                    "tags": ["users"],
                    "responses": {
                        "200": {
                            "description": "Success"
                        }
                    }
                }
            }
        }
    }


class TestOpenAPIValidatorBasic:
    """Testes básicos do OpenAPIValidator."""

    def test_valid_openapi_passes(self, valid_openapi):
        """OpenAPI válido deve passar validação."""
        report = validate_openapi(valid_openapi)

        assert report.ok is True
        assert len(report.errors) == 0
        assert len(report.missing_fields) == 0

    def test_validate_openapi_returns_validation_report(self, valid_openapi):
        """validate_openapi deve retornar ValidationReport."""
        report = validate_openapi(valid_openapi)

        assert isinstance(report, ValidationReport)
        assert hasattr(report, "ok")
        assert hasattr(report, "errors")
        assert hasattr(report, "missing_fields")

    def test_validation_report_to_dict(self, valid_openapi):
        """ValidationReport deve ter método to_dict."""
        report = validate_openapi(valid_openapi)
        result = report.to_dict()

        assert isinstance(result, dict)
        assert "ok" in result
        assert "errors" in result
        assert "missing_fields" in result


class TestRequiredFields:
    """Testes de campos obrigatórios de nível superior."""

    def test_openapi_without_openapi_field_fails(self):
        """OpenAPI sem campo 'openapi' deve falhar."""
        invalid = {
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "tags": ["users"],
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert any("openapi" in e for e in report.errors)
        assert "openapi" in report.missing_fields

    def test_openapi_without_paths_fails(self):
        """OpenAPI sem campo 'paths' deve falhar."""
        invalid = {
            "openapi": "3.0.0"
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert any("paths" in e for e in report.errors)
        assert "paths" in report.missing_fields

    def test_openapi_with_empty_dict_fails(self):
        """OpenAPI vazio deve falhar."""
        report = validate_openapi({})

        assert report.ok is False
        assert len(report.errors) >= 2  # openapi e paths


class TestPathsNotEmpty:
    """Testes da regra: paths não pode estar vazio."""

    def test_empty_paths_fails(self):
        """paths vazio deve falhar."""
        invalid = {
            "openapi": "3.0.0",
            "paths": {}
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert any("vazio" in e or "empty" in e.lower() for e in report.errors)

    def test_paths_with_one_endpoint_passes(self, valid_openapi):
        """paths com pelo menos um endpoint deve passar."""
        report = validate_openapi(valid_openapi)

        assert report.ok is True


class TestPathNotEmpty:
    """Testes da regra: path não pode estar vazio (sem métodos)."""

    def test_path_without_methods_fails(self):
        """Path sem métodos HTTP deve falhar."""
        invalid = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {}
            }
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert any("/users" in e for e in report.errors)

    def test_path_with_only_parameters_fails(self):
        """Path com apenas 'parameters' (sem métodos) deve falhar."""
        invalid = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "parameters": [
                        {"name": "id", "in": "query"}
                    ]
                }
            }
        }
        report = validate_openapi(invalid)

        assert report.ok is False


class TestOperationRequiredFields:
    """Testes de campos obrigatórios em operações."""

    def test_operation_without_operation_id_fails(self):
        """Operação sem operationId deve falhar."""
        invalid = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        "tags": ["users"],
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert any("operationId" in e for e in report.errors)

    def test_operation_without_responses_fails(self):
        """Operação sem responses deve falhar."""
        invalid = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "tags": ["users"]
                    }
                }
            }
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert any("responses" in e for e in report.errors)

    def test_operation_without_tags_fails(self):
        """Operação sem tags deve falhar."""
        invalid = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert any("tags" in e for e in report.errors)

    def test_operation_with_empty_tags_fails(self):
        """Operação com tags vazio deve falhar."""
        invalid = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "tags": [],
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert any("tags" in e for e in report.errors)


class TestMultiplePaths:
    """Testes com múltiplos paths."""

    def test_multiple_valid_paths_passes(self):
        """Múltiplos paths válidos devem passar."""
        valid = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "tags": ["users"],
                        "responses": {"200": {"description": "OK"}}
                    },
                    "post": {
                        "operationId": "createUser",
                        "tags": ["users"],
                        "responses": {"201": {"description": "Created"}}
                    }
                },
                "/products": {
                    "get": {
                        "operationId": "listProducts",
                        "tags": ["products"],
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        report = validate_openapi(valid)

        assert report.ok is True

    def test_one_invalid_path_fails_all(self):
        """Um path inválido deve falhar toda validação."""
        invalid = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "tags": ["users"],
                        "responses": {"200": {"description": "OK"}}
                    }
                },
                "/products": {
                    "get": {
                        # Falta operationId
                        "tags": ["products"],
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert any("/products" in e for e in report.errors)


class TestHTTPMethods:
    """Testes com diferentes métodos HTTP."""

    def test_all_http_methods_valid(self):
        """Todos os métodos HTTP válidos devem funcionar."""
        valid = {
            "openapi": "3.0.0",
            "paths": {
                "/resource": {
                    "get": {
                        "operationId": "getResource",
                        "tags": ["resource"],
                        "responses": {"200": {"description": "OK"}}
                    },
                    "post": {
                        "operationId": "createResource",
                        "tags": ["resource"],
                        "responses": {"201": {"description": "Created"}}
                    },
                    "put": {
                        "operationId": "updateResource",
                        "tags": ["resource"],
                        "responses": {"200": {"description": "OK"}}
                    },
                    "patch": {
                        "operationId": "patchResource",
                        "tags": ["resource"],
                        "responses": {"200": {"description": "OK"}}
                    },
                    "delete": {
                        "operationId": "deleteResource",
                        "tags": ["resource"],
                        "responses": {"204": {"description": "No Content"}}
                    }
                }
            }
        }
        report = validate_openapi(valid)

        assert report.ok is True


class TestOpenAPIValidatorClass:
    """Testes da classe OpenAPIValidator."""

    def test_validator_instantiates(self):
        """OpenAPIValidator deve instanciar sem erro."""
        validator = OpenAPIValidator()
        assert validator is not None

    def test_validator_validate_method(self, valid_openapi):
        """Método validate deve funcionar."""
        validator = OpenAPIValidator()
        report = validator.validate(valid_openapi)

        assert isinstance(report, ValidationReport)
        assert report.ok is True


class TestComplexOpenAPIScenarios:
    """Testes de cenários complexos."""

    def test_openapi_with_path_parameters(self):
        """OpenAPI com path parameters deve passar."""
        valid = {
            "openapi": "3.0.0",
            "paths": {
                "/users/{id}": {
                    "get": {
                        "operationId": "getUser",
                        "tags": ["users"],
                        "parameters": [
                            {"name": "id", "in": "path", "required": True}
                        ],
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        report = validate_openapi(valid)

        assert report.ok is True

    def test_openapi_with_multiple_tags(self):
        """OpenAPI com múltiplas tags deve passar."""
        valid = {
            "openapi": "3.0.0",
            "paths": {
                "/admin/users": {
                    "get": {
                        "operationId": "adminListUsers",
                        "tags": ["admin", "users"],
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }
        report = validate_openapi(valid)

        assert report.ok is True

    def test_missing_fields_are_reported(self):
        """Campos faltantes devem ser reportados em missing_fields."""
        invalid = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        # Falta operationId, responses e tags
                    }
                }
            }
        }
        report = validate_openapi(invalid)

        assert report.ok is False
        assert len(report.missing_fields) >= 3
