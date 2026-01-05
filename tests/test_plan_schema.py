"""Testes do JSON Schema do PLAN."""

import json
from pathlib import Path

import jsonschema
import pytest


@pytest.fixture
def plan_schema():
    """Carrega o schema do PLAN."""
    schema_path = Path(__file__).parent.parent / "schemas" / "plan.schema.json"
    with open(schema_path) as f:
        return json.load(f)


@pytest.fixture
def valid_plan():
    """Retorna um PLAN válido mínimo."""
    return {
        "meta": {
            "version": "v1",
            "strategy": "PATCH_ONLY",
        },
        "tasks": [
            {
                "id": "task_create_model",
                "title": "Create model",
                "order": 1,
                "files": ["src/models/entity.py"],
                "acceptance": ["Model exists"],
            }
        ],
    }


class TestSchemaStructure:
    """Testes da estrutura do schema."""

    def test_schema_has_required_fields(self, plan_schema):
        """Schema deve ter required com meta e tasks."""
        assert "required" in plan_schema
        assert "meta" in plan_schema["required"]
        assert "tasks" in plan_schema["required"]

    def test_schema_meta_properties(self, plan_schema):
        """Schema meta deve ter version e strategy."""
        meta = plan_schema["properties"]["meta"]
        assert "version" in meta["properties"]
        assert "strategy" in meta["properties"]

    def test_schema_strategy_is_enum(self, plan_schema):
        """Strategy deve ser enum com PATCH_ONLY."""
        strategy = plan_schema["properties"]["meta"]["properties"]["strategy"]
        assert "enum" in strategy
        assert "PATCH_ONLY" in strategy["enum"]

    def test_schema_tasks_properties(self, plan_schema):
        """Schema tasks deve ter propriedades corretas."""
        tasks_items = plan_schema["properties"]["tasks"]["items"]
        assert "id" in tasks_items["properties"]
        assert "title" in tasks_items["properties"]
        assert "order" in tasks_items["properties"]
        assert "files" in tasks_items["properties"]
        assert "acceptance" in tasks_items["properties"]

    def test_schema_task_id_has_pattern(self, plan_schema):
        """Task id deve ter pattern ^task_[a-z0-9_]+$."""
        task_id = plan_schema["properties"]["tasks"]["items"]["properties"]["id"]
        assert "pattern" in task_id
        assert task_id["pattern"] == "^task_[a-z0-9_]+$"

    def test_schema_order_minimum_is_1(self, plan_schema):
        """Order deve ter minimum 1."""
        order = plan_schema["properties"]["tasks"]["items"]["properties"]["order"]
        assert "minimum" in order
        assert order["minimum"] == 1

    def test_schema_files_min_items_is_1(self, plan_schema):
        """Files deve ter minItems 1."""
        files = plan_schema["properties"]["tasks"]["items"]["properties"]["files"]
        assert "minItems" in files
        assert files["minItems"] == 1

    def test_schema_acceptance_min_items_is_1(self, plan_schema):
        """Acceptance deve ter minItems 1."""
        acceptance = plan_schema["properties"]["tasks"]["items"]["properties"]["acceptance"]
        assert "minItems" in acceptance
        assert acceptance["minItems"] == 1


class TestSchemaValidation:
    """Testes de validação contra o schema."""

    def test_valid_plan_passes_schema(self, plan_schema, valid_plan):
        """PLAN válido deve passar validação de schema."""
        jsonschema.validate(valid_plan, plan_schema)

    def test_missing_meta_fails_schema(self, plan_schema, valid_plan):
        """PLAN sem meta deve falhar validação."""
        del valid_plan["meta"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_missing_tasks_fails_schema(self, plan_schema, valid_plan):
        """PLAN sem tasks deve falhar validação."""
        del valid_plan["tasks"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_empty_tasks_fails_schema(self, plan_schema, valid_plan):
        """PLAN com tasks vazio deve falhar validação."""
        valid_plan["tasks"] = []
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_missing_version_fails_schema(self, plan_schema, valid_plan):
        """Meta sem version deve falhar validação."""
        del valid_plan["meta"]["version"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_missing_strategy_fails_schema(self, plan_schema, valid_plan):
        """Meta sem strategy deve falhar validação."""
        del valid_plan["meta"]["strategy"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_invalid_strategy_fails_schema(self, plan_schema, valid_plan):
        """Strategy inválida deve falhar validação."""
        valid_plan["meta"]["strategy"] = "FULL_REPLACE"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)


class TestTaskValidation:
    """Testes de validação de tasks contra schema."""

    def test_task_missing_id_fails(self, plan_schema, valid_plan):
        """Task sem id deve falhar."""
        del valid_plan["tasks"][0]["id"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_task_missing_title_fails(self, plan_schema, valid_plan):
        """Task sem title deve falhar."""
        del valid_plan["tasks"][0]["title"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_task_missing_order_fails(self, plan_schema, valid_plan):
        """Task sem order deve falhar."""
        del valid_plan["tasks"][0]["order"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_task_missing_files_fails(self, plan_schema, valid_plan):
        """Task sem files deve falhar."""
        del valid_plan["tasks"][0]["files"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_task_missing_acceptance_fails(self, plan_schema, valid_plan):
        """Task sem acceptance deve falhar."""
        del valid_plan["tasks"][0]["acceptance"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_task_empty_files_fails(self, plan_schema, valid_plan):
        """Task com files vazio deve falhar."""
        valid_plan["tasks"][0]["files"] = []
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_task_empty_acceptance_fails(self, plan_schema, valid_plan):
        """Task com acceptance vazio deve falhar."""
        valid_plan["tasks"][0]["acceptance"] = []
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)


class TestTaskIdPattern:
    """Testes do padrão de task id."""

    def test_valid_task_id_passes(self, plan_schema, valid_plan):
        """Task id com padrão correto deve passar."""
        valid_plan["tasks"][0]["id"] = "task_create_user_model"
        jsonschema.validate(valid_plan, plan_schema)

    def test_task_id_with_numbers_passes(self, plan_schema, valid_plan):
        """Task id com números deve passar."""
        valid_plan["tasks"][0]["id"] = "task_step_1"
        jsonschema.validate(valid_plan, plan_schema)

    def test_task_id_without_prefix_fails(self, plan_schema, valid_plan):
        """Task id sem prefixo task_ deve falhar."""
        valid_plan["tasks"][0]["id"] = "create_user"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_task_id_with_uppercase_fails(self, plan_schema, valid_plan):
        """Task id com maiúsculas deve falhar."""
        valid_plan["tasks"][0]["id"] = "task_CreateUser"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_task_id_with_hyphen_fails(self, plan_schema, valid_plan):
        """Task id com hífen deve falhar."""
        valid_plan["tasks"][0]["id"] = "task_create-user"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)


class TestOrderValidation:
    """Testes de validação de order."""

    def test_order_1_passes(self, plan_schema, valid_plan):
        """Order 1 deve passar."""
        valid_plan["tasks"][0]["order"] = 1
        jsonschema.validate(valid_plan, plan_schema)

    def test_order_0_fails(self, plan_schema, valid_plan):
        """Order 0 deve falhar (minimum é 1)."""
        valid_plan["tasks"][0]["order"] = 0
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_order_negative_fails(self, plan_schema, valid_plan):
        """Order negativo deve falhar."""
        valid_plan["tasks"][0]["order"] = -1
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_order_float_fails(self, plan_schema, valid_plan):
        """Order float deve falhar."""
        valid_plan["tasks"][0]["order"] = 1.5
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)


class TestStatusValidation:
    """Testes de validação de status."""

    def test_status_pending_passes(self, plan_schema, valid_plan):
        """Status pending deve passar."""
        valid_plan["tasks"][0]["status"] = "pending"
        jsonschema.validate(valid_plan, plan_schema)

    def test_status_in_progress_passes(self, plan_schema, valid_plan):
        """Status in_progress deve passar."""
        valid_plan["tasks"][0]["status"] = "in_progress"
        jsonschema.validate(valid_plan, plan_schema)

    def test_status_completed_passes(self, plan_schema, valid_plan):
        """Status completed deve passar."""
        valid_plan["tasks"][0]["status"] = "completed"
        jsonschema.validate(valid_plan, plan_schema)

    def test_status_skipped_passes(self, plan_schema, valid_plan):
        """Status skipped deve passar."""
        valid_plan["tasks"][0]["status"] = "skipped"
        jsonschema.validate(valid_plan, plan_schema)

    def test_status_invalid_fails(self, plan_schema, valid_plan):
        """Status inválido deve falhar."""
        valid_plan["tasks"][0]["status"] = "failed"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(valid_plan, plan_schema)

    def test_status_is_optional(self, plan_schema, valid_plan):
        """Status é opcional."""
        if "status" in valid_plan["tasks"][0]:
            del valid_plan["tasks"][0]["status"]
        jsonschema.validate(valid_plan, plan_schema)


class TestDependsOnValidation:
    """Testes de validação de depends_on."""

    def test_depends_on_is_optional(self, plan_schema, valid_plan):
        """depends_on é opcional."""
        if "depends_on" in valid_plan["tasks"][0]:
            del valid_plan["tasks"][0]["depends_on"]
        jsonschema.validate(valid_plan, plan_schema)

    def test_depends_on_accepts_array(self, plan_schema, valid_plan):
        """depends_on aceita array de strings."""
        valid_plan["tasks"][0]["depends_on"] = ["task_other"]
        jsonschema.validate(valid_plan, plan_schema)

    def test_depends_on_accepts_multiple(self, plan_schema, valid_plan):
        """depends_on aceita múltiplas dependências."""
        valid_plan["tasks"][0]["depends_on"] = ["task_a", "task_b", "task_c"]
        jsonschema.validate(valid_plan, plan_schema)

    def test_depends_on_accepts_empty_array(self, plan_schema, valid_plan):
        """depends_on aceita array vazio."""
        valid_plan["tasks"][0]["depends_on"] = []
        jsonschema.validate(valid_plan, plan_schema)


class TestOptionalMetaFields:
    """Testes de campos opcionais do meta."""

    def test_ir_version_is_optional(self, plan_schema, valid_plan):
        """ir_version é opcional."""
        jsonschema.validate(valid_plan, plan_schema)

    def test_ir_version_accepts_string(self, plan_schema, valid_plan):
        """ir_version aceita string."""
        valid_plan["meta"]["ir_version"] = "v2"
        jsonschema.validate(valid_plan, plan_schema)

    def test_project_name_is_optional(self, plan_schema, valid_plan):
        """project_name é opcional."""
        jsonschema.validate(valid_plan, plan_schema)

    def test_project_name_accepts_string(self, plan_schema, valid_plan):
        """project_name aceita string."""
        valid_plan["meta"]["project_name"] = "My Project"
        jsonschema.validate(valid_plan, plan_schema)

    def test_created_at_is_optional(self, plan_schema, valid_plan):
        """created_at é opcional."""
        jsonschema.validate(valid_plan, plan_schema)

    def test_created_at_accepts_datetime(self, plan_schema, valid_plan):
        """created_at aceita datetime string."""
        valid_plan["meta"]["created_at"] = "2024-01-01T12:00:00Z"
        jsonschema.validate(valid_plan, plan_schema)


class TestComplexPlan:
    """Testes com PLAN complexo."""

    def test_multi_task_plan_passes(self, plan_schema):
        """PLAN com múltiplas tasks deve passar."""
        plan = {
            "meta": {
                "version": "v1",
                "strategy": "PATCH_ONLY",
                "ir_version": "v1",
                "project_name": "E-commerce",
                "created_at": "2024-01-01T12:00:00Z",
            },
            "tasks": [
                {
                    "id": "task_create_model",
                    "title": "Create model",
                    "order": 1,
                    "files": ["src/models/entity.py"],
                    "acceptance": ["Model exists"],
                },
                {
                    "id": "task_create_api",
                    "title": "Create API",
                    "order": 2,
                    "files": ["src/api/routes.py", "src/api/handlers.py"],
                    "acceptance": ["Routes defined", "Handlers work"],
                    "depends_on": ["task_create_model"],
                    "status": "pending",
                },
                {
                    "id": "task_create_tests",
                    "title": "Create tests",
                    "order": 3,
                    "files": ["tests/test_entity.py"],
                    "acceptance": ["Tests pass"],
                    "depends_on": ["task_create_model", "task_create_api"],
                    "status": "pending",
                },
            ],
        }
        jsonschema.validate(plan, plan_schema)
