"""Testes para o Build Validator."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from validators.build_validator import (
    BuildComponent,
    BuildReport,
    BuildResult,
    BuildValidator,
    validate_build,
)


@pytest.fixture
def temp_generated():
    """Cria um diretório temporário simulando generated/."""
    temp_dir = tempfile.mkdtemp()
    generated_dir = Path(temp_dir) / "generated"
    generated_dir.mkdir()
    yield generated_dir, temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_project(temp_generated):
    """Cria um projeto mock com estrutura básica."""
    generated_dir, _ = temp_generated
    project_dir = generated_dir / "test_project"
    project_dir.mkdir()

    # Backend
    backend_dir = project_dir / "backend"
    backend_dir.mkdir()
    (backend_dir / "pom.xml").write_text("<project/>")

    # Frontend
    frontend_dir = project_dir / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text('{"name": "app"}')

    return project_dir, generated_dir


# ==================== BUILD RESULT TESTS ====================


class TestBuildResult:
    """Testes do BuildResult."""

    def test_build_result_to_dict(self):
        """BuildResult.to_dict deve funcionar."""
        result = BuildResult(
            component="backend",
            success=True,
            command="mvn test",
            exit_code=0,
            stdout="Build successful",
            stderr="",
            duration_seconds=10.5,
        )

        d = result.to_dict()

        assert d["component"] == "backend"
        assert d["success"] is True
        assert d["command"] == "mvn test"
        assert d["exit_code"] == 0
        assert d["duration_seconds"] == 10.5

    def test_build_result_truncates_long_output(self):
        """BuildResult deve truncar outputs longos."""
        long_output = "x" * 2000
        result = BuildResult(
            component="test",
            success=True,
            command="test",
            stdout=long_output,
            stderr=long_output,
        )

        d = result.to_dict()

        assert len(d["stdout"]) == 1000
        assert len(d["stderr"]) == 1000


class TestBuildReport:
    """Testes do BuildReport."""

    def test_build_report_to_dict(self):
        """BuildReport.to_dict deve funcionar."""
        report = BuildReport(
            ok=True,
            project="test_project",
            results=[
                BuildResult(
                    component="backend",
                    success=True,
                    command="mvn test",
                )
            ],
            errors=[],
        )

        d = report.to_dict()

        assert d["ok"] is True
        assert d["project"] == "test_project"
        assert len(d["results"]) == 1
        assert d["errors"] == []


# ==================== VALIDATOR INITIALIZATION TESTS ====================


class TestBuildValidatorInit:
    """Testes de inicialização do BuildValidator."""

    def test_default_initialization(self):
        """BuildValidator deve inicializar com valores padrão."""
        validator = BuildValidator()

        assert validator.generated_root == Path("/home/bazari/generated")
        assert validator.timeout == BuildValidator.DEFAULT_TIMEOUT

    def test_custom_initialization(self, temp_generated):
        """BuildValidator deve aceitar valores customizados."""
        generated_dir, _ = temp_generated

        validator = BuildValidator(
            generated_root=str(generated_dir),
            timeout=60,
        )

        assert validator.generated_root == generated_dir
        assert validator.timeout == 60


# ==================== PROJECT NOT FOUND TESTS ====================


class TestProjectNotFound:
    """Testes quando projeto não existe."""

    def test_validate_nonexistent_project(self, temp_generated):
        """Validar projeto inexistente deve falhar."""
        generated_dir, _ = temp_generated
        validator = BuildValidator(str(generated_dir))

        report = validator.validate("nonexistent")

        assert not report.ok
        assert "not found" in report.errors[0].lower()

    def test_validate_backend_missing_dir(self, temp_generated):
        """Validar backend sem diretório deve falhar."""
        generated_dir, _ = temp_generated
        project_dir = generated_dir / "no_backend"
        project_dir.mkdir()

        validator = BuildValidator(str(generated_dir))
        report = validator.validate_backend_only("no_backend")

        assert not report.ok
        assert len(report.results) == 1
        assert not report.results[0].success
        assert "not found" in report.results[0].stderr.lower()

    def test_validate_frontend_missing_dir(self, temp_generated):
        """Validar frontend sem diretório deve falhar."""
        generated_dir, _ = temp_generated
        project_dir = generated_dir / "no_frontend"
        project_dir.mkdir()

        validator = BuildValidator(str(generated_dir))
        report = validator.validate_frontend_only("no_frontend")

        assert not report.ok
        assert len(report.results) == 1
        assert not report.results[0].success
        assert "not found" in report.results[0].stderr.lower()


# ==================== MISSING FILES TESTS ====================


class TestMissingFiles:
    """Testes quando arquivos de configuração estão faltando."""

    def test_backend_missing_pom(self, temp_generated):
        """Backend sem pom.xml deve falhar."""
        generated_dir, _ = temp_generated
        project_dir = generated_dir / "no_pom"
        project_dir.mkdir()
        (project_dir / "backend").mkdir()

        validator = BuildValidator(str(generated_dir))
        report = validator.validate_backend_only("no_pom")

        assert not report.ok
        assert "pom.xml" in report.results[0].stderr

    def test_frontend_missing_package_json(self, temp_generated):
        """Frontend sem package.json deve falhar."""
        generated_dir, _ = temp_generated
        project_dir = generated_dir / "no_package"
        project_dir.mkdir()
        (project_dir / "frontend").mkdir()

        validator = BuildValidator(str(generated_dir))
        report = validator.validate_frontend_only("no_package")

        assert not report.ok
        assert "package.json" in report.results[0].stderr


# ==================== COMMAND EXECUTION TESTS (MOCKED) ====================


class TestCommandExecution:
    """Testes de execução de comandos (mockados)."""

    def test_backend_build_success(self, mock_project):
        """Backend build com sucesso deve retornar ok."""
        project_dir, generated_dir = mock_project

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="BUILD SUCCESS",
                stderr="",
            )

            validator = BuildValidator(str(generated_dir))
            report = validator.validate_backend_only("test_project")

            assert report.ok
            assert report.results[0].success
            assert report.results[0].component == "backend"
            mock_run.assert_called_once()

    def test_backend_build_failure(self, mock_project):
        """Backend build com falha deve retornar erro."""
        project_dir, generated_dir = mock_project

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Compilation failure",
            )

            validator = BuildValidator(str(generated_dir))
            report = validator.validate_backend_only("test_project")

            assert not report.ok
            assert not report.results[0].success
            assert "Compilation failure" in report.results[0].stderr

    def test_frontend_build_success(self, mock_project):
        """Frontend build com sucesso deve retornar ok."""
        project_dir, generated_dir = mock_project

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Done",
                stderr="",
            )

            validator = BuildValidator(str(generated_dir))
            report = validator.validate_frontend_only("test_project")

            assert report.ok
            assert len(report.results) == 2  # npm ci + npm run build
            assert report.results[0].component == "frontend:install"
            assert report.results[1].component == "frontend:build"
            assert mock_run.call_count == 2

    def test_frontend_npm_ci_failure_skips_build(self, mock_project):
        """Se npm ci falhar, npm run build não deve executar."""
        project_dir, generated_dir = mock_project

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="npm ERR!",
            )

            validator = BuildValidator(str(generated_dir))
            report = validator.validate_frontend_only("test_project")

            assert not report.ok
            assert len(report.results) == 1  # Apenas npm ci
            assert not report.results[0].success
            mock_run.assert_called_once()

    def test_validate_all_components(self, mock_project):
        """Validar todos os componentes deve executar backend e frontend."""
        project_dir, generated_dir = mock_project

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Success",
                stderr="",
            )

            validator = BuildValidator(str(generated_dir))
            report = validator.validate("test_project", BuildComponent.ALL)

            assert report.ok
            assert len(report.results) == 3  # backend + npm ci + npm run build
            # backend, frontend:install, frontend:build
            components = [r.component for r in report.results]
            assert "backend" in components
            assert "frontend:install" in components
            assert "frontend:build" in components


# ==================== TIMEOUT TESTS ====================


class TestTimeout:
    """Testes de timeout."""

    def test_command_timeout(self, mock_project):
        """Comando que excede timeout deve falhar."""
        project_dir, generated_dir = mock_project

        with patch("subprocess.run") as mock_run:
            import subprocess

            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["mvn", "test"],
                timeout=300,
            )

            validator = BuildValidator(str(generated_dir))
            report = validator.validate_backend_only("test_project")

            assert not report.ok
            assert "timed out" in report.results[0].stderr.lower()

    def test_command_not_found(self, mock_project):
        """Comando não encontrado deve falhar graciosamente."""
        project_dir, generated_dir = mock_project

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("mvn not found")

            validator = BuildValidator(str(generated_dir))
            report = validator.validate_backend_only("test_project")

            assert not report.ok
            assert "not found" in report.results[0].stderr.lower()


# ==================== CONVENIENCE FUNCTION TESTS ====================


class TestConvenienceFunction:
    """Testes da função de conveniência."""

    def test_validate_build_function(self, mock_project):
        """Função validate_build deve funcionar."""
        project_dir, generated_dir = mock_project

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Success",
                stderr="",
            )

            report = validate_build(
                "test_project",
                generated_root=str(generated_dir),
                components=BuildComponent.BACKEND,
            )

            assert report.ok
            assert report.project == "test_project"


# ==================== BUILD COMPONENT ENUM TESTS ====================


class TestBuildComponent:
    """Testes do enum BuildComponent."""

    def test_component_values(self):
        """Verificar valores do enum."""
        assert BuildComponent.BACKEND.value == "backend"
        assert BuildComponent.FRONTEND.value == "frontend"
        assert BuildComponent.ALL.value == "all"


# ==================== INTEGRATION TESTS (SKIPPABLE) ====================


class TestIntegrationWithRealBuilds:
    """Testes de integração com builds reais.

    Estes testes requerem mvn e npm instalados.
    """

    @pytest.fixture
    def real_project(self, temp_generated):
        """Cria projeto com arquivos reais do template."""
        generated_dir, _ = temp_generated

        # Copiar templates reais se existirem
        templates_path = Path("/home/bazari/templates")
        if not templates_path.exists():
            pytest.skip("Templates not available")

        from repo import RepoGenerator

        generator = RepoGenerator(
            templates_root=str(templates_path),
            output_root=str(generated_dir),
        )
        project_dir = generator.create_repo("integration_test")

        return project_dir, generated_dir

    def test_real_backend_build(self, real_project):
        """Testar build real do backend com Maven."""
        project_dir, generated_dir = real_project

        # Verificar se Maven está disponível
        import shutil as sh

        if not sh.which("mvn"):
            pytest.skip("Maven not installed")

        validator = BuildValidator(str(generated_dir))
        report = validator.validate_backend_only("integration_test")

        # Template puro deve passar no build
        assert report.ok, f"Backend build failed: {report.errors}"

    def test_real_frontend_build(self, real_project):
        """Testar build real do frontend com npm."""
        project_dir, generated_dir = real_project

        # Verificar se npm está disponível
        import shutil as sh

        if not sh.which("npm"):
            pytest.skip("npm not installed")

        validator = BuildValidator(str(generated_dir))
        report = validator.validate_frontend_only("integration_test")

        # Template puro deve passar no build
        assert report.ok, f"Frontend build failed: {report.errors}"


# ==================== ERROR HANDLING TESTS ====================


class TestErrorHandling:
    """Testes de tratamento de erros."""

    def test_generic_exception_handling(self, mock_project):
        """Exceção genérica deve ser tratada graciosamente."""
        project_dir, generated_dir = mock_project

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            validator = BuildValidator(str(generated_dir))
            report = validator.validate_backend_only("test_project")

            assert not report.ok
            assert "error" in report.results[0].stderr.lower()

    def test_partial_success_reports_correctly(self, mock_project):
        """Sucesso parcial deve ser reportado corretamente."""
        project_dir, generated_dir = mock_project

        call_count = [0]

        def mock_run_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # Backend sucesso
                return MagicMock(returncode=0, stdout="OK", stderr="")
            elif call_count[0] == 2:  # npm ci sucesso
                return MagicMock(returncode=0, stdout="OK", stderr="")
            else:  # npm build falha
                return MagicMock(returncode=1, stdout="", stderr="Build error")

        with patch("subprocess.run", side_effect=mock_run_side_effect):
            validator = BuildValidator(str(generated_dir))
            report = validator.validate("test_project", BuildComponent.ALL)

            assert not report.ok  # Falhou no geral
            assert report.results[0].success  # Backend ok
            assert report.results[1].success  # npm ci ok
            assert not report.results[2].success  # npm build falhou
