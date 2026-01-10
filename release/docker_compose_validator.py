"""Docker Compose Validator - Valida e garante docker-compose.yml correto.

Garante que o docker-compose.yml gerado contenha:
- Servico postgres
- Servico backend
- Servico frontend

Aceite: `docker compose up -d` sobe os 3 servicos sem erro.
"""

import os
import logging
import subprocess
import sys
import json
import urllib.request
import urllib.error
import time
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from release.runtime_evidence_collector import collect_runtime_evidence


@dataclass
class DockerComposeValidationResult:
    """Resultado da validacao do docker-compose."""

    valid: bool
    file_exists: bool
    file_path: Optional[str] = None
    services_found: List[str] = field(default_factory=list)
    missing_services: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "valid": self.valid,
            "file_exists": self.file_exists,
            "file_path": self.file_path,
            "services_found": self.services_found,
            "missing_services": self.missing_services,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class DockerContextValidationResult:
    """Resultado da validação de build contexts do docker-compose.

    Gate pré-docker que verifica se todos os build contexts e Dockerfiles existem
    antes de executar docker compose up.
    """

    valid: bool
    compose_file_path: str = ""
    resolved_context_paths: List[str] = field(default_factory=list)
    missing_context_paths: List[str] = field(default_factory=list)
    resolved_dockerfile_paths: List[str] = field(default_factory=list)
    missing_dockerfile_paths: List[str] = field(default_factory=list)
    nginx_conf_valid: bool = False
    nginx_conf_path: str = ""
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        return {
            "docker_context_validation_ok": self.valid,
            "compose_file_path": self.compose_file_path,
            "resolved_context_paths": self.resolved_context_paths,
            "missing_context_paths": self.missing_context_paths,
            "resolved_dockerfile_paths": self.resolved_dockerfile_paths,
            "missing_dockerfile_paths": self.missing_dockerfile_paths,
            "nginx_conf_valid": self.nginx_conf_valid,
            "nginx_conf_path": self.nginx_conf_path,
            "errors": self.errors,
        }


@dataclass
class DockerComposeUpResult:
    """Resultado do docker compose up."""

    success: bool
    services_started: List[str] = field(default_factory=list)
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    # Campos adicionais para run log
    docker_compose_command: str = ""
    docker_ps_snapshot: str = ""
    docker_logs_backend_tail: str = ""
    docker_logs_frontend_tail: str = ""
    readiness_ok: bool = False
    readiness_duration_ms: float = 0.0
    # Evidências de runtime coletadas quando readiness falha
    runtime_evidence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        result = {
            "success": self.success,
            "services_started": self.services_started,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:1000] if self.stdout else "",
            "stderr": self.stderr[:1000] if self.stderr else "",
            "duration_ms": self.duration_ms,
            "docker_compose_command": self.docker_compose_command,
            "docker_ps_snapshot": self.docker_ps_snapshot,
            "docker_logs_backend_tail": self.docker_logs_backend_tail[:500] if self.docker_logs_backend_tail else "",
            "docker_logs_frontend_tail": self.docker_logs_frontend_tail[:500] if self.docker_logs_frontend_tail else "",
            "readiness_ok": self.readiness_ok,
            "readiness_duration_ms": self.readiness_duration_ms,
        }
        if self.runtime_evidence:
            result["runtime_evidence"] = self.runtime_evidence
        return result


class DockerComposeValidator:
    """Validador de docker-compose.yml.

    Garante que:
    1. O arquivo docker-compose.yml existe
    2. Contem os servicos obrigatorios: postgres, backend, frontend
    3. Os servicos podem ser iniciados com docker compose up

    Attributes:
        generated_root: Diretorio raiz dos projetos gerados
        required_services: Lista de servicos obrigatorios
    """

    DEFAULT_GENERATED_ROOT = "/home/bazari/generated"
    REQUIRED_SERVICES = ["postgres", "backend", "frontend"]

    def __init__(
        self,
        generated_root: Optional[str] = None,
        required_services: Optional[List[str]] = None,
    ):
        """Inicializa o validador.

        Args:
            generated_root: Diretorio raiz dos projetos gerados
            required_services: Lista de servicos obrigatorios (opcional)
        """
        self.generated_root = Path(generated_root or self.DEFAULT_GENERATED_ROOT)
        self.required_services = required_services or self.REQUIRED_SERVICES.copy()

    def validate(self, project: str) -> DockerComposeValidationResult:
        """Valida o docker-compose.yml de um projeto.

        Args:
            project: Nome do projeto

        Returns:
            DockerComposeValidationResult com o resultado
        """
        repo_path = self.generated_root / project
        errors: List[str] = []
        warnings: List[str] = []

        # Verificar se o arquivo existe
        compose_file = self._find_compose_file(repo_path)
        if not compose_file:
            return DockerComposeValidationResult(
                valid=False,
                file_exists=False,
                errors=["docker-compose.yml not found"],
            )

        # Ler e parsear o arquivo
        try:
            with open(compose_file) as f:
                compose_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return DockerComposeValidationResult(
                valid=False,
                file_exists=True,
                file_path=str(compose_file),
                errors=[f"Invalid YAML: {e}"],
            )
        except Exception as e:
            return DockerComposeValidationResult(
                valid=False,
                file_exists=True,
                file_path=str(compose_file),
                errors=[f"Error reading file: {e}"],
            )

        # Verificar estrutura basica
        if not compose_data:
            return DockerComposeValidationResult(
                valid=False,
                file_exists=True,
                file_path=str(compose_file),
                errors=["Empty docker-compose.yml"],
            )

        # Verificar servicos
        services = compose_data.get("services", {})
        if not services:
            return DockerComposeValidationResult(
                valid=False,
                file_exists=True,
                file_path=str(compose_file),
                errors=["No services defined"],
            )

        # Verificar servicos obrigatorios
        services_found = list(services.keys())
        missing_services = []

        for required in self.required_services:
            if required not in services:
                # Verificar aliases comuns
                aliases = self._get_service_aliases(required)
                found_alias = None
                for alias in aliases:
                    if alias in services:
                        found_alias = alias
                        break

                if not found_alias:
                    missing_services.append(required)
                else:
                    warnings.append(f"Service '{required}' found as '{found_alias}'")

        # Verificar configuracoes basicas de cada servico
        for service_name, service_config in services.items():
            service_warnings = self._validate_service_config(service_name, service_config)
            warnings.extend(service_warnings)

        valid = len(missing_services) == 0 and len(errors) == 0

        return DockerComposeValidationResult(
            valid=valid,
            file_exists=True,
            file_path=str(compose_file),
            services_found=services_found,
            missing_services=missing_services,
            errors=errors,
            warnings=warnings,
        )

    def ensure_valid(self, project: str) -> Tuple[bool, DockerComposeValidationResult]:
        """Garante que o docker-compose.yml e valido, criando se necessario.

        Args:
            project: Nome do projeto

        Returns:
            Tupla (sucesso, resultado da validacao)
        """
        # Primeiro, validar
        result = self.validate(project)

        if result.valid:
            return True, result

        # Se o arquivo nao existe, criar um template
        if not result.file_exists:
            created = self._create_docker_compose(project)
            if created:
                result = self.validate(project)
                return result.valid, result
            return False, result

        # Se falta servicos, tentar adicionar
        if result.missing_services:
            updated = self._add_missing_services(project, result.missing_services)
            if updated:
                result = self.validate(project)
                return result.valid, result

        return False, result

    # Constantes de timeout conforme política canônica
    DOCKER_UP_TIMEOUT = 300  # 300 segundos para docker compose up
    READINESS_TIMEOUT = 240  # 240 segundos para readiness loop
    READINESS_POLL_INTERVAL = 2  # polling a cada 2s
    READINESS_FINGERPRINT = "DCV_FINGERPRINT_20260105_B"
    _LOGGER = logging.getLogger(__name__)

    def test_docker_compose_up(
        self,
        project: str,
        detach: bool = True,
        timeout: int = DOCKER_UP_TIMEOUT,
    ) -> DockerComposeUpResult:
        """Testa se docker compose up funciona.

        Args:
            project: Nome do projeto
            detach: Rodar em background (-d)
            timeout: Timeout em segundos (default: 300)

        Returns:
            DockerComposeUpResult com o resultado
        """
        repo_path = self.generated_root / project
        compose_file = self._find_compose_file(repo_path)

        if not compose_file:
            return DockerComposeUpResult(
                success=False,
                exit_code=-1,
                stderr="docker-compose.yml not found",
            )

        # Construir comando
        cmd = ["docker", "compose", "up", "--build"]
        if detach:
            cmd.append("-d")

        cmd_str = " ".join(cmd)
        start_time = datetime.now()

        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                timeout=timeout,
            )

            duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Coletar docker ps snapshot
            ps_snapshot = self._get_docker_ps_snapshot(repo_path)

            # Coletar logs dos serviços
            backend_logs = self._get_service_logs(repo_path, "backend", lines=50)
            frontend_logs = self._get_service_logs(repo_path, "frontend", lines=50)

            # Verificar servicos iniciados
            services_started = []
            if result.returncode == 0:
                # Obter lista de servicos rodando
                ps_result = subprocess.run(
                    ["docker", "compose", "ps", "--format", "{{.Service}}"],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=10,
                )
                if ps_result.returncode == 0:
                    services_started = ps_result.stdout.decode().strip().split("\n")
                    services_started = [s for s in services_started if s]

            return DockerComposeUpResult(
                success=result.returncode == 0,
                services_started=services_started,
                exit_code=result.returncode,
                stdout=result.stdout.decode(),
                stderr=result.stderr.decode(),
                duration_ms=duration_ms,
                docker_compose_command=cmd_str,
                docker_ps_snapshot=ps_snapshot,
                docker_logs_backend_tail=backend_logs,
                docker_logs_frontend_tail=frontend_logs,
            )

        except subprocess.TimeoutExpired:
            # Coletar evidências mesmo em timeout
            ps_snapshot = self._get_docker_ps_snapshot(repo_path)
            backend_logs = self._get_service_logs(repo_path, "backend", lines=50)
            frontend_logs = self._get_service_logs(repo_path, "frontend", lines=50)

            return DockerComposeUpResult(
                success=False,
                exit_code=-1,
                stderr="Command timed out",
                docker_compose_command=cmd_str,
                docker_ps_snapshot=ps_snapshot,
                docker_logs_backend_tail=backend_logs,
                docker_logs_frontend_tail=frontend_logs,
            )
        except FileNotFoundError:
            return DockerComposeUpResult(
                success=False,
                exit_code=-1,
                stderr="docker command not found",
                docker_compose_command=cmd_str,
            )
        except Exception as e:
            return DockerComposeUpResult(
                success=False,
                exit_code=-1,
                stderr=str(e),
                docker_compose_command=cmd_str,
            )

    def wait_for_readiness(
        self,
        project: str,
        timeout: int = READINESS_TIMEOUT,
        poll_interval: int = READINESS_POLL_INTERVAL,
    ) -> DockerComposeUpResult:
        """Aguarda containers ficarem prontos (readiness loop).

        Executa loop determinístico de readiness:
        - Máximo: timeout segundos (default 120)
        - Polling: poll_interval segundos (default 2)

        Critérios mínimos:
        - Backend healthcheck HTTP 200
        - Frontend responde HTTP

        Args:
            project: Nome do projeto
            timeout: Timeout máximo em segundos
            poll_interval: Intervalo entre polls em segundos

        Returns:
            DockerComposeUpResult com readiness_ok e readiness_duration_ms
        """
        import time

        repo_path = self.generated_root / project
        start_time = datetime.now()
        elapsed = 0
        iter_count = 0

        expected_services = ["backend", "frontend", "db"]

        backend_ready = False
        frontend_ready = False

        while elapsed < timeout:
            if iter_count == 0:
                try:
                    fingerprint_line = (
                        f"[READINESS][FINGERPRINT] {self.READINESS_FINGERPRINT} file={__file__}"
                    )
                    print(fingerprint_line, file=sys.stderr, flush=True)
                    (repo_path / ".engine_readiness_fingerprint.txt").write_text(
                        fingerprint_line + "\n", encoding="utf-8"
                    )
                except Exception:
                    pass

            iter_count += 1
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            self._LOGGER.info(
                "[READINESS][LOOP] iter=%s elapsed_ms=%s timeout_ms=%s",
                iter_count,
                elapsed_ms,
                int(timeout * 1000),
            )
            print(
                f"[READINESS][LOOP] iter={iter_count} elapsed_ms={elapsed_ms} timeout_ms={int(timeout * 1000)}",
                file=sys.stderr,
                flush=True,
            )

            docker_services: List[str] = []
            docker_raw = ""
            try:
                ps_result = subprocess.run(
                    ["docker", "compose", "ps", "--format", "{{.Service}}"],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=10,
                )
                docker_raw = ps_result.stdout.decode()
                if ps_result.returncode == 0:
                    docker_services = [s for s in docker_raw.strip().split("\n") if s]
            except Exception as e:
                docker_raw = repr(e)

            self._LOGGER.info(
                "[READINESS][DOCKER_PS] services=%s count=%s",
                docker_services,
                len(docker_services),
            )
            self._LOGGER.debug("[READINESS][DOCKER_PS_RAW] %s", docker_raw)
            print(
                f"[READINESS][DOCKER_PS] services={docker_services} count={len(docker_services)}",
                file=sys.stderr,
                flush=True,
            )
            if docker_raw:
                self._LOGGER.debug("[READINESS][DOCKER_PS_RAW] %s", docker_raw)

            if set(expected_services) - set(docker_services):
                self._LOGGER.info(
                    "[READINESS][GATE] BLOCKED_BY_DOCKER_PS expected=%s got=%s",
                    expected_services,
                    docker_services,
                )
                print(
                    f"[READINESS][GATE] BLOCKED_BY_DOCKER_PS expected={expected_services} got={docker_services}",
                    file=sys.stderr,
                    flush=True,
                )

            # Verificar backend (porta 8080)
            if not backend_ready:
                http_start = time.monotonic()
                try:
                    req = urllib.request.Request(
                        "http://localhost:8080/actuator/health",
                        method="GET",
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        if resp.status == 200:
                            backend_ready = True
                        self._LOGGER.info(
                            "[READINESS][HTTP_CHECK] name=backend url=%s status=%s error=%s elapsed_ms=%s",
                            "http://localhost:8080/actuator/health",
                            getattr(resp, "status", None),
                            None,
                            int((time.monotonic() - http_start) * 1000),
                        )
                        print(
                            f"[READINESS][HTTP_CHECK] name=backend url=http://localhost:8080/actuator/health status={getattr(resp, 'status', None)} err=None elapsed_ms={int((time.monotonic() - http_start) * 1000)}",
                            file=sys.stderr,
                            flush=True,
                        )
                except (urllib.error.URLError, Exception) as exc:
                    self._LOGGER.info(
                        "[READINESS][HTTP_CHECK] name=backend url=%s status=%s error=%s elapsed_ms=%s",
                        "http://localhost:8080/actuator/health",
                        None,
                        repr(exc),
                        int((time.monotonic() - http_start) * 1000),
                    )
                    print(
                        f"[READINESS][HTTP_CHECK] name=backend url=http://localhost:8080/actuator/health status=None err={repr(exc)} elapsed_ms={int((time.monotonic() - http_start) * 1000)}",
                        file=sys.stderr,
                        flush=True,
                    )

            # Verificar frontend (porta 5173 - mapeada no docker-compose)
            if not frontend_ready:
                http_start = time.monotonic()
                try:
                    req = urllib.request.Request(
                        "http://localhost:5173/",
                        method="GET",
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        if resp.status in (200, 304):
                            frontend_ready = True
                        self._LOGGER.info(
                            "[READINESS][HTTP_CHECK] name=frontend url=%s status=%s error=%s elapsed_ms=%s",
                            "http://localhost:5173/",
                            getattr(resp, "status", None),
                            None,
                            int((time.monotonic() - http_start) * 1000),
                        )
                        print(
                            f"[READINESS][HTTP_CHECK] name=frontend url=http://localhost:5173/ status={getattr(resp, 'status', None)} err=None elapsed_ms={int((time.monotonic() - http_start) * 1000)}",
                            file=sys.stderr,
                            flush=True,
                        )
                except (urllib.error.URLError, Exception) as exc:
                    self._LOGGER.info(
                        "[READINESS][HTTP_CHECK] name=frontend url=%s status=%s error=%s elapsed_ms=%s",
                        "http://localhost:5173/",
                        None,
                        repr(exc),
                        int((time.monotonic() - http_start) * 1000),
                    )
                    print(
                        f"[READINESS][HTTP_CHECK] name=frontend url=http://localhost:5173/ status=None err={repr(exc)} elapsed_ms={int((time.monotonic() - http_start) * 1000)}",
                        file=sys.stderr,
                        flush=True,
                    )

            # Ambos prontos?
            docker_ok = not (set(expected_services) - set(docker_services))
            http_ok = backend_ready and frontend_ready
            ready = docker_ok and http_ok

            self._LOGGER.info(
                "[READINESS][DECISION] docker_ok=%s http_ok=%s ready=%s",
                str(docker_ok).lower(),
                str(http_ok).lower(),
                str(ready).lower(),
            )
            print(
                f"[READINESS][DECISION] docker_ok={str(docker_ok).lower()} http_ok={str(http_ok).lower()} ready={str(ready).lower()}",
                file=sys.stderr,
                flush=True,
            )

            if backend_ready and frontend_ready:
                break

            time.sleep(poll_interval)
            elapsed = (datetime.now() - start_time).total_seconds()

        readiness_duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        readiness_ok = backend_ready and frontend_ready

        # Coletar evidências finais
        ps_snapshot = self._get_docker_ps_snapshot(repo_path)
        backend_logs = self._get_service_logs(repo_path, "backend", lines=50)
        frontend_logs = self._get_service_logs(repo_path, "frontend", lines=50)

        # Obter serviços rodando
        services_started = []
        try:
            ps_result = subprocess.run(
                ["docker", "compose", "ps", "--format", "{{.Service}}"],
                cwd=repo_path,
                capture_output=True,
                timeout=10,
            )
            if ps_result.returncode == 0:
                services_started = ps_result.stdout.decode().strip().split("\n")
                services_started = [s for s in services_started if s]
        except Exception:
            pass

        # COLETAR EVIDÊNCIAS DE RUNTIME SE READINESS FALHOU OU BACKEND SUMIU
        runtime_evidence = None
        need_evidence = (not readiness_ok) or ("backend" not in services_started)
        if need_evidence:
            evidence_dir = repo_path / ".engine_evidence"
            try:
                evidence_dir.mkdir(parents=True, exist_ok=True)
                runtime_evidence = collect_runtime_evidence(
                    repo_path=str(repo_path),
                    compose_file="docker-compose.yml",
                    services=["backend", "frontend", "db"],
                    out_dir=evidence_dir,
                )
                self._LOGGER.info(
                    "[READINESS][EVIDENCE] Classificação: %s - %s",
                    runtime_evidence.get("conclusion_hint", {}).get("classification", "UNKNOWN"),
                    runtime_evidence.get("conclusion_hint", {}).get("reason", "N/A"),
                )
            except Exception as e:
                self._LOGGER.error("[READINESS][EVIDENCE] Erro ao coletar evidências: %s", e)
                minimal = {
                    "timestamp": datetime.now().isoformat(),
                    "repo_path": str(repo_path),
                    "fingerprint": self.READINESS_FINGERPRINT,
                    "error": repr(e),
                }
                try:
                    evidence_dir.mkdir(parents=True, exist_ok=True)
                    (evidence_dir / "runtime_evidence_minimal.json").write_text(
                        json.dumps(minimal, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                runtime_evidence = minimal

        result = DockerComposeUpResult(
            success=readiness_ok,
            services_started=services_started,
            readiness_ok=readiness_ok,
            readiness_duration_ms=readiness_duration_ms,
            docker_ps_snapshot=ps_snapshot,
            docker_logs_backend_tail=backend_logs,
            docker_logs_frontend_tail=frontend_logs,
        )

        # Anexar evidências ao resultado
        if runtime_evidence:
            result.runtime_evidence = runtime_evidence  # type: ignore

        return result

    def _get_docker_ps_snapshot(self, repo_path: Path) -> str:
        """Obtém snapshot do docker compose ps."""
        try:
            result = subprocess.run(
                ["docker", "compose", "ps"],
                cwd=repo_path,
                capture_output=True,
                timeout=10,
            )
            return result.stdout.decode() if result.returncode == 0 else ""
        except Exception:
            return ""

    def _get_service_logs(self, repo_path: Path, service: str, lines: int = 50) -> str:
        """Obtém últimas linhas de log de um serviço."""
        try:
            result = subprocess.run(
                ["docker", "compose", "logs", "--tail", str(lines), service],
                cwd=repo_path,
                capture_output=True,
                timeout=10,
            )
            return result.stdout.decode() if result.returncode == 0 else ""
        except Exception:
            return ""

    def stop_services(self, project: str, timeout: int = 30) -> bool:
        """Para os servicos do docker compose.

        Args:
            project: Nome do projeto
            timeout: Timeout em segundos

        Returns:
            True se parou com sucesso
        """
        repo_path = self.generated_root / project

        try:
            result = subprocess.run(
                ["docker", "compose", "down"],
                cwd=repo_path,
                capture_output=True,
                timeout=timeout,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _find_compose_file(self, repo_path: Path) -> Optional[Path]:
        """Encontra o arquivo docker-compose.yml."""
        candidates = [
            repo_path / "docker-compose.yml",
            repo_path / "docker-compose.yaml",
            repo_path / "compose.yml",
            repo_path / "compose.yaml",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _get_service_aliases(self, service: str) -> List[str]:
        """Retorna aliases comuns para um servico."""
        aliases = {
            "postgres": ["postgresql", "db", "database", "pg"],
            "backend": ["api", "server", "app", "service"],
            "frontend": ["web", "ui", "client", "webapp"],
        }
        return aliases.get(service, [])

    def _validate_service_config(
        self,
        service_name: str,
        service_config: Dict[str, Any],
    ) -> List[str]:
        """Valida configuracao de um servico."""
        warnings = []

        if not service_config:
            warnings.append(f"Service '{service_name}' has empty configuration")
            return warnings

        # Verificar se tem image ou build
        if "image" not in service_config and "build" not in service_config:
            warnings.append(f"Service '{service_name}' has no image or build defined")

        # Verificar portas para servicos que precisam
        if service_name in ["backend", "api", "server"]:
            if "ports" not in service_config:
                warnings.append(f"Service '{service_name}' has no ports exposed")

        if service_name in ["frontend", "web", "ui"]:
            if "ports" not in service_config:
                warnings.append(f"Service '{service_name}' has no ports exposed")

        return warnings

    def _create_docker_compose(self, project: str) -> bool:
        """Cria um docker-compose.yml basico."""
        repo_path = self.generated_root / project
        compose_file = repo_path / "docker-compose.yml"

        # Determinar configuracoes baseadas na estrutura do projeto
        has_backend = (repo_path / "backend").exists()
        has_frontend = (repo_path / "frontend").exists()

        compose_content = self._generate_compose_content(
            project,
            has_backend=has_backend,
            has_frontend=has_frontend,
        )

        try:
            repo_path.mkdir(parents=True, exist_ok=True)
            with open(compose_file, "w") as f:
                f.write(compose_content)
            return True
        except Exception:
            return False

    def _add_missing_services(self, project: str, missing: List[str]) -> bool:
        """Adiciona servicos faltando ao docker-compose.yml."""
        repo_path = self.generated_root / project
        compose_file = self._find_compose_file(repo_path)

        if not compose_file:
            return False

        try:
            with open(compose_file) as f:
                compose_data = yaml.safe_load(f) or {}

            if "services" not in compose_data:
                compose_data["services"] = {}

            for service in missing:
                if service not in compose_data["services"]:
                    compose_data["services"][service] = self._get_service_template(service)

            with open(compose_file, "w") as f:
                yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)

            return True
        except Exception:
            return False

    def _generate_compose_content(
        self,
        project: str,
        has_backend: bool = True,
        has_frontend: bool = True,
    ) -> str:
        """Gera conteudo do docker-compose.yml."""
        content = f"""version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: {project}-postgres
    environment:
      POSTGRES_DB: {project}
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

"""

        if has_backend:
            content += f"""  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: {project}-backend
    environment:
      SPRING_DATASOURCE_URL: jdbc:postgresql://postgres:5432/{project}
      SPRING_DATASOURCE_USERNAME: postgres
      SPRING_DATASOURCE_PASSWORD: postgres
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy

"""

        if has_frontend:
            content += f"""  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: {project}-frontend
    environment:
      VITE_API_URL: http://localhost:8080
    ports:
      - "3000:3000"
    depends_on:
      - backend

"""

        content += """volumes:
  postgres_data:
"""

        return content

    def _get_service_template(self, service: str) -> Dict[str, Any]:
        """Retorna template para um servico."""
        templates = {
            "postgres": {
                "image": "postgres:15-alpine",
                "environment": {
                    "POSTGRES_DB": "app",
                    "POSTGRES_USER": "postgres",
                    "POSTGRES_PASSWORD": "postgres",
                },
                "ports": ["5432:5432"],
                "volumes": ["postgres_data:/var/lib/postgresql/data"],
            },
            "backend": {
                "build": {
                    "context": "./backend",
                    "dockerfile": "Dockerfile",
                },
                "ports": ["8080:8080"],
                "depends_on": ["postgres"],
            },
            "frontend": {
                "build": {
                    "context": "./frontend",
                    "dockerfile": "Dockerfile",
                },
                "ports": ["3000:3000"],
                "depends_on": ["backend"],
            },
        }

        return templates.get(service, {"image": "alpine:latest"})


    def validate_build_contexts(
        self,
        project: str,
        compose_file_path: Optional[str] = None,
    ) -> DockerContextValidationResult:
        """Gate: Valida se todos os build contexts e Dockerfiles existem.

        Este gate é determinístico e deve ser executado ANTES de `docker compose up`.
        Se falhar, o release deve abortar com status DOCKER_UP_FAILED.

        Validações:
        1. Build context (diretório) existe
        2. Dockerfile existe dentro do context (ou no path especificado)

        Args:
            project: Nome do projeto
            compose_file_path: Path opcional do docker-compose.yml (auto-detectado se não fornecido)

        Returns:
            DockerContextValidationResult com:
            - valid: True se todos os contexts e Dockerfiles existem
            - compose_file_path: Path do arquivo compose usado
            - resolved_context_paths: Lista de paths de contexts resolvidos que existem
            - missing_context_paths: Lista de paths de contexts que não existem
            - resolved_dockerfile_paths: Lista de paths de Dockerfiles que existem
            - missing_dockerfile_paths: Lista de paths de Dockerfiles que não existem
            - errors: Lista de erros encontrados
        """
        repo_path = self.generated_root / project
        errors: List[str] = []
        resolved_context_paths: List[str] = []
        missing_context_paths: List[str] = []
        resolved_dockerfile_paths: List[str] = []
        missing_dockerfile_paths: List[str] = []

        # Encontrar arquivo compose
        if compose_file_path:
            compose_file = Path(compose_file_path)
            if not compose_file.exists():
                return DockerContextValidationResult(
                    valid=False,
                    compose_file_path=compose_file_path,
                    errors=[f"Compose file not found: {compose_file_path}"],
                )
        else:
            compose_file = self._find_compose_file(repo_path)
            if not compose_file:
                return DockerContextValidationResult(
                    valid=False,
                    errors=["docker-compose.yml not found in project"],
                )

        compose_dir = compose_file.parent

        # Ler e parsear o arquivo
        try:
            with open(compose_file) as f:
                compose_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return DockerContextValidationResult(
                valid=False,
                compose_file_path=str(compose_file),
                errors=[f"Invalid YAML: {e}"],
            )
        except Exception as e:
            return DockerContextValidationResult(
                valid=False,
                compose_file_path=str(compose_file),
                errors=[f"Error reading file: {e}"],
            )

        if not compose_data:
            return DockerContextValidationResult(
                valid=False,
                compose_file_path=str(compose_file),
                errors=["Empty docker-compose.yml"],
            )

        # Extrair services
        services = compose_data.get("services", {})
        if not services:
            return DockerContextValidationResult(
                valid=False,
                compose_file_path=str(compose_file),
                errors=["No services defined in docker-compose.yml"],
            )

        # Verificar build contexts e Dockerfiles de cada serviço
        for service_name, service_config in services.items():
            if not service_config:
                continue

            build_config = service_config.get("build")
            if not build_config:
                # Serviço usa image:, não build: - ok, não precisa validar context
                continue

            # build pode ser string (context direto) ou dict com context key
            if isinstance(build_config, str):
                context_path = build_config
                dockerfile_name = "Dockerfile"  # default
            elif isinstance(build_config, dict):
                context_path = build_config.get("context", ".")
                dockerfile_name = build_config.get("dockerfile", "Dockerfile")
            else:
                errors.append(f"Service '{service_name}': invalid build configuration type")
                continue

            # Resolver context path relativo ao diretório do compose file
            if context_path.startswith("/"):
                resolved_context = Path(context_path)
            else:
                resolved_context = (compose_dir / context_path).resolve()

            resolved_context_str = str(resolved_context)

            # 1. Verificar existência do context (diretório)
            if resolved_context.exists() and resolved_context.is_dir():
                resolved_context_paths.append(resolved_context_str)
            else:
                missing_context_paths.append(resolved_context_str)
                errors.append(
                    f"Service '{service_name}': build context not found: {context_path} "
                    f"(resolved to: {resolved_context_str})"
                )
                # Se context não existe, não faz sentido verificar Dockerfile
                continue

            # 2. Verificar existência do Dockerfile dentro do context
            if dockerfile_name.startswith("/"):
                # Path absoluto do Dockerfile (raro, mas possível)
                resolved_dockerfile = Path(dockerfile_name)
            else:
                # Path relativo ao context
                resolved_dockerfile = resolved_context / dockerfile_name

            resolved_dockerfile_str = str(resolved_dockerfile)

            if resolved_dockerfile.exists() and resolved_dockerfile.is_file():
                resolved_dockerfile_paths.append(resolved_dockerfile_str)
            else:
                missing_dockerfile_paths.append(resolved_dockerfile_str)
                errors.append(
                    f"Dockerfile missing for service '{service_name}': {resolved_dockerfile_str}"
                )

        # Validar nginx.conf do frontend (obrigatório para proxy /api/)
        nginx_conf_valid = False
        nginx_conf_path = ""
        frontend_context = None

        # Encontrar o context do frontend
        frontend_service = services.get("frontend", {})
        if frontend_service:
            build_config = frontend_service.get("build", {})
            if isinstance(build_config, str):
                frontend_context = compose_dir / build_config
            elif isinstance(build_config, dict):
                context_path = build_config.get("context", ".")
                frontend_context = compose_dir / context_path

        if frontend_context and frontend_context.exists():
            nginx_conf_file = frontend_context / "nginx.conf"
            nginx_conf_path = str(nginx_conf_file)

            if nginx_conf_file.exists():
                # Validar conteúdo do nginx.conf
                try:
                    nginx_content = nginx_conf_file.read_text()

                    has_api_location = "location /api/" in nginx_content
                    has_proxy_pass = "proxy_pass http://backend" in nginx_content

                    if has_api_location and has_proxy_pass:
                        nginx_conf_valid = True
                    else:
                        if not has_api_location:
                            errors.append(
                                f"nginx.conf missing 'location /api/' block: {nginx_conf_path}"
                            )
                        if not has_proxy_pass:
                            errors.append(
                                f"nginx.conf missing 'proxy_pass http://backend': {nginx_conf_path}"
                            )
                except Exception as e:
                    errors.append(f"Error reading nginx.conf: {e}")
            else:
                errors.append(f"nginx.conf not found in frontend context: {nginx_conf_path}")

        # Válido apenas se não há contexts nem Dockerfiles faltando E nginx.conf válido
        valid = (
            len(missing_context_paths) == 0
            and len(missing_dockerfile_paths) == 0
            and nginx_conf_valid
        )

        return DockerContextValidationResult(
            valid=valid,
            compose_file_path=str(compose_file),
            resolved_context_paths=resolved_context_paths,
            missing_context_paths=missing_context_paths,
            resolved_dockerfile_paths=resolved_dockerfile_paths,
            missing_dockerfile_paths=missing_dockerfile_paths,
            nginx_conf_valid=nginx_conf_valid,
            nginx_conf_path=nginx_conf_path,
            errors=errors,
        )


def validate_build_contexts(project: str) -> dict:
    """Função de conveniência para validar build contexts do docker-compose.

    Gate pré-docker que verifica se todos os build contexts existem.

    Args:
        project: Nome do projeto

    Returns:
        Dicionário com resultado da validação
    """
    validator = DockerComposeValidator()
    result = validator.validate_build_contexts(project)
    return result.to_dict()


def validate_docker_compose(project: str) -> dict:
    """Funcao de conveniencia para validar docker-compose.

    Args:
        project: Nome do projeto

    Returns:
        Dicionario com resultado da validacao
    """
    validator = DockerComposeValidator()
    result = validator.validate(project)
    return result.to_dict()


def ensure_docker_compose(project: str) -> Tuple[bool, dict]:
    """Funcao de conveniencia para garantir docker-compose valido.

    Args:
        project: Nome do projeto

    Returns:
        Tupla (sucesso, resultado)
    """
    validator = DockerComposeValidator()
    success, result = validator.ensure_valid(project)
    return success, result.to_dict()
