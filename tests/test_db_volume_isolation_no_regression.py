"""Testes anti-regressão para isolamento de volume DB por exec_id.

Objetivo: Garantir que o comportamento de volume isolation continua funcionando
após mudanças no código, sem regressões.

Casos cobertos:
1. Release com exec_id: volume escopado
2. Sem exec_id: volume fixo (compatibilidade)
3. Dois exec_ids geram composites distintos
4. Release report contém db_volume_name
5. Compose não tem container_name
"""

import json
import pytest
import yaml
from pathlib import Path

from repo.repo_generator import RepoGenerator
from release.release_report import ReleaseReportGenerator, ReleaseReport


class TestReleaseComposeVolumeIsolation:
    """Testes para garantir que compose em release tem volume escopado."""

    @pytest.fixture
    def temp_templates(self, tmp_path):
        """Cria estrutura de templates temporária."""
        templates_root = tmp_path / "templates"
        templates_root.mkdir()

        # Criar template docker
        docker_dir = templates_root / "docker"
        docker_dir.mkdir()

        # docker-compose.yml template idêntico ao real
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

    def test_release_compose_volume_scoped_by_exec_id(
        self, temp_templates, temp_output
    ):
        """[Anti-regressão] Compose em release tem volume escopado por exec_id."""
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

        # 1. Volume mount no serviço db deve conter exec_id
        db_volumes = compose["services"]["db"]["volumes"]
        volume_mount = [v for v in db_volumes if "postgres_data" in v][0]

        expected_volume = f"postgres_data_{exec_id}"
        assert expected_volume in volume_mount, (
            f"Volume mount deveria conter '{expected_volume}', "
            f"mas encontrou: {volume_mount}"
        )

        # 2. Volume deve estar declarado em volumes:
        assert expected_volume in compose.get("volumes", {}), (
            f"Volume '{expected_volume}' deveria estar em volumes:, "
            f"encontrado: {list(compose.get('volumes', {}).keys())}"
        )

        # 3. NÃO deve ter container_name em nenhum serviço
        for service_name, service_config in compose.get("services", {}).items():
            assert "container_name" not in service_config, (
                f"Serviço '{service_name}' não deveria ter 'container_name'"
            )

    def test_non_release_compose_keeps_fixed_volume_name(
        self, temp_templates, temp_output
    ):
        """[Anti-regressão] Sem exec_id, volume usa nome padrão (compatibilidade)."""
        generator = RepoGenerator(
            templates_root=str(temp_templates),
            output_root=str(temp_output),
        )

        # Sem exec_id (modo não-release ou dev)
        repo_path = generator.create_repo("test_project_no_exec", exec_id=None)

        compose_path = repo_path / "docker-compose.yml"
        compose_content = compose_path.read_text()
        compose = yaml.safe_load(compose_content)

        # Volume mount deve ser o padrão
        db_volumes = compose["services"]["db"]["volumes"]
        volume_mount = [v for v in db_volumes if "postgres_data" in v][0]

        assert volume_mount.startswith("postgres_data:/"), (
            f"Volume mount deveria ser 'postgres_data:/...', mas é: {volume_mount}"
        )

        # Volume declarado deve ser o padrão
        assert "postgres_data" in compose.get("volumes", {}), (
            "Volume 'postgres_data' deveria estar presente sem exec_id"
        )

    def test_two_exec_ids_generate_two_distinct_compose_files(
        self, temp_templates, temp_output
    ):
        """[Anti-regressão] Dois exec_ids geram composes com volumes diferentes."""
        generator = RepoGenerator(
            templates_root=str(temp_templates),
            output_root=str(temp_output),
        )

        # Primeiro release
        exec_id_a = "petclinic_aaaaaa"
        repo_a = generator.create_repo("project_a", exec_id=exec_id_a)
        compose_a = yaml.safe_load((repo_a / "docker-compose.yml").read_text())
        volumes_a = list(compose_a.get("volumes", {}).keys())

        # Segundo release
        exec_id_b = "petclinic_bbbbbb"
        repo_b = generator.create_repo("project_b", exec_id=exec_id_b)
        compose_b = yaml.safe_load((repo_b / "docker-compose.yml").read_text())
        volumes_b = list(compose_b.get("volumes", {}).keys())

        # Volumes devem ser diferentes
        assert volumes_a != volumes_b, (
            f"Volumes deveriam ser diferentes: A={volumes_a}, B={volumes_b}"
        )

        # E cada um deve conter seu exec_id
        assert f"postgres_data_{exec_id_a}" in volumes_a, (
            f"Volume A deveria conter exec_id_a: {volumes_a}"
        )
        assert f"postgres_data_{exec_id_b}" in volumes_b, (
            f"Volume B deveria conter exec_id_b: {volumes_b}"
        )


class TestReleaseReportContainsDbVolumeName:
    """Testes para garantir que release_report contém db_volume_name."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretório de store temporário."""
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_release_report_json_contains_db_volume_name(self, temp_store):
        """[Anti-regressão] release_report.json contém db_volume_name com exec_id."""
        generator = ReleaseReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        exec_id = "petclinic_test123"
        run_result = {
            "success": True,
            "final_status": "running",
            "execution_id": exec_id,
            "build_ok": True,
            "docker_compose_ok": True,
            "smoke_ok": True,
            "smoke_passed": 6,
            "smoke_failed": 0,
            "services_running": ["backend", "db", "frontend"],
        }

        report = generator.generate("test_project", run_result)
        report_dict = report.to_dict()

        # Verificar campo no JSON
        assert "release" in report_dict
        assert "db_volume_name" in report_dict["release"], (
            "release_report.json deve conter 'db_volume_name' em 'release'"
        )

        expected_volume = f"postgres_data_{exec_id}"
        assert report_dict["release"]["db_volume_name"] == expected_volume, (
            f"db_volume_name deveria ser '{expected_volume}', "
            f"mas é: {report_dict['release']['db_volume_name']}"
        )

    def test_release_report_md_contains_db_volume_name(self, temp_store):
        """[Anti-regressão] release_report.md contém linha com DB Volume."""
        generator = ReleaseReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        exec_id = "petclinic_md456"
        run_result = {
            "success": True,
            "final_status": "running",
            "execution_id": exec_id,
            "build_ok": True,
            "docker_compose_ok": True,
            "smoke_ok": True,
        }

        report = generator.generate("test_project", run_result)
        md_content = report.to_markdown()

        expected_volume = f"postgres_data_{exec_id}"
        assert "DB Volume" in md_content, (
            "release_report.md deve conter 'DB Volume'"
        )
        assert expected_volume in md_content, (
            f"release_report.md deve conter '{expected_volume}'"
        )

    def test_release_report_without_exec_id_uses_default_volume(self, temp_store):
        """[Anti-regressão] Sem exec_id, db_volume_name é 'postgres_data'."""
        generator = ReleaseReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        # Sem execution_id
        run_result = {
            "success": True,
            "final_status": "running",
            "execution_id": None,  # Sem exec_id
            "build_ok": True,
        }

        report = generator.generate("test_project", run_result)
        report_dict = report.to_dict()

        assert report_dict["release"]["db_volume_name"] == "postgres_data", (
            "Sem exec_id, db_volume_name deve ser 'postgres_data'"
        )

    def test_release_report_save_creates_json_with_db_volume(self, temp_store, tmp_path):
        """[Anti-regressão] Arquivo JSON salvo contém db_volume_name."""
        generator = ReleaseReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        exec_id = "petclinic_save789"
        run_result = {
            "success": True,
            "final_status": "running",
            "execution_id": exec_id,
            "build_ok": True,
            "docker_compose_ok": True,
            "smoke_ok": True,
        }

        output_dir = tmp_path / "releases"
        result = generator.generate_and_save(
            "test_project", run_result, output_dir=output_dir
        )

        # Ler JSON salvo
        json_path = Path(result["files"]["json"])
        assert json_path.exists(), "Arquivo JSON não foi criado"

        with open(json_path) as f:
            saved_report = json.load(f)

        expected_volume = f"postgres_data_{exec_id}"
        assert saved_report["release"]["db_volume_name"] == expected_volume, (
            f"JSON salvo deve ter db_volume_name='{expected_volume}'"
        )

    def test_release_report_json_contains_execution_id(self, temp_store):
        """[Anti-regressão] release_report.json contém execution_id."""
        generator = ReleaseReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        exec_id = "petclinic_execid123"
        run_result = {
            "success": True,
            "final_status": "running",
            "execution_id": exec_id,
            "build_ok": True,
            "docker_compose_ok": True,
            "smoke_ok": True,
        }

        report = generator.generate("test_project", run_result)
        report_dict = report.to_dict()

        # Verificar execution_id no top-level
        assert "execution_id" in report_dict, (
            "release_report.json deve conter 'execution_id' no top-level"
        )
        assert report_dict["execution_id"] == exec_id, (
            f"execution_id deveria ser '{exec_id}', "
            f"mas é: {report_dict['execution_id']}"
        )

    def test_release_report_save_json_contains_execution_id(self, temp_store, tmp_path):
        """[Anti-regressão] Arquivo JSON salvo contém execution_id."""
        generator = ReleaseReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        exec_id = "petclinic_saved_execid"
        run_result = {
            "success": True,
            "final_status": "running",
            "execution_id": exec_id,
            "build_ok": True,
        }

        output_dir = tmp_path / "releases"
        result = generator.generate_and_save(
            "test_project", run_result, output_dir=output_dir
        )

        json_path = Path(result["files"]["json"])
        with open(json_path) as f:
            saved_report = json.load(f)

        assert saved_report["execution_id"] == exec_id, (
            f"JSON salvo deve ter execution_id='{exec_id}'"
        )


class TestComposeNoContainerName:
    """Teste específico para garantir ausência de container_name."""

    @pytest.fixture
    def temp_templates(self, tmp_path):
        """Cria templates com compose sem container_name."""
        templates_root = tmp_path / "templates"
        templates_root.mkdir()

        docker_dir = templates_root / "docker"
        docker_dir.mkdir()

        # Compose SEM container_name (como deve ser)
        compose_content = """services:
  db:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    depends_on:
      - db

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    depends_on:
      - backend

volumes:
  postgres_data:
"""
        (docker_dir / "docker-compose.yml").write_text(compose_content)

        for name in ["spring-boot", "react-vite", "postgres-flyway"]:
            tmpl_dir = templates_root / name
            tmpl_dir.mkdir()
            (tmpl_dir / "placeholder.txt").write_text("")

        return templates_root

    def test_compose_never_has_container_name(self, temp_templates, tmp_path):
        """[Anti-regressão] docker-compose.yml nunca tem container_name."""
        output_dir = tmp_path / "generated"
        output_dir.mkdir()

        generator = RepoGenerator(
            templates_root=str(temp_templates),
            output_root=str(output_dir),
        )

        # Testar com exec_id
        repo_path = generator.create_repo("test_with_exec", exec_id="exec_123")
        compose_content = (repo_path / "docker-compose.yml").read_text()

        assert "container_name" not in compose_content, (
            "docker-compose.yml não deve conter 'container_name'"
        )

        # Testar sem exec_id
        repo_path2 = generator.create_repo("test_without_exec", exec_id=None)
        compose_content2 = (repo_path2 / "docker-compose.yml").read_text()

        assert "container_name" not in compose_content2, (
            "docker-compose.yml sem exec_id também não deve ter 'container_name'"
        )
