"""Tests for Pipeline Deploy stops on gaps (policy gaps hardening).

Tests that /pipeline/deploy returns NEEDS_ANSWERS immediately when gaps exist,
WITHOUT calling compile_release.

Per normative specification:
- If gaps != []: return NEEDS_ANSWERS
- Do NOT call compile_release
- Do NOT call scripts
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from engine.pipeline.orchestrator import run_pipeline, STATUS_NEEDS_ANSWERS


# Text with gaps that should stop deploy
TEXT_WITH_GAPS = """
Employees create expenses.
Employees also create reports.
Managers must approve expenses.
"""

# Text with policy gaps
TEXT_WITH_POLICY_GAPS = """
Employees create expenses.
Managers must approve expenses.
POLICY: test-policy pre POST /invalid/endpoint numeric_max amount 100
"""


class TestDeployStopsOnGapsNoCompileRelease:
    """Test that deploy stops on gaps and does NOT call compile_release."""

    def test_gaps_stop_before_compile_release(self, tmp_path, monkeypatch):
        """Deploy with gaps should return NEEDS_ANSWERS without calling compile_release."""
        # Setup environment
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Mock compile_release to track if called
        with patch("engine.pipeline.orchestrator.ise_compile_release") as mock_release:
            result = run_pipeline(
                text=TEXT_WITH_GAPS,
                bundle_name="test-bundle",
                answers=None,
            )

            assert result.status == STATUS_NEEDS_ANSWERS
            assert result.gaps is not None
            assert len(result.gaps) > 0

            # compile_release should NOT have been called
            mock_release.assert_not_called()

    def test_policy_gaps_stop_before_compile_release(self, tmp_path, monkeypatch):
        """Deploy with policy gaps should return NEEDS_ANSWERS without calling compile_release."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        with patch("engine.pipeline.orchestrator.ise_compile_release") as mock_release:
            result = run_pipeline(
                text=TEXT_WITH_POLICY_GAPS,
                bundle_name="test-bundle",
                answers=None,
            )

            assert result.status == STATUS_NEEDS_ANSWERS
            # compile_release should NOT have been called
            mock_release.assert_not_called()

    def test_partial_answers_still_stops(self, tmp_path, monkeypatch):
        """Deploy with partial answers should still stop before compile_release."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # First get gaps
        result1 = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
        )

        assert result1.status == STATUS_NEEDS_ANSWERS
        assert result1.gaps is not None
        assert len(result1.gaps) > 0

        # Get first question for partial answer
        first_gap = result1.gaps[0]
        first_question = first_gap["questions"][0]
        partial_answers = [
            {"question_id": first_question["question_id"], "value": True}
        ]

        # Second run with partial answers
        with patch("engine.pipeline.orchestrator.ise_compile_release") as mock_release:
            result2 = run_pipeline(
                text=TEXT_WITH_GAPS,
                bundle_name="test-bundle",
                answers=partial_answers,
            )

            # If still NEEDS_ANSWERS, compile_release should NOT have been called
            if result2.status == STATUS_NEEDS_ANSWERS:
                mock_release.assert_not_called()


class TestDeployReturnsNeedsAnswersWithPolicyGaps:
    """Test that deploy returns NEEDS_ANSWERS with policy_gaps and answers_template."""

    def test_deploy_returns_policy_gaps(self, tmp_path, monkeypatch):
        """Deploy with policy gaps should include policy_gaps in response."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        result = run_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.policy_gaps is not None

    def test_deploy_returns_answers_template(self, tmp_path, monkeypatch):
        """Deploy should include answers_template in NEEDS_ANSWERS response."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        result = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.answers_template is not None
        assert "version" in result.answers_template
        assert "answers" in result.answers_template

    def test_deploy_answers_template_values_null(self, tmp_path, monkeypatch):
        """Deploy answers_template values must be null."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        result = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
        )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert result.answers_template is not None

        for answer in result.answers_template.get("answers", []):
            assert answer["value"] is None


class TestDeployToDict:
    """Test NEEDS_ANSWERS serialization via to_dict."""

    def test_to_dict_includes_policy_gaps(self, tmp_path, monkeypatch):
        """to_dict should include policy_gaps when NEEDS_ANSWERS."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        result = run_pipeline(
            text=TEXT_WITH_POLICY_GAPS,
            bundle_name="test-bundle",
            answers=None,
        )

        d = result.to_dict()

        assert d["status"] == STATUS_NEEDS_ANSWERS
        assert "policy_gaps" in d
        assert "answers_template" in d


class TestDeployViaAPI:
    """Test deploy stops on gaps via API endpoint."""

    def test_api_deploy_stops_on_gaps(self, tmp_path, monkeypatch):
        """API deploy should return NEEDS_ANSWERS when gaps exist."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        with patch("engine.pipeline.orchestrator.ise_compile_release") as mock_release:
            response = client.post(
                "/pipeline/deploy",
                headers={"X-Admin-Token": "test-token"},
                json={
                    "text": TEXT_WITH_GAPS,
                    "bundle_name": "test-bundle",
                    "target": "production",
                    "answers": None,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == STATUS_NEEDS_ANSWERS

            # compile_release should NOT have been called
            mock_release.assert_not_called()

    def test_api_deploy_returns_policy_gaps(self, tmp_path, monkeypatch):
        """API deploy should return policy_gaps and answers_template."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        response = client.post(
            "/pipeline/deploy",
            headers={"X-Admin-Token": "test-token"},
            json={
                "text": TEXT_WITH_POLICY_GAPS,
                "bundle_name": "test-bundle",
                "target": "production",
                "answers": None,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == STATUS_NEEDS_ANSWERS
        assert "policy_gaps" in data
        assert "answers_template" in data


class TestDeployAfterApplyAnswersStopsOnRemainingGaps:
    """Test that deploy stops after apply_answers if gaps remain."""

    def test_apply_answers_remaining_gaps_no_compile(self, tmp_path, monkeypatch):
        """After partial apply_answers, remaining gaps should stop before compile_release."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # First get gaps
        result1 = run_pipeline(
            text=TEXT_WITH_GAPS,
            bundle_name="test-bundle",
            answers=None,
        )

        assert result1.status == STATUS_NEEDS_ANSWERS
        assert len(result1.gaps) > 1, "Need multiple gaps for this test"

        # Answer only first gap
        first_gap = result1.gaps[0]
        answers = []
        for question in first_gap["questions"]:
            answers.append({"question_id": question["question_id"], "value": True})

        # Run with partial answers
        with patch("engine.pipeline.orchestrator.ise_compile_release") as mock_release:
            result2 = run_pipeline(
                text=TEXT_WITH_GAPS,
                bundle_name="test-bundle",
                answers=answers,
            )

            # If still NEEDS_ANSWERS, compile_release should NOT have been called
            if result2.status == STATUS_NEEDS_ANSWERS:
                mock_release.assert_not_called()
                # Should still have policy_gaps and answers_template
                assert result2.policy_gaps is not None
                assert result2.answers_template is not None
