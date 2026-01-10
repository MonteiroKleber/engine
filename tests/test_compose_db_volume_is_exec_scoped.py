"""Testes para garantir que o volume do DB é isolado por exec_id.

Objetivo: Evitar checksum mismatch do Flyway entre execuções,
garantindo que cada release use um volume de Postgres exclusivo.
"""

import pytest
import yaml
from pathlib import Path

from repo.repo_generator import RepoGenerator


class TestComposeDbVolumeIsExecScoped:
    """Testa que docker-compose.yml tem volume de postgres com exec_id."""

    @pytest.fixture
    def temp_templates(self, tmp_path):
        """Cria estrutura de templates temporária."""
        templates_root = tmp_path / "templates"
        templates_root.mkdir()

        # Criar template docker
        docker_dir = templates_root / "docker"
        docker_dir.mkdir()

        # Escrever docker-compose.yml template (como o real)
        compose_content = """services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: app_db
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD: app_password
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-db:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_user -d app_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      SPRING_PROFILES_ACTIVE: dev
      SPRING_DATASOURCE_URL: jdbc:postgresql://db:5432/app_db
      SPRING_DATASOURCE_USERNAME: app_user
      SPRING_DATASOURCE_PASSWORD: app_password
    ports:
      - "8080:8080"
    depends_on:
      db:
        condition: service_healthy

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "5173:80"
    depends_on:
      - backend

volumes:
  postgres_data:
"""
        (docker_dir / "docker-compose.yml").write_text(compose_content)

        # Criar templates vazios para backend/frontend/db
        for name in ["spring-boot", "react-vite", "postgres-flyway"]:
            tmpl_dir = templates_root / name
            tmpl_dir.mkdir()
            (tmpl_dir / "placeholder.txt").write_text("placeholder")

        return templates_root

    @pytest.fixture
    def temp_output(self, tmp_path):
        """Cria diretório de saída temporário."""
        output_dir = tmp_path / "generated"
        output_dir.mkdir()
        return output_dir

    def test_compose_with_exec_id_has_scoped_volume_in_db_service(
        self, temp_templates, temp_output
    ):
        """Volume do DB deve conter exec_id na montagem do serviço."""
        generator = RepoGenerator(
            templates_root=str(temp_templates),
            output_root=str(temp_output),
        )

        exec_id = "petclinic_abc123"
        repo_path = generator.create_repo("test_project", exec_id=exec_id)

        compose_path = repo_path / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml não foi criado"

        compose_content = compose_path.read_text()
        compose = yaml.safe_load(compose_content)

        # Verificar que o serviço db usa volume com exec_id
        db_volumes = compose["services"]["db"]["volumes"]
        volume_mount = [v for v in db_volumes if "postgres_data" in v][0]

        expected_volume = f"postgres_data_{exec_id}"
        assert expected_volume in volume_mount, (
            f"Volume mount deveria conter '{expected_volume}', "
            f"mas encontrou: {volume_mount}"
        )

    def test_compose_with_exec_id_has_scoped_volume_in_declaration(
        self, temp_templates, temp_output
    ):
        """Volume do DB deve conter exec_id na declaração de volumes."""
        generator = RepoGenerator(
            templates_root=str(temp_templates),
            output_root=str(temp_output),
        )

        exec_id = "petclinic_xyz789"
        repo_path = generator.create_repo("test_project2", exec_id=exec_id)

        compose_path = repo_path / "docker-compose.yml"
        compose_content = compose_path.read_text()
        compose = yaml.safe_load(compose_content)

        # Verificar que o volume está declarado com exec_id
        expected_volume = f"postgres_data_{exec_id}"
        assert expected_volume in compose.get("volumes", {}), (
            f"Volume '{expected_volume}' deveria estar declarado em volumes:, "
            f"mas volumes contém: {list(compose.get('volumes', {}).keys())}"
        )

    def test_compose_without_exec_id_uses_default_volume(
        self, temp_templates, temp_output
    ):
        """Sem exec_id, volume deve usar nome padrão (modo não-release)."""
        generator = RepoGenerator(
            templates_root=str(temp_templates),
            output_root=str(temp_output),
        )

        # Sem exec_id
        repo_path = generator.create_repo("test_project3", exec_id=None)

        compose_path = repo_path / "docker-compose.yml"
        compose_content = compose_path.read_text()
        compose = yaml.safe_load(compose_content)

        # Volume deve ser o padrão
        assert "postgres_data" in compose.get("volumes", {}), (
            "Volume 'postgres_data' deveria estar presente sem exec_id"
        )

        # E NÃO deve ter sufixo de exec_id
        db_volumes = compose["services"]["db"]["volumes"]
        volume_mount = [v for v in db_volumes if "postgres_data" in v][0]
        assert volume_mount.startswith("postgres_data:"), (
            f"Volume mount deveria ser 'postgres_data:...', mas é: {volume_mount}"
        )

    def test_compose_has_no_container_name(self, temp_templates, temp_output):
        """docker-compose.yml não deve ter container_name em nenhum serviço."""
        generator = RepoGenerator(
            templates_root=str(temp_templates),
            output_root=str(temp_output),
        )

        repo_path = generator.create_repo("test_project4", exec_id="exec_123")

        compose_path = repo_path / "docker-compose.yml"
        compose_content = compose_path.read_text()
        compose = yaml.safe_load(compose_content)

        for service_name, service_config in compose.get("services", {}).items():
            assert "container_name" not in service_config, (
                f"Serviço '{service_name}' não deveria ter 'container_name'"
            )

    def test_two_releases_have_different_volumes(self, temp_templates, temp_output):
        """Dois releases sequenciais devem ter volumes diferentes."""
        generator = RepoGenerator(
            templates_root=str(temp_templates),
            output_root=str(temp_output),
        )

        # Primeiro release
        exec_id_1 = "petclinic_run1"
        repo_path_1 = generator.create_repo("project_run1", exec_id=exec_id_1)
        compose_1 = yaml.safe_load((repo_path_1 / "docker-compose.yml").read_text())
        volumes_1 = list(compose_1.get("volumes", {}).keys())

        # Segundo release
        exec_id_2 = "petclinic_run2"
        repo_path_2 = generator.create_repo("project_run2", exec_id=exec_id_2)
        compose_2 = yaml.safe_load((repo_path_2 / "docker-compose.yml").read_text())
        volumes_2 = list(compose_2.get("volumes", {}).keys())

        # Volumes devem ser diferentes
        assert volumes_1 != volumes_2, (
            f"Volumes deveriam ser diferentes entre execuções: "
            f"run1={volumes_1}, run2={volumes_2}"
        )

        # E ambos devem conter seus respectivos exec_ids
        assert f"postgres_data_{exec_id_1}" in volumes_1
        assert f"postgres_data_{exec_id_2}" in volumes_2


class TestComposeDbVolumeIntegration:
    """Teste de integração leve (sem docker real) simulando release."""

    @pytest.fixture
    def temp_templates(self, tmp_path):
        """Cria estrutura de templates."""
        templates_root = tmp_path / "templates"
        templates_root.mkdir()

        docker_dir = templates_root / "docker"
        docker_dir.mkdir()

        compose_content = """services:
  db:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
"""
        (docker_dir / "docker-compose.yml").write_text(compose_content)

        for name in ["spring-boot", "react-vite", "postgres-flyway"]:
            tmpl_dir = templates_root / name
            tmpl_dir.mkdir()
            (tmpl_dir / "placeholder.txt").write_text("")

        return templates_root

    def test_simulated_release_creates_exec_scoped_compose(
        self, temp_templates, tmp_path
    ):
        """Simula release run e confirma compose exec-scoped."""
        output_dir = tmp_path / "generated"
        output_dir.mkdir()

        # Simular criação de exec_id como o engine faz
        import uuid
        project = "petclinic"
        exec_id = f"{project}_{uuid.uuid4().hex[:8]}"

        generator = RepoGenerator(
            templates_root=str(temp_templates),
            output_root=str(output_dir),
        )

        repo_path = generator.create_repo(project, exec_id=exec_id)

        # Verificar compose
        compose_path = repo_path / "docker-compose.yml"
        compose_content = compose_path.read_text()

        # Deve conter o volume com exec_id em pelo menos 2 lugares
        expected_volume = f"postgres_data_{exec_id}"
        occurrences = compose_content.count(expected_volume)

        assert occurrences >= 2, (
            f"Volume '{expected_volume}' deveria aparecer pelo menos 2x "
            f"(montagem + declaração), mas apareceu {occurrences}x"
        )

        # NÃO deve conter container_name
        assert "container_name:" not in compose_content, (
            "docker-compose.yml não deveria ter 'container_name:'"
        )

        # NÃO deve conter o volume antigo (sem exec_id)
        # Verificar que 'postgres_data:' sozinho não existe
        compose = yaml.safe_load(compose_content)
        old_volume = "postgres_data"
        assert old_volume not in compose.get("volumes", {}), (
            f"Volume antigo '{old_volume}' não deveria existir, "
            f"apenas '{expected_volume}'"
        )
