"""Tests for Pipeline Build BUILT path."""

import json
import pytest
from pathlib import Path

from engine.pipeline.orchestrator import (
    build_pipeline,
    STATUS_BUILT,
    STATUS_NEEDS_ANSWERS,
)


# Valid text that the extractor can handle
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
            q_type = question.get("question_type", "boolean")
            default = question.get("default_value")

            if default is not None:
                value = default
            elif q_type == "boolean":
                value = True
            elif q_type == "number":
                value = 1
            elif q_type == "choice":
                options = question.get("options", [])
                value = options[0] if options else "default"
            else:
                value = "default"

            answers.append({"question_id": q_id, "value": value})

    return answers


class TestBuildReturnsBuilt:
    """Test that successful build returns BUILT status."""

    def test_build_returns_built(self, tmp_path):
        """Build with all answers should return BUILT."""
        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        # Get answers for all gaps
        answers = get_answers_for_gaps(result1)

        # Second run with answers
        result = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_BUILT
        assert result.bundle_name == "test-bundle"
        assert result.run_id is not None
        assert result.bundle_path is not None

    def test_build_creates_bundle_path(self, tmp_path):
        """Build should create bundle at expected path."""
        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        # Second run with answers
        result = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_BUILT
        assert result.bundle_path is not None

        # Verify path exists
        bundle_path = Path(result.bundle_path)
        assert bundle_path.exists()
        assert bundle_path.is_dir()

        # Verify path is in dev-runs sandbox
        assert "dev-runs" in str(bundle_path)
        assert result.run_id in str(bundle_path)

    def test_build_creates_manifest(self, tmp_path):
        """Build should create bundle.manifest.json."""
        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        # Second run with answers
        result = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_BUILT
        assert result.bundle_path is not None

        # Verify manifest exists
        bundle_path = Path(result.bundle_path)
        manifest_path = bundle_path / "bundle.manifest.json"
        assert manifest_path.exists()

        # Verify manifest is valid JSON
        manifest = json.loads(manifest_path.read_text())
        assert "bundle_name" in manifest
        assert "bundle_hash" in manifest
        assert "contracts" in manifest

    def test_build_includes_all_hashes(self, tmp_path):
        """BUILT result should include all trace hashes."""
        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        # Second run with answers
        result = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_BUILT
        assert result.hash_sir is not None
        assert len(result.hash_sir) == 64  # SHA256 hex
        assert result.hash_draft is not None
        assert len(result.hash_draft) == 64
        assert result.hash_idl_final is not None
        assert len(result.hash_idl_final) == 64
        assert result.bundle_hash is not None

    def test_build_run_id_is_uuid(self, tmp_path):
        """Run ID should be a valid UUID v4."""
        import uuid

        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        # Second run with answers
        result = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_BUILT
        assert result.run_id is not None

        # Verify it's a valid UUID
        parsed = uuid.UUID(result.run_id)
        assert parsed.version == 4


class TestBuildToDict:
    """Test BUILT result serialization."""

    def test_to_dict_includes_build_fields(self, tmp_path):
        """to_dict should include run_id, bundle_path, hashes."""
        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        # Second run with answers
        result = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        d = result.to_dict()

        assert d["status"] == "BUILT"
        assert d["bundle_name"] == "test-bundle"
        assert "run_id" in d
        assert "bundle_path" in d
        assert "hash_sir" in d
        assert "hash_draft" in d
        assert "hash_idl_final" in d
        assert "bundle_hash" in d
        # BUILT should not have error or gaps
        assert "error" not in d
        assert "gaps" not in d


class TestBuildViaAPI:
    """Test BUILT response via API endpoint."""

    def test_api_returns_built(self, tmp_path, monkeypatch):
        """API should return BUILT with proper structure."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        # First call to get gaps
        response1 = client.post(
            "/pipeline/build",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle", "answers": None},
        )

        data1 = response1.json()
        answers = []
        if data1.get("status") == "NEEDS_ANSWERS" and data1.get("gaps"):
            for gap in data1["gaps"]:
                for question in gap.get("questions", []):
                    q_id = question["question_id"]
                    default = question.get("default_value", True)
                    answers.append({"question_id": q_id, "value": default})

        # Second call with answers
        response = client.post(
            "/pipeline/build",
            json={
                "text": VALID_TEXT,
                "bundle_name": "test-bundle",
                "answers": answers,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "BUILT"
        assert "run_id" in data
        assert "bundle_path" in data
        assert "bundle_hash" in data

    def test_api_validation_text_required(self, tmp_path, monkeypatch):
        """API should return 400 if text is empty."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        response = client.post(
            "/pipeline/build",
            json={"text": "", "bundle_name": "test-bundle", "answers": None},
        )

        # Pydantic validates min_length=1
        assert response.status_code == 422

    def test_api_validation_bundle_name_required(self, tmp_path, monkeypatch):
        """API should return 400 if bundle_name is empty."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        response = client.post(
            "/pipeline/build",
            json={"text": VALID_TEXT, "bundle_name": "", "answers": None},
        )

        # Pydantic validates min_length=1
        assert response.status_code == 422
