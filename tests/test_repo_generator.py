"""Testes para o Repo Generator."""

import shutil
import tempfile
from pathlib import Path

import pytest

from repo.repo_generator import RepoGenerator, create_repo


@pytest.fixture
def temp_templates():
    """Cria um diretório temporário com templates mock."""
    temp_dir = tempfile.mkdtemp()
    templates_dir = Path(temp_dir) / "templates"

    # Criar estrutura mock de templates
    (templates_dir / "spring-boot/src/main/java").mkdir(parents=True)
    (templates_dir / "spring-boot/pom.xml").write_text("<project/>")

    (templates_dir / "react-vite/src").mkdir(parents=True)
    (templates_dir / "react-vite/package.json").write_text('{"name": "app"}')

    (templates_dir / "postgres-flyway/migrations").mkdir(parents=True)
    (templates_dir / "postgres-flyway/flyway.conf").write_text("flyway.url=jdbc:")

    (templates_dir / "docker").mkdir(parents=True)
    (templates_dir / "docker/docker-compose.yml").write_text("version: '3.8'")
    (templates_dir / "docker/docker-compose.dev.yml").write_text("version: '3.8'")
    (templates_dir / "docker/Dockerfile.backend").write_text("FROM maven")
    (templates_dir / "docker/Dockerfile.frontend").write_text("FROM node")
    (templates_dir / "docker/nginx.conf").write_text("server {}")
    (templates_dir / "docker/.env.example").write_text("DB_HOST=localhost")

    yield templates_dir, temp_dir

    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_output():
    """Cria um diretório temporário para output."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


class TestRepoGeneratorBasic:
    """Testes básicos do RepoGenerator."""

    def test_init_with_defaults(self):
        """RepoGenerator deve inicializar com valores padrão."""
        generator = RepoGenerator()

        assert generator.templates_root == Path("/home/bazari/templates")
        assert generator.output_root == Path("/home/bazari/generated")

    def test_init_with_custom_paths(self, temp_templates, temp_output):
        """RepoGenerator deve aceitar caminhos customizados."""
        templates_dir, _ = temp_templates

        generator = RepoGenerator(
            templates_root=str(templates_dir),
            output_root=str(temp_output),
        )

        assert generator.templates_root == templates_dir
        assert generator.output_root == temp_output


class TestCreateRepo:
    """Testes do método create_repo."""

    def test_create_repo_returns_path(self, temp_templates, temp_output):
        """create_repo deve retornar o Path do projeto criado."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        result = generator.create_repo("test_project")

        assert isinstance(result, Path)
        assert result == temp_output / "test_project"

    def test_create_repo_creates_directory(self, temp_templates, temp_output):
        """create_repo deve criar o diretório do projeto."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        result = generator.create_repo("my_project")

        assert result.exists()
        assert result.is_dir()

    def test_create_repo_creates_backend(self, temp_templates, temp_output):
        """create_repo deve criar diretório backend."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        result = generator.create_repo("project1")

        backend = result / "backend"
        assert backend.exists()
        assert (backend / "pom.xml").exists()
        assert (backend / "src/main/java").exists()

    def test_create_repo_creates_frontend(self, temp_templates, temp_output):
        """create_repo deve criar diretório frontend."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        result = generator.create_repo("project2")

        frontend = result / "frontend"
        assert frontend.exists()
        assert (frontend / "package.json").exists()
        assert (frontend / "src").exists()

    def test_create_repo_creates_db(self, temp_templates, temp_output):
        """create_repo deve criar diretório db."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        result = generator.create_repo("project3")

        db = result / "db"
        assert db.exists()
        assert (db / "flyway.conf").exists()
        assert (db / "migrations").exists()

    def test_create_repo_creates_docker_compose(self, temp_templates, temp_output):
        """create_repo deve criar docker-compose.yml."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        result = generator.create_repo("project4")

        compose = result / "docker-compose.yml"
        assert compose.exists()
        assert "version" in compose.read_text()

    def test_create_repo_creates_docker_compose_dev(self, temp_templates, temp_output):
        """create_repo deve criar docker-compose.dev.yml."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        result = generator.create_repo("project5")

        compose_dev = result / "docker-compose.dev.yml"
        assert compose_dev.exists()

    def test_create_repo_creates_docker_dir(self, temp_templates, temp_output):
        """create_repo deve criar diretório docker com Dockerfiles."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        result = generator.create_repo("project6")

        docker_dir = result / "docker"
        assert docker_dir.exists()
        assert (docker_dir / "Dockerfile.backend").exists()
        assert (docker_dir / "Dockerfile.frontend").exists()
        assert (docker_dir / "nginx.conf").exists()

    def test_create_repo_creates_env_example(self, temp_templates, temp_output):
        """create_repo deve criar .env.example."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        result = generator.create_repo("project7")

        env_example = result / ".env.example"
        assert env_example.exists()


class TestCreateRepoErrors:
    """Testes de erros do create_repo."""

    def test_empty_project_name_raises(self, temp_templates, temp_output):
        """create_repo deve falhar com nome vazio."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        with pytest.raises(ValueError, match="cannot be empty"):
            generator.create_repo("")

    def test_whitespace_project_name_raises(self, temp_templates, temp_output):
        """create_repo deve falhar com nome só espaços."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        with pytest.raises(ValueError, match="cannot be empty"):
            generator.create_repo("   ")

    def test_missing_templates_raises(self, temp_output):
        """create_repo deve falhar se templates não existirem."""
        generator = RepoGenerator("/nonexistent/path", str(temp_output))

        with pytest.raises(FileNotFoundError, match="Templates root not found"):
            generator.create_repo("test")

    def test_existing_project_raises(self, temp_templates, temp_output):
        """create_repo deve falhar se projeto já existir."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        generator.create_repo("existing")

        with pytest.raises(FileExistsError, match="already exists"):
            generator.create_repo("existing")


class TestRepoExists:
    """Testes do método repo_exists."""

    def test_repo_exists_false_when_not_created(self, temp_templates, temp_output):
        """repo_exists deve retornar False se não existir."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        assert generator.repo_exists("nonexistent") is False

    def test_repo_exists_true_after_create(self, temp_templates, temp_output):
        """repo_exists deve retornar True após criar."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        generator.create_repo("myproject")

        assert generator.repo_exists("myproject") is True


class TestDeleteRepo:
    """Testes do método delete_repo."""

    def test_delete_repo_removes_directory(self, temp_templates, temp_output):
        """delete_repo deve remover o diretório."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        generator.create_repo("to_delete")
        assert generator.repo_exists("to_delete")

        generator.delete_repo("to_delete")
        assert not generator.repo_exists("to_delete")

    def test_delete_nonexistent_raises(self, temp_templates, temp_output):
        """delete_repo deve falhar se projeto não existir."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        with pytest.raises(FileNotFoundError, match="not found"):
            generator.delete_repo("nonexistent")


class TestGetRepoPath:
    """Testes do método get_repo_path."""

    def test_get_repo_path_returns_none_if_not_exists(self, temp_templates, temp_output):
        """get_repo_path deve retornar None se não existir."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        assert generator.get_repo_path("nonexistent") is None

    def test_get_repo_path_returns_path_if_exists(self, temp_templates, temp_output):
        """get_repo_path deve retornar Path se existir."""
        templates_dir, _ = temp_templates
        generator = RepoGenerator(str(templates_dir), str(temp_output))

        generator.create_repo("myproject")

        path = generator.get_repo_path("myproject")
        assert path is not None
        assert path == temp_output / "myproject"


class TestCreateRepoFunction:
    """Testes da função de conveniência create_repo."""

    def test_create_repo_function_works(self, temp_templates, temp_output):
        """Função create_repo deve funcionar."""
        templates_dir, _ = temp_templates

        result = create_repo(
            "test_project",
            templates_root=str(templates_dir),
            output_root=str(temp_output),
        )

        assert result.exists()
        assert (result / "backend").exists()
        assert (result / "frontend").exists()
        assert (result / "db").exists()
        assert (result / "docker-compose.yml").exists()


class TestWithRealTemplates:
    """Testes com templates reais (se existirem)."""

    @pytest.fixture
    def real_output(self):
        """Cria diretório de output temporário."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    def test_create_repo_with_real_templates(self, real_output):
        """create_repo deve funcionar com templates reais."""
        templates_path = Path("/home/bazari/templates")

        if not templates_path.exists():
            pytest.skip("Real templates not available")

        generator = RepoGenerator(str(templates_path), str(real_output))
        result = generator.create_repo("demo")

        # Verificar estrutura
        assert result.exists()
        assert (result / "backend").exists()
        assert (result / "frontend").exists()
        assert (result / "db").exists()
        assert (result / "docker-compose.yml").exists()

        # Verificar arquivos específicos
        assert (result / "backend/pom.xml").exists()
        assert (result / "frontend/package.json").exists()
        assert (result / "db/flyway.conf").exists()

    def test_created_repo_stays_in_generated(self, real_output):
        """Arquivos criados devem ficar apenas em generated/."""
        templates_path = Path("/home/bazari/templates")

        if not templates_path.exists():
            pytest.skip("Real templates not available")

        generator = RepoGenerator(str(templates_path), str(real_output))
        result = generator.create_repo("demo_isolated")

        # Verificar que tudo está dentro do output
        for path in result.rglob("*"):
            assert str(path).startswith(str(real_output))
