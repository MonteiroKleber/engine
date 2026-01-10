"""Teste de regressão: out_dir aceita str além de Path.

Bug original: AttributeError("'str' object has no attribute 'mkdir'")
quando out_dir era passado como string.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import release.runtime_evidence_collector as rec
from release.runtime_evidence_collector import SubprocessResult


@pytest.fixture
def temp_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docker-compose.yml").write_text("services: {}")

    # Mock _run_command para não depender de docker real
    def fake_run_command(cmd, cwd=None, timeout=None):
        return SubprocessResult(
            ok=True,
            stdout="",
            stderr="",
            exit_code=0,
            command=" ".join(cmd) if isinstance(cmd, list) else str(cmd),
            error="",
        )

    monkeypatch.setattr(rec, "_run_command", fake_run_command)

    return repo


def test_collect_runtime_evidence_accepts_str_out_dir(temp_repo):
    """Passar out_dir como string não causa exception e cria arquivos."""
    out_dir = temp_repo / "evidence"

    # Passar out_dir como STRING (não Path) - era o bug original
    evidence = rec.collect_runtime_evidence(
        repo_path=str(temp_repo),
        compose_file="docker-compose.yml",
        services=["backend"],
        out_dir=str(out_dir),  # STRING, não Path
    )

    # Verificar que arquivos foram criados
    assert out_dir.exists(), "Diretório de evidências não foi criado"
    files = list(out_dir.glob("runtime_evidence_*.json"))
    assert files, "Nenhum arquivo de evidência JSON gerado"

    md_files = list(out_dir.glob("runtime_evidence_*.md"))
    assert md_files, "Nenhum arquivo de evidência Markdown gerado"

    data = json.loads(files[0].read_text())
    assert data["repo_path"] == str(temp_repo)
    assert evidence["repo_path"] == str(temp_repo)
    assert "conclusion_hint" in evidence


def test_collect_runtime_evidence_accepts_path_out_dir(temp_repo):
    """Passar out_dir como Path continua funcionando."""
    out_dir = temp_repo / "evidence_path"

    evidence = rec.collect_runtime_evidence(
        repo_path=str(temp_repo),
        compose_file="docker-compose.yml",
        services=["backend"],
        out_dir=out_dir,  # Path, não string
    )

    assert out_dir.exists()
    files = list(out_dir.glob("runtime_evidence_*.json"))
    assert files, "Arquivo JSON não foi gerado"


def test_collect_runtime_evidence_none_out_dir_no_files(temp_repo):
    """Passar out_dir=None não salva arquivos."""
    evidence = rec.collect_runtime_evidence(
        repo_path=str(temp_repo),
        compose_file="docker-compose.yml",
        services=["backend"],
        out_dir=None,
    )

    # Evidence deve ser retornado mas nenhum arquivo criado
    assert evidence is not None
    assert "conclusion_hint" in evidence

    # Nenhum arquivo runtime_evidence no temp_repo
    files = list(temp_repo.glob("**/runtime_evidence_*.json"))
    assert len(files) == 0, "Arquivos foram criados mesmo com out_dir=None"
