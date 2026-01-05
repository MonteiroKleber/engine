"""Testes para o Smoke Runner.

Verifica:
- Smoke tests funcionam com repo minimo
- Backend: healthcheck config, CRUD endpoints
- Frontend: build, main route
- Artefatos sao salvos em /generated/<project>/smoke/
- Retorna PASS/FAIL corretamente
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from release.smoke_runner import (
    SmokeRunner,
    LiveSmokeRunner,
    SmokeReport,
    SmokeResult,
    run_smoke,
)


# ==================== FIXTURES ====================


@pytest.fixture
def runner(tmp_path):
    """Runner com paths temporarios."""
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir(exist_ok=True)
    return SmokeRunner(generated_root=str(generated_dir))


@pytest.fixture
def minimal_project(tmp_path):
    """Projeto minimo (apenas diretorio vazio)."""
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    project = generated / "minimal"
    project.mkdir(exist_ok=True)
    return project


@pytest.fixture
def backend_project(tmp_path):
    """Projeto com backend estruturado."""
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    project = generated / "backend_project"
    project.mkdir(exist_ok=True)

    # Backend
    backend = project / "backend"
    backend.mkdir()
    (backend / "pom.xml").write_text("""
        <project>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-actuator</artifactId>
                </dependency>
            </dependencies>
        </project>
    """)

    # src/main/java structure
    src_main = backend / "src" / "main" / "java" / "com" / "example"
    src_main.mkdir(parents=True)

    # Controller
    (src_main / "UserController.java").write_text("""
        @RestController
        @RequestMapping("/api/users")
        public class UserController {
            @GetMapping
            public List<User> list() {
                return userService.findAll();
            }
        }
    """)

    return project


@pytest.fixture
def frontend_project(tmp_path):
    """Projeto com frontend estruturado."""
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    project = generated / "frontend_project"
    project.mkdir(exist_ok=True)

    # Frontend
    frontend = project / "frontend"
    frontend.mkdir(exist_ok=True)
    (frontend / "package.json").write_text('{"name": "test", "scripts": {"build": "echo ok"}}')

    # src structure
    src = frontend / "src"
    src.mkdir(exist_ok=True)
    (src / "App.tsx").write_text("""
        export default function App() {
            return <div>Hello</div>;
        }
    """)

    return project


@pytest.fixture
def complete_project(tmp_path):
    """Projeto completo com backend e frontend."""
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    project = generated / "complete"
    project.mkdir(exist_ok=True)

    # Backend
    backend = project / "backend"
    backend.mkdir(exist_ok=True)
    (backend / "pom.xml").write_text("""
        <project>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-actuator</artifactId>
                </dependency>
            </dependencies>
        </project>
    """)

    src_main = backend / "src" / "main" / "java" / "com" / "example"
    src_main.mkdir(parents=True)
    (src_main / "ProductController.java").write_text("""
        @RestController
        @RequestMapping("/api/products")
        public class ProductController {
            @GetMapping
            public List<Product> list() {
                return service.findAll();
            }
        }
    """)

    # Frontend
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name": "test", "scripts": {"build": "echo ok"}}')
    src = frontend / "src"
    src.mkdir()
    (src / "App.tsx").write_text("export default function App() { return <div>App</div>; }")

    return project


# ==================== TESTS: SMOKE RESULT ====================


class TestSmokeResult:
    """Testes do SmokeResult."""

    def test_to_dict(self):
        """to_dict deve converter corretamente."""
        result = SmokeResult(
            name="test_name",
            category="backend",
            status="PASS",
            message="Test passed",
            duration_ms=100.5,
            details={"key": "value"},
        )

        d = result.to_dict()

        assert d["name"] == "test_name"
        assert d["category"] == "backend"
        assert d["status"] == "PASS"
        assert d["message"] == "Test passed"
        assert d["duration_ms"] == 100.5
        assert d["details"] == {"key": "value"}

    def test_default_values(self):
        """Valores default devem funcionar."""
        result = SmokeResult(
            name="test",
            category="frontend",
            status="FAIL",
            message="Failed",
        )

        assert result.duration_ms == 0.0
        assert result.details == {}


# ==================== TESTS: SMOKE REPORT ====================


class TestSmokeReport:
    """Testes do SmokeReport."""

    def test_to_dict(self):
        """to_dict deve converter corretamente."""
        report = SmokeReport(
            project="test",
            repo_path="/path/to/repo",
            timestamp="2024-01-01T00:00:00",
        )

        d = report.to_dict()

        assert d["project"] == "test"
        assert d["repo_path"] == "/path/to/repo"
        assert d["total_tests"] == 0
        assert d["overall_status"] == "UNKNOWN"

    def test_add_result_updates_counters(self):
        """add_result deve atualizar contadores."""
        report = SmokeReport(
            project="test",
            repo_path="/path",
            timestamp="now",
        )

        report.add_result(SmokeResult("t1", "backend", "PASS", "ok"))
        assert report.total_tests == 1
        assert report.passed == 1

        report.add_result(SmokeResult("t2", "backend", "FAIL", "fail"))
        assert report.total_tests == 2
        assert report.failed == 1

        report.add_result(SmokeResult("t3", "backend", "SKIP", "skip"))
        assert report.total_tests == 3
        assert report.skipped == 1

    def test_finalize_pass(self):
        """finalize deve definir PASS quando todos passam."""
        report = SmokeReport(project="test", repo_path="/path", timestamp="now")
        report.add_result(SmokeResult("t1", "backend", "PASS", "ok"))
        report.add_result(SmokeResult("t2", "frontend", "PASS", "ok"))

        report.finalize()

        assert report.overall_status == "PASS"

    def test_finalize_fail(self):
        """finalize deve definir FAIL quando ha falhas."""
        report = SmokeReport(project="test", repo_path="/path", timestamp="now")
        report.add_result(SmokeResult("t1", "backend", "PASS", "ok"))
        report.add_result(SmokeResult("t2", "frontend", "FAIL", "fail"))

        report.finalize()

        assert report.overall_status == "FAIL"

    def test_finalize_partial(self):
        """finalize deve definir PARTIAL quando ha skips."""
        report = SmokeReport(project="test", repo_path="/path", timestamp="now")
        report.add_result(SmokeResult("t1", "backend", "PASS", "ok"))
        report.add_result(SmokeResult("t2", "frontend", "SKIP", "skip"))

        report.finalize()

        assert report.overall_status == "PARTIAL"


# ==================== TESTS: SMOKE RUNNER BASIC ====================


class TestSmokeRunnerBasic:
    """Testes basicos do SmokeRunner."""

    def test_default_paths(self):
        """Runner deve usar paths padrao."""
        runner = SmokeRunner()

        assert runner.generated_root == Path(SmokeRunner.DEFAULT_GENERATED_ROOT)
        assert runner.backend_port == SmokeRunner.DEFAULT_BACKEND_PORT
        assert runner.frontend_port == SmokeRunner.DEFAULT_FRONTEND_PORT

    def test_custom_paths(self, tmp_path):
        """Runner deve aceitar paths customizados."""
        runner = SmokeRunner(
            generated_root=str(tmp_path),
            backend_port=9090,
            frontend_port=4000,
        )

        assert runner.generated_root == tmp_path
        assert runner.backend_port == 9090
        assert runner.frontend_port == 4000


# ==================== TESTS: RUN SMOKE TESTS ====================


class TestRunSmokeTests:
    """Testes do metodo run_smoke_tests."""

    def test_returns_smoke_report(self, runner, minimal_project):
        """Deve retornar SmokeReport."""
        runner.generated_root = minimal_project.parent

        result = runner.run_smoke_tests("minimal")

        assert isinstance(result, SmokeReport)

    def test_nonexistent_project_fails(self, runner):
        """Projeto inexistente deve falhar."""
        result = runner.run_smoke_tests("nonexistent")

        assert result.overall_status == "FAIL"
        assert any(r.name == "project_exists" and r.status == "FAIL" for r in result.results)

    def test_minimal_project_has_results(self, runner, minimal_project):
        """Projeto minimo deve ter resultados."""
        runner.generated_root = minimal_project.parent

        result = runner.run_smoke_tests("minimal")

        assert result.total_tests > 0
        assert len(result.results) > 0

    def test_saves_artifacts(self, runner, minimal_project):
        """Deve salvar artefatos em smoke/."""
        runner.generated_root = minimal_project.parent

        result = runner.run_smoke_tests("minimal")

        smoke_dir = minimal_project / "smoke"
        assert smoke_dir.exists()
        assert result.artifacts_path == str(smoke_dir)

        # Verificar que arquivo de relatorio existe
        report_files = list(smoke_dir.glob("smoke_report_*.json"))
        assert len(report_files) > 0

        # Verificar que summary existe
        summary_file = smoke_dir / "latest_summary.txt"
        assert summary_file.exists()

    def test_skip_backend(self, runner, backend_project):
        """Deve pular testes de backend quando solicitado."""
        runner.generated_root = backend_project.parent

        result = runner.run_smoke_tests("backend_project", skip_backend=True)

        backend_results = [r for r in result.results if r.category == "backend"]
        assert len(backend_results) == 0

    def test_skip_frontend(self, runner, frontend_project):
        """Deve pular testes de frontend quando solicitado."""
        runner.generated_root = frontend_project.parent

        result = runner.run_smoke_tests("frontend_project", skip_frontend=True)

        frontend_results = [r for r in result.results if r.category == "frontend"]
        assert len(frontend_results) == 0


# ==================== TESTS: BACKEND SMOKE ====================


class TestBackendSmoke:
    """Testes de smoke do backend."""

    def test_backend_exists_pass(self, runner, backend_project):
        """Deve passar quando backend existe."""
        runner.generated_root = backend_project.parent

        result = runner.run_smoke_tests("backend_project", skip_frontend=True)

        backend_exists = next((r for r in result.results if r.name == "backend_exists"), None)
        assert backend_exists is not None
        assert backend_exists.status == "PASS"

    def test_backend_exists_skip(self, runner, minimal_project):
        """Deve skipar quando backend nao existe."""
        runner.generated_root = minimal_project.parent

        result = runner.run_smoke_tests("minimal", skip_frontend=True)

        backend_exists = next((r for r in result.results if r.name == "backend_exists"), None)
        assert backend_exists is not None
        assert backend_exists.status == "SKIP"

    def test_healthcheck_configured_pass(self, runner, backend_project):
        """Deve passar quando actuator esta configurado."""
        runner.generated_root = backend_project.parent

        # Mock compile para passar e testar o healthcheck
        with patch.object(runner, "_test_backend_compiles") as mock_compile:
            mock_compile.return_value = SmokeResult("backend_compiles", "backend", "PASS", "ok")
            result = runner.run_smoke_tests("backend_project", skip_frontend=True)

        healthcheck = next((r for r in result.results if r.name == "healthcheck_configured"), None)
        assert healthcheck is not None
        assert healthcheck.status == "PASS"
        assert "/actuator/health" in healthcheck.message

    def test_healthcheck_configured_fail(self, tmp_path):
        """Deve falhar quando actuator nao esta configurado."""
        generated = tmp_path / "generated"
        generated.mkdir(exist_ok=True)
        project = generated / "no_actuator"
        project.mkdir(exist_ok=True)

        backend = project / "backend"
        backend.mkdir(exist_ok=True)
        (backend / "pom.xml").write_text("<project></project>")

        runner = SmokeRunner(generated_root=str(generated))

        # Mock compile para passar e testar o healthcheck
        with patch.object(runner, "_test_backend_compiles") as mock_compile:
            mock_compile.return_value = SmokeResult("backend_compiles", "backend", "PASS", "ok")
            result = runner.run_smoke_tests("no_actuator", skip_frontend=True)

        healthcheck = next((r for r in result.results if r.name == "healthcheck_configured"), None)
        assert healthcheck is not None
        assert healthcheck.status == "FAIL"

    def test_crud_endpoint_pass(self, runner, backend_project):
        """Deve passar quando controller existe."""
        runner.generated_root = backend_project.parent

        # Mock compile para passar e testar o CRUD
        with patch.object(runner, "_test_backend_compiles") as mock_compile:
            mock_compile.return_value = SmokeResult("backend_compiles", "backend", "PASS", "ok")
            result = runner.run_smoke_tests("backend_project", entities=["User"], skip_frontend=True)

        crud = next((r for r in result.results if r.name == "crud_endpoint_user"), None)
        assert crud is not None
        assert crud.status == "PASS"

    def test_crud_endpoint_fail(self, runner, backend_project):
        """Deve falhar quando controller nao existe."""
        runner.generated_root = backend_project.parent

        # Mock compile para passar e testar o CRUD
        with patch.object(runner, "_test_backend_compiles") as mock_compile:
            mock_compile.return_value = SmokeResult("backend_compiles", "backend", "PASS", "ok")
            result = runner.run_smoke_tests("backend_project", entities=["NonExistent"], skip_frontend=True)

        crud = next((r for r in result.results if r.name == "crud_endpoint_nonexistent"), None)
        assert crud is not None
        assert crud.status == "FAIL"


# ==================== TESTS: FRONTEND SMOKE ====================


class TestFrontendSmoke:
    """Testes de smoke do frontend."""

    def test_frontend_exists_pass(self, runner, frontend_project):
        """Deve passar quando frontend existe."""
        runner.generated_root = frontend_project.parent

        result = runner.run_smoke_tests("frontend_project", skip_backend=True)

        frontend_exists = next((r for r in result.results if r.name == "frontend_exists"), None)
        assert frontend_exists is not None
        assert frontend_exists.status == "PASS"

    def test_frontend_exists_skip(self, runner, minimal_project):
        """Deve skipar quando frontend nao existe."""
        runner.generated_root = minimal_project.parent

        result = runner.run_smoke_tests("minimal", skip_backend=True)

        frontend_exists = next((r for r in result.results if r.name == "frontend_exists"), None)
        assert frontend_exists is not None
        assert frontend_exists.status == "SKIP"

    def test_package_json_pass(self, runner, frontend_project):
        """Deve passar quando package.json existe."""
        runner.generated_root = frontend_project.parent

        result = runner.run_smoke_tests("frontend_project", skip_backend=True)

        pkg = next((r for r in result.results if r.name == "package_json_exists"), None)
        assert pkg is not None
        assert pkg.status == "PASS"

    def test_main_route_pass(self, runner, frontend_project):
        """Deve passar quando App.tsx existe."""
        runner.generated_root = frontend_project.parent

        # Mock npm install e build para nao executar
        with patch.object(runner, "_test_npm_install") as mock_install, \
             patch.object(runner, "_test_npm_build") as mock_build:
            mock_install.return_value = SmokeResult("npm_install", "frontend", "PASS", "ok")
            mock_build.return_value = SmokeResult("npm_build", "frontend", "PASS", "ok")

            result = runner.run_smoke_tests("frontend_project", skip_backend=True)

        main_route = next((r for r in result.results if r.name == "main_route_exists"), None)
        assert main_route is not None
        assert main_route.status == "PASS"

    def test_main_route_fail(self, tmp_path):
        """Deve falhar quando main route nao existe."""
        generated = tmp_path / "generated"
        generated.mkdir()
        project = generated / "no_route"
        project.mkdir()

        frontend = project / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text('{"name": "test"}')
        (frontend / "src").mkdir()

        runner = SmokeRunner(generated_root=str(generated))

        with patch.object(runner, "_test_npm_install") as mock_install, \
             patch.object(runner, "_test_npm_build") as mock_build:
            mock_install.return_value = SmokeResult("npm_install", "frontend", "PASS", "ok")
            mock_build.return_value = SmokeResult("npm_build", "frontend", "PASS", "ok")

            result = runner.run_smoke_tests("no_route", skip_backend=True)

        main_route = next((r for r in result.results if r.name == "main_route_exists"), None)
        assert main_route is not None
        assert main_route.status == "FAIL"


# ==================== TESTS: COMPLETE PROJECT ====================


class TestCompleteProject:
    """Testes com projeto completo."""

    def test_complete_project_has_all_categories(self, runner, complete_project):
        """Projeto completo deve ter resultados de todas as categorias."""
        runner.generated_root = complete_project.parent

        # Mock npm para nao executar
        with patch.object(runner, "_test_npm_install") as mock_install, \
             patch.object(runner, "_test_npm_build") as mock_build:
            mock_install.return_value = SmokeResult("npm_install", "frontend", "PASS", "ok")
            mock_build.return_value = SmokeResult("npm_build", "frontend", "PASS", "ok")

            result = runner.run_smoke_tests("complete", entities=["Product"])

        categories = {r.category for r in result.results}
        assert "backend" in categories
        assert "frontend" in categories

    def test_complete_project_saves_json_report(self, runner, complete_project):
        """Deve salvar relatorio JSON."""
        runner.generated_root = complete_project.parent

        with patch.object(runner, "_test_npm_install") as mock_install, \
             patch.object(runner, "_test_npm_build") as mock_build:
            mock_install.return_value = SmokeResult("npm_install", "frontend", "PASS", "ok")
            mock_build.return_value = SmokeResult("npm_build", "frontend", "PASS", "ok")

            result = runner.run_smoke_tests("complete")

        smoke_dir = complete_project / "smoke"
        report_files = list(smoke_dir.glob("smoke_report_*.json"))
        assert len(report_files) > 0

        with open(report_files[0]) as f:
            report_data = json.load(f)

        assert report_data["project"] == "complete"
        assert "results" in report_data


# ==================== TESTS: CONVENIENCE FUNCTION ====================


class TestConvenienceFunction:
    """Testes da funcao run_smoke."""

    def test_run_smoke_returns_dict(self, tmp_path):
        """run_smoke deve retornar dict."""
        generated = tmp_path / "generated"
        generated.mkdir()
        project = generated / "test"
        project.mkdir()

        with patch.object(SmokeRunner, "DEFAULT_GENERATED_ROOT", str(generated)):
            result = run_smoke("test")

        assert isinstance(result, dict)
        assert "project" in result
        assert "overall_status" in result


# ==================== TESTS: LIVE SMOKE RUNNER ====================


class TestLiveSmokeRunner:
    """Testes do LiveSmokeRunner."""

    def test_inherits_from_smoke_runner(self):
        """Deve herdar de SmokeRunner."""
        runner = LiveSmokeRunner()
        assert isinstance(runner, SmokeRunner)

    def test_run_live_without_requests(self, tmp_path):
        """Deve skipar quando requests nao esta instalado."""
        generated = tmp_path / "generated"
        generated.mkdir()
        project = generated / "test"
        project.mkdir()

        runner = LiveSmokeRunner(generated_root=str(generated))

        with patch("release.smoke_runner.HAS_REQUESTS", False):
            result = runner.run_live_smoke_tests("test")

        assert any(r.name == "requests_library" and r.status == "SKIP" for r in result.results)


# ==================== TESTS: PASS/FAIL ACCEPTANCE ====================


class TestPassFailAcceptance:
    """Testes do criterio de aceite: retorna PASS/FAIL."""

    def test_returns_pass_for_valid_project(self, runner, complete_project):
        """Deve retornar PASS para projeto valido."""
        runner.generated_root = complete_project.parent

        with patch.object(runner, "_test_npm_install") as mock_install, \
             patch.object(runner, "_test_npm_build") as mock_build, \
             patch.object(runner, "_test_backend_compiles") as mock_compile:
            mock_install.return_value = SmokeResult("npm_install", "frontend", "PASS", "ok")
            mock_build.return_value = SmokeResult("npm_build", "frontend", "PASS", "ok")
            mock_compile.return_value = SmokeResult("backend_compiles", "backend", "PASS", "ok")

            result = runner.run_smoke_tests("complete")

        assert result.overall_status in ["PASS", "PARTIAL"]

    def test_returns_fail_for_invalid_project(self, runner):
        """Deve retornar FAIL para projeto invalido."""
        result = runner.run_smoke_tests("nonexistent")

        assert result.overall_status == "FAIL"

    def test_status_is_in_report_dict(self, runner, minimal_project):
        """overall_status deve estar no dict do relatorio."""
        runner.generated_root = minimal_project.parent

        result = runner.run_smoke_tests("minimal")
        report_dict = result.to_dict()

        assert "overall_status" in report_dict
        assert report_dict["overall_status"] in ["PASS", "FAIL", "PARTIAL", "SKIP"]
