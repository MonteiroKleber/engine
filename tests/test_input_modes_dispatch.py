"""Testes para Input Modes Dispatch.

Testa os 3 modos de entrada do motor:
- NATURAL: texto livre → Draft → GATE 1 → GATE 2 → IDL v1
- DRAFT: IDL Draft v1 JSON → GATE 1 → GATE 2 → IDL v1
- IDL: IDL v1 (texto .idl ou JSON) → Contract Gate

E detecção automática (AUTO).
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from orchestrator.input_mode import (
    InputMode,
    InputModeError,
    parse_input_mode,
    detect_input_mode_auto,
    validate_input_mode_match,
)
from orchestrator.input_dispatcher import (
    InputDispatcher,
    InputDispatchResult,
    dispatch_input,
)
from idl import IDL_SCHEMA_VERSION, IDL_DRAFT_SCHEMA_VERSION


class TestInputModeEnum:
    """Testes do enum InputMode."""

    def test_input_mode_values(self):
        """InputMode tem valores corretos."""
        assert InputMode.NATURAL.value == "natural"
        assert InputMode.DRAFT.value == "draft"
        assert InputMode.IDL.value == "idl"
        assert InputMode.AUTO.value == "auto"

    def test_parse_input_mode_valid(self):
        """parse_input_mode aceita valores válidos."""
        assert parse_input_mode("natural") == InputMode.NATURAL
        assert parse_input_mode("draft") == InputMode.DRAFT
        assert parse_input_mode("idl") == InputMode.IDL
        assert parse_input_mode("auto") == InputMode.AUTO

    def test_parse_input_mode_case_insensitive(self):
        """parse_input_mode é case-insensitive."""
        assert parse_input_mode("NATURAL") == InputMode.NATURAL
        assert parse_input_mode("Draft") == InputMode.DRAFT
        assert parse_input_mode("IDL") == InputMode.IDL
        assert parse_input_mode("AUTO") == InputMode.AUTO

    def test_parse_input_mode_invalid(self):
        """parse_input_mode rejeita valores inválidos."""
        with pytest.raises(ValueError) as exc_info:
            parse_input_mode("invalid")
        assert "Invalid input mode" in str(exc_info.value)


class TestAutoDetection:
    """Testes de detecção automática de modo."""

    def test_detect_idl_by_extension(self):
        """AUTO detecta IDL por extensão .idl."""
        mode, reason = detect_input_mode_auto(
            "system Test {}",
            "/path/to/spec.idl",
        )
        assert mode == InputMode.IDL
        assert ".idl" in reason

    def test_detect_idl_by_json_schema_version(self):
        """AUTO detecta IDL por JSON schema_version idl.v1."""
        json_content = json.dumps({
            "schema_version": IDL_SCHEMA_VERSION,
            "system": {"id": "test", "name": "Test"},
        })
        mode, reason = detect_input_mode_auto(json_content, "/path/to/spec.json")
        assert mode == InputMode.IDL
        assert IDL_SCHEMA_VERSION in reason

    def test_detect_draft_by_json_schema_version(self):
        """AUTO detecta DRAFT por JSON schema_version idl_draft.v1."""
        json_content = json.dumps({
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "test",
        })
        mode, reason = detect_input_mode_auto(json_content, "/path/to/draft.json")
        assert mode == InputMode.DRAFT
        assert IDL_DRAFT_SCHEMA_VERSION in reason

    def test_detect_natural_by_text(self):
        """AUTO detecta NATURAL por texto livre."""
        mode, reason = detect_input_mode_auto(
            "Quero um sistema de cadastro de empresas",
            None,
        )
        assert mode == InputMode.NATURAL
        assert "free-form text" in reason

    def test_detect_idl_by_keywords(self):
        """AUTO detecta IDL por keywords (system, actor, entity)."""
        mode, reason = detect_input_mode_auto(
            "system TestSystem { name: \"Test\" }",
            None,
        )
        assert mode == InputMode.IDL
        assert "IDL v1 keywords" in reason

    def test_detect_idl_by_actor_keyword(self):
        """AUTO detecta IDL por keyword actor."""
        mode, reason = detect_input_mode_auto(
            "actor Admin : human { permissions: [all] }",
            None,
        )
        assert mode == InputMode.IDL
        assert "keywords" in reason

    def test_detect_idl_by_entity_keyword(self):
        """AUTO detecta IDL por keyword entity."""
        mode, reason = detect_input_mode_auto(
            "entity User { id: uuid }",
            None,
        )
        assert mode == InputMode.IDL
        assert "keywords" in reason

    def test_error_on_unknown_json_schema_version(self):
        """AUTO falha com erro em JSON sem schema_version conhecido."""
        json_content = json.dumps({
            "schema_version": "unknown.v1",
            "data": "test",
        })
        with pytest.raises(InputModeError) as exc_info:
            detect_input_mode_auto(json_content, "/path/to/file.json")
        assert "Unknown schema_version" in str(exc_info.value)

    def test_error_on_json_without_schema_version(self):
        """AUTO falha com erro em JSON sem schema_version."""
        json_content = json.dumps({"data": "test"})
        with pytest.raises(InputModeError) as exc_info:
            detect_input_mode_auto(json_content, "/path/to/file.json")
        assert "no 'schema_version' field" in str(exc_info.value)

    def test_error_on_diagnostic_report_schema(self):
        """AUTO falha com erro claro em DiagnosticReport."""
        json_content = json.dumps({
            "schema_version": "diagnostic_report.v1",
            "report": {},
        })
        with pytest.raises(InputModeError) as exc_info:
            detect_input_mode_auto(json_content, "/path/to/report.json")
        assert "DiagnosticReport" in str(exc_info.value)


class TestInputModeValidation:
    """Testes de validação de modo declarado vs detectado."""

    def test_validate_idl_declared_but_draft_content(self):
        """Falha quando --input-mode=idl mas conteúdo é Draft."""
        with pytest.raises(InputModeError) as exc_info:
            validate_input_mode_match(
                InputMode.IDL,
                InputMode.DRAFT,
                "test.json",
            )
        assert "input-mode=idl" in str(exc_info.value)
        assert "input-mode=draft" in str(exc_info.value)

    def test_validate_draft_declared_but_idl_content(self):
        """Falha quando --input-mode=draft mas conteúdo é IDL."""
        with pytest.raises(InputModeError) as exc_info:
            validate_input_mode_match(
                InputMode.DRAFT,
                InputMode.IDL,
                "test.json",
            )
        assert "input-mode=draft" in str(exc_info.value)
        assert "input-mode=idl" in str(exc_info.value)

    def test_validate_auto_always_passes(self):
        """AUTO não precisa validar correspondência."""
        # Não deve lançar exceção
        validate_input_mode_match(InputMode.AUTO, InputMode.IDL, "test")
        validate_input_mode_match(InputMode.AUTO, InputMode.DRAFT, "test")
        validate_input_mode_match(InputMode.AUTO, InputMode.NATURAL, "test")

    def test_validate_natural_accepts_anything(self):
        """NATURAL aceita qualquer coisa (vai tentar processar)."""
        # Não deve lançar exceção
        validate_input_mode_match(InputMode.NATURAL, InputMode.IDL, "test")
        validate_input_mode_match(InputMode.NATURAL, InputMode.DRAFT, "test")


class TestDispatcherIDLMode:
    """Testes do dispatcher para modo IDL."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria store temporário."""
        return str(tmp_path / "store")

    def test_dispatch_idl_text_file(self, temp_store):
        """Dispatch IDL de arquivo .idl."""
        idl_content = """
        system TestSystem {
            name: "Test System"
        }
        """
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.IDL,
            input_payload=idl_content,
            input_path="/path/to/spec.idl",
        )

        assert result.success is True
        assert result.input_mode_resolved == InputMode.IDL
        assert result.idl_schema_version == IDL_SCHEMA_VERSION
        assert result.idl_content_hash != ""
        assert result.draft_used is False

    def test_dispatch_idl_does_not_call_gates(self, temp_store):
        """IDL mode não passa por GATE 1 ou GATE 2."""
        idl_content = """
        system TestSystem {
            name: "Test"
        }
        """
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.IDL,
            input_payload=idl_content,
            input_path="/path/to/spec.idl",
        )

        assert result.success is True
        # Não deve ter erros de gate
        assert result.gate1_errors == []
        assert result.gate2_errors == []
        assert result.draft_used is False


class TestDispatcherDraftMode:
    """Testes do dispatcher para modo DRAFT."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria store temporário."""
        return str(tmp_path / "store")

    def test_dispatch_draft_valid(self, temp_store):
        """Dispatch Draft válido passa GATE 1 e GATE 2."""
        draft_json = json.dumps({
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "test",
            "actors": [
                {"id": "admin", "role": "administrator", "permissions": []},
            ],
        })
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.DRAFT,
            input_payload=draft_json,
        )

        assert result.success is True
        assert result.input_mode_resolved == InputMode.DRAFT
        assert result.draft_used is True
        assert result.draft_schema_version == IDL_DRAFT_SCHEMA_VERSION
        assert result.idl_schema_version == IDL_SCHEMA_VERSION

    def test_dispatch_draft_gate1_failure(self, temp_store):
        """Draft com estrutura inválida falha no GATE 1."""
        # Schema version correto mas actor com campo inválido
        draft_json = json.dumps({
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "test",
            "actors": [
                {"id": 123, "role": "admin"},  # id should be string, not int
            ],
        })
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.DRAFT,
            input_payload=draft_json,
        )

        assert result.success is False
        assert "GATE 1" in result.errors[0]
        assert len(result.gate1_errors) > 0

    def test_dispatch_draft_gate2_failure_open_questions(self, temp_store):
        """Draft com open_questions falha no GATE 2."""
        draft_json = json.dumps({
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "test",
            "actors": [
                {"id": "admin", "role": "admin", "permissions": []},
            ],
            "open_questions": ["What about authentication?"],
        })
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.DRAFT,
            input_payload=draft_json,
        )

        assert result.success is False
        assert "GATE 2" in result.errors[0]
        assert len(result.gate2_errors) > 0

    def test_dispatch_draft_gate2_failure_unknown_fields(self, temp_store):
        """Draft com campos unknown falha no GATE 2."""
        draft_json = json.dumps({
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "test",
            "actors": [
                {"id": "admin", "role": "unknown", "permissions": []},
            ],
        })
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.DRAFT,
            input_payload=draft_json,
        )

        assert result.success is False
        assert "GATE 2" in result.errors[0]
        assert len(result.gate2_errors) > 0


class TestDispatcherNaturalMode:
    """Testes do dispatcher para modo NATURAL."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria store temporário."""
        return str(tmp_path / "store")

    def test_dispatch_natural_blocks_at_gate2(self, temp_store):
        """NATURAL sempre bloqueia no GATE 2 (requer intake compiler)."""
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.NATURAL,
            input_payload="Quero um sistema de cadastro de empresas",
        )

        # NATURAL sem intake compiler deve bloquear no GATE 2
        assert result.success is False
        assert result.input_mode_resolved == InputMode.NATURAL
        assert result.draft_used is True
        assert "GATE 2" in result.errors[0] or "open_questions" in str(result.errors)


class TestDispatcherAutoMode:
    """Testes do dispatcher para modo AUTO."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria store temporário."""
        return str(tmp_path / "store")

    def test_auto_detects_idl_by_extension(self, temp_store):
        """AUTO detecta IDL por extensão e vai para caminho IDL."""
        idl_content = """
        system TestSystem {
            name: "Test"
        }
        """
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.AUTO,
            input_payload=idl_content,
            input_path="/path/to/spec.idl",
        )

        assert result.success is True
        assert result.input_mode_resolved == InputMode.IDL
        assert ".idl" in result.detection_reason

    def test_auto_detects_draft_by_json(self, temp_store):
        """AUTO detecta DRAFT por JSON e aplica GATE 1 + GATE 2."""
        draft_json = json.dumps({
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "test",
            "actors": [
                {"id": "admin", "role": "admin", "permissions": []},
            ],
        })
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.AUTO,
            input_payload=draft_json,
            input_path="/path/to/draft.json",
        )

        assert result.success is True
        assert result.input_mode_resolved == InputMode.DRAFT
        assert result.draft_used is True

    def test_auto_detects_idl_json_by_schema(self, temp_store):
        """AUTO detecta IDL JSON por schema_version e aplica Contract Gate."""
        # Para IDL JSON, precisamos de um documento válido
        idl_content = """
        system TestSystem {
            name: "Test"
        }
        """
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.AUTO,
            input_payload=idl_content,
            input_path="/path/to/spec.idl",
        )

        assert result.success is True
        assert result.input_mode_resolved == InputMode.IDL

    def test_auto_detects_natural_by_text(self, temp_store):
        """AUTO detecta NATURAL por texto e bloqueia no GATE 2."""
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.AUTO,
            input_payload="Quero um sistema de cadastro de empresas",
        )

        assert result.success is False
        assert result.input_mode_resolved == InputMode.NATURAL
        assert "GATE 2" in result.errors[0] or "open_questions" in str(result.errors)

    def test_auto_fails_on_unknown_json(self, temp_store):
        """AUTO falha em JSON com schema_version desconhecido."""
        json_content = json.dumps({
            "schema_version": "unknown.v1",
            "data": "test",
        })
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.AUTO,
            input_payload=json_content,
            input_path="/path/to/file.json",
        )

        assert result.success is False
        assert "Unknown schema_version" in result.errors[0]


class TestInputModeMismatch:
    """Testes de mismatch entre modo declarado e conteúdo."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria store temporário."""
        return str(tmp_path / "store")

    def test_idl_mode_with_draft_json_fails(self, temp_store):
        """--input-mode=idl com Draft JSON falha com mensagem clara."""
        draft_json = json.dumps({
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "test",
        })
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.IDL,
            input_payload=draft_json,
            input_path="/path/to/file.json",
        )

        assert result.success is False
        assert "input-mode=idl" in result.errors[0]
        assert "input-mode=draft" in result.errors[0]

    def test_draft_mode_with_idl_json_fails(self, temp_store):
        """--input-mode=draft com IDL JSON falha com mensagem clara."""
        idl_json = json.dumps({
            "schema_version": IDL_SCHEMA_VERSION,
            "system": {"id": "test", "name": "Test"},
        })
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.DRAFT,
            input_payload=idl_json,
            input_path="/path/to/file.json",
        )

        assert result.success is False
        assert "input-mode=draft" in result.errors[0]
        assert "input-mode=idl" in result.errors[0]


class TestResultIncludesInputMode:
    """Testes que o resultado inclui input_mode_resolved."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria store temporário."""
        return str(tmp_path / "store")

    def test_result_includes_input_mode_resolved(self, temp_store):
        """Resultado inclui input_mode_resolved."""
        idl_content = """
        system TestSystem {
            name: "Test"
        }
        """
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.AUTO,
            input_payload=idl_content,
            input_path="/path/to/spec.idl",
        )

        assert result.input_mode_resolved is not None
        assert result.input_mode_resolved in [InputMode.IDL, InputMode.DRAFT, InputMode.NATURAL]

    def test_result_to_dict_includes_mode(self, temp_store):
        """Result.to_dict() inclui input_mode_resolved."""
        idl_content = """
        system TestSystem {
            name: "Test"
        }
        """
        dispatcher = InputDispatcher(temp_store)
        result = dispatcher.dispatch(
            project="test",
            input_mode=InputMode.IDL,
            input_payload=idl_content,
            input_path="/path/to/spec.idl",
        )

        result_dict = result.to_dict()
        assert "input_mode_resolved" in result_dict
        assert result_dict["input_mode_resolved"] == "idl"


class TestNoLLMInDraftOrIDL:
    """Testes garantindo que DRAFT/IDL não chamam LLM."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria store temporário."""
        return str(tmp_path / "store")

    def test_draft_mode_no_intake_called(self, temp_store):
        """DRAFT mode não chama intake/LLM."""
        draft_json = json.dumps({
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "test",
            "actors": [
                {"id": "admin", "role": "admin", "permissions": []},
            ],
        })

        # Mock para verificar que intake não é chamado
        with patch("orchestrator.input_dispatcher.InputDispatcher._dispatch_natural") as mock_natural:
            dispatcher = InputDispatcher(temp_store)
            result = dispatcher.dispatch(
                project="test",
                input_mode=InputMode.DRAFT,
                input_payload=draft_json,
            )

            # _dispatch_natural não deve ser chamado
            mock_natural.assert_not_called()

    def test_idl_mode_no_intake_called(self, temp_store):
        """IDL mode não chama intake/LLM."""
        idl_content = """
        system TestSystem {
            name: "Test"
        }
        """

        # Mock para verificar que intake não é chamado
        with patch("orchestrator.input_dispatcher.InputDispatcher._dispatch_natural") as mock_natural:
            dispatcher = InputDispatcher(temp_store)
            result = dispatcher.dispatch(
                project="test",
                input_mode=InputMode.IDL,
                input_payload=idl_content,
                input_path="/path/to/spec.idl",
            )

            # _dispatch_natural não deve ser chamado
            mock_natural.assert_not_called()


class TestConvenienceFunction:
    """Testes da função de conveniência dispatch_input."""

    def test_dispatch_input_convenience(self, tmp_path):
        """dispatch_input funciona como wrapper."""
        idl_content = """
        system TestSystem {
            name: "Test"
        }
        """
        store_root = str(tmp_path / "store")

        result = dispatch_input(
            project="test",
            input_mode=InputMode.IDL,
            input_payload=idl_content,
            input_path="/path/to/spec.idl",
            store_root=store_root,
        )

        assert result.success is True
        assert result.input_mode_resolved == InputMode.IDL
