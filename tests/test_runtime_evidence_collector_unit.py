"""Testes unitários do Runtime Evidence Collector.

Testa que o coletor:
(a) chama docker inspect com format correto,
(b) registra campos obrigatórios no JSON,
(c) não explode quando docker não está disponível (captura erro).

Instruções de reprodução:
  python main.py --project petclinic --input "<input>" --release 2>&1 | tee readiness_debug.log
  grep "[EVIDENCE]" readiness_debug.log

Arquivos de evidência ficam em:
  /home/bazari/engine/demo_store/<project>/releases/runtime_evidence_*.json
  /home/bazari/engine/demo_store/<project>/releases/runtime_evidence_*.md
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from release.runtime_evidence_collector import (
    _run_command,
    _parse_inspect_state,
    _classify_failure,
    collect_runtime_evidence,
    SubprocessResult,
)


class TestRunCommand:
    """Testa a função _run_command."""

    def test_successful_command(self):
        """Comando bem-sucedido retorna ok=True."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr="",
            )
            result = _run_command(["echo", "test"])
            assert result.ok is True
            assert result.exit_code == 0
            assert result.stdout == "output"

    def test_failed_command(self):
        """Comando falho retorna ok=False."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error",
            )
            result = _run_command(["false"])
            assert result.ok is False
            assert result.exit_code == 1

    def test_command_not_found(self):
        """Comando não encontrado não explode."""
        result = _run_command(["comando_inexistente_xyz"])
        assert result.ok is False
        assert "not found" in result.error.lower() or "No such file" in result.error

    def test_timeout_handling(self):
        """Timeout é capturado sem exceção."""
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["sleep", "100"],
                timeout=1,
            )
            result = _run_command(["sleep", "100"], timeout=1)
            assert result.ok is False
            assert "Timeout" in result.error

    def test_result_to_dict(self):
        """SubprocessResult serializa para dict corretamente."""
        result = SubprocessResult(
            ok=True,
            stdout="out",
            stderr="err",
            exit_code=0,
            command="test",
            error="",
        )
        d = result.to_dict()
        assert d["ok"] is True
        assert d["stdout"] == "out"
        assert d["exit_code"] == 0


class TestParseInspectState:
    """Testa o parser de docker inspect."""

    def test_parses_valid_inspect_json(self):
        """Parseia JSON válido do docker inspect."""
        inspect_json = json.dumps([{
            "State": {
                "Status": "exited",
                "Running": False,
                "ExitCode": 137,
                "OOMKilled": True,
                "Error": "",
                "FinishedAt": "2026-01-05T10:00:00Z",
                "StartedAt": "2026-01-05T09:55:00Z",
            },
            "HostConfig": {
                "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
            },
            "RestartCount": 3,
            "Config": {
                "Env": [
                    "SPRING_PROFILES_ACTIVE=dev",
                    "JAVA_OPTS=-Xmx512m",
                    "POSTGRES_PASSWORD=secret",
                ],
            },
        }])

        parsed = _parse_inspect_state(inspect_json)

        assert parsed["status"] == "exited"
        assert parsed["running"] is False
        assert parsed["exit_code"] == 137
        assert parsed["oom_killed"] is True
        assert parsed["restart_count"] == 3
        assert "SPRING_PROFILES_ACTIVE=dev" in parsed["relevant_env"]
        assert "JAVA_OPTS=-Xmx512m" in parsed["relevant_env"]
        # Senha deve estar mascarada
        assert "POSTGRES_PASSWORD=***MASKED***" in parsed["relevant_env"]

    def test_handles_empty_json(self):
        """Lida com JSON vazio sem explodir."""
        parsed = _parse_inspect_state("[]")
        assert "parse_error" in parsed

    def test_handles_invalid_json(self):
        """Lida com JSON inválido sem explodir."""
        parsed = _parse_inspect_state("not json")
        assert "parse_error" in parsed

    def test_handles_null_values(self):
        """Lida com valores null no JSON."""
        inspect_json = json.dumps([{
            "State": {
                "Status": None,
                "ExitCode": None,
            },
            "Config": {},
        }])
        parsed = _parse_inspect_state(inspect_json)
        assert parsed["status"] is None


class TestClassifyFailure:
    """Testa a classificação de falhas."""

    def test_classifies_oom_from_inspect(self):
        """Classifica OOM quando OOMKilled=true."""
        result = _classify_failure(
            inspect_parsed={"oom_killed": True, "exit_code": 137},
            docker_events_stdout="",
            host_oom_stdout="",
            backend_logs_stdout="",
        )
        assert result["classification"] == "OOM"
        assert "OOMKilled" in result["reason"]

    def test_classifies_oom_from_events(self):
        """Classifica OOM quando docker events contém 'oom'."""
        result = _classify_failure(
            inspect_parsed={"oom_killed": False, "exit_code": 137},
            docker_events_stdout="2026-01-05 container-1 oom exitCode=137",
            host_oom_stdout="",
            backend_logs_stdout="",
        )
        assert result["classification"] == "OOM"
        assert "oom" in result["reason"].lower()

    def test_classifies_oom_from_dmesg(self):
        """Classifica OOM quando dmesg indica OOM kill de java."""
        result = _classify_failure(
            inspect_parsed={"oom_killed": False, "exit_code": 137},
            docker_events_stdout="",
            host_oom_stdout="[ 1234.567890] Killed process 1234 (java) total-vm:2048000kB",
            backend_logs_stdout="",
        )
        assert result["classification"] == "OOM"
        assert "dmesg" in result["reason"].lower()

    def test_classifies_app_exception(self):
        """Classifica APP_EXCEPTION quando há stacktrace nos logs."""
        result = _classify_failure(
            inspect_parsed={"oom_killed": False, "exit_code": 1},
            docker_events_stdout="",
            host_oom_stdout="",
            backend_logs_stdout="""
                org.springframework.beans.factory.BeanCreationException: Error creating bean
                    at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory.createBean
                Caused by: java.lang.RuntimeException: Database connection failed
            """,
        )
        assert result["classification"] == "APP_EXCEPTION"
        assert "stacktrace" in result["reason"].lower() or "exception" in result["reason"].lower()

    def test_classifies_restart_loop(self):
        """Classifica RESTART_LOOP quando RestartCount > 0."""
        result = _classify_failure(
            inspect_parsed={"oom_killed": False, "exit_code": 0, "restart_count": 5},
            docker_events_stdout="",
            host_oom_stdout="",
            backend_logs_stdout="",
        )
        assert result["classification"] == "RESTART_LOOP"
        assert "RestartCount" in result["reason"]

    def test_classifies_exit_code_without_logs(self):
        """Classifica EXIT_CODE quando exit!=0 sem stacktrace."""
        result = _classify_failure(
            inspect_parsed={"oom_killed": False, "exit_code": 143, "restart_count": 0},
            docker_events_stdout="",
            host_oom_stdout="",
            backend_logs_stdout="Container terminated",
        )
        assert result["classification"] == "EXIT_CODE"
        assert "143" in result["reason"]

    def test_classifies_unknown_when_no_evidence(self):
        """Classifica UNKNOWN quando não há evidência."""
        result = _classify_failure(
            inspect_parsed={"oom_killed": False, "exit_code": 0, "restart_count": 0},
            docker_events_stdout="",
            host_oom_stdout="",
            backend_logs_stdout="",
        )
        assert result["classification"] == "UNKNOWN"


class TestCollectRuntimeEvidence:
    """Testa a coleta completa de evidências."""

    def test_returns_required_fields(self):
        """Retorna todos os campos obrigatórios no JSON."""
        with patch("release.runtime_evidence_collector._run_command") as mock_run:
            # Mock para retornar resultados vazios
            mock_run.return_value = SubprocessResult(
                ok=False,
                stdout="",
                stderr="command not found",
                exit_code=127,
                error="command not found",
            )

            evidence = collect_runtime_evidence(
                repo_path="/tmp/test",
                compose_file="docker-compose.yml",
            )

            # Verificar campos obrigatórios
            assert "timestamp" in evidence
            assert "repo_path" in evidence
            assert "compose_file" in evidence
            assert "compose_ps" in evidence
            assert "backend" in evidence
            assert "docker_events" in evidence
            assert "host_oom" in evidence
            assert "conclusion_hint" in evidence

            # Verificar estrutura do backend
            assert "container_id" in evidence["backend"]
            assert "inspect" in evidence["backend"]
            assert "logs" in evidence["backend"]

            # Verificar conclusion_hint
            assert "classification" in evidence["conclusion_hint"]
            assert "reason" in evidence["conclusion_hint"]

    def test_handles_docker_unavailable(self):
        """Não explode quando docker não está disponível."""
        with patch("release.runtime_evidence_collector._run_command") as mock_run:
            mock_run.return_value = SubprocessResult(
                ok=False,
                stdout="",
                stderr="",
                exit_code=127,
                error="docker: command not found",
            )

            # Não deve lançar exceção
            evidence = collect_runtime_evidence(
                repo_path="/tmp/nonexistent",
                compose_file="docker-compose.yml",
            )

            assert evidence is not None
            assert evidence["compose_ps"]["ok"] is False
            assert evidence["backend"]["container_id"] is None

    def test_calls_docker_inspect_correctly(self):
        """Chama docker inspect com o container ID correto."""
        with patch("release.runtime_evidence_collector._run_command") as mock_run:
            # Simular retorno do ps -q com container ID
            def side_effect(cmd, **kwargs):
                if "ps" in cmd and "-q" in cmd:
                    return SubprocessResult(
                        ok=True,
                        stdout="abc123def456\n",
                        stderr="",
                        exit_code=0,
                    )
                if "inspect" in cmd:
                    assert "abc123def456" in cmd, f"Esperava container ID no comando: {cmd}"
                    return SubprocessResult(
                        ok=True,
                        stdout='[{"State": {"Status": "running"}}]',
                        stderr="",
                        exit_code=0,
                    )
                return SubprocessResult(
                    ok=True,
                    stdout="",
                    stderr="",
                    exit_code=0,
                )

            mock_run.side_effect = side_effect

            evidence = collect_runtime_evidence(
                repo_path="/tmp/test",
                compose_file="docker-compose.yml",
            )

            assert evidence["backend"]["container_id"] == "abc123def456"

    def test_saves_evidence_when_out_dir_provided(self, tmp_path):
        """Salva arquivos JSON e MD quando out_dir é fornecido."""
        with patch("release.runtime_evidence_collector._run_command") as mock_run:
            mock_run.return_value = SubprocessResult(
                ok=False,
                stdout="",
                stderr="",
                exit_code=127,
                error="not found",
            )

            out_dir = tmp_path / "evidence"
            evidence = collect_runtime_evidence(
                repo_path="/tmp/test",
                out_dir=out_dir,
            )

            # Verificar que arquivos foram criados
            json_files = list(out_dir.glob("runtime_evidence_*.json"))
            md_files = list(out_dir.glob("runtime_evidence_*.md"))

            assert len(json_files) == 1
            assert len(md_files) == 1

            # Verificar conteúdo do JSON
            with open(json_files[0]) as f:
                saved = json.load(f)
            assert saved["repo_path"] == "/tmp/test"
            assert "conclusion_hint" in saved


class TestMarkdownReport:
    """Testa a geração do relatório Markdown."""

    def test_generates_markdown_with_all_sections(self, tmp_path):
        """Gera Markdown com todas as seções."""
        from release.runtime_evidence_collector import _generate_markdown_report

        evidence = {
            "timestamp": "2026-01-05T12:00:00",
            "repo_path": "/tmp/test",
            "compose_file": "docker-compose.yml",
            "compose_ps": {"ok": True, "stdout": "backend running"},
            "backend": {
                "container_id": "abc123",
                "inspect": {
                    "ok": True,
                    "parsed": {
                        "status": "exited",
                        "running": False,
                        "exit_code": 137,
                        "oom_killed": True,
                        "restart_count": 0,
                    },
                },
                "logs": {"ok": True, "stdout": "Line 1\nLine 2\nLine 3"},
            },
            "docker_events": {"ok": True, "stdout": "container die"},
            "host_oom": {"ok": True, "stdout": "Killed process java"},
            "conclusion_hint": {
                "classification": "OOM",
                "reason": "OOMKilled=true",
            },
        }

        md = _generate_markdown_report(evidence)

        assert "# Runtime Evidence Report" in md
        assert "OOM" in md
        assert "abc123" in md
        assert "137" in md  # ExitCode
        assert "True" in md or "true" in md.lower()  # OOMKilled
