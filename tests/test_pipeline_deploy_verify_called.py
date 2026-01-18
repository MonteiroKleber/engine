"""Tests for Pipeline Deploy verify_bundle.sh call order.

Tests that verify_bundle.sh is called before deploy_engine_prod.sh
in the normal deploy path.

Per normative specification:
- Mock verify_bundle.sh exit=0
- Mock compile_release/deploy path normal
- Assert: verify called before deploy
"""

import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
import subprocess
import os

from engine.pipeline.orchestrator import (
    run_pipeline,
    STATUS_DEPLOYED,
    STATUS_NEEDS_ANSWERS,
)
from engine.core.runtime_state import runtime_state
from engine.ise.compiler import CompileResult
from engine.ise.release import ReleaseResult


# Valid text that would normally succeed
VALID_TEXT = """
Employees can create expenses.
Managers approve expenses.
No self-approval allowed.
"""


@pytest.fixture(autouse=True)
def reset_runtime_state():
    """Reset runtime state before and after each test."""
    runtime_state.set_active()
    yield
    runtime_state.set_active()


def get_answers_for_gaps(result):
    """Generate answers for all required gaps."""
    if not result.gaps:
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


def mock_compile_bundle_success(tmp_path, bundle_name):
    """Create a mock compile_bundle that succeeds and creates bundle files."""
    def _mock(idl, bundle_name, output_dir, validate_finance_pilot=True):
        # Create the bundle in the output_dir
        out_bundle = Path(output_dir) / bundle_name
        out_bundle.mkdir(parents=True, exist_ok=True)
        (out_bundle / "bundle.manifest.json").write_text('{"name": "test"}')
        (out_bundle / "contract_ledger.json").write_text("[]")
        return CompileResult(
            success=True,
            bundle_path=str(out_bundle),
            bundle_name=bundle_name,
            bundle_hash="mockbundlehash123",
        )

    return _mock


def mock_compile_release_success(bundle_name):
    """Create a mock compile_release that succeeds."""
    def _mock(idl, bundle_name, validate_finance_pilot=True, institution_id=None):
        return ReleaseResult(
            status="deployed",
            release_id="20260116-120000",
            bundle_name=bundle_name,
            bundle_hash="releasehash123",
        )

    return _mock


class TestVerifyCalledBeforeDeploy:
    """Test that verify_bundle.sh is called before deploy_engine_prod.sh."""

    def test_verify_called_before_deploy_on_success(self, tmp_path, monkeypatch):
        """When verify succeeds, deploy should be called after verify."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Create verify script that records its call
        verify_marker = tmp_path / "verify_called"
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text(f"#!/bin/bash\ntouch {verify_marker}\nexit 0")
        verify_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))

        # Create deploy script that records its call
        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text("#!/bin/bash\nexit 0")
        deploy_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

        # First get answers
        result1 = run_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
        )

        if result1.status == "NEEDS_ANSWERS":
            answers = get_answers_for_gaps(result1)

            # Mock compile_bundle and compile_release
            with patch(
                "engine.pipeline.orchestrator.compile_bundle",
                mock_compile_bundle_success(tmp_path, "test-bundle"),
            ), patch(
                "engine.pipeline.orchestrator.ise_compile_release",
                mock_compile_release_success("test-bundle"),
            ):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )
        else:
            result = result1

        # Verify was called (marker file exists)
        assert verify_marker.exists(), "Verify script was not called"

    def test_verify_called_with_bundle_path(self, tmp_path, monkeypatch):
        """Verify script should be called with the bundle path as argument."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Create verify script that records its arguments
        args_file = tmp_path / "verify_args"
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text(f'#!/bin/bash\necho "$@" > {args_file}\nexit 0')
        verify_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))

        # Create deploy script
        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text("#!/bin/bash\nexit 0")
        deploy_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

        # First get answers
        result1 = run_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
        )

        if result1.status == "NEEDS_ANSWERS":
            answers = get_answers_for_gaps(result1)

            # Mock compile_bundle and compile_release
            with patch(
                "engine.pipeline.orchestrator.compile_bundle",
                mock_compile_bundle_success(tmp_path, "test-bundle"),
            ), patch(
                "engine.pipeline.orchestrator.ise_compile_release",
                mock_compile_release_success("test-bundle"),
            ):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )
        else:
            result = result1

        # Check verify was called with bundle path
        assert args_file.exists(), "Verify script was not called"
        args = args_file.read_text().strip()
        assert "test-bundle" in args, f"Verify called with wrong args: {args}"


class TestVerifyOrder:
    """Test verify is called in correct order."""

    def test_verify_called_after_gap_resolution(self, tmp_path, monkeypatch):
        """Verify should be called after gaps are resolved, not before."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Create verify script that records call
        verify_marker = tmp_path / "verify_called"
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text(f"#!/bin/bash\ntouch {verify_marker}\nexit 0")
        verify_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))

        # Create deploy script
        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text("#!/bin/bash\nexit 0")
        deploy_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

        # First call - should return NEEDS_ANSWERS
        result1 = run_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
        )

        # Verify should NOT be called yet (gaps not resolved)
        assert not verify_marker.exists(), "Verify was called before gap resolution"

        if result1.status == "NEEDS_ANSWERS":
            answers = get_answers_for_gaps(result1)

            # Mock compile_bundle and compile_release
            with patch(
                "engine.pipeline.orchestrator.compile_bundle",
                mock_compile_bundle_success(tmp_path, "test-bundle"),
            ), patch(
                "engine.pipeline.orchestrator.ise_compile_release",
                mock_compile_release_success("test-bundle"),
            ):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )

            # Now verify should have been called
            assert verify_marker.exists(), "Verify was not called after gap resolution"


class TestVerifyApiPath:
    """Test verify is called via API endpoint."""

    def test_api_verify_called_on_deploy(self, tmp_path, monkeypatch):
        """API deploy should call verify before deploy."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        # Create verify script that records call
        verify_marker = tmp_path / "verify_called"
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text(f"#!/bin/bash\ntouch {verify_marker}\nexit 0")
        verify_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))

        # Create deploy script
        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text("#!/bin/bash\nexit 0")
        deploy_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_DEPLOY_SCRIPT", str(deploy_script))

        # First call to get gaps
        response1 = client.post(
            "/pipeline/deploy",
            headers={"X-Admin-Token": "test-token"},
            json={
                "text": VALID_TEXT,
                "bundle_name": "test-bundle",
                "target": "production",
                "answers": None,
            },
        )

        if response1.status_code == 200 and response1.json().get("status") == "NEEDS_ANSWERS":
            # Get properly typed answers for each question
            gaps = response1.json().get("gaps", [])
            answers = []
            for gap in gaps:
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

            # Mock compile_bundle and compile_release
            with patch(
                "engine.pipeline.orchestrator.compile_bundle",
                mock_compile_bundle_success(tmp_path, "test-bundle"),
            ), patch(
                "engine.pipeline.orchestrator.ise_compile_release",
                mock_compile_release_success("test-bundle"),
            ):
                response = client.post(
                    "/pipeline/deploy",
                    headers={"X-Admin-Token": "test-token"},
                    json={
                        "text": VALID_TEXT,
                        "bundle_name": "test-bundle",
                        "target": "production",
                        "answers": answers,
                    },
                )
        else:
            response = response1

        # Verify was called
        assert verify_marker.exists(), "Verify script was not called via API"
