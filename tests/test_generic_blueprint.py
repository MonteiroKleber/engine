"""Testes para o GenericBlueprint.

Verifica:
- NÃO cria entidades
- NÃO cria endpoints
- NÃO cria tarefas novas
- NÃO altera IR/OAS/PLAN
- Apenas organiza e ordena o que já existe
"""

import pytest
from copy import deepcopy

from blueprints.generic_blueprint import (
    GenericBlueprint,
    BlueprintResult,
    apply_blueprint,
)


# ==================== FIXTURES ====================


@pytest.fixture
def sample_ir():
    """IR de exemplo."""
    return {
        "entities": [
            {"name": "User", "fields": [{"name": "id", "type": "Long"}]},
            {"name": "Product", "fields": [{"name": "id", "type": "Long"}]},
        ],
        "relationships": [],
    }


@pytest.fixture
def sample_oas():
    """OAS de exemplo."""
    return {
        "openapi": "3.0.0",
        "paths": {
            "/users": {"get": {"operationId": "listUsers"}},
            "/products": {"get": {"operationId": "listProducts"}},
        },
    }


@pytest.fixture
def sample_rbac():
    """RBAC de exemplo."""
    return {
        "roles": ["admin", "user"],
        "permissions": [
            {"operation_id": "listUsers", "required_role": "user"},
            {"operation_id": "listProducts", "required_role": "user"},
        ],
    }


@pytest.fixture
def sample_plan():
    """PLAN de exemplo com tarefas em ordem aleatória."""
    return {
        "project": "test",
        "tasks": [
            {"id": "task-3", "phase": "frontend", "priority": "medium", "description": "Create UI"},
            {"id": "task-1", "phase": "database", "priority": "high", "description": "Create schema"},
            {"id": "task-4", "phase": "testing", "priority": "low", "description": "Write tests"},
            {"id": "task-2", "phase": "backend", "priority": "high", "description": "Create API"},
        ],
    }


@pytest.fixture
def ordered_plan():
    """PLAN já ordenado por fase e prioridade."""
    return {
        "project": "test",
        "tasks": [
            {"id": "task-1", "phase": "database", "priority": "high", "description": "Create schema"},
            {"id": "task-2", "phase": "backend", "priority": "high", "description": "Create API"},
            {"id": "task-3", "phase": "frontend", "priority": "medium", "description": "Create UI"},
            {"id": "task-4", "phase": "testing", "priority": "low", "description": "Write tests"},
        ],
    }


@pytest.fixture
def empty_plan():
    """PLAN vazio."""
    return {"project": "test", "tasks": []}


# ==================== TESTS: INTERFACE ====================


class TestGenericBlueprintInterface:
    """Testes da interface obrigatória."""

    def test_has_apply_method(self):
        """GenericBlueprint deve ter método apply."""
        blueprint = GenericBlueprint()
        assert hasattr(blueprint, "apply")
        assert callable(blueprint.apply)

    def test_apply_signature(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """apply deve aceitar (ir, oas, rbac, plan) e retornar BlueprintResult."""
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert isinstance(result, BlueprintResult)
        assert isinstance(result.plan, dict)

    def test_apply_returns_plan(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """apply deve retornar um PLAN válido."""
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert "tasks" in result.plan
        assert isinstance(result.plan["tasks"], list)


# ==================== TESTS: NO-OP BEHAVIOR ====================


class TestNoOpBehavior:
    """Testes do comportamento no-op."""

    def test_strict_mode_returns_unchanged(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Em strict_mode, PLAN deve ser retornado sem modificações."""
        blueprint = GenericBlueprint(strict_mode=True)
        original = deepcopy(sample_plan)

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        # Tarefas devem estar na mesma ordem
        assert result.plan["tasks"] == original["tasks"]
        assert not result.reordered

    def test_does_not_add_tasks(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Blueprint NUNCA deve adicionar tarefas."""
        blueprint = GenericBlueprint()
        original_count = len(sample_plan["tasks"])

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert len(result.plan["tasks"]) == original_count
        assert result.original_task_count == original_count
        assert result.final_task_count == original_count

    def test_does_not_remove_tasks(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Blueprint NUNCA deve remover tarefas."""
        blueprint = GenericBlueprint()
        original_ids = {t["id"] for t in sample_plan["tasks"]}

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        result_ids = {t["id"] for t in result.plan["tasks"]}
        assert original_ids == result_ids

    def test_does_not_modify_task_content(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Blueprint NUNCA deve modificar conteúdo das tarefas."""
        blueprint = GenericBlueprint()
        original_tasks = {t["id"]: deepcopy(t) for t in sample_plan["tasks"]}

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        for task in result.plan["tasks"]:
            original = original_tasks[task["id"]]
            assert task == original

    def test_does_not_modify_ir(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Blueprint NUNCA deve modificar IR."""
        blueprint = GenericBlueprint()
        original_ir = deepcopy(sample_ir)

        blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert sample_ir == original_ir

    def test_does_not_modify_oas(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Blueprint NUNCA deve modificar OAS."""
        blueprint = GenericBlueprint()
        original_oas = deepcopy(sample_oas)

        blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert sample_oas == original_oas

    def test_does_not_modify_rbac(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Blueprint NUNCA deve modificar RBAC."""
        blueprint = GenericBlueprint()
        original_rbac = deepcopy(sample_rbac)

        blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert sample_rbac == original_rbac

    def test_does_not_modify_original_plan(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Blueprint NUNCA deve modificar o PLAN original."""
        blueprint = GenericBlueprint()
        original_plan = deepcopy(sample_plan)

        blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert sample_plan == original_plan


# ==================== TESTS: REORDERING ====================


class TestReordering:
    """Testes de reordenação."""

    def test_reorders_by_phase(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve reordenar tarefas por fase."""
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        phases = [t["phase"] for t in result.plan["tasks"]]
        # database < backend < frontend < testing
        assert phases.index("database") < phases.index("backend")
        assert phases.index("backend") < phases.index("frontend")
        assert phases.index("frontend") < phases.index("testing")

    def test_reorders_by_priority_within_phase(self, sample_ir, sample_oas, sample_rbac):
        """Deve reordenar tarefas por prioridade dentro da mesma fase."""
        plan = {
            "tasks": [
                {"id": "t1", "phase": "backend", "priority": "low"},
                {"id": "t2", "phase": "backend", "priority": "high"},
                {"id": "t3", "phase": "backend", "priority": "medium"},
            ]
        }
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, plan)

        priorities = [t["priority"] for t in result.plan["tasks"]]
        assert priorities == ["high", "medium", "low"]

    def test_already_ordered_no_change(self, sample_ir, sample_oas, sample_rbac, ordered_plan):
        """PLAN já ordenado não deve ser alterado."""
        blueprint = GenericBlueprint()
        original = deepcopy(ordered_plan)

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, ordered_plan)

        # Ordem deve ser a mesma
        assert [t["id"] for t in result.plan["tasks"]] == [t["id"] for t in original["tasks"]]

    def test_reports_reordering(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve reportar quando houve reordenação."""
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert result.reordered
        assert len(result.changes) > 0


# ==================== TESTS: EMPTY PLAN ====================


class TestEmptyPlan:
    """Testes com PLAN vazio."""

    def test_handles_empty_tasks(self, sample_ir, sample_oas, sample_rbac, empty_plan):
        """Deve lidar com lista de tarefas vazia."""
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, empty_plan)

        assert result.plan["tasks"] == []
        assert result.original_task_count == 0
        assert result.final_task_count == 0

    def test_no_reorder_for_empty(self, sample_ir, sample_oas, sample_rbac, empty_plan):
        """PLAN vazio não deve reportar reordenação."""
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, empty_plan)

        assert not result.reordered


# ==================== TESTS: PHASE ORDER ====================


class TestPhaseOrder:
    """Testes da ordem de fases."""

    def test_default_phase_order(self):
        """Ordem de fases padrão deve estar definida."""
        assert "setup" in GenericBlueprint.DEFAULT_PHASE_ORDER
        assert "database" in GenericBlueprint.DEFAULT_PHASE_ORDER
        assert "backend" in GenericBlueprint.DEFAULT_PHASE_ORDER
        assert "frontend" in GenericBlueprint.DEFAULT_PHASE_ORDER
        assert "testing" in GenericBlueprint.DEFAULT_PHASE_ORDER
        assert "deployment" in GenericBlueprint.DEFAULT_PHASE_ORDER

    def test_unknown_phase_goes_last(self, sample_ir, sample_oas, sample_rbac):
        """Fases desconhecidas devem ir para o final."""
        plan = {
            "tasks": [
                {"id": "t1", "phase": "unknown_phase", "priority": "high"},
                {"id": "t2", "phase": "database", "priority": "high"},
            ]
        }
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, plan)

        # database deve vir antes de unknown_phase
        ids = [t["id"] for t in result.plan["tasks"]]
        assert ids.index("t2") < ids.index("t1")


# ==================== TESTS: PRIORITY ORDER ====================


class TestPriorityOrder:
    """Testes da ordem de prioridades."""

    def test_priority_order_defined(self):
        """Ordem de prioridades deve estar definida."""
        assert GenericBlueprint.PRIORITY_ORDER["critical"] < GenericBlueprint.PRIORITY_ORDER["high"]
        assert GenericBlueprint.PRIORITY_ORDER["high"] < GenericBlueprint.PRIORITY_ORDER["medium"]
        assert GenericBlueprint.PRIORITY_ORDER["medium"] < GenericBlueprint.PRIORITY_ORDER["low"]

    def test_unknown_priority_defaults_to_medium(self, sample_ir, sample_oas, sample_rbac):
        """Prioridade desconhecida deve ser tratada como medium."""
        plan = {
            "tasks": [
                {"id": "t1", "phase": "backend", "priority": "unknown"},
                {"id": "t2", "phase": "backend", "priority": "high"},
                {"id": "t3", "phase": "backend", "priority": "low"},
            ]
        }
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, plan)

        # high < unknown(medium) < low
        ids = [t["id"] for t in result.plan["tasks"]]
        assert ids.index("t2") < ids.index("t1") < ids.index("t3")


# ==================== TESTS: INVARIANTS ====================


class TestInvariants:
    """Testes de invariantes."""

    def test_validate_invariants_success(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """validate_invariants deve retornar True para blueprint válido."""
        blueprint = GenericBlueprint()
        original = deepcopy(sample_plan)

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert blueprint.validate_invariants(original, result.plan)

    def test_validate_invariants_detects_added_task(self):
        """validate_invariants deve detectar tarefa adicionada."""
        blueprint = GenericBlueprint()

        original = {"tasks": [{"id": "t1"}]}
        modified = {"tasks": [{"id": "t1"}, {"id": "t2"}]}

        assert not blueprint.validate_invariants(original, modified)

    def test_validate_invariants_detects_removed_task(self):
        """validate_invariants deve detectar tarefa removida."""
        blueprint = GenericBlueprint()

        original = {"tasks": [{"id": "t1"}, {"id": "t2"}]}
        modified = {"tasks": [{"id": "t1"}]}

        assert not blueprint.validate_invariants(original, modified)

    def test_validate_invariants_detects_modified_content(self):
        """validate_invariants deve detectar conteúdo modificado."""
        blueprint = GenericBlueprint()

        original = {"tasks": [{"id": "t1", "description": "Original"}]}
        modified = {"tasks": [{"id": "t1", "description": "Modified"}]}

        assert not blueprint.validate_invariants(original, modified)

    def test_blueprint_result_enforces_invariant(self):
        """BlueprintResult deve falhar se task count mudar."""
        with pytest.raises(ValueError, match="task count"):
            BlueprintResult(
                plan={"tasks": []},
                original_task_count=5,
                final_task_count=3,
            )


# ==================== TESTS: BLUEPRINT RESULT ====================


class TestBlueprintResult:
    """Testes do BlueprintResult."""

    def test_to_dict(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """to_dict deve retornar estrutura correta."""
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)
        d = result.to_dict()

        assert "plan" in d
        assert "reordered" in d
        assert "original_task_count" in d
        assert "final_task_count" in d
        assert "changes" in d


# ==================== TESTS: CONVENIENCE FUNCTION ====================


class TestApplyBlueprintFunction:
    """Testes da função de conveniência."""

    def test_apply_blueprint_function(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """apply_blueprint deve funcionar como GenericBlueprint.apply."""
        result = apply_blueprint(sample_ir, sample_oas, sample_rbac, sample_plan)

        assert isinstance(result, BlueprintResult)
        assert len(result.plan["tasks"]) == len(sample_plan["tasks"])

    def test_apply_blueprint_strict_mode(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """apply_blueprint com strict_mode deve retornar sem modificações."""
        original = deepcopy(sample_plan)

        result = apply_blueprint(sample_ir, sample_oas, sample_rbac, sample_plan, strict_mode=True)

        assert result.plan["tasks"] == original["tasks"]
        assert not result.reordered


# ==================== TESTS: EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos limite."""

    def test_single_task(self, sample_ir, sample_oas, sample_rbac):
        """Deve lidar com uma única tarefa."""
        plan = {"tasks": [{"id": "t1", "phase": "backend", "priority": "high"}]}
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, plan)

        assert len(result.plan["tasks"]) == 1
        assert result.original_task_count == 1

    def test_tasks_without_phase(self, sample_ir, sample_oas, sample_rbac):
        """Deve lidar com tarefas sem fase definida."""
        plan = {"tasks": [{"id": "t1", "priority": "high"}]}
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, plan)

        assert len(result.plan["tasks"]) == 1

    def test_tasks_without_priority(self, sample_ir, sample_oas, sample_rbac):
        """Deve lidar com tarefas sem prioridade definida."""
        plan = {"tasks": [{"id": "t1", "phase": "backend"}]}
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, plan)

        assert len(result.plan["tasks"]) == 1

    def test_tasks_without_id(self, sample_ir, sample_oas, sample_rbac):
        """Deve lidar com tarefas sem ID."""
        plan = {"tasks": [{"phase": "backend", "priority": "high"}]}
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, plan)

        assert len(result.plan["tasks"]) == 1

    def test_plan_without_tasks_key(self, sample_ir, sample_oas, sample_rbac):
        """Deve lidar com PLAN sem chave 'tasks'."""
        plan = {"project": "test"}
        blueprint = GenericBlueprint()

        result = blueprint.apply(sample_ir, sample_oas, sample_rbac, plan)

        assert result.original_task_count == 0
        assert result.final_task_count == 0


# ==================== TESTS: DETERMINISM ====================


class TestDeterminism:
    """Testes de determinismo."""

    def test_same_input_same_output(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Mesma entrada deve produzir mesma saída."""
        blueprint = GenericBlueprint()

        result1 = blueprint.apply(sample_ir, sample_oas, sample_rbac, deepcopy(sample_plan))
        result2 = blueprint.apply(sample_ir, sample_oas, sample_rbac, deepcopy(sample_plan))

        assert result1.plan == result2.plan

    def test_idempotent(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Aplicar duas vezes deve produzir mesmo resultado."""
        blueprint = GenericBlueprint()

        result1 = blueprint.apply(sample_ir, sample_oas, sample_rbac, sample_plan)
        result2 = blueprint.apply(sample_ir, sample_oas, sample_rbac, result1.plan)

        # Após primeira ordenação, a segunda não deve mudar nada
        assert result1.plan == result2.plan


# ==================== TESTS: GENERIC INPUTS ====================


class TestGenericInputs:
    """Testes com inputs genéricos/diversos.

    Verifica que blueprint funciona com diferentes tipos de entrada.
    """

    def test_minimal_inputs(self):
        """Blueprint deve funcionar com inputs mínimos vazios."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {}
        rbac = {}
        plan = {"tasks": []}

        result = blueprint.apply(ir, oas, rbac, plan)

        assert result.plan is not None
        assert result.original_task_count == 0
        assert result.final_task_count == 0

    def test_null_like_inputs(self):
        """Blueprint deve funcionar com inputs None-like."""
        blueprint = GenericBlueprint()

        ir = {"domain": None}
        oas = {"paths": None}
        rbac = {"roles": None}
        plan = {"tasks": [{"id": "t1", "phase": "backend"}]}

        result = blueprint.apply(ir, oas, rbac, plan)

        assert len(result.plan["tasks"]) == 1

    def test_complex_ir_input(self):
        """Blueprint deve funcionar com IR complexo."""
        blueprint = GenericBlueprint()

        ir = {
            "meta": {"project": "complex", "version": "v1"},
            "domain": {
                "entities": [
                    {
                        "name": "User",
                        "attributes": [
                            {"name": "id", "type": "uuid", "constraints": ["not_null", "primary_key"]},
                            {"name": "email", "type": "string", "constraints": ["unique"]},
                            {"name": "profile", "type": "json", "nullable": True},
                        ],
                        "relationships": [
                            {"name": "orders", "target": "Order", "type": "one_to_many"},
                        ],
                    },
                    {
                        "name": "Order",
                        "attributes": [
                            {"name": "id", "type": "uuid"},
                            {"name": "total", "type": "decimal"},
                        ],
                    },
                ],
            },
            "srs_traceability": [
                {"requirement_id": "REQ-001", "entity": "User"},
            ],
        }
        oas = {}
        rbac = {}
        plan = {"tasks": [{"id": "t1"}]}

        result = blueprint.apply(ir, oas, rbac, plan)

        assert len(result.plan["tasks"]) == 1

    def test_complex_oas_input(self):
        """Blueprint deve funcionar com OAS complexo."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {
            "openapi": "3.0.0",
            "info": {"title": "Complex API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "parameters": [
                            {"name": "page", "in": "query", "schema": {"type": "integer"}},
                        ],
                        "responses": {"200": {"description": "OK"}},
                    },
                    "post": {
                        "operationId": "createUser",
                        "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}},
                    },
                },
                "/users/{id}": {
                    "get": {"operationId": "getUser"},
                    "put": {"operationId": "updateUser"},
                    "delete": {"operationId": "deleteUser"},
                },
            },
            "components": {
                "schemas": {
                    "User": {"type": "object", "properties": {"id": {"type": "string"}}},
                },
            },
        }
        rbac = {}
        plan = {"tasks": [{"id": "t1"}]}

        result = blueprint.apply(ir, oas, rbac, plan)

        assert len(result.plan["tasks"]) == 1

    def test_complex_rbac_input(self):
        """Blueprint deve funcionar com RBAC complexo."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {}
        rbac = {
            "roles": ["guest", "user", "admin", "superadmin"],
            "role_hierarchy": {
                "superadmin": ["admin"],
                "admin": ["user"],
                "user": ["guest"],
            },
            "permissions": [
                {"operation_id": "listUsers", "required_role": "user", "conditions": []},
                {"operation_id": "createUser", "required_role": "admin"},
                {"operation_id": "deleteUser", "required_role": "superadmin"},
            ],
        }
        plan = {"tasks": [{"id": "t1"}]}

        result = blueprint.apply(ir, oas, rbac, plan)

        assert len(result.plan["tasks"]) == 1

    def test_complex_plan_input(self):
        """Blueprint deve funcionar com PLAN complexo."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {}
        rbac = {}
        plan = {
            "meta": {"project": "complex", "version": "v1"},
            "tasks": [
                {
                    "id": "task-1",
                    "phase": "setup",
                    "priority": "critical",
                    "description": "Setup project structure",
                    "dependencies": [],
                    "artifacts": ["pom.xml", "package.json"],
                },
                {
                    "id": "task-2",
                    "phase": "database",
                    "priority": "high",
                    "description": "Create database schema",
                    "dependencies": ["task-1"],
                    "artifacts": ["V1__init.sql"],
                },
                {
                    "id": "task-3",
                    "phase": "backend",
                    "priority": "high",
                    "description": "Implement entities",
                    "dependencies": ["task-2"],
                    "artifacts": ["User.java", "Product.java"],
                },
                {
                    "id": "task-4",
                    "phase": "backend",
                    "priority": "medium",
                    "description": "Implement services",
                    "dependencies": ["task-3"],
                },
                {
                    "id": "task-5",
                    "phase": "frontend",
                    "priority": "medium",
                    "description": "Create UI components",
                    "dependencies": ["task-3"],
                },
                {
                    "id": "task-6",
                    "phase": "testing",
                    "priority": "low",
                    "description": "Write integration tests",
                    "dependencies": ["task-4", "task-5"],
                },
            ],
        }

        result = blueprint.apply(ir, oas, rbac, plan)

        assert len(result.plan["tasks"]) == 6
        assert result.original_task_count == 6
        assert result.final_task_count == 6

    def test_unicode_inputs(self):
        """Blueprint deve funcionar com caracteres unicode."""
        blueprint = GenericBlueprint()

        ir = {"domain": {"entities": [{"name": "Usuário", "attributes": []}]}}
        oas = {"paths": {"/usuários": {"get": {"operationId": "listarUsuários"}}}}
        rbac = {"roles": ["administrador", "usuário"]}
        plan = {
            "tasks": [
                {"id": "tarefa-1", "phase": "backend", "description": "Criar entidade Usuário"},
                {"id": "tarefa-2", "phase": "frontend", "description": "Criar tela de usuários"},
            ]
        }

        result = blueprint.apply(ir, oas, rbac, plan)

        assert len(result.plan["tasks"]) == 2

    def test_large_task_list(self):
        """Blueprint deve funcionar com muitas tarefas."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {}
        rbac = {}
        plan = {
            "tasks": [
                {"id": f"task-{i}", "phase": "backend", "priority": "medium"}
                for i in range(100)
            ]
        }

        result = blueprint.apply(ir, oas, rbac, plan)

        assert len(result.plan["tasks"]) == 100
        assert result.original_task_count == 100
        assert result.final_task_count == 100

    def test_all_phases_represented(self):
        """Blueprint deve funcionar com todas as fases representadas."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {}
        rbac = {}
        plan = {
            "tasks": [
                {"id": "t1", "phase": "deployment", "priority": "low"},
                {"id": "t2", "phase": "testing", "priority": "medium"},
                {"id": "t3", "phase": "integration", "priority": "high"},
                {"id": "t4", "phase": "frontend", "priority": "medium"},
                {"id": "t5", "phase": "backend", "priority": "high"},
                {"id": "t6", "phase": "database", "priority": "critical"},
                {"id": "t7", "phase": "setup", "priority": "critical"},
            ]
        }

        result = blueprint.apply(ir, oas, rbac, plan)

        # Verifica ordenação correta: setup → database → backend → frontend → integration → testing → deployment
        phases = [t["phase"] for t in result.plan["tasks"]]
        expected_order = ["setup", "database", "backend", "frontend", "integration", "testing", "deployment"]
        assert phases == expected_order

    def test_all_priorities_represented(self):
        """Blueprint deve funcionar com todas as prioridades representadas."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {}
        rbac = {}
        plan = {
            "tasks": [
                {"id": "t1", "phase": "backend", "priority": "low"},
                {"id": "t2", "phase": "backend", "priority": "medium"},
                {"id": "t3", "phase": "backend", "priority": "high"},
                {"id": "t4", "phase": "backend", "priority": "critical"},
            ]
        }

        result = blueprint.apply(ir, oas, rbac, plan)

        # Verifica ordenação correta: critical → high → medium → low
        priorities = [t["priority"] for t in result.plan["tasks"]]
        expected_order = ["critical", "high", "medium", "low"]
        assert priorities == expected_order

    def test_extra_fields_preserved(self):
        """Blueprint deve preservar campos extras nas tarefas."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {}
        rbac = {}
        plan = {
            "tasks": [
                {
                    "id": "t1",
                    "phase": "backend",
                    "priority": "high",
                    "custom_field": "custom_value",
                    "nested": {"key": "value"},
                    "list_field": [1, 2, 3],
                },
            ]
        }

        result = blueprint.apply(ir, oas, rbac, plan)

        task = result.plan["tasks"][0]
        assert task["custom_field"] == "custom_value"
        assert task["nested"] == {"key": "value"}
        assert task["list_field"] == [1, 2, 3]
