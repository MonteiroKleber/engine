"""Tests for Pipeline Deploy blocked in SAFE_MODE.

Tests that /pipeline/deploy returns 503 PIPELINE_ENGINE_SAFE_MODE when
the engine runtime is in SAFE_MODE, and compile_release is NOT called.

Per normative specification:
- If engine is in SAFE_MODE: block deploy with 503
- Do NOT call compile_release
- Do NOT call scripts
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from engine.pipeline.orchestrator import (
    run_pipeline,
    STATUS_FAILED,
    PIPELINE_ENGINE_SAFE_MODE,
)
from engine.core.runtime_state import runtime_state, RuntimeMode


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


class TestDeployBlockedInSafeMode:
    """Test that deploy is blocked when engine is in SAFE_MODE."""

    def test_safe_mode_returns_failed_with_error_code(self, tmp_path, monkeypatch):
        """Deploy in SAFE_MODE should return FAILED with PIPELINE_ENGINE_SAFE_MODE."""
        # Setup environment
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Set engine to SAFE_MODE
        runtime_state.set_safe_mode("TEST_SAFE_MODE", ["Test reason"])

        # Attempt deploy
        result = run_pipeline(
            text=VALID_TEXT,
            bundle_name="test-bundle",
            answers=None,
        )

        assert result.status == STATUS_FAILED
        assert result.error_code == PIPELINE_ENGINE_SAFE_MODE
        assert "SAFE_MODE" in result.error_message
        assert "TEST_SAFE_MODE" in result.error_message

    def test_safe_mode_does_not_call_compile_release(self, tmp_path, monkeypatch):
        """In SAFE_MODE, compile_release should NOT be called."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Set engine to SAFE_MODE
        runtime_state.set_safe_mode("TEST_SAFE_MODE")

        with patch("engine.pipeline.orchestrator.ise_compile_release") as mock_release:
            result = run_pipeline(
                text=VALID_TEXT,
                bundle_name="test-bundle",
                answers=None,
            )

            assert result.status == STATUS_FAILED
            assert result.error_code == PIPELINE_ENGINE_SAFE_MODE
            # compile_release should NOT have been called
            mock_release.assert_not_called()

    def test_safe_mode_does_not_extract_sir(self, tmp_path, monkeypatch):
        """In SAFE_MODE, even SIR extraction should not happen."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Set engine to SAFE_MODE
        runtime_state.set_safe_mode("BUNDLE_CONTRACT_HASH_MISMATCH")

        with patch("engine.pipeline.orchestrator.get_extractor") as mock_extractor:
            result = run_pipeline(
                text=VALID_TEXT,
                bundle_name="test-bundle",
                answers=None,
            )

            assert result.status == STATUS_FAILED
            assert result.error_code == PIPELINE_ENGINE_SAFE_MODE
            # Extractor should NOT have been called (blocked before Step 1)
            mock_extractor.assert_not_called()


class TestDeployApiBlockedInSafeMode:
    """Test that deploy API returns 503 when engine is in SAFE_MODE."""

    def test_api_returns_503_in_safe_mode(self, tmp_path, monkeypatch):
        """API should return 503 PIPELINE_ENGINE_SAFE_MODE."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        # Set engine to SAFE_MODE
        runtime_state.set_safe_mode("TEST_SAFE_MODE")

        response = client.post(
            "/pipeline/deploy",
            headers={"X-Admin-Token": "test-token"},
            json={
                "text": VALID_TEXT,
                "bundle_name": "test-bundle",
                "target": "production",
                "answers": None,
            },
        )

        assert response.status_code == 503
        data = response.json()
        assert data["code"] == PIPELINE_ENGINE_SAFE_MODE
        assert "SAFE_MODE" in data["message"]

    def test_api_returns_503_with_reason_code(self, tmp_path, monkeypatch):
        """API 503 response should include the SAFE_MODE reason code."""
        from fastapi.testclient import TestClient
        from engine.api.server import app

        client = TestClient(app, raise_server_exceptions=False)

        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-token")

        # Set engine to SAFE_MODE with specific reason
        runtime_state.set_safe_mode("BUNDLE_CONTRACT_HASH_MISMATCH", ["contract.json"])

        response = client.post(
            "/pipeline/deploy",
            headers={"X-Admin-Token": "test-token"},
            json={
                "text": VALID_TEXT,
                "bundle_name": "test-bundle",
                "target": "production",
            },
        )

        assert response.status_code == 503
        data = response.json()
        assert "BUNDLE_CONTRACT_HASH_MISMATCH" in data["message"]


class TestDeployWorksWhenActive:
    """Test that deploy works normally when engine is ACTIVE."""

    def test_active_mode_proceeds_normally(self, tmp_path, monkeypatch):
        """In ACTIVE mode, deploy should proceed (may fail for other reasons)."""
        bundles_root = tmp_path / "bundles"
        bundles_root.mkdir()
        monkeypatch.setenv("ENGINE_PROD_BUNDLES_ROOT", str(bundles_root))

        # Ensure engine is ACTIVE
        runtime_state.set_active()

        # Mock compile_release since we just want to verify SAFE_MODE doesn't block
        with patch("engine.pipeline.orchestrator.ise_compile_release") as mock_release:
            mock_release.return_value = MagicMock(
                status="failed",
                release_id="test-release",
                bundle_hash="abc123",
                error_code="SOME_ERROR",
                error_message="Test error",
            )

            # This may return NEEDS_ANSWERS or continue to compile - either way
            # it should NOT be blocked by SAFE_MODE check
            result = run_pipeline(
                text=VALID_TEXT,
                bundle_name="test-bundle",
                answers=None,
            )

            # Result should NOT have PIPELINE_ENGINE_SAFE_MODE error
            assert result.error_code != PIPELINE_ENGINE_SAFE_MODE
