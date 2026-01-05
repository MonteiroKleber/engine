"""Testes para garantir que DiagnosticReport e Generator tratam repo_path corretamente.

NOTA: Com o novo padrão arquitetural, DiagnosticReport NUNCA recebe repo_path=None.
A normalização ocorre no DiagnosticReportGenerator.

Estes testes validam que o fluxo completo (via Generator) funciona corretamente
quando o run_result não contém repo_path.
"""

import pytest
from datetime import datetime

from release.diagnostic_report import (
    DiagnosticReport,
    DiagnosticReportGenerator,
)


class TestDiagnosticReportWithValidPaths:
    """Testes para DiagnosticReport com paths válidos (contrato normal)."""

    def test_diagnostic_report_with_valid_paths_works(self):
        """DiagnosticReport funciona normalmente com paths válidos."""
        repo_path = "/home/bazari/generated/test_project"
        failed_repo_path = "/home/bazari/generated/_failed/BUILD_FAILED/test_123"

        report = DiagnosticReport(
            project="test_project",
            final_status="BUILD_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp=datetime.now().isoformat(),
            build_ok=False,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=[],
            repo_path=repo_path,
            failed_repo_path=failed_repo_path,
        )

        actions = report._generate_suggested_actions()

        # Nenhuma ação deve conter placeholders
        for action in actions:
            assert "<repo_path>" not in action
            assert "<failed_repo_path>" not in action

        # Deve conter os paths reais
        has_repo_path = any(repo_path in a for a in actions)
        assert has_repo_path, (
            f"Pelo menos uma ação deveria conter '{repo_path}'"
        )

    def test_diagnostic_report_markdown_with_valid_paths(self):
        """Markdown é gerado corretamente com paths válidos."""
        repo_path = "/home/bazari/generated/test_project"
        failed_repo_path = "/home/bazari/generated/_failed/BUILD_FAILED/test_123"

        report = DiagnosticReport(
            project="test_project",
            final_status="BUILD_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp=datetime.now().isoformat(),
            build_ok=False,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=[],
            repo_path=repo_path,
            failed_repo_path=failed_repo_path,
        )

        md_content = report.to_markdown()

        assert md_content is not None
        assert "<repo_path>" not in md_content
        assert "<failed_repo_path>" not in md_content


class TestDiagnosticReportGeneratorHandlesNoneRepoPath:
    """Testes para DiagnosticReportGenerator com repo_path=None no run_result."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretório de store temporário."""
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_generator_creates_report_without_repo_path(self, temp_store):
        """Generator cria report mesmo sem repo_path no run_result."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        # run_result sem repo_path (simula caso de falha precoce)
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "build_ok": False,
            "docker_compose_ok": False,
            "smoke_ok": False,
            "errors": ["Early failure"],
            # repo_path AUSENTE
        }

        report = generator.generate("test_project", run_result)

        assert report is not None, "Generator deveria criar report mesmo sem repo_path"
        assert report.repo_path is not None, "repo_path não deve ser None após normalização"
        assert report.repo_path == "/tmp/generated/test_project"

        # to_markdown não deve crashar
        md = report.to_markdown()
        assert md is not None
        assert "<repo_path>" not in md

    def test_generator_save_without_repo_path(self, temp_store):
        """Generator salva arquivo mesmo sem repo_path."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "UNKNOWN_RELEASE_FAILED",
            "build_ok": False,
            "errors": ["Unknown error"],
            # repo_path AUSENTE
        }

        result = generator.generate_and_save("test_project", run_result)

        assert result is not None, "Generator deveria salvar arquivo"
        assert "markdown" in result, "Result deveria ter caminho markdown"

        # Verificar que arquivo existe
        from pathlib import Path
        md_path = Path(result["markdown"])
        assert md_path.exists(), f"Arquivo {md_path} deveria existir"

        # Verificar conteúdo não tem placeholders
        content = md_path.read_text()
        assert "<repo_path>" not in content
        assert "<failed_repo_path>" not in content

    def test_generator_with_explicit_none_repo_path(self, temp_store):
        """Generator trata repo_path=None explícito."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "DOCKER_UP_FAILED",
            "build_ok": True,
            "docker_compose_ok": False,
            "repo_path": None,  # Explicitamente None
            "failed_repo_path": None,
        }

        report = generator.generate("test_project", run_result)

        assert report is not None
        assert report.repo_path is not None
        assert report.failed_repo_path is not None

        md = report.to_markdown()
        assert md is not None
        assert len(md) > 0
        assert "<repo_path>" not in md
        assert "<failed_repo_path>" not in md

    def test_generator_with_failed_repo_path_but_none_repo_path(self, temp_store):
        """Generator usa failed_repo_path quando presente, mesmo com repo_path=None."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "DOCKER_UP_FAILED",
            "build_ok": True,
            "docker_compose_ok": False,
            "repo_path": None,
            "failed_repo_path": "/home/bazari/generated/_failed/DOCKER_UP_FAILED/test_123",
        }

        report = generator.generate("test_project", run_result)

        assert report is not None
        assert report.repo_path == "/tmp/generated/test_project"
        assert report.failed_repo_path == "/home/bazari/generated/_failed/DOCKER_UP_FAILED/test_123"

        actions = report._generate_suggested_actions()

        # Nenhuma ação deve conter placeholders não-substituídos
        for action in actions:
            assert "<failed_repo_path>" not in action

        # DOCKER_UP_FAILED usa <failed_repo_path>, deve estar substituído
        has_actual_path = any("/home/bazari/generated/_failed" in a for a in actions)
        assert has_actual_path, (
            "Pelo menos uma ação deveria conter o caminho real do failed_repo_path"
        )
