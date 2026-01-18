"""Tests for Pipeline Download ZIP endpoint."""

import zipfile
import pytest
from pathlib import Path

from engine.pipeline.orchestrator import build_pipeline, STATUS_BUILT, STATUS_NEEDS_ANSWERS
from engine.pipeline.exporter import export_bundle_zip


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


class TestDownloadReturnsZip:
    """Test download endpoint returns correct ZIP."""

    def test_download_returns_zip_content(self, tmp_path, monkeypatch):
        """Download should return ZIP file content."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        # Build bundle
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )
        answers = get_answers_for_gaps(result1)

        result_built = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        assert result_built.status == STATUS_BUILT
        run_id = result_built.run_id

        # Export
        export = export_bundle_zip(
            run_id=run_id,
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )
        assert export.success

        # Download
        response = client.get(
            f"/pipeline/build/download?run_id={run_id}&bundle_name=test-bundle"
        )

        assert response.status_code == 200
        assert len(response.content) > 0

        # Verify it's a valid ZIP
        import io
        with zipfile.ZipFile(io.BytesIO(response.content), "r") as zf:
            assert len(zf.namelist()) > 0

    def test_download_has_correct_content_type(self, tmp_path, monkeypatch):
        """Download should return application/zip content type."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        # Build and export
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )
        answers = get_answers_for_gaps(result1)

        result_built = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        run_id = result_built.run_id

        export_bundle_zip(
            run_id=run_id,
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )

        # Download
        response = client.get(
            f"/pipeline/build/download?run_id={run_id}&bundle_name=test-bundle"
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"

    def test_download_has_content_disposition_header(self, tmp_path, monkeypatch):
        """Download should have Content-Disposition attachment header."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        # Build and export
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="my-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )
        answers = get_answers_for_gaps(result1)

        result_built = build_pipeline(
            text=VALID_TEXT,
            bundle_name="my-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        run_id = result_built.run_id

        export_bundle_zip(
            run_id=run_id,
            bundle_name="my-bundle",
            bundles_root=str(tmp_path),
        )

        # Download
        response = client.get(
            f"/pipeline/build/download?run_id={run_id}&bundle_name=my-bundle"
        )

        assert response.status_code == 200
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp
        assert 'filename="my-bundle.zip"' in content_disp


class TestDownloadViaAPI:
    """Test download via API endpoint."""

    def test_download_after_export(self, tmp_path, monkeypatch):
        """Full flow: build -> export -> download."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        # Build via API
        build_response1 = client.post(
            "/pipeline/build",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle", "answers": None},
        )
        assert build_response1.status_code == 200
        data1 = build_response1.json()

        # Get answers
        answers = []
        if data1.get("status") == "NEEDS_ANSWERS" and data1.get("gaps"):
            for gap in data1["gaps"]:
                for question in gap.get("questions", []):
                    q_id = question["question_id"]
                    default = question.get("default_value", True)
                    answers.append({"question_id": q_id, "value": default})

        # Build with answers
        build_response2 = client.post(
            "/pipeline/build",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle", "answers": answers},
        )
        assert build_response2.status_code == 200
        data2 = build_response2.json()
        assert data2["status"] == "BUILT"
        run_id = data2["run_id"]

        # Export via API
        export_response = client.post(
            "/pipeline/build/export",
            json={"run_id": run_id, "bundle_name": "test-bundle"},
        )
        assert export_response.status_code == 200
        export_data = export_response.json()
        assert export_data["status"] == "EXPORTED"
        assert "download_url" in export_data

        # Download via API
        download_response = client.get(export_data["download_url"])
        assert download_response.status_code == 200
        assert len(download_response.content) > 0

    def test_download_no_auth_required(self, tmp_path, monkeypatch):
        """Download should NOT require authentication."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        # Build and export
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )
        answers = get_answers_for_gaps(result1)

        result_built = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        run_id = result_built.run_id

        export_bundle_zip(
            run_id=run_id,
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )

        # Download without any auth headers
        response = client.get(
            f"/pipeline/build/download?run_id={run_id}&bundle_name=test-bundle"
            # No X-Admin-Token header!
        )

        assert response.status_code == 200


class TestDownloadNotFound:
    """Test download returns 404 when ZIP not found."""

    def test_download_without_export_returns_404(self, tmp_path, monkeypatch):
        """Download without prior export should return 404."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        # Build but don't export
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )
        answers = get_answers_for_gaps(result1)

        result_built = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        run_id = result_built.run_id

        # Try to download without exporting first
        response = client.get(
            f"/pipeline/build/download?run_id={run_id}&bundle_name=test-bundle"
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "PIPELINE_DOWNLOAD_NOT_FOUND"

    def test_download_nonexistent_run_returns_404(self, tmp_path, monkeypatch):
        """Download with nonexistent run_id should return 404."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/pipeline/build/download?run_id=nonexistent-run-id&bundle_name=test-bundle"
        )

        assert response.status_code == 404
