"""Tests for Pipeline Deploy verify_bundle.sh failure handling.

Tests that when verify_bundle.sh returns exit != 0, the pipeline returns
409 PIPELINE_VERIFY_FAILED and deploy_engine_prod.sh is NOT called.

Per normative specification:
- Mock verify_bundle.sh returning exit=1
- Expect 409 PIPELINE_VERIFY_FAILED
- Assert: deploy script NOT called
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import subprocess
import os

from engine.pipeline.orchestrator import (
    run_pipeline,
    STATUS_FAILED,
    PIPELINE_VERIFY_FAILED,
)
from engine.core.runtime_state import runtime_state
from engine.ise.compiler import CompileResult


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


class TestDeployVerifyFailed:
    """Test that deploy fails with 409 when verify_bundle.sh fails."""

    def test_verify_failed_returns_409_error_code(self, tmp_path, monkeypatch):
        """When verify_bundle.sh fails, should return PIPELINE_VERIFY_FAILED."""
        # Setup environment
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Create a fake verify script that returns exit 1
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 1")
        verify_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))

        # Create a fake deploy script (should not be called)
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

            # Mock compile_bundle to succeed (IDL insufficient for finance-pilot)
            with patch(
                "engine.pipeline.orchestrator.compile_bundle",
                mock_compile_bundle_success(tmp_path, "test-bundle"),
            ):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )
        else:
            result = result1

        assert result.status == STATUS_FAILED
        assert result.error_code == PIPELINE_VERIFY_FAILED
        assert result.exit_code == 1

    def test_verify_failed_does_not_call_deploy_script(self, tmp_path, monkeypatch):
        """When verify fails, deploy_engine_prod.sh should NOT be called."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Create a failing verify script
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 1")
        verify_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))

        # Create a deploy script that writes a marker file
        deploy_marker = tmp_path / "deploy_called"
        deploy_script = tmp_path / "deploy_engine_prod.sh"
        deploy_script.write_text(f"#!/bin/bash\ntouch {deploy_marker}\nexit 0")
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

            # Mock compile_bundle to succeed
            with patch(
                "engine.pipeline.orchestrator.compile_bundle",
                mock_compile_bundle_success(tmp_path, "test-bundle"),
            ):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )
        else:
            result = result1

        assert result.status == STATUS_FAILED
        assert result.error_code == PIPELINE_VERIFY_FAILED
        # Deploy script should NOT have been called (marker file should not exist)
        assert not deploy_marker.exists(), "Deploy script was called but should not have been"


class TestDeployApiVerifyFailed:
    """Test that deploy API returns 409 when verification fails."""

    def test_api_returns_409_on_verify_failure(self, tmp_path, monkeypatch):
        """API should return 409 PIPELINE_VERIFY_FAILED."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        # Create a failing verify script
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 1")
        verify_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))

        # Create a deploy script
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

            # Mock compile_bundle to succeed
            with patch(
                "engine.pipeline.orchestrator.compile_bundle",
                mock_compile_bundle_success(tmp_path, "test-bundle"),
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

        assert response.status_code == 409
        data = response.json()
        assert data["code"] == PIPELINE_VERIFY_FAILED

    def test_api_409_includes_exit_code(self, tmp_path, monkeypatch):
        """API 409 response should include the exit code."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        # Create a failing verify script with exit code 42
        verify_script = tmp_path / "verify_bundle.sh"
        verify_script.write_text("#!/bin/bash\nexit 42")
        verify_script.chmod(0o755)
        monkeypatch.setenv("ENGINE_VERIFY_SCRIPT", str(verify_script))

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

            # Mock compile_bundle to succeed
            with patch(
                "engine.pipeline.orchestrator.compile_bundle",
                mock_compile_bundle_success(tmp_path, "test-bundle"),
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

        assert response.status_code == 409
        data = response.json()
        assert data["exit_code"] == 42
