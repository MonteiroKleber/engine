"""Tests for Pipeline deploy success - verifies release is called."""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from engine.pipeline.orchestrator import run_pipeline, STATUS_DEPLOYED, STATUS_NEEDS_ANSWERS
from engine.ise.release import ReleaseResult
from engine.ise.compiler import CompileResult


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


class TestDeploySuccessCallsRelease:
    """Test that successful pipeline calls compile_release."""

    def test_deploy_calls_compile_release(self, tmp_path, monkeypatch):
        """Pipeline should call compile_release with correct args."""
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

        # First run to get gaps
        result1 = run_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
        )

        # Get answers for all gaps
        answers = get_answers_for_gaps(result1)

        release_called = False
        call_args = {}

        def mock_compile_release(idl, bundle_name, validate_finance_pilot=True, institution_id=None):
            nonlocal release_called, call_args
            release_called = True
            call_args = {
                "idl": idl,
                "bundle_name": bundle_name,
                "validate_finance_pilot": validate_finance_pilot,
            }
            return ReleaseResult(
                status="deployed",
                release_id="20260115-120000",
                bundle_name=bundle_name,
                bundle_hash="abc123",
            )

        with patch("engine.pipeline.orchestrator.compile_bundle", side_effect=mock_compile_bundle_success):
            with patch("engine.pipeline.orchestrator.ise_compile_release", side_effect=mock_compile_release):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )

        assert release_called, "compile_release should have been called"
        assert call_args["bundle_name"] == "test-bundle"
        assert call_args["validate_finance_pilot"] is True
        # IDL should be valid JSON
        idl_data = json.loads(call_args["idl"])
        # Final IDL has structure like approvals, auth, rbac, etc.
        assert "approvals" in idl_data or "rbac" in idl_data or "auth" in idl_data

    def test_deploy_success_returns_deployed(self, tmp_path, monkeypatch):
        """Successful release should return DEPLOYED status."""
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
                status="deployed",
                release_id="20260115-120000",
                bundle_name=bundle_name,
                bundle_hash="abc123def456",
            )

        with patch("engine.pipeline.orchestrator.compile_bundle", side_effect=mock_compile_bundle_success):
            with patch("engine.pipeline.orchestrator.ise_compile_release", side_effect=mock_compile_release):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )

        assert result.status == STATUS_DEPLOYED
        assert result.release_id == "20260115-120000"
        assert result.bundle_hash == "abc123def456"

    def test_deploy_success_includes_all_hashes(self, tmp_path, monkeypatch):
        """DEPLOYED result should include all trace hashes."""
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
                status="deployed",
                release_id="20260115-120000",
                bundle_name=bundle_name,
                bundle_hash="bundlehash123",
            )

        with patch("engine.pipeline.orchestrator.compile_bundle", side_effect=mock_compile_bundle_success):
            with patch("engine.pipeline.orchestrator.ise_compile_release", side_effect=mock_compile_release):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )

        assert result.status == STATUS_DEPLOYED
        assert result.hash_sir is not None
        assert len(result.hash_sir) == 64  # SHA256 hex
        assert result.hash_draft is not None
        assert len(result.hash_draft) == 64
        assert result.hash_idl_final is not None
        assert len(result.hash_idl_final) == 64
        assert result.bundle_hash == "bundlehash123"

    def test_deploy_success_to_dict(self, tmp_path, monkeypatch):
        """DEPLOYED to_dict should have correct structure."""
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
                status="deployed",
                release_id="20260115-120000",
                bundle_name=bundle_name,
                bundle_hash="hash123",
            )

        with patch("engine.pipeline.orchestrator.compile_bundle", side_effect=mock_compile_bundle_success):
            with patch("engine.pipeline.orchestrator.ise_compile_release", side_effect=mock_compile_release):
                result = run_pipeline(
                    text=VALID_TEXT,
                    bundle_name="test-bundle",
                    answers=answers,
                )

        d = result.to_dict()

        assert d["status"] == "DEPLOYED"
        assert d["bundle_name"] == "test-bundle"
        assert d["release_id"] == "20260115-120000"
        assert "hash_sir" in d
        assert "hash_draft" in d
        assert "hash_idl_final" in d
        assert "bundle_hash" in d
        # DEPLOYED should not have error or gaps
        assert "error" not in d
        assert "gaps" not in d
