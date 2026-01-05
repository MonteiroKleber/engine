"""QA/Release Agent - Smoke tests, checklists e release bundles.

Este agente e responsavel por:
1. Executar smoke tests no repositorio gerado
2. Gerar checklist de release
3. Emitir bundle de release

REGRA: Gera relatorio estruturado mesmo com repo minimo.
"""

import os
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SmokeTestResult:
    """Resultado de um smoke test individual."""

    name: str
    passed: bool
    message: str
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


@dataclass
class SmokeTestReport:
    """Relatorio completo de smoke tests."""

    repo_path: str
    timestamp: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    results: List[SmokeTestResult] = field(default_factory=list)
    overall_status: str = "unknown"
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "repo_path": self.repo_path,
            "timestamp": self.timestamp,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "overall_status": self.overall_status,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ChecklistItem:
    """Item individual do checklist de release."""

    id: str
    category: str
    description: str
    status: str  # "ok", "warning", "error", "skipped"
    message: str
    required: bool = True
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "id": self.id,
            "category": self.category,
            "description": self.description,
            "status": self.status,
            "message": self.message,
            "required": self.required,
            "details": self.details,
        }


@dataclass
class ChecklistReport:
    """Relatorio completo do checklist de release."""

    repo_path: str
    timestamp: str
    items: List[ChecklistItem] = field(default_factory=list)
    ready_for_release: bool = False
    blocking_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "repo_path": self.repo_path,
            "timestamp": self.timestamp,
            "items": [i.to_dict() for i in self.items],
            "ready_for_release": self.ready_for_release,
            "blocking_issues": self.blocking_issues,
            "warnings": self.warnings,
        }


class QAReleaseAgent:
    """Agente de QA e Release.

    Responsavel por:
    - Smoke tests: verificacoes rapidas de sanidade
    - Checklist: lista de verificacoes pre-release
    - Bundle: empacotamento para release

    Attributes:
        store_root: Diretorio raiz do store de artefatos
        generated_root: Diretorio raiz dos projetos gerados
    """

    # Diretorio padrao de projetos gerados
    DEFAULT_GENERATED_ROOT = "/home/bazari/generated"
    DEFAULT_STORE_ROOT = "/home/bazari/engine/demo_store"

    def __init__(
        self,
        store_root: Optional[str] = None,
        generated_root: Optional[str] = None,
    ):
        """Inicializa o agente.

        Args:
            store_root: Diretorio raiz do store
            generated_root: Diretorio raiz dos projetos gerados
        """
        self.store_root = Path(store_root or self.DEFAULT_STORE_ROOT)
        self.generated_root = Path(generated_root or self.DEFAULT_GENERATED_ROOT)

    def run_smoke(self, repo_path: str) -> dict:
        """Executa smoke tests no repositorio.

        Smoke tests sao verificacoes rapidas de sanidade:
        - Estrutura de diretorios existe
        - Arquivos essenciais existem
        - Configuracoes basicas estao presentes

        Args:
            repo_path: Caminho para o repositorio gerado

        Returns:
            Dicionario com resultado dos smoke tests
        """
        start_time = datetime.now()
        repo = Path(repo_path)
        results: List[SmokeTestResult] = []

        # Test 1: Diretorio existe
        results.append(self._test_directory_exists(repo))

        # Test 2: Estrutura basica
        results.append(self._test_basic_structure(repo))

        # Test 3: Backend existe
        results.append(self._test_backend_exists(repo))

        # Test 4: Frontend existe
        results.append(self._test_frontend_exists(repo))

        # Test 5: Database existe
        results.append(self._test_database_exists(repo))

        # Test 6: Docker compose existe
        results.append(self._test_docker_compose_exists(repo))

        # Test 7: Backend compila (se existir)
        results.append(self._test_backend_compiles(repo))

        # Test 8: Frontend compila (se existir)
        results.append(self._test_frontend_compiles(repo))

        # Calcular estatisticas
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed and r.message != "skipped")
        skipped = sum(1 for r in results if r.message == "skipped")

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Determinar status geral
        if failed > 0:
            overall_status = "failed"
        elif skipped == len(results):
            overall_status = "skipped"
        else:
            overall_status = "passed"

        report = SmokeTestReport(
            repo_path=str(repo_path),
            timestamp=datetime.now().isoformat(),
            total_tests=len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            results=results,
            overall_status=overall_status,
            duration_ms=duration_ms,
        )

        return report.to_dict()

    def run_checklist(self, repo_path: str) -> dict:
        """Executa checklist de release.

        Checklist verifica items necessarios para release:
        - Estrutura de projeto completa
        - Configuracoes de producao
        - Documentacao minima
        - Seguranca basica

        Args:
            repo_path: Caminho para o repositorio gerado

        Returns:
            Dicionario com resultado do checklist
        """
        repo = Path(repo_path)
        items: List[ChecklistItem] = []
        blocking_issues: List[str] = []
        warnings: List[str] = []

        # Categoria: Structure
        items.append(self._check_project_structure(repo))
        items.append(self._check_backend_structure(repo))
        items.append(self._check_frontend_structure(repo))
        items.append(self._check_database_structure(repo))

        # Categoria: Configuration
        items.append(self._check_docker_config(repo))
        items.append(self._check_env_config(repo))

        # Categoria: Security
        items.append(self._check_security_config(repo))
        items.append(self._check_no_secrets(repo))

        # Categoria: Documentation
        items.append(self._check_readme_exists(repo))

        # Categoria: Build
        items.append(self._check_build_files(repo))

        # Coletar issues bloqueantes e warnings
        for item in items:
            if item.status == "error" and item.required:
                blocking_issues.append(f"[{item.id}] {item.message}")
            elif item.status == "warning":
                warnings.append(f"[{item.id}] {item.message}")

        # Determinar se esta pronto para release
        ready_for_release = len(blocking_issues) == 0

        report = ChecklistReport(
            repo_path=str(repo_path),
            timestamp=datetime.now().isoformat(),
            items=items,
            ready_for_release=ready_for_release,
            blocking_issues=blocking_issues,
            warnings=warnings,
        )

        return report.to_dict()

    def emit_release_bundle(self, project: str) -> str:
        """Gera bundle de release para o projeto.

        O bundle contem:
        - Codigo fonte compactado
        - Artefatos de especificacao (SRS, IR, OAS, RBAC, PLAN)
        - Metadados de release

        Args:
            project: Nome do projeto

        Returns:
            Caminho para o bundle gerado
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bundle_name = f"{project}_release_{timestamp}"
        bundle_dir = self.store_root / project / "releases" / bundle_name
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # 1. Copiar artefatos de especificacao
        artifacts_dir = bundle_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        self._copy_latest_artifacts(project, artifacts_dir)

        # 2. Copiar codigo fonte (se existir)
        source_dir = bundle_dir / "source"
        repo_path = self.generated_root / project
        if repo_path.exists():
            self._copy_source(repo_path, source_dir)

        # 3. Gerar metadados
        metadata = self._generate_release_metadata(project, bundle_name)
        metadata_path = bundle_dir / "release_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # 4. Gerar arquivo zip do bundle
        bundle_zip = self.store_root / project / "releases" / f"{bundle_name}.zip"
        shutil.make_archive(
            str(bundle_zip).replace(".zip", ""),
            "zip",
            bundle_dir,
        )

        return str(bundle_zip)

    # ==================== SMOKE TESTS ====================

    def _test_directory_exists(self, repo: Path) -> SmokeTestResult:
        """Testa se o diretorio do repositorio existe."""
        if repo.exists() and repo.is_dir():
            return SmokeTestResult(
                name="directory_exists",
                passed=True,
                message="Repository directory exists",
            )
        return SmokeTestResult(
            name="directory_exists",
            passed=False,
            message=f"Repository directory not found: {repo}",
        )

    def _test_basic_structure(self, repo: Path) -> SmokeTestResult:
        """Testa se a estrutura basica existe."""
        if not repo.exists():
            return SmokeTestResult(
                name="basic_structure",
                passed=False,
                message="skipped",
            )

        # Verificar se tem pelo menos um subdiretorio
        subdirs = [d for d in repo.iterdir() if d.is_dir()]
        if len(subdirs) > 0:
            return SmokeTestResult(
                name="basic_structure",
                passed=True,
                message=f"Found {len(subdirs)} subdirectories",
                details={"subdirs": [d.name for d in subdirs]},
            )
        return SmokeTestResult(
            name="basic_structure",
            passed=False,
            message="No subdirectories found",
        )

    def _test_backend_exists(self, repo: Path) -> SmokeTestResult:
        """Testa se o backend existe."""
        backend = repo / "backend"
        if not repo.exists():
            return SmokeTestResult(
                name="backend_exists",
                passed=False,
                message="skipped",
            )

        if backend.exists() and backend.is_dir():
            return SmokeTestResult(
                name="backend_exists",
                passed=True,
                message="Backend directory exists",
            )
        return SmokeTestResult(
            name="backend_exists",
            passed=False,
            message="Backend directory not found",
        )

    def _test_frontend_exists(self, repo: Path) -> SmokeTestResult:
        """Testa se o frontend existe."""
        frontend = repo / "frontend"
        if not repo.exists():
            return SmokeTestResult(
                name="frontend_exists",
                passed=False,
                message="skipped",
            )

        if frontend.exists() and frontend.is_dir():
            return SmokeTestResult(
                name="frontend_exists",
                passed=True,
                message="Frontend directory exists",
            )
        return SmokeTestResult(
            name="frontend_exists",
            passed=False,
            message="Frontend directory not found",
        )

    def _test_database_exists(self, repo: Path) -> SmokeTestResult:
        """Testa se o database existe."""
        database = repo / "database"
        if not repo.exists():
            return SmokeTestResult(
                name="database_exists",
                passed=False,
                message="skipped",
            )

        if database.exists() and database.is_dir():
            return SmokeTestResult(
                name="database_exists",
                passed=True,
                message="Database directory exists",
            )
        return SmokeTestResult(
            name="database_exists",
            passed=False,
            message="Database directory not found",
        )

    def _test_docker_compose_exists(self, repo: Path) -> SmokeTestResult:
        """Testa se o docker-compose existe."""
        if not repo.exists():
            return SmokeTestResult(
                name="docker_compose_exists",
                passed=False,
                message="skipped",
            )

        docker_compose = repo / "docker-compose.yml"
        docker_compose_yaml = repo / "docker-compose.yaml"

        if docker_compose.exists() or docker_compose_yaml.exists():
            return SmokeTestResult(
                name="docker_compose_exists",
                passed=True,
                message="docker-compose file exists",
            )
        return SmokeTestResult(
            name="docker_compose_exists",
            passed=False,
            message="docker-compose file not found",
        )

    def _test_backend_compiles(self, repo: Path) -> SmokeTestResult:
        """Testa se o backend compila."""
        backend = repo / "backend"
        if not backend.exists():
            return SmokeTestResult(
                name="backend_compiles",
                passed=False,
                message="skipped",
            )

        # Verificar se e um projeto Maven
        pom = backend / "pom.xml"
        if pom.exists():
            try:
                result = subprocess.run(
                    ["mvn", "compile", "-q", "-DskipTests"],
                    cwd=backend,
                    capture_output=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    return SmokeTestResult(
                        name="backend_compiles",
                        passed=True,
                        message="Backend compiles successfully (Maven)",
                    )
                return SmokeTestResult(
                    name="backend_compiles",
                    passed=False,
                    message="Backend compilation failed",
                    details={"stderr": result.stderr.decode()[:500]},
                )
            except subprocess.TimeoutExpired:
                return SmokeTestResult(
                    name="backend_compiles",
                    passed=False,
                    message="Backend compilation timed out",
                )
            except FileNotFoundError:
                return SmokeTestResult(
                    name="backend_compiles",
                    passed=False,
                    message="skipped",
                    details={"reason": "mvn not found"},
                )

        return SmokeTestResult(
            name="backend_compiles",
            passed=False,
            message="skipped",
            details={"reason": "Unknown backend type"},
        )

    def _test_frontend_compiles(self, repo: Path) -> SmokeTestResult:
        """Testa se o frontend compila."""
        frontend = repo / "frontend"
        if not frontend.exists():
            return SmokeTestResult(
                name="frontend_compiles",
                passed=False,
                message="skipped",
            )

        # Verificar se e um projeto Node
        package_json = frontend / "package.json"
        if package_json.exists():
            try:
                # Primeiro instalar dependencias
                subprocess.run(
                    ["npm", "install"],
                    cwd=frontend,
                    capture_output=True,
                    timeout=120,
                )
                # Depois compilar
                result = subprocess.run(
                    ["npm", "run", "build"],
                    cwd=frontend,
                    capture_output=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    return SmokeTestResult(
                        name="frontend_compiles",
                        passed=True,
                        message="Frontend compiles successfully (npm)",
                    )
                return SmokeTestResult(
                    name="frontend_compiles",
                    passed=False,
                    message="Frontend compilation failed",
                    details={"stderr": result.stderr.decode()[:500]},
                )
            except subprocess.TimeoutExpired:
                return SmokeTestResult(
                    name="frontend_compiles",
                    passed=False,
                    message="Frontend compilation timed out",
                )
            except FileNotFoundError:
                return SmokeTestResult(
                    name="frontend_compiles",
                    passed=False,
                    message="skipped",
                    details={"reason": "npm not found"},
                )

        return SmokeTestResult(
            name="frontend_compiles",
            passed=False,
            message="skipped",
            details={"reason": "Unknown frontend type"},
        )

    # ==================== CHECKLIST ITEMS ====================

    def _check_project_structure(self, repo: Path) -> ChecklistItem:
        """Verifica estrutura do projeto."""
        if not repo.exists():
            return ChecklistItem(
                id="STRUCT-001",
                category="structure",
                description="Project directory exists",
                status="error",
                message="Project directory not found",
                required=True,
            )
        return ChecklistItem(
            id="STRUCT-001",
            category="structure",
            description="Project directory exists",
            status="ok",
            message="Project directory exists",
            required=True,
        )

    def _check_backend_structure(self, repo: Path) -> ChecklistItem:
        """Verifica estrutura do backend."""
        backend = repo / "backend"
        if not repo.exists():
            return ChecklistItem(
                id="STRUCT-002",
                category="structure",
                description="Backend structure",
                status="skipped",
                message="Project not found",
                required=True,
            )

        if not backend.exists():
            return ChecklistItem(
                id="STRUCT-002",
                category="structure",
                description="Backend structure",
                status="error",
                message="Backend directory not found",
                required=True,
            )

        # Verificar arquivos essenciais
        pom = backend / "pom.xml"
        src = backend / "src"

        missing = []
        if not pom.exists():
            missing.append("pom.xml")
        if not src.exists():
            missing.append("src/")

        if missing:
            return ChecklistItem(
                id="STRUCT-002",
                category="structure",
                description="Backend structure",
                status="warning",
                message=f"Missing: {', '.join(missing)}",
                required=True,
                details={"missing": missing},
            )

        return ChecklistItem(
            id="STRUCT-002",
            category="structure",
            description="Backend structure",
            status="ok",
            message="Backend structure is complete",
            required=True,
        )

    def _check_frontend_structure(self, repo: Path) -> ChecklistItem:
        """Verifica estrutura do frontend."""
        frontend = repo / "frontend"
        if not repo.exists():
            return ChecklistItem(
                id="STRUCT-003",
                category="structure",
                description="Frontend structure",
                status="skipped",
                message="Project not found",
                required=True,
            )

        if not frontend.exists():
            return ChecklistItem(
                id="STRUCT-003",
                category="structure",
                description="Frontend structure",
                status="error",
                message="Frontend directory not found",
                required=True,
            )

        # Verificar arquivos essenciais
        package_json = frontend / "package.json"
        src = frontend / "src"

        missing = []
        if not package_json.exists():
            missing.append("package.json")
        if not src.exists():
            missing.append("src/")

        if missing:
            return ChecklistItem(
                id="STRUCT-003",
                category="structure",
                description="Frontend structure",
                status="warning",
                message=f"Missing: {', '.join(missing)}",
                required=True,
                details={"missing": missing},
            )

        return ChecklistItem(
            id="STRUCT-003",
            category="structure",
            description="Frontend structure",
            status="ok",
            message="Frontend structure is complete",
            required=True,
        )

    def _check_database_structure(self, repo: Path) -> ChecklistItem:
        """Verifica estrutura do database."""
        database = repo / "database"
        if not repo.exists():
            return ChecklistItem(
                id="STRUCT-004",
                category="structure",
                description="Database structure",
                status="skipped",
                message="Project not found",
                required=False,
            )

        if not database.exists():
            return ChecklistItem(
                id="STRUCT-004",
                category="structure",
                description="Database structure",
                status="warning",
                message="Database directory not found",
                required=False,
            )

        # Verificar se tem migrations
        migrations = list(database.glob("*.sql")) + list(database.glob("**/*.sql"))
        if not migrations:
            return ChecklistItem(
                id="STRUCT-004",
                category="structure",
                description="Database structure",
                status="warning",
                message="No SQL migrations found",
                required=False,
            )

        return ChecklistItem(
            id="STRUCT-004",
            category="structure",
            description="Database structure",
            status="ok",
            message=f"Found {len(migrations)} migration files",
            required=False,
            details={"migrations_count": len(migrations)},
        )

    def _check_docker_config(self, repo: Path) -> ChecklistItem:
        """Verifica configuracao Docker."""
        if not repo.exists():
            return ChecklistItem(
                id="CONFIG-001",
                category="configuration",
                description="Docker configuration",
                status="skipped",
                message="Project not found",
                required=True,
            )

        docker_compose = repo / "docker-compose.yml"
        docker_compose_yaml = repo / "docker-compose.yaml"

        if not docker_compose.exists() and not docker_compose_yaml.exists():
            return ChecklistItem(
                id="CONFIG-001",
                category="configuration",
                description="Docker configuration",
                status="error",
                message="docker-compose file not found",
                required=True,
            )

        return ChecklistItem(
            id="CONFIG-001",
            category="configuration",
            description="Docker configuration",
            status="ok",
            message="docker-compose file exists",
            required=True,
        )

    def _check_env_config(self, repo: Path) -> ChecklistItem:
        """Verifica configuracao de ambiente."""
        if not repo.exists():
            return ChecklistItem(
                id="CONFIG-002",
                category="configuration",
                description="Environment configuration",
                status="skipped",
                message="Project not found",
                required=False,
            )

        env_example = repo / ".env.example"
        env_file = repo / ".env"

        if env_example.exists():
            return ChecklistItem(
                id="CONFIG-002",
                category="configuration",
                description="Environment configuration",
                status="ok",
                message=".env.example exists",
                required=False,
            )

        if env_file.exists():
            return ChecklistItem(
                id="CONFIG-002",
                category="configuration",
                description="Environment configuration",
                status="warning",
                message=".env exists but .env.example is missing",
                required=False,
            )

        return ChecklistItem(
            id="CONFIG-002",
            category="configuration",
            description="Environment configuration",
            status="warning",
            message="No environment configuration found",
            required=False,
        )

    def _check_security_config(self, repo: Path) -> ChecklistItem:
        """Verifica configuracao de seguranca."""
        if not repo.exists():
            return ChecklistItem(
                id="SEC-001",
                category="security",
                description="Security configuration",
                status="skipped",
                message="Project not found",
                required=True,
            )

        # Verificar se tem configuracao de seguranca no backend
        backend = repo / "backend"
        if backend.exists():
            security_config = list(backend.glob("**/Security*.java"))
            if security_config:
                return ChecklistItem(
                    id="SEC-001",
                    category="security",
                    description="Security configuration",
                    status="ok",
                    message=f"Found {len(security_config)} security config files",
                    required=True,
                    details={"files": [f.name for f in security_config]},
                )

        return ChecklistItem(
            id="SEC-001",
            category="security",
            description="Security configuration",
            status="warning",
            message="No security configuration found",
            required=True,
        )

    def _check_no_secrets(self, repo: Path) -> ChecklistItem:
        """Verifica se nao ha secrets expostos."""
        if not repo.exists():
            return ChecklistItem(
                id="SEC-002",
                category="security",
                description="No exposed secrets",
                status="skipped",
                message="Project not found",
                required=True,
            )

        # Verificar se .env nao esta comitado (se .gitignore existe)
        gitignore = repo / ".gitignore"
        env_file = repo / ".env"

        if env_file.exists():
            if gitignore.exists():
                with open(gitignore) as f:
                    content = f.read()
                if ".env" in content:
                    return ChecklistItem(
                        id="SEC-002",
                        category="security",
                        description="No exposed secrets",
                        status="ok",
                        message=".env is in .gitignore",
                        required=True,
                    )
            return ChecklistItem(
                id="SEC-002",
                category="security",
                description="No exposed secrets",
                status="warning",
                message=".env exists but may not be in .gitignore",
                required=True,
            )

        return ChecklistItem(
            id="SEC-002",
            category="security",
            description="No exposed secrets",
            status="ok",
            message="No .env file found (good)",
            required=True,
        )

    def _check_readme_exists(self, repo: Path) -> ChecklistItem:
        """Verifica se README existe."""
        if not repo.exists():
            return ChecklistItem(
                id="DOC-001",
                category="documentation",
                description="README exists",
                status="skipped",
                message="Project not found",
                required=False,
            )

        readme = repo / "README.md"
        readme_txt = repo / "README.txt"
        readme_plain = repo / "README"

        if readme.exists() or readme_txt.exists() or readme_plain.exists():
            return ChecklistItem(
                id="DOC-001",
                category="documentation",
                description="README exists",
                status="ok",
                message="README file exists",
                required=False,
            )

        return ChecklistItem(
            id="DOC-001",
            category="documentation",
            description="README exists",
            status="warning",
            message="No README file found",
            required=False,
        )

    def _check_build_files(self, repo: Path) -> ChecklistItem:
        """Verifica se arquivos de build existem."""
        if not repo.exists():
            return ChecklistItem(
                id="BUILD-001",
                category="build",
                description="Build files exist",
                status="skipped",
                message="Project not found",
                required=True,
            )

        build_files = []

        # Backend
        backend = repo / "backend"
        if backend.exists():
            pom = backend / "pom.xml"
            if pom.exists():
                build_files.append("backend/pom.xml")

        # Frontend
        frontend = repo / "frontend"
        if frontend.exists():
            package_json = frontend / "package.json"
            if package_json.exists():
                build_files.append("frontend/package.json")

        if not build_files:
            return ChecklistItem(
                id="BUILD-001",
                category="build",
                description="Build files exist",
                status="error",
                message="No build files found",
                required=True,
            )

        return ChecklistItem(
            id="BUILD-001",
            category="build",
            description="Build files exist",
            status="ok",
            message=f"Found {len(build_files)} build files",
            required=True,
            details={"files": build_files},
        )

    # ==================== BUNDLE HELPERS ====================

    def _copy_latest_artifacts(self, project: str, dest: Path) -> None:
        """Copia os artefatos mais recentes para o bundle."""
        project_store = self.store_root / project
        if not project_store.exists():
            return

        artifact_types = ["SRS", "IR", "OAS", "RBAC", "PLAN"]

        for artifact_type in artifact_types:
            artifact_dir = project_store / artifact_type
            if not artifact_dir.exists():
                continue

            # Encontrar versao mais recente
            versions = []
            for f in artifact_dir.iterdir():
                if f.is_file():
                    name = f.stem
                    if name.startswith("v") and name[1:].isdigit():
                        versions.append((int(name[1:]), f))

            if versions:
                versions.sort(key=lambda x: x[0], reverse=True)
                latest = versions[0][1]
                shutil.copy(latest, dest / f"{artifact_type}_{latest.name}")

    def _copy_source(self, repo: Path, dest: Path) -> None:
        """Copia o codigo fonte para o bundle."""
        if not repo.exists():
            return

        # Copiar apenas diretorios relevantes
        for subdir in ["backend", "frontend", "database"]:
            src = repo / subdir
            if src.exists():
                shutil.copytree(src, dest / subdir, dirs_exist_ok=True)

        # Copiar arquivos na raiz
        for pattern in ["docker-compose.yml", "docker-compose.yaml", "README.md", ".env.example"]:
            src = repo / pattern
            if src.exists():
                shutil.copy(src, dest / pattern)

    def _generate_release_metadata(self, project: str, bundle_name: str) -> Dict[str, Any]:
        """Gera metadados do release."""
        return {
            "project": project,
            "bundle_name": bundle_name,
            "created_at": datetime.now().isoformat(),
            "generator": "QAReleaseAgent",
            "version": "1.0.0",
            "artifacts_included": ["SRS", "IR", "OAS", "RBAC", "PLAN"],
            "source_included": True,
        }
