"""Tests for Loader + Safe Mode (Etapa 3.1)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.errors import (
    BUNDLE_MANIFEST_MISSING,
    BUNDLE_MANIFEST_INVALID_JSON,
    BUNDLE_CONTRACT_MISSING,
    BUNDLE_CONTRACT_HASH_MISMATCH,
    BUNDLE_CONTRACT_INVALID_JSON,
)
from engine.loader.load_bundle import load_bundle
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


@pytest.fixture(autouse=True)
def reset_runtime_state():
    """Reset runtime state before each test."""
    runtime_state.set_active()
    yield
    runtime_state.set_active()


def create_manifest(bundle_path: Path, contracts: list) -> None:
    """Create a bundle manifest with given contracts."""
    manifest = {
        "name": "test-bundle",
        "version": "1.0.0",
        "contracts": contracts
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


def create_contract(bundle_path: Path, filename: str, content: dict) -> str:
    """Create a contract file and return its SHA-256 hash."""
    contract_path = bundle_path / filename
    with open(contract_path, "w", encoding="utf-8") as f:
        json.dump(content, f)
    return compute_sha256(contract_path)


class TestActiveWhenBundleIntact:
    """Test that runtime is ACTIVE when bundle is intact."""

    def test_active_when_bundle_intact(self, tmp_path: Path):
        """Bundle with valid manifest and matching hashes should result in ACTIVE mode."""
        # Create valid contract
        contract_content = {"version": "1.0.0", "data": "test"}
        contract_hash = create_contract(tmp_path, "test_contract.json", contract_content)

        # Create manifest with correct hash
        create_manifest(tmp_path, [
            {
                "file": "test_contract.json",
                "sha256": f"SHA256:{contract_hash}",
                "required": True
            }
        ])

        # Load bundle
        result = load_bundle(tmp_path)

        # Verify ACTIVE mode
        assert result is not None
        assert runtime_state.is_active()
        assert runtime_state.reason_code is None

        # Test /health endpoint
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["mode"] == "ACTIVE"


class TestSafeModeOnHashMismatch:
    """Test SAFE_MODE on hash mismatch."""

    def test_safe_mode_on_hash_mismatch(self, tmp_path: Path):
        """Mismatched hash should trigger SAFE_MODE with BUNDLE_CONTRACT_HASH_MISMATCH."""
        # Create contract
        contract_content = {"version": "1.0.0", "data": "test"}
        create_contract(tmp_path, "test_contract.json", contract_content)

        # Create manifest with WRONG hash
        wrong_hash = "0" * 64
        create_manifest(tmp_path, [
            {
                "file": "test_contract.json",
                "sha256": f"SHA256:{wrong_hash}",
                "required": True
            }
        ])

        # Load bundle
        result = load_bundle(tmp_path)

        # Verify SAFE_MODE
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_CONTRACT_HASH_MISMATCH

        # Test /health endpoint
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["mode"] == "SAFE_MODE"
        assert data["reason_code"] == BUNDLE_CONTRACT_HASH_MISMATCH


class TestSafeModeOnMissingContract:
    """Test SAFE_MODE on missing contract."""

    def test_safe_mode_on_missing_contract(self, tmp_path: Path):
        """Missing required contract should trigger SAFE_MODE with BUNDLE_CONTRACT_MISSING."""
        # Create manifest referencing non-existent file
        create_manifest(tmp_path, [
            {
                "file": "missing_contract.json",
                "sha256": "SHA256:" + "a" * 64,
                "required": True
            }
        ])

        # Load bundle
        result = load_bundle(tmp_path)

        # Verify SAFE_MODE
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_CONTRACT_MISSING

        # Test /health endpoint
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["mode"] == "SAFE_MODE"
        assert data["reason_code"] == BUNDLE_CONTRACT_MISSING


class TestSafeModeOnInvalidContractJson:
    """Test SAFE_MODE on invalid contract JSON."""

    def test_safe_mode_on_invalid_contract_json(self, tmp_path: Path):
        """Invalid JSON in contract should trigger SAFE_MODE with BUNDLE_CONTRACT_INVALID_JSON."""
        # Create invalid JSON file
        invalid_json_path = tmp_path / "invalid.json"
        with open(invalid_json_path, "w", encoding="utf-8") as f:
            f.write("{invalid json content")

        # Calculate hash of the invalid content
        invalid_hash = compute_sha256(invalid_json_path)

        # Create manifest with correct hash but invalid JSON content
        create_manifest(tmp_path, [
            {
                "file": "invalid.json",
                "sha256": f"SHA256:{invalid_hash}",
                "required": True
            }
        ])

        # Load bundle
        result = load_bundle(tmp_path)

        # Verify SAFE_MODE
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_CONTRACT_INVALID_JSON

        # Test /health endpoint
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["mode"] == "SAFE_MODE"
        assert data["reason_code"] == BUNDLE_CONTRACT_INVALID_JSON


class TestSafeModeOnInvalidManifestJson:
    """Test SAFE_MODE on invalid manifest JSON."""

    def test_safe_mode_on_invalid_manifest_json(self, tmp_path: Path):
        """Invalid JSON in manifest should trigger SAFE_MODE with BUNDLE_MANIFEST_INVALID_JSON."""
        # Create invalid manifest
        manifest_path = tmp_path / "bundle.manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write("{invalid manifest json")

        # Load bundle
        result = load_bundle(tmp_path)

        # Verify SAFE_MODE
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_MANIFEST_INVALID_JSON

        # Test /health endpoint
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["mode"] == "SAFE_MODE"
        assert data["reason_code"] == BUNDLE_MANIFEST_INVALID_JSON


class TestSafeModeOnMissingManifest:
    """Test SAFE_MODE on missing manifest."""

    def test_safe_mode_on_missing_manifest(self, tmp_path: Path):
        """Missing manifest should trigger SAFE_MODE with BUNDLE_MANIFEST_MISSING."""
        # Load bundle without creating manifest
        result = load_bundle(tmp_path)

        # Verify SAFE_MODE
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_MANIFEST_MISSING

        # Test /health endpoint
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["mode"] == "SAFE_MODE"
        assert data["reason_code"] == BUNDLE_MANIFEST_MISSING


class TestHashFormats:
    """Test different hash format acceptance."""

    def test_hash_without_prefix(self, tmp_path: Path):
        """Hash without SHA256: prefix should be accepted."""
        contract_content = {"version": "1.0.0"}
        contract_hash = create_contract(tmp_path, "contract.json", contract_content)

        # Create manifest with hash WITHOUT prefix
        create_manifest(tmp_path, [
            {
                "file": "contract.json",
                "sha256": contract_hash,  # No prefix
                "required": True
            }
        ])

        result = load_bundle(tmp_path)
        assert result is not None
        assert runtime_state.is_active()

    def test_hash_with_prefix(self, tmp_path: Path):
        """Hash with SHA256: prefix should be accepted."""
        contract_content = {"version": "1.0.0"}
        contract_hash = create_contract(tmp_path, "contract.json", contract_content)

        # Create manifest with hash WITH prefix
        create_manifest(tmp_path, [
            {
                "file": "contract.json",
                "sha256": f"SHA256:{contract_hash}",  # With prefix
                "required": True
            }
        ])

        result = load_bundle(tmp_path)
        assert result is not None
        assert runtime_state.is_active()


class TestOptionalContracts:
    """Test handling of optional contracts."""

    def test_missing_optional_contract_stays_active(self, tmp_path: Path):
        """Missing optional contract should NOT trigger SAFE_MODE."""
        # Create manifest with missing optional contract
        create_manifest(tmp_path, [
            {
                "file": "optional.json",
                "sha256": "SHA256:" + "b" * 64,
                "required": False  # Optional
            }
        ])

        result = load_bundle(tmp_path)
        assert result is not None
        assert runtime_state.is_active()
