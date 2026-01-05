"""Testes do Contract Gate e contract_notes do DiagnosticReport v1.

Valida:
1) contract_notes fora do hash
2) contract_gate passa quando JSON está íntegro
3) contract_gate falha quando JSON é adulterado
4) Markdown header em 2 linhas separadas
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
    extract_hashable_payload_from_canonical,
)


class TestContractNotesOutsideHash:
    """Testes para garantir que contract_notes não afeta o hash."""

    def test_contract_notes_does_not_affect_hash(self):
        """[Contrato] contract_notes NÃO entra no hash."""
        # Report SEM contract_notes
        report_without = DiagnosticReport(
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
            errors=["Error"],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
            contract_notes=None,
        )

        # Report COM contract_notes
        report_with = DiagnosticReport(
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
            errors=["Error"],
            repo_path="/path/to/repo",
            failed_repo_path="/path/to/failed",
            contract_notes="This is a note for future compatibility",
        )

        hash_without = report_without.to_canonical_dict()["content_hash_sha256"]
        hash_with = report_with.to_canonical_dict()["content_hash_sha256"]

        assert hash_without == hash_with, (
            "contract_notes NÃO deve afetar o hash"
        )

    def test_contract_notes_in_canonical_dict(self):
        """[Contrato] contract_notes aparece em to_canonical_dict quando setado."""
        report = DiagnosticReport(
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
            contract_notes="My custom note",
        )

        canonical = report.to_canonical_dict()

        assert "contract_notes" in canonical
        assert canonical["contract_notes"] == "My custom note"

    def test_contract_notes_absent_when_none(self):
        """[Contrato] contract_notes ausente em to_canonical_dict quando None."""
        report = DiagnosticReport(
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
            contract_notes=None,
        )

        canonical = report.to_canonical_dict()

        assert "contract_notes" not in canonical

    def test_contract_notes_not_in_hashable_dict(self):
        """[Contrato] contract_notes NÃO aparece em to_hashable_dict."""
        report = DiagnosticReport(
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
            contract_notes="This should not appear",
        )

        hashable = report.to_hashable_dict()

        assert "contract_notes" not in hashable


class TestContractGatePasses:
    """Testes para Contract Gate quando JSON está íntegro."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_contract_gate_passes_on_valid_json(self, temp_store):
        """[Contract Gate] Passa quando JSON salvo está íntegro."""
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

        # Não deve lançar exceção
        result = generator.generate_and_save("test_project", run_result)

        assert result is not None
        assert "json" in result
        assert "markdown" in result

        # Verificar que arquivos existem
        json_path = Path(result["json"])
        md_path = Path(result["markdown"])
        assert json_path.exists()
        assert md_path.exists()

    def test_contract_gate_passes_with_contract_notes(self, temp_store):
        """[Contract Gate] Passa com contract_notes presente."""
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
            "contract_notes": "Test note for contract gate",
        }

        # Não deve lançar exceção
        result = generator.generate_and_save("test_project", run_result)

        assert result is not None

        # Verificar que contract_notes está no JSON
        json_path = Path(result["json"])
        with open(json_path) as f:
            saved = json.load(f)

        assert "contract_notes" in saved
        assert saved["contract_notes"] == "Test note for contract gate"


class TestContractGateFails:
    """Testes para Contract Gate quando JSON é adulterado."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_contract_gate_fails_when_final_status_modified(self, temp_store):
        """[Contract Gate] Falha quando final_status é adulterado."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "build_ok": False,
            "errors": ["Error"],
        }

        # Gerar e salvar normalmente
        result = generator.generate_and_save("test_project", run_result)
        json_path = Path(result["json"])

        # Adulterar o JSON
        with open(json_path) as f:
            data = json.load(f)

        data["final_status"] = "SMOKE_FAILED"  # Adulteração

        with open(json_path, 'w') as f:
            json.dump(data, f)

        # Validar manualmente usando o helper
        with pytest.raises(RuntimeError) as excinfo:
            generator._validate_contract_gate(json_path)

        assert "Contract Gate FAILED" in str(excinfo.value)
        assert "hash mismatch" in str(excinfo.value)

    def test_contract_gate_fails_when_errors_modified(self, temp_store):
        """[Contract Gate] Falha quando errors é adulterado."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "build_ok": False,
            "errors": ["Original error"],
        }

        result = generator.generate_and_save("test_project", run_result)
        json_path = Path(result["json"])

        # Adulterar o JSON
        with open(json_path) as f:
            data = json.load(f)

        data["errors"] = ["Modified error"]  # Adulteração

        with open(json_path, 'w') as f:
            json.dump(data, f)

        with pytest.raises(RuntimeError) as excinfo:
            generator._validate_contract_gate(json_path)

        assert "Contract Gate FAILED" in str(excinfo.value)

    def test_extract_hashable_payload_works(self):
        """[Helper] extract_hashable_payload_from_canonical funciona."""
        canonical = {
            "schema_version": "diagnostic_report.v1",
            "content_hash_sha256": "abc123",
            "project": "test",
            "final_status": "BUILD_FAILED",
            "engine_version": "1.0.0",
            "timestamp": "2026-01-05T10:00:00",
            "duration_ms": 1000.0,
            "build_ok": False,
            "docker_compose_ok": False,
            "smoke_ok": False,
            "errors": ["Error"],
            "repo_path": "/path",
            "failed_repo_path": "/path",
            "docker_ps_snapshot": "",
            "docker_logs_backend_tail": "",
            "docker_logs_frontend_tail": "",
            "suggested_actions": ["action1"],
            "probable_cause": "cause",
            "possible_causes": ["cause1"],
            "objective_evidence": ["evidence1"],
            "contract_notes": "note",
        }

        hashable = extract_hashable_payload_from_canonical(canonical)

        # Deve conter apenas campos hashable
        assert "schema_version" in hashable
        assert "project" in hashable
        assert "final_status" in hashable
        assert "errors" in hashable
        assert "suggested_actions" in hashable

        # Não deve conter campos voláteis ou extras
        assert "timestamp" not in hashable
        assert "duration_ms" not in hashable
        assert "content_hash_sha256" not in hashable
        assert "contract_notes" not in hashable
        assert "probable_cause" not in hashable


class TestMarkdownHeaderTwoLines:
    """Testes para garantir que o Markdown header está em 2 linhas."""

    def test_markdown_has_schema_version_on_separate_line(self):
        """[Markdown] SCHEMA VERSION está em linha separada."""
        report = DiagnosticReport(
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
            repo_path="/path",
            failed_repo_path="/path",
        )

        md = report.to_markdown()
        lines = md.split('\n')

        # Encontrar linha com SCHEMA VERSION
        schema_lines = [l for l in lines if "SCHEMA VERSION:" in l]
        assert len(schema_lines) == 1

        schema_line = schema_lines[0]

        # Não deve conter CONTENT HASH na mesma linha
        assert "CONTENT HASH" not in schema_line

    def test_markdown_has_content_hash_on_separate_line(self):
        """[Markdown] CONTENT HASH está em linha separada."""
        report = DiagnosticReport(
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
            repo_path="/path",
            failed_repo_path="/path",
        )

        md = report.to_markdown()
        lines = md.split('\n')

        # Encontrar linha com CONTENT HASH
        hash_lines = [l for l in lines if "CONTENT HASH:" in l]
        assert len(hash_lines) == 1

        hash_line = hash_lines[0]

        # Não deve conter SCHEMA VERSION na mesma linha
        assert "SCHEMA VERSION" not in hash_line

    def test_markdown_contract_section_format(self):
        """[Markdown] Seção Contract tem formato correto."""
        report = DiagnosticReport(
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
            repo_path="/path",
            failed_repo_path="/path",
        )

        md = report.to_markdown()

        # Verificar que ambos estão presentes
        assert "SCHEMA VERSION: diagnostic_report.v1" in md
        assert "CONTENT HASH:" in md

        # Verificar que hash tem 64 caracteres (SHA256)
        import re
        hash_match = re.search(r"CONTENT HASH: ([a-f0-9]{64})", md)
        assert hash_match is not None, "Hash SHA256 deve ter 64 caracteres hex"


class TestGeneratorPropagatesContractNotes:
    """Testes para garantir que Generator propaga contract_notes."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_generator_propagates_contract_notes_from_run_result(self, temp_store):
        """[Generator] Propaga contract_notes do run_result."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            "contract_notes": "Note from run_result",
        }

        report = generator.generate("test_project", run_result)

        assert report is not None
        assert report.contract_notes == "Note from run_result"

    def test_generator_handles_missing_contract_notes(self, temp_store):
        """[Generator] Lida com contract_notes ausente."""
        generator = DiagnosticReportGenerator(
            store_root=str(temp_store),
            generated_root="/tmp/generated",
        )

        run_result = {
            "success": False,
            "release_mode": True,
            "final_status": "BUILD_FAILED",
            # contract_notes ausente
        }

        report = generator.generate("test_project", run_result)

        assert report is not None
        assert report.contract_notes is None
