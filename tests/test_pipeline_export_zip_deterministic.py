"""Tests for Pipeline Export ZIP deterministic behavior."""

import zipfile
import pytest
from pathlib import Path

from engine.pipeline.orchestrator import build_pipeline, STATUS_BUILT, STATUS_NEEDS_ANSWERS
from engine.pipeline.exporter import (
    export_bundle_zip,
    compute_sha256,
    FIXED_ZIP_TIMESTAMP,
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


class TestExportDeterministic:
    """Test that export produces deterministic ZIP."""

    def test_export_produces_same_hash_on_multiple_runs(self, tmp_path):
        """Two exports of same bundle should produce identical SHA256."""
        # First build
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

        # First export
        export1 = export_bundle_zip(
            run_id=run_id,
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )
        assert export1.success
        hash1 = export1.zip_sha256

        # Delete ZIP and re-export
        zip_path = Path(export1.zip_path)
        zip_path.unlink()

        # Second export
        export2 = export_bundle_zip(
            run_id=run_id,
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )
        assert export2.success
        hash2 = export2.zip_sha256

        # Hashes must be identical
        assert hash1 == hash2

    def test_export_zip_has_fixed_timestamps(self, tmp_path):
        """All files in ZIP should have fixed timestamp 1980-01-01."""
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

        # Check ZIP contents
        with zipfile.ZipFile(export.zip_path, "r") as zf:
            for info in zf.infolist():
                assert info.date_time == FIXED_ZIP_TIMESTAMP, f"File {info.filename} has wrong timestamp"

    def test_export_zip_has_sorted_paths(self, tmp_path):
        """Files in ZIP should be sorted alphabetically."""
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

        # Check ZIP contents are sorted
        with zipfile.ZipFile(export.zip_path, "r") as zf:
            names = zf.namelist()
            assert names == sorted(names), "Files in ZIP are not sorted"

    def test_export_zip_contains_bundle_root(self, tmp_path):
        """ZIP should contain files under <bundle_name>/ root."""
        # Build bundle
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

        assert result_built.status == STATUS_BUILT
        run_id = result_built.run_id

        # Export
        export = export_bundle_zip(
            run_id=run_id,
            bundle_name="my-bundle",
            bundles_root=str(tmp_path),
        )
        assert export.success

        # Check all files start with bundle name
        with zipfile.ZipFile(export.zip_path, "r") as zf:
            for name in zf.namelist():
                assert name.startswith("my-bundle/"), f"File {name} doesn't start with bundle root"

    def test_export_zip_contains_manifest(self, tmp_path):
        """ZIP should contain bundle.manifest.json."""
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

        # Check manifest exists
        with zipfile.ZipFile(export.zip_path, "r") as zf:
            names = zf.namelist()
            assert "test-bundle/bundle.manifest.json" in names

    def test_export_uses_deflate_compression(self, tmp_path):
        """ZIP should use DEFLATED compression."""
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

        # Check compression type
        with zipfile.ZipFile(export.zip_path, "r") as zf:
            for info in zf.infolist():
                assert info.compress_type == zipfile.ZIP_DEFLATED


class TestExportResult:
    """Test export result structure."""

    def test_export_returns_zip_path(self, tmp_path):
        """Export should return zip_path."""
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

        run_id = result_built.run_id

        # Export
        export = export_bundle_zip(
            run_id=run_id,
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )

        assert export.success
        assert export.zip_path is not None
        assert Path(export.zip_path).exists()
        assert export.zip_path.endswith(".zip")

    def test_export_returns_sha256(self, tmp_path):
        """Export should return zip_sha256."""
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

        run_id = result_built.run_id

        # Export
        export = export_bundle_zip(
            run_id=run_id,
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )

        assert export.success
        assert export.zip_sha256 is not None
        assert len(export.zip_sha256) == 64  # SHA256 hex

        # Verify hash is correct
        actual_hash = compute_sha256(Path(export.zip_path))
        assert export.zip_sha256 == actual_hash

    def test_export_returns_download_url(self, tmp_path):
        """Export should return download_url."""
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

        run_id = result_built.run_id

        # Export
        export = export_bundle_zip(
            run_id=run_id,
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )

        assert export.success
        assert export.download_url is not None
        assert f"run_id={run_id}" in export.download_url
        assert "bundle_name=test-bundle" in export.download_url

    def test_export_to_dict(self, tmp_path):
        """Export to_dict should have correct structure."""
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

        run_id = result_built.run_id

        # Export
        export = export_bundle_zip(
            run_id=run_id,
            bundle_name="test-bundle",
            bundles_root=str(tmp_path),
        )

        d = export.to_dict()

        assert d["status"] == "EXPORTED"
        assert "zip_path" in d
        assert "zip_sha256" in d
        assert "download_url" in d
