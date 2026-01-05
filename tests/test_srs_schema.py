"""Testes para validação do schema SRS."""

import json
from pathlib import Path

import pytest
import jsonschema

from intake.normalizer import Normalizer
from intake.req_analyst import RequirementsAnalyst


@pytest.fixture
def srs_schema():
    """Carrega o schema SRS."""
    schema_path = Path(__file__).parent.parent / "schemas" / "srs.schema.json"
    with open(schema_path) as f:
        return json.load(f)


@pytest.fixture
def valid_srs():
    """Retorna um SRS válido para testes."""
    return {
        "id": "srs-001",
        "title": "Sistema de Gestão",
        "version": "1.0.0",
        "requirements": [
            {
                "id": "REQ-001",
                "description": "O sistema deve permitir login de usuários",
                "priority": "high",
                "type": "functional",
            },
            {
                "id": "REQ-002",
                "description": "O sistema deve responder em menos de 2 segundos",
                "priority": "medium",
                "type": "non-functional",
            },
        ],
        "metadata": {
            "created_at": "2024-01-01T00:00:00Z",
            "language": "pt-BR",
        },
    }


class TestSRSSchema:
    """Testes do schema SRS."""

    def test_valid_srs_passes_validation(self, srs_schema, valid_srs):
        """SRS válido deve passar na validação."""
        jsonschema.validate(instance=valid_srs, schema=srs_schema)

    def test_srs_without_id_fails(self, srs_schema, valid_srs):
        """SRS sem id deve falhar."""
        del valid_srs["id"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_srs, schema=srs_schema)

    def test_srs_without_title_fails(self, srs_schema, valid_srs):
        """SRS sem title deve falhar."""
        del valid_srs["title"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_srs, schema=srs_schema)

    def test_srs_without_requirements_fails(self, srs_schema, valid_srs):
        """SRS sem requirements deve falhar."""
        del valid_srs["requirements"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_srs, schema=srs_schema)

    def test_requirement_invalid_priority_fails(self, srs_schema, valid_srs):
        """Requisito com prioridade inválida deve falhar."""
        valid_srs["requirements"][0]["priority"] = "critical"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_srs, schema=srs_schema)

    def test_empty_requirements_is_valid(self, srs_schema, valid_srs):
        """SRS com lista vazia de requirements é válido."""
        valid_srs["requirements"] = []
        jsonschema.validate(instance=valid_srs, schema=srs_schema)


class TestGeneratedSRSValidation:
    """Testes de validação de SRS gerado pelo sistema."""

    def test_generated_srs_is_valid(self, srs_schema):
        """SRS gerado pelo RequirementsAnalyst deve ser válido contra schema."""
        normalizer = Normalizer()
        analyst = RequirementsAnalyst()

        # Gerar SRS a partir de input
        raw_input = "Sistema de gestão de produtos com cadastro e listagem"
        normalized = normalizer.normalize(raw_input)
        srs = analyst.generate_srs(normalized, "Sistema de Produtos")

        # Validar contra schema
        jsonschema.validate(instance=srs, schema=srs_schema)

    def test_generated_srs_has_required_fields(self, srs_schema):
        """SRS gerado deve ter todos os campos obrigatórios."""
        normalizer = Normalizer()
        analyst = RequirementsAnalyst()

        normalized = normalizer.normalize("qualquer input")
        srs = analyst.generate_srs(normalized, "Meu Sistema")

        # Verificar campos obrigatórios
        assert "id" in srs
        assert "title" in srs
        assert "requirements" in srs
        assert isinstance(srs["requirements"], list)

    def test_generated_srs_requirements_are_valid(self, srs_schema):
        """Requisitos gerados devem ter estrutura válida."""
        normalizer = Normalizer()
        analyst = RequirementsAnalyst()

        normalized = normalizer.normalize("cadastrar e listar produtos")
        srs = analyst.generate_srs(normalized, "Sistema")

        # Verificar cada requisito
        for req in srs["requirements"]:
            assert "id" in req
            assert "description" in req
            assert "priority" in req
            assert req["priority"] in ["high", "medium", "low"]

    def test_generated_srs_with_various_inputs(self, srs_schema):
        """SRS gerado com vários tipos de input deve ser válido."""
        normalizer = Normalizer()
        analyst = RequirementsAnalyst()

        inputs = [
            "sistema simples",
            "quero cadastrar usuários e listar pedidos",
            "   texto com espaços   ",
            "Sistema de CRM\ncom múltiplas linhas\ne funcionalidades",
        ]

        for raw_input in inputs:
            normalized = normalizer.normalize(raw_input)
            srs = analyst.generate_srs(normalized, "Sistema Teste")

            # Cada SRS gerado deve ser válido
            jsonschema.validate(instance=srs, schema=srs_schema)
