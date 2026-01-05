"""Testes para o Planner Agent."""

import pytest

from agents.planner_agent import PlannerAgent
from validators.plan_validator import validate_plan


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
                    ],
                }
            ],
        },
        "api_intent": {"resources": ["cliente"]},
        "ui": {"pages": []},
        "nfr": {"security": {"auth_required": True}},
    }


@pytest.fixture
def multi_entity_ir():
    """Retorna um IR com múltiplas entidades."""
    return {
        "meta": {"project_name": "E-commerce", "version": "v2"},
        "domain": {
            "entities": [
                {
                    "name": "produto",
                    "fields": [
                        {"name": "id", "type": "uuid", "required": True},
                        {"name": "nome", "type": "string", "required": True},
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
        "api_intent": {"resources": ["produto", "pedido"]},
        "ui": {"pages": []},
        "nfr": {},
    }


@pytest.fixture
def sample_openapi():
    """Retorna um OpenAPI de exemplo."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/api/clientes": {
                "get": {"operationId": "listCliente", "responses": {"200": {}}},
                "post": {"operationId": "createCliente", "responses": {"201": {}}},
            },
            "/api/clientes/{id}": {
                "get": {"operationId": "getCliente", "responses": {"200": {}}},
                "put": {"operationId": "updateCliente", "responses": {"200": {}}},
                "delete": {"operationId": "deleteCliente", "responses": {"204": {}}},
            },
        },
        "components": {"schemas": {"Cliente": {"type": "object"}}},
    }


@pytest.fixture
def sample_rbac():
    """Retorna um RBAC de exemplo."""
    return {
        "roles": ["authenticated", "admin"],
        "permissions": [
            {"operation_id": "listCliente", "required_role": "authenticated"},
            {"operation_id": "createCliente", "required_role": "authenticated"},
            {"operation_id": "getCliente", "required_role": "authenticated"},
            {"operation_id": "updateCliente", "required_role": "authenticated"},
            {"operation_id": "deleteCliente", "required_role": "authenticated"},
        ],
    }


class TestPlannerAgentBasic:
    """Testes básicos do PlannerAgent."""

    def test_generate_plan_returns_dict(self, sample_ir, sample_openapi, sample_rbac):
        """generate_plan deve retornar dict."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        assert isinstance(plan, dict)

    def test_plan_has_meta(self, sample_ir, sample_openapi, sample_rbac):
        """Plan deve ter meta."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        assert "meta" in plan
        assert "version" in plan["meta"]
        assert "strategy" in plan["meta"]

    def test_plan_has_tasks(self, sample_ir, sample_openapi, sample_rbac):
        """Plan deve ter tasks."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        assert "tasks" in plan
        assert len(plan["tasks"]) > 0

    def test_plan_passes_validation(self, sample_ir, sample_openapi, sample_rbac):
        """Plan gerado deve passar validação."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        report = validate_plan(plan)
        assert report.ok is True, f"Validation failed: {report.errors}"


class TestPlanMeta:
    """Testes do meta do plan."""

    def test_meta_has_strategy_patch_only(self, sample_ir, sample_openapi, sample_rbac):
        """Strategy deve ser PATCH_ONLY."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        assert plan["meta"]["strategy"] == "PATCH_ONLY"

    def test_meta_has_ir_version(self, sample_ir, sample_openapi, sample_rbac):
        """Meta deve ter ir_version."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        assert plan["meta"]["ir_version"] == "v1"

    def test_meta_has_project_name(self, sample_ir, sample_openapi, sample_rbac):
        """Meta deve ter project_name."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        assert plan["meta"]["project_name"] == "Sistema Teste"

    def test_meta_has_created_at(self, sample_ir, sample_openapi, sample_rbac):
        """Meta deve ter created_at."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        assert "created_at" in plan["meta"]


class TestTaskGeneration:
    """Testes de geração de tasks."""

    def test_one_entity_generates_8_tasks(self, sample_ir, sample_openapi, sample_rbac):
        """Uma entidade deve gerar 8 tasks."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        assert len(plan["tasks"]) == 8

    def test_two_entities_generate_16_tasks(self, multi_entity_ir, sample_openapi, sample_rbac):
        """Duas entidades devem gerar 16 tasks."""
        agent = PlannerAgent()
        plan = agent.generate_plan(multi_entity_ir, sample_openapi, sample_rbac)

        assert len(plan["tasks"]) == 16

    def test_tasks_have_unique_ids(self, sample_ir, sample_openapi, sample_rbac):
        """Todos os task ids devem ser únicos."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        ids = [t["id"] for t in plan["tasks"]]
        assert len(ids) == len(set(ids))

    def test_tasks_have_sequential_order(self, sample_ir, sample_openapi, sample_rbac):
        """Orders devem ser sequenciais 1..N."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        orders = [t["order"] for t in plan["tasks"]]
        expected = list(range(1, len(orders) + 1))
        assert sorted(orders) == expected


class TestTaskStructure:
    """Testes da estrutura das tasks."""

    def test_tasks_have_files(self, sample_ir, sample_openapi, sample_rbac):
        """Todas tasks devem ter files não vazio."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        for task in plan["tasks"]:
            assert "files" in task
            assert len(task["files"]) > 0

    def test_tasks_have_acceptance(self, sample_ir, sample_openapi, sample_rbac):
        """Todas tasks devem ter acceptance não vazio."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        for task in plan["tasks"]:
            assert "acceptance" in task
            assert len(task["acceptance"]) > 0

    def test_tasks_have_title(self, sample_ir, sample_openapi, sample_rbac):
        """Todas tasks devem ter title."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        for task in plan["tasks"]:
            assert "title" in task
            assert len(task["title"]) > 0


class TestTaskOrder:
    """Testes da ordem das tasks."""

    def test_migration_is_first_for_entity(self, sample_ir, sample_openapi, sample_rbac):
        """Migration deve ser a primeira task."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        first_task = plan["tasks"][0]
        assert "migration" in first_task["id"]

    def test_model_is_second_for_entity(self, sample_ir, sample_openapi, sample_rbac):
        """Model deve ser a segunda task."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        second_task = plan["tasks"][1]
        assert "model" in second_task["id"]

    def test_repository_is_third_for_entity(self, sample_ir, sample_openapi, sample_rbac):
        """Repository deve ser a terceira task."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        third_task = plan["tasks"][2]
        assert "repository" in third_task["id"]

    def test_api_client_is_last_for_entity(self, sample_ir, sample_openapi, sample_rbac):
        """API client deve ser a última task."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        last_task = plan["tasks"][-1]
        assert "api_client" in last_task["id"]


class TestTaskDependencies:
    """Testes de dependências entre tasks."""

    def test_model_depends_on_migration(self, sample_ir, sample_openapi, sample_rbac):
        """Model deve depender de migration."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        model_task = next(t for t in plan["tasks"] if "model" in t["id"])
        assert "depends_on" in model_task
        assert any("migration" in dep for dep in model_task["depends_on"])

    def test_repository_depends_on_model(self, sample_ir, sample_openapi, sample_rbac):
        """Repository deve depender de model."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        repo_task = next(t for t in plan["tasks"] if "repository" in t["id"])
        assert "depends_on" in repo_task
        assert any("model" in dep for dep in repo_task["depends_on"])

    def test_service_depends_on_repository(self, sample_ir, sample_openapi, sample_rbac):
        """Service deve depender de repository."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        service_task = next(t for t in plan["tasks"] if "service" in t["id"])
        assert "depends_on" in service_task
        assert any("repository" in dep for dep in service_task["depends_on"])

    def test_controller_depends_on_service(self, sample_ir, sample_openapi, sample_rbac):
        """Controller deve depender de service."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        controller_task = next(t for t in plan["tasks"] if "controller" in t["id"])
        assert "depends_on" in controller_task
        assert any("service" in dep for dep in controller_task["depends_on"])


class TestTaskFiles:
    """Testes dos arquivos gerados."""

    def test_migration_file_path(self, sample_ir, sample_openapi, sample_rbac):
        """Migration deve ter path correto."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        migration_task = next(t for t in plan["tasks"] if "migration" in t["id"])
        assert any("db/migration" in f for f in migration_task["files"])
        assert any(".sql" in f for f in migration_task["files"])

    def test_model_file_path(self, sample_ir, sample_openapi, sample_rbac):
        """Model deve ter path correto."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        model_task = next(t for t in plan["tasks"] if "model" in t["id"])
        assert any("domain" in f for f in model_task["files"])
        assert any(".java" in f for f in model_task["files"])

    def test_frontend_pages_have_three_files(self, sample_ir, sample_openapi, sample_rbac):
        """Frontend pages deve ter 3 arquivos (List, New, Detail)."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        pages_task = next(t for t in plan["tasks"] if "frontend_pages" in t["id"])
        assert len(pages_task["files"]) == 3
        assert any("List.tsx" in f for f in pages_task["files"])
        assert any("New.tsx" in f for f in pages_task["files"])
        assert any("Detail.tsx" in f for f in pages_task["files"])


class TestControllerAcceptance:
    """Testes de acceptance do controller."""

    def test_controller_references_operation_ids(self, sample_ir, sample_openapi, sample_rbac):
        """Controller acceptance deve referenciar operationIds."""
        agent = PlannerAgent()
        plan = agent.generate_plan(sample_ir, sample_openapi, sample_rbac)

        controller_task = next(t for t in plan["tasks"] if "controller" in t["id"])
        acceptance_text = " ".join(controller_task["acceptance"])

        # Deve mencionar operações
        assert "listCliente" in acceptance_text or "operations" in acceptance_text.lower()


class TestMultipleEntities:
    """Testes com múltiplas entidades."""

    def test_each_entity_gets_8_tasks(self, multi_entity_ir, sample_openapi, sample_rbac):
        """Cada entidade deve ter 8 tasks."""
        agent = PlannerAgent()
        plan = agent.generate_plan(multi_entity_ir, sample_openapi, sample_rbac)

        produto_tasks = [t for t in plan["tasks"] if "produto" in t["id"]]
        pedido_tasks = [t for t in plan["tasks"] if "pedido" in t["id"]]

        assert len(produto_tasks) == 8
        assert len(pedido_tasks) == 8

    def test_global_order_is_sequential(self, multi_entity_ir, sample_openapi, sample_rbac):
        """Order global deve ser sequencial 1..N."""
        agent = PlannerAgent()
        plan = agent.generate_plan(multi_entity_ir, sample_openapi, sample_rbac)

        orders = [t["order"] for t in plan["tasks"]]
        assert orders == list(range(1, 17))

    def test_plan_with_multiple_entities_passes_validation(
        self, multi_entity_ir, sample_openapi, sample_rbac
    ):
        """Plan com múltiplas entidades deve passar validação."""
        agent = PlannerAgent()
        plan = agent.generate_plan(multi_entity_ir, sample_openapi, sample_rbac)

        report = validate_plan(plan)
        assert report.ok is True, f"Validation failed: {report.errors}"


class TestEmptyInput:
    """Testes com input vazio."""

    def test_empty_entities_returns_empty_tasks(self, sample_openapi, sample_rbac):
        """IR sem entidades deve retornar tasks vazio."""
        ir = {
            "meta": {"project_name": "Empty", "version": "v1"},
            "domain": {"entities": []},
            "api_intent": {},
            "ui": {},
            "nfr": {},
        }
        agent = PlannerAgent()
        plan = agent.generate_plan(ir, sample_openapi, sample_rbac)

        assert plan["tasks"] == []
