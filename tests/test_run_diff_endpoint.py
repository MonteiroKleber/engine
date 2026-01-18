"""Tests for Run Diff Endpoint."""

import json
import pytest
from pathlib import Path

from engine.pipeline.registry import reset_registry
from engine.pipeline.diff import (
    DiffResult,
    diff_runs,
    generate_unified_diff,
    RUN_DIFF_TOO_LARGE,
    MAX_DIFF_SIZE_BYTES,
)
from engine.pipeline.run_detail import DEV_RUN_IDL_NOT_FOUND
from engine.ise import errors as ise_errors


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Setup environment for tests."""
    reset_registry()
    monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))
    monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    return tmp_path


def create_run_with_idl(tmp_path, run_id: str, idl_content: str):
    """Helper to create a run with idl_final.idl."""
    run_dir = tmp_path / "dev-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "idl_final.idl").write_text(idl_content, encoding="utf-8")
    return run_dir


class TestGenerateUnifiedDiff:
    """Test generate_unified_diff function."""

    def test_diff_identical_texts(self):
        """Identical texts should produce empty diff."""
        text = "line1\nline2\nline3"
        diff = generate_unified_diff(text, text)

        # Unified diff of identical texts is empty
        assert diff == "" or not diff.strip()

    def test_diff_different_texts(self):
        """Different texts should produce unified diff."""
        text_a = "line1\nline2\nline3"
        text_b = "line1\nmodified\nline3"

        diff = generate_unified_diff(text_a, text_b)

        assert "---" in diff
        assert "+++" in diff
        assert "-line2" in diff
        assert "+modified" in diff

    def test_diff_with_labels(self):
        """Diff should include custom labels."""
        text_a = "old"
        text_b = "new"

        diff = generate_unified_diff(text_a, text_b, label_a="file_a.txt", label_b="file_b.txt")

        assert "file_a.txt" in diff
        assert "file_b.txt" in diff


class TestDiffRuns:
    """Test diff_runs function."""

    def test_diff_identical_runs(self, tmp_path):
        """Identical IDL files should produce empty diff."""
        idl = '{"system": "test", "version": "1.0.0"}'
        create_run_with_idl(tmp_path, "run-a", idl)
        create_run_with_idl(tmp_path, "run-b", idl)

        result = diff_runs("run-a", "run-b", str(tmp_path))

        assert result.success
        assert result.is_identical is True
        assert result.diff == "" or not result.diff.strip()

    def test_diff_different_runs(self, tmp_path):
        """Different IDL files should produce unified diff."""
        idl_a = '{"system": "test", "version": "1.0.0"}'
        idl_b = '{"system": "test", "version": "2.0.0"}'
        create_run_with_idl(tmp_path, "run-a", idl_a)
        create_run_with_idl(tmp_path, "run-b", idl_b)

        result = diff_runs("run-a", "run-b", str(tmp_path))

        assert result.success
        assert result.is_identical is False
        assert "1.0.0" in result.diff
        assert "2.0.0" in result.diff

    def test_diff_run_a_not_found(self, tmp_path):
        """Missing run_a should return error."""
        idl_b = '{"system": "test"}'
        create_run_with_idl(tmp_path, "run-b", idl_b)

        result = diff_runs("nonexistent", "run-b", str(tmp_path))

        assert not result.success
        assert result.error_code == DEV_RUN_IDL_NOT_FOUND
        assert "nonexistent" in result.error_message

    def test_diff_run_b_not_found(self, tmp_path):
        """Missing run_b should return error."""
        idl_a = '{"system": "test"}'
        create_run_with_idl(tmp_path, "run-a", idl_a)

        result = diff_runs("run-a", "nonexistent", str(tmp_path))

        assert not result.success
        assert result.error_code == DEV_RUN_IDL_NOT_FOUND
        assert "nonexistent" in result.error_message

    def test_diff_too_large_run_a(self, tmp_path):
        """Large IDL in run_a should return error."""
        large_idl = "x" * (MAX_DIFF_SIZE_BYTES + 1)
        idl_b = '{"system": "test"}'
        create_run_with_idl(tmp_path, "run-a", large_idl)
        create_run_with_idl(tmp_path, "run-b", idl_b)

        result = diff_runs("run-a", "run-b", str(tmp_path))

        assert not result.success
        assert result.error_code == RUN_DIFF_TOO_LARGE

    def test_diff_too_large_run_b(self, tmp_path):
        """Large IDL in run_b should return error."""
        idl_a = '{"system": "test"}'
        large_idl = "x" * (MAX_DIFF_SIZE_BYTES + 1)
        create_run_with_idl(tmp_path, "run-a", idl_a)
        create_run_with_idl(tmp_path, "run-b", large_idl)

        result = diff_runs("run-a", "run-b", str(tmp_path))

        assert not result.success
        assert result.error_code == RUN_DIFF_TOO_LARGE

    def test_diff_returns_sizes(self, tmp_path):
        """Result should include file sizes."""
        idl_a = '{"a": 1}'
        idl_b = '{"b": 2, "c": 3}'
        create_run_with_idl(tmp_path, "run-a", idl_a)
        create_run_with_idl(tmp_path, "run-b", idl_b)

        result = diff_runs("run-a", "run-b", str(tmp_path))

        assert result.success
        assert result.size_a == len(idl_a.encode("utf-8"))
        assert result.size_b == len(idl_b.encode("utf-8"))


class TestDiffEndpointAuth:
    """Test authentication for diff endpoint."""

    def test_diff_without_token_returns_401(self, setup_env):
        """Diff endpoint without token should return 401."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/pipeline/build/diff?run_a=a&run_b=b")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED

    def test_diff_with_invalid_token_returns_401(self, setup_env, monkeypatch):
        """Diff endpoint with invalid token should return 401."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/diff?run_a=a&run_b=b",
            headers={"X-Admin-Token": "wrong-token"},
        )

        assert response.status_code == 401

    def test_diff_with_valid_token_passes_auth(self, setup_env, monkeypatch):
        """Diff endpoint with valid token should pass auth (may return 404)."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/diff?run_a=nonexistent1&run_b=nonexistent2",
            headers={"X-Admin-Token": "test-token"},
        )

        # Auth passes, returns 404 for not found
        assert response.status_code == 404


class TestDiffEndpointResponse:
    """Test diff endpoint response."""

    def test_diff_returns_unified_diff(self, setup_env, monkeypatch):
        """Diff endpoint should return unified diff."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        tmp_path = setup_env
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        idl_a = '{"system": "test", "version": "1.0.0"}'
        idl_b = '{"system": "test", "version": "2.0.0"}'
        create_run_with_idl(tmp_path, "run-a", idl_a)
        create_run_with_idl(tmp_path, "run-b", idl_b)

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/diff?run_a=run-a&run_b=run-b",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["run_a"] == "run-a"
        assert data["run_b"] == "run-b"
        assert data["is_identical"] is False
        assert "diff" in data

    def test_diff_identical_returns_empty(self, setup_env, monkeypatch):
        """Diff endpoint should return empty diff for identical files."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        tmp_path = setup_env
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        idl = '{"system": "test"}'
        create_run_with_idl(tmp_path, "run-a", idl)
        create_run_with_idl(tmp_path, "run-b", idl)

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/diff?run_a=run-a&run_b=run-b",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_identical"] is True

    def test_diff_not_found_returns_404(self, setup_env, monkeypatch):
        """Diff endpoint should return 404 for missing IDL."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/diff?run_a=nonexistent&run_b=also-nonexistent",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == DEV_RUN_IDL_NOT_FOUND

    def test_diff_too_large_returns_413(self, setup_env, monkeypatch):
        """Diff endpoint should return 413 for large IDL files."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        tmp_path = setup_env
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        large_idl = "x" * (MAX_DIFF_SIZE_BYTES + 1)
        small_idl = '{"system": "test"}'
        create_run_with_idl(tmp_path, "run-large", large_idl)
        create_run_with_idl(tmp_path, "run-small", small_idl)

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/diff?run_a=run-large&run_b=run-small",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 413
        data = response.json()
        assert data["code"] == RUN_DIFF_TOO_LARGE


class TestDiffEndpointValidation:
    """Test diff endpoint parameter validation."""

    def test_diff_missing_run_a_returns_422(self, setup_env, monkeypatch):
        """Diff endpoint should return 422 when run_a is missing."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/diff?run_b=b",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 422

    def test_diff_missing_run_b_returns_422(self, setup_env, monkeypatch):
        """Diff endpoint should return 422 when run_b is missing."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/diff?run_a=a",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 422


class TestDiffResult:
    """Test DiffResult dataclass."""

    def test_to_dict_success(self):
        """Successful result should serialize correctly."""
        result = DiffResult(
            success=True,
            run_a="run-a",
            run_b="run-b",
            diff="--- a\n+++ b\n",
            is_identical=False,
            size_a=100,
            size_b=200,
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["run_a"] == "run-a"
        assert d["run_b"] == "run-b"
        assert d["is_identical"] is False
        assert d["size_a"] == 100
        assert d["size_b"] == 200

    def test_to_dict_error(self):
        """Error result should serialize correctly."""
        result = DiffResult(
            success=False,
            error_code=RUN_DIFF_TOO_LARGE,
            error_message="Too large",
        )

        d = result.to_dict()

        assert d["success"] is False
        assert d["error"]["code"] == RUN_DIFF_TOO_LARGE
