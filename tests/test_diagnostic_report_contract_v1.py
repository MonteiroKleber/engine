"""Testes do contrato canônico DiagnosticReport v1.

Valida:
1) schema_version presente no JSON e Markdown
2) content_hash_sha256 presente no JSON e Markdown
3) Hash estável: mesma entrada => mesmo hash
4) Hash muda quando campo incluído muda
5) Hash NÃO muda quando campo excluído muda
6) generate_and_save() salva JSON + MD em diagnostics/
7) Normalização de repo_path continua válida
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

from release.diagnostic_report import (
    DIAGNOSTIC_REPORT_SCHEMA_VERSION,
    DiagnosticReport,
    DiagnosticReportGenerator,
    compute_content_hash_sha256,
)


class TestSchemaVersionAndHash:
    """Testes para schema_version e content_hash_sha256."""

    @pytest.fixture
    def sample_report(self):
        """Cria um DiagnosticReport de exemplo."""
        return DiagnosticReport(
            project="test_project",
            final_status="BUILD_FAILED",
            engine_version="1.0.0",
            duration_ms=1500.0,
            timestamp="2026-01-05T12:00:00",
            build_ok=False,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="Error in backend",
            docker_logs_frontend_tail="",
            errors=["Build failed", "Compilation error"],
            repo_path="/home/bazari/generated/test_project",
            failed_repo_path="/home/bazari/generated/_failed/BUILD_FAILED/test_123",
        )

    def test_schema_version_present_in_json(self, sample_report):
        """[Contrato] schema_version presente no JSON."""
        canonical = sample_report.to_canonical_dict()

        assert "schema_version" in canonical
        assert canonical["schema_version"] == DIAGNOSTIC_REPORT_SCHEMA_VERSION
        assert canonical["schema_version"] == "diagnostic_report.v1"

    def test_content_hash_present_in_json(self, sample_report):
        """[Contrato] content_hash_sha256 presente no JSON."""
        canonical = sample_report.to_canonical_dict()

        assert "content_hash_sha256" in canonical
        assert isinstance(canonical["content_hash_sha256"], str)
        assert len(canonical["content_hash_sha256"]) == 64  # SHA256 hex

    def test_schema_version_present_in_markdown(self, sample_report):
        """[Contrato] schema_version presente no Markdown."""
        md = sample_report.to_markdown()

        assert "SCHEMA VERSION:" in md
        assert DIAGNOSTIC_REPORT_SCHEMA_VERSION in md

    def test_content_hash_present_in_markdown(self, sample_report):
        """[Contrato] content_hash_sha256 presente no Markdown."""
        md = sample_report.to_markdown()

        assert "CONTENT HASH:" in md

        # Verificar que o hash no markdown é o mesmo que no JSON
        canonical = sample_report.to_canonical_dict()
        assert canonical["content_hash_sha256"] in md


class TestHashStability:
    """Testes para estabilidade do hash."""

    def test_same_input_produces_same_hash(self):
        """[Contrato] Mesma entrada produz mesmo hash."""
        # Criar dois reports idênticos
        def create_report():
            return DiagnosticReport(
                project="petclinic",
                final_status="SMOKE_FAILED",
                engine_version="1.0.0",
                duration_ms=2000.0,
                timestamp="2026-01-05T14:00:00",
                build_ok=True,
                docker_compose_ok=True,
                smoke_ok=False,
                docker_ps_snapshot="NAME  IMAGE  STATUS\ndb    postgres  Up",
                docker_logs_backend_tail="Started application",
                docker_logs_frontend_tail="Compiled successfully",
                errors=["Smoke test timeout"],
                repo_path="/home/bazari/generated/petclinic",
                failed_repo_path="/home/bazari/generated/_failed/SMOKE_FAILED/petclinic_abc",
            )

        report1 = create_report()
        report2 = create_report()

        hash1 = report1.to_canonical_dict()["content_hash_sha256"]
        hash2 = report2.to_canonical_dict()["content_hash_sha256"]

        assert hash1 == hash2, "Mesmo input deve produzir mesmo hash"

    def test_hash_changes_when_errors_change(self):
        """[Contrato] Hash muda quando errors muda."""
        report1 = DiagnosticReport(
            project="test",
            final_status="BUILD_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp="2026-01-05T10:00:00",
            build_ok=False,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=["Error A"],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        report2 = DiagnosticReport(
            project="test",
            final_status="BUILD_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp="2026-01-05T10:00:00",
            build_ok=False,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=["Error B"],  # Diferente
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        hash1 = report1.to_canonical_dict()["content_hash_sha256"]
        hash2 = report2.to_canonical_dict()["content_hash_sha256"]

        assert hash1 != hash2, "Hash deve mudar quando errors muda"

    def test_hash_changes_when_docker_logs_backend_changes(self):
        """[Contrato] Hash muda quando docker_logs_backend_tail muda."""
        report1 = DiagnosticReport(
            project="test",
            final_status="DOCKER_UP_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp="2026-01-05T10:00:00",
            build_ok=True,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="Log A",
            docker_logs_frontend_tail="",
            errors=[],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        report2 = DiagnosticReport(
            project="test",
            final_status="DOCKER_UP_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp="2026-01-05T10:00:00",
            build_ok=True,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="Log B",  # Diferente
            docker_logs_frontend_tail="",
            errors=[],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        hash1 = report1.to_canonical_dict()["content_hash_sha256"]
        hash2 = report2.to_canonical_dict()["content_hash_sha256"]

        assert hash1 != hash2, "Hash deve mudar quando docker_logs_backend_tail muda"

    def test_hash_does_not_change_when_timestamp_changes(self):
        """[Contrato] Hash NÃO muda quando timestamp muda (campo volátil)."""
        report1 = DiagnosticReport(
            project="test",
            final_status="BUILD_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp="2026-01-05T10:00:00",  # Timestamp A
            build_ok=False,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=["Error"],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        report2 = DiagnosticReport(
            project="test",
            final_status="BUILD_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp="2026-01-05T15:30:00",  # Timestamp B (diferente)
            build_ok=False,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=["Error"],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        hash1 = report1.to_canonical_dict()["content_hash_sha256"]
        hash2 = report2.to_canonical_dict()["content_hash_sha256"]

        assert hash1 == hash2, "Hash NÃO deve mudar quando apenas timestamp muda"

    def test_hash_does_not_change_when_duration_ms_changes(self):
        """[Contrato] Hash NÃO muda quando duration_ms muda (campo volátil)."""
        report1 = DiagnosticReport(
            project="test",
            final_status="SMOKE_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,  # Duration A
            timestamp="2026-01-05T10:00:00",
            build_ok=True,
            docker_compose_ok=True,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=[],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        report2 = DiagnosticReport(
            project="test",
            final_status="SMOKE_FAILED",
            engine_version="1.0.0",
            duration_ms=5000.0,  # Duration B (diferente)
            timestamp="2026-01-05T10:00:00",
            build_ok=True,
            docker_compose_ok=True,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=[],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        hash1 = report1.to_canonical_dict()["content_hash_sha256"]
        hash2 = report2.to_canonical_dict()["content_hash_sha256"]

        assert hash1 == hash2, "Hash NÃO deve mudar quando apenas duration_ms muda"

    def test_hash_changes_when_final_status_changes(self):
        """[Contrato] Hash muda quando final_status muda."""
        report1 = DiagnosticReport(
            project="test",
            final_status="BUILD_FAILED",
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp="2026-01-05T10:00:00",
            build_ok=False,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=[],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        report2 = DiagnosticReport(
            project="test",
            final_status="DOCKER_UP_FAILED",  # Diferente
            engine_version="1.0.0",
            duration_ms=1000.0,
            timestamp="2026-01-05T10:00:00",
            build_ok=False,
            docker_compose_ok=False,
            smoke_ok=False,
            docker_ps_snapshot="",
            docker_logs_backend_tail="",
            docker_logs_frontend_tail="",
            errors=[],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
        )

        hash1 = report1.to_canonical_dict()["content_hash_sha256"]
        hash2 = report2.to_canonical_dict()["content_hash_sha256"]

        assert hash1 != hash2, "Hash deve mudar quando final_status muda"


class TestGenerateAndSavePersistence:
    """Testes para persistência via generate_and_save()."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretório de store temporário."""
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_generate_and_save_creates_json_and_md(self, temp_store):
        """[Contrato] generate_and_save() salva JSON + MD."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "build_ok": False,
            "errors": ["Compilation failed"],
        }

        result = generator.generate_and_save("test_project", run_result)

        assert result is not None
        assert "json" in result
        assert "markdown" in result

        # Verificar que arquivos existem
        json_path = Path(result["json"])
        md_path = Path(result["markdown"])

        assert json_path.exists(), f"JSON não existe: {json_path}"
        assert md_path.exists(), f"Markdown não existe: {md_path}"

    def test_files_saved_in_diagnostics_directory(self, temp_store):
        """[Contrato] Arquivos salvos em diagnostics/ dentro do projeto."""
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
        }

        result = generator.generate_and_save("myproject", run_result)

        json_path = Path(result["json"])
        md_path = Path(result["markdown"])

        # Verificar caminho contém diagnostics/
        expected_dir = temp_store / "myproject" / "diagnostics"
        assert json_path.parent == expected_dir
        assert md_path.parent == expected_dir

    def test_saved_json_contains_schema_and_hash(self, temp_store):
        """[Contrato] JSON salvo contém schema_version e content_hash_sha256."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "SMOKE_FAILED",
            "build_ok": True,
            "docker_compose_ok": True,
            "smoke_ok": False,
            "errors": ["Timeout"],
        }

        result = generator.generate_and_save("petclinic", run_result)

        # Ler JSON salvo
        json_path = Path(result["json"])
        with open(json_path) as f:
            saved_data = json.load(f)

        assert "schema_version" in saved_data
        assert saved_data["schema_version"] == DIAGNOSTIC_REPORT_SCHEMA_VERSION

        assert "content_hash_sha256" in saved_data
        assert len(saved_data["content_hash_sha256"]) == 64

    def test_saved_markdown_contains_schema_and_hash(self, temp_store):
        """[Contrato] Markdown salvo contém schema_version e content_hash_sha256."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "build_ok": False,
        }

        result = generator.generate_and_save("test_project", run_result)

        # Ler Markdown salvo
        md_path = Path(result["markdown"])
        md_content = md_path.read_text()

        assert "SCHEMA VERSION:" in md_content
        assert DIAGNOSTIC_REPORT_SCHEMA_VERSION in md_content
        assert "CONTENT HASH:" in md_content


class TestRepoPathNormalizationStillWorks:
    """Testes para garantir que normalização de repo_path ainda funciona."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_normalization_still_works_with_contract(self, temp_store):
        """[Contrato] Normalização de repo_path continua funcionando."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        # run_result sem repo_path
        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "build_ok": False,
            # repo_path AUSENTE
        }

        report = generator.generate("test_project", run_result)

        assert report is not None
        assert report.repo_path == "/tmp/generated/test_project"
        assert report.failed_repo_path == "/tmp/generated/test_project"

        # Verificar que JSON gerado está correto
        canonical = report.to_canonical_dict()
        assert canonical["repo_path"] == "/tmp/generated/test_project"
        assert canonical["failed_repo_path"] == "/tmp/generated/test_project"


class TestComputeHashFunction:
    """Testes para a função compute_content_hash_sha256."""

    def test_compute_hash_returns_64_char_hex(self):
        """[Função] compute_content_hash_sha256 retorna hex de 64 chars."""
        payload = {"key": "value", "number": 42}
        hash_result = compute_content_hash_sha256(payload)

        assert isinstance(hash_result, str)
        assert len(hash_result) == 64
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_compute_hash_is_deterministic(self):
        """[Função] compute_content_hash_sha256 é determinístico."""
        payload = {"a": 1, "b": [1, 2, 3], "c": {"nested": "value"}}

        hash1 = compute_content_hash_sha256(payload)
        hash2 = compute_content_hash_sha256(payload)

        assert hash1 == hash2

    def test_compute_hash_uses_sorted_keys(self):
        """[Função] Hash é o mesmo independente da ordem das chaves."""
        payload1 = {"z": 1, "a": 2, "m": 3}
        payload2 = {"a": 2, "m": 3, "z": 1}

        hash1 = compute_content_hash_sha256(payload1)
        hash2 = compute_content_hash_sha256(payload2)

        assert hash1 == hash2, "Hash deve ser igual para dicts com mesmos valores em ordem diferente"

    def test_compute_hash_handles_unicode(self):
        """[Função] compute_content_hash_sha256 lida com unicode."""
        payload = {"message": "Erro de compilação: variável não definida"}
        hash_result = compute_content_hash_sha256(payload)

        assert len(hash_result) == 64
