"""Smoke Test Runner - Executa smoke tests em projetos gerados.

Este modulo executa testes de smoke para:
1. Backend: healthcheck e CRUD basico
2. Frontend: build e renderizacao

Artefatos sao salvos em: /home/bazari/generated/<project>/smoke/

REGRA: Smoke executa localmente e retorna PASS/FAIL.
"""

import json
import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


@dataclass
class SmokeResult:
    """Resultado de um smoke test individual."""

    name: str
    category: str  # "backend", "frontend", "infrastructure"
    status: str  # "PASS", "FAIL", "SKIP"
    message: str
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


@dataclass
class SmokeReport:
    """Relatorio completo de smoke tests."""

    project: str
    repo_path: str
    timestamp: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[SmokeResult] = field(default_factory=list)
    overall_status: str = "UNKNOWN"  # "PASS", "FAIL", "PARTIAL"
    duration_ms: float = 0.0
    artifacts_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "project": self.project,
            "repo_path": self.repo_path,
            "timestamp": self.timestamp,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "overall_status": self.overall_status,
            "duration_ms": self.duration_ms,
            "artifacts_path": self.artifacts_path,
        }

    def add_result(self, result: SmokeResult) -> None:
        """Adiciona resultado e atualiza contadores."""
        self.results.append(result)
        self.total_tests += 1
        if result.status == "PASS":
            self.passed += 1
        elif result.status == "FAIL":
            self.failed += 1
        else:
            self.skipped += 1

    def finalize(self) -> None:
        """Finaliza o relatorio calculando status geral."""
        if self.failed > 0:
            self.overall_status = "FAIL"
        elif self.passed > 0 and self.skipped > 0:
            self.overall_status = "PARTIAL"
        elif self.passed > 0:
            self.overall_status = "PASS"
        else:
            self.overall_status = "SKIP"


class SmokeRunner:
    """Executa smoke tests em projetos gerados.

    Smoke tests verificam:
    - Backend: healthcheck e endpoints CRUD
    - Frontend: build e renderizacao

    Attributes:
        generated_root: Diretorio raiz dos projetos gerados
        backend_port: Porta para o backend (default: 8080)
        frontend_port: Porta para o frontend (default: 3000)
        timeout: Timeout em segundos para cada teste
    """

    DEFAULT_GENERATED_ROOT = "/home/bazari/generated"
    DEFAULT_BACKEND_PORT = 8080
    DEFAULT_FRONTEND_PORT = 5173  # Mapeado no docker-compose: 5173:80
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        generated_root: Optional[str] = None,
        backend_port: int = DEFAULT_BACKEND_PORT,
        frontend_port: int = DEFAULT_FRONTEND_PORT,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Inicializa o runner.

        Args:
            generated_root: Diretorio raiz dos projetos gerados
            backend_port: Porta para o backend
            frontend_port: Porta para o frontend
            timeout: Timeout em segundos
        """
        self.generated_root = Path(generated_root or self.DEFAULT_GENERATED_ROOT)
        self.backend_port = backend_port
        self.frontend_port = frontend_port
        self.timeout = timeout

    def run_smoke_tests(
        self,
        project: str,
        entities: Optional[List[str]] = None,
        skip_backend: bool = False,
        skip_frontend: bool = False,
    ) -> SmokeReport:
        """Executa todos os smoke tests para um projeto.

        Args:
            project: Nome do projeto
            entities: Lista de entidades para testar CRUD (opcional)
            skip_backend: Pular testes de backend
            skip_frontend: Pular testes de frontend

        Returns:
            SmokeReport com resultados
        """
        start_time = datetime.now()
        repo_path = self.generated_root / project

        report = SmokeReport(
            project=project,
            repo_path=str(repo_path),
            timestamp=datetime.now().isoformat(),
        )

        # Verificar se o projeto existe
        if not repo_path.exists():
            report.add_result(SmokeResult(
                name="project_exists",
                category="infrastructure",
                status="FAIL",
                message=f"Project directory not found: {repo_path}",
            ))
            report.finalize()
            return report

        # Backend tests
        if not skip_backend:
            backend_results = self._run_backend_smoke(repo_path, entities)
            for result in backend_results:
                report.add_result(result)

        # Frontend tests
        if not skip_frontend:
            frontend_results = self._run_frontend_smoke(repo_path)
            for result in frontend_results:
                report.add_result(result)

        # Calcular duracao e finalizar
        report.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        report.finalize()

        # Salvar artefatos
        artifacts_path = self._save_smoke_artifacts(project, report)
        report.artifacts_path = artifacts_path

        return report

    def _run_backend_smoke(
        self,
        repo_path: Path,
        entities: Optional[List[str]] = None,
    ) -> List[SmokeResult]:
        """Executa smoke tests do backend.

        Args:
            repo_path: Caminho do repositorio
            entities: Lista de entidades para testar

        Returns:
            Lista de resultados
        """
        results: List[SmokeResult] = []
        backend_path = repo_path / "backend"

        # Test 1: Backend directory exists
        if not backend_path.exists():
            results.append(SmokeResult(
                name="backend_exists",
                category="backend",
                status="SKIP",
                message="Backend directory not found",
            ))
            return results

        results.append(SmokeResult(
            name="backend_exists",
            category="backend",
            status="PASS",
            message="Backend directory exists",
        ))

        # Test 2: Backend compiles
        compile_result = self._test_backend_compiles(backend_path)
        results.append(compile_result)

        if compile_result.status != "PASS":
            # Se nao compila, nao faz sentido testar HTTP
            return results

        # Test 3: Healthcheck (sem servidor rodando, apenas verifica estrutura)
        healthcheck_result = self._test_healthcheck_config(backend_path)
        results.append(healthcheck_result)

        # Test 4: CRUD endpoints existem no codigo
        if entities:
            for entity in entities:
                crud_result = self._test_crud_endpoint_exists(backend_path, entity)
                results.append(crud_result)

        return results

    def _run_frontend_smoke(self, repo_path: Path) -> List[SmokeResult]:
        """Executa smoke tests do frontend.

        Args:
            repo_path: Caminho do repositorio

        Returns:
            Lista de resultados
        """
        results: List[SmokeResult] = []
        frontend_path = repo_path / "frontend"

        # Test 1: Frontend directory exists
        if not frontend_path.exists():
            results.append(SmokeResult(
                name="frontend_exists",
                category="frontend",
                status="SKIP",
                message="Frontend directory not found",
            ))
            return results

        results.append(SmokeResult(
            name="frontend_exists",
            category="frontend",
            status="PASS",
            message="Frontend directory exists",
        ))

        # Test 2: package.json exists
        package_json = frontend_path / "package.json"
        if not package_json.exists():
            results.append(SmokeResult(
                name="package_json_exists",
                category="frontend",
                status="FAIL",
                message="package.json not found",
            ))
            return results

        results.append(SmokeResult(
            name="package_json_exists",
            category="frontend",
            status="PASS",
            message="package.json exists",
        ))

        # Test 3: npm install
        install_result = self._test_npm_install(frontend_path)
        results.append(install_result)

        if install_result.status != "PASS":
            return results

        # Test 4: npm run build
        build_result = self._test_npm_build(frontend_path)
        results.append(build_result)

        # Test 5: Main route file exists
        route_result = self._test_main_route_exists(frontend_path)
        results.append(route_result)

        return results

    def _test_backend_compiles(self, backend_path: Path) -> SmokeResult:
        """Testa se o backend compila."""
        start_time = time.time()

        pom = backend_path / "pom.xml"
        if not pom.exists():
            return SmokeResult(
                name="backend_compiles",
                category="backend",
                status="SKIP",
                message="pom.xml not found - not a Maven project",
            )

        try:
            result = subprocess.run(
                ["mvn", "compile", "-q", "-DskipTests"],
                cwd=backend_path,
                capture_output=True,
                timeout=120,
            )
            duration_ms = (time.time() - start_time) * 1000

            if result.returncode == 0:
                return SmokeResult(
                    name="backend_compiles",
                    category="backend",
                    status="PASS",
                    message="Backend compiles successfully",
                    duration_ms=duration_ms,
                )
            return SmokeResult(
                name="backend_compiles",
                category="backend",
                status="FAIL",
                message="Backend compilation failed",
                duration_ms=duration_ms,
                details={"stderr": result.stderr.decode()[:1000]},
            )
        except subprocess.TimeoutExpired:
            return SmokeResult(
                name="backend_compiles",
                category="backend",
                status="FAIL",
                message="Backend compilation timed out",
            )
        except FileNotFoundError:
            return SmokeResult(
                name="backend_compiles",
                category="backend",
                status="SKIP",
                message="mvn command not found",
            )

    def _test_healthcheck_config(self, backend_path: Path) -> SmokeResult:
        """Testa se healthcheck esta configurado."""
        # Verificar se actuator esta no pom.xml
        pom = backend_path / "pom.xml"
        if not pom.exists():
            return SmokeResult(
                name="healthcheck_configured",
                category="backend",
                status="SKIP",
                message="pom.xml not found",
            )

        try:
            pom_content = pom.read_text()
            if "spring-boot-starter-actuator" in pom_content:
                return SmokeResult(
                    name="healthcheck_configured",
                    category="backend",
                    status="PASS",
                    message="Actuator dependency found - healthcheck available at /actuator/health",
                    details={"endpoint": "/actuator/health"},
                )
            return SmokeResult(
                name="healthcheck_configured",
                category="backend",
                status="FAIL",
                message="Actuator dependency not found in pom.xml",
            )
        except Exception as e:
            return SmokeResult(
                name="healthcheck_configured",
                category="backend",
                status="FAIL",
                message=f"Error reading pom.xml: {e}",
            )

    def _test_crud_endpoint_exists(self, backend_path: Path, entity: str) -> SmokeResult:
        """Testa se endpoint CRUD existe para uma entidade."""
        # Procurar controller para a entidade
        entity_lower = entity.lower()
        entity_capitalized = entity.capitalize()

        # Padroes de nome de controller
        controller_patterns = [
            f"{entity_capitalized}Controller.java",
            f"{entity_capitalized}sController.java",
            f"{entity}Controller.java",
        ]

        src_main = backend_path / "src" / "main" / "java"
        if not src_main.exists():
            return SmokeResult(
                name=f"crud_endpoint_{entity_lower}",
                category="backend",
                status="SKIP",
                message="src/main/java not found",
            )

        # Buscar controller
        for pattern in controller_patterns:
            controllers = list(src_main.rglob(pattern))
            if controllers:
                controller = controllers[0]
                try:
                    content = controller.read_text()
                    # Verificar se tem mapeamento de API
                    if "@RestController" in content or "@Controller" in content:
                        # Verificar se tem endpoint GET
                        has_get = "@GetMapping" in content or '@RequestMapping(method = RequestMethod.GET' in content
                        if has_get:
                            return SmokeResult(
                                name=f"crud_endpoint_{entity_lower}",
                                category="backend",
                                status="PASS",
                                message=f"CRUD endpoint found for {entity}",
                                details={
                                    "controller": controller.name,
                                    "endpoint": f"/api/{entity_lower}s",
                                },
                            )
                except Exception:
                    pass

        return SmokeResult(
            name=f"crud_endpoint_{entity_lower}",
            category="backend",
            status="FAIL",
            message=f"CRUD endpoint not found for {entity}",
        )

    def _test_npm_install(self, frontend_path: Path) -> SmokeResult:
        """Testa npm install."""
        start_time = time.time()

        # Verificar se node_modules ja existe
        node_modules = frontend_path / "node_modules"
        if node_modules.exists():
            return SmokeResult(
                name="npm_install",
                category="frontend",
                status="PASS",
                message="node_modules already exists",
                duration_ms=0,
            )

        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=frontend_path,
                capture_output=True,
                timeout=180,
            )
            duration_ms = (time.time() - start_time) * 1000

            if result.returncode == 0:
                return SmokeResult(
                    name="npm_install",
                    category="frontend",
                    status="PASS",
                    message="npm install succeeded",
                    duration_ms=duration_ms,
                )
            return SmokeResult(
                name="npm_install",
                category="frontend",
                status="FAIL",
                message="npm install failed",
                duration_ms=duration_ms,
                details={"stderr": result.stderr.decode()[:1000]},
            )
        except subprocess.TimeoutExpired:
            return SmokeResult(
                name="npm_install",
                category="frontend",
                status="FAIL",
                message="npm install timed out",
            )
        except FileNotFoundError:
            return SmokeResult(
                name="npm_install",
                category="frontend",
                status="SKIP",
                message="npm command not found",
            )

    def _test_npm_build(self, frontend_path: Path) -> SmokeResult:
        """Testa npm run build."""
        start_time = time.time()

        try:
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=frontend_path,
                capture_output=True,
                timeout=180,
            )
            duration_ms = (time.time() - start_time) * 1000

            if result.returncode == 0:
                return SmokeResult(
                    name="npm_build",
                    category="frontend",
                    status="PASS",
                    message="npm run build succeeded",
                    duration_ms=duration_ms,
                )
            return SmokeResult(
                name="npm_build",
                category="frontend",
                status="FAIL",
                message="npm run build failed",
                duration_ms=duration_ms,
                details={"stderr": result.stderr.decode()[:1000]},
            )
        except subprocess.TimeoutExpired:
            return SmokeResult(
                name="npm_build",
                category="frontend",
                status="FAIL",
                message="npm run build timed out",
            )
        except FileNotFoundError:
            return SmokeResult(
                name="npm_build",
                category="frontend",
                status="SKIP",
                message="npm command not found",
            )

    def _test_main_route_exists(self, frontend_path: Path) -> SmokeResult:
        """Testa se a rota principal existe."""
        src = frontend_path / "src"
        if not src.exists():
            return SmokeResult(
                name="main_route_exists",
                category="frontend",
                status="FAIL",
                message="src directory not found",
            )

        # Procurar arquivos de rota principal
        main_files = [
            "App.tsx",
            "App.jsx",
            "App.js",
            "main.tsx",
            "main.jsx",
            "main.js",
            "index.tsx",
            "index.jsx",
        ]

        for main_file in main_files:
            files = list(src.rglob(main_file))
            if files:
                # Verificar se o arquivo tem conteudo de componente
                try:
                    content = files[0].read_text()
                    if "export" in content or "function" in content or "class" in content:
                        return SmokeResult(
                            name="main_route_exists",
                            category="frontend",
                            status="PASS",
                            message=f"Main route found: {files[0].name}",
                            details={"file": str(files[0].relative_to(frontend_path))},
                        )
                except Exception:
                    pass

        return SmokeResult(
            name="main_route_exists",
            category="frontend",
            status="FAIL",
            message="Main route file not found (App.tsx, main.tsx, etc.)",
        )

    def _save_smoke_artifacts(self, project: str, report: SmokeReport) -> str:
        """Salva artefatos do smoke test.

        Args:
            project: Nome do projeto
            report: Relatorio de smoke

        Returns:
            Caminho dos artefatos
        """
        smoke_dir = self.generated_root / project / "smoke"
        smoke_dir.mkdir(parents=True, exist_ok=True)

        # Gerar nome do arquivo com timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = smoke_dir / f"smoke_report_{timestamp}.json"

        # Salvar relatorio
        with open(report_file, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        # Salvar summary
        summary_file = smoke_dir / "latest_summary.txt"
        with open(summary_file, "w") as f:
            f.write(f"Smoke Test Summary - {project}\n")
            f.write(f"{'=' * 50}\n")
            f.write(f"Timestamp: {report.timestamp}\n")
            f.write(f"Overall Status: {report.overall_status}\n")
            f.write(f"Total: {report.total_tests} | Pass: {report.passed} | Fail: {report.failed} | Skip: {report.skipped}\n")
            f.write(f"Duration: {report.duration_ms:.2f}ms\n")
            f.write(f"\nDetails:\n")
            for result in report.results:
                status_icon = "✓" if result.status == "PASS" else "✗" if result.status == "FAIL" else "○"
                f.write(f"  [{status_icon}] {result.name}: {result.message}\n")

        return str(smoke_dir)


class LiveSmokeRunner(SmokeRunner):
    """Runner que executa testes com servidores rodando.

    Estende SmokeRunner para incluir testes HTTP reais.
    Requer que o backend e frontend estejam rodando.
    """

    def run_live_smoke_tests(
        self,
        project: str,
        entities: Optional[List[str]] = None,
        backend_url: Optional[str] = None,
        frontend_url: Optional[str] = None,
    ) -> SmokeReport:
        """Executa smoke tests com requisicoes HTTP reais.

        Args:
            project: Nome do projeto
            entities: Lista de entidades para testar
            backend_url: URL do backend (default: http://localhost:8080)
            frontend_url: URL do frontend (default: http://localhost:3000)

        Returns:
            SmokeReport com resultados
        """
        if not HAS_REQUESTS:
            report = SmokeReport(
                project=project,
                repo_path=str(self.generated_root / project),
                timestamp=datetime.now().isoformat(),
            )
            report.add_result(SmokeResult(
                name="requests_library",
                category="infrastructure",
                status="SKIP",
                message="requests library not installed",
            ))
            report.finalize()
            return report

        backend_url = backend_url or f"http://localhost:{self.backend_port}"
        frontend_url = frontend_url or f"http://localhost:{self.frontend_port}"

        start_time = datetime.now()
        repo_path = self.generated_root / project

        report = SmokeReport(
            project=project,
            repo_path=str(repo_path),
            timestamp=datetime.now().isoformat(),
        )

        # Backend HTTP tests
        backend_results = self._run_backend_http_tests(backend_url, entities)
        for result in backend_results:
            report.add_result(result)

        # Frontend HTTP tests
        frontend_results = self._run_frontend_http_tests(frontend_url)
        for result in frontend_results:
            report.add_result(result)

        report.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        report.finalize()

        # Salvar artefatos
        artifacts_path = self._save_smoke_artifacts(project, report)
        report.artifacts_path = artifacts_path

        return report

    def _run_backend_http_tests(
        self,
        backend_url: str,
        entities: Optional[List[str]] = None,
    ) -> List[SmokeResult]:
        """Executa testes HTTP do backend."""
        results: List[SmokeResult] = []

        # Test 1: Healthcheck
        healthcheck_result = self._test_healthcheck_http(backend_url)
        results.append(healthcheck_result)

        # Test 2: CRUD endpoints
        if entities and healthcheck_result.status == "PASS":
            for entity in entities:
                crud_result = self._test_crud_http(backend_url, entity)
                results.append(crud_result)

        return results

    def _run_frontend_http_tests(self, frontend_url: str) -> List[SmokeResult]:
        """Executa testes HTTP do frontend."""
        results: List[SmokeResult] = []

        # Test 1: Main page loads
        main_page_result = self._test_frontend_main_page(frontend_url)
        results.append(main_page_result)

        # Test 2: API proxy - /api via frontend MUST NOT return HTML
        api_proxy_result = self._test_frontend_api_proxy(frontend_url)
        results.append(api_proxy_result)

        return results

    def _test_frontend_api_proxy(self, frontend_url: str) -> SmokeResult:
        """Testa se /api/ via frontend retorna JSON (proxy) e NAO HTML.

        Este teste OBRIGATORIO garante que o nginx.conf tem proxy_pass configurado.
        Se /api/ retornar HTML (SPA fallback), o frontend NAO consegue chamar a API.

        Causa de FAIL: FRONTEND_API_PROXY_MISSING
        """
        start_time = time.time()
        # Testar /api/empresas ou qualquer endpoint /api/
        url = f"{frontend_url}/api/empresas"

        try:
            response = requests.get(url, timeout=self.timeout)
            duration_ms = (time.time() - start_time) * 1000

            content_type = response.headers.get("content-type", "").lower()
            body_preview = response.text[:200] if response.text else ""

            # FAIL se content-type for text/html
            if "text/html" in content_type:
                return SmokeResult(
                    name="frontend_api_proxy",
                    category="frontend",
                    status="FAIL",
                    message="FRONTEND_API_PROXY_MISSING: /api/ returns HTML instead of JSON",
                    duration_ms=duration_ms,
                    details={
                        "url": url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "body_preview": body_preview,
                        "cause": "nginx.conf missing proxy_pass for /api/",
                    },
                )

            # FAIL se body comecar com <!DOCTYPE html
            if body_preview.strip().lower().startswith("<!doctype html"):
                return SmokeResult(
                    name="frontend_api_proxy",
                    category="frontend",
                    status="FAIL",
                    message="FRONTEND_API_PROXY_MISSING: /api/ returns HTML document",
                    duration_ms=duration_ms,
                    details={
                        "url": url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "body_preview": body_preview,
                        "cause": "nginx.conf missing proxy_pass for /api/",
                    },
                )

            # PASS se content-type for application/json
            if "application/json" in content_type:
                return SmokeResult(
                    name="frontend_api_proxy",
                    category="frontend",
                    status="PASS",
                    message="Frontend API proxy OK: /api/ returns JSON",
                    duration_ms=duration_ms,
                    details={
                        "url": url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                    },
                )

            # PASS se status code indica backend respondeu (200, 401, 403, 404)
            # e NAO e HTML
            if response.status_code in [200, 204, 401, 403, 404]:
                return SmokeResult(
                    name="frontend_api_proxy",
                    category="frontend",
                    status="PASS",
                    message=f"Frontend API proxy OK: /api/ returned {response.status_code}",
                    duration_ms=duration_ms,
                    details={
                        "url": url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                    },
                )

            # Outros casos - PASS com warning
            return SmokeResult(
                name="frontend_api_proxy",
                category="frontend",
                status="PASS",
                message=f"Frontend API proxy responded with {response.status_code}",
                duration_ms=duration_ms,
                details={
                    "url": url,
                    "status_code": response.status_code,
                    "content_type": content_type,
                },
            )

        except requests.exceptions.ConnectionError:
            return SmokeResult(
                name="frontend_api_proxy",
                category="frontend",
                status="FAIL",
                message=f"Could not connect to {url}",
            )
        except requests.exceptions.Timeout:
            return SmokeResult(
                name="frontend_api_proxy",
                category="frontend",
                status="FAIL",
                message="Request timed out",
            )
        except Exception as e:
            return SmokeResult(
                name="frontend_api_proxy",
                category="frontend",
                status="FAIL",
                message=f"Error: {e}",
            )

    def _test_healthcheck_http(self, backend_url: str) -> SmokeResult:
        """Testa GET /actuator/health."""
        start_time = time.time()
        url = f"{backend_url}/actuator/health"

        try:
            response = requests.get(url, timeout=self.timeout)
            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                return SmokeResult(
                    name="healthcheck_http",
                    category="backend",
                    status="PASS",
                    message="GET /actuator/health returned 200",
                    duration_ms=duration_ms,
                    details={"status_code": 200, "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:200]},
                )
            return SmokeResult(
                name="healthcheck_http",
                category="backend",
                status="FAIL",
                message=f"GET /actuator/health returned {response.status_code}",
                duration_ms=duration_ms,
                details={"status_code": response.status_code},
            )
        except requests.exceptions.ConnectionError:
            return SmokeResult(
                name="healthcheck_http",
                category="backend",
                status="FAIL",
                message=f"Could not connect to {url}",
            )
        except requests.exceptions.Timeout:
            return SmokeResult(
                name="healthcheck_http",
                category="backend",
                status="FAIL",
                message="Request timed out",
            )
        except Exception as e:
            return SmokeResult(
                name="healthcheck_http",
                category="backend",
                status="FAIL",
                message=f"Error: {e}",
            )

    def _test_crud_http(self, backend_url: str, entity: str) -> SmokeResult:
        """Testa GET /api/<entityPlural>."""
        start_time = time.time()
        entity_plural = f"{entity.lower()}s"
        url = f"{backend_url}/api/{entity_plural}"

        try:
            response = requests.get(url, timeout=self.timeout)
            duration_ms = (time.time() - start_time) * 1000

            # 200 = sucesso sem auth
            # 401 = requer auth (esperado se RBAC ativo)
            # 403 = forbidden (esperado se RBAC ativo)
            if response.status_code in [200, 401, 403]:
                return SmokeResult(
                    name=f"crud_http_{entity.lower()}",
                    category="backend",
                    status="PASS",
                    message=f"GET /api/{entity_plural} returned {response.status_code}",
                    duration_ms=duration_ms,
                    details={"status_code": response.status_code, "endpoint": url},
                )
            return SmokeResult(
                name=f"crud_http_{entity.lower()}",
                category="backend",
                status="FAIL",
                message=f"GET /api/{entity_plural} returned {response.status_code}",
                duration_ms=duration_ms,
                details={"status_code": response.status_code},
            )
        except requests.exceptions.ConnectionError:
            return SmokeResult(
                name=f"crud_http_{entity.lower()}",
                category="backend",
                status="FAIL",
                message=f"Could not connect to {url}",
            )
        except Exception as e:
            return SmokeResult(
                name=f"crud_http_{entity.lower()}",
                category="backend",
                status="FAIL",
                message=f"Error: {e}",
            )

    def _test_frontend_main_page(self, frontend_url: str) -> SmokeResult:
        """Testa se a pagina principal carrega."""
        start_time = time.time()

        try:
            response = requests.get(frontend_url, timeout=self.timeout)
            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                # Verificar se tem conteudo HTML
                content_type = response.headers.get("content-type", "")
                has_html = "text/html" in content_type or "<html" in response.text.lower()

                if has_html:
                    return SmokeResult(
                        name="frontend_main_page",
                        category="frontend",
                        status="PASS",
                        message="Main page loads successfully",
                        duration_ms=duration_ms,
                        details={"status_code": 200, "content_type": content_type},
                    )
                return SmokeResult(
                    name="frontend_main_page",
                    category="frontend",
                    status="FAIL",
                    message="Main page returned 200 but no HTML content",
                    duration_ms=duration_ms,
                )
            return SmokeResult(
                name="frontend_main_page",
                category="frontend",
                status="FAIL",
                message=f"Main page returned {response.status_code}",
                duration_ms=duration_ms,
            )
        except requests.exceptions.ConnectionError:
            return SmokeResult(
                name="frontend_main_page",
                category="frontend",
                status="FAIL",
                message=f"Could not connect to {frontend_url}",
            )
        except Exception as e:
            return SmokeResult(
                name="frontend_main_page",
                category="frontend",
                status="FAIL",
                message=f"Error: {e}",
            )


def run_smoke(project: str, entities: Optional[List[str]] = None) -> dict:
    """Funcao de conveniencia para executar smoke tests.

    Args:
        project: Nome do projeto
        entities: Lista de entidades para testar

    Returns:
        Dicionario com resultado
    """
    runner = SmokeRunner()
    report = runner.run_smoke_tests(project, entities)
    return report.to_dict()
