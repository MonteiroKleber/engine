"""Tests for ISE manifest and SHA256 hashes.

Updated for loader-compatible manifest format (2026-01-18).
"""

import json
import hashlib
import pytest

from engine.ise.manifest import (
    sha256_bytes,
    sha256_str,
    generate_manifest,
    generate_manifest_json,
    get_bundle_hash,
    REQUIRED_CONTRACTS,
)


class TestSHA256Functions:
    """Test SHA256 hash functions."""

    def test_sha256_bytes_empty(self):
        """Test SHA256 of empty bytes."""
        result = sha256_bytes(b"")
        # Known SHA256 of empty string
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert result == expected

    def test_sha256_bytes_known_value(self):
        """Test SHA256 of known value."""
        result = sha256_bytes(b"hello")
        # Known SHA256 of "hello"
        expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        assert result == expected

    def test_sha256_str_utf8(self):
        """Test SHA256 of string with UTF-8 encoding."""
        result = sha256_str("hello")
        # Should match bytes version
        expected = sha256_bytes(b"hello")
        assert result == expected

    def test_sha256_str_unicode(self):
        """Test SHA256 of string with unicode characters."""
        result = sha256_str("héllo wörld")
        # Verify it's a valid 64-char hex string
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_sha256_deterministic(self):
        """Test SHA256 is deterministic."""
        content = "test content"
        result1 = sha256_str(content)
        result2 = sha256_str(content)
        assert result1 == result2


class TestGenerateManifest:
    """Test manifest generation in loader-compatible format."""

    def test_manifest_structure(self):
        """Test manifest has required fields in loader format."""
        contracts = {
            "rbac.json": '{"version": "1.0"}',
            "workflows.json": '{"version": "1.0"}',
        }

        manifest = generate_manifest(
            bundle_name="test-bundle",
            version="1.0.0",
            contracts=contracts,
            system_name="Test System",
        )

        # Loader-compatible format
        assert manifest["name"] == "test-bundle"
        assert manifest["version"] == "1.0.0"
        assert manifest["description"] == "Test System bundle"
        assert "contracts" in manifest
        assert isinstance(manifest["contracts"], list)

        # Metadata in _metadata
        assert "_metadata" in manifest
        assert manifest["_metadata"]["manifest_version"] == "1.0"
        assert manifest["_metadata"]["system_name"] == "Test System"
        assert "created_at" in manifest["_metadata"]
        assert "bundle_hash" in manifest["_metadata"]

    def test_manifest_contract_hashes(self):
        """Test manifest contains correct contract hashes with SHA256: prefix."""
        contracts = {
            "rbac.json": '{"version": "1.0"}',
        }

        manifest = generate_manifest(
            bundle_name="test-bundle",
            version="1.0.0",
            contracts=contracts,
        )

        # Verify hash matches actual content with SHA256: prefix
        expected_hash = sha256_str('{"version": "1.0"}')

        # contracts is now an array
        rbac_contract = next(c for c in manifest["contracts"] if c["file"] == "rbac.json")
        assert rbac_contract["sha256"] == f"SHA256:{expected_hash}"
        assert rbac_contract["required"] is True  # rbac.json is required

    def test_manifest_bundle_hash_deterministic(self):
        """Test bundle hash is deterministic."""
        contracts = {
            "rbac.json": '{"version": "1.0"}',
            "workflows.json": '{"version": "1.0"}',
        }

        manifest1 = generate_manifest(
            bundle_name="test-bundle",
            version="1.0.0",
            contracts=contracts,
        )
        manifest2 = generate_manifest(
            bundle_name="test-bundle",
            version="1.0.0",
            contracts=contracts,
        )

        assert get_bundle_hash(manifest1) == get_bundle_hash(manifest2)

    def test_manifest_bundle_hash_changes_with_content(self):
        """Test bundle hash changes when content changes."""
        contracts1 = {
            "rbac.json": '{"version": "1.0"}',
        }
        contracts2 = {
            "rbac.json": '{"version": "2.0"}',
        }

        manifest1 = generate_manifest(
            bundle_name="test-bundle",
            version="1.0.0",
            contracts=contracts1,
        )
        manifest2 = generate_manifest(
            bundle_name="test-bundle",
            version="1.0.0",
            contracts=contracts2,
        )

        assert get_bundle_hash(manifest1) != get_bundle_hash(manifest2)

    def test_manifest_sorted_contracts(self):
        """Test contracts are sorted alphabetically in hash computation."""
        # Order shouldn't matter
        contracts1 = {
            "a.json": "content_a",
            "b.json": "content_b",
        }
        contracts2 = {
            "b.json": "content_b",
            "a.json": "content_a",
        }

        manifest1 = generate_manifest("test", "1.0", contracts1)
        manifest2 = generate_manifest("test", "1.0", contracts2)

        assert get_bundle_hash(manifest1) == get_bundle_hash(manifest2)

    def test_generate_manifest_json(self):
        """Test JSON manifest generation."""
        contracts = {
            "rbac.json": '{"version": "1.0"}',
        }

        manifest_json = generate_manifest_json(
            bundle_name="test-bundle",
            version="1.0.0",
            contracts=contracts,
        )

        # Should be valid JSON
        manifest = json.loads(manifest_json)
        assert manifest["name"] == "test-bundle"

    def test_required_contracts_flag(self):
        """Test that required contracts are marked required=true."""
        contracts = {
            "rbac.json": '{"version": "1.0"}',
            "openapi.yaml": 'openapi: "3.0.0"',
        }

        manifest = generate_manifest("test", "1.0", contracts)

        rbac = next(c for c in manifest["contracts"] if c["file"] == "rbac.json")
        openapi = next(c for c in manifest["contracts"] if c["file"] == "openapi.yaml")

        assert rbac["required"] is True, "rbac.json should be required"
        assert openapi["required"] is False, "openapi.yaml should be optional"


class TestManifestHashVerification:
    """Test that manifest hashes can be verified."""

    def test_verify_contract_hash(self):
        """Test that contract hashes can be independently verified."""
        content = '{"version": "1.0", "name": "rbac"}'
        contracts = {"rbac.json": content}

        manifest = generate_manifest("test", "1.0", contracts)

        # Independently compute hash
        computed_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Find rbac.json in contracts array
        rbac_contract = next(c for c in manifest["contracts"] if c["file"] == "rbac.json")
        assert rbac_contract["sha256"] == f"SHA256:{computed_hash}"

    def test_verify_bundle_hash_algorithm(self):
        """Test bundle hash algorithm is reproducible."""
        contracts = {
            "a.json": "content_a",
            "b.json": "content_b",
        }

        manifest = generate_manifest("test", "1.0", contracts)

        # Reproduce the algorithm
        contract_hashes = {
            filename: sha256_str(content)
            for filename, content in sorted(contracts.items())
        }
        all_hashes = "".join(
            f"{k}:{v}" for k, v in sorted(contract_hashes.items())
        )
        expected_bundle_hash = sha256_str(all_hashes)

        assert get_bundle_hash(manifest) == expected_bundle_hash
