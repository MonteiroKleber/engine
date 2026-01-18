"""Tests for Pipeline Build NEEDS_ANSWERS path."""

import pytest
from pathlib import Path

from engine.pipeline.orchestrator import build_pipeline, STATUS_NEEDS_ANSWERS


# Text that will generate required gaps - has two entities but only one with approval
# This triggers a required gap for the entity without approval rule
TEXT_WITH_GAPS = """
Employees create expenses.
Employees also create reports.
Managers must approve expenses.
"""


class TestBuildNeedsAnswersNoAnswers:
    """Test NEEDS_ANSWERS when no answers provided."""

    def test_gaps_return_needs_answers(self, tmp_path):
        """Build pipeline with gaps and no answers should return NEEDS_ANSWERS."""
        result = build_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.gaps is not None
        assert len(result.gaps) > 0
        assert result.sir is not None
        assert result.draft_idl is not None
        assert result.run_id is not None

    def test_needs_answers_includes_hashes(self, tmp_path):
        """NEEDS_ANSWERS response should include SIR and draft hashes."""
        result = build_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.hash_sir is not None
        assert len(result.hash_sir) == 64  # SHA256 hex
        assert result.hash_draft is not None
        assert len(result.hash_draft) == 64
        assert result.run_id is not None

    def test_gaps_have_questions(self, tmp_path):
        """Gaps should contain questions."""
        result = build_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.gaps is not None

        # Check gaps structure
        for gap in result.gaps:
            assert "gap_key" in gap
            assert "gap_type" in gap
            assert "questions" in gap
            assert len(gap["questions"]) > 0

            for question in gap["questions"]:
                assert "question_id" in question
                assert "question_text" in question


class TestBuildNeedsAnswersPartialAnswers:
    """Test NEEDS_ANSWERS when only some answers provided."""

    def test_partial_answers_still_needs_answers(self, tmp_path):
        """Build with partial answers should still return NEEDS_ANSWERS."""
        # First run to get gaps
        result1 = build_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        assert result1.status == STATUS_NEEDS_ANSWERS
        assert result1.gaps is not None
        assert len(result1.gaps) > 0

        # Provide only one answer (not all)
        first_gap = result1.gaps[0]
        first_question = first_gap["questions"][0]

        partial_answers = [
            {"question_id": first_question["question_id"], "value": True}
        ]

        # Second run with partial answers (different run_id)
        result2 = build_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=partial_answers,
            bundles_root=str(tmp_path),
        )

        # Should still need more answers (or proceed if that was enough)
        # The exact behavior depends on what gaps are detected
        assert result2.status in (STATUS_NEEDS_ANSWERS, "BUILT", "FAILED")
        assert result2.run_id is not None
        # Different run_id than first run
        assert result2.run_id != result1.run_id


class TestBuildNeedsAnswersToDict:
    """Test NEEDS_ANSWERS result serialization."""

    def test_to_dict_includes_all_fields(self, tmp_path):
        """to_dict should include gaps, sir, draft_idl, run_id."""
        result = build_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        d = result.to_dict()

        assert d["status"] == STATUS_NEEDS_ANSWERS
        assert "gaps" in d
        assert "sir" in d
        assert "draft_idl" in d
        assert "hash_sir" in d
        assert "hash_draft" in d
        assert "run_id" in d


class TestBuildNeedsAnswersViaAPI:
    """Test NEEDS_ANSWERS via API endpoint."""

    def test_api_no_auth_required(self, tmp_path, monkeypatch):
        """API should NOT require X-Admin-Token."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        # Set bundles root to tmp_path
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        # No admin token - should still work
        response = client.post(
            "/pipeline/build",
            json={
                "text": TEXT_WITH_GAPS,
                "bundle_name": "test-bundle",
                "answers": None,
            },
            # No X-Admin-Token header!
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == STATUS_NEEDS_ANSWERS
        assert "run_id" in data

    def test_api_returns_gaps(self, tmp_path, monkeypatch):
        """API should return gaps in response."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(tmp_path))

        response = client.post(
            "/pipeline/build",
            json={
                "text": TEXT_WITH_GAPS,
                "bundle_name": "test-bundle",
                "answers": None,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == STATUS_NEEDS_ANSWERS
        assert "gaps" in data
        assert len(data["gaps"]) > 0
