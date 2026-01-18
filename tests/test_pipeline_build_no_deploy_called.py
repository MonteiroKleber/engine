"""Tests verifying Pipeline Build does NOT call deploy functions."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from engine.pipeline.orchestrator import (
    build_pipeline,
    STATUS_BUILT,
    STATUS_NEEDS_ANSWERS,
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


class TestBuildNeverCallsCompileRelease:
    """Test that build_pipeline never calls compile_release."""

    def test_build_does_not_call_compile_release(self, tmp_path):
        """build_pipeline should NOT call ise_compile_release."""
        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        compile_release_called = False

        def mock_compile_release(*args, **kwargs):
            nonlocal compile_release_called
            compile_release_called = True
            raise AssertionError("compile_release should NOT be called!")

        with patch(
            "engine.pipeline.orchestrator.ise_compile_release",
            side_effect=mock_compile_release,
        ):
            # Second run with answers
            result = build_pipeline(
                text=VALID_TEXT,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )

        assert result.status == STATUS_BUILT
        assert not compile_release_called, "compile_release should NOT have been called"

    def test_build_needs_answers_does_not_call_compile_release(self, tmp_path):
        """NEEDS_ANSWERS path should also not call compile_release."""
        compile_release_called = False

        def mock_compile_release(*args, **kwargs):
            nonlocal compile_release_called
            compile_release_called = True
            raise AssertionError("compile_release should NOT be called!")

        with patch(
            "engine.pipeline.orchestrator.ise_compile_release",
            side_effect=mock_compile_release,
        ):
            result = build_pipeline(
                text=VALID_TEXT,
                bundle_name="test-bundle",
                answers=None,
                bundles_root=str(tmp_path),
            )

        assert result.status == STATUS_NEEDS_ANSWERS
        assert not compile_release_called


class TestBuildNeverCallsSubprocess:
    """Test that build_pipeline never calls subprocess."""

    def test_build_does_not_call_subprocess_run(self, tmp_path):
        """build_pipeline should NOT call subprocess.run."""
        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        subprocess_called = False

        def mock_subprocess_run(*args, **kwargs):
            nonlocal subprocess_called
            subprocess_called = True
            raise AssertionError("subprocess.run should NOT be called!")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Second run with answers
            result = build_pipeline(
                text=VALID_TEXT,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )

        assert result.status == STATUS_BUILT
        assert not subprocess_called, "subprocess.run should NOT have been called"

    def test_build_does_not_call_subprocess_popen(self, tmp_path):
        """build_pipeline should NOT call subprocess.Popen."""
        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        popen_called = False

        def mock_popen(*args, **kwargs):
            nonlocal popen_called
            popen_called = True
            raise AssertionError("subprocess.Popen should NOT be called!")

        with patch("subprocess.Popen", side_effect=mock_popen):
            # Second run with answers
            result = build_pipeline(
                text=VALID_TEXT,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )

        assert result.status == STATUS_BUILT
        assert not popen_called, "subprocess.Popen should NOT have been called"


class TestBuildNeverCallsScripts:
    """Test that build_pipeline never calls verify/deploy scripts."""

    def test_build_ignores_script_env_vars(self, tmp_path, monkeypatch):
        """build_pipeline should NOT read ENGINE_VERIFY_SCRIPT or ENGINE_DEPLOY_SCRIPT."""
        # Set script env vars that would fail if used
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", "/nonexistent/verify.sh")
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", "/nonexistent/deploy.sh")

        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        # Second run with answers - should succeed because scripts are NOT called
        result = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),
        )

        assert result.status == STATUS_BUILT

    def test_build_does_not_require_bundles_root_env(self, tmp_path):
        """build_pipeline should work with explicit bundles_root, ignoring env."""
        # Don't set ENGINE_PROD_BUNDLES_ROOT - should still work with explicit param

        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),  # Explicit param
        )

        answers = get_answers_for_gaps(result1)

        # Second run with answers
        result = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=answers,
            bundles_root=str(tmp_path),  # Explicit param
        )

        assert result.status == STATUS_BUILT


class TestBuildUsesCompileBundle:
    """Test that build_pipeline uses compile_bundle (not compile_release)."""

    def test_build_calls_compile_bundle(self, tmp_path):
        """build_pipeline should call compile_bundle."""
        # First run to get gaps
        result1 = build_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
            bundles_root=str(tmp_path),
        )

        answers = get_answers_for_gaps(result1)

        compile_bundle_called = False
        call_args = {}

        original_compile_bundle = None

        def mock_compile_bundle(idl, bundle_name, output_dir, validate_finance_pilot):
            nonlocal compile_bundle_called, call_args
            compile_bundle_called = True
            call_args = {
                "idl": idl,
                "bundle_name": bundle_name,
                "output_dir": output_dir,
                "validate_finance_pilot": validate_finance_pilot,
            }
            # Call the original function
            from engine.ise.compiler import compile_bundle as real_compile_bundle
            return real_compile_bundle(idl, bundle_name, output_dir, validate_finance_pilot)

        with patch(
            "engine.pipeline.orchestrator.compile_bundle",
            side_effect=mock_compile_bundle,
        ):
            # Second run with answers
            result = build_pipeline(
                text=VALID_TEXT,
                bundle_name="test-bundle",
                answers=answers,
                bundles_root=str(tmp_path),
            )

        assert result.status == STATUS_BUILT
        assert compile_bundle_called, "compile_bundle should have been called"
        assert call_args["bundle_name"] == "test-bundle"
        assert "dev-runs" in call_args["output_dir"]
        # Sandbox builds skip finance-pilot validation
        assert call_args["validate_finance_pilot"] is False
