"""Tests for AuditPack CLI (FASE 8 / E8.1).

Tests:
1. Gerar auditpack para um episódio fixture => zip criado e index válido
2. Determinismo: gerar duas vezes => index.root_hash igual
3. Se existir arquivo proibido (fixture .env) => falha SECURITY com error_code AUDITPACK_SECURITY_BLOCKED
4. index.json valida no schema auditpack_index.v1
5. root_hash muda se qualquer arquivo do pack mudar
"""

import hashlib
import json
import pytest
import tempfile
import zipfile
from pathlib import Path

from episodes.episode_store import EpisodeStore, compute_content_hash
from auditpack import (
    AUDITPACK_INDEX_SCHEMA_VERSION,
    FORBIDDEN_PATTERNS,
    AuditPackError,
    AuditPackSecurityError,
    AuditPackValidationError,
    build_auditpack,
    compute_auditpack_index,
    compute_root_hash,
    verify_no_secrets,
    validate_auditpack_index,
    generate_readme_audit,
    generate_sha256sums,
)
from auditpack.auditpack import compute_file_hash, compute_content_hash as compute_hash
from auditpack.auditpack_cli import cmd_auditpack, AuditPackCLIResult


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_store():
    """Create a temporary episode store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield EpisodeStore(Path(tmpdir))


@pytest.fixture
def sample_episode(temp_store):
    """Create a sample episode with various files."""
    episode_id = "exec-audit-001"
    temp_store.create_episode(
        episode_id=episode_id,
        execution_id=episode_id,
        input_mode="natural",
        input_hash="sha256:" + "a" * 64,
    )

    # Add some contracts
    episode_dir = temp_store._get_episode_dir(episode_id)
    contracts_dir = episode_dir / "contracts"
    contracts_dir.mkdir(exist_ok=True)

    (contracts_dir / "contract_001.json").write_text(json.dumps({
        "name": "TestContract",
        "version": "1.0.0",
    }))

    # Add input file
    input_dir = episode_dir / "input"
    input_dir.mkdir(exist_ok=True)
    (input_dir / "input.txt").write_text("Sample input content")

    # Register a simple runlog
    runlog = {
        "schema_version": "runlog.v1",
        "execution_id": episode_id,
        "final_status": "success",
        "blocked_reason": None,
        "duration_ms": 100,
        "errors": [],
        "error_codes": [],
    }
    temp_store.register_runlog(episode_id, runlog)

    return episode_id


@pytest.fixture
def episode_with_approval(temp_store):
    """Create an episode with approval."""
    episode_id = "exec-approved-001"
    temp_store.create_episode(
        episode_id=episode_id,
        execution_id=episode_id,
        input_mode="natural",
        input_hash="sha256:" + "b" * 64,
    )

    # Add approval
    episode_dir = temp_store._get_episode_dir(episode_id)
    approvals_dir = episode_dir / "approvals"
    approvals_dir.mkdir(exist_ok=True)

    (approvals_dir / "approval_001.json").write_text(json.dumps({
        "approved_by": "admin",
        "approved_at": "2024-01-01T00:00:00Z",
    }))

    # Register runlog
    runlog = {
        "schema_version": "runlog.v1",
        "execution_id": episode_id,
        "final_status": "success",
        "blocked_reason": None,
        "duration_ms": 50,
        "errors": [],
        "error_codes": [],
    }
    temp_store.register_runlog(episode_id, runlog)

    return episode_id


@pytest.fixture
def episode_with_cr(temp_store):
    """Create an episode with change request."""
    episode_id = "exec-cr-001"
    temp_store.create_episode(
        episode_id=episode_id,
        execution_id=episode_id,
        input_mode="idl",
        input_hash="sha256:" + "c" * 64,
    )

    # Add change request
    episode_dir = temp_store._get_episode_dir(episode_id)
    cr_dir = episode_dir / "change_request"
    cr_dir.mkdir(exist_ok=True)

    (cr_dir / "change_request.json").write_text(json.dumps({
        "schema_version": "change_request.v1",
        "change_request_id": "cr-001",
        "previous_episode_id": "exec-000",
    }))

    # Register runlog
    runlog = {
        "schema_version": "runlog.v1",
        "execution_id": episode_id,
        "final_status": "success",
        "blocked_reason": None,
        "duration_ms": 75,
        "errors": [],
        "error_codes": [],
    }
    temp_store.register_runlog(episode_id, runlog)

    return episode_id


@pytest.fixture
def episode_with_forbidden_file(temp_store):
    """Create an episode with a forbidden file (.env)."""
    episode_id = "exec-forbidden-001"
    temp_store.create_episode(
        episode_id=episode_id,
        execution_id=episode_id,
        input_mode="natural",
        input_hash="sha256:" + "d" * 64,
    )

    # Add a forbidden .env file in input directory
    episode_dir = temp_store._get_episode_dir(episode_id)
    input_dir = episode_dir / "input"
    input_dir.mkdir(exist_ok=True)

    (input_dir / ".env").write_text("SECRET_KEY=should_not_be_here")

    # Register runlog
    runlog = {
        "schema_version": "runlog.v1",
        "execution_id": episode_id,
        "final_status": "success",
        "blocked_reason": None,
        "duration_ms": 25,
        "errors": [],
        "error_codes": [],
    }
    temp_store.register_runlog(episode_id, runlog)

    return episode_id


# =============================================================================
# Test 1: Generate auditpack for episode fixture => zip created and index valid
# =============================================================================


class TestAuditPackGeneration:
    """Test that auditpack generation creates valid ZIP with valid index."""

    def test_build_auditpack_creates_zip(self, temp_store, sample_episode):
        """Auditpack ZIP is created successfully."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"

            result = build_auditpack(
                episode_dir=episode_dir,
                out_zip=out_zip,
                include_artifacts=False,
            )

            assert result["success"] is True
            assert result["episode_id"] == sample_episode
            assert out_zip.exists()
            assert result["root_hash"].startswith("sha256:")
            assert result["total_files"] > 0

    def test_build_auditpack_zip_contains_index(self, temp_store, sample_episode):
        """Auditpack ZIP contains index.json."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                assert "auditpack/index.json" in names

    def test_build_auditpack_zip_contains_readme(self, temp_store, sample_episode):
        """Auditpack ZIP contains README_AUDIT.md."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                assert "auditpack/README_AUDIT.md" in names

    def test_build_auditpack_zip_contains_sha256sums(self, temp_store, sample_episode):
        """Auditpack ZIP contains sha256sums.txt."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                assert "auditpack/hashes/sha256sums.txt" in names

    def test_build_auditpack_zip_contains_manifest(self, temp_store, sample_episode):
        """Auditpack ZIP contains episode manifest."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                assert "auditpack/episode/manifest.json" in names

    def test_build_auditpack_zip_contains_runlog(self, temp_store, sample_episode):
        """Auditpack ZIP contains episode runlog."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                assert "auditpack/episode/runlog.json" in names

    def test_build_auditpack_includes_contracts(self, temp_store, sample_episode):
        """Auditpack ZIP includes contracts directory."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                assert any("contracts/" in name for name in names)

    def test_build_auditpack_includes_input(self, temp_store, sample_episode):
        """Auditpack ZIP includes input directory."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                assert any("input/" in name for name in names)


class TestAuditPackCLI:
    """Test the CLI interface for auditpack."""

    def test_cmd_auditpack_success(self, temp_store, sample_episode):
        """cmd_auditpack returns success for valid episode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"

            result = cmd_auditpack(
                episode_id=sample_episode,
                out_zip=out_zip,
                include_artifacts=False,
                base_path=temp_store.base_path,
            )

            assert result.success is True
            assert result.out_zip == str(out_zip)
            assert "root_hash" in result.data
            assert out_zip.exists()

    def test_cmd_auditpack_episode_not_found(self, temp_store):
        """cmd_auditpack returns error for non-existent episode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"

            result = cmd_auditpack(
                episode_id="nonexistent",
                out_zip=out_zip,
                base_path=temp_store.base_path,
            )

            assert result.success is False
            assert "EPISODE_NOT_FOUND" in result.error_codes


# =============================================================================
# Test 2: Determinism - generate twice => index.root_hash equal
# =============================================================================


class TestAuditPackDeterminism:
    """Test that auditpack generation is deterministic."""

    def test_root_hash_deterministic(self, temp_store, sample_episode):
        """Generating auditpack twice produces same root_hash."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip1 = Path(tmpdir) / "audit1.zip"
            out_zip2 = Path(tmpdir) / "audit2.zip"

            result1 = build_auditpack(episode_dir=episode_dir, out_zip=out_zip1)
            result2 = build_auditpack(episode_dir=episode_dir, out_zip=out_zip2)

            assert result1["root_hash"] == result2["root_hash"]

    def test_files_sorted_in_index(self, temp_store, sample_episode):
        """Files in index are sorted by path."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            result = build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            files = result["index"]["files"]
            paths = [f["path"] for f in files]
            assert paths == sorted(paths)

    def test_index_json_canonical(self, temp_store, sample_episode):
        """index.json uses canonical JSON (sorted keys)."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            with zipfile.ZipFile(out_zip, "r") as zf:
                index_content = zf.read("auditpack/index.json").decode("utf-8")
                index = json.loads(index_content)

                # Re-serialize with sort_keys and compare
                canonical = json.dumps(index, indent=2, sort_keys=True)
                assert index_content == canonical

    def test_compute_root_hash_deterministic(self):
        """compute_root_hash is deterministic for same input."""
        files = [
            {"path": "b/file.txt", "sha256": "sha256:" + "a" * 64},
            {"path": "a/file.txt", "sha256": "sha256:" + "b" * 64},
        ]

        hash1 = compute_root_hash(files)
        hash2 = compute_root_hash(files)

        assert hash1 == hash2

    def test_compute_root_hash_order_independent(self):
        """compute_root_hash produces same result regardless of input order."""
        files1 = [
            {"path": "b/file.txt", "sha256": "sha256:" + "a" * 64},
            {"path": "a/file.txt", "sha256": "sha256:" + "b" * 64},
        ]
        files2 = [
            {"path": "a/file.txt", "sha256": "sha256:" + "b" * 64},
            {"path": "b/file.txt", "sha256": "sha256:" + "a" * 64},
        ]

        hash1 = compute_root_hash(files1)
        hash2 = compute_root_hash(files2)

        assert hash1 == hash2


# =============================================================================
# Test 3: Forbidden file (.env) => SECURITY error with AUDITPACK_SECURITY_BLOCKED
# =============================================================================


class TestAuditPackSecurity:
    """Test security checks in auditpack."""

    def test_forbidden_env_file_blocked(self, temp_store, episode_with_forbidden_file):
        """Episode with .env file is blocked."""
        episode_dir = temp_store._get_episode_dir(episode_with_forbidden_file)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"

            with pytest.raises(AuditPackSecurityError) as exc_info:
                build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            assert "SECURITY:" in str(exc_info.value)
            assert exc_info.value.error_code == "AUDITPACK_SECURITY_BLOCKED"

    def test_cli_returns_security_error(self, temp_store, episode_with_forbidden_file):
        """CLI returns proper error for forbidden file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"

            result = cmd_auditpack(
                episode_id=episode_with_forbidden_file,
                out_zip=out_zip,
                base_path=temp_store.base_path,
            )

            assert result.success is False
            assert "AUDITPACK_SECURITY_BLOCKED" in result.error_codes

    def test_verify_no_secrets_raises_for_env(self):
        """verify_no_secrets raises for .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("SECRET=value")

            with pytest.raises(AuditPackSecurityError):
                verify_no_secrets([env_file])

    def test_verify_no_secrets_raises_for_secrets_dir(self):
        """verify_no_secrets raises for secrets/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets"
            secrets_dir.mkdir()
            secret_file = secrets_dir / "api_key.txt"
            secret_file.write_text("key123")

            with pytest.raises(AuditPackSecurityError):
                verify_no_secrets([secret_file], Path(tmpdir))

    def test_verify_no_secrets_raises_for_private_key(self):
        """verify_no_secrets raises for private_key file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = Path(tmpdir) / "private_key.pem"
            key_file.write_text("-----BEGIN RSA PRIVATE KEY-----")

            with pytest.raises(AuditPackSecurityError):
                verify_no_secrets([key_file])

    def test_verify_no_secrets_passes_for_safe_files(self):
        """verify_no_secrets passes for safe files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            safe_file = Path(tmpdir) / "manifest.json"
            safe_file.write_text('{"name": "test"}')

            # Should not raise
            verify_no_secrets([safe_file])

    def test_forbidden_patterns_list_not_empty(self):
        """FORBIDDEN_PATTERNS list is not empty."""
        assert len(FORBIDDEN_PATTERNS) > 0
        assert ".env" in FORBIDDEN_PATTERNS


# =============================================================================
# Test 4: index.json validates against auditpack_index.v1 schema
# =============================================================================


class TestAuditPackIndexSchema:
    """Test that index.json validates against schema."""

    def test_index_validates_against_schema(self, temp_store, sample_episode):
        """Generated index validates against schema."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            result = build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            # Should not raise
            validate_auditpack_index(result["index"])

    def test_index_has_required_fields(self, temp_store, sample_episode):
        """Index has all required fields."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            result = build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            index = result["index"]

            assert "schema_version" in index
            assert "episode_id" in index
            assert "files" in index
            assert "root_hash_sha256" in index
            assert "algorithm" in index

    def test_index_schema_version_correct(self, temp_store, sample_episode):
        """Index schema_version is correct."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            result = build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            assert result["index"]["schema_version"] == AUDITPACK_INDEX_SCHEMA_VERSION

    def test_index_files_have_required_fields(self, temp_store, sample_episode):
        """Each file entry has required fields."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            result = build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            for file_entry in result["index"]["files"]:
                assert "path" in file_entry
                assert "sha256" in file_entry
                assert "size_bytes" in file_entry

    def test_index_hash_format_correct(self, temp_store, sample_episode):
        """Hash format is sha256:<hex>."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            result = build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            # Root hash
            assert result["index"]["root_hash_sha256"].startswith("sha256:")
            assert len(result["index"]["root_hash_sha256"]) == 7 + 64  # sha256: + 64 hex

            # File hashes
            for file_entry in result["index"]["files"]:
                assert file_entry["sha256"].startswith("sha256:")
                assert len(file_entry["sha256"]) == 7 + 64

    def test_validate_auditpack_index_raises_for_invalid(self):
        """validate_auditpack_index raises for invalid index."""
        invalid_index = {"invalid": "data"}

        with pytest.raises(AuditPackValidationError):
            validate_auditpack_index(invalid_index)

    def test_index_stats_correct(self, temp_store, episode_with_approval):
        """Index stats reflect actual content."""
        episode_dir = temp_store._get_episode_dir(episode_with_approval)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            result = build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            stats = result["index"]["stats"]
            assert stats["has_approval"] is True
            assert stats["total_files"] == len(result["index"]["files"])

    def test_index_stats_change_request(self, temp_store, episode_with_cr):
        """Index stats reflect change request presence."""
        episode_dir = temp_store._get_episode_dir(episode_with_cr)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            result = build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            stats = result["index"]["stats"]
            assert stats["has_change_request"] is True


# =============================================================================
# Test 5: root_hash changes if any file in pack changes
# =============================================================================


class TestAuditPackRootHashIntegrity:
    """Test that root_hash changes when content changes."""

    def test_root_hash_changes_when_file_changes(self, temp_store, sample_episode):
        """root_hash changes when file content changes."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip1 = Path(tmpdir) / "audit1.zip"
            result1 = build_auditpack(episode_dir=episode_dir, out_zip=out_zip1)

            # Modify a file
            contract_file = episode_dir / "contracts" / "contract_001.json"
            contract_file.write_text(json.dumps({
                "name": "ModifiedContract",
                "version": "2.0.0",
            }))

            out_zip2 = Path(tmpdir) / "audit2.zip"
            result2 = build_auditpack(episode_dir=episode_dir, out_zip=out_zip2)

            assert result1["root_hash"] != result2["root_hash"]

    def test_root_hash_changes_when_file_added(self, temp_store, sample_episode):
        """root_hash changes when new file is added."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip1 = Path(tmpdir) / "audit1.zip"
            result1 = build_auditpack(episode_dir=episode_dir, out_zip=out_zip1)

            # Add a new file
            contracts_dir = episode_dir / "contracts"
            (contracts_dir / "contract_002.json").write_text(json.dumps({
                "name": "NewContract",
            }))

            out_zip2 = Path(tmpdir) / "audit2.zip"
            result2 = build_auditpack(episode_dir=episode_dir, out_zip=out_zip2)

            assert result1["root_hash"] != result2["root_hash"]

    def test_root_hash_changes_when_file_removed(self, temp_store, sample_episode):
        """root_hash changes when file is removed."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        # Add an extra file first
        contracts_dir = episode_dir / "contracts"
        extra_file = contracts_dir / "contract_extra.json"
        extra_file.write_text('{"name": "Extra"}')

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip1 = Path(tmpdir) / "audit1.zip"
            result1 = build_auditpack(episode_dir=episode_dir, out_zip=out_zip1)

            # Remove the file
            extra_file.unlink()

            out_zip2 = Path(tmpdir) / "audit2.zip"
            result2 = build_auditpack(episode_dir=episode_dir, out_zip=out_zip2)

            assert result1["root_hash"] != result2["root_hash"]

    def test_compute_root_hash_changes_with_path(self):
        """compute_root_hash changes when path changes."""
        files1 = [{"path": "a/file.txt", "sha256": "sha256:" + "a" * 64}]
        files2 = [{"path": "b/file.txt", "sha256": "sha256:" + "a" * 64}]

        hash1 = compute_root_hash(files1)
        hash2 = compute_root_hash(files2)

        assert hash1 != hash2

    def test_compute_root_hash_changes_with_content(self):
        """compute_root_hash changes when file hash changes."""
        files1 = [{"path": "a/file.txt", "sha256": "sha256:" + "a" * 64}]
        files2 = [{"path": "a/file.txt", "sha256": "sha256:" + "b" * 64}]

        hash1 = compute_root_hash(files1)
        hash2 = compute_root_hash(files2)

        assert hash1 != hash2


# =============================================================================
# Additional Tests: README and SHA256SUMS
# =============================================================================


class TestAuditPackReadme:
    """Test README_AUDIT.md generation."""

    def test_generate_readme_audit_contains_episode_id(self):
        """README contains episode ID."""
        index = {
            "stats": {"total_files": 5, "total_size_bytes": 1000},
            "root_hash_sha256": "sha256:" + "a" * 64,
        }

        readme = generate_readme_audit("test-episode", index)

        assert "test-episode" in readme

    def test_generate_readme_audit_contains_verification_instructions(self):
        """README contains verification instructions."""
        index = {
            "stats": {"total_files": 5, "total_size_bytes": 1000},
            "root_hash_sha256": "sha256:" + "a" * 64,
        }

        readme = generate_readme_audit("test-episode", index)

        assert "Verification" in readme
        assert "python3" in readme
        assert "sha256sum" in readme

    def test_generate_readme_audit_contains_root_hash(self):
        """README contains root hash."""
        root_hash = "sha256:" + "a" * 64
        index = {
            "stats": {"total_files": 5, "total_size_bytes": 1000},
            "root_hash_sha256": root_hash,
        }

        readme = generate_readme_audit("test-episode", index)

        assert root_hash in readme


class TestAuditPackSha256sums:
    """Test sha256sums.txt generation."""

    def test_generate_sha256sums_format(self):
        """sha256sums.txt has correct format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "file1.txt"
            file1.write_text("content1")

            file2 = Path(tmpdir) / "file2.txt"
            file2.write_text("content2")

            files = [(file1, "path/file1.txt"), (file2, "path/file2.txt")]

            sums = generate_sha256sums(files)

            lines = sums.strip().split("\n")
            assert len(lines) == 2

            for line in lines:
                parts = line.split("  ")
                assert len(parts) == 2
                assert len(parts[0]) == 64  # SHA256 hex without prefix

    def test_generate_sha256sums_sorted(self):
        """sha256sums.txt is sorted by path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "file1.txt"
            file1.write_text("content1")

            file2 = Path(tmpdir) / "file2.txt"
            file2.write_text("content2")

            # Provide in reverse order
            files = [(file2, "z/file2.txt"), (file1, "a/file1.txt")]

            sums = generate_sha256sums(files)

            lines = sums.strip().split("\n")
            # First line should have path starting with 'a'
            assert "a/file1.txt" in lines[0]
            assert "z/file2.txt" in lines[1]


# =============================================================================
# Test: Include Artifacts Option
# =============================================================================


class TestAuditPackArtifacts:
    """Test include_artifacts option."""

    def test_include_artifacts_false_excludes_artifacts(self, temp_store, sample_episode):
        """include_artifacts=False excludes artifacts directory."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        # Add artifacts
        artifacts_dir = episode_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        (artifacts_dir / "artifact.txt").write_text("artifact content")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip, include_artifacts=False)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                assert not any("artifacts/" in name for name in names)

    def test_include_artifacts_true_includes_artifacts(self, temp_store, sample_episode):
        """include_artifacts=True includes artifacts directory."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        # Add artifacts
        artifacts_dir = episode_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        (artifacts_dir / "artifact.txt").write_text("artifact content")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            build_auditpack(episode_dir=episode_dir, out_zip=out_zip, include_artifacts=True)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                assert any("artifacts/" in name for name in names)

    def test_index_reflects_include_artifacts(self, temp_store, sample_episode):
        """Index includes include_artifacts flag."""
        episode_dir = temp_store._get_episode_dir(sample_episode)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            result = build_auditpack(
                episode_dir=episode_dir,
                out_zip=out_zip,
                include_artifacts=True,
            )

            assert result["index"]["include_artifacts"] is True


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestAuditPackErrors:
    """Test error handling in auditpack."""

    def test_episode_dir_not_found(self):
        """build_auditpack raises for non-existent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"
            fake_dir = Path(tmpdir) / "nonexistent"

            with pytest.raises(AuditPackError) as exc_info:
                build_auditpack(episode_dir=fake_dir, out_zip=out_zip)

            assert "not found" in str(exc_info.value)

    def test_missing_manifest(self, temp_store):
        """build_auditpack raises for missing manifest."""
        # Create episode directory without manifest
        episode_id = "no-manifest"
        engine_dir = temp_store.base_path / ".engine"
        engine_dir.mkdir(parents=True, exist_ok=True)
        episode_dir = engine_dir / "episodes" / episode_id
        episode_dir.mkdir(parents=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_zip = Path(tmpdir) / "audit.zip"

            with pytest.raises(AuditPackError) as exc_info:
                build_auditpack(episode_dir=episode_dir, out_zip=out_zip)

            assert "manifest" in str(exc_info.value).lower()


# =============================================================================
# Test: Hash Computation
# =============================================================================


class TestHashComputation:
    """Test hash computation functions."""

    def test_compute_file_hash(self):
        """compute_file_hash returns correct format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("hello world")

            hash_result = compute_file_hash(file_path)

            assert hash_result.startswith("sha256:")
            assert len(hash_result) == 7 + 64

    def test_compute_content_hash(self):
        """compute_content_hash returns correct format."""
        content = b"test content"

        hash_result = compute_hash(content)

        assert hash_result.startswith("sha256:")
        assert len(hash_result) == 7 + 64

    def test_compute_content_hash_deterministic(self):
        """compute_content_hash is deterministic."""
        content = b"test content"

        hash1 = compute_hash(content)
        hash2 = compute_hash(content)

        assert hash1 == hash2

    def test_compute_content_hash_different_for_different_content(self):
        """compute_content_hash differs for different content."""
        hash1 = compute_hash(b"content1")
        hash2 = compute_hash(b"content2")

        assert hash1 != hash2
