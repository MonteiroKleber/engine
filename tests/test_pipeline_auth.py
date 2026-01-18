"""Tests for Pipeline API authentication."""

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.ise import errors


client = TestClient(app, raise_server_exceptions=False)

VALID_TEXT = """
Employees can create expenses.
Managers approve expenses.
No self-approval allowed.
"""


class TestPipelineNoToken:
    """Test pipeline deploy without admin token configured."""

    def test_no_env_token_returns_401(self, monkeypatch):
        """Missing ENGINE_ISE_ADMIN_TOKEN env should return 401."""
        monkeypatch.delenv("ENGINE_ISE_ADMIN_TOKEN", raising=False)

        response = client.post(
            "/pipeline/deploy",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle"},
        )

        assert response.status_code == 401
        assert errors.ISE_ADMIN_UNAUTHORIZED in str(response.json())


class TestPipelineWrongToken:
    """Test pipeline deploy with wrong admin token."""

    def test_wrong_token_returns_401(self, monkeypatch):
        """Wrong X-Admin-Token should return 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-secret")

        response = client.post(
            "/pipeline/deploy",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle"},
            headers={"X-Admin-Token": "wrong-token"},
        )

        assert response.status_code == 401
        assert errors.ISE_ADMIN_UNAUTHORIZED in str(response.json())

    def test_empty_token_returns_401(self, monkeypatch):
        """Empty X-Admin-Token should return 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-secret")

        response = client.post(
            "/pipeline/deploy",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle"},
            headers={"X-Admin-Token": ""},
        )

        assert response.status_code == 401
        assert errors.ISE_ADMIN_UNAUTHORIZED in str(response.json())


class TestPipelineMissingHeader:
    """Test pipeline deploy with missing X-Admin-Token header."""

    def test_missing_header_returns_401(self, monkeypatch):
        """Missing X-Admin-Token header should return 401."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-secret")

        response = client.post(
            "/pipeline/deploy",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle"},
        )

        assert response.status_code == 401
        assert errors.ISE_ADMIN_UNAUTHORIZED in str(response.json())


class TestPipelineCorrectToken:
    """Test pipeline deploy with correct admin token."""

    def test_correct_token_passes_auth(self, monkeypatch, tmp_path):
        """Correct token should pass auth (may fail later in pipeline)."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "correct-secret")

        # Setup mock scripts and bundles for pipeline
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

        response = client.post(
            "/pipeline/deploy",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle"},
            headers={"X-Admin-Token": "correct-secret"},
        )

        # Should not be 401 - auth passed
        assert response.status_code != 401
        # May be 200 or other status depending on pipeline result
        data = response.json()
        # Should have a status field from pipeline
        assert "status" in data

    def test_token_case_sensitive(self, monkeypatch):
        """Token comparison should be case sensitive."""
        monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "Secret123")

        response = client.post(
            "/pipeline/deploy",
            json={"text": VALID_TEXT, "bundle_name": "test-bundle"},
            headers={"X-Admin-Token": "secret123"},  # lowercase
        )

        assert response.status_code == 401
        assert errors.ISE_ADMIN_UNAUTHORIZED in str(response.json())
