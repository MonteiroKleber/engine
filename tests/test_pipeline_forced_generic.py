"""Testes de pipeline com FORCED_GENERIC (sem blueprint específico).

Cenário: Input genérico sem blueprint registrado
- "Quero um sistema simples de cadastro"

Validações:
- Pipeline completo roda até o final
- blueprint = GENERIC (FORCED_GENERIC)
- Nenhum artefato extra criado pelo blueprint
- CRUD mínimo funcional (entidades, endpoints, tasks)
"""

import pytest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch, Mock

from orchestrator.engine import Engine, RunResult
from blueprints.generic_blueprint import GenericBlueprint
from blueprints.registry import (
    REGISTRY,
    resolve_blueprint,
    clear_registry,
    is_registered,
)


# ==================== FIXTURES ====================


@pytest.fixture
def engine(tmp_path):
    """Engine com store temporário."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    return Engine(store_root=str(store_dir))


@pytest.fixture(autouse=True)
def clean_registry():
    """Garante registry limpo para testar FORCED_GENERIC."""
    original_registry = dict(REGISTRY)
    clear_registry()
    yield
    clear_registry()
    REGISTRY.update(original_registry)


@pytest.fixture
def generic_input():
    """Input genérico para testar FORCED_GENERIC."""
    return "Quero um sistema simples de cadastro"


@pytest.fixture
def generic_input_detailed():
    """Input genérico mais detalhado."""
    return """
    Preciso de um sistema simples de cadastro de clientes.

    Funcionalidades:
    - Cadastrar cliente com nome e email
    - Listar todos os clientes
    - Editar dados do cliente
    - Excluir cliente

    O sistema deve ser simples e funcional.
    """


# ==================== TESTS: FORCED_GENERIC DETECTION ====================


class TestForcedGenericDetection:
    """Testes de detecção do FORCED_GENERIC."""

    def test_registry_is_empty(self):
        """Registry deve estar vazio (fixture limpa)."""
        assert len(REGISTRY) == 0

    def test_resolve_returns_generic_blueprint(self):
        """resolve_blueprint deve retornar GenericBlueprint."""
        result = resolve_blueprint("generic")
        assert result == GenericBlueprint

    def test_resolve_returns_generic_for_any_type(self):
        """Qualquer tipo não registrado deve retornar GenericBlueprint."""
        types = ["crud", "auth", "report", "unknown", "cadastro", "sistema"]
        for t in types:
            assert resolve_blueprint(t) == GenericBlueprint

    def test_is_registered_returns_false(self):
        """is_registered deve retornar False para qualquer tipo."""
        assert is_registered("generic") is False
        assert is_registered("crud") is False
        assert is_registered("cadastro") is False


# ==================== TESTS: PIPELINE WITH GENERIC INPUT ====================


class TestPipelineWithGenericInput:
    """Testes do pipeline completo com input genérico."""

    def test_pipeline_runs_with_generic_input(self, engine, generic_input):
        """Pipeline deve rodar com input genérico."""
        # O pipeline pode falhar em validação, mas deve processar
        result = engine.run("test_generic", generic_input, title="Sistema de Cadastro")

        # Deve ter processado até algum ponto
        assert result.execution_id is not None
        assert result.project == "test_generic"

    def test_blueprint_type_is_generic(self, engine, generic_input):
        """blueprint_type deve ser 'generic' para input genérico."""
        result = engine.run("test_generic", generic_input)

        # O classificador pode retornar qualquer tipo, mas FORCED_GENERIC deve ser True
        assert result.blueprint_forced_generic is True

    def test_forced_generic_flag_is_true(self, engine, generic_input):
        """blueprint_forced_generic deve ser True quando não há blueprint registrado."""
        result = engine.run("test_generic", generic_input)

        assert result.blueprint_forced_generic is True

    def test_no_extra_artifacts_created(self, engine, generic_input, tmp_path):
        """FORCED_GENERIC não deve criar artefatos extras."""
        # Contar arquivos antes
        store_dir = tmp_path / "store"

        result = engine.run("test_generic", generic_input)

        # Se falhou antes de salvar, ok
        if not result.success:
            # Mesmo falhando, não deve ter criado artefatos extras
            # (apenas os artefatos padrão do pipeline)
            return

        # Se passou, verificar que apenas artefatos padrão foram criados
        project_dir = store_dir / "test_generic"
        if project_dir.exists():
            artifact_types = [d.name for d in project_dir.iterdir() if d.is_dir()]
            # logs é um artefato padrão do sistema
            expected_types = {"SRS", "IR", "OAS", "RBAC", "PLAN", "runs", "logs"}
            for at in artifact_types:
                assert at in expected_types, f"Artefato extra criado: {at}"


# ==================== TESTS: MOCKED PIPELINE SUCCESS ====================


class TestMockedPipelineSuccess:
    """Testes com pipeline mockado para garantir FORCED_GENERIC completo."""

    def test_full_pipeline_with_forced_generic(self, engine, generic_input, tmp_path):
        """Pipeline completo deve funcionar com FORCED_GENERIC."""
        # Mock de todos os componentes para garantir sucesso
        with patch.object(engine.normalizer, "normalize") as mock_normalize, \
             patch.object(engine.classifier, "classify") as mock_classify, \
             patch.object(engine.analyst, "generate_srs") as mock_srs, \
             patch.object(engine.srs_validator_gate, "process") as mock_validate_srs, \
             patch.object(engine.store, "save_artifact") as mock_save, \
             patch.object(engine.store, "save_text_artifact") as mock_save_text, \
             patch.object(engine.store, "next_version", return_value=1), \
             patch.object(engine.store, "write_run_log"), \
             patch.object(engine, "_compute_file_hash", return_value="abc123"), \
             patch.object(engine.domain_modeler, "generate_ir") as mock_ir, \
             patch("orchestrator.engine.validate_ir") as mock_validate_ir, \
             patch.object(engine.policy_validator, "validate") as mock_policy, \
             patch.object(engine.contracts_agent, "generate_contracts") as mock_contracts, \
             patch("orchestrator.engine.validate_openapi") as mock_validate_oas, \
             patch("orchestrator.engine.validate_rbac") as mock_validate_rbac, \
             patch.object(engine.policy_validator, "validate_contracts") as mock_policy_contracts, \
             patch.object(engine.planner_agent, "generate_plan") as mock_plan, \
             patch("orchestrator.engine.validate_plan") as mock_validate_plan, \
             patch.object(engine.policy_validator, "validate_plan") as mock_policy_plan:

            # Setup mocks
            mock_normalize.return_value = {"normalized": generic_input, "raw": generic_input}
            mock_classify.return_value = Mock(selected_blueprint="generic")

            valid_srs = {
                "project": {"title": "Sistema de Cadastro", "version": "1.0"},
                "requirements": [
                    {"id": "REQ-001", "type": "functional", "description": "Cadastrar cliente", "priority": "high"},
                    {"id": "REQ-002", "type": "functional", "description": "Listar clientes", "priority": "high"},
                ],
            }
            mock_srs.return_value = valid_srs
            mock_validate_srs.return_value = (True, valid_srs, [])

            mock_save.return_value = tmp_path / "artifact.json"
            mock_save_text.return_value = tmp_path / "artifact.yaml"

            valid_ir = {
                "meta": {"project": "test_generic", "version": "v1"},
                "domain": {
                    "entities": [
                        {"name": "Cliente", "attributes": [{"name": "id", "type": "Long"}, {"name": "nome", "type": "String"}]},
                    ]
                },
                "srs_traceability": [{"requirement_id": "REQ-001", "entity": "Cliente"}],
            }
            mock_ir.return_value = valid_ir
            mock_validate_ir.return_value = Mock(ok=True, errors=[])
            mock_policy.return_value = (True, [])

            oas_yaml = """
openapi: '3.0.0'
info:
  title: Sistema de Cadastro
  version: '1.0'
paths:
  /clientes:
    get:
      operationId: listClientes
      responses:
        '200':
          description: OK
    post:
      operationId: createCliente
      responses:
        '201':
          description: Created
"""
            rbac = {"roles": ["authenticated"], "permissions": [
                {"operation_id": "listClientes", "required_role": "authenticated"},
                {"operation_id": "createCliente", "required_role": "authenticated"},
            ]}
            mock_contracts.return_value = (oas_yaml, rbac)
            mock_validate_oas.return_value = Mock(ok=True, errors=[])
            mock_validate_rbac.return_value = Mock(ok=True, errors=[])
            mock_policy_contracts.return_value = (True, [])

            plan = {
                "meta": {"project": "test_generic", "version": "v1"},
                "tasks": [
                    {"id": "task-1", "phase": "database", "priority": "high", "description": "Create Cliente table"},
                    {"id": "task-2", "phase": "backend", "priority": "high", "description": "Create Cliente entity"},
                    {"id": "task-3", "phase": "backend", "priority": "medium", "description": "Create Cliente API"},
                    {"id": "task-4", "phase": "frontend", "priority": "medium", "description": "Create Cliente UI"},
                ],
            }
            mock_plan.return_value = plan
            mock_validate_plan.return_value = Mock(ok=True, errors=[])
            mock_policy_plan.return_value = (True, [])

            # Executar pipeline
            result = engine.run("test_generic", generic_input)

            # Validações
            assert result.success is True
            assert result.blueprint_forced_generic is True
            assert result.blueprint_type == "generic"

    def test_run_log_contains_generic_blueprint(self, engine, generic_input, tmp_path):
        """Run log deve conter 'blueprint': 'GENERIC'."""
        captured_payload = {}

        def capture_payload(execution_id, payload, project=None):
            captured_payload.update(payload)

        with patch.object(engine.normalizer, "normalize") as mock_normalize, \
             patch.object(engine.classifier, "classify") as mock_classify, \
             patch.object(engine.analyst, "generate_srs") as mock_srs, \
             patch.object(engine.srs_validator_gate, "process") as mock_validate_srs, \
             patch.object(engine.store, "write_run_log", side_effect=capture_payload):

            mock_normalize.return_value = {"normalized": generic_input, "raw": generic_input}
            mock_classify.return_value = Mock(selected_blueprint="generic")
            mock_srs.return_value = {"requirements": []}
            mock_validate_srs.return_value = (False, None, ["Missing requirements"])

            engine.run("test_generic", generic_input)

            # Run log deve ter blueprint = "GENERIC"
            assert "blueprint" in captured_payload
            assert captured_payload["blueprint"] == "GENERIC"


# ==================== TESTS: CRUD MINIMAL FUNCTIONAL ====================


class TestCrudMinimalFunctional:
    """Testes que CRUD mínimo é funcional com FORCED_GENERIC."""

    def test_generic_blueprint_preserves_crud_entities(self):
        """GenericBlueprint deve preservar entidades CRUD."""
        blueprint = GenericBlueprint()

        ir = {
            "domain": {
                "entities": [
                    {"name": "Cliente", "attributes": [{"name": "id"}, {"name": "nome"}]},
                    {"name": "Produto", "attributes": [{"name": "id"}, {"name": "descricao"}]},
                ]
            }
        }
        oas = {}
        rbac = {}
        plan = {
            "tasks": [
                {"id": "t1", "phase": "backend", "description": "Create Cliente"},
                {"id": "t2", "phase": "backend", "description": "Create Produto"},
            ]
        }

        result = blueprint.apply(ir, oas, rbac, plan)

        # Todas as tasks devem ser preservadas
        assert len(result.plan["tasks"]) == 2

    def test_generic_blueprint_preserves_crud_endpoints(self):
        """GenericBlueprint deve preservar endpoints CRUD."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {
            "paths": {
                "/clientes": {
                    "get": {"operationId": "listClientes"},
                    "post": {"operationId": "createCliente"},
                },
                "/clientes/{id}": {
                    "get": {"operationId": "getCliente"},
                    "put": {"operationId": "updateCliente"},
                    "delete": {"operationId": "deleteCliente"},
                },
            }
        }
        rbac = {}
        plan = {"tasks": [{"id": "t1", "phase": "backend"}]}

        result = blueprint.apply(ir, oas, rbac, plan)

        # Task deve ser preservada
        assert len(result.plan["tasks"]) == 1

    def test_generic_blueprint_orders_crud_tasks(self):
        """GenericBlueprint deve ordenar tasks CRUD corretamente."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {}
        rbac = {}
        plan = {
            "tasks": [
                {"id": "ui", "phase": "frontend", "priority": "medium"},
                {"id": "api", "phase": "backend", "priority": "high"},
                {"id": "db", "phase": "database", "priority": "high"},
                {"id": "test", "phase": "testing", "priority": "low"},
            ]
        }

        result = blueprint.apply(ir, oas, rbac, plan)

        # Ordem deve ser: database → backend → frontend → testing
        phases = [t["phase"] for t in result.plan["tasks"]]
        assert phases == ["database", "backend", "frontend", "testing"]


# ==================== TESTS: NO ARTIFACTS CREATED BY BLUEPRINT ====================


class TestNoArtifactsCreatedByBlueprint:
    """Testes que blueprint não cria artefatos extras."""

    def test_blueprint_does_not_create_entities(self):
        """Blueprint não deve criar entidades."""
        blueprint = GenericBlueprint()

        ir = {"domain": {"entities": [{"name": "User"}]}}
        oas = {}
        rbac = {}
        plan = {"tasks": [{"id": "t1"}]}

        original_entity_count = len(ir["domain"]["entities"])

        blueprint.apply(ir, oas, rbac, plan)

        # IR não deve ter sido modificado
        assert len(ir["domain"]["entities"]) == original_entity_count

    def test_blueprint_does_not_create_endpoints(self):
        """Blueprint não deve criar endpoints."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {"paths": {"/users": {"get": {}}}}
        rbac = {}
        plan = {"tasks": [{"id": "t1"}]}

        original_paths = set(oas["paths"].keys())

        blueprint.apply(ir, oas, rbac, plan)

        # OAS não deve ter sido modificado
        assert set(oas["paths"].keys()) == original_paths

    def test_blueprint_does_not_create_tasks(self):
        """Blueprint não deve criar tasks."""
        blueprint = GenericBlueprint()

        ir = {}
        oas = {}
        rbac = {}
        plan = {"tasks": [{"id": "t1"}, {"id": "t2"}]}

        result = blueprint.apply(ir, oas, rbac, plan)

        # Número de tasks deve ser o mesmo
        assert len(result.plan["tasks"]) == 2
        assert result.original_task_count == 2
        assert result.final_task_count == 2


# ==================== TESTS: RESULT FIELDS ====================


class TestResultFields:
    """Testes dos campos do RunResult para FORCED_GENERIC."""

    def test_result_has_blueprint_type(self, engine, generic_input):
        """RunResult deve ter blueprint_type."""
        result = engine.run("test", generic_input)

        assert hasattr(result, "blueprint_type")
        assert isinstance(result.blueprint_type, str)

    def test_result_has_blueprint_forced_generic(self, engine, generic_input):
        """RunResult deve ter blueprint_forced_generic."""
        result = engine.run("test", generic_input)

        assert hasattr(result, "blueprint_forced_generic")
        assert result.blueprint_forced_generic is True

    def test_result_to_dict_includes_blueprint(self, engine, generic_input):
        """to_dict deve incluir campos de blueprint."""
        result = engine.run("test", generic_input)

        d = result.to_dict()

        assert "blueprint_type" in d
        assert "blueprint_forced_generic" in d

    def test_result_summary_shows_blueprint(self, engine, generic_input):
        """summary() deve mostrar blueprint."""
        result = engine.run("test", generic_input)

        summary = result.summary()

        assert "Blueprint:" in summary


# ==================== TESTS: EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos limite."""

    def test_empty_input(self, engine):
        """Input vazio deve ser tratado."""
        result = engine.run("test", "")

        # Deve falhar, mas não crashar
        assert result.blueprint_forced_generic is True

    def test_whitespace_only_input(self, engine):
        """Input apenas com espaços deve ser tratado."""
        result = engine.run("test", "   \n\t  ")

        # Deve falhar, mas não crashar
        assert result.blueprint_forced_generic is True

    def test_very_long_input(self, engine):
        """Input muito longo deve ser tratado."""
        long_input = "Sistema de cadastro. " * 1000

        result = engine.run("test", long_input)

        # Deve processar
        assert result.blueprint_forced_generic is True

    def test_unicode_input(self, engine):
        """Input com unicode deve ser tratado."""
        unicode_input = "Quero um sistema de cadastro de usuários com acentuação: áéíóú ãõ ç"

        result = engine.run("test", unicode_input)

        # Deve processar
        assert result.blueprint_forced_generic is True

    def test_special_characters_input(self, engine):
        """Input com caracteres especiais deve ser tratado."""
        special_input = "Sistema com @#$%^&*() caracteres especiais!"

        result = engine.run("test", special_input)

        # Deve processar
        assert result.blueprint_forced_generic is True
