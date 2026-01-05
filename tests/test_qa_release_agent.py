"""Testes para o QA/Release Agent.

Verifica:
- Smoke tests funcionam com repo minimo
- Smoke tests funcionam com repo completo
- Checklist gera relatorio estruturado
- Bundle e gerado corretamente
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from release.qa_release_agent import (
    QAReleaseAgent,
    SmokeTestReport,
    SmokeTestResult,
    ChecklistReport,
    ChecklistItem,
)


# ==================== FIXTURES ====================


@pytest.fixture
def agent(tmp_path):
    """Agente com paths temporarios."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    return QAReleaseAgent(
        store_root=str(store_dir),
        generated_root=str(generated_dir),
    )


@pytest.fixture
def minimal_repo(tmp_path):
    """Repositorio minimo (apenas diretorio vazio)."""
    repo = tmp_path / "minimal_repo"
    repo.mkdir()
    return repo


@pytest.fixture
def complete_repo(tmp_path):
    """Repositorio completo com todas as estruturas."""
    repo = tmp_path / "complete_repo"
    repo.mkdir()

    # Backend
    backend = repo / "backend"
    backend.mkdir()
    (backend / "pom.xml").write_text("<project></project>")
    (backend / "src").mkdir()
    (backend / "src" / "main").mkdir()
    (backend / "src" / "main" / "java").mkdir()

    # Adicionar SecurityConfig.java
    security_config = backend / "src" / "main" / "java" / "SecurityConfig.java"
    security_config.write_text("public class SecurityConfig {}")

    # Frontend
    frontend = repo / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name": "test"}')
    (frontend / "src").mkdir()

    # Database
    database = repo / "database"
    database.mkdir()
    (database / "V1__init.sql").write_text("CREATE TABLE test;")

    # Docker
    (repo / "docker-compose.yml").write_text("version: '3'")

    # Docs
    (repo / "README.md").write_text("# Test Project")

    # Env
    (repo / ".env.example").write_text("DB_HOST=localhost")
    (repo / ".gitignore").write_text(".env\nnode_modules/")

    return repo


@pytest.fixture
def store_with_artifacts(tmp_path):
    """Store com artefatos de teste."""
    store = tmp_path / "artifact_store"
    store.mkdir()

    project_dir = store / "test_project"
    project_dir.mkdir()

    # SRS
    srs_dir = project_dir / "SRS"
    srs_dir.mkdir()
    (srs_dir / "v1.json").write_text('{"version": 1}')
    (srs_dir / "v2.json").write_text('{"version": 2}')

    # IR
    ir_dir = project_dir / "IR"
    ir_dir.mkdir()
    (ir_dir / "v1.json").write_text('{"version": 1}')

    # OAS
    oas_dir = project_dir / "OAS"
    oas_dir.mkdir()
    (oas_dir / "v1.yaml").write_text("openapi: 3.0.0")

    # RBAC
    rbac_dir = project_dir / "RBAC"
    rbac_dir.mkdir()
    (rbac_dir / "v1.json").write_text('{"version": 1}')

    # PLAN
    plan_dir = project_dir / "PLAN"
    plan_dir.mkdir()
    (plan_dir / "v1.json").write_text('{"version": 1}')

    return store


# ==================== TESTS: SMOKE TESTS ====================


class TestSmokeTests:
    """Testes do metodo run_smoke."""

    def test_smoke_returns_dict(self, agent, minimal_repo):
        """run_smoke deve retornar dicionario."""
        result = agent.run_smoke(str(minimal_repo))
        assert isinstance(result, dict)

    def test_smoke_has_required_fields(self, agent, minimal_repo):
        """Resultado deve ter campos obrigatorios."""
        result = agent.run_smoke(str(minimal_repo))

        assert "repo_path" in result
        assert "timestamp" in result
        assert "total_tests" in result
        assert "passed" in result
        assert "failed" in result
        assert "skipped" in result
        assert "results" in result
        assert "overall_status" in result
        assert "duration_ms" in result

    def test_smoke_with_minimal_repo(self, agent, minimal_repo):
        """Smoke tests devem funcionar com repo minimo."""
        result = agent.run_smoke(str(minimal_repo))

        # Repo minimo deve passar em alguns testes
        assert result["total_tests"] > 0
        assert result["repo_path"] == str(minimal_repo)

    def test_smoke_with_nonexistent_repo(self, agent, tmp_path):
        """Smoke tests devem lidar com repo inexistente."""
        nonexistent = tmp_path / "nonexistent"
        result = agent.run_smoke(str(nonexistent))

        # Deve falhar graciosamente
        assert result["passed"] == 0
        assert result["overall_status"] in ["failed", "skipped"]

    def test_smoke_with_complete_repo(self, agent, complete_repo):
        """Smoke tests devem passar com repo completo."""
        result = agent.run_smoke(str(complete_repo))

        # Repo completo deve ter mais passes
        assert result["passed"] >= 5  # directory, structure, backend, frontend, database, docker

    def test_smoke_results_have_names(self, agent, minimal_repo):
        """Cada resultado deve ter nome."""
        result = agent.run_smoke(str(minimal_repo))

        for r in result["results"]:
            assert "name" in r
            assert r["name"] != ""

    def test_smoke_results_have_passed_flag(self, agent, minimal_repo):
        """Cada resultado deve ter flag passed."""
        result = agent.run_smoke(str(minimal_repo))

        for r in result["results"]:
            assert "passed" in r
            assert isinstance(r["passed"], bool)

    def test_smoke_results_have_message(self, agent, minimal_repo):
        """Cada resultado deve ter mensagem."""
        result = agent.run_smoke(str(minimal_repo))

        for r in result["results"]:
            assert "message" in r

    def test_smoke_counts_are_consistent(self, agent, complete_repo):
        """Contagens devem ser consistentes."""
        result = agent.run_smoke(str(complete_repo))

        total = result["passed"] + result["failed"] + result["skipped"]
        assert total == result["total_tests"]


# ==================== TESTS: CHECKLIST ====================


class TestChecklist:
    """Testes do metodo run_checklist."""

    def test_checklist_returns_dict(self, agent, minimal_repo):
        """run_checklist deve retornar dicionario."""
        result = agent.run_checklist(str(minimal_repo))
        assert isinstance(result, dict)

    def test_checklist_has_required_fields(self, agent, minimal_repo):
        """Resultado deve ter campos obrigatorios."""
        result = agent.run_checklist(str(minimal_repo))

        assert "repo_path" in result
        assert "timestamp" in result
        assert "items" in result
        assert "ready_for_release" in result
        assert "blocking_issues" in result
        assert "warnings" in result

    def test_checklist_with_minimal_repo(self, agent, minimal_repo):
        """Checklist deve funcionar com repo minimo."""
        result = agent.run_checklist(str(minimal_repo))

        # Repo minimo provavelmente nao esta pronto para release
        assert result["repo_path"] == str(minimal_repo)
        assert isinstance(result["items"], list)

    def test_checklist_with_nonexistent_repo(self, agent, tmp_path):
        """Checklist deve lidar com repo inexistente."""
        nonexistent = tmp_path / "nonexistent"
        result = agent.run_checklist(str(nonexistent))

        assert result["ready_for_release"] is False
        assert len(result["blocking_issues"]) > 0

    def test_checklist_with_complete_repo(self, agent, complete_repo):
        """Checklist deve passar com repo completo."""
        result = agent.run_checklist(str(complete_repo))

        # Repo completo pode estar pronto (ou ter apenas warnings)
        # Verificar que passou mais verificacoes
        ok_items = [i for i in result["items"] if i["status"] == "ok"]
        assert len(ok_items) >= 5

    def test_checklist_items_have_id(self, agent, minimal_repo):
        """Cada item deve ter ID."""
        result = agent.run_checklist(str(minimal_repo))

        for item in result["items"]:
            assert "id" in item
            assert item["id"] != ""

    def test_checklist_items_have_category(self, agent, minimal_repo):
        """Cada item deve ter categoria."""
        result = agent.run_checklist(str(minimal_repo))

        for item in result["items"]:
            assert "category" in item
            assert item["category"] in ["structure", "configuration", "security", "documentation", "build"]

    def test_checklist_items_have_status(self, agent, minimal_repo):
        """Cada item deve ter status."""
        result = agent.run_checklist(str(minimal_repo))

        for item in result["items"]:
            assert "status" in item
            assert item["status"] in ["ok", "warning", "error", "skipped"]

    def test_checklist_blocking_issues_from_required_errors(self, agent, minimal_repo):
        """Issues bloqueantes devem vir de erros em items required."""
        result = agent.run_checklist(str(minimal_repo))

        # Verificar que blocking issues existem
        for issue in result["blocking_issues"]:
            # Deve ter formato [ID] message
            assert "[" in issue and "]" in issue

    def test_checklist_ready_when_no_blocking_issues(self, agent, complete_repo):
        """ready_for_release deve ser True quando nao ha blocking issues."""
        result = agent.run_checklist(str(complete_repo))

        if len(result["blocking_issues"]) == 0:
            assert result["ready_for_release"] is True


# ==================== TESTS: EMIT RELEASE BUNDLE ====================


class TestEmitReleaseBundle:
    """Testes do metodo emit_release_bundle."""

    def test_bundle_returns_path(self, store_with_artifacts, tmp_path):
        """emit_release_bundle deve retornar caminho."""
        generated = tmp_path / "gen_for_bundle"
        generated.mkdir()

        agent = QAReleaseAgent(
            store_root=str(store_with_artifacts),
            generated_root=str(generated),
        )

        # Criar projeto gerado
        project_dir = generated / "test_project"
        project_dir.mkdir()
        (project_dir / "backend").mkdir()
        (project_dir / "backend" / "pom.xml").write_text("<project/>")

        result = agent.emit_release_bundle("test_project")

        assert isinstance(result, str)
        assert result.endswith(".zip")

    def test_bundle_creates_zip_file(self, store_with_artifacts, tmp_path):
        """Bundle deve criar arquivo zip."""
        generated = tmp_path / "gen_zip"
        generated.mkdir()

        agent = QAReleaseAgent(
            store_root=str(store_with_artifacts),
            generated_root=str(generated),
        )

        # Criar projeto minimo
        project_dir = generated / "test_project"
        project_dir.mkdir()

        result = agent.emit_release_bundle("test_project")

        assert Path(result).exists()

    def test_bundle_includes_metadata(self, store_with_artifacts, tmp_path):
        """Bundle deve incluir metadata."""
        generated = tmp_path / "gen_meta"
        generated.mkdir()

        agent = QAReleaseAgent(
            store_root=str(store_with_artifacts),
            generated_root=str(generated),
        )

        project_dir = generated / "test_project"
        project_dir.mkdir()

        agent.emit_release_bundle("test_project")

        # Verificar que metadata foi criada no diretorio do bundle
        releases_dir = store_with_artifacts / "test_project" / "releases"
        assert releases_dir.exists()

        # Encontrar o bundle mais recente
        bundles = [d for d in releases_dir.iterdir() if d.is_dir()]
        assert len(bundles) > 0

        metadata_path = bundles[0] / "release_metadata.json"
        assert metadata_path.exists()

        with open(metadata_path) as f:
            metadata = json.load(f)

        assert "project" in metadata
        assert "created_at" in metadata
        assert "generator" in metadata

    def test_bundle_copies_artifacts(self, store_with_artifacts, tmp_path):
        """Bundle deve copiar artefatos."""
        generated = tmp_path / "gen_artifacts"
        generated.mkdir()

        agent = QAReleaseAgent(
            store_root=str(store_with_artifacts),
            generated_root=str(generated),
        )

        project_dir = generated / "test_project"
        project_dir.mkdir()

        agent.emit_release_bundle("test_project")

        # Verificar que artefatos foram copiados
        releases_dir = store_with_artifacts / "test_project" / "releases"
        bundles = [d for d in releases_dir.iterdir() if d.is_dir()]
        artifacts_dir = bundles[0] / "artifacts"

        assert artifacts_dir.exists()
        # Deve ter pelo menos alguns artefatos
        artifacts = list(artifacts_dir.iterdir())
        assert len(artifacts) > 0


# ==================== TESTS: DATACLASSES ====================


class TestSmokeTestResult:
    """Testes do SmokeTestResult."""

    def test_to_dict(self):
        """to_dict deve converter corretamente."""
        result = SmokeTestResult(
            name="test_name",
            passed=True,
            message="Test passed",
            duration_ms=100.5,
            details={"key": "value"},
        )

        d = result.to_dict()

        assert d["name"] == "test_name"
        assert d["passed"] is True
        assert d["message"] == "Test passed"
        assert d["duration_ms"] == 100.5
        assert d["details"] == {"key": "value"}


class TestSmokeTestReport:
    """Testes do SmokeTestReport."""

    def test_to_dict(self):
        """to_dict deve converter corretamente."""
        report = SmokeTestReport(
            repo_path="/path/to/repo",
            timestamp="2024-01-01T00:00:00",
            total_tests=3,
            passed=2,
            failed=1,
            skipped=0,
            results=[
                SmokeTestResult(name="t1", passed=True, message="ok"),
            ],
            overall_status="passed",
            duration_ms=500.0,
        )

        d = report.to_dict()

        assert d["repo_path"] == "/path/to/repo"
        assert d["total_tests"] == 3
        assert len(d["results"]) == 1


class TestChecklistItem:
    """Testes do ChecklistItem."""

    def test_to_dict(self):
        """to_dict deve converter corretamente."""
        item = ChecklistItem(
            id="TEST-001",
            category="test",
            description="Test item",
            status="ok",
            message="Passed",
            required=True,
            details={"extra": "info"},
        )

        d = item.to_dict()

        assert d["id"] == "TEST-001"
        assert d["category"] == "test"
        assert d["status"] == "ok"
        assert d["required"] is True


class TestChecklistReport:
    """Testes do ChecklistReport."""

    def test_to_dict(self):
        """to_dict deve converter corretamente."""
        report = ChecklistReport(
            repo_path="/path/to/repo",
            timestamp="2024-01-01T00:00:00",
            items=[
                ChecklistItem(id="T1", category="test", description="d", status="ok", message="m"),
            ],
            ready_for_release=True,
            blocking_issues=[],
            warnings=["minor issue"],
        )

        d = report.to_dict()

        assert d["ready_for_release"] is True
        assert len(d["items"]) == 1
        assert len(d["warnings"]) == 1


# ==================== TESTS: EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos limite."""

    def test_smoke_with_empty_subdirs(self, agent, tmp_path):
        """Smoke deve funcionar com subdiretorios vazios."""
        repo = tmp_path / "empty_subdirs"
        repo.mkdir()
        (repo / "backend").mkdir()
        (repo / "frontend").mkdir()

        result = agent.run_smoke(str(repo))

        assert result["total_tests"] > 0

    def test_checklist_with_partial_structure(self, agent, tmp_path):
        """Checklist deve funcionar com estrutura parcial."""
        repo = tmp_path / "partial"
        repo.mkdir()
        (repo / "backend").mkdir()
        (repo / "backend" / "pom.xml").write_text("<project/>")

        result = agent.run_checklist(str(repo))

        # Deve ter items ok e error/warning
        statuses = [i["status"] for i in result["items"]]
        assert "ok" in statuses or "warning" in statuses

    def test_bundle_with_no_artifacts(self, tmp_path):
        """Bundle deve funcionar sem artefatos."""
        store = tmp_path / "empty_store"
        store.mkdir()
        (store / "empty_project").mkdir()

        generated = tmp_path / "gen_dir"
        generated.mkdir()

        agent = QAReleaseAgent(
            store_root=str(store),
            generated_root=str(generated),
        )

        result = agent.emit_release_bundle("empty_project")

        # Deve criar bundle mesmo sem artefatos
        assert Path(result).exists()

    def test_smoke_handles_permission_errors(self, agent, tmp_path):
        """Smoke deve lidar com erros de permissao."""
        repo = tmp_path / "no_access"
        repo.mkdir()

        # Simular que o diretorio existe mas tem problemas
        result = agent.run_smoke(str(repo))

        # Deve retornar resultado estruturado
        assert "results" in result

    def test_checklist_categories_coverage(self, agent, complete_repo):
        """Checklist deve cobrir todas as categorias."""
        result = agent.run_checklist(str(complete_repo))

        categories = {i["category"] for i in result["items"]}

        assert "structure" in categories
        assert "configuration" in categories
        assert "security" in categories
        assert "documentation" in categories
        assert "build" in categories


# ==================== TESTS: AGENT INITIALIZATION ====================


class TestAgentInitialization:
    """Testes de inicializacao do agente."""

    def test_default_paths(self):
        """Agente deve usar paths padrao."""
        agent = QAReleaseAgent()

        assert agent.store_root == Path(QAReleaseAgent.DEFAULT_STORE_ROOT)
        assert agent.generated_root == Path(QAReleaseAgent.DEFAULT_GENERATED_ROOT)

    def test_custom_paths(self, tmp_path):
        """Agente deve aceitar paths customizados."""
        store = tmp_path / "store"
        generated = tmp_path / "gen"

        agent = QAReleaseAgent(
            store_root=str(store),
            generated_root=str(generated),
        )

        assert agent.store_root == store
        assert agent.generated_root == generated


# ==================== TESTS: REPORT STRUCTURE FOR MINIMAL REPO ====================


class TestMinimalRepoReport:
    """Testes de relatorio com repo minimo (criterio de aceite)."""

    def test_smoke_generates_structured_report_for_minimal(self, agent, tmp_path):
        """Smoke deve gerar relatorio estruturado mesmo com repo minimo."""
        minimal = tmp_path / "minimal"
        minimal.mkdir()

        result = agent.run_smoke(str(minimal))

        # Deve ter estrutura completa
        assert "repo_path" in result
        assert "timestamp" in result
        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) > 0

        # Cada resultado deve ser estruturado
        for r in result["results"]:
            assert "name" in r
            assert "passed" in r
            assert "message" in r

    def test_checklist_generates_structured_report_for_minimal(self, agent, tmp_path):
        """Checklist deve gerar relatorio estruturado mesmo com repo minimo."""
        minimal = tmp_path / "minimal"
        minimal.mkdir()

        result = agent.run_checklist(str(minimal))

        # Deve ter estrutura completa
        assert "repo_path" in result
        assert "timestamp" in result
        assert "items" in result
        assert isinstance(result["items"], list)
        assert len(result["items"]) > 0

        # Cada item deve ser estruturado
        for i in result["items"]:
            assert "id" in i
            assert "category" in i
            assert "status" in i
            assert "message" in i

    def test_report_is_json_serializable(self, agent, tmp_path):
        """Relatorios devem ser serializaveis para JSON."""
        minimal = tmp_path / "minimal"
        minimal.mkdir()

        smoke = agent.run_smoke(str(minimal))
        checklist = agent.run_checklist(str(minimal))

        # Nao deve lancar excecao
        json.dumps(smoke)
        json.dumps(checklist)
