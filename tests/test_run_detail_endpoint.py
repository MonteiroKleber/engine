"""Tests for Run Detail Endpoint."""

import json
import pytest
from pathlib import Path

from engine.pipeline.registry import (
    DevRunsRegistry,
    reset_registry,
)
from engine.pipeline.run_detail import (
    TraceInfo,
    RunDetailResult,
    get_run_detail,
    load_trace,
    load_idl_final,
    DEV_RUN_NOT_FOUND,
    DEV_RUN_TRACE_NOT_FOUND,
)
from engine.ise import errors as ise_errors


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Setup environment for tests."""
    reset_registry()
    monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))
    monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    return tmp_path


def create_run_with_trace(tmp_path, run_id: str, bundle_name: str):
    """Helper to create a run with trace.json and idl_final.idl."""
    # Create registry entry
    reset_registry()
    registry = DevRunsRegistry(tmp_path / "registry.jsonl")
    registry.emit_created(run_id, bundle_name, str(tmp_path / "dev-runs" / run_id / bundle_name))

    # Create run directory structure
    run_dir = tmp_path / "dev-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    bundle_dir = run_dir / bundle_name
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Create trace.json
    trace_data = {
        "run_id": run_id,
        "bundle_name": bundle_name,
        "sir_sha256": "sir_hash_123",
        "draft_sha256": "draft_hash_456",
        "final_idl_sha256": "idl_hash_789",
        "bundle_manifest_sha256": "manifest_hash_abc",
        "contract_ledger_sha256": "ledger_hash_def",
    }
    (run_dir / "trace.json").write_text(json.dumps(trace_data), encoding="utf-8")

    # Create idl_final.idl
    idl_data = {"system": "test", "version": "1.0.0"}
    (run_dir / "idl_final.idl").write_text(json.dumps(idl_data, indent=2), encoding="utf-8")

    return registry


class TestTraceInfo:
    """Test TraceInfo dataclass."""

    def test_to_dict(self):
        """TraceInfo should serialize correctly."""
        trace = TraceInfo(
            run_id="run-123",
            bundle_name="test-bundle",
            sir_sha256="sir_hash",
            draft_sha256="draft_hash",
            final_idl_sha256="idl_hash",
            bundle_manifest_sha256="manifest_hash",
            contract_ledger_sha256="ledger_hash",
        )

        d = trace.to_dict()

        assert d["run_id"] == "run-123"
        assert d["bundle_name"] == "test-bundle"
        assert d["sir_sha256"] == "sir_hash"
        assert d["draft_sha256"] == "draft_hash"
        assert d["final_idl_sha256"] == "idl_hash"
        assert d["bundle_manifest_sha256"] == "manifest_hash"
        assert d["contract_ledger_sha256"] == "ledger_hash"

    def test_from_dict(self):
        """TraceInfo should deserialize correctly."""
        data = {
            "run_id": "run-456",
            "bundle_name": "my-bundle",
            "sir_sha256": "a",
            "draft_sha256": "b",
            "final_idl_sha256": "c",
            "bundle_manifest_sha256": "d",
            "contract_ledger_sha256": "e",
        }

        trace = TraceInfo.from_dict(data)

        assert trace.run_id == "run-456"
        assert trace.bundle_name == "my-bundle"


class TestLoadTrace:
    """Test load_trace function."""

    def test_load_trace_success(self, tmp_path):
        """load_trace should return TraceInfo when trace.json exists."""
        run_dir = tmp_path / "dev-runs" / "run-123"
        run_dir.mkdir(parents=True, exist_ok=True)

        trace_data = {
            "run_id": "run-123",
            "bundle_name": "test",
            "sir_sha256": "a",
            "draft_sha256": "b",
            "final_idl_sha256": "c",
            "bundle_manifest_sha256": "d",
            "contract_ledger_sha256": "e",
        }
        (run_dir / "trace.json").write_text(json.dumps(trace_data))

        trace = load_trace("run-123", str(tmp_path))

        assert trace is not None
        assert trace.run_id == "run-123"

    def test_load_trace_not_found(self, tmp_path):
        """load_trace should return None when trace.json doesn't exist."""
        trace = load_trace("nonexistent", str(tmp_path))
        assert trace is None


class TestLoadIdlFinal:
    """Test load_idl_final function."""

    def test_load_idl_success(self, tmp_path):
        """load_idl_final should return content when file exists."""
        run_dir = tmp_path / "dev-runs" / "run-123"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "idl_final.idl").write_text('{"system": "test"}')

        idl = load_idl_final("run-123", str(tmp_path))

        assert idl is not None
        assert "test" in idl

    def test_load_idl_not_found(self, tmp_path):
        """load_idl_final should return None when file doesn't exist."""
        idl = load_idl_final("nonexistent", str(tmp_path))
        assert idl is None


class TestGetRunDetail:
    """Test get_run_detail function."""

    def test_get_run_detail_success(self, tmp_path, monkeypatch):
        """get_run_detail should return full detail when run exists."""
        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
        create_run_with_trace(tmp_path, "run-123", "test-bundle")

        result = get_run_detail("run-123", str(tmp_path))

        assert result.success
        assert result.run_id == "run-123"
        assert result.bundle_name == "test-bundle"
        assert result.trace is not None
        assert result.trace.sir_sha256 == "sir_hash_123"

    def test_get_run_detail_not_found(self, tmp_path, monkeypatch):
        """get_run_detail should fail when run doesn't exist in registry."""
        reset_registry()
        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))

        result = get_run_detail("nonexistent", str(tmp_path))

        assert not result.success
        assert result.error_code == DEV_RUN_NOT_FOUND

    def test_get_run_detail_trace_not_found(self, tmp_path, monkeypatch):
        """get_run_detail should fail when trace.json doesn't exist."""
        reset_registry()
        monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))

        # Create registry entry but no trace file
        registry = DevRunsRegistry(tmp_path / "registry.jsonl")
        registry.emit_created("run-123", "test-bundle", str(tmp_path / "dev-runs" / "run-123" / "test-bundle"))

        result = get_run_detail("run-123", str(tmp_path))

        assert not result.success
        assert result.error_code == DEV_RUN_TRACE_NOT_FOUND


class TestRunDetailEndpointAuth:
    """Test authentication for run detail endpoint."""

    def test_detail_without_token_returns_401(self, setup_env):
        """Detail endpoint without token should return 401."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/pipeline/build/runs/some-run-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED

    def test_detail_with_invalid_token_returns_401(self, setup_env, monkeypatch):
        """Detail endpoint with invalid token should return 401."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs/some-run-id",
            headers={"X-Admin-Token": "wrong-token"},
        )

        assert response.status_code == 401

    def test_detail_with_valid_token_passes_auth(self, setup_env, monkeypatch):
        """Detail endpoint with valid token should pass auth (may return 404)."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs/nonexistent-run",
            headers={"X-Admin-Token": "test-token"},
        )

        # Auth passes, returns 404 for not found
        assert response.status_code == 404


class TestRunDetailEndpointResponse:
    """Test run detail endpoint response."""

    def test_detail_returns_full_info(self, setup_env, monkeypatch):
        """Detail endpoint should return full run info."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        tmp_path = setup_env
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        create_run_with_trace(tmp_path, "run-abc", "my-bundle")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs/run-abc",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["run_id"] == "run-abc"
        assert data["bundle_name"] == "my-bundle"
        assert "trace" in data
        assert data["trace"]["sir_sha256"] == "sir_hash_123"

    def test_detail_not_found_returns_404(self, setup_env, monkeypatch):
        """Detail endpoint should return 404 for nonexistent run."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs/nonexistent",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == DEV_RUN_NOT_FOUND

    def test_detail_trace_not_found_returns_404(self, setup_env, monkeypatch):
        """Detail endpoint should return 404 when trace.json missing."""
        from fastapi.testclient import TestClient
        from engine.api.server import app
        from engine.pipeline.registry import get_registry

        tmp_path = setup_env
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        # Create registry entry but no trace file
        registry = get_registry()
        registry.emit_created("run-no-trace", "bundle", str(tmp_path / "dev-runs" / "run-no-trace" / "bundle"))

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs/run-no-trace",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == DEV_RUN_TRACE_NOT_FOUND


class TestRunDetailResult:
    """Test RunDetailResult dataclass."""

    def test_to_dict_success(self):
        """Successful result should serialize correctly."""
        trace = TraceInfo(
            run_id="run-123",
            bundle_name="test",
            sir_sha256="a",
            draft_sha256="b",
            final_idl_sha256="c",
            bundle_manifest_sha256="d",
            contract_ledger_sha256="e",
        )
        result = RunDetailResult(
            success=True,
            run_id="run-123",
            bundle_name="test",
            created_at="2024-01-15T10:00:00+00:00",
            has_zip=True,
            zip_path="/path/to/zip",
            deleted=False,
            trace=trace,
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["run_id"] == "run-123"
        assert d["trace"]["sir_sha256"] == "a"

    def test_to_dict_error(self):
        """Error result should serialize correctly."""
        result = RunDetailResult(
            success=False,
            error_code=DEV_RUN_NOT_FOUND,
            error_message="Run not found",
        )

        d = result.to_dict()

        assert d["success"] is False
        assert d["error"]["code"] == DEV_RUN_NOT_FOUND
