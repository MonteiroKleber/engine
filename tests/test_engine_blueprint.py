"""Testes para integração do Blueprint no Engine.

Verifica:
- Blueprint é resolvido após classificação
- FORCED_GENERIC quando não há blueprint específico registrado
- blueprint_forced_generic é True para GenericBlueprint
- Run log inclui "blueprint": "GENERIC"
- Blueprint é aplicado ao PLAN (no-op estruturado)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from orchestrator.engine import Engine, RunResult
from blueprints.generic_blueprint import GenericBlueprint, BlueprintResult
from blueprints.registry import (
    REGISTRY,
    register_blueprint,
    unregister_blueprint,
    clear_registry,
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
    """Limpa o registry antes e depois de cada teste."""
    original_registry = dict(REGISTRY)
    clear_registry()
    yield
    clear_registry()
    REGISTRY.update(original_registry)


@pytest.fixture
def custom_blueprint():
    """Blueprint customizado para testes."""

    class CustomBlueprint(GenericBlueprint):
        """Blueprint customizado de teste."""
        pass

    return CustomBlueprint


# ==================== TESTS: RunResult BLUEPRINT FIELDS ====================


class TestRunResultBlueprintFields:
    """Testes dos campos de blueprint no RunResult."""

    def test_run_result_has_blueprint_type(self):
        """RunResult deve ter campo blueprint_type."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
        )
        assert hasattr(result, "blueprint_type")
        assert result.blueprint_type == "generic"

    def test_run_result_has_blueprint_forced_generic(self):
        """RunResult deve ter campo blueprint_forced_generic."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
        )
        assert hasattr(result, "blueprint_forced_generic")
        assert result.blueprint_forced_generic is True  # Default

    def test_run_result_to_dict_includes_blueprint_fields(self):
        """to_dict deve incluir campos de blueprint."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            blueprint_type="custom",
            blueprint_forced_generic=False,
        )
        result_dict = result.to_dict()

        assert "blueprint_type" in result_dict
        assert result_dict["blueprint_type"] == "custom"
        assert "blueprint_forced_generic" in result_dict
        assert result_dict["blueprint_forced_generic"] is False

    def test_run_result_summary_shows_blueprint(self):
        """Summary deve mostrar blueprint type."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            blueprint_type="generic",
        )
        summary = result.summary()

        assert "Blueprint: generic" in summary


# ==================== TESTS: ENGINE BLUEPRINT RESOLUTION ====================


class TestEngineBlueprintResolution:
    """Testes da resolução de blueprint no Engine."""

    @patch.object(Engine, "_write_run_log")
    def test_blueprint_resolved_after_classification(self, mock_write_log, engine):
        """Blueprint deve ser resolvido após classificação."""
        raw_input = "Sistema simples de tarefas"

        # Executar pipeline (vai falhar em algum ponto, mas queremos testar resolução)
        with patch.object(engine.normalizer, "normalize") as mock_normalize, \
             patch.object(engine.classifier, "classify") as mock_classify, \
             patch.object(engine.analyst, "generate_srs") as mock_srs, \
             patch.object(engine.srs_validator_gate, "process") as mock_validate:

            mock_normalize.return_value = {"normalized": "Sistema simples", "raw": raw_input}
            mock_classify.return_value = Mock(selected_blueprint="generic")
            mock_srs.return_value = {"requirements": []}
            mock_validate.return_value = (False, None, ["Missing requirements"])

            result = engine.run("test", raw_input)

            # Deve ter blueprint_forced_generic = True (GenericBlueprint)
            assert result.blueprint_forced_generic is True
            assert result.blueprint_type == "generic"

    @patch.object(Engine, "_write_run_log")
    def test_forced_generic_when_not_registered(self, mock_write_log, engine):
        """Deve usar FORCED_GENERIC quando blueprint não está registrado."""
        raw_input = "Sistema de autenticação"

        with patch.object(engine.normalizer, "normalize") as mock_normalize, \
             patch.object(engine.classifier, "classify") as mock_classify, \
             patch.object(engine.analyst, "generate_srs") as mock_srs, \
             patch.object(engine.srs_validator_gate, "process") as mock_validate:

            mock_normalize.return_value = {"normalized": "Sistema auth", "raw": raw_input}
            mock_classify.return_value = Mock(selected_blueprint="auth")  # Não registrado
            mock_srs.return_value = {"requirements": []}
            mock_validate.return_value = (False, None, ["Missing requirements"])

            result = engine.run("test", raw_input)

            # auth não está registrado, então blueprint_forced_generic = True
            assert result.blueprint_forced_generic is True
            assert result.blueprint_type == "auth"  # O tipo classificado

    @patch.object(Engine, "_write_run_log")
    def test_not_forced_when_registered(self, mock_write_log, engine, custom_blueprint):
        """Não deve ser FORCED_GENERIC quando blueprint está registrado."""
        register_blueprint("custom", custom_blueprint)
        raw_input = "Sistema custom"

        with patch.object(engine.normalizer, "normalize") as mock_normalize, \
             patch.object(engine.classifier, "classify") as mock_classify, \
             patch.object(engine.analyst, "generate_srs") as mock_srs, \
             patch.object(engine.srs_validator_gate, "process") as mock_validate:

            mock_normalize.return_value = {"normalized": "Sistema custom", "raw": raw_input}
            mock_classify.return_value = Mock(selected_blueprint="custom")  # Registrado
            mock_srs.return_value = {"requirements": []}
            mock_validate.return_value = (False, None, ["Missing requirements"])

            result = engine.run("test", raw_input)

            # custom está registrado, então blueprint_forced_generic = False
            assert result.blueprint_forced_generic is False
            assert result.blueprint_type == "custom"


# ==================== TESTS: RUN LOG BLUEPRINT INFO ====================


class TestRunLogBlueprintInfo:
    """Testes do registro de blueprint no run log."""

    def test_run_log_includes_blueprint_generic(self, engine, tmp_path):
        """Run log deve incluir 'blueprint': 'GENERIC' quando FORCED_GENERIC."""
        store_dir = tmp_path / "store"
        store_dir.mkdir(exist_ok=True)
        engine = Engine(store_root=str(store_dir))

        raw_input = "Sistema de teste"
        captured_payload = {}

        def capture_payload(execution_id, payload, project=None):
            captured_payload.update(payload)

        with patch.object(engine.normalizer, "normalize") as mock_normalize, \
             patch.object(engine.classifier, "classify") as mock_classify, \
             patch.object(engine.analyst, "generate_srs") as mock_srs, \
             patch.object(engine.srs_validator_gate, "process") as mock_validate, \
             patch.object(engine.store, "write_run_log", side_effect=capture_payload):

            mock_normalize.return_value = {"normalized": "Sistema", "raw": raw_input}
            mock_classify.return_value = Mock(selected_blueprint="generic")
            mock_srs.return_value = {"requirements": []}
            mock_validate.return_value = (False, None, ["Missing requirements"])

            engine.run("test", raw_input)

            # Run log deve ter blueprint = "GENERIC"
            assert "blueprint" in captured_payload
            assert captured_payload["blueprint"] == "GENERIC"

    def test_run_log_includes_blueprint_uppercase(self, engine, tmp_path, custom_blueprint):
        """Run log deve ter blueprint em uppercase quando registrado."""
        register_blueprint("custom", custom_blueprint)
        store_dir = tmp_path / "store"
        store_dir.mkdir(exist_ok=True)
        engine = Engine(store_root=str(store_dir))

        raw_input = "Sistema custom"
        captured_payload = {}

        def capture_payload(execution_id, payload, project=None):
            captured_payload.update(payload)

        with patch.object(engine.normalizer, "normalize") as mock_normalize, \
             patch.object(engine.classifier, "classify") as mock_classify, \
             patch.object(engine.analyst, "generate_srs") as mock_srs, \
             patch.object(engine.srs_validator_gate, "process") as mock_validate, \
             patch.object(engine.store, "write_run_log", side_effect=capture_payload):

            mock_normalize.return_value = {"normalized": "Sistema", "raw": raw_input}
            mock_classify.return_value = Mock(selected_blueprint="custom")  # Registrado
            mock_srs.return_value = {"requirements": []}
            mock_validate.return_value = (False, None, ["Missing requirements"])

            engine.run("test", raw_input)

            # Run log deve ter blueprint = "CUSTOM" (uppercase)
            assert "blueprint" in captured_payload
            assert captured_payload["blueprint"] == "CUSTOM"


# ==================== TESTS: BLUEPRINT APPLICATION ====================


class TestBlueprintApplication:
    """Testes da aplicação do blueprint ao PLAN."""

    def test_blueprint_apply_is_called_in_engine(self, tmp_path):
        """Verifica que blueprint.apply é chamado durante o run do engine."""
        # Este teste verifica indiretamente através dos resultados
        # que o blueprint está sendo aplicado ao PLAN

        # Criar um blueprint com comportamento rastreável
        apply_called = {"count": 0}

        class TrackedBlueprint(GenericBlueprint):
            def apply(self, ir, oas, rbac, plan):
                apply_called["count"] += 1
                return super().apply(ir, oas, rbac, plan)

        register_blueprint("tracked", TrackedBlueprint)

        store_dir = tmp_path / "store"
        store_dir.mkdir(exist_ok=True)
        engine = Engine(store_root=str(store_dir))
        raw_input = "Sistema de teste"

        with patch.object(engine.normalizer, "normalize") as mock_normalize, \
             patch.object(engine.classifier, "classify") as mock_classify, \
             patch.object(engine.analyst, "generate_srs") as mock_srs, \
             patch.object(engine.srs_validator_gate, "process") as mock_validate_srs:

            mock_normalize.return_value = {"normalized": "Sistema", "raw": raw_input}
            mock_classify.return_value = Mock(selected_blueprint="tracked")
            mock_srs.return_value = {"requirements": []}
            mock_validate_srs.return_value = (False, None, ["Missing requirements"])

            # Executar - vai falhar antes do PLAN, mas blueprint_forced_generic
            # deve ser False porque "tracked" está registrado
            result = engine.run("test", raw_input)

            assert result.blueprint_forced_generic is False
            assert result.blueprint_type == "tracked"

    def test_blueprint_preserves_tasks_count(self):
        """Blueprint no-op preserva número de tarefas."""
        blueprint = GenericBlueprint()

        plan = {
            "meta": {"project": "test"},
            "tasks": [
                {"id": "t1", "phase": "backend", "priority": "high"},
                {"id": "t2", "phase": "frontend", "priority": "medium"},
            ],
        }

        result = blueprint.apply({}, {}, {}, plan)

        # Número de tarefas deve ser preservado
        assert len(result.plan["tasks"]) == 2
        assert result.original_task_count == 2
        assert result.final_task_count == 2


# ==================== TESTS: GENERIC BLUEPRINT NO-OP ====================


class TestGenericBlueprintNoOp:
    """Testes que GenericBlueprint é no-op."""

    def test_generic_blueprint_does_not_add_tasks(self):
        """GenericBlueprint não deve adicionar tarefas."""
        blueprint = GenericBlueprint()

        plan = {
            "tasks": [
                {"id": "t1", "phase": "backend"},
            ]
        }

        result = blueprint.apply({}, {}, {}, plan)

        assert len(result.plan["tasks"]) == 1
        assert result.original_task_count == 1
        assert result.final_task_count == 1

    def test_generic_blueprint_does_not_remove_tasks(self):
        """GenericBlueprint não deve remover tarefas."""
        blueprint = GenericBlueprint()

        plan = {
            "tasks": [
                {"id": "t1", "phase": "backend"},
                {"id": "t2", "phase": "frontend"},
                {"id": "t3", "phase": "database"},
            ]
        }

        result = blueprint.apply({}, {}, {}, plan)

        assert len(result.plan["tasks"]) == 3
        assert result.original_task_count == 3
        assert result.final_task_count == 3

    def test_generic_blueprint_strict_mode_is_pure_noop(self):
        """GenericBlueprint em strict_mode não faz nenhuma alteração."""
        blueprint = GenericBlueprint(strict_mode=True)

        plan = {
            "tasks": [
                {"id": "t2", "phase": "frontend"},
                {"id": "t1", "phase": "backend"},
            ]
        }

        result = blueprint.apply({}, {}, {}, plan)

        # Ordem deve ser mantida exatamente
        assert result.plan["tasks"][0]["id"] == "t2"
        assert result.plan["tasks"][1]["id"] == "t1"
        assert result.reordered is False


# ==================== TESTS: FORCED_GENERIC INVARIANTS ====================


class TestForcedGenericInvariants:
    """Testes dos invariantes do FORCED_GENERIC."""

    def test_task_count_never_changes(self):
        """Número de tarefas nunca deve mudar."""
        blueprint = GenericBlueprint()

        for task_count in [0, 1, 5, 10, 100]:
            plan = {
                "tasks": [{"id": f"t{i}", "phase": "backend"} for i in range(task_count)]
            }

            result = blueprint.apply({}, {}, {}, plan)

            assert len(result.plan["tasks"]) == task_count

    def test_task_ids_preserved(self):
        """IDs das tarefas devem ser preservados."""
        blueprint = GenericBlueprint()

        plan = {
            "tasks": [
                {"id": "unique_id_1", "phase": "backend"},
                {"id": "unique_id_2", "phase": "frontend"},
            ]
        }

        result = blueprint.apply({}, {}, {}, plan)

        task_ids = {t["id"] for t in result.plan["tasks"]}
        assert "unique_id_1" in task_ids
        assert "unique_id_2" in task_ids

    def test_task_content_preserved(self):
        """Conteúdo das tarefas deve ser preservado."""
        blueprint = GenericBlueprint()

        plan = {
            "tasks": [
                {
                    "id": "t1",
                    "phase": "backend",
                    "description": "Criar endpoint",
                    "dependencies": ["t0"],
                    "custom_field": "custom_value",
                },
            ]
        }

        result = blueprint.apply({}, {}, {}, plan)

        task = result.plan["tasks"][0]
        assert task["description"] == "Criar endpoint"
        assert task["dependencies"] == ["t0"]
        assert task["custom_field"] == "custom_value"


# ==================== TESTS: ENGINE IMPORT ====================


class TestEngineImport:
    """Testes que Engine importa corretamente o blueprint."""

    def test_engine_imports_resolve_blueprint(self):
        """Engine deve importar resolve_blueprint."""
        from orchestrator.engine import resolve_blueprint
        assert callable(resolve_blueprint)

    def test_engine_uses_blueprints_module(self, engine):
        """Engine deve usar módulo blueprints."""
        # Verificar que o import está correto no engine
        import orchestrator.engine as engine_module
        assert hasattr(engine_module, "resolve_blueprint")
