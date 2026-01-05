"""Testes para o schema IR."""

import json
from pathlib import Path

import pytest
import jsonschema


@pytest.fixture
def ir_schema():
    """Carrega o schema IR."""
    schema_path = Path(__file__).parent.parent / "schemas" / "ir.schema.json"
    with open(schema_path) as f:
        return json.load(f)


@pytest.fixture
def valid_ir():
    """Retorna um IR válido para testes."""
    return {
        "meta": {
            "project_name": "Sistema Teste",
            "version": "1.0.0",
            "created_at": "2024-01-01T00:00:00Z",
            "srs_version": "v1",
        },
        "domain": {
            "entities": [
                {
                    "name": "empresa",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "uuid", "required": True, "unique": True, "indexed": True},
                        {"name": "nome", "type": "string", "required": True, "unique": False, "indexed": False},
                        {"name": "cnpj", "type": "string", "required": True, "unique": True, "indexed": True},
                    ],
                }
            ],
            "relations": [],
            "workflows": [],
            "rules": [
                {"id": "BR-001", "description": "CNPJ deve ser único", "severity": "ERROR"}
            ],
        },
        "api_intent": {
            "resources": ["empresa"],
            "operations": [
                {"resource": "empresa", "method": "GET", "path": "/api/empresas"},
                {"resource": "empresa", "method": "POST", "path": "/api/empresas"},
            ],
        },
        "ui": {
            "pages": [
                {"path": "/app/empresa/list", "title": "Listar Empresas", "components": ["table"], "actions": ["list", "view"]},
                {"path": "/app/empresa/new", "title": "Nova Empresa", "components": ["form"], "actions": ["create"]},
                {"path": "/app/empresa/:id", "title": "Detalhes Empresa", "components": ["form"], "actions": ["view", "update", "delete"]},
            ]
        },
        "nfr": {
            "security": {
                "auth_required": True,
                "audit_log_required": True,
            },
            "performance": {
                "max_response_time_ms": 2000,
            },
        },
    }


class TestIRSchemaLoading:
    """Testes de carregamento do schema IR."""

    def test_ir_schema_loads_without_error(self, ir_schema):
        """Schema IR deve carregar sem erro."""
        assert ir_schema is not None
        assert "$schema" in ir_schema
        assert ir_schema["$id"] == "ir.schema.json"

    def test_ir_schema_has_required_sections(self, ir_schema):
        """Schema IR deve ter as seções obrigatórias."""
        assert "properties" in ir_schema
        properties = ir_schema["properties"]

        required_sections = ["meta", "domain", "api_intent", "ui", "nfr"]
        for section in required_sections:
            assert section in properties, f"Seção '{section}' ausente no schema"

    def test_ir_schema_required_fields(self, ir_schema):
        """Schema IR deve exigir campos obrigatórios."""
        assert "required" in ir_schema
        assert set(ir_schema["required"]) == {"meta", "domain", "api_intent", "ui", "nfr"}


class TestIRValidation:
    """Testes de validação de IR contra schema."""

    def test_valid_ir_passes_validation(self, ir_schema, valid_ir):
        """IR válido deve passar na validação."""
        jsonschema.validate(instance=valid_ir, schema=ir_schema)

    def test_ir_without_meta_fails(self, ir_schema, valid_ir):
        """IR sem meta deve falhar."""
        del valid_ir["meta"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_ir, schema=ir_schema)

    def test_ir_without_domain_fails(self, ir_schema, valid_ir):
        """IR sem domain deve falhar."""
        del valid_ir["domain"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_ir, schema=ir_schema)

    def test_ir_without_entities_fails(self, ir_schema, valid_ir):
        """IR sem entities no domain deve falhar."""
        del valid_ir["domain"]["entities"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_ir, schema=ir_schema)

    def test_ir_with_empty_entities_fails(self, ir_schema, valid_ir):
        """IR com entities vazio deve falhar (minItems: 1)."""
        valid_ir["domain"]["entities"] = []
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_ir, schema=ir_schema)

    def test_ir_without_api_intent_fails(self, ir_schema, valid_ir):
        """IR sem api_intent deve falhar."""
        del valid_ir["api_intent"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_ir, schema=ir_schema)

    def test_ir_without_ui_fails(self, ir_schema, valid_ir):
        """IR sem ui deve falhar."""
        del valid_ir["ui"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_ir, schema=ir_schema)

    def test_ir_without_nfr_fails(self, ir_schema, valid_ir):
        """IR sem nfr deve falhar."""
        del valid_ir["nfr"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_ir, schema=ir_schema)

    def test_ir_entity_without_name_fails(self, ir_schema, valid_ir):
        """Entidade sem name deve falhar."""
        del valid_ir["domain"]["entities"][0]["name"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_ir, schema=ir_schema)

    def test_ir_entity_without_fields_fails(self, ir_schema, valid_ir):
        """Entidade sem fields deve falhar."""
        del valid_ir["domain"]["entities"][0]["fields"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_ir, schema=ir_schema)


class TestIRGeneratedByDomainModeler:
    """Testes de IR gerado pelo DomainModeler a partir de SRS."""

    def test_domain_modeler_generates_valid_ir(self, ir_schema):
        """IR gerado pelo DomainModeler deve ser válido contra schema."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler

        # Gerar SRS
        normalizer = Normalizer()
        analyst = RequirementsAnalyst()

        raw_input = "Sistema de cadastro de empresas com nome, cnpj e endereço"
        normalized = normalizer.normalize(raw_input)
        srs = analyst.generate_srs(normalized, "Sistema Empresas")

        # Gerar IR
        modeler = DomainModeler()
        ir = modeler.generate_ir(srs)

        # Validar IR contra schema
        jsonschema.validate(instance=ir, schema=ir_schema)

    def test_domain_modeler_ir_has_entities_from_srs(self, ir_schema):
        """IR gerado deve ter entidades baseadas no SRS."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()

        normalized = normalizer.normalize("sistema de produtos e pedidos")
        srs = analyst.generate_srs(normalized, "Sistema Vendas")
        ir = modeler.generate_ir(srs)

        # Deve ter entidades
        assert len(ir["domain"]["entities"]) >= 1

        # Validar contra schema
        jsonschema.validate(instance=ir, schema=ir_schema)

    def test_domain_modeler_ir_without_entities_fails_validation(self, ir_schema):
        """IR gerado sem entidades deve falhar validação."""
        from agents.domain_modeler import DomainModeler

        modeler = DomainModeler()

        # SRS sem data_requirements
        srs_empty = {
            "title": "Sistema Vazio",
            "meta": {"project_name": "Vazio"},
        }

        ir = modeler.generate_ir(srs_empty)

        # Deve ter entities vazio (falha validação)
        assert ir["domain"]["entities"] == []

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=ir, schema=ir_schema)

    def test_domain_modeler_ir_has_ui_pages(self, ir_schema):
        """IR gerado deve ter páginas UI CRUD."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()

        normalized = normalizer.normalize("cadastro de clientes")
        srs = analyst.generate_srs(normalized, "CRM")
        ir = modeler.generate_ir(srs)

        # Deve ter páginas UI
        assert len(ir["ui"]["pages"]) >= 1

        # Cada entidade deve ter 3 páginas (list, new, :id)
        entity_count = len(ir["domain"]["entities"])
        assert len(ir["ui"]["pages"]) >= entity_count * 3

    def test_domain_modeler_ir_has_api_resources(self, ir_schema):
        """IR gerado deve ter recursos na API."""
        from intake.normalizer import Normalizer
        from intake.req_analyst import RequirementsAnalyst
        from agents.domain_modeler import DomainModeler

        normalizer = Normalizer()
        analyst = RequirementsAnalyst()
        modeler = DomainModeler()

        normalized = normalizer.normalize("sistema de produtos")
        srs = analyst.generate_srs(normalized, "Loja")
        ir = modeler.generate_ir(srs)

        # Deve ter resources
        assert len(ir["api_intent"]["resources"]) >= 1

        # Resources devem corresponder a entidades
        entity_names = [e["name"] for e in ir["domain"]["entities"]]
        for resource in ir["api_intent"]["resources"]:
            assert resource in entity_names
