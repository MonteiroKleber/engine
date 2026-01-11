"""Testes para o Engine Build Loop (Dia 6)."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.engine import Engine, RunResult


# ==================== FIXTURES ====================


@pytest.fixture
def temp_dirs():
    """Cria diretórios temporários para testes."""
    temp_dir = tempfile.mkdtemp()
    store_dir = Path(temp_dir) / "store"
    generated_dir = Path(temp_dir) / "generated"
    templates_dir = Path(temp_dir) / "templates"

    store_dir.mkdir()
    generated_dir.mkdir()
    templates_dir.mkdir()

    yield store_dir, generated_dir, templates_dir, temp_dir

    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_input():
    """Input de exemplo para testes."""
    return """
    Sistema de Gestão de Produtos

    Requisitos:
    - Cadastrar produtos com nome e preço
    - Listar todos os produtos
    - Atualizar produto existente
    - Remover produto
    """


# ==================== RUN RESULT TESTS ====================


class TestRunResultBuildFields:
    """Testes dos campos de build no RunResult."""

    def test_run_result_has_repo_path(self):
        """RunResult deve ter campo repo_path."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="demo",
            repo_path="/home/bazari/generated/demo",
        )

        assert result.repo_path == "/home/bazari/generated/demo"

    def test_run_result_has_patch_count(self):
        """RunResult deve ter campo patch_count."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="demo",
            patch_count=32,
        )

        assert result.patch_count == 32

    def test_run_result_has_build_ok(self):
        """RunResult deve ter campo build_ok."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="demo",
            build_ok=True,
        )

        assert result.build_ok is True

    def test_run_result_has_build_errors(self):
        """RunResult deve ter campo build_errors."""
        result = RunResult(
            success=False,
            execution_id="test",
            project="demo",
            build_errors=["Error 1", "Error 2"],
        )

        assert len(result.build_errors) == 2

    def test_to_dict_includes_build_fields(self):
        """to_dict deve incluir campos de build."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="demo",
            repo_path="/path/to/repo",
            patch_count=10,
            build_ok=True,
            build_errors=[],
        )

        d = result.to_dict()

        assert "repo_path" in d
        assert "patch_count" in d
        assert "build_ok" in d
        assert "build_errors" in d

    def test_summary_includes_patches(self):
        """summary deve incluir contagem de patches."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="demo",
            patch_count=32,
            build_ok=True,
        )

        summary = result.summary()

        assert "Patches: 32" in summary

    def test_summary_includes_build_status(self):
        """summary deve incluir status do build."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="demo",
            repo_path="/path",
            build_ok=True,
        )

        summary = result.summary()

        assert "Build: OK" in summary

    def test_summary_build_failed(self):
        """summary deve mostrar FAILED quando build falha."""
        result = RunResult(
            success=False,
            execution_id="test",
            project="demo",
            repo_path="/path",
            build_ok=False,
        )

        summary = result.summary()

        assert "Build: FAILED" in summary

    def test_summary_build_skipped(self):
        """summary deve mostrar SKIPPED quando não há repo."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="demo",
            repo_path=None,
            build_ok=False,
        )

        summary = result.summary()

        assert "Build: SKIPPED" in summary


# ==================== ENGINE CONFIGURATION TESTS ====================


class TestEngineConfiguration:
    """Testes de configuração do Engine."""

    def test_engine_has_generated_root(self):
        """Engine deve ter GENERATED_ROOT configurado."""
        engine = Engine()
        assert engine.GENERATED_ROOT == "/home/bazari/generated"

    def test_engine_has_templates_root(self):
        """Engine deve ter TEMPLATES_ROOT configurado."""
        engine = Engine()
        assert engine.TEMPLATES_ROOT == "/home/bazari/templates"


# ==================== RUN WITH BUILD TESTS (MOCKED) ====================


class TestRunWithBuildMocked:
    """Testes do run_with_build com mocks."""

    def test_skip_build_returns_after_artifacts(self, temp_dirs):
        """skip_build=True deve retornar após gerar artefatos."""
        store_dir, generated_dir, templates_dir, _ = temp_dirs

        engine = Engine(str(store_dir))

        # Mock run() para retornar sucesso
        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="demo",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            result = engine.run_with_build("demo", "input", skip_build=True)

            assert result.success
            assert result.repo_path is None
            assert result.patch_count == 0

    def test_run_with_build_fails_if_run_fails(self, temp_dirs):
        """run_with_build deve falhar se run() falhar."""
        store_dir, _, _, _ = temp_dirs

        engine = Engine(str(store_dir))

        # Mock run() para retornar falha
        mock_result = RunResult(
            success=False,
            execution_id="test_123",
            project="demo",
            errors=["SRS validation failed"],
        )

        with patch.object(engine, 'run', return_value=mock_result):
            result = engine.run_with_build("demo", "input")

            assert not result.success
            assert result.build_ok is False


# ==================== INTEGRATION TESTS ====================


class TestEngineIntegration:
    """Testes de integração do Engine."""

    def test_run_with_build_skip_generates_artifacts(self):
        """run_with_build com skip_build deve gerar artefatos."""
        # Este teste requer a infraestrutura completa
        # Pulamos se templates não existirem
        templates_path = Path("/home/bazari/templates")
        if not templates_path.exists():
            pytest.skip("Templates not available")

        # Usar store temporário
        temp_store = tempfile.mkdtemp()

        try:
            engine = Engine(temp_store)

            input_text = """
            Sistema de Teste

            Requisitos:
            - Cadastrar item com nome
            - Listar itens
            """

            # Executar com skip_build para testar apenas artefatos
            result = engine.run_with_build(
                "test_artifacts_only",
                input_text,
                "Sistema de Teste",
                skip_build=True,
            )

            # Verificar resultado
            assert result.success
            assert result.plan_version is not None
            assert result.tasks_count > 0
            assert result.entities_count > 0

        finally:
            shutil.rmtree(temp_store)

    def test_run_with_build_applies_patches(self):
        """run_with_build deve aplicar patches (mesmo que build falhe)."""
        templates_path = Path("/home/bazari/templates")
        if not templates_path.exists():
            pytest.skip("Templates not available")

        temp_store = tempfile.mkdtemp()

        try:
            engine = Engine(temp_store)

            input_text = """
            Sistema de Teste

            Requisitos:
            - Cadastrar produto com nome
            - Listar produtos
            """

            # Executar com build (pode falhar por erros de TypeScript)
            result = engine.run_with_build(
                "test_patches_apply",
                input_text,
                "Sistema de Teste",
            )

            # Verificar que patches foram gerados
            assert result.patch_count > 0

            # Repo pode ter sido criado (mesmo que build tenha falhado)
            # Se build falhou, repo foi removido pelo rollback

        finally:
            shutil.rmtree(temp_store)
            # Limpar repo gerado (se existir)
            test_repo = Path("/home/bazari/generated/test_patches_apply")
            if test_repo.exists():
                shutil.rmtree(test_repo)

    def test_run_log_includes_build_fields(self):
        """run log deve incluir campos de build."""
        templates_path = Path("/home/bazari/templates")
        if not templates_path.exists():
            pytest.skip("Templates not available")

        temp_store = tempfile.mkdtemp()

        try:
            engine = Engine(temp_store)

            input_text = """
            Sistema Simples

            Requisitos:
            - CRUD de entidade
            """

            result = engine.run_with_build(
                "test_run_log",
                input_text,
                skip_build=True,  # Pular build para teste rápido
            )

            # Verificar que run log foi escrito
            import json
            runs_dir = Path(temp_store) / "test_run_log" / "runs"
            if runs_dir.exists():
                run_files = list(runs_dir.glob("*.json"))
                if run_files:
                    with open(run_files[0], "r") as f:
                        run_log = json.load(f)

                    # Verificar campos no payload
                    assert "payload" in run_log
                    payload = run_log["payload"]
                    assert "result" in payload
                    assert "build_ok" in payload

        finally:
            shutil.rmtree(temp_store)


# ==================== ROLLBACK TESTS ====================


class TestBuildRollback:
    """Testes de rollback quando build falha."""

    def test_rollback_removes_repo_on_build_failure(self, temp_dirs):
        """Rollback deve remover repo quando build falha."""
        store_dir, generated_dir, templates_dir, _ = temp_dirs

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        # Criar estrutura de templates mock
        (templates_dir / "spring-boot").mkdir()
        (templates_dir / "spring-boot" / "pom.xml").write_text("<project/>")
        (templates_dir / "react-vite").mkdir()
        (templates_dir / "react-vite" / "package.json").write_text('{"name": "app"}')
        (templates_dir / "postgres-flyway").mkdir()
        (templates_dir / "postgres-flyway" / "flyway.conf").write_text("url=")
        (templates_dir / "docker").mkdir()
        (templates_dir / "docker" / "docker-compose.yml").write_text("version: '3'")

        # Mock run() para retornar sucesso com artefatos
        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="rollback_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        # Mock dos artefatos e build failure
        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.BuildValidator') as mock_build:
                        # Simular build failure
                        mock_report = MagicMock()
                        mock_report.ok = False
                        mock_report.errors = ["Build failed"]
                        mock_build.return_value.validate.return_value = mock_report

                        result = engine.run_with_build("rollback_test", "input")

                        assert not result.success
                        assert not result.build_ok
                        # Repo deve ter sido removido
                        assert not (generated_dir / "rollback_test").exists()
