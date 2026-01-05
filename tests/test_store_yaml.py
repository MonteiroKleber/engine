"""Testes para suporte a YAML no artifacts store."""

import shutil
import tempfile
from pathlib import Path

import pytest

from store.artifacts_store import ArtifactsStore


class TestStoreYAMLSupport:
    """Testes de suporte a artefatos YAML."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_save_text_artifact_creates_yaml_file(self, temp_store):
        """save_text_artifact deve criar arquivo YAML."""
        store = ArtifactsStore(temp_store)
        yaml_content = """openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
paths: {}
"""
        path = store.save_text_artifact("test_project", "OAS", 1, yaml_content, ext="yaml")

        assert path.exists()
        assert path.name == "v1.yaml"
        assert path.read_text() == yaml_content

    def test_load_text_artifact_returns_content(self, temp_store):
        """load_text_artifact deve retornar conteúdo do arquivo."""
        store = ArtifactsStore(temp_store)
        yaml_content = "openapi: 3.0.0\n"

        store.save_text_artifact("test_project", "OAS", 1, yaml_content, ext="yaml")
        loaded = store.load_text_artifact("test_project", "OAS", 1, ext="yaml")

        assert loaded == yaml_content

    def test_load_text_artifact_nonexistent_returns_none(self, temp_store):
        """load_text_artifact deve retornar None se arquivo não existe."""
        store = ArtifactsStore(temp_store)

        result = store.load_text_artifact("test_project", "OAS", 99, ext="yaml")

        assert result is None

    def test_load_latest_text_returns_newest_version(self, temp_store):
        """load_latest_text deve retornar a versão mais recente."""
        store = ArtifactsStore(temp_store)

        store.save_text_artifact("test_project", "OAS", 1, "version: 1\n", ext="yaml")
        store.save_text_artifact("test_project", "OAS", 2, "version: 2\n", ext="yaml")
        store.save_text_artifact("test_project", "OAS", 3, "version: 3\n", ext="yaml")

        latest = store.load_latest_text("test_project", "OAS", ext="yaml")

        assert latest == "version: 3\n"

    def test_load_latest_text_nonexistent_returns_none(self, temp_store):
        """load_latest_text deve retornar None se não há versões."""
        store = ArtifactsStore(temp_store)

        result = store.load_latest_text("test_project", "OAS", ext="yaml")

        assert result is None

    def test_next_version_works_for_yaml(self, temp_store):
        """next_version deve funcionar para artefatos YAML."""
        store = ArtifactsStore(temp_store)

        # Primeira versão
        v1 = store.next_version("test_project", "OAS")
        assert v1 == 1

        # Salvar e verificar próxima
        store.save_text_artifact("test_project", "OAS", 1, "v1\n", ext="yaml")
        v2 = store.next_version("test_project", "OAS")
        assert v2 == 2

    def test_list_artifacts_works_for_yaml(self, temp_store):
        """list_artifacts deve listar artefatos YAML."""
        store = ArtifactsStore(temp_store)

        store.save_text_artifact("test_project", "OAS", 1, "v1\n", ext="yaml")
        store.save_text_artifact("test_project", "OAS", 2, "v2\n", ext="yaml")

        artifacts = store.list_artifacts("test_project", "OAS")

        assert len(artifacts) == 2
        assert artifacts[0]["version"] == 1
        assert artifacts[0]["path"].endswith("v1.yaml")
        assert artifacts[1]["version"] == 2
        assert artifacts[1]["path"].endswith("v2.yaml")


class TestStoreRBACSupport:
    """Testes de suporte a RBAC no store."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_save_rbac_artifact(self, temp_store):
        """save_artifact deve salvar RBAC como JSON."""
        store = ArtifactsStore(temp_store)
        rbac = {
            "roles": ["authenticated", "admin"],
            "permissions": [
                {"operation_id": "listUsers", "required_role": "authenticated"}
            ]
        }

        path = store.save_artifact("test_project", "RBAC", 1, rbac)

        assert path.exists()
        assert path.name == "v1.json"

    def test_load_rbac_artifact(self, temp_store):
        """load_version deve carregar RBAC."""
        store = ArtifactsStore(temp_store)
        rbac = {
            "roles": ["authenticated"],
            "permissions": []
        }

        store.save_artifact("test_project", "RBAC", 1, rbac)
        loaded = store.load_version("test_project", "RBAC", 1)

        assert loaded == rbac

    def test_rbac_versioning(self, temp_store):
        """RBAC deve suportar versionamento."""
        store = ArtifactsStore(temp_store)

        rbac_v1 = {"roles": ["user"], "permissions": []}
        rbac_v2 = {"roles": ["user", "admin"], "permissions": []}

        store.save_artifact("test_project", "RBAC", 1, rbac_v1)
        store.save_artifact("test_project", "RBAC", 2, rbac_v2)

        assert store.load_version("test_project", "RBAC", 1) == rbac_v1
        assert store.load_version("test_project", "RBAC", 2) == rbac_v2
        assert store.load_latest("test_project", "RBAC") == rbac_v2


class TestStoreProjectStructure:
    """Testes da estrutura de projeto com novos kinds."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_ensure_project_structure_creates_all_dirs(self, temp_store):
        """_ensure_project_structure deve criar todos os diretórios."""
        store = ArtifactsStore(temp_store)
        store._ensure_project_structure("test_project")

        project_path = Path(temp_store) / "test_project"
        assert (project_path / "SRS").exists()
        assert (project_path / "IR").exists()
        assert (project_path / "OAS").exists()
        assert (project_path / "RBAC").exists()
        assert (project_path / "PLAN").exists()
        assert (project_path / "logs").exists()
        assert (project_path / "runs").exists()

    def test_kind_extensions_mapping(self, temp_store):
        """KIND_EXTENSIONS deve mapear kinds para extensões."""
        store = ArtifactsStore(temp_store)

        assert store._get_extension_for_kind("SRS") == "json"
        assert store._get_extension_for_kind("IR") == "json"
        assert store._get_extension_for_kind("RBAC") == "json"
        assert store._get_extension_for_kind("OAS") == "yaml"
        assert store._get_extension_for_kind("PLAN") == "json"
        assert store._get_extension_for_kind("unknown") == "json"  # default


class TestStorePLANSupport:
    """Testes de suporte a PLAN no store."""

    @pytest.fixture
    def temp_store(self):
        """Cria um diretório temporário para o store."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_plan(self):
        """Retorna um PLAN de exemplo."""
        return {
            "meta": {
                "version": "v1",
                "strategy": "PATCH_ONLY",
                "project_name": "Test Project",
            },
            "tasks": [
                {
                    "id": "task_create_model",
                    "title": "Create model",
                    "order": 1,
                    "files": ["src/models/entity.py"],
                    "acceptance": ["Model exists"],
                }
            ],
        }

    def test_save_plan_artifact(self, temp_store, sample_plan):
        """save_artifact deve salvar PLAN como JSON."""
        store = ArtifactsStore(temp_store)

        path = store.save_artifact("test_project", "PLAN", 1, sample_plan)

        assert path.exists()
        assert path.name == "v1.json"

    def test_load_plan_artifact(self, temp_store, sample_plan):
        """load_version deve carregar PLAN."""
        store = ArtifactsStore(temp_store)

        store.save_artifact("test_project", "PLAN", 1, sample_plan)
        loaded = store.load_version("test_project", "PLAN", 1)

        assert loaded == sample_plan

    def test_plan_versioning(self, temp_store):
        """PLAN deve suportar versionamento."""
        store = ArtifactsStore(temp_store)

        plan_v1 = {
            "meta": {"version": "v1", "strategy": "PATCH_ONLY"},
            "tasks": [{"id": "task_1", "title": "Task 1", "order": 1, "files": ["f1.py"], "acceptance": ["ok"]}],
        }
        plan_v2 = {
            "meta": {"version": "v2", "strategy": "PATCH_ONLY"},
            "tasks": [
                {"id": "task_1", "title": "Task 1", "order": 1, "files": ["f1.py"], "acceptance": ["ok"]},
                {"id": "task_2", "title": "Task 2", "order": 2, "files": ["f2.py"], "acceptance": ["ok"]},
            ],
        }

        store.save_artifact("test_project", "PLAN", 1, plan_v1)
        store.save_artifact("test_project", "PLAN", 2, plan_v2)

        assert store.load_version("test_project", "PLAN", 1) == plan_v1
        assert store.load_version("test_project", "PLAN", 2) == plan_v2
        assert store.load_latest("test_project", "PLAN") == plan_v2

    def test_plan_next_version(self, temp_store, sample_plan):
        """next_version deve funcionar para PLAN."""
        store = ArtifactsStore(temp_store)

        v1 = store.next_version("test_project", "PLAN")
        assert v1 == 1

        store.save_artifact("test_project", "PLAN", 1, sample_plan)
        v2 = store.next_version("test_project", "PLAN")
        assert v2 == 2

    def test_plan_list_artifacts(self, temp_store, sample_plan):
        """list_artifacts deve listar PLANs."""
        store = ArtifactsStore(temp_store)

        store.save_artifact("test_project", "PLAN", 1, sample_plan)
        sample_plan["meta"]["version"] = "v2"
        store.save_artifact("test_project", "PLAN", 2, sample_plan)

        artifacts = store.list_artifacts("test_project", "PLAN")

        assert len(artifacts) == 2
        assert artifacts[0]["version"] == 1
        assert artifacts[0]["path"].endswith("v1.json")
        assert artifacts[1]["version"] == 2
        assert artifacts[1]["path"].endswith("v2.json")
