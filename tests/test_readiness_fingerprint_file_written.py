"""Testa que o readiness escreve fingerprint e evidencia mínima em caso de falha."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import release.docker_compose_validator as dcv


class DummyResult(SimpleNamespace):
    pass


@pytest.fixture
def temp_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    # Mock subprocess.run para não chamar docker
    def fake_run(*args, **kwargs):
        return DummyResult(stdout=b"", stderr=b"", returncode=0)

    monkeypatch.setattr(dcv.subprocess, "run", fake_run)

    # Mock urlopen para forçar falha HTTP
    class FakeError(Exception):
        pass

    def fake_urlopen(*args, **kwargs):
        raise FakeError("network off")

    monkeypatch.setattr(dcv.urllib.request, "urlopen", fake_urlopen)

    # Mock collect_runtime_evidence para lançar exceção e forçar minimal json
    def fake_collect(**kwargs):
        raise RuntimeError("collect failed")

    monkeypatch.setattr(dcv, "collect_runtime_evidence", fake_collect)

    # Não dormir em testes
    monkeypatch.setattr(dcv.time, "sleep", lambda x: None)

    return repo


def test_readiness_writes_fingerprint_and_minimal_evidence(temp_repo):
    validator = dcv.DockerComposeValidator(generated_root=str(temp_repo.parent))

    # Forçar timeout curto para sair rápido
    result = validator.wait_for_readiness(
        project="repo",
        timeout=0.1,
        poll_interval=0.01,
    )

    repo_root = temp_repo.parent / "repo"
    fingerprint_file = repo_root / ".engine_readiness_fingerprint.txt"
    evidence_file = repo_root / ".engine_evidence" / "runtime_evidence_minimal.json"

    assert fingerprint_file.exists(), "Fingerprint file não foi criado"
    assert dcv.DockerComposeValidator.READINESS_FINGERPRINT in fingerprint_file.read_text()
    assert evidence_file.exists(), "Evidência mínima não foi criada"
    data = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert data.get("fingerprint") == dcv.DockerComposeValidator.READINESS_FINGERPRINT
    assert "error" in data
