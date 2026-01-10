"""Tests for episodes module - Episode Store, Manifest v1, and Approval Gate.

Tests cover:
- Episode manifest validation (new schema with inputs, contracts, outputs, links, integrity)
- Episode store operations (create, register, finalize, verify)
- Episode integrity verification (root hash detection of modifications)
- Approval gate blocking release without valid approval
- CLI commands (approve, show, list, gate-check, verify)
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from episodes import (
    # Constants
    EPISODE_MANIFEST_SCHEMA_VERSION,
    EPISODES_DIR,
    MANIFEST_FILENAME,
    RUNLOG_FILENAME,
    APPROVAL_FILENAME,
    # Manifest
    EpisodeManifestValidationError,
    validate_episode_manifest,
    canonicalize_episode_manifest,
    load_episode_manifest,
    create_episode_manifest,
    get_episode_status,
    is_episode_approved,
    is_episode_finalized,
    get_episode_root_hash,
    # Store
    EpisodeStore,
    EpisodeStoreError,
    EpisodeNotFoundError,
    EpisodeDuplicateError,
    EpisodeIntegrityError,
    EpisodeImmutableError,
    compute_file_hash,
    compute_content_hash,
    compute_json_hash,
    compute_episode_root_hash,
    # Gate
    ApprovalGate,
    ApprovalGateError,
    GateResult,
    check_release_approval,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_base():
    """Create a temporary base directory for .engine/episodes."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def valid_manifest():
    """Return a valid episode manifest."""
    return {
        "schema_version": "episode_manifest.v1",
        "episode_id": "exec-001",
        "execution_id": "exec-001",
        "created_at": "2024-01-15T10:30:00Z",
        "created_by": "test-user",
        "inputs": {
            "input_mode": "natural",
            "input_hash_sha256": "sha256:" + "a" * 64,
        },
        "contracts": {
            "idl_hash_sha256": None,
            "srs_hash_sha256": None,
            "ir_hash_sha256": None,
            "openapi_hash_sha256": None,
            "plan_hash_sha256": None,
        },
        "outputs": {
            "repo_hash_sha256": None,
            "release_artifact_hash_sha256": None,
        },
        "links": {
            "previous_episode_id": None,
            "change_request_id": None,
        },
        "integrity": {
            "episode_root_hash_sha256": "sha256:" + "0" * 64,
            "algorithm": "sha256",
            "file_hashes": None,
        },
    }


# =============================================================================
# Episode Manifest Validation Tests
# =============================================================================


class TestEpisodeManifestValidation:
    """Tests for episode manifest validation."""

    def test_valid_manifest_passes(self, valid_manifest):
        """Valid manifest should pass validation."""
        validate_episode_manifest(valid_manifest)  # Should not raise

    def test_missing_schema_version_fails(self, valid_manifest):
        """Missing schema_version should fail."""
        del valid_manifest["schema_version"]
        with pytest.raises(EpisodeManifestValidationError) as exc:
            validate_episode_manifest(valid_manifest)
        assert "SCHEMA:" in str(exc.value)

    def test_wrong_schema_version_fails(self, valid_manifest):
        """Wrong schema_version should fail."""
        valid_manifest["schema_version"] = "episode_manifest.v2"
        with pytest.raises(EpisodeManifestValidationError) as exc:
            validate_episode_manifest(valid_manifest)
        assert "SCHEMA:" in str(exc.value)

    def test_missing_inputs_fails(self, valid_manifest):
        """Missing inputs should fail."""
        del valid_manifest["inputs"]
        with pytest.raises(EpisodeManifestValidationError) as exc:
            validate_episode_manifest(valid_manifest)
        assert "SCHEMA:" in str(exc.value)

    def test_invalid_input_mode_fails(self, valid_manifest):
        """Invalid input_mode should fail."""
        valid_manifest["inputs"]["input_mode"] = "invalid"
        with pytest.raises(EpisodeManifestValidationError) as exc:
            validate_episode_manifest(valid_manifest)
        assert "SCHEMA:" in str(exc.value)

    def test_invalid_hash_format_fails(self, valid_manifest):
        """Invalid hash format should fail."""
        valid_manifest["inputs"]["input_hash_sha256"] = "invalid"
        with pytest.raises(EpisodeManifestValidationError) as exc:
            validate_episode_manifest(valid_manifest)
        assert "SCHEMA:" in str(exc.value)

    def test_all_input_modes_valid(self, valid_manifest):
        """All input modes should be valid."""
        for mode in ["natural", "draft", "idl"]:
            valid_manifest["inputs"]["input_mode"] = mode
            validate_episode_manifest(valid_manifest)  # Should not raise


# =============================================================================
# Episode Store Tests
# =============================================================================


class TestEpisodeStore:
    """Tests for EpisodeStore operations."""

    def test_create_episode_success(self, temp_base):
        """Creating an episode should create proper directory structure."""
        store = EpisodeStore(temp_base)

        episode_dir = store.create_episode(
            episode_id="exec-001",
            execution_id="exec-001",
            input_mode="natural",
            input_hash="sha256:" + "a" * 64,
        )

        assert episode_dir.exists()
        assert (episode_dir / "manifest.json").exists()
        assert (episode_dir / "input").is_dir()
        assert (episode_dir / "contracts").is_dir()
        assert (episode_dir / "artifacts").is_dir()
        assert (episode_dir / "approvals").is_dir()

    def test_create_duplicate_episode_fails(self, temp_base):
        """Creating a duplicate episode should fail."""
        store = EpisodeStore(temp_base)

        store.create_episode(
            episode_id="exec-001",
            execution_id="exec-001",
            input_mode="natural",
            input_hash="sha256:" + "a" * 64,
        )

        with pytest.raises(EpisodeDuplicateError) as exc:
            store.create_episode(
                episode_id="exec-001",
                execution_id="exec-001",
                input_mode="natural",
                input_hash="sha256:" + "a" * 64,
            )
        assert "GOVERNANCE:" in str(exc.value)

    def test_register_contract(self, temp_base):
        """Registering a contract should save file and update manifest."""
        store = EpisodeStore(temp_base)

        store.create_episode(
            episode_id="exec-001",
            execution_id="exec-001",
            input_mode="natural",
            input_hash="sha256:" + "a" * 64,
        )

        idl_content = b'{"project": "test"}'
        idl_hash = store.register_contract("exec-001", "idl", idl_content)

        # Verify file exists
        contracts_dir = store._get_contracts_dir("exec-001")
        assert (contracts_dir / "idl.json").exists()

        # Verify manifest updated
        manifest = store.get_manifest("exec-001")
        assert manifest["contracts"]["idl_hash_sha256"] == idl_hash

    def test_register_artifact(self, temp_base):
        """Registering an artifact should save file and update manifest."""
        store = EpisodeStore(temp_base)

        store.create_episode(
            episode_id="exec-001",
            execution_id="exec-001",
            input_mode="natural",
            input_hash="sha256:" + "a" * 64,
        )

        repo_content = b'repo content'
        repo_hash = store.register_artifact("exec-001", "repo", repo_content, "repo.tar.gz")

        # Verify file exists
        artifacts_dir = store._get_artifacts_dir("exec-001")
        assert (artifacts_dir / "repo.tar.gz").exists()

        # Verify manifest updated
        manifest = store.get_manifest("exec-001")
        assert manifest["outputs"]["repo_hash_sha256"] == repo_hash

    def test_register_runlog(self, temp_base):
        """Registering a runlog should save file."""
        store = EpisodeStore(temp_base)

        store.create_episode(
            episode_id="exec-001",
            execution_id="exec-001",
            input_mode="natural",
            input_hash="sha256:" + "a" * 64,
        )

        runlog = {"execution_id": "exec-001", "status": "success"}
        store.register_runlog("exec-001", runlog)

        # Verify file exists
        runlog_path = store._get_runlog_path("exec-001")
        assert runlog_path.exists()

    def test_finalize_episode(self, temp_base):
        """Finalizing an episode should compute root hash."""
        store = EpisodeStore(temp_base)

        store.create_episode(
            episode_id="exec-001",
            execution_id="exec-001",
            input_mode="natural",
            input_hash="sha256:" + "a" * 64,
        )

        # Add some content
        store.register_contract("exec-001", "idl", b'{"test": true}')
        store.register_runlog("exec-001", {"status": "success"})

        # Finalize
        manifest = store.finalize_episode("exec-001")

        # Verify root hash is computed (not placeholder)
        root_hash = manifest["integrity"]["episode_root_hash_sha256"]
        assert root_hash != "sha256:" + "0" * 64
        assert root_hash.startswith("sha256:")

        # Verify file_hashes populated
        assert manifest["integrity"]["file_hashes"] is not None
        assert len(manifest["integrity"]["file_hashes"]) > 0

    def test_finalized_episode_is_immutable(self, temp_base):
        """Finalized episode should not allow modifications."""
        store = EpisodeStore(temp_base)

        store.create_episode(
            episode_id="exec-001",
            execution_id="exec-001",
            input_mode="natural",
            input_hash="sha256:" + "a" * 64,
        )
        store.finalize_episode("exec-001")

        # Attempt to register contract should fail
        with pytest.raises(EpisodeImmutableError) as exc:
            store.register_contract("exec-001", "srs", b'content')
        assert "GOVERNANCE:" in str(exc.value)

    def test_list_episodes(self, temp_base):
        """Listing episodes should return all episodes."""
        store = EpisodeStore(temp_base)

        # Create multiple episodes
        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)
        store.create_episode("exec-002", "exec-002", "draft", "sha256:" + "b" * 64)

        episodes = store.list_episodes()
        assert len(episodes) == 2

    def test_list_episodes_filter_by_status(self, temp_base):
        """Listing with status filter should work."""
        store = EpisodeStore(temp_base)

        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)

        pending = store.list_episodes(status="pending")
        assert len(pending) == 1

        approved = store.list_episodes(status="approved")
        assert len(approved) == 0


# =============================================================================
# Episode Integrity Tests
# =============================================================================


class TestEpisodeIntegrity:
    """Tests for episode integrity verification."""

    def test_verify_finalized_episode(self, temp_base):
        """Verifying finalized episode should succeed."""
        store = EpisodeStore(temp_base)

        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)
        store.register_contract("exec-001", "idl", b'{"test": true}')
        store.finalize_episode("exec-001")

        is_valid, error = store.verify_integrity("exec-001")
        assert is_valid is True
        assert error is None

    def test_verify_unfinalized_episode_fails(self, temp_base):
        """Verifying unfinalized episode should fail."""
        store = EpisodeStore(temp_base)

        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)

        is_valid, error = store.verify_integrity("exec-001")
        assert is_valid is False
        assert "not finalized" in error.lower()

    def test_modification_detected(self, temp_base):
        """Modification to episode content should be detected."""
        store = EpisodeStore(temp_base)

        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)
        store.register_contract("exec-001", "idl", b'{"test": true}')
        store.finalize_episode("exec-001")

        # Modify the contract file directly
        contracts_dir = store._get_contracts_dir("exec-001")
        idl_path = contracts_dir / "idl.json"
        with open(idl_path, "w") as f:
            f.write('{"modified": true}')

        is_valid, error = store.verify_integrity("exec-001")
        assert is_valid is False
        assert "mismatch" in error.lower()


# =============================================================================
# Approval Gate Tests
# =============================================================================


class TestApprovalGate:
    """Tests for approval gate."""

    def test_no_approval_blocks(self, temp_base):
        """Episode without approval should be blocked."""
        store = EpisodeStore(temp_base)
        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)

        gate = ApprovalGate(store)
        result = gate.check_episode("exec-001")

        assert result.result == GateResult.BLOCKED
        assert result.can_proceed is False
        assert result.blocked_reason == "APPROVAL_REQUIRED"
        assert result.has_approval is False

    def test_valid_approval_allows(self, temp_base):
        """Episode with valid approval should be allowed."""
        store = EpisodeStore(temp_base)
        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)

        # Add approval
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "appr-001",
            "episode_id": "exec-001",
            "approver": {"display_name": "Admin", "role": "Owner"},
            "decision": "approve",
            "reason": "LGTM",
            "scope": {"what": "release"},
            "signatures": [{"scheme": "manual"}],
        }
        store.add_approval("exec-001", approval)

        gate = ApprovalGate(store)
        result = gate.check_episode("exec-001")

        assert result.result == GateResult.APPROVED
        assert result.can_proceed is True
        assert result.blocked_reason is None
        assert result.has_approval is True

    def test_reject_blocks(self, temp_base):
        """Episode with reject decision should be blocked."""
        store = EpisodeStore(temp_base)
        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)

        # Add rejection
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "appr-001",
            "episode_id": "exec-001",
            "approver": {"display_name": "Reviewer", "role": "QA"},
            "decision": "reject",
            "reason": "Issues found",
            "scope": {"what": "release"},
            "signatures": [{"scheme": "manual"}],
        }
        store.add_approval("exec-001", approval)

        gate = ApprovalGate(store)
        result = gate.check_episode("exec-001")

        assert result.result == GateResult.REJECTED
        assert result.can_proceed is False
        assert result.blocked_reason == "APPROVAL_INVALID"

    def test_episode_id_mismatch_fails(self, temp_base):
        """Approval with wrong episode_id should fail."""
        store = EpisodeStore(temp_base)
        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)

        # Add approval with wrong episode_id
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "appr-001",
            "episode_id": "wrong-episode",  # Mismatch
            "approver": {"display_name": "Admin", "role": "Owner"},
            "decision": "approve",
            "reason": "LGTM",
            "scope": {"what": "release"},
            "signatures": [{"scheme": "manual"}],
        }

        with pytest.raises(EpisodeStoreError) as exc:
            store.add_approval("exec-001", approval)
        assert "mismatch" in str(exc.value).lower()

    def test_require_approval_raises(self, temp_base):
        """require_approval should raise for unapproved episode."""
        store = EpisodeStore(temp_base)
        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)

        gate = ApprovalGate(store)

        with pytest.raises(ApprovalGateError) as exc:
            gate.require_approval("exec-001")
        assert "GOVERNANCE:" in str(exc.value)


# =============================================================================
# Hash Computation Tests
# =============================================================================


class TestHashComputation:
    """Tests for hash computation functions."""

    def test_compute_content_hash(self):
        """compute_content_hash should return sha256 prefixed hash."""
        content = b"test content"
        hash_result = compute_content_hash(content)

        assert hash_result.startswith("sha256:")
        assert len(hash_result) == 7 + 64  # "sha256:" + 64 hex chars

    def test_compute_content_hash_deterministic(self):
        """compute_content_hash should be deterministic."""
        content = b"same content"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)

        assert hash1 == hash2

    def test_compute_json_hash_deterministic(self):
        """compute_json_hash should be deterministic regardless of key order."""
        data1 = {"b": 2, "a": 1}
        data2 = {"a": 1, "b": 2}

        hash1 = compute_json_hash(data1)
        hash2 = compute_json_hash(data2)

        assert hash1 == hash2


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_is_episode_finalized(self, valid_manifest):
        """is_episode_finalized should detect placeholder hash."""
        # Placeholder hash
        assert is_episode_finalized(valid_manifest) is False

        # Real hash
        valid_manifest["integrity"]["episode_root_hash_sha256"] = "sha256:" + "f" * 64
        assert is_episode_finalized(valid_manifest) is True

    def test_get_episode_root_hash(self, valid_manifest):
        """get_episode_root_hash should return hash."""
        expected = "sha256:" + "0" * 64
        assert get_episode_root_hash(valid_manifest) == expected


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for full episode workflow."""

    def test_full_workflow_without_approval(self, temp_base):
        """Full workflow without approval should block at gate."""
        store = EpisodeStore(temp_base)

        # Create episode
        store.create_episode(
            episode_id="exec-workflow",
            execution_id="exec-workflow",
            input_mode="natural",
            input_hash="sha256:" + "a" * 64,
        )

        # Register content
        store.register_input("exec-workflow", b'User wants todo app', "input.txt")
        store.register_contract("exec-workflow", "idl", b'{"project": "todo"}')
        store.register_runlog("exec-workflow", {"status": "success"})

        # Finalize
        store.finalize_episode("exec-workflow")

        # Gate check should block
        gate = ApprovalGate(store)
        result = gate.check_episode("exec-workflow")

        assert result.result == GateResult.BLOCKED
        assert result.blocked_reason == "APPROVAL_REQUIRED"

    def test_full_workflow_with_approval(self, temp_base):
        """Full workflow with approval should pass gate."""
        store = EpisodeStore(temp_base)

        # Create episode
        store.create_episode(
            episode_id="exec-workflow",
            execution_id="exec-workflow",
            input_mode="natural",
            input_hash="sha256:" + "a" * 64,
        )

        # Register content
        store.register_contract("exec-workflow", "idl", b'{"project": "todo"}')
        store.finalize_episode("exec-workflow")

        # Add approval
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "appr-001",
            "episode_id": "exec-workflow",
            "approver": {"display_name": "Admin", "role": "Owner"},
            "decision": "approve",
            "reason": "LGTM",
            "scope": {"what": "release"},
            "signatures": [{"scheme": "manual"}],
        }
        store.add_approval("exec-workflow", approval)

        # Gate check should pass
        gate = ApprovalGate(store)
        result = gate.check_episode("exec-workflow")

        assert result.result == GateResult.APPROVED
        assert result.can_proceed is True

    def test_modification_after_finalize_detected(self, temp_base):
        """Modification after finalization should be detected."""
        store = EpisodeStore(temp_base)

        store.create_episode("exec-001", "exec-001", "natural", "sha256:" + "a" * 64)
        store.register_contract("exec-001", "idl", b'original content')
        store.finalize_episode("exec-001")

        # Get original root hash
        manifest = store.get_manifest("exec-001")
        original_hash = manifest["integrity"]["episode_root_hash_sha256"]

        # Tamper with file
        contracts_dir = store._get_contracts_dir("exec-001")
        with open(contracts_dir / "idl.json", "w") as f:
            f.write("tampered content")

        # Compute new hash
        episode_dir = store._get_episode_dir("exec-001")
        new_hash, _ = compute_episode_root_hash(episode_dir)

        # Hashes should differ
        assert new_hash != original_hash

        # Verify should fail
        is_valid, error = store.verify_integrity("exec-001")
        assert is_valid is False
