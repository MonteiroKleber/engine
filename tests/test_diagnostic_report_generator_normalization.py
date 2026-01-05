"""Testes de normalização de repo_path no DiagnosticReportGenerator.

Objetivo: Garantir que DiagnosticReport NUNCA recebe repo_path=None ou
failed_repo_path=None. Toda normalização ocorre no Generator.

Padrão arquitetural:
- DiagnosticReport é uma camada pura, sem lógica defensiva
- DiagnosticReportGenerator normaliza todos os paths antes de criar o Report
"""

import pytest
from pathlib import Path

from release.diagnostic_report import (
    DiagnosticReport,
    DiagnosticReportGenerator,
)


class TestGeneratorNormalizesRepoPath:
    """Testes para normalização de repo_path no Generator."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretório de store temporário."""
        store = tmp_path / "store"
        store.mkdir()
        return store

    @pytest.fixture
    def generator(self, temp_store):
        """Cria generator com paths conhecidos."""
        return DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

    def test_repo_path_absent_is_normalized(self, generator):
        """[Normalização] repo_path ausente no run_result → normalizado."""
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "build_ok": False,
            # repo_path AUSENTE
        }

        report = generator.generate("test_project", run_result)

        assert report is not None
        assert report.repo_path == "/tmp/generated/test_project", (
            f"repo_path deveria ser normalizado, mas é: {report.repo_path}"
        )

    def test_repo_path_none_explicit_is_normalized(self, generator):
        """[Normalização] repo_path=None explícito → normalizado."""
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "build_ok": False,
            "repo_path": None,  # Explicitamente None
        }

        report = generator.generate("my_project", run_result)

        assert report is not None
        assert report.repo_path == "/tmp/generated/my_project", (
            f"repo_path deveria ser normalizado, mas é: {report.repo_path}"
        )

    def test_repo_path_empty_string_is_normalized(self, generator):
        """[Normalização] repo_path='' (string vazia) → normalizado."""
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "SMOKE_FAILED",
            "repo_path": "",  # String vazia
        }

        report = generator.generate("empty_project", run_result)

        assert report is not None
        assert report.repo_path == "/tmp/generated/empty_project", (
            f"repo_path deveria ser normalizado de string vazia, mas é: {report.repo_path}"
        )

    def test_failed_repo_path_absent_inherits_repo_path(self, generator):
        """[Normalização] failed_repo_path ausente → herda repo_path."""
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "DOCKER_UP_FAILED",
            "repo_path": "/custom/path/project",
            # failed_repo_path AUSENTE
        }

        report = generator.generate("test_project", run_result)

        assert report is not None
        assert report.failed_repo_path == "/custom/path/project", (
            f"failed_repo_path deveria herdar repo_path, mas é: {report.failed_repo_path}"
        )

    def test_failed_repo_path_none_inherits_repo_path(self, generator):
        """[Normalização] failed_repo_path=None → herda repo_path."""
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "DOCKER_UP_FAILED",
            "repo_path": "/another/path/project",
            "failed_repo_path": None,  # Explicitamente None
        }

        report = generator.generate("test_project", run_result)

        assert report is not None
        assert report.failed_repo_path == "/another/path/project", (
            f"failed_repo_path deveria herdar repo_path, mas é: {report.failed_repo_path}"
        )

    def test_failed_repo_path_empty_inherits_repo_path(self, generator):
        """[Normalização] failed_repo_path='' → herda repo_path."""
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "SMOKE_FAILED",
            "repo_path": "/some/repo/path",
            "failed_repo_path": "",  # String vazia
        }

        report = generator.generate("test_project", run_result)

        assert report is not None
        assert report.failed_repo_path == "/some/repo/path", (
            f"failed_repo_path deveria herdar repo_path, mas é: {report.failed_repo_path}"
        )

    def test_both_paths_present_are_preserved(self, generator):
        """[Normalização] Ambos presentes → preservados."""
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "repo_path": "/home/bazari/generated/petclinic",
            "failed_repo_path": "/home/bazari/generated/_failed/BUILD_FAILED/petclinic_123",
        }

        report = generator.generate("petclinic", run_result)

        assert report is not None
        assert report.repo_path == "/home/bazari/generated/petclinic", (
            f"repo_path deveria ser preservado, mas é: {report.repo_path}"
        )
        assert report.failed_repo_path == "/home/bazari/generated/_failed/BUILD_FAILED/petclinic_123", (
            f"failed_repo_path deveria ser preservado, mas é: {report.failed_repo_path}"
        )

    def test_report_repo_path_never_none(self, generator):
        """[Invariante] report.repo_path nunca é None."""
        test_cases = [
            {"repo_path": None},
            {"repo_path": ""},
            {},  # ausente
            {"repo_path": None, "failed_repo_path": None},
        ]

        for i, extra_fields in enumerate(test_cases):
            run_result = {
                "success": False,
                "release_mode": True,
                "final_status": "UNKNOWN_RELEASE_FAILED",
                **extra_fields,
            }

            report = generator.generate(f"project_{i}", run_result)

            assert report is not None, f"Case {i}: report não deveria ser None"
            assert report.repo_path is not None, (
                f"Case {i}: report.repo_path NUNCA deve ser None"
            )
            assert isinstance(report.repo_path, str), (
                f"Case {i}: report.repo_path deve ser string"
            )
            assert len(report.repo_path) > 0, (
                f"Case {i}: report.repo_path não deve ser string vazia"
            )

    def test_report_failed_repo_path_never_none(self, generator):
        """[Invariante] report.failed_repo_path nunca é None."""
        test_cases = [
            {"failed_repo_path": None},
            {"failed_repo_path": ""},
            {},  # ausente
            {"repo_path": "/custom/path", "failed_repo_path": None},
            {"repo_path": None, "failed_repo_path": None},
        ]

        for i, extra_fields in enumerate(test_cases):
            run_result = {
                "success": False,
                "release_mode": True,
                "final_status": "DOCKER_UP_FAILED",
                **extra_fields,
            }

            report = generator.generate(f"project_{i}", run_result)

            assert report is not None, f"Case {i}: report não deveria ser None"
            assert report.failed_repo_path is not None, (
                f"Case {i}: report.failed_repo_path NUNCA deve ser None"
            )
            assert isinstance(report.failed_repo_path, str), (
                f"Case {i}: report.failed_repo_path deve ser string"
            )
            assert len(report.failed_repo_path) > 0, (
                f"Case {i}: report.failed_repo_path não deve ser string vazia"
            )


class TestNormalizedReportGeneratesValidMarkdown:
    """Testes para garantir que report normalizado gera markdown válido."""

    @pytest.fixture
    def generator(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return DiagnosticReportGenerator(
            store_root=str(store),
            generated_root="/tmp/generated",
        )

    def test_markdown_with_normalized_paths_no_placeholders(self, generator):
        """[Integração] Markdown gerado não contém placeholders não-substituídos."""
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            # repo_path e failed_repo_path ausentes
        }

        report = generator.generate("test_project", run_result)
        md = report.to_markdown()

        # Não deve conter placeholders não-substituídos
        assert "<repo_path>" not in md, "Markdown não deve conter <repo_path>"
        assert "<failed_repo_path>" not in md, "Markdown não deve conter <failed_repo_path>"

        # Deve conter o path normalizado
        assert "/tmp/generated/test_project" in md, (
            "Markdown deve conter o path normalizado"
        )

    def test_markdown_with_docker_up_failed_uses_failed_repo_path(self, generator):
        """[Integração] DOCKER_UP_FAILED usa failed_repo_path corretamente."""
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "DOCKER_UP_FAILED",
            "repo_path": "/home/bazari/generated/myapp",
            "failed_repo_path": "/home/bazari/generated/_failed/DOCKER_UP_FAILED/myapp_abc123",
        }

        report = generator.generate("myapp", run_result)
        md = report.to_markdown()

        # DOCKER_UP_FAILED tem ações que usam <failed_repo_path>
        assert "/home/bazari/generated/_failed/DOCKER_UP_FAILED/myapp_abc123" in md, (
            "Markdown deve conter o failed_repo_path para DOCKER_UP_FAILED"
        )


class TestNormalizationWithGenerateAndSave:
    """Testes para normalização no fluxo completo generate_and_save."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_generate_and_save_with_missing_paths(self, temp_store):
        """[E2E] generate_and_save funciona com paths ausentes."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "SMOKE_FAILED",
            # repo_path e failed_repo_path ausentes
        }

        result = generator.generate_and_save("test_project", run_result)

        assert result is not None
        assert "markdown" in result

        # Verificar arquivo existe e tem conteúdo válido
        md_path = Path(result["markdown"])
        assert md_path.exists()

        content = md_path.read_text()
        assert "<repo_path>" not in content
        assert "<failed_repo_path>" not in content
        assert "/tmp/generated/test_project" in content
