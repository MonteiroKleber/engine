"""Testes de integração: Runtime Evidence wired on readiness fail.

Testa que, ao simular readiness fail, o coletor é invocado e os arquivos são gerados.

Instruções de reprodução:
  cd /home/bazari/engine
  python main.py --project petclinic --input "<input>" --release 2>&1 | tee readiness_debug.log
  grep "[EVIDENCE]" readiness_debug.log
  ls -la demo_store/petclinic/releases/runtime_evidence_*.json

Arquivos de evidência ficam em:
  /home/bazari/engine/demo_store/<project>/releases/runtime_evidence_*.json
  /home/bazari/engine/demo_store/<project>/releases/runtime_evidence_*.md
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from release.docker_compose_validator import DockerComposeValidator, DockerComposeUpResult
from release.runtime_evidence_collector import SubprocessResult


class TestRuntimeEvidenceWiredOnReadinessFail:
    """Testa que o coletor de evidências é invocado quando readiness falha."""

    @pytest.fixture
    def mock_subprocess_for_readiness_fail(self):
        """Mock subprocess para simular readiness fail com backend crashando."""
        call_count = {"value": 0}

        def mock_run(cmd, **kwargs):
            call_count["value"] += 1
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd

            # Simular docker compose ps que mostra backend sumindo
            # NOTA: _run_command usa text=True, então stdout/stderr são strings, não bytes
            if "docker" in cmd_str and "ps" in cmd_str and "--format" in cmd_str:
                if call_count["value"] <= 3:
                    # Primeiras iterações: backend presente
                    return MagicMock(
                        returncode=0,
                        stdout="backend\ndb\nfrontend\n",
                        stderr="",
                    )
                else:
                    # Depois: backend some
                    return MagicMock(
                        returncode=0,
                        stdout="db\nfrontend\n",
                        stderr="",
                    )

            if "docker" in cmd_str and "compose" in cmd_str and "ps" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="NAME   STATUS\ndb     running\nfrontend running\n",
                    stderr="",
                )

            if "docker" in cmd_str and "inspect" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps([{
                        "State": {
                            "Status": "exited",
                            "Running": False,
                            "ExitCode": 137,
                            "OOMKilled": True,
                            "Error": "",
                            "FinishedAt": "2026-01-05T10:00:00Z",
                        },
                        "RestartCount": 0,
                        "HostConfig": {"RestartPolicy": {"Name": "no"}},
                        "Config": {"Env": ["JAVA_OPTS=-Xmx512m"]},
                    }]),
                    stderr="",
                )

            if "docker" in cmd_str and "logs" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="Started Application...\nout of memory\n",
                    stderr="",
                )

            if "docker" in cmd_str and "events" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="2026-01-05 backend oom\n",
                    stderr="",
                )

            if "dmesg" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="[12345] Killed process 1234 (java)\n",
                    stderr="",
                )

            # Default
            return MagicMock(returncode=0, stdout="", stderr="")

        return mock_run

    def test_evidence_collected_on_readiness_timeout(self, tmp_path, mock_subprocess_for_readiness_fail):
        """Evidências são coletadas quando readiness timeout."""
        repo_path = tmp_path / "test_project"
        repo_path.mkdir()
        (repo_path / "docker-compose.yml").write_text("services: {}")

        with patch("subprocess.run", side_effect=mock_subprocess_for_readiness_fail):
            with patch("urllib.request.urlopen") as mock_urlopen:
                # Simular HTTP check falhando (connection refused)
                mock_urlopen.side_effect = ConnectionRefusedError("Connection refused")

                validator = DockerComposeValidator(generated_root=str(tmp_path))

                # Executar com timeout curto para forçar falha
                result = validator.wait_for_readiness(
                    project="test_project",
                    timeout=1,  # 1 segundo de timeout
                    poll_interval=0.1,
                )

                # Verificar que readiness falhou
                assert result.readiness_ok is False

                # Verificar que evidências foram coletadas
                assert hasattr(result, 'runtime_evidence')
                assert result.runtime_evidence is not None

                # Verificar classificação
                hint = result.runtime_evidence.get("conclusion_hint", {})
                assert hint.get("classification") in ["OOM", "APP_EXCEPTION", "EXIT_CODE", "RESTART_LOOP", "UNKNOWN"]

    def test_evidence_contains_required_fields(self, tmp_path, mock_subprocess_for_readiness_fail):
        """Evidências contêm todos os campos obrigatórios."""
        repo_path = tmp_path / "test_project"
        repo_path.mkdir()
        (repo_path / "docker-compose.yml").write_text("services: {}")

        with patch("subprocess.run", side_effect=mock_subprocess_for_readiness_fail):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = ConnectionRefusedError()

                validator = DockerComposeValidator(generated_root=str(tmp_path))
                result = validator.wait_for_readiness(
                    project="test_project",
                    timeout=1,
                    poll_interval=0.1,
                )

                evidence = result.runtime_evidence

                # Campos obrigatórios
                assert "timestamp" in evidence
                assert "repo_path" in evidence
                assert "backend" in evidence
                assert "compose_ps" in evidence
                assert "docker_events" in evidence
                assert "host_oom" in evidence
                assert "conclusion_hint" in evidence

                # Estrutura do backend
                assert "container_id" in evidence["backend"]
                assert "inspect" in evidence["backend"]
                assert "logs" in evidence["backend"]

    def test_evidence_not_collected_on_success(self, tmp_path):
        """Evidências NÃO são coletadas quando readiness é bem-sucedido."""
        repo_path = tmp_path / "test_project"
        repo_path.mkdir()
        (repo_path / "docker-compose.yml").write_text("services: {}")

        def mock_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            # NOTA: subprocess.run sem text=True retorna bytes
            # O validator usa .decode() em alguns lugares, então retornar bytes
            if "ps" in cmd_str and "--format" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=b"backend\ndb\nfrontend\n",
                    stderr=b"",
                )
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with patch("subprocess.run", side_effect=mock_run):
            with patch("urllib.request.urlopen") as mock_urlopen:
                # Simular HTTP check bem-sucedido
                mock_response = MagicMock()
                mock_response.status = 200
                mock_response.__enter__ = MagicMock(return_value=mock_response)
                mock_response.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_response

                validator = DockerComposeValidator(generated_root=str(tmp_path))
                result = validator.wait_for_readiness(
                    project="test_project",
                    timeout=5,
                    poll_interval=0.1,
                )

                # Verificar que readiness foi bem-sucedido
                assert result.readiness_ok is True

                # Evidências não devem ser coletadas em sucesso
                assert result.runtime_evidence is None


class TestRuntimeEvidenceToDict:
    """Testa que runtime_evidence é incluído no to_dict()."""

    def test_runtime_evidence_included_in_to_dict(self):
        """runtime_evidence é incluído quando presente."""
        result = DockerComposeUpResult(
            success=False,
            readiness_ok=False,
            runtime_evidence={
                "conclusion_hint": {
                    "classification": "OOM",
                    "reason": "test",
                }
            },
        )

        d = result.to_dict()
        assert "runtime_evidence" in d
        assert d["runtime_evidence"]["conclusion_hint"]["classification"] == "OOM"

    def test_runtime_evidence_not_included_when_none(self):
        """runtime_evidence não é incluído quando None."""
        result = DockerComposeUpResult(
            success=True,
            readiness_ok=True,
            runtime_evidence=None,
        )

        d = result.to_dict()
        assert "runtime_evidence" not in d


class TestEvidenceFilesGenerated:
    """Testa que arquivos de evidência são gerados."""

    def test_json_file_generated(self, tmp_path):
        """Arquivo JSON é gerado."""
        from release.runtime_evidence_collector import _save_evidence

        evidence = {
            "timestamp": "2026-01-05T12:00:00",
            "repo_path": "/tmp/test",
            "conclusion_hint": {"classification": "OOM", "reason": "test"},
        }

        _save_evidence(evidence, tmp_path)

        json_files = list(tmp_path.glob("runtime_evidence_*.json"))
        assert len(json_files) == 1

        with open(json_files[0]) as f:
            saved = json.load(f)
        assert saved["conclusion_hint"]["classification"] == "OOM"

    def test_markdown_file_generated(self, tmp_path):
        """Arquivo Markdown é gerado."""
        from release.runtime_evidence_collector import _save_evidence

        evidence = {
            "timestamp": "2026-01-05T12:00:00",
            "repo_path": "/tmp/test",
            "compose_ps": {"ok": True, "stdout": "running"},
            "backend": {
                "container_id": "abc123",
                "inspect": {
                    "ok": True,
                    "parsed": {
                        "status": "exited",
                        "exit_code": 137,
                        "oom_killed": True,
                    },
                },
                "logs": {"ok": True, "stdout": "log line"},
            },
            "docker_events": {"ok": True, "stdout": ""},
            "host_oom": {"ok": True, "stdout": ""},
            "conclusion_hint": {"classification": "OOM", "reason": "OOMKilled=true"},
        }

        _save_evidence(evidence, tmp_path)

        md_files = list(tmp_path.glob("runtime_evidence_*.md"))
        assert len(md_files) == 1

        content = md_files[0].read_text()
        assert "Runtime Evidence Report" in content
        assert "OOM" in content
        assert "137" in content
