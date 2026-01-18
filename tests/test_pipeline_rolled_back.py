"""Tests for Pipeline ROLLED_BACK path."""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from engine.pipeline.orchestrator import run_pipeline, STATUS_ROLLED_BACK, STATUS_NEEDS_ANSWERS
from engine.ise.release import ReleaseResult
from engine.ise.compiler import CompileResult
from engine.ise import errors as ise_errors


def mock_compile_bundle_success(idl, bundle_name, output_dir, validate_finance_pilot=True):
    """Mock compile_bundle that succeeds and creates bundle files."""
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


class TestRolledBackOnDeployFailure:
    """Test ROLLED_BACK when deploy script fails."""

    def test_deploy_failure_returns_rolled_back(self, tmp_path, monkeypatch):
        """Deploy failure should return ROLLED_BACK status."""
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
        result1 = run_pipeline(text=VALID_TEXT, bundle_name="test-bundle", answers=None)
        answers = get_answers_for_gaps(result1)

        def mock_compile_release(idl, bundle_name, validate_finance_pilot=True, institution_id=None):
            return ReleaseResult(
                status="rolled_back",
                release_id="20260115-120000",
                bundle_name=bundle_name,
                bundle_hash="abc123",
                error_code=ise_errors.ISE_DEPLOY_FAILED,
                error_message="Deploy failed, rolled back",
                exit_code=1,
            )

        with patch("engine.pipeline.orchestrator.compile_bundle", side_effect=mock_compile_bundle_success):
            with patch("engine.pipeline.orchestrator.ise_compile_release", side_effect=mock_compile_release):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )

        assert result.status == STATUS_ROLLED_BACK
        assert result.error_code == ise_errors.ISE_DEPLOY_FAILED
        assert result.exit_code == 1

    def test_rolled_back_includes_hashes(self, tmp_path, monkeypatch):
        """ROLLED_BACK should still include trace hashes."""
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
        result1 = run_pipeline(text=VALID_TEXT, bundle_name="test-bundle", answers=None)
        answers = get_answers_for_gaps(result1)

        def mock_compile_release(idl, bundle_name, validate_finance_pilot=True, institution_id=None):
            return ReleaseResult(
                status="rolled_back",
                release_id="20260115-120000",
                bundle_name=bundle_name,
                bundle_hash="abc123",
                error_code=ise_errors.ISE_DEPLOY_FAILED,
                error_message="Deploy failed",
                exit_code=1,
            )

        with patch("engine.pipeline.orchestrator.compile_bundle", side_effect=mock_compile_bundle_success):
            with patch("engine.pipeline.orchestrator.ise_compile_release", side_effect=mock_compile_release):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )

        assert result.status == STATUS_ROLLED_BACK
        assert result.hash_sir is not None
        assert len(result.hash_sir) == 64
        assert result.hash_draft is not None
        assert len(result.hash_draft) == 64
        assert result.hash_idl_final is not None
        assert len(result.hash_idl_final) == 64

    def test_rolled_back_to_dict_includes_error(self, tmp_path, monkeypatch):
        """ROLLED_BACK to_dict should include error details."""
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
        result1 = run_pipeline(text=VALID_TEXT, bundle_name="test-bundle", answers=None)
        answers = get_answers_for_gaps(result1)

        def mock_compile_release(idl, bundle_name, validate_finance_pilot=True, institution_id=None):
            return ReleaseResult(
                status="rolled_back",
                release_id="20260115-120000",
                bundle_name=bundle_name,
                bundle_hash="abc123",
                error_code=ise_errors.ISE_DEPLOY_FAILED,
                error_message="Deploy script exited with code 1",
                exit_code=1,
            )

        with patch("engine.pipeline.orchestrator.compile_bundle", side_effect=mock_compile_bundle_success):
            with patch("engine.pipeline.orchestrator.ise_compile_release", side_effect=mock_compile_release):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )

        d = result.to_dict()

        assert d["status"] == "ROLLED_BACK"
        assert "error" in d
        assert d["error"]["code"] == ise_errors.ISE_DEPLOY_FAILED
        assert d["error"]["exit_code"] == 1
        assert "message" in d["error"]

    def test_rolled_back_preserves_release_id(self, tmp_path, monkeypatch):
        """ROLLED_BACK should preserve release_id and bundle_hash."""
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
        result1 = run_pipeline(text=VALID_TEXT, bundle_name="test-bundle", answers=None)
        answers = get_answers_for_gaps(result1)

        def mock_compile_release(idl, bundle_name, validate_finance_pilot=True, institution_id=None):
            return ReleaseResult(
                status="rolled_back",
                release_id="20260115-143021",
                bundle_name=bundle_name,
                bundle_hash="specifichash999",
                error_code=ise_errors.ISE_DEPLOY_FAILED,
                error_message="Deploy failed",
                exit_code=42,
            )

        with patch("engine.pipeline.orchestrator.compile_bundle", side_effect=mock_compile_bundle_success):
            with patch("engine.pipeline.orchestrator.ise_compile_release", side_effect=mock_compile_release):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )

        assert result.status == STATUS_ROLLED_BACK
        assert result.release_id == "20260115-143021"
        assert result.bundle_hash == "specifichash999"
        assert result.exit_code == 42


class TestRolledBackViaAPI:
    """Test ROLLED_BACK response via API endpoint."""

    def test_api_returns_rolled_back(self, tmp_path, monkeypatch):
        """API should return ROLLED_BACK with proper structure."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "secret")

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

        # First call to get gaps
        response1 = client.post(
            "/pipeline/deploy",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle", "answers": None},
            headers={"X-Admin-Token": "secret"},
        )

        data1 = response1.json()
        answers = []
        if data1.get("status") == "NEEDS_ANSWERS" and data1.get("gaps"):
            for gap in data1["gaps"]:
                for question in gap.get("questions", []):
                    q_id = question["question_id"]
                    default = question.get("default_value", True)
                    answers.append({"question_id": q_id, "value": default})

        def mock_compile_release(idl, bundle_name, validate_finance_pilot=True, institution_id=None):
            return ReleaseResult(
                status="rolled_back",
                release_id="20260115-120000",
                bundle_name=bundle_name,
                bundle_hash="abc123",
                error_code=ise_errors.ISE_DEPLOY_FAILED,
                error_message="Deploy failed",
                exit_code=1,
            )

        with patch("engine.pipeline.orchestrator.compile_bundle", side_effect=mock_compile_bundle_success):
            with patch("engine.pipeline.orchestrator.ise_compile_release", side_effect=mock_compile_release):
                response = client.post(
                    "/pipeline/deploy",
                    json={
                        "text": VALID_TEXT,
                        "bundle_name": "test-bundle",
                        "answers": answers,
                    },
                    headers={"X-Admin-Token": "secret"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ROLLED_BACK"
        assert "error" in data
        assert data["error"]["code"] == ise_errors.ISE_DEPLOY_FAILED
