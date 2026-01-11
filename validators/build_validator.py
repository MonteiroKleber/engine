"""Build Validator - Valida que projetos gerados compilam corretamente.

Executa builds em:
- Backend (backend/): mvn test
- Frontend (frontend/): npm ci && npm run build

Critério: Templates puros devem passar no build.
"""

import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import get_config


class BuildComponent(Enum):
    """Componentes do projeto que podem ser buildados."""

    BACKEND = "backend"
    FRONTEND = "frontend"
    ALL = "all"


@dataclass
class BuildResult:
    """Resultado de um build."""

    component: str
    success: bool
    command: str
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "component": self.component,
            "success": self.success,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:1000] if self.stdout else "",
            "stderr": self.stderr[:1000] if self.stderr else "",
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class BuildReport:
    """Relatório completo de validação de build."""

    ok: bool
    project: str
    results: List[BuildResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "ok": self.ok,
            "project": self.project,
            "results": [r.to_dict() for r in self.results],
            "errors": self.errors,
            "warnings": self.warnings,
        }


class BuildValidator:
    """Valida builds de projetos gerados.

    Executa comandos de build para backend e frontend,
    verificando que o código compila sem erros.

    Attributes:
        generated_root: Diretório raiz dos projetos gerados
        timeout: Timeout em segundos para cada comando
    """

    # Timeouts padrão
    DEFAULT_TIMEOUT = 300  # 5 minutos
    NPM_CI_TIMEOUT = 180   # 3 minutos para npm ci
    MVN_TIMEOUT = 300      # 5 minutos para mvn

    def __init__(
        self,
        generated_root: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Inicializa o BuildValidator.

        Args:
            generated_root: Diretório raiz dos projetos gerados (from config if None)
            timeout: Timeout padrão em segundos
        """
        self.generated_root = Path(generated_root or get_config().generated_root)
        self.timeout = timeout

    def _run_command(
        self,
        command: List[str],
        cwd: Path,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> tuple[int, str, str, float]:
        """Executa um comando e retorna resultado.

        Args:
            command: Comando como lista de strings
            cwd: Diretório de trabalho
            timeout: Timeout em segundos (None usa padrão)
            env: Variáveis de ambiente adicionais

        Returns:
            Tupla (exit_code, stdout, stderr, duration_seconds)
        """
        import time

        start_time = time.time()
        timeout = timeout or self.timeout

        # Preparar ambiente
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
            )
            duration = time.time() - start_time
            return result.returncode, result.stdout, result.stderr, duration

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return -1, "", f"Command timed out after {timeout}s", duration

        except FileNotFoundError as e:
            duration = time.time() - start_time
            return -1, "", f"Command not found: {e}", duration

        except Exception as e:
            duration = time.time() - start_time
            return -1, "", f"Error executing command: {e}", duration

    def _validate_backend(self, project_dir: Path) -> BuildResult:
        """Valida o build do backend (Maven/Spring Boot).

        Args:
            project_dir: Diretório do projeto

        Returns:
            BuildResult do backend
        """
        backend_dir = project_dir / "backend"
        command = ["mvn", "test", "-B", "-q"]  # -B batch mode, -q quiet

        if not backend_dir.exists():
            return BuildResult(
                component="backend",
                success=False,
                command=" ".join(command),
                exit_code=-1,
                stderr=f"Backend directory not found: {backend_dir}",
            )

        if not (backend_dir / "pom.xml").exists():
            return BuildResult(
                component="backend",
                success=False,
                command=" ".join(command),
                exit_code=-1,
                stderr="pom.xml not found in backend/",
            )

        exit_code, stdout, stderr, duration = self._run_command(
            command,
            cwd=backend_dir,
            timeout=self.MVN_TIMEOUT,
        )

        return BuildResult(
            component="backend",
            success=exit_code == 0,
            command=" ".join(command),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
        )

    def _validate_frontend(self, project_dir: Path) -> List[BuildResult]:
        """Valida o build do frontend (npm/Vite).

        Args:
            project_dir: Diretório do projeto

        Returns:
            Lista de BuildResults (npm ci + npm run build)
        """
        frontend_dir = project_dir / "frontend"
        results = []

        if not frontend_dir.exists():
            return [
                BuildResult(
                    component="frontend",
                    success=False,
                    command="npm ci",
                    exit_code=-1,
                    stderr=f"Frontend directory not found: {frontend_dir}",
                )
            ]

        if not (frontend_dir / "package.json").exists():
            return [
                BuildResult(
                    component="frontend",
                    success=False,
                    command="npm ci",
                    exit_code=-1,
                    stderr="package.json not found in frontend/",
                )
            ]

        # 1. npm ci (install dependencies)
        # Use npm install if package-lock.json doesn't exist
        has_lock = (frontend_dir / "package-lock.json").exists()
        npm_ci_cmd = ["npm", "ci"] if has_lock else ["npm", "install"]
        exit_code, stdout, stderr, duration = self._run_command(
            npm_ci_cmd,
            cwd=frontend_dir,
            timeout=self.NPM_CI_TIMEOUT,
        )

        npm_ci_result = BuildResult(
            component="frontend:install",
            success=exit_code == 0,
            command=" ".join(npm_ci_cmd),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
        )
        results.append(npm_ci_result)

        # Se npm ci falhou, não tenta o build
        if not npm_ci_result.success:
            return results

        # 2. npm run build
        npm_build_cmd = ["npm", "run", "build"]
        exit_code, stdout, stderr, duration = self._run_command(
            npm_build_cmd,
            cwd=frontend_dir,
            timeout=self.timeout,
        )

        npm_build_result = BuildResult(
            component="frontend:build",
            success=exit_code == 0,
            command=" ".join(npm_build_cmd),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
        )
        results.append(npm_build_result)

        return results

    def validate(
        self,
        project: str,
        components: BuildComponent = BuildComponent.ALL,
    ) -> BuildReport:
        """Valida o build de um projeto.

        Args:
            project: Nome do projeto
            components: Quais componentes validar (backend, frontend, all)

        Returns:
            BuildReport com resultados
        """
        project_dir = self.generated_root / project
        results: List[BuildResult] = []
        errors: List[str] = []

        # Verificar se projeto existe
        if not project_dir.exists():
            return BuildReport(
                ok=False,
                project=project,
                errors=[f"Project not found: {project_dir}"],
            )

        # Validar backend
        if components in (BuildComponent.BACKEND, BuildComponent.ALL):
            backend_result = self._validate_backend(project_dir)
            results.append(backend_result)
            if not backend_result.success:
                errors.append(f"Backend build failed: {backend_result.stderr[:200]}")

        # Validar frontend
        if components in (BuildComponent.FRONTEND, BuildComponent.ALL):
            frontend_results = self._validate_frontend(project_dir)
            results.extend(frontend_results)
            for fr in frontend_results:
                if not fr.success:
                    errors.append(f"{fr.component} failed: {fr.stderr[:200]}")

        # Determinar sucesso geral
        all_success = all(r.success for r in results)

        return BuildReport(
            ok=all_success,
            project=project,
            results=results,
            errors=errors,
        )

    def validate_backend_only(self, project: str) -> BuildReport:
        """Valida apenas o backend de um projeto.

        Args:
            project: Nome do projeto

        Returns:
            BuildReport com resultado do backend
        """
        return self.validate(project, BuildComponent.BACKEND)

    def validate_frontend_only(self, project: str) -> BuildReport:
        """Valida apenas o frontend de um projeto.

        Args:
            project: Nome do projeto

        Returns:
            BuildReport com resultado do frontend
        """
        return self.validate(project, BuildComponent.FRONTEND)


def validate_build(
    project: str,
    generated_root: Optional[str] = None,
    components: BuildComponent = BuildComponent.ALL,
) -> BuildReport:
    """Função de conveniência para validar build.

    Args:
        project: Nome do projeto
        generated_root: Diretório raiz dos projetos gerados (from config if None)
        components: Quais componentes validar

    Returns:
        BuildReport com resultados
    """
    validator = BuildValidator(generated_root)
    return validator.validate(project, components)
