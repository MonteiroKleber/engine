"""Testes para o Blueprint Policy Validator.

Verifica gates anti-invenção:
1. Não pode criar entidade fora do IR
2. Não pode criar endpoint fora do OAS
3. Não pode criar task fora do PLAN
4. Não pode alterar contratos (IR, OAS, RBAC)

REGRA: Blueprint só pode consumir, nunca produzir.
"""

import pytest
from copy import deepcopy

from validators.blueprint_policy_validator import (
    BlueprintPolicyValidator,
    BlueprintPolicyReport,
    validate_blueprint_policy,
    validate_blueprint_plan_only,
)


# ==================== FIXTURES ====================


@pytest.fixture
def validator():
    """Instância do validador."""
    return BlueprintPolicyValidator()


@pytest.fixture
def sample_ir():
    """IR de exemplo."""
    return {
        "meta": {"project": "test", "version": "v1"},
        "domain": {
            "entities": [
                {"name": "User", "attributes": [{"name": "id", "type": "uuid"}]},
                {"name": "Product", "attributes": [{"name": "id", "type": "uuid"}]},
            ]
        },
        "srs_traceability": [],
    }


@pytest.fixture
def sample_oas():
    """OAS de exemplo."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/users": {
                "get": {"operationId": "listUsers", "responses": {"200": {"description": "OK"}}},
                "post": {"operationId": "createUser", "responses": {"201": {"description": "Created"}}},
            },
            "/products": {
                "get": {"operationId": "listProducts", "responses": {"200": {"description": "OK"}}},
            },
        },
    }


@pytest.fixture
def sample_rbac():
    """RBAC de exemplo."""
    return {
        "roles": ["admin", "user"],
        "permissions": [
            {"operation_id": "listUsers", "required_role": "user"},
            {"operation_id": "createUser", "required_role": "admin"},
        ],
    }


@pytest.fixture
def sample_plan():
    """PLAN de exemplo."""
    return {
        "meta": {"project": "test", "version": "v1"},
        "tasks": [
            {"id": "task-1", "phase": "backend", "priority": "high", "description": "Create User entity"},
            {"id": "task-2", "phase": "backend", "priority": "medium", "description": "Create Product entity"},
            {"id": "task-3", "phase": "frontend", "priority": "low", "description": "Create UI"},
        ],
    }


# ==================== TESTS: VALID BLUEPRINT (NO CHANGES) ====================


class TestValidBlueprint:
    """Testes para blueprints válidos que não violam políticas."""

    def test_no_changes_is_valid(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Blueprint que não muda nada deve ser válido."""
        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, sample_plan,
        )

        assert result.ok is True
        assert len(result.violations) == 0

    def test_reordered_tasks_is_valid(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Blueprint que apenas reordena tasks deve ser válido."""
        result_plan = deepcopy(sample_plan)
        # Inverter ordem das tasks
        result_plan["tasks"] = list(reversed(result_plan["tasks"]))

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, result_plan,
        )

        assert result.ok is True
        assert len(result.violations) == 0

    def test_deep_copy_is_valid(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deep copy dos artefatos deve ser válido."""
        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            deepcopy(sample_ir), deepcopy(sample_oas), deepcopy(sample_rbac), deepcopy(sample_plan),
        )

        assert result.ok is True


# ==================== TESTS: GATE 1 - ENTITY CREATION ====================


class TestEntityCreationGate:
    """Testes do gate anti-criação de entidades."""

    def test_detects_new_entity(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar entidade criada fora do IR."""
        result_ir = deepcopy(sample_ir)
        result_ir["domain"]["entities"].append({
            "name": "Order",
            "attributes": [{"name": "id", "type": "uuid"}],
        })

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            result_ir, sample_oas, sample_rbac, sample_plan,
        )

        assert result.ok is False
        assert "Order" in result.entities_created
        assert any("Entity created outside IR: Order" in v for v in result.violations)

    def test_detects_multiple_new_entities(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar múltiplas entidades criadas."""
        result_ir = deepcopy(sample_ir)
        result_ir["domain"]["entities"].extend([
            {"name": "Order", "attributes": []},
            {"name": "Invoice", "attributes": []},
        ])

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            result_ir, sample_oas, sample_rbac, sample_plan,
        )

        assert result.ok is False
        assert "Order" in result.entities_created
        assert "Invoice" in result.entities_created
        assert len(result.entities_created) == 2

    def test_same_entities_is_valid(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Manter mesmas entidades deve ser válido."""
        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, sample_plan,
        )

        assert len(result.entities_created) == 0


# ==================== TESTS: GATE 2 - ENDPOINT CREATION ====================


class TestEndpointCreationGate:
    """Testes do gate anti-criação de endpoints."""

    def test_detects_new_endpoint(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar endpoint criado fora do OAS."""
        result_oas = deepcopy(sample_oas)
        result_oas["paths"]["/orders"] = {
            "get": {"operationId": "listOrders", "responses": {"200": {"description": "OK"}}},
        }

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, result_oas, sample_rbac, sample_plan,
        )

        assert result.ok is False
        assert "GET /orders" in result.endpoints_created
        assert any("Endpoint created outside OAS" in v for v in result.violations)

    def test_detects_new_method_on_existing_path(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar novo método em path existente."""
        result_oas = deepcopy(sample_oas)
        result_oas["paths"]["/users"]["delete"] = {
            "operationId": "deleteUser",
            "responses": {"204": {"description": "No Content"}},
        }

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, result_oas, sample_rbac, sample_plan,
        )

        assert result.ok is False
        assert "DELETE /users" in result.endpoints_created

    def test_detects_multiple_new_endpoints(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar múltiplos endpoints criados."""
        result_oas = deepcopy(sample_oas)
        result_oas["paths"]["/orders"] = {
            "get": {"operationId": "listOrders"},
            "post": {"operationId": "createOrder"},
        }

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, result_oas, sample_rbac, sample_plan,
        )

        assert result.ok is False
        assert "GET /orders" in result.endpoints_created
        assert "POST /orders" in result.endpoints_created

    def test_same_endpoints_is_valid(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Manter mesmos endpoints deve ser válido."""
        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, sample_plan,
        )

        assert len(result.endpoints_created) == 0


# ==================== TESTS: GATE 3 - TASK CREATION ====================


class TestTaskCreationGate:
    """Testes do gate anti-criação de tasks."""

    def test_detects_new_task(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar task criada fora do PLAN."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"].append({
            "id": "task-4",
            "phase": "testing",
            "priority": "high",
            "description": "New task",
        })

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, result_plan,
        )

        assert result.ok is False
        assert "task-4" in result.tasks_created
        assert any("Task created outside PLAN: task-4" in v for v in result.violations)

    def test_detects_multiple_new_tasks(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar múltiplas tasks criadas."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"].extend([
            {"id": "task-4", "phase": "testing"},
            {"id": "task-5", "phase": "deployment"},
        ])

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, result_plan,
        )

        assert result.ok is False
        assert "task-4" in result.tasks_created
        assert "task-5" in result.tasks_created

    def test_reordered_tasks_is_valid(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Reordenar tasks sem criar novas deve ser válido."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"] = list(reversed(result_plan["tasks"]))

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, result_plan,
        )

        assert len(result.tasks_created) == 0


# ==================== TESTS: GATE 4 - CONTRACT ALTERATION ====================


class TestContractAlterationGate:
    """Testes do gate anti-alteração de contratos."""

    def test_detects_ir_alteration(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar alteração no IR."""
        result_ir = deepcopy(sample_ir)
        result_ir["domain"]["entities"][0]["attributes"].append({"name": "email", "type": "string"})

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            result_ir, sample_oas, sample_rbac, sample_plan,
        )

        assert result.ok is False
        assert "IR" in result.contracts_altered
        assert any("Contract altered: IR" in v for v in result.violations)

    def test_detects_oas_alteration(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar alteração no OAS."""
        result_oas = deepcopy(sample_oas)
        result_oas["info"]["version"] = "2.0.0"

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, result_oas, sample_rbac, sample_plan,
        )

        assert result.ok is False
        assert "OAS" in result.contracts_altered

    def test_detects_rbac_alteration(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar alteração no RBAC."""
        result_rbac = deepcopy(sample_rbac)
        result_rbac["roles"].append("superadmin")

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, result_rbac, sample_plan,
        )

        assert result.ok is False
        assert "RBAC" in result.contracts_altered

    def test_detects_multiple_contract_alterations(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar múltiplas alterações de contrato."""
        result_ir = deepcopy(sample_ir)
        result_ir["meta"]["version"] = "v2"

        result_oas = deepcopy(sample_oas)
        result_oas["info"]["version"] = "2.0.0"

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            result_ir, result_oas, sample_rbac, sample_plan,
        )

        assert result.ok is False
        assert "IR" in result.contracts_altered
        assert "OAS" in result.contracts_altered

    def test_no_alteration_is_valid(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Não alterar contratos deve ser válido."""
        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, sample_plan,
        )

        assert len(result.contracts_altered) == 0


# ==================== TESTS: PLAN ONLY VALIDATION ====================


class TestPlanOnlyValidation:
    """Testes da validação somente do PLAN."""

    def test_valid_reorder(self, validator, sample_plan):
        """Reordenar tasks é válido."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"] = list(reversed(result_plan["tasks"]))

        result = validator.validate_plan_only(sample_plan, result_plan)

        assert result.ok is True

    def test_detects_task_creation(self, validator, sample_plan):
        """Detecta criação de task."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"].append({"id": "task-new", "phase": "testing"})

        result = validator.validate_plan_only(sample_plan, result_plan)

        assert result.ok is False
        assert "task-new" in result.tasks_created

    def test_detects_task_removal(self, validator, sample_plan):
        """Detecta remoção de task."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"] = result_plan["tasks"][:2]  # Remove task-3

        result = validator.validate_plan_only(sample_plan, result_plan)

        assert result.ok is False
        assert any("Task removed from PLAN: task-3" in v for v in result.violations)

    def test_detects_task_content_alteration(self, validator, sample_plan):
        """Detecta alteração de conteúdo de task."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"][0]["description"] = "Modified description"

        result = validator.validate_plan_only(sample_plan, result_plan)

        assert result.ok is False
        assert any("Task content altered: task-1" in v for v in result.violations)


# ==================== TESTS: BLUEPRINT POLICY REPORT ====================


class TestBlueprintPolicyReport:
    """Testes do BlueprintPolicyReport."""

    def test_to_dict(self):
        """to_dict deve retornar dicionário correto."""
        report = BlueprintPolicyReport(
            ok=False,
            violations=["violation1", "violation2"],
            entities_created=["Entity1"],
            endpoints_created=["GET /test"],
            tasks_created=["task-new"],
            contracts_altered=["IR"],
        )

        result = report.to_dict()

        assert result["ok"] is False
        assert len(result["violations"]) == 2
        assert "Entity1" in result["entities_created"]
        assert "GET /test" in result["endpoints_created"]
        assert "task-new" in result["tasks_created"]
        assert "IR" in result["contracts_altered"]

    def test_ok_report(self):
        """Report OK deve ter listas vazias."""
        report = BlueprintPolicyReport(ok=True)

        assert report.ok is True
        assert report.violations == []
        assert report.entities_created == []
        assert report.endpoints_created == []
        assert report.tasks_created == []
        assert report.contracts_altered == []


# ==================== TESTS: CONVENIENCE FUNCTIONS ====================


class TestConvenienceFunctions:
    """Testes das funções de conveniência."""

    def test_validate_blueprint_policy_valid(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """validate_blueprint_policy deve retornar tupla correta para válido."""
        ok, violations = validate_blueprint_policy(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, sample_plan,
        )

        assert ok is True
        assert violations == []

    def test_validate_blueprint_policy_invalid(self, sample_ir, sample_oas, sample_rbac, sample_plan):
        """validate_blueprint_policy deve retornar tupla correta para inválido."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"].append({"id": "new-task", "phase": "testing"})

        ok, violations = validate_blueprint_policy(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, result_plan,
        )

        assert ok is False
        assert len(violations) > 0

    def test_validate_blueprint_plan_only_valid(self, sample_plan):
        """validate_blueprint_plan_only deve retornar tupla correta para válido."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"] = list(reversed(result_plan["tasks"]))

        ok, violations = validate_blueprint_plan_only(sample_plan, result_plan)

        assert ok is True
        assert violations == []

    def test_validate_blueprint_plan_only_invalid(self, sample_plan):
        """validate_blueprint_plan_only deve retornar tupla correta para inválido."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"].append({"id": "new-task", "phase": "testing"})

        ok, violations = validate_blueprint_plan_only(sample_plan, result_plan)

        assert ok is False
        assert len(violations) > 0


# ==================== TESTS: EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos limite."""

    def test_empty_ir(self, validator, sample_oas, sample_rbac, sample_plan):
        """IR vazio deve ser tratado corretamente."""
        empty_ir = {"domain": {"entities": []}}

        result = validator.validate(
            empty_ir, sample_oas, sample_rbac, sample_plan,
            empty_ir, sample_oas, sample_rbac, sample_plan,
        )

        assert result.ok is True

    def test_empty_oas(self, validator, sample_ir, sample_rbac, sample_plan):
        """OAS vazio deve ser tratado corretamente."""
        empty_oas = {"paths": {}}

        result = validator.validate(
            sample_ir, empty_oas, sample_rbac, sample_plan,
            sample_ir, empty_oas, sample_rbac, sample_plan,
        )

        assert result.ok is True

    def test_empty_plan(self, validator, sample_ir, sample_oas, sample_rbac):
        """PLAN vazio deve ser tratado corretamente."""
        empty_plan = {"tasks": []}

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, empty_plan,
            sample_ir, sample_oas, sample_rbac, empty_plan,
        )

        assert result.ok is True

    def test_task_without_id(self, validator, sample_ir, sample_oas, sample_rbac):
        """Task sem ID deve ser ignorada na verificação."""
        plan_no_id = {"tasks": [{"phase": "backend"}]}

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, plan_no_id,
            sample_ir, sample_oas, sample_rbac, plan_no_id,
        )

        assert result.ok is True

    def test_entity_without_name(self, validator, sample_oas, sample_rbac, sample_plan):
        """Entidade sem name deve ser ignorada na verificação."""
        ir_no_name = {"domain": {"entities": [{"attributes": []}]}}

        result = validator.validate(
            ir_no_name, sample_oas, sample_rbac, sample_plan,
            ir_no_name, sample_oas, sample_rbac, sample_plan,
        )

        assert result.ok is True


# ==================== TESTS: COMBINED VIOLATIONS ====================


class TestCombinedViolations:
    """Testes de múltiplas violações combinadas."""

    def test_all_violations_at_once(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Deve detectar todas as violações combinadas."""
        # Criar entidade nova
        result_ir = deepcopy(sample_ir)
        result_ir["domain"]["entities"].append({"name": "NewEntity", "attributes": []})

        # Criar endpoint novo
        result_oas = deepcopy(sample_oas)
        result_oas["paths"]["/new"] = {"get": {"operationId": "newOp"}}

        # Alterar RBAC
        result_rbac = deepcopy(sample_rbac)
        result_rbac["roles"].append("newrole")

        # Criar task nova
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"].append({"id": "new-task", "phase": "testing"})

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            result_ir, result_oas, result_rbac, result_plan,
        )

        assert result.ok is False
        assert len(result.entities_created) == 1
        assert len(result.endpoints_created) == 1
        assert len(result.contracts_altered) >= 2  # IR e RBAC alterados
        assert len(result.tasks_created) == 1
        assert len(result.violations) >= 4

    def test_violation_messages_are_descriptive(self, validator, sample_ir, sample_oas, sample_rbac, sample_plan):
        """Mensagens de violação devem ser descritivas."""
        result_plan = deepcopy(sample_plan)
        result_plan["tasks"].append({"id": "task-new", "phase": "testing"})

        result = validator.validate(
            sample_ir, sample_oas, sample_rbac, sample_plan,
            sample_ir, sample_oas, sample_rbac, result_plan,
        )

        assert any("Task created outside PLAN: task-new" in v for v in result.violations)
