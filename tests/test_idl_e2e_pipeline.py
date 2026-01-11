"""Testes E2E para IDL textual como entrada do pipeline.

Valida que --input-mode idl funciona end-to-end:
1. IDL textual → parse → IR → OAS → artefatos
2. Erros de parse são classificados corretamente
3. O modo IDL não é ignorado (idl_to_ir é chamado)
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from orchestrator.engine import Engine
from idl.idl_to_ir import idl_to_ir, IDLToIRError


# Fixture: IDL textual mínimo válido
MINIMAL_IDL = """
system lojas {
    name: "Sistema de Cadastro de Lojas"
    description: "Sistema para gerenciamento de lojas"
    version: "1.0.0"
    domain: "retail"
}

actors {
    human admin {
        name: "Administrador"
        description: "Administrador do sistema"
        permissions: [manage_stores, view_reports]
        authentication: token
    }
}

entities {
    entity Store {
        field id: uuid required unique
        field name: string required
        field cnpj: string required unique
        field is_active: bool default(true)
    }
}

usecases {
    usecase create_store {
        name: "Cadastrar Loja"
        description: "Permite cadastrar uma nova loja"
        actor: admin
        priority: high
        complexity: simple
    }

    usecase list_stores {
        name: "Listar Lojas"
        description: "Lista todas as lojas"
        actor: admin
        priority: high
        complexity: simple
    }
}
"""

# Fixture: IDL inválido
INVALID_IDL = """
system broken {
    name "Missing colon"
}
"""

# Fixture: IDL sem entidades
IDL_NO_ENTITIES = """
system empty {
    name: "Sistema Vazio"
}

actors {
    human user {
        name: "Usuário"
    }
}
"""


class TestIDLPipelineE2E:
    """Testes E2E do pipeline com entrada IDL."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretório temporário para store."""
        store = tmp_path / "store"
        store.mkdir()
        return str(store)

    @pytest.fixture
    def temp_generated(self, tmp_path):
        """Cria diretório temporário para generated."""
        generated = tmp_path / "generated"
        generated.mkdir()
        return str(generated)

    @pytest.fixture
    def idl_file(self, tmp_path):
        """Cria arquivo IDL temporário."""
        idl_path = tmp_path / "spec.idl"
        idl_path.write_text(MINIMAL_IDL, encoding="utf-8")
        return str(idl_path)

    def test_idl_to_pipeline_generates_artifacts(self, temp_store, temp_generated, idl_file):
        """[E2E] IDL textual → pipeline → artefatos gerados (skip build)."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="lojas_test",
            raw_input=idl_file,
            title="Sistema de Lojas",
            skip_build=True,
            input_mode="idl",
        )

        # Verificar sucesso
        assert result.success is True, f"Pipeline falhou: {result.errors}"
        assert result.final_status == "artifacts_only"

        # Verificar que IR foi gerado
        assert result.ir_version is not None
        assert result.entities_count > 0

        # Verificar que OAS foi gerado
        assert result.oas_version is not None

        # Verificar que PLAN foi gerado
        assert result.plan_version is not None

        # Verificar runlog (está em runs/ subdir com timestamp)
        runs_path = Path(temp_store) / "lojas_test" / "runs"
        assert runs_path.exists(), "Runs directory não foi criado"
        runlog_files = list(runs_path.glob("*.json"))
        assert len(runlog_files) >= 1, "Nenhum runlog encontrado"
        runlog_wrapper = json.loads(runlog_files[0].read_text())
        runlog = runlog_wrapper.get("payload", runlog_wrapper)  # Handle wrapper
        assert runlog["schema_version"] == "runlog.v1"
        assert runlog.get("blocked_reason") is None

    def test_idl_inline_content(self, temp_store, temp_generated):
        """[E2E] IDL inline (não arquivo) também funciona."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="inline_test",
            raw_input=MINIMAL_IDL,  # Conteúdo inline
            title="Sistema Inline",
            skip_build=True,
            input_mode="idl",
        )

        assert result.success is True, f"Pipeline falhou: {result.errors}"
        assert result.entities_count > 0

    def test_idl_mode_not_ignored(self, temp_store, temp_generated, idl_file):
        """[E2E] --input-mode=idl não entra no fluxo de texto normalizado."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        # Patch idl_to_ir para verificar que foi chamado
        with patch("orchestrator.engine.idl_to_ir", wraps=idl_to_ir) as mock_idl_to_ir:
            result = engine.run_with_build(
                project="mode_check",
                raw_input=idl_file,
                title="Verificação de Modo",
                skip_build=True,
                input_mode="idl",
            )

            # idl_to_ir DEVE ter sido chamado
            assert mock_idl_to_ir.called, "idl_to_ir não foi chamado - input_mode foi ignorado!"
            assert result.success is True

    def test_idl_parse_error_classified(self, temp_store, temp_generated):
        """[E2E] Parse inválido retorna erro classificado."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="invalid_idl",
            raw_input=INVALID_IDL,
            skip_build=True,
            input_mode="idl",
        )

        # Deve falhar
        assert result.success is False

        # Erro deve estar classificado
        assert len(result.errors) > 0
        assert any("SCHEMA:" in e for e in result.errors), "Erro não tem prefixo SCHEMA:"

        # Error code deve estar presente
        assert result.error_codes is not None
        assert "IDL_PARSE_FAILED" in result.error_codes

    def test_idl_no_entities_error(self, temp_store, temp_generated):
        """[E2E] IDL sem entidades falha com erro classificado."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="no_entities",
            raw_input=IDL_NO_ENTITIES,
            skip_build=True,
            input_mode="idl",
        )

        # Deve falhar
        assert result.success is False

        # Erro deve indicar falta de entidades
        assert len(result.errors) > 0
        assert "IDL_TO_IR_INCOMPLETE" in (result.error_codes or [])

    def test_ir_has_correct_structure(self, temp_store, temp_generated, idl_file):
        """[E2E] IR gerado tem estrutura correta."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="ir_check",
            raw_input=idl_file,
            skip_build=True,
            input_mode="idl",
        )

        assert result.success is True

        # Carregar IR
        ir_path = Path(temp_store) / "ir_check" / "IR" / f"v{result.ir_version}.json"
        assert ir_path.exists(), f"IR não encontrado em {ir_path}"

        ir = json.loads(ir_path.read_text())

        # Verificar estrutura
        assert "meta" in ir
        assert "domain" in ir
        assert "api_intent" in ir

        # Verificar entidades
        entities = ir["domain"]["entities"]
        assert len(entities) >= 1
        store_entity = next((e for e in entities if e["name"] == "store"), None)
        assert store_entity is not None, "Entidade 'store' não encontrada no IR"

        # Verificar campos
        field_names = [f["name"] for f in store_entity["fields"]]
        assert "id" in field_names
        assert "name" in field_names
        assert "cnpj" in field_names

        # Verificar API resources
        resources = ir["api_intent"]["resources"]
        assert len(resources) >= 1

    def test_oas_generated_with_paths(self, temp_store, temp_generated, idl_file):
        """[E2E] OpenAPI é gerado com pelo menos 1 path."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="oas_check",
            raw_input=idl_file,
            skip_build=True,
            input_mode="idl",
        )

        assert result.success is True
        assert result.oas_version is not None

        # Carregar OAS (pode ser YAML ou JSON)
        import yaml
        oas_path = Path(temp_store) / "oas_check" / "OAS" / f"v{result.oas_version}.yaml"
        if not oas_path.exists():
            oas_path = Path(temp_store) / "oas_check" / "OAS" / f"v{result.oas_version}.json"

        assert oas_path.exists(), f"OAS não encontrado"

        oas_content = oas_path.read_text()
        if oas_path.suffix == ".yaml":
            oas = yaml.safe_load(oas_content)
        else:
            oas = json.loads(oas_content)

        # Verificar paths
        assert "paths" in oas
        assert len(oas["paths"]) >= 1, "OAS não tem nenhum path"


class TestIDLToIRConverter:
    """Testes unitários do conversor IDL → IR."""

    def test_idl_to_ir_basic(self):
        """[Unit] Conversão básica IDL → IR."""
        from idl.idl_v1 import IDLParser

        parser = IDLParser()
        doc = parser.parse(MINIMAL_IDL)

        ir = idl_to_ir(doc, "Test Project")

        assert "meta" in ir
        assert "domain" in ir
        assert ir["meta"]["source"] == "idl"

        entities = ir["domain"]["entities"]
        assert len(entities) == 1
        assert entities[0]["name"] == "store"

    def test_idl_to_ir_requires_entities(self):
        """[Unit] Conversão falha se não houver entidades."""
        from idl.idl_v1 import IDLParser

        parser = IDLParser()
        doc = parser.parse(IDL_NO_ENTITIES)

        with pytest.raises(IDLToIRError) as exc_info:
            idl_to_ir(doc, "Test")

        assert exc_info.value.error_code == "IDL_TO_IR_INCOMPLETE"

    def test_idl_to_ir_generates_crud(self):
        """[Unit] CRUD é gerado para entidades."""
        from idl.idl_v1 import IDLParser

        parser = IDLParser()
        doc = parser.parse(MINIMAL_IDL)

        ir = idl_to_ir(doc, "Test")

        # resources é lista de strings (nomes de entidades)
        resources = ir["api_intent"]["resources"]
        assert len(resources) >= 1
        assert "store" in resources

        # operations contém os métodos HTTP
        operations = ir["api_intent"]["operations"]
        methods = [op["method"] for op in operations]

        # Deve ter pelo menos GET/POST/PUT/DELETE
        assert "GET" in methods
        assert "POST" in methods

    def test_idl_to_ir_converts_actors_to_roles(self):
        """[Unit] Atores são convertidos para roles."""
        from idl.idl_v1 import IDLParser

        parser = IDLParser()
        doc = parser.parse(MINIMAL_IDL)

        ir = idl_to_ir(doc, "Test")

        assert "roles" in ir
        assert len(ir["roles"]) >= 1
        assert ir["roles"][0]["id"] == "admin"


class TestRunLogDuration:
    """Testes para verificar que duration_ms é persistido corretamente no runlog."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return str(store)

    @pytest.fixture
    def temp_generated(self, tmp_path):
        generated = tmp_path / "generated"
        generated.mkdir()
        return str(generated)

    def test_duration_ms_is_positive_in_runlog(self, temp_store, temp_generated):
        """[Regression] duration_ms no runlog persistido deve ser > 0."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        # Rodar um pipeline simples
        result = engine.run_with_build(
            project="duration_test",
            raw_input="Sistema de teste com entidade Produto",
            skip_build=True,
            input_mode="natural",
        )

        assert result.success is True, f"Pipeline falhou: {result.errors}"

        # Verificar runlog persistido
        runs_path = Path(temp_store) / "duration_test" / "runs"
        assert runs_path.exists(), "Runs directory não encontrado"

        runlog_files = list(runs_path.glob("*.json"))
        assert len(runlog_files) >= 1, "Nenhum runlog encontrado"

        runlog_wrapper = json.loads(runlog_files[0].read_text())
        runlog = runlog_wrapper.get("payload", runlog_wrapper)

        # Assertions críticas
        assert "duration_ms" in runlog, "duration_ms não presente no runlog"
        assert isinstance(runlog["duration_ms"], int), "duration_ms deve ser int"
        assert runlog["duration_ms"] > 0, f"duration_ms deve ser > 0, got {runlog['duration_ms']}"

        # Schema version não alterado
        assert runlog["schema_version"] == "runlog.v1"

    def test_duration_ms_consistent_with_result(self, temp_store, temp_generated):
        """[Regression] duration_ms no runlog deve ser consistente com result.duration_ms."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="duration_consistency",
            raw_input="Sistema de cadastro de clientes com nome, email e telefone",
            skip_build=True,
            input_mode="natural",
        )

        assert result.success is True

        # Verificar que o result também tem duration_ms > 0
        assert result.duration_ms > 0, f"result.duration_ms deve ser > 0, got {result.duration_ms}"

        # Verificar runlog
        runs_path = Path(temp_store) / "duration_consistency" / "runs"
        runlog_files = list(runs_path.glob("*.json"))
        runlog_wrapper = json.loads(runlog_files[0].read_text())
        runlog = runlog_wrapper.get("payload", runlog_wrapper)

        # Ambos devem ser positivos (não precisam ser exatamente iguais
        # porque são calculados em momentos diferentes)
        assert runlog["duration_ms"] > 0
        assert result.duration_ms > 0

        # Devem estar na mesma ordem de grandeza (diferença < 1 segundo para testes rápidos)
        diff = abs(result.duration_ms - runlog["duration_ms"])
        assert diff < 1000, f"Diferença muito grande: {diff}ms"


class TestNaturalModeUnaffected:
    """Testes para garantir que o modo natural não foi quebrado."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return str(store)

    @pytest.fixture
    def temp_generated(self, tmp_path):
        generated = tmp_path / "generated"
        generated.mkdir()
        return str(generated)

    def test_natural_mode_still_works(self, temp_store, temp_generated):
        """[Regression] Modo natural continua funcionando."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="natural_test",
            raw_input="Sistema de cadastro de clientes com nome, email e telefone",
            skip_build=True,
            input_mode="natural",
        )

        assert result.success is True, f"Modo natural quebrou: {result.errors}"
        assert result.entities_count > 0

    def test_auto_mode_with_text(self, temp_store, temp_generated):
        """[Regression] Modo auto com texto livre funciona."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="auto_test",
            raw_input="Quero um sistema de pedidos com cliente e produto",
            skip_build=True,
            input_mode="auto",
        )

        assert result.success is True, f"Modo auto quebrou: {result.errors}"


class TestIDLInputDiagnostics:
    """Testes para diagnóstico melhorado de erros de input IDL."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return str(store)

    @pytest.fixture
    def temp_generated(self, tmp_path):
        generated = tmp_path / "generated"
        generated.mkdir()
        return str(generated)

    def test_file_not_found_returns_classified_error(self, temp_store, temp_generated):
        """[A] input_mode=idl com caminho inexistente -> IDL_INPUT_FILE_NOT_FOUND."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        # Caminho que não existe
        nonexistent_path = "/tmp/this/path/does/not/exist/spec.idl"

        result = engine.run_with_build(
            project="file_not_found_test",
            raw_input=nonexistent_path,
            skip_build=True,
            input_mode="idl",
        )

        # Deve falhar
        assert result.success is False

        # Erro classificado correto
        assert "IDL_INPUT_FILE_NOT_FOUND" in result.error_codes, \
            f"Expected IDL_INPUT_FILE_NOT_FOUND, got {result.error_codes}"

        # Mensagem de erro contém o path
        assert len(result.errors) > 0
        assert nonexistent_path in result.errors[0], \
            f"Error message should contain path: {result.errors[0]}"
        assert "SCHEMA:" in result.errors[0], \
            f"Error should have SCHEMA: prefix: {result.errors[0]}"

    def test_parse_error_includes_first_chars(self, temp_store, temp_generated, tmp_path):
        """[B] Arquivo com conteúdo inválido inclui first_chars no erro."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        # Criar arquivo com conteúdo inválido começando com '@'
        invalid_file = tmp_path / "invalid.idl"
        invalid_content = "@version(\"1.0.0\")\n@invalid syntax here"
        invalid_file.write_text(invalid_content)

        result = engine.run_with_build(
            project="parse_error_test",
            raw_input=str(invalid_file),
            skip_build=True,
            input_mode="idl",
        )

        # Deve falhar com parse error
        assert result.success is False
        assert "IDL_PARSE_FAILED" in result.error_codes

        # Erro deve conter first_chars para diagnóstico
        assert len(result.errors) > 0
        error_msg = result.errors[0]
        assert "first_chars=" in error_msg, \
            f"Error should contain first_chars snippet: {error_msg}"
        assert "@version" in error_msg or "'@" in error_msg, \
            f"first_chars should show the @ character: {error_msg}"

    def test_valid_file_still_works(self, temp_store, temp_generated, tmp_path):
        """[C] Arquivo IDL válido continua funcionando após mudanças."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        # Criar arquivo IDL válido
        valid_file = tmp_path / "valid.idl"
        valid_file.write_text(MINIMAL_IDL)

        result = engine.run_with_build(
            project="valid_file_test",
            raw_input=str(valid_file),
            skip_build=True,
            input_mode="idl",
        )

        # Deve funcionar
        assert result.success is True, f"Valid IDL file failed: {result.errors}"
        assert result.entities_count >= 1

    def test_inline_content_still_works(self, temp_store, temp_generated):
        """[C] Conteúdo IDL inline continua funcionando."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        result = engine.run_with_build(
            project="inline_test",
            raw_input=MINIMAL_IDL,
            skip_build=True,
            input_mode="idl",
        )

        # Deve funcionar
        assert result.success is True, f"Inline IDL failed: {result.errors}"
        assert result.entities_count >= 1

    def test_path_detection_with_slash(self, temp_store, temp_generated):
        """Caminho com / é detectado como path, não inline."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        # Isso parece um path (contém /)
        fake_path = "some/path/to/file.idl"

        result = engine.run_with_build(
            project="slash_path_test",
            raw_input=fake_path,
            skip_build=True,
            input_mode="idl",
        )

        # Deve falhar com file not found, não parse error
        assert result.success is False
        assert "IDL_INPUT_FILE_NOT_FOUND" in result.error_codes, \
            f"Path with / should be detected as file: {result.error_codes}"

    def test_path_detection_with_idl_extension(self, temp_store, temp_generated):
        """Caminho terminando em .idl é detectado como path."""
        engine = Engine(
            store_root=temp_store,
            generated_root=temp_generated,
        )

        # Isso parece um path (termina em .idl)
        fake_path = "myspec.idl"

        result = engine.run_with_build(
            project="idl_ext_test",
            raw_input=fake_path,
            skip_build=True,
            input_mode="idl",
        )

        # Deve falhar com file not found
        assert result.success is False
        assert "IDL_INPUT_FILE_NOT_FOUND" in result.error_codes, \
            f".idl extension should be detected as file: {result.error_codes}"
