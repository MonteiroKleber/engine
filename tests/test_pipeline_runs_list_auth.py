"""Tests for Pipeline Runs List Authentication."""

import pytest
from datetime import datetime, timezone, timedelta

from engine.pipeline.registry import (
    DevRunsRegistry,
    RegistryEvent,
    EVENT_DEV_RUN_CREATED,
    reset_registry,
)
from engine.ise import errors as ise_errors


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Setup environment for tests."""
    reset_registry()
    monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))
    monkeypatch.setenv("ENGINE_DEV_RUNS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    return tmp_path


class TestRunsListAuth:
    """Test authentication for /pipeline/build/runs endpoint."""

    def test_runs_without_token_returns_401(self, setup_env):
        """Runs endpoint without token should return 401."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/pipeline/build/runs")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ise_errors.ISE_ADMIN_UNAUTHORIZED

    def test_runs_with_invalid_token_returns_401(self, setup_env, monkeypatch):
        """Runs endpoint with invalid token should return 401."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs",
            headers={"X-Admin-Token": "wrong-token"},
        )

        assert response.status_code == 401

    def test_runs_with_valid_token_returns_200(self, setup_env, monkeypatch):
        """Runs endpoint with valid token should return 200."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "runs" in data
        assert "total" in data


class TestRunsListResponse:
    """Test /pipeline/build/runs response structure."""

    def test_runs_returns_empty_list_initially(self, setup_env, monkeypatch):
        """Runs endpoint should return empty list initially."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_runs_returns_created_runs(self, setup_env, monkeypatch):
        """Runs endpoint should return runs from registry."""
        from fastapi.testclient import TestClient
        from engine.api.server import app
        from engine.pipeline.registry import get_registry

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        # Create some runs in registry
        registry = get_registry()
        registry.emit_created("run-001", "bundle-1", "/path/1")
        registry.emit_created("run-002", "bundle-2", "/path/2")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["runs"]) == 2

    def test_runs_sorted_newest_first(self, setup_env, monkeypatch):
        """Runs should be sorted newest first."""
        from fastapi.testclient import TestClient
        from engine.api.server import app
        from engine.pipeline.registry import get_registry

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        registry = get_registry()

        # Create runs with specific timestamps
        now = datetime.now(timezone.utc)
        event1 = RegistryEvent(
            event_type=EVENT_DEV_RUN_CREATED,
            run_id="run-old",
            bundle_name="bundle-old",
            timestamp=(now - timedelta(hours=2)).isoformat(),
            bundle_path="/path/old",
        )
        event2 = RegistryEvent(
            event_type=EVENT_DEV_RUN_CREATED,
            run_id="run-new",
            bundle_name="bundle-new",
            timestamp=now.isoformat(),
            bundle_path="/path/new",
        )
        registry.append_event(event1)
        registry.append_event(event2)

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs",
            headers={"X-Admin-Token": "test-token"},
        )

        data = response.json()
        assert data["runs"][0]["run_id"] == "run-new"  # Newest first
        assert data["runs"][1]["run_id"] == "run-old"

    def test_runs_excludes_deleted(self, setup_env, monkeypatch):
        """Runs should exclude deleted runs."""
        from fastapi.testclient import TestClient
        from engine.api.server import app
        from engine.pipeline.registry import get_registry

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        registry = get_registry()
        registry.emit_created("run-001", "bundle-1", "/path/1")
        registry.emit_created("run-002", "bundle-2", "/path/2")
        registry.emit_deleted("run-001", "bundle-1")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs",
            headers={"X-Admin-Token": "test-token"},
        )

        data = response.json()
        assert data["total"] == 1
        assert data["runs"][0]["run_id"] == "run-002"

    def test_runs_includes_zip_info(self, setup_env, monkeypatch):
        """Runs should include zip info when exported."""
        from fastapi.testclient import TestClient
        from engine.api.server import app
        from engine.pipeline.registry import get_registry

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        registry = get_registry()
        registry.emit_created("run-001", "bundle-1", "/path/1")
        registry.emit_exported("run-001", "bundle-1", "/zip/path", "sha256hash")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs",
            headers={"X-Admin-Token": "test-token"},
        )

        data = response.json()
        run = data["runs"][0]
        assert run["has_zip"] is True
        assert run["zip_path"] == "/zip/path"
        assert run["zip_sha256"] == "sha256hash"


class TestRunsListLimit:
    """Test limit parameter for /pipeline/build/runs."""

    def test_runs_default_limit_50(self, setup_env, monkeypatch):
        """Default limit should be 50."""
        from fastapi.testclient import TestClient
        from engine.api.server import app
        from engine.pipeline.registry import get_registry

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        registry = get_registry()
        for i in range(60):
            registry.emit_created(f"run-{i:03d}", f"bundle-{i}", f"/path/{i}")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs",
            headers={"X-Admin-Token": "test-token"},
        )

        data = response.json()
        assert len(data["runs"]) == 50

    def test_runs_custom_limit(self, setup_env, monkeypatch):
        """Custom limit should be respected."""
        from fastapi.testclient import TestClient
        from engine.api.server import app
        from engine.pipeline.registry import get_registry

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        registry = get_registry()
        for i in range(20):
            registry.emit_created(f"run-{i:03d}", f"bundle-{i}", f"/path/{i}")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs?limit=5",
            headers={"X-Admin-Token": "test-token"},
        )

        data = response.json()
        assert len(data["runs"]) == 5

    def test_runs_max_limit_200(self, setup_env, monkeypatch):
        """Limit should cap at 200."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs?limit=500",
            headers={"X-Admin-Token": "test-token"},
        )

        # Should return 422 because limit > 200
        assert response.status_code == 422

    def test_runs_invalid_limit_returns_422(self, setup_env, monkeypatch):
        """Invalid limit should return 422."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/runs?limit=0",
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 422


class TestCleanupAuth:
    """Test authentication for /pipeline/build/cleanup endpoint."""

    def test_cleanup_without_token_returns_401(self, setup_env):
        """Cleanup endpoint without token should return 401."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/pipeline/build/cleanup",
            json={"dry_run": True},
        )

        assert response.status_code == 401

    def test_cleanup_with_invalid_token_returns_401(self, setup_env, monkeypatch):
        """Cleanup endpoint with invalid token should return 401."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/pipeline/build/cleanup",
            json={"dry_run": True},
            headers={"X-Admin-Token": "wrong-token"},
        )

        assert response.status_code == 401

    def test_cleanup_with_valid_token_returns_200(self, setup_env, monkeypatch):
        """Cleanup endpoint with valid token should return 200."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/pipeline/build/cleanup",
            json={"dry_run": True},
            headers={"X-Admin-Token": "test-token"},
        )

        assert response.status_code == 200
