"""Tests for Pipeline Export not found cases."""

import pytest

from engine.pipeline.orchestrator import build_pipeline, STATUS_BUILT, STATUS_NEEDS_ANSWERS
from engine.pipeline.exporter import (
    export_bundle_zip,
    PIPELINE_RUN_NOT_FOUND,
    PIPELINE_BUNDLE_NOT_FOUND,
)


VALID_TEXT = """
Employees can create expenses.
Managers approve expenses.
No self-approval allowed.
"""


def get_answers_for_gaps(result):
    """Generate mock answers for all required gaps."""
    if result.status != STATUS_NEEDS_ANSWERS or not result.gaps:
        return []

    answers = []
    for gap in result.gaps:
        for question in gap.get("questions", []):
            q_id = question["question_id"]
            default = question.get("default_value", True)
            answers.append({"question_id": q_id, "value": default})

    return answers


class TestExportRunNotFound:
    """Test export when run does not exist."""

    def test_export_nonexistent_run_returns_error(self, tmp_path):
        """Export with nonexistent run_id should return error."""
        result = export_bundle_zip(
            run_id="nonexistent-run-id",
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )

        assert not result.success
        assert result.error_code == PIPELINE_RUN_NOT_FOUND
        assert "not found" in result.error_message.lower()

    def test_export_nonexistent_run_to_dict(self, tmp_path):
        """Export error to_dict should have correct structure."""
        result = export_bundle_zip(
            run_id="nonexistent-run-id",
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )

        d = result.to_dict()

        assert d["status"] == "FAILED"
        assert "error" in d
        assert d["error"]["code"] == PIPELINE_RUN_NOT_FOUND


class TestExportBundleNotFound:
    """Test export when bundle does not exist in run."""

    def test_export_nonexistent_bundle_returns_error(self, tmp_path):
        """Export with nonexistent bundle should return error."""
        # Build a bundle first
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="actual-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )
        answers = get_answers_for_gaps(result1)

        result_built = build_pipeline(
            text=VALID_TEXT,
            bundle_name="actual-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        assert result_built.status == STATUS_BUILT
        run_id = result_built.run_id

        # Try to export a different bundle name
        result = export_bundle_zip(
            run_id=run_id,
            bundle_name="wrong-bundle-name",
            bundles_root=str(tmp_path),
        )

        assert not result.success
        assert result.error_code == PIPELINE_BUNDLE_NOT_FOUND
        assert "not found" in result.error_message.lower()


class TestExportViaAPINotFound:
    """Test export via API returns correct HTTP errors."""

    def test_api_export_nonexistent_run_returns_404(self, tmp_path, monkeypatch):
        """API export with nonexistent run should return 404."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/pipeline/build/export",
            json={"run_id": "nonexistent-run-id", "bundle_name": "test-bundle"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == PIPELINE_RUN_NOT_FOUND

    def test_api_export_nonexistent_bundle_returns_404(self, tmp_path, monkeypatch):
        """API export with nonexistent bundle should return 404."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        # Build a bundle first
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="actual-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )
        answers = get_answers_for_gaps(result1)

        result_built = build_pipeline(
            text=VALID_TEXT,
            bundle_name="actual-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        run_id = result_built.run_id

        # Try to export wrong bundle name
        response = client.post(
            "/pipeline/build/export",
            json={"run_id": run_id, "bundle_name": "wrong-bundle"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == PIPELINE_BUNDLE_NOT_FOUND

    def test_api_export_empty_run_id_returns_422(self, tmp_path, monkeypatch):
        """API export with empty run_id should return 422."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/pipeline/build/export",
            json={"run_id": "", "bundle_name": "test-bundle"},
        )

        assert response.status_code == 422

    def test_api_export_empty_bundle_name_returns_422(self, tmp_path, monkeypatch):
        """API export with empty bundle_name should return 422."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/pipeline/build/export",
            json={"run_id": "some-run-id", "bundle_name": ""},
        )

        assert response.status_code == 422


class TestDownloadViaAPINotFound:
    """Test download via API returns correct HTTP errors."""

    def test_api_download_missing_run_id_returns_422(self, tmp_path, monkeypatch):
        """API download without run_id should return 422."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/pipeline/build/download?bundle_name=test-bundle")

        assert response.status_code == 422

    def test_api_download_missing_bundle_name_returns_422(self, tmp_path, monkeypatch):
        """API download without bundle_name should return 422."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/pipeline/build/download?run_id=some-run-id")

        assert response.status_code == 422
