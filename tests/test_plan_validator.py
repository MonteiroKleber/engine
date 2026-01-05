"""Testes para o validador de PLAN."""

import pytest

from validators.plan_validator import PlanValidator, validate_plan


@pytest.fixture
def valid_plan():
    """Retorna um PLAN válido."""
    return {
        "meta": {
            "version": "v1",
            "strategy": "PATCH_ONLY",
            "ir_version": "v1",
            "project_name": "Test Project",
        },
        "tasks": [
            {
                "id": "task_create_user_model",
                "title": "Create User model",
                "order": 1,
                "files": ["src/models/user.py"],
                "acceptance": ["User model exists", "Has required fields"],
            }
        ],
    }


@pytest.fixture
def multi_task_plan():
    """Retorna um PLAN com múltiplas tasks."""
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
            },
            {
                "id": "task_create_api",
                "title": "Create API endpoints",
                "order": 2,
                "files": ["src/api/routes.py", "src/api/handlers.py"],
                "acceptance": ["Routes defined", "Handlers implemented"],
                "depends_on": ["task_create_model"],
            },
            {
                "id": "task_create_tests",
                "title": "Create tests",
                "order": 3,
                "files": ["tests/test_entity.py"],
                "acceptance": ["Tests pass"],
                "depends_on": ["task_create_model", "task_create_api"],
            },
        ],
    }


class TestPlanValidatorBasic:
    """Testes básicos do PlanValidator."""

    def test_valid_plan_passes(self, valid_plan):
        """PLAN válido deve passar validação."""
        report = validate_plan(valid_plan)
        assert report.ok is True
        assert len(report.errors) == 0

    def test_empty_dict_fails(self):
        """Dict vazio deve falhar."""
        report = validate_plan({})
        assert report.ok is False
        assert len(report.errors) > 0

    def test_missing_meta_fails(self, valid_plan):
        """PLAN sem meta deve falhar."""
        del valid_plan["meta"]
        report = validate_plan(valid_plan)
        assert report.ok is False
        assert "meta" in report.missing_fields

    def test_missing_tasks_fails(self, valid_plan):
        """PLAN sem tasks deve falhar."""
        del valid_plan["tasks"]
        report = validate_plan(valid_plan)
        assert report.ok is False
        assert "tasks" in report.missing_fields


class TestPlanMetaValidation:
    """Testes de validação do meta."""

    def test_meta_requires_version(self, valid_plan):
        """meta deve ter version."""
        del valid_plan["meta"]["version"]
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_meta_requires_strategy(self, valid_plan):
        """meta deve ter strategy."""
        del valid_plan["meta"]["strategy"]
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_strategy_must_be_patch_only(self, valid_plan):
        """strategy deve ser PATCH_ONLY."""
        valid_plan["meta"]["strategy"] = "FULL_REPLACE"
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_strategy_patch_only_valid(self, valid_plan):
        """strategy PATCH_ONLY deve ser válido."""
        valid_plan["meta"]["strategy"] = "PATCH_ONLY"
        report = validate_plan(valid_plan)
        assert report.ok is True


class TestPlanTasksValidation:
    """Testes de validação das tasks."""

    def test_tasks_cannot_be_empty(self, valid_plan):
        """tasks não pode ser array vazio."""
        valid_plan["tasks"] = []
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_task_requires_id(self, valid_plan):
        """task deve ter id."""
        del valid_plan["tasks"][0]["id"]
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_task_requires_title(self, valid_plan):
        """task deve ter title."""
        del valid_plan["tasks"][0]["title"]
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_task_requires_order(self, valid_plan):
        """task deve ter order."""
        del valid_plan["tasks"][0]["order"]
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_task_requires_files(self, valid_plan):
        """task deve ter files."""
        del valid_plan["tasks"][0]["files"]
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_task_requires_acceptance(self, valid_plan):
        """task deve ter acceptance."""
        del valid_plan["tasks"][0]["acceptance"]
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_task_files_cannot_be_empty(self, valid_plan):
        """task.files não pode ser array vazio."""
        valid_plan["tasks"][0]["files"] = []
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_task_acceptance_cannot_be_empty(self, valid_plan):
        """task.acceptance não pode ser array vazio."""
        valid_plan["tasks"][0]["acceptance"] = []
        report = validate_plan(valid_plan)
        assert report.ok is False


class TestTaskIdPattern:
    """Testes do padrão de task id."""

    def test_valid_task_id_pattern(self, valid_plan):
        """task_* pattern deve ser válido."""
        valid_plan["tasks"][0]["id"] = "task_create_user"
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_task_id_with_numbers(self, valid_plan):
        """task id com números deve ser válido."""
        valid_plan["tasks"][0]["id"] = "task_step_1"
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_task_id_without_prefix_fails(self, valid_plan):
        """task id sem prefixo task_ deve falhar."""
        valid_plan["tasks"][0]["id"] = "create_user"
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_task_id_with_uppercase_fails(self, valid_plan):
        """task id com maiúsculas deve falhar."""
        valid_plan["tasks"][0]["id"] = "task_CreateUser"
        report = validate_plan(valid_plan)
        assert report.ok is False


class TestTaskOrder:
    """Testes de order das tasks."""

    def test_order_must_be_positive(self, valid_plan):
        """order deve ser >= 1."""
        valid_plan["tasks"][0]["order"] = 0
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_order_cannot_be_negative(self, valid_plan):
        """order não pode ser negativo."""
        valid_plan["tasks"][0]["order"] = -1
        report = validate_plan(valid_plan)
        assert report.ok is False

    def test_order_must_be_integer(self, valid_plan):
        """order deve ser integer."""
        valid_plan["tasks"][0]["order"] = 1.5
        report = validate_plan(valid_plan)
        assert report.ok is False


class TestTaskDependencies:
    """Testes de dependências entre tasks."""

    def test_depends_on_is_optional(self, valid_plan):
        """depends_on é opcional."""
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_depends_on_accepts_array(self, valid_plan):
        """depends_on aceita array de strings."""
        valid_plan["tasks"][0]["depends_on"] = ["task_other"]
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_multi_task_with_dependencies(self, multi_task_plan):
        """PLAN com múltiplas tasks e dependências deve ser válido."""
        report = validate_plan(multi_task_plan)
        assert report.ok is True


class TestTaskStatus:
    """Testes de status das tasks."""

    def test_status_is_optional(self, valid_plan):
        """status é opcional."""
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_status_pending_valid(self, valid_plan):
        """status pending deve ser válido."""
        valid_plan["tasks"][0]["status"] = "pending"
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_status_in_progress_valid(self, valid_plan):
        """status in_progress deve ser válido."""
        valid_plan["tasks"][0]["status"] = "in_progress"
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_status_completed_valid(self, valid_plan):
        """status completed deve ser válido."""
        valid_plan["tasks"][0]["status"] = "completed"
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_status_skipped_valid(self, valid_plan):
        """status skipped deve ser válido."""
        valid_plan["tasks"][0]["status"] = "skipped"
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_invalid_status_fails(self, valid_plan):
        """status inválido deve falhar."""
        valid_plan["tasks"][0]["status"] = "failed"
        report = validate_plan(valid_plan)
        assert report.ok is False


class TestMultipleTasks:
    """Testes com múltiplas tasks."""

    def test_multiple_tasks_valid(self, multi_task_plan):
        """PLAN com múltiplas tasks deve ser válido."""
        report = validate_plan(multi_task_plan)
        assert report.ok is True

    def test_multiple_files_per_task(self, multi_task_plan):
        """task com múltiplos files deve ser válido."""
        report = validate_plan(multi_task_plan)
        assert report.ok is True
        # task_create_api tem 2 files
        assert len(multi_task_plan["tasks"][1]["files"]) == 2

    def test_multiple_acceptance_criteria(self, multi_task_plan):
        """task com múltiplos acceptance deve ser válido."""
        report = validate_plan(multi_task_plan)
        assert report.ok is True
        # task_create_api tem 2 acceptance
        assert len(multi_task_plan["tasks"][1]["acceptance"]) == 2


class TestValidationReport:
    """Testes do ValidationReport."""

    def test_report_has_ok_field(self, valid_plan):
        """Report deve ter campo ok."""
        report = validate_plan(valid_plan)
        assert hasattr(report, "ok")

    def test_report_has_errors_field(self, valid_plan):
        """Report deve ter campo errors."""
        report = validate_plan(valid_plan)
        assert hasattr(report, "errors")

    def test_report_has_missing_fields_field(self, valid_plan):
        """Report deve ter campo missing_fields."""
        report = validate_plan(valid_plan)
        assert hasattr(report, "missing_fields")

    def test_report_to_dict(self, valid_plan):
        """Report deve converter para dict."""
        report = validate_plan(valid_plan)
        d = report.to_dict()
        assert "ok" in d
        assert "errors" in d
        assert "missing_fields" in d


class TestPlanValidatorClass:
    """Testes da classe PlanValidator."""

    def test_validator_instantiation(self):
        """PlanValidator deve instanciar corretamente."""
        validator = PlanValidator()
        assert validator.schema is not None

    def test_validator_has_schema(self):
        """PlanValidator deve ter schema carregado."""
        validator = PlanValidator()
        assert "properties" in validator.schema
        assert "meta" in validator.schema["properties"]
        assert "tasks" in validator.schema["properties"]


class TestUniqueTaskIds:
    """Testes de IDs únicos entre tasks."""

    def test_unique_ids_pass(self, multi_task_plan):
        """Tasks com IDs únicos devem passar."""
        report = validate_plan(multi_task_plan)
        assert report.ok is True

    def test_duplicate_ids_fail(self, valid_plan):
        """Tasks com IDs duplicados devem falhar."""
        valid_plan["tasks"].append({
            "id": "task_create_user_model",  # duplicado
            "title": "Another task",
            "order": 2,
            "files": ["src/other.py"],
            "acceptance": ["Done"],
        })
        report = validate_plan(valid_plan)
        assert report.ok is False
        assert any("Duplicate task id" in e for e in report.errors)

    def test_duplicate_ids_reports_both_indices(self, valid_plan):
        """Erro de ID duplicado deve mostrar índices."""
        valid_plan["tasks"].append({
            "id": "task_create_user_model",
            "title": "Another task",
            "order": 2,
            "files": ["src/other.py"],
            "acceptance": ["Done"],
        })
        report = validate_plan(valid_plan)
        assert report.ok is False
        error_msg = [e for e in report.errors if "Duplicate" in e][0]
        assert "index 1" in error_msg
        assert "index 0" in error_msg

    def test_multiple_duplicates_all_reported(self):
        """Múltiplos IDs duplicados devem ser todos reportados."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {"id": "task_a", "title": "A1", "order": 1, "files": ["a.py"], "acceptance": ["ok"]},
                {"id": "task_a", "title": "A2", "order": 2, "files": ["b.py"], "acceptance": ["ok"]},
                {"id": "task_b", "title": "B1", "order": 3, "files": ["c.py"], "acceptance": ["ok"]},
                {"id": "task_b", "title": "B2", "order": 4, "files": ["d.py"], "acceptance": ["ok"]},
            ],
        }
        report = validate_plan(plan)
        assert report.ok is False
        assert len([e for e in report.errors if "Duplicate" in e]) >= 2


class TestOrderSequence:
    """Testes de sequência de orders (1..N sem buracos)."""

    def test_valid_sequence_passes(self, multi_task_plan):
        """Sequência 1,2,3 deve passar."""
        report = validate_plan(multi_task_plan)
        assert report.ok is True

    def test_single_task_order_1_passes(self, valid_plan):
        """Task única com order=1 deve passar."""
        report = validate_plan(valid_plan)
        assert report.ok is True

    def test_gap_in_sequence_fails(self):
        """Sequência com buraco (1,3) deve falhar."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {"id": "task_a", "title": "A", "order": 1, "files": ["a.py"], "acceptance": ["ok"]},
                {"id": "task_b", "title": "B", "order": 3, "files": ["b.py"], "acceptance": ["ok"]},
            ],
        }
        report = validate_plan(plan)
        assert report.ok is False
        assert any("gaps" in e for e in report.errors)

    def test_duplicate_order_fails(self):
        """Orders duplicados (1,1,2) devem falhar."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {"id": "task_a", "title": "A", "order": 1, "files": ["a.py"], "acceptance": ["ok"]},
                {"id": "task_b", "title": "B", "order": 1, "files": ["b.py"], "acceptance": ["ok"]},
                {"id": "task_c", "title": "C", "order": 2, "files": ["c.py"], "acceptance": ["ok"]},
            ],
        }
        report = validate_plan(plan)
        assert report.ok is False
        assert any("duplicates" in e for e in report.errors)

    def test_not_starting_at_1_fails(self):
        """Sequência não começando em 1 (2,3) deve falhar."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {"id": "task_a", "title": "A", "order": 2, "files": ["a.py"], "acceptance": ["ok"]},
                {"id": "task_b", "title": "B", "order": 3, "files": ["b.py"], "acceptance": ["ok"]},
            ],
        }
        report = validate_plan(plan)
        assert report.ok is False

    def test_unordered_but_valid_sequence_passes(self):
        """Sequência válida mas fora de ordem (3,1,2) deve passar."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {"id": "task_c", "title": "C", "order": 3, "files": ["c.py"], "acceptance": ["ok"]},
                {"id": "task_a", "title": "A", "order": 1, "files": ["a.py"], "acceptance": ["ok"]},
                {"id": "task_b", "title": "B", "order": 2, "files": ["b.py"], "acceptance": ["ok"]},
            ],
        }
        report = validate_plan(plan)
        assert report.ok is True

    def test_large_sequence_valid(self):
        """Sequência grande (1..10) deve passar."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {"id": f"task_{i}", "title": f"Task {i}", "order": i, "files": [f"f{i}.py"], "acceptance": ["ok"]}
                for i in range(1, 11)
            ],
        }
        report = validate_plan(plan)
        assert report.ok is True

    def test_large_sequence_with_gap_fails(self):
        """Sequência grande com buraco deve falhar."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {"id": f"task_{i}", "title": f"Task {i}", "order": i, "files": [f"f{i}.py"], "acceptance": ["ok"]}
                for i in [1, 2, 3, 5, 6, 7]  # missing 4
            ],
        }
        report = validate_plan(plan)
        assert report.ok is False
        assert any("4" in e for e in report.errors)


class TestCombinedInternalValidations:
    """Testes combinando múltiplas validações internas."""

    def test_duplicate_id_and_order_gap(self):
        """Duplicata de ID e buraco de order devem ambos ser reportados."""
        plan = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [
                {"id": "task_a", "title": "A", "order": 1, "files": ["a.py"], "acceptance": ["ok"]},
                {"id": "task_a", "title": "A dup", "order": 3, "files": ["b.py"], "acceptance": ["ok"]},
            ],
        }
        report = validate_plan(plan)
        assert report.ok is False
        assert any("Duplicate" in e for e in report.errors)
        assert any("gaps" in e or "missing" in e.lower() for e in report.errors)

    def test_schema_error_blocks_internal_validation(self, valid_plan):
        """Erro de schema deve bloquear validações internas."""
        valid_plan["tasks"][0]["id"] = "invalid_without_task_prefix"
        report = validate_plan(valid_plan)
        assert report.ok is False
        # Erro é de schema (pattern), não de validação interna
        assert not any("Duplicate" in e for e in report.errors)
        assert not any("gaps" in e for e in report.errors)
