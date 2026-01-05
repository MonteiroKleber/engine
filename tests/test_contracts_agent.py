"""Testes para o Contracts Agent."""

import yaml
import pytest

from agents.contracts_agent import ContractsAgent


@pytest.fixture
def sample_ir():
    """Retorna um IR de exemplo com uma entidade."""
    return {
        "meta": {
            "project_name": "Sistema Teste",
            "version": "v1",
        },
        "domain": {
            "entities": [
                {
                    "name": "cliente",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "uuid", "required": True},
                        {"name": "nome", "type": "string", "required": True},
                        {"name": "email", "type": "string", "required": True},
                        {"name": "ativo", "type": "boolean", "required": False},
                    ],
                }
            ],
        },
        "api_intent": {
            "resources": ["cliente"],
        },
    }


@pytest.fixture
def multi_entity_ir():
    """Retorna um IR com múltiplas entidades."""
    return {
        "meta": {"project_name": "E-commerce"},
        "domain": {
            "entities": [
                {
                    "name": "produto",
                    "fields": [
                        {"name": "id", "type": "uuid", "required": True},
                        {"name": "nome", "type": "string", "required": True},
                        {"name": "preco", "type": "number", "required": True},
                    ],
                },
                {
                    "name": "pedido",
                    "fields": [
                        {"name": "id", "type": "uuid", "required": True},
                        {"name": "total", "type": "number", "required": True},
                    ],
                },
            ],
        },
    }


class TestContractsAgentBasic:
    """Testes básicos do ContractsAgent."""

    def test_generate_contracts_returns_tuple(self, sample_ir):
        """generate_contracts deve retornar tuple (yaml_str, dict)."""
        agent = ContractsAgent()
        result = agent.generate_contracts(sample_ir)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], dict)

    def test_openapi_is_valid_yaml(self, sample_ir):
        """OpenAPI retornado deve ser YAML válido."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)

        # Deve parsear sem erro
        openapi = yaml.safe_load(openapi_yaml)
        assert isinstance(openapi, dict)

    def test_rbac_has_required_fields(self, sample_ir):
        """RBAC deve ter roles e permissions."""
        agent = ContractsAgent()
        _, rbac = agent.generate_contracts(sample_ir)

        assert "roles" in rbac
        assert "permissions" in rbac


class TestOpenAPIGeneration:
    """Testes de geração do OpenAPI."""

    def test_openapi_has_version(self, sample_ir):
        """OpenAPI deve ter campo 'openapi'."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        assert "openapi" in openapi
        assert openapi["openapi"] == "3.0.0"

    def test_openapi_has_info(self, sample_ir):
        """OpenAPI deve ter campo 'info' com title e version."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        assert "info" in openapi
        assert "title" in openapi["info"]
        assert "version" in openapi["info"]

    def test_openapi_has_paths(self, sample_ir):
        """OpenAPI deve ter campo 'paths'."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        assert "paths" in openapi
        assert len(openapi["paths"]) > 0

    def test_one_entity_generates_5_operations(self, sample_ir):
        """Uma entidade deve gerar 5 operações CRUD."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        # Contar operações (métodos HTTP)
        operations = 0
        for path, methods in openapi["paths"].items():
            for method in methods:
                if method in ["get", "post", "put", "patch", "delete"]:
                    operations += 1

        assert operations == 5

    def test_crud_paths_correct(self, sample_ir):
        """Paths CRUD devem seguir padrão /api/{plural} e /api/{plural}/{id}."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        paths = list(openapi["paths"].keys())
        assert "/api/clientes" in paths
        assert "/api/clientes/{id}" in paths

    def test_collection_path_has_get_and_post(self, sample_ir):
        """Path de coleção deve ter GET e POST."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        collection = openapi["paths"]["/api/clientes"]
        assert "get" in collection
        assert "post" in collection

    def test_item_path_has_get_put_delete(self, sample_ir):
        """Path de item deve ter GET, PUT e DELETE."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        item = openapi["paths"]["/api/clientes/{id}"]
        assert "get" in item
        assert "put" in item
        assert "delete" in item


class TestOperationIds:
    """Testes de operationId."""

    def test_operations_have_operation_id(self, sample_ir):
        """Todas operações devem ter operationId."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        for path, methods in openapi["paths"].items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "patch", "delete"]:
                    assert "operationId" in operation

    def test_operation_ids_follow_pattern(self, sample_ir):
        """operationIds devem seguir padrão list/create/get/update/delete."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        expected_ops = {"listCliente", "createCliente", "getCliente", "updateCliente", "deleteCliente"}
        found_ops = set()

        for path, methods in openapi["paths"].items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "patch", "delete"]:
                    found_ops.add(operation["operationId"])

        assert found_ops == expected_ops


class TestTags:
    """Testes de tags."""

    def test_operations_have_tags(self, sample_ir):
        """Todas operações devem ter tags."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        for path, methods in openapi["paths"].items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "patch", "delete"]:
                    assert "tags" in operation
                    assert len(operation["tags"]) > 0

    def test_tags_match_entity(self, sample_ir):
        """Tags devem corresponder à entidade."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        for path, methods in openapi["paths"].items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "patch", "delete"]:
                    assert "Cliente" in operation["tags"]


class TestResponses:
    """Testes de responses."""

    def test_get_has_200_response(self, sample_ir):
        """GET deve ter response 200."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        get_op = openapi["paths"]["/api/clientes"]["get"]
        assert "200" in get_op["responses"]

    def test_post_has_201_response(self, sample_ir):
        """POST deve ter response 201."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        post_op = openapi["paths"]["/api/clientes"]["post"]
        assert "201" in post_op["responses"]

    def test_all_operations_have_400_and_500(self, sample_ir):
        """Todas operações devem ter responses 400 e 500."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        for path, methods in openapi["paths"].items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "patch", "delete"]:
                    assert "400" in operation["responses"]
                    assert "500" in operation["responses"]


class TestSchemas:
    """Testes de schemas."""

    def test_components_schemas_exist(self, sample_ir):
        """Deve existir components/schemas."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        assert "components" in openapi
        assert "schemas" in openapi["components"]

    def test_entity_schema_exists(self, sample_ir):
        """Schema da entidade deve existir."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        assert "Cliente" in openapi["components"]["schemas"]

    def test_schema_has_properties(self, sample_ir):
        """Schema deve ter properties."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        schema = openapi["components"]["schemas"]["Cliente"]
        assert "properties" in schema
        assert "id" in schema["properties"]
        assert "nome" in schema["properties"]
        assert "email" in schema["properties"]

    def test_id_is_always_string(self, sample_ir):
        """Campo id deve ser sempre string no schema."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        schema = openapi["components"]["schemas"]["Cliente"]
        assert schema["properties"]["id"]["type"] == "string"


class TestRBACGeneration:
    """Testes de geração do RBAC."""

    def test_rbac_has_authenticated_role(self, sample_ir):
        """RBAC deve ter role 'authenticated'."""
        agent = ContractsAgent()
        _, rbac = agent.generate_contracts(sample_ir)

        assert "authenticated" in rbac["roles"]

    def test_rbac_has_admin_role(self, sample_ir):
        """RBAC deve ter role 'admin'."""
        agent = ContractsAgent()
        _, rbac = agent.generate_contracts(sample_ir)

        assert "admin" in rbac["roles"]

    def test_rbac_has_permissions_for_all_operations(self, sample_ir):
        """RBAC deve ter permissions para todas as operações."""
        agent = ContractsAgent()
        openapi_yaml, rbac = agent.generate_contracts(sample_ir)
        openapi = yaml.safe_load(openapi_yaml)

        # Coletar todos operationIds do OpenAPI
        operation_ids = set()
        for path, methods in openapi["paths"].items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "patch", "delete"]:
                    operation_ids.add(operation["operationId"])

        # Verificar que todos estão no RBAC
        rbac_op_ids = {p["operation_id"] for p in rbac["permissions"]}
        assert operation_ids == rbac_op_ids

    def test_all_permissions_require_authenticated(self, sample_ir):
        """Todas permissions devem requerer 'authenticated'."""
        agent = ContractsAgent()
        _, rbac = agent.generate_contracts(sample_ir)

        for permission in rbac["permissions"]:
            assert permission["required_role"] == "authenticated"

    def test_one_entity_generates_5_permissions(self, sample_ir):
        """Uma entidade deve gerar 5 permissions."""
        agent = ContractsAgent()
        _, rbac = agent.generate_contracts(sample_ir)

        assert len(rbac["permissions"]) == 5


class TestMultipleEntities:
    """Testes com múltiplas entidades."""

    def test_multiple_entities_generate_multiple_paths(self, multi_entity_ir):
        """Múltiplas entidades devem gerar múltiplos paths."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(multi_entity_ir)
        openapi = yaml.safe_load(openapi_yaml)

        # 2 entidades * 2 paths cada = 4 paths
        assert len(openapi["paths"]) == 4

    def test_multiple_entities_generate_10_operations(self, multi_entity_ir):
        """2 entidades devem gerar 10 operações."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(multi_entity_ir)
        openapi = yaml.safe_load(openapi_yaml)

        operations = 0
        for path, methods in openapi["paths"].items():
            for method in methods:
                if method in ["get", "post", "put", "patch", "delete"]:
                    operations += 1

        assert operations == 10

    def test_multiple_entities_generate_10_permissions(self, multi_entity_ir):
        """2 entidades devem gerar 10 permissions."""
        agent = ContractsAgent()
        _, rbac = agent.generate_contracts(multi_entity_ir)

        assert len(rbac["permissions"]) == 10

    def test_multiple_schemas_generated(self, multi_entity_ir):
        """Múltiplas entidades devem gerar múltiplos schemas."""
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(multi_entity_ir)
        openapi = yaml.safe_load(openapi_yaml)

        assert "Produto" in openapi["components"]["schemas"]
        assert "Pedido" in openapi["components"]["schemas"]


class TestEdgeCases:
    """Testes de casos especiais."""

    def test_empty_entities_generates_empty_paths(self):
        """IR sem entidades deve gerar paths vazio."""
        ir = {
            "meta": {"project_name": "Empty"},
            "domain": {"entities": []},
        }
        agent = ContractsAgent()
        openapi_yaml, rbac = agent.generate_contracts(ir)
        openapi = yaml.safe_load(openapi_yaml)

        assert openapi["paths"] == {}
        assert rbac["permissions"] == []

    def test_entity_without_fields(self):
        """Entidade sem fields deve gerar schema vazio."""
        ir = {
            "meta": {"project_name": "Minimal"},
            "domain": {
                "entities": [
                    {"name": "item", "fields": []}
                ]
            },
        }
        agent = ContractsAgent()
        openapi_yaml, _ = agent.generate_contracts(ir)
        openapi = yaml.safe_load(openapi_yaml)

        schema = openapi["components"]["schemas"]["Item"]
        assert schema["properties"] == {}
