"""Tests for offline proof verification.

Tests cover:
- PASS: Valid bundle (DSL→IRCS→ISE pipeline)
- FAIL: Altered contract hash
- FAIL: Invalid manifest hash in ledger
- FAIL: Inconsistent ledger vs manifest
- FAIL: Missing source_idl_sha256
- FAIL: Invalid source_idl_sha256 format
- FAIL: Path traversal attempts
"""

import hashlib
import json
from pathlib import Path

import pytest

from engine.proof import (
    PROOF_CONTRACT_HASH_MISMATCH,
    PROOF_CONTRACT_MISSING,
    PROOF_LEDGER_CONTRACT_EXTRA,
    PROOF_LEDGER_CONTRACT_HASH_MISMATCH,
    PROOF_LEDGER_CONTRACT_MISSING,
    PROOF_LEDGER_INVALID_JSON,
    PROOF_LEDGER_MANIFEST_HASH_MISMATCH,
    PROOF_LEDGER_MISSING,
    PROOF_MANIFEST_INVALID_JSON,
    PROOF_MANIFEST_INVALID_SCHEMA,
    PROOF_MANIFEST_MISSING,
    PROOF_PATH_TRAVERSAL,
    PROOF_SOURCE_IDL_INVALID_FORMAT,
    PROOF_SOURCE_IDL_MISSING,
    ProofResult,
    is_valid_sha256_hex,
    verify_bundle_offline,
)


def sha256_bytes(data: bytes) -> str:
    """Compute SHA256 of bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_str(text: str) -> str:
    """Compute SHA256 of string (UTF-8)."""
    return sha256_bytes(text.encode("utf-8"))


def create_valid_bundle(tmp_path: Path) -> Path:
    """Create a valid bundle for testing.

    Returns the bundle path.
    """
    bundle_path = tmp_path / "test-bundle"
    bundle_path.mkdir()

    # Create contracts
    contracts = {
        "rbac.json": '{"roles": []}',
        "workflows.json": '{"workflows": []}',
    }

    contract_hashes = {}
    for filename, content in contracts.items():
        file_path = bundle_path / filename
        file_path.write_text(content)
        contract_hashes[filename] = sha256_str(content)

    # Create manifest
    manifest = {
        "name": "test-bundle",
        "version": "1.0.0",
        "description": "Test bundle",
        "contracts": [
            {
                "file": filename,
                "sha256": f"SHA256:{hash_val}",
                "required": True,
            }
            for filename, hash_val in contract_hashes.items()
        ],
    }

    manifest_path = bundle_path / "bundle.manifest.json"
    manifest_content = json.dumps(manifest, indent=2, sort_keys=True)
    manifest_path.write_text(manifest_content)
    manifest_hash = sha256_str(manifest_content)

    # Create ledger
    source_idl_sha256 = "a" * 64  # Valid 64-char hex

    ledger = {
        "ledger_version": "1.0",
        "bundle_name": "test-bundle",
        "bundle_version": "1.0.0",
        "manifest_hash": manifest_hash,
        "source_idl_sha256": source_idl_sha256,
        "contracts": [
            {
                "contract_name": filename,
                "content_hash": hash_val,
                "status": "active",
            }
            for filename, hash_val in contract_hashes.items()
        ],
    }

    ledger_path = bundle_path / "contract_ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True))

    return bundle_path


class TestIsValidSha256Hex:
    """Tests for is_valid_sha256_hex helper."""

    def test_valid_lowercase(self):
        assert is_valid_sha256_hex("a" * 64)

    def test_valid_uppercase(self):
        assert is_valid_sha256_hex("A" * 64)

    def test_valid_mixed(self):
        assert is_valid_sha256_hex("aAbBcCdD" * 8)

    def test_valid_numeric(self):
        assert is_valid_sha256_hex("0123456789abcdef" * 4)

    def test_invalid_too_short(self):
        assert not is_valid_sha256_hex("a" * 63)

    def test_invalid_too_long(self):
        assert not is_valid_sha256_hex("a" * 65)

    def test_invalid_not_hex(self):
        assert not is_valid_sha256_hex("g" * 64)

    def test_invalid_empty(self):
        assert not is_valid_sha256_hex("")

    def test_invalid_not_string(self):
        assert not is_valid_sha256_hex(123)  # type: ignore


class TestVerifyBundleOfflinePass:
    """Tests for successful verification (PASS cases)."""

    def test_valid_bundle_passes(self, tmp_path: Path):
        """Valid bundle should pass verification."""
        bundle_path = create_valid_bundle(tmp_path)
        result = verify_bundle_offline(bundle_path)

        assert result.passed is True
        assert result.error_code is None
        assert result.bundle_name == "test-bundle"
        assert result.bundle_version == "1.0.0"
        assert result.source_idl_sha256 == "a" * 64
        assert result.contracts_verified == 2

    def test_result_to_dict(self, tmp_path: Path):
        """Result should be serializable to dict."""
        bundle_path = create_valid_bundle(tmp_path)
        result = verify_bundle_offline(bundle_path)
        d = result.to_dict()

        assert d["passed"] is True
        assert d["bundle_name"] == "test-bundle"

    def test_hash_with_prefix_accepted(self, tmp_path: Path):
        """Hashes with SHA256: prefix should be accepted."""
        bundle_path = create_valid_bundle(tmp_path)
        # Bundle was created with SHA256: prefix - should work
        result = verify_bundle_offline(bundle_path)
        assert result.passed is True


class TestVerifyBundleOfflineManifestFail:
    """Tests for manifest-related failures."""

    def test_missing_manifest_fails(self, tmp_path: Path):
        """Missing manifest should fail with PROOF_MANIFEST_MISSING."""
        bundle_path = tmp_path / "empty-bundle"
        bundle_path.mkdir()

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_MANIFEST_MISSING

    def test_invalid_manifest_json_fails(self, tmp_path: Path):
        """Invalid JSON in manifest should fail."""
        bundle_path = tmp_path / "bad-json-bundle"
        bundle_path.mkdir()

        manifest_path = bundle_path / "bundle.manifest.json"
        manifest_path.write_text("{ invalid json }")

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_MANIFEST_INVALID_JSON

    def test_manifest_missing_contracts_array_fails(self, tmp_path: Path):
        """Manifest without contracts array should fail."""
        bundle_path = tmp_path / "no-contracts-bundle"
        bundle_path.mkdir()

        manifest_path = bundle_path / "bundle.manifest.json"
        manifest_path.write_text('{"name": "test"}')

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_MANIFEST_INVALID_SCHEMA


class TestVerifyBundleOfflineContractFail:
    """Tests for contract-related failures."""

    def test_missing_required_contract_fails(self, tmp_path: Path):
        """Missing required contract should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        # Delete one contract
        (bundle_path / "rbac.json").unlink()

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_CONTRACT_MISSING
        assert result.details.get("file") == "rbac.json"

    def test_contract_hash_mismatch_fails(self, tmp_path: Path):
        """Altered contract content should fail hash verification."""
        bundle_path = create_valid_bundle(tmp_path)

        # Alter contract content (1 byte change)
        rbac_path = bundle_path / "rbac.json"
        rbac_path.write_text('{"roles": [1]}')  # Changed from []

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_CONTRACT_HASH_MISMATCH
        assert result.details.get("file") == "rbac.json"
        assert "expected" in result.details
        assert "actual" in result.details

    def test_path_traversal_absolute_fails(self, tmp_path: Path):
        """Absolute path in contract file should fail."""
        bundle_path = tmp_path / "traversal-bundle"
        bundle_path.mkdir()

        manifest = {
            "name": "test",
            "version": "1.0.0",
            "contracts": [
                {"file": "/etc/passwd", "sha256": "a" * 64, "required": True}
            ],
        }

        manifest_path = bundle_path / "bundle.manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_PATH_TRAVERSAL

    def test_path_traversal_dotdot_fails(self, tmp_path: Path):
        """Path with .. should fail."""
        bundle_path = tmp_path / "traversal-bundle2"
        bundle_path.mkdir()

        manifest = {
            "name": "test",
            "version": "1.0.0",
            "contracts": [
                {"file": "../secret.json", "sha256": "a" * 64, "required": True}
            ],
        }

        manifest_path = bundle_path / "bundle.manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_PATH_TRAVERSAL


class TestVerifyBundleOfflineLedgerFail:
    """Tests for ledger-related failures."""

    def test_missing_ledger_fails(self, tmp_path: Path):
        """Missing ledger should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        # Delete ledger
        (bundle_path / "contract_ledger.json").unlink()

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_LEDGER_MISSING

    def test_invalid_ledger_json_fails(self, tmp_path: Path):
        """Invalid JSON in ledger should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        ledger_path = bundle_path / "contract_ledger.json"
        ledger_path.write_text("{ invalid }")

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_LEDGER_INVALID_JSON

    def test_ledger_manifest_hash_mismatch_fails(self, tmp_path: Path):
        """Ledger with wrong manifest_hash should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        # Read and modify ledger
        ledger_path = bundle_path / "contract_ledger.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["manifest_hash"] = "b" * 64  # Wrong hash
        ledger_path.write_text(json.dumps(ledger))

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_LEDGER_MANIFEST_HASH_MISMATCH

    def test_ledger_missing_contract_fails(self, tmp_path: Path):
        """Ledger missing a contract from manifest should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        # Remove one contract from ledger
        ledger_path = bundle_path / "contract_ledger.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["contracts"] = [
            c for c in ledger["contracts"] if c["contract_name"] != "rbac.json"
        ]
        ledger_path.write_text(json.dumps(ledger))

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_LEDGER_CONTRACT_MISSING

    def test_ledger_extra_contract_fails(self, tmp_path: Path):
        """Ledger with extra contract not in manifest should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        # Add extra contract to ledger
        ledger_path = bundle_path / "contract_ledger.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["contracts"].append({
            "contract_name": "extra.json",
            "content_hash": "c" * 64,
            "status": "active",
        })
        ledger_path.write_text(json.dumps(ledger))

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_LEDGER_CONTRACT_EXTRA

    def test_ledger_contract_hash_mismatch_fails(self, tmp_path: Path):
        """Ledger with wrong contract hash should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        # Modify hash in ledger
        ledger_path = bundle_path / "contract_ledger.json"
        ledger = json.loads(ledger_path.read_text())
        for c in ledger["contracts"]:
            if c["contract_name"] == "rbac.json":
                c["content_hash"] = "d" * 64  # Wrong hash
        ledger_path.write_text(json.dumps(ledger))

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_LEDGER_CONTRACT_HASH_MISMATCH


class TestVerifyBundleOfflineSourceIdlFail:
    """Tests for source_idl_sha256 failures."""

    def test_missing_source_idl_sha256_fails(self, tmp_path: Path):
        """Missing source_idl_sha256 should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        # Remove source_idl_sha256 from ledger
        ledger_path = bundle_path / "contract_ledger.json"
        ledger = json.loads(ledger_path.read_text())
        del ledger["source_idl_sha256"]
        ledger_path.write_text(json.dumps(ledger))

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_SOURCE_IDL_MISSING

    def test_invalid_source_idl_sha256_too_short_fails(self, tmp_path: Path):
        """source_idl_sha256 with wrong length should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        # Set invalid source_idl_sha256
        ledger_path = bundle_path / "contract_ledger.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["source_idl_sha256"] = "a" * 63  # Too short
        ledger_path.write_text(json.dumps(ledger))

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_SOURCE_IDL_INVALID_FORMAT

    def test_invalid_source_idl_sha256_not_hex_fails(self, tmp_path: Path):
        """source_idl_sha256 with non-hex chars should fail."""
        bundle_path = create_valid_bundle(tmp_path)

        # Set invalid source_idl_sha256
        ledger_path = bundle_path / "contract_ledger.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["source_idl_sha256"] = "g" * 64  # Not hex
        ledger_path.write_text(json.dumps(ledger))

        result = verify_bundle_offline(bundle_path)

        assert result.passed is False
        assert result.error_code == PROOF_SOURCE_IDL_INVALID_FORMAT


class TestE2EPipeline:
    """End-to-end test with real DSL→IRCS→ISE pipeline."""

    def test_dsl_to_bundle_verifies_offline(self, tmp_path: Path):
        """Bundle generated from DSL pipeline should pass offline verification."""
        from engine.idl_dsl import parse_dsl
        from engine.ise import compile_from_ircs

        dsl = '''
system TestSystem {
  name: "Test System"
  description: "E2E test"
  version: 1.0.0
  domain: "test"
  owner: "Test"
  contact: "test@test.com"
  tenancy: single
}

actors {
  human operator {
    name: "Operator"
    description: "Test operator"
    authentication: oauth2
    permissions: [test.read]
  }
}

entities {
  entity Item {
    storage { tenant_field: tenant_id }
    field id: uuid required
    field tenant_id: uuid required
    field name: string required
  }
}
'''

        # Parse DSL to IRCS
        ir = parse_dsl(dsl)
        assert ir["ir_version"] == "ircs.v1"
        dsl_hash = ir["source_idl_sha256"]

        # Compile to bundle
        bundle_dir = tmp_path / "bundles"
        result = compile_from_ircs(ir, "e2e-test", str(bundle_dir))
        assert result.success

        # Verify offline
        bundle_path = Path(result.bundle_path)
        proof_result = verify_bundle_offline(bundle_path)

        assert proof_result.passed is True
        assert proof_result.source_idl_sha256 == dsl_hash
        assert proof_result.bundle_name == "e2e-test"
        assert proof_result.contracts_verified > 0


class TestCLI:
    """Tests for CLI functionality."""

    def test_cli_verify_pass(self, tmp_path: Path):
        """CLI should return exit code 0 for valid bundle."""
        import subprocess

        bundle_path = create_valid_bundle(tmp_path)

        result = subprocess.run(
            ["python", "-m", "engine.proof", "verify", str(bundle_path)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent / "src",
        )

        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_cli_verify_fail(self, tmp_path: Path):
        """CLI should return exit code 1 for invalid bundle."""
        import subprocess

        bundle_path = tmp_path / "empty"
        bundle_path.mkdir()

        result = subprocess.run(
            ["python", "-m", "engine.proof", "verify", str(bundle_path)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent / "src",
        )

        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_cli_verify_json_output(self, tmp_path: Path):
        """CLI with --json should output valid JSON."""
        import subprocess

        bundle_path = create_valid_bundle(tmp_path)

        result = subprocess.run(
            ["python", "-m", "engine.proof", "verify", str(bundle_path), "--json"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent / "src",
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["passed"] is True
        assert output["bundle_name"] == "test-bundle"
