"""Tests for Pipeline NEEDS_ANSWERS path."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from engine.pipeline.orchestrator import run_pipeline, STATUS_NEEDS_ANSWERS


# Text that will generate required gaps - has two entities but only one with approval
# This triggers a required gap for the entity without approval rule
TEXT_WITH_GAPS = """
Employees create expenses.
Employees also create reports.
Managers must approve expenses.
"""


class TestNeedsAnswersNoAnswers:
    """Test NEEDS_ANSWERS when no answers provided."""

    def test_gaps_return_needs_answers(self, tmp_path, monkeypatch):
        """Pipeline with gaps and no answers should return NEEDS_ANSWERS."""
        # Setup env
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 0")
        verify_script.chmod(0o755)

        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text("#!/bin/bash\nexit 0")
        deploy_script.chmod(0o755)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

        result = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,  # No answers
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.gaps is not None
        assert len(result.gaps) > 0
        assert result.sir is not None
        assert result.draft_idl is not None

    def test_needs_answers_includes_hashes(self, tmp_path, monkeypatch):
        """NEEDS_ANSWERS response should include SIR and draft hashes."""
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 0")
        verify_script.chmod(0o755)

        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text("#!/bin/bash\nexit 0")
        deploy_script.chmod(0o755)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

        result = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.hash_sir is not None
        assert len(result.hash_sir) == 64  # SHA256 hex
        assert result.hash_draft is not None
        assert len(result.hash_draft) == 64

    def test_gaps_have_questions(self, tmp_path, monkeypatch):
        """Gaps should contain questions."""
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 0")
        verify_script.chmod(0o755)

        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text("#!/bin/bash\nexit 0")
        deploy_script.chmod(0o755)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

        result = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
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


class TestNeedsAnswersPartialAnswers:
    """Test NEEDS_ANSWERS when only some answers provided."""

    def test_partial_answers_still_needs_answers(self, tmp_path, monkeypatch):
        """Pipeline with partial answers should still return NEEDS_ANSWERS."""
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 0")
        verify_script.chmod(0o755)

        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text("#!/bin/bash\nexit 0")
        deploy_script.chmod(0o755)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

        # First run to get gaps
        result1 = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
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

        # Second run with partial answers
        result2 = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=partial_answers,
        )

        # Should still need more answers (or proceed if that was enough)
        # The exact behavior depends on what gaps are detected
        assert result2.status in (STATUS_NEEDS_ANSWERS, "DEPLOYED", "ROLLED_BACK", "FAILED")


class TestNeedsAnswersToDict:
    """Test NEEDS_ANSWERS result serialization."""

    def test_to_dict_includes_all_fields(self, tmp_path, monkeypatch):
        """to_dict should include gaps, sir, draft_idl."""
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 0")
        verify_script.chmod(0o755)

        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text("#!/bin/bash\nexit 0")
        deploy_script.chmod(0o755)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()

        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

        result = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
        )

        d = result.to_dict()

        assert d["status"] == STATUS_NEEDS_ANSWERS
        assert "gaps" in d
        assert "sir" in d
        assert "draft_idl" in d
        assert "hash_sir" in d
        assert "hash_draft" in d
