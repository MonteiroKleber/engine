"""Runtime Evidence Collector - Coleta evidências de crash de containers.

Objetivo: Provar a causa de crashes de containers durante o release,
coletando evidências objetivas de runtime (ExitCode, OOMKilled, logs, events).

Uso: Chamado automaticamente quando readiness falha ou backend desaparece.
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

_LOGGER = logging.getLogger(__name__)


@dataclass
class SubprocessResult:
    """Resultado de um comando subprocess."""
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    command: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "command": self.command,
            "error": self.error,
        }


def _run_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    timeout: int = 5,
) -> SubprocessResult:
    """Executa comando de forma segura, nunca lançando exceção.

    Args:
        cmd: Lista de argumentos do comando
        cwd: Diretório de trabalho
        timeout: Timeout em segundos

    Returns:
        SubprocessResult com ok=False se falhar
    """
    cmd_str = " ".join(cmd)
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        return SubprocessResult(
            ok=result.returncode == 0,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.returncode,
            command=cmd_str,
        )
    except subprocess.TimeoutExpired as e:
        return SubprocessResult(
            ok=False,
            stdout=e.stdout.decode() if e.stdout else "",
            stderr=e.stderr.decode() if e.stderr else "",
            exit_code=-1,
            command=cmd_str,
            error=f"TimeoutExpired after {timeout}s",
        )
    except FileNotFoundError:
        return SubprocessResult(
            ok=False,
            stdout="",
            stderr="",
            exit_code=-1,
            command=cmd_str,
            error="Command not found",
        )
    except Exception as e:
        return SubprocessResult(
            ok=False,
            stdout="",
            stderr="",
            exit_code=-1,
            command=cmd_str,
            error=repr(e),
        )


def _parse_inspect_state(inspect_json: str) -> Dict[str, Any]:
    """Parseia output do docker inspect e extrai campos relevantes.

    Args:
        inspect_json: Output JSON do docker inspect

    Returns:
        Dicionário com campos parseados
    """
    try:
        data = json.loads(inspect_json)
        if not data or not isinstance(data, list) or len(data) == 0:
            return {"parse_error": "Empty or invalid inspect output"}

        container = data[0]
        state = container.get("State", {})
        host_config = container.get("HostConfig", {})
        config = container.get("Config", {})

        # Extrair variáveis de ambiente relevantes (mascarar segredos)
        env_vars = config.get("Env", [])
        relevant_env = []
        for var in env_vars:
            if var.startswith(("SPRING_", "JAVA_", "JVM_", "POSTGRES_")):
                # Mascarar valores de senha
                if "PASSWORD" in var.upper() or "SECRET" in var.upper():
                    key = var.split("=")[0]
                    relevant_env.append(f"{key}=***MASKED***")
                else:
                    relevant_env.append(var)

        return {
            "status": state.get("Status"),
            "running": state.get("Running"),
            "exit_code": state.get("ExitCode"),
            "oom_killed": state.get("OOMKilled"),
            "error": state.get("Error"),
            "finished_at": state.get("FinishedAt"),
            "started_at": state.get("StartedAt"),
            "restart_policy": host_config.get("RestartPolicy"),
            "restart_count": container.get("RestartCount"),
            "relevant_env": relevant_env,
        }
    except json.JSONDecodeError as e:
        return {"parse_error": f"JSON decode error: {e}"}
    except Exception as e:
        return {"parse_error": repr(e)}


def _classify_failure(
    inspect_parsed: Dict[str, Any],
    docker_events_stdout: str,
    host_oom_stdout: str,
    backend_logs_stdout: str,
) -> Dict[str, str]:
    """Classifica a falha baseado em evidências coletadas.

    Regras (em ordem de prioridade):
    1. OOM: inspect.oom_killed=true OU docker events contém "oom" OU dmesg contém "Killed process"
    2. APP_EXCEPTION: ExitCode != 0 e logs têm stacktrace (Exception/Error)
    3. RESTART_LOOP: RestartCount > 0 OU events mostram die/restart repetido
    4. EXIT_CODE: ExitCode != 0 sem logs
    5. UNKNOWN: demais casos

    Returns:
        {"classification": "...", "reason": "..."}
    """
    classification = "UNKNOWN"
    reason = "Sem evidência conclusiva"

    oom_killed = inspect_parsed.get("oom_killed", False)
    exit_code = inspect_parsed.get("exit_code")
    restart_count = inspect_parsed.get("restart_count", 0) or 0

    # 1. Verificar OOM
    oom_indicators = []
    if oom_killed:
        oom_indicators.append("docker inspect OOMKilled=true")
    if "oom" in docker_events_stdout.lower():
        oom_indicators.append("docker events contém 'oom'")
    if re.search(r"killed process.*java|out of memory", host_oom_stdout, re.IGNORECASE):
        oom_indicators.append("dmesg indica OOM kill")

    if oom_indicators:
        classification = "OOM"
        reason = "; ".join(oom_indicators)
        return {"classification": classification, "reason": reason}

    # 2. Verificar APP_EXCEPTION
    if exit_code is not None and exit_code != 0:
        # Procurar stacktrace nos logs
        exception_patterns = [
            r"Exception",
            r"Error:",
            r"at\s+[\w.]+\(",  # stacktrace line
            r"Caused by:",
            r"java\.\w+Exception",
            r"org\.springframework\.\w+Exception",
        ]
        has_exception = any(
            re.search(pattern, backend_logs_stdout, re.IGNORECASE)
            for pattern in exception_patterns
        )
        if has_exception:
            classification = "APP_EXCEPTION"
            reason = f"ExitCode={exit_code} com stacktrace/exception nos logs"
            return {"classification": classification, "reason": reason}

    # 3. Verificar RESTART_LOOP
    if restart_count > 0:
        classification = "RESTART_LOOP"
        reason = f"RestartCount={restart_count}"
        return {"classification": classification, "reason": reason}

    # Contar eventos die nos docker events
    die_count = docker_events_stdout.lower().count("die")
    if die_count > 1:
        classification = "RESTART_LOOP"
        reason = f"Múltiplos eventos 'die' detectados ({die_count})"
        return {"classification": classification, "reason": reason}

    # 4. Verificar EXIT_CODE
    if exit_code is not None and exit_code != 0:
        classification = "EXIT_CODE"
        reason = f"ExitCode={exit_code} sem stacktrace nos logs"
        return {"classification": classification, "reason": reason}

    return {"classification": classification, "reason": reason}


def collect_runtime_evidence(
    repo_path: str,
    compose_file: str = "docker-compose.yml",
    services: Optional[List[str]] = None,
    out_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Coleta evidências de runtime para diagnóstico de crash.

    Args:
        repo_path: Caminho do repositório com docker-compose
        compose_file: Nome do arquivo docker-compose (default: docker-compose.yml)
        services: Lista de serviços a investigar (default: ["backend"])
        out_dir: Diretório para salvar evidências (opcional)

    Returns:
        Dicionário com todas as evidências coletadas
    """
    if out_dir is not None and not isinstance(out_dir, Path):
        out_dir = Path(out_dir)

    if services is None:
        services = ["backend"]

    repo = Path(repo_path)
    compose_path = repo / compose_file
    timestamp = datetime.now().isoformat()

    _LOGGER.info("[EVIDENCE] Iniciando coleta de evidências em %s", repo_path)

    evidence: Dict[str, Any] = {
        "timestamp": timestamp,
        "repo_path": str(repo_path),
        "compose_file": compose_file,
        "compose_ps": {},
        "backend": {
            "container_id": None,
            "inspect": {"ok": False, "raw": "", "parsed": {}},
            "logs": {"ok": False, "stdout": "", "stderr": "", "exit_code": -1},
        },
        "docker_events": {"ok": False, "stdout": "", "stderr": "", "exit_code": -1},
        "host_oom": {"ok": False, "stdout": "", "stderr": "", "exit_code": -1},
        "conclusion_hint": {"classification": "UNKNOWN", "reason": "Coleta não completada"},
    }

    # A) Docker Compose ps -a (estado completo)
    _LOGGER.info("[EVIDENCE] Coletando docker compose ps -a")
    ps_result = _run_command(
        ["docker", "compose", "-f", compose_file, "ps", "-a"],
        cwd=repo,
        timeout=10,
    )
    evidence["compose_ps"] = ps_result.to_dict()

    # B) Descobrir container ID do backend
    _LOGGER.info("[EVIDENCE] Descobrindo container ID do backend")
    id_result = _run_command(
        ["docker", "compose", "-f", compose_file, "ps", "-q", "backend"],
        cwd=repo,
        timeout=5,
    )

    container_id = None
    if id_result.ok and id_result.stdout.strip():
        container_id = id_result.stdout.strip().split("\n")[0]
        evidence["backend"]["container_id"] = container_id
        _LOGGER.info("[EVIDENCE] Backend container ID: %s", container_id)
    else:
        # Tentar via docker ps -a com filtro
        _LOGGER.info("[EVIDENCE] Tentando descobrir container ID via docker ps -a")
        ps_all_result = _run_command(
            ["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project.working_dir={repo}",
             "--filter", "label=com.docker.compose.service=backend", "-q"],
            timeout=5,
        )
        if ps_all_result.ok and ps_all_result.stdout.strip():
            container_id = ps_all_result.stdout.strip().split("\n")[0]
            evidence["backend"]["container_id"] = container_id
            _LOGGER.info("[EVIDENCE] Backend container ID (via ps -a): %s", container_id)
        else:
            _LOGGER.warning("[EVIDENCE] Backend container ID não encontrado")
            evidence["backend"]["container_id"] = None

    # C) Docker inspect do backend
    if container_id:
        _LOGGER.info("[EVIDENCE] Executando docker inspect %s", container_id)
        inspect_result = _run_command(
            ["docker", "inspect", container_id],
            timeout=5,
        )
        evidence["backend"]["inspect"] = {
            "ok": inspect_result.ok,
            "exit_code": inspect_result.exit_code,
            "raw": inspect_result.stdout[:5000] if inspect_result.stdout else "",
            "parsed": _parse_inspect_state(inspect_result.stdout) if inspect_result.ok else {},
            "error": inspect_result.error,
        }
    else:
        evidence["backend"]["inspect"] = {
            "ok": False,
            "exit_code": -1,
            "raw": "",
            "parsed": {},
            "error": "Container ID não encontrado",
        }

    # D) Logs do backend
    _LOGGER.info("[EVIDENCE] Coletando logs do backend")
    logs_result = _run_command(
        ["docker", "compose", "-f", compose_file, "logs", "-t", "--no-color", "--tail", "400", "backend"],
        cwd=repo,
        timeout=10,
    )
    evidence["backend"]["logs"] = logs_result.to_dict()

    # E) Docker events (últimos 10 minutos, com timeout curto)
    _LOGGER.info("[EVIDENCE] Coletando docker events")
    events_result = _run_command(
        [
            "docker", "events",
            "--since", "10m",
            "--filter", "type=container",
            "--filter", "event=die",
            "--filter", "event=oom",
            "--filter", "event=kill",
            "--format", "{{.Time}} {{.Actor.Attributes.name}} {{.Action}} exitCode={{.Actor.Attributes.exitCode}}",
        ],
        timeout=3,  # Timeout curto pois events bloqueia
    )
    evidence["docker_events"] = events_result.to_dict()

    # F) Evidência de OOM no host (melhor esforço)
    _LOGGER.info("[EVIDENCE] Verificando OOM no host via dmesg")
    oom_result = _run_command(
        ["dmesg", "-T"],
        timeout=5,
    )
    if oom_result.ok:
        # Filtrar apenas linhas relevantes
        oom_lines = []
        for line in oom_result.stdout.split("\n"):
            if re.search(r"killed process|oom|out of memory", line, re.IGNORECASE):
                oom_lines.append(line)
        evidence["host_oom"] = {
            "ok": True,
            "stdout": "\n".join(oom_lines[-50:]) if oom_lines else "(nenhuma evidência de OOM)",
            "stderr": oom_result.stderr,
            "exit_code": oom_result.exit_code,
        }
    else:
        evidence["host_oom"] = {
            "ok": False,
            "stdout": "",
            "stderr": oom_result.stderr or oom_result.error,
            "exit_code": oom_result.exit_code,
            "error": oom_result.error or "permission denied ou comando não disponível",
        }

    # Classificar a falha
    inspect_parsed = evidence["backend"]["inspect"].get("parsed", {})
    evidence["conclusion_hint"] = _classify_failure(
        inspect_parsed,
        evidence["docker_events"].get("stdout", ""),
        evidence["host_oom"].get("stdout", ""),
        evidence["backend"]["logs"].get("stdout", ""),
    )

    _LOGGER.info(
        "[EVIDENCE] Classificação: %s - %s",
        evidence["conclusion_hint"]["classification"],
        evidence["conclusion_hint"]["reason"],
    )

    # Salvar evidências se out_dir fornecido
    if out_dir:
        _save_evidence(evidence, out_dir)

    return evidence


def _save_evidence(evidence: Dict[str, Any], out_dir: Path) -> None:
    """Salva evidências em JSON e Markdown.

    Args:
        evidence: Dicionário com evidências coletadas
        out_dir: Diretório de saída
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Salvar JSON
    json_path = out_dir / f"runtime_evidence_{timestamp_str}.json"
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, ensure_ascii=False)
        _LOGGER.info("[EVIDENCE] JSON salvo em %s", json_path)
    except Exception as e:
        _LOGGER.error("[EVIDENCE] Erro ao salvar JSON: %s", e)

    # Salvar Markdown
    md_path = out_dir / f"runtime_evidence_{timestamp_str}.md"
    try:
        md_content = _generate_markdown_report(evidence)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        _LOGGER.info("[EVIDENCE] Markdown salvo em %s", md_path)
    except Exception as e:
        _LOGGER.error("[EVIDENCE] Erro ao salvar Markdown: %s", e)


def _generate_markdown_report(evidence: Dict[str, Any]) -> str:
    """Gera relatório Markdown das evidências.

    Args:
        evidence: Dicionário com evidências coletadas

    Returns:
        String com conteúdo Markdown
    """
    lines = [
        "# Runtime Evidence Report",
        "",
        f"**Timestamp:** {evidence.get('timestamp', 'N/A')}",
        f"**Repo Path:** {evidence.get('repo_path', 'N/A')}",
        "",
        "---",
        "",
        "## Classificação da Falha",
        "",
        f"**Classification:** `{evidence['conclusion_hint']['classification']}`",
        f"**Reason:** {evidence['conclusion_hint']['reason']}",
        "",
        "---",
        "",
        "## Backend Container",
        "",
        f"**Container ID:** `{evidence['backend'].get('container_id') or 'NÃO ENCONTRADO'}`",
        "",
    ]

    # Inspect parsed
    inspect = evidence["backend"].get("inspect", {})
    parsed = inspect.get("parsed", {})
    if parsed and "parse_error" not in parsed:
        lines.extend([
            "### Docker Inspect",
            "",
            "| Campo | Valor |",
            "|-------|-------|",
            f"| Status | `{parsed.get('status', 'N/A')}` |",
            f"| Running | `{parsed.get('running', 'N/A')}` |",
            f"| **ExitCode** | `{parsed.get('exit_code', 'N/A')}` |",
            f"| **OOMKilled** | `{parsed.get('oom_killed', 'N/A')}` |",
            f"| Error | `{parsed.get('error', '') or '(vazio)'}` |",
            f"| FinishedAt | `{parsed.get('finished_at', 'N/A')}` |",
            f"| StartedAt | `{parsed.get('started_at', 'N/A')}` |",
            f"| **RestartCount** | `{parsed.get('restart_count', 'N/A')}` |",
            f"| RestartPolicy | `{parsed.get('restart_policy', 'N/A')}` |",
            "",
        ])

        # Variáveis de ambiente relevantes
        if parsed.get("relevant_env"):
            lines.extend([
                "### Variáveis de Ambiente Relevantes",
                "",
                "```",
            ])
            lines.extend(parsed["relevant_env"][:10])
            lines.extend(["```", ""])
    else:
        lines.extend([
            "### Docker Inspect",
            "",
            f"**Erro:** {inspect.get('error', 'N/A')}",
            "",
        ])

    # Logs do backend (últimas 30 linhas)
    logs = evidence["backend"].get("logs", {})
    logs_stdout = logs.get("stdout", "")
    if logs_stdout:
        log_lines = logs_stdout.strip().split("\n")
        last_lines = log_lines[-30:]
        lines.extend([
            "---",
            "",
            "## Backend Logs (últimas 30 linhas)",
            "",
            "```",
        ])
        lines.extend(last_lines)
        lines.extend(["```", ""])
    else:
        lines.extend([
            "---",
            "",
            "## Backend Logs",
            "",
            f"**Status:** {'OK' if logs.get('ok') else 'FALHOU'}",
            f"**Erro:** {logs.get('error', logs.get('stderr', 'N/A'))}",
            "",
        ])

    # Docker events
    events = evidence.get("docker_events", {})
    events_stdout = events.get("stdout", "")
    if events_stdout and events_stdout.strip():
        lines.extend([
            "---",
            "",
            "## Docker Events (die/oom/kill)",
            "",
            "```",
            events_stdout.strip()[:2000],
            "```",
            "",
        ])

    # Host OOM
    host_oom = evidence.get("host_oom", {})
    oom_stdout = host_oom.get("stdout", "")
    if host_oom.get("ok") and oom_stdout and oom_stdout != "(nenhuma evidência de OOM)":
        lines.extend([
            "---",
            "",
            "## Evidência de OOM no Host (dmesg)",
            "",
            "```",
            oom_stdout[:2000],
            "```",
            "",
        ])
    elif not host_oom.get("ok"):
        lines.extend([
            "---",
            "",
            "## Evidência de OOM no Host",
            "",
            f"**Erro:** {host_oom.get('error', host_oom.get('stderr', 'N/A'))}",
            "(dmesg pode requerer permissões elevadas)",
            "",
        ])

    # Docker compose ps
    ps = evidence.get("compose_ps", {})
    if ps.get("stdout"):
        lines.extend([
            "---",
            "",
            "## Docker Compose PS",
            "",
            "```",
            ps["stdout"][:2000],
            "```",
            "",
        ])

    lines.extend([
        "---",
        "",
        "*Gerado por Runtime Evidence Collector*",
        f"*{evidence.get('timestamp', '')}*",
    ])

    return "\n".join(lines)
