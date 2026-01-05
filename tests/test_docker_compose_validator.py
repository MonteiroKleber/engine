"""Testes para o Docker Compose Validator.

Verifica:
- Validacao de docker-compose.yml
- Servicos obrigatorios: postgres, backend, frontend
- Criacao de template quando faltando
- docker compose up funciona

Aceite:
- `docker compose up -d` sobe os 3 servicos sem erro.
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from release.docker_compose_validator import (
    DockerComposeValidator,
    DockerComposeValidationResult,
    DockerComposeUpResult,
    validate_docker_compose,
    ensure_docker_compose,
)


# ==================== FIXTURES ====================


@pytest.fixture
def validator(tmp_path):
    """Validator com paths temporarios."""
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir(exist_ok=True)
    return DockerComposeValidator(generated_root=str(generated_dir))


@pytest.fixture
def valid_compose_project(tmp_path):
    """Projeto com docker-compose.yml valido."""
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    project = generated / "valid_project"
    project.mkdir(exist_ok=True)

    compose_content = """
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"

  backend:
    build: ./backend
    ports:
      - "8080:8080"
    depends_on:
      - postgres

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend

volumes:
  postgres_data:
"""

    (project / "docker-compose.yml").write_text(compose_content)
    (project / "backend").mkdir(exist_ok=True)
    (project / "frontend").mkdir(exist_ok=True)
    (project / "backend" / "Dockerfile").write_text("FROM scratch\n")
    (project / "frontend" / "Dockerfile").write_text("FROM scratch\n")

    return project


@pytest.fixture
def missing_services_project(tmp_path):
    """Projeto com docker-compose.yml faltando servicos."""
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    project = generated / "missing_services"
    project.mkdir(exist_ok=True)

    compose_content = """
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
"""

    (project / "docker-compose.yml").write_text(compose_content)

    return project


@pytest.fixture
def no_compose_project(tmp_path):
    """Projeto sem docker-compose.yml."""
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    project = generated / "no_compose"
    project.mkdir(exist_ok=True)

    return project


@pytest.fixture
def invalid_yaml_project(tmp_path):
    """Projeto com docker-compose.yml invalido."""
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    project = generated / "invalid_yaml"
    project.mkdir(exist_ok=True)

    (project / "docker-compose.yml").write_text("invalid: yaml: content: [[[")

    return project


# ==================== TESTS: VALIDATION RESULT ====================


class TestDockerComposeValidationResult:
    """Testes do DockerComposeValidationResult."""

    def test_to_dict(self):
        """to_dict deve converter corretamente."""
        result = DockerComposeValidationResult(
            valid=True,
            file_exists=True,
            file_path="/path/to/compose.yml",
            services_found=["postgres", "backend", "frontend"],
            missing_services=[],
            errors=[],
            warnings=["Minor warning"],
        )

        d = result.to_dict()

        assert d["valid"] is True
        assert d["file_exists"] is True
        assert d["file_path"] == "/path/to/compose.yml"
        assert len(d["services_found"]) == 3
        assert len(d["warnings"]) == 1

    def test_default_values(self):
        """Valores default devem funcionar."""
        result = DockerComposeValidationResult(
            valid=False,
            file_exists=False,
        )

        assert result.services_found == []
        assert result.missing_services == []
        assert result.errors == []
        assert result.warnings == []


# ==================== TESTS: UP RESULT ====================


class TestDockerComposeUpResult:
    """Testes do DockerComposeUpResult."""

    def test_to_dict(self):
        """to_dict deve converter corretamente."""
        result = DockerComposeUpResult(
            success=True,
            services_started=["postgres", "backend", "frontend"],
            exit_code=0,
            stdout="Started",
            stderr="",
            duration_ms=5000.0,
        )

        d = result.to_dict()

        assert d["success"] is True
        assert len(d["services_started"]) == 3
        assert d["exit_code"] == 0

    def test_truncates_long_output(self):
        """Deve truncar output muito longo."""
        long_output = "x" * 2000
        result = DockerComposeUpResult(
            success=True,
            stdout=long_output,
            stderr=long_output,
        )

        d = result.to_dict()

        assert len(d["stdout"]) == 1000
        assert len(d["stderr"]) == 1000


# ==================== TESTS: VALIDATOR BASIC ====================


class TestValidatorBasic:
    """Testes basicos do DockerComposeValidator."""

    def test_default_values(self):
        """Validator deve usar valores padrao."""
        validator = DockerComposeValidator()

        assert validator.generated_root == Path(DockerComposeValidator.DEFAULT_GENERATED_ROOT)
        assert validator.required_services == DockerComposeValidator.REQUIRED_SERVICES

    def test_custom_values(self, tmp_path):
        """Validator deve aceitar valores customizados."""
        validator = DockerComposeValidator(
            generated_root=str(tmp_path),
            required_services=["db", "api"],
        )

        assert validator.generated_root == tmp_path
        assert validator.required_services == ["db", "api"]


# ==================== TESTS: VALIDATE ====================


class TestValidate:
    """Testes do metodo validate."""

    def test_valid_compose(self, validator, valid_compose_project):
        """Deve validar compose correto."""
        validator.generated_root = valid_compose_project.parent

        result = validator.validate("valid_project")

        assert result.valid is True
        assert result.file_exists is True
        assert "postgres" in result.services_found
        assert "backend" in result.services_found
        assert "frontend" in result.services_found
        assert len(result.missing_services) == 0

    def test_missing_file(self, validator, no_compose_project):
        """Deve falhar quando arquivo nao existe."""
        validator.generated_root = no_compose_project.parent

        result = validator.validate("no_compose")

        assert result.valid is False
        assert result.file_exists is False
        assert "not found" in result.errors[0].lower()

    def test_missing_services(self, validator, missing_services_project):
        """Deve detectar servicos faltando."""
        validator.generated_root = missing_services_project.parent

        result = validator.validate("missing_services")

        assert result.valid is False
        assert result.file_exists is True
        assert "backend" in result.missing_services
        assert "frontend" in result.missing_services

    def test_invalid_yaml(self, validator, invalid_yaml_project):
        """Deve detectar YAML invalido."""
        validator.generated_root = invalid_yaml_project.parent

        result = validator.validate("invalid_yaml")

        assert result.valid is False
        assert result.file_exists is True
        assert any("yaml" in e.lower() for e in result.errors)

    def test_empty_compose(self, tmp_path):
        """Deve detectar compose vazio."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "empty"
        project.mkdir(exist_ok=True)
        (project / "docker-compose.yml").write_text("")

        validator = DockerComposeValidator(generated_root=str(generated))
        result = validator.validate("empty")

        assert result.valid is False
        assert "empty" in result.errors[0].lower()

    def test_no_services(self, tmp_path):
        """Deve detectar compose sem servicos."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "no_services"
        project.mkdir(exist_ok=True)
        (project / "docker-compose.yml").write_text("version: '3.8'\n")

        validator = DockerComposeValidator(generated_root=str(generated))
        result = validator.validate("no_services")

        assert result.valid is False
        assert any("no services" in e.lower() for e in result.errors)


# ==================== TESTS: SERVICE ALIASES ====================


class TestServiceAliases:
    """Testes de aliases de servicos."""

    def test_postgres_alias_db(self, tmp_path):
        """Deve aceitar 'db' como alias de postgres."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "alias_test"
        project.mkdir(exist_ok=True)

        compose_content = """
version: '3.8'
services:
  db:
    image: postgres:15
    ports:
      - "5432:5432"
  backend:
    build: ./backend
    ports:
      - "8080:8080"
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
"""
        (project / "docker-compose.yml").write_text(compose_content)

        validator = DockerComposeValidator(generated_root=str(generated))
        result = validator.validate("alias_test")

        # Deve ter warning sobre alias, mas nao estar em missing
        assert "postgres" not in result.missing_services
        assert any("db" in w for w in result.warnings)

    def test_backend_alias_api(self, tmp_path):
        """Deve aceitar 'api' como alias de backend."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "api_alias"
        project.mkdir(exist_ok=True)

        compose_content = """
version: '3.8'
services:
  postgres:
    image: postgres:15
  api:
    build: ./backend
    ports:
      - "8080:8080"
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
"""
        (project / "docker-compose.yml").write_text(compose_content)

        validator = DockerComposeValidator(generated_root=str(generated))
        result = validator.validate("api_alias")

        assert "backend" not in result.missing_services


# ==================== TESTS: ENSURE VALID ====================


class TestEnsureValid:
    """Testes do metodo ensure_valid."""

    def test_already_valid(self, validator, valid_compose_project):
        """Deve retornar True para compose ja valido."""
        validator.generated_root = valid_compose_project.parent

        success, result = validator.ensure_valid("valid_project")

        assert success is True
        assert result.valid is True

    def test_creates_missing_file(self, validator, no_compose_project):
        """Deve criar arquivo quando faltando."""
        validator.generated_root = no_compose_project.parent

        # Criar estrutura backend/frontend
        (no_compose_project / "backend").mkdir(exist_ok=True)
        (no_compose_project / "frontend").mkdir(exist_ok=True)

        success, result = validator.ensure_valid("no_compose")

        assert success is True
        assert (no_compose_project / "docker-compose.yml").exists()

    def test_adds_missing_services(self, validator, missing_services_project):
        """Deve adicionar servicos faltando."""
        validator.generated_root = missing_services_project.parent

        success, result = validator.ensure_valid("missing_services")

        assert success is True

        # Verificar que servicos foram adicionados
        with open(missing_services_project / "docker-compose.yml") as f:
            compose_data = yaml.safe_load(f)

        assert "backend" in compose_data["services"]
        assert "frontend" in compose_data["services"]


# ==================== TESTS: DOCKER COMPOSE UP ====================


@pytest.mark.integration
@pytest.mark.docker
class TestDockerComposeUp:
    """Testes do metodo test_docker_compose_up.

    Estes testes requerem Docker para funcionar corretamente.
    Para pular: pytest -m "not docker"
    """

    def test_file_not_found(self, validator, no_compose_project):
        """Deve falhar quando arquivo nao existe."""
        validator.generated_root = no_compose_project.parent

        result = validator.test_docker_compose_up("no_compose")

        assert result.success is False
        assert "not found" in result.stderr.lower()

    def test_docker_not_found(self, validator, valid_compose_project):
        """Deve falhar quando docker nao esta instalado."""
        validator.generated_root = valid_compose_project.parent

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("docker not found")

            result = validator.test_docker_compose_up("valid_project")

        assert result.success is False
        assert "not found" in result.stderr.lower()

    def test_timeout(self, validator, valid_compose_project):
        """Deve lidar com timeout."""
        validator.generated_root = valid_compose_project.parent

        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("docker", 60)

            result = validator.test_docker_compose_up("valid_project", timeout=60)

        assert result.success is False
        assert "timed out" in result.stderr.lower()

    def test_success(self, validator, valid_compose_project):
        """Deve retornar sucesso quando docker funciona."""
        validator.generated_root = valid_compose_project.parent

        # 1. docker compose up --build -d
        mock_up_result = MagicMock()
        mock_up_result.returncode = 0
        mock_up_result.stdout = b"Started"
        mock_up_result.stderr = b""

        # 2. docker compose ps (snapshot)
        mock_ps_snapshot = MagicMock()
        mock_ps_snapshot.returncode = 0
        mock_ps_snapshot.stdout = b"NAME\npostgres\nbackend\nfrontend"

        # 3. docker compose logs backend
        mock_logs_backend = MagicMock()
        mock_logs_backend.returncode = 0
        mock_logs_backend.stdout = b"backend started"

        # 4. docker compose logs frontend
        mock_logs_frontend = MagicMock()
        mock_logs_frontend.returncode = 0
        mock_logs_frontend.stdout = b"frontend started"

        # 5. docker compose ps --format (services list)
        mock_ps_services = MagicMock()
        mock_ps_services.returncode = 0
        mock_ps_services.stdout = b"postgres\nbackend\nfrontend"

        with patch("release.docker_compose_validator.subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock_up_result,
                mock_ps_snapshot,
                mock_logs_backend,
                mock_logs_frontend,
                mock_ps_services,
            ]

            result = validator.test_docker_compose_up("valid_project")

        assert result.success is True
        assert result.exit_code == 0


# ==================== TESTS: STOP SERVICES ====================


class TestStopServices:
    """Testes do metodo stop_services."""

    def test_stop_success(self, validator, valid_compose_project):
        """Deve parar servicos com sucesso."""
        validator.generated_root = valid_compose_project.parent

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            success = validator.stop_services("valid_project")

        assert success is True

    def test_stop_failure(self, validator, valid_compose_project):
        """Deve retornar False em caso de erro."""
        validator.generated_root = valid_compose_project.parent

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Error")

            success = validator.stop_services("valid_project")

        assert success is False


# ==================== TESTS: FIND COMPOSE FILE ====================


class TestFindComposeFile:
    """Testes do metodo _find_compose_file."""

    def test_finds_yml(self, tmp_path):
        """Deve encontrar docker-compose.yml."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "docker-compose.yml").write_text("version: '3'")

        validator = DockerComposeValidator()
        result = validator._find_compose_file(project)

        assert result is not None
        assert result.name == "docker-compose.yml"

    def test_finds_yaml(self, tmp_path):
        """Deve encontrar docker-compose.yaml."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "docker-compose.yaml").write_text("version: '3'")

        validator = DockerComposeValidator()
        result = validator._find_compose_file(project)

        assert result is not None
        assert result.name == "docker-compose.yaml"

    def test_finds_compose_yml(self, tmp_path):
        """Deve encontrar compose.yml."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "compose.yml").write_text("version: '3'")

        validator = DockerComposeValidator()
        result = validator._find_compose_file(project)

        assert result is not None
        assert result.name == "compose.yml"

    def test_not_found(self, tmp_path):
        """Deve retornar None quando nao existe."""
        project = tmp_path / "project"
        project.mkdir()

        validator = DockerComposeValidator()
        result = validator._find_compose_file(project)

        assert result is None


# ==================== TESTS: GENERATE COMPOSE CONTENT ====================


class TestGenerateComposeContent:
    """Testes do metodo _generate_compose_content."""

    def test_generates_all_services(self):
        """Deve gerar todos os servicos."""
        validator = DockerComposeValidator()

        content = validator._generate_compose_content(
            "test_project",
            has_backend=True,
            has_frontend=True,
        )

        assert "postgres:" in content
        assert "backend:" in content
        assert "frontend:" in content

    def test_skips_backend(self):
        """Deve pular backend quando nao tem."""
        validator = DockerComposeValidator()

        content = validator._generate_compose_content(
            "test_project",
            has_backend=False,
            has_frontend=True,
        )

        assert "postgres:" in content
        assert "backend:" not in content
        assert "frontend:" in content

    def test_skips_frontend(self):
        """Deve pular frontend quando nao tem."""
        validator = DockerComposeValidator()

        content = validator._generate_compose_content(
            "test_project",
            has_backend=True,
            has_frontend=False,
        )

        assert "postgres:" in content
        assert "backend:" in content
        assert "frontend:" not in content

    def test_uses_project_name(self):
        """Deve usar nome do projeto."""
        validator = DockerComposeValidator()

        content = validator._generate_compose_content("my_app")

        assert "my_app" in content


# ==================== TESTS: CONVENIENCE FUNCTIONS ====================


class TestConvenienceFunctions:
    """Testes das funcoes de conveniencia."""

    def test_validate_docker_compose(self, tmp_path):
        """validate_docker_compose deve retornar dict."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "test"
        project.mkdir(exist_ok=True)

        with patch.object(DockerComposeValidator, "DEFAULT_GENERATED_ROOT", str(generated)):
            result = validate_docker_compose("test")

        assert isinstance(result, dict)
        assert "valid" in result

    def test_ensure_docker_compose(self, tmp_path):
        """ensure_docker_compose deve retornar tupla."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "test"
        project.mkdir(exist_ok=True)

        with patch.object(DockerComposeValidator, "DEFAULT_GENERATED_ROOT", str(generated)):
            success, result = ensure_docker_compose("test")

        assert isinstance(success, bool)
        assert isinstance(result, dict)


# ==================== TESTS: REQUIRED SERVICES ACCEPTANCE ====================


class TestRequiredServicesAcceptance:
    """Testes do criterio de aceite: 3 servicos obrigatorios."""

    def test_requires_postgres(self, tmp_path):
        """Deve exigir postgres."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "no_postgres"
        project.mkdir(exist_ok=True)

        compose_content = """
version: '3.8'
services:
  backend:
    build: ./backend
  frontend:
    build: ./frontend
"""
        (project / "docker-compose.yml").write_text(compose_content)

        validator = DockerComposeValidator(generated_root=str(generated))
        result = validator.validate("no_postgres")

        assert result.valid is False
        assert "postgres" in result.missing_services

    def test_requires_backend(self, tmp_path):
        """Deve exigir backend."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "no_backend"
        project.mkdir(exist_ok=True)

        compose_content = """
version: '3.8'
services:
  postgres:
    image: postgres:15
  frontend:
    build: ./frontend
"""
        (project / "docker-compose.yml").write_text(compose_content)

        validator = DockerComposeValidator(generated_root=str(generated))
        result = validator.validate("no_backend")

        assert result.valid is False
        assert "backend" in result.missing_services

    def test_requires_frontend(self, tmp_path):
        """Deve exigir frontend."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "no_frontend"
        project.mkdir(exist_ok=True)

        compose_content = """
version: '3.8'
services:
  postgres:
    image: postgres:15
  backend:
    build: ./backend
"""
        (project / "docker-compose.yml").write_text(compose_content)

        validator = DockerComposeValidator(generated_root=str(generated))
        result = validator.validate("no_frontend")

        assert result.valid is False
        assert "frontend" in result.missing_services

    def test_valid_with_all_three(self, validator, valid_compose_project):
        """Deve ser valido com todos os 3 servicos."""
        validator.generated_root = valid_compose_project.parent

        result = validator.validate("valid_project")

        assert result.valid is True
        assert len(result.missing_services) == 0
        assert "postgres" in result.services_found
        assert "backend" in result.services_found
        assert "frontend" in result.services_found
