"""Tests for Episode Chaining (FASE 7 / E7.3).

Tests:
1. Execução change gera novo episódio com manifest contendo previous_episode_id + change_request_id
2. CR inválido => falha SCHEMA com error_code adequado
3. CR.previous_episode_id diferente do argumento => falha INTEGRITY (CR_PREVIOUS_MISMATCH)
4. RunLog final inclui bloco change_request
5. Determinismo: cr_hash_sha256 é do JSON canonical, e muda apenas quando conteúdo não-volátil muda
"""

import json
import pytest
import tempfile
from pathlib import Path

from episodes.episode_store import (
    EpisodeStore,
    compute_content_hash,
    CHANGE_REQUEST_DIR,
    CHANGE_REQUEST_FILENAME,
)
from episodes.change_cli import (
    cmd_change,
    create_change_runlog,
    finalize_change_runlog,
    ChangeResult,
)
from change_requests.cr_v1 import (
    create_cr,
    validate_cr,
    canonicalize_cr,
    cr_hash_sha256,
    CRValidationError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_store():
    """Create a temporary episode store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield EpisodeStore(Path(tmpdir))


@pytest.fixture
def sample_cr():
    """Create a sample change request."""
    return create_cr(
        change_request_id="cr-001",
        previous_episode_id="exec-001",
        requester_name="John Doe",
        requester_role="Developer",
        reason="Add new feature",
        target="backend",
        summary="Add user authentication",
        risk_level="low",
        entities_affected=["User", "Session"],
        usecases_affected=["UC-Login"],
        invariants=[{
            "name": "password_hashed",
            "description": "Passwords must be hashed",
            "severity": "must",
        }],
        acceptance_criteria=["Users can log in", "Users can log out"],
    )


@pytest.fixture
def previous_episode(temp_store):
    """Create a previous episode to chain from."""
    episode_id = "exec-001"
    temp_store.create_episode(
        episode_id=episode_id,
        execution_id=episode_id,
        input_mode="natural",
        input_hash="sha256:" + "a" * 64,
    )
    return episode_id


@pytest.fixture
def cr_file(sample_cr, tmp_path):
    """Create a CR file."""
    cr_path = tmp_path / "change_request.json"
    with open(cr_path, "w") as f:
        json.dump(sample_cr, f)
    return cr_path


# =============================================================================
# Test: Episode Chaining Creates Linked Episode
# =============================================================================


class TestEpisodeChainingCreatesLinkedEpisode:
    """Test that change execution creates a new episode with proper links."""

    def test_change_creates_episode_with_previous_episode_id(
        self, temp_store, previous_episode, sample_cr, tmp_path
    ):
        """Change execution creates episode with previous_episode_id in manifest."""
        # Create CR file
        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(sample_cr, f)

        # Execute change
        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert result.success
        assert result.episode_id is not None

        # Check manifest has previous_episode_id
        manifest = temp_store.get_manifest(result.episode_id)
        assert manifest["links"]["previous_episode_id"] == previous_episode

    def test_change_creates_episode_with_change_request_id(
        self, temp_store, previous_episode, sample_cr, tmp_path
    ):
        """Change execution creates episode with change_request_id in manifest."""
        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(sample_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert result.success

        manifest = temp_store.get_manifest(result.episode_id)
        assert manifest["links"]["change_request_id"] == sample_cr["change_request_id"]

    def test_change_creates_episode_with_cr_hash(
        self, temp_store, previous_episode, sample_cr, tmp_path
    ):
        """Change execution creates episode with cr_hash_sha256 in manifest."""
        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(sample_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert result.success

        manifest = temp_store.get_manifest(result.episode_id)
        expected_hash = cr_hash_sha256(sample_cr)
        assert manifest["links"]["cr_hash_sha256"] == expected_hash

    def test_change_stores_cr_in_episode(
        self, temp_store, previous_episode, sample_cr, tmp_path
    ):
        """Change execution stores the CR in the episode's change_request directory."""
        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(sample_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert result.success

        # Check CR is stored
        stored_cr = temp_store.get_change_request(result.episode_id)
        assert stored_cr is not None
        assert stored_cr["change_request_id"] == sample_cr["change_request_id"]


# =============================================================================
# Test: CR Validation Errors
# =============================================================================


class TestCRValidationErrors:
    """Test that invalid CRs fail with SCHEMA prefix."""

    def test_invalid_cr_missing_field_fails_schema(self, temp_store, previous_episode, tmp_path):
        """Invalid CR missing required field fails with SCHEMA error."""
        invalid_cr = {
            "schema_version": "idl_change_request.v1",
            "change_request_id": "cr-001",
            # Missing previous_episode_id and other required fields
        }

        cr_path = tmp_path / "invalid_cr.json"
        with open(cr_path, "w") as f:
            json.dump(invalid_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert not result.success
        assert "CR_SCHEMA_INVALID" in result.error_codes
        assert any("SCHEMA:" in e for e in result.errors)

    def test_invalid_cr_wrong_schema_version_fails(self, temp_store, previous_episode, tmp_path):
        """CR with wrong schema_version fails validation."""
        invalid_cr = {
            "schema_version": "wrong.version",
            "change_request_id": "cr-001",
            "previous_episode_id": previous_episode,
        }

        cr_path = tmp_path / "invalid_cr.json"
        with open(cr_path, "w") as f:
            json.dump(invalid_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert not result.success
        assert "CR_SCHEMA_INVALID" in result.error_codes

    def test_cr_file_not_found_fails(self, temp_store, previous_episode, tmp_path):
        """Non-existent CR file fails appropriately."""
        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=tmp_path / "nonexistent.json",
            base_path=temp_store.base_path,
        )

        assert not result.success
        assert "CR_NOT_FOUND" in result.error_codes


# =============================================================================
# Test: CR Previous Episode Mismatch
# =============================================================================


class TestCRPreviousEpisodeMismatch:
    """Test that CR.previous_episode_id mismatch is detected."""

    def test_cr_previous_mismatch_fails_integrity(self, temp_store, previous_episode, tmp_path):
        """CR with different previous_episode_id fails with INTEGRITY prefix."""
        mismatched_cr = create_cr(
            change_request_id="cr-001",
            previous_episode_id="different-episode",  # Mismatch!
            requester_name="John Doe",
            requester_role="Developer",
            reason="Add feature",
            target="backend",
            summary="Add feature",
        )

        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(mismatched_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,  # exec-001
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert not result.success
        assert "CR_PREVIOUS_MISMATCH" in result.error_codes
        assert any("INTEGRITY:" in e for e in result.errors)

    def test_cr_previous_mismatch_error_includes_both_ids(
        self, temp_store, previous_episode, tmp_path
    ):
        """CR previous mismatch error includes both expected and actual IDs."""
        mismatched_cr = create_cr(
            change_request_id="cr-001",
            previous_episode_id="wrong-episode",
            requester_name="John Doe",
            requester_role="Developer",
            reason="Add feature",
            target="backend",
            summary="Add feature",
        )

        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(mismatched_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert not result.success
        # Check error message contains both IDs
        error_msg = result.errors[0]
        assert "wrong-episode" in error_msg
        assert previous_episode in error_msg


# =============================================================================
# Test: RunLog Contains Change Request Block
# =============================================================================


class TestRunLogContainsChangeRequestBlock:
    """Test that the runlog includes the change_request block."""

    def test_runlog_has_change_request_block(
        self, temp_store, previous_episode, sample_cr, tmp_path
    ):
        """RunLog includes change_request with all required fields."""
        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(sample_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert result.success

        # Read runlog from episode
        runlog_path = temp_store._get_runlog_path(result.episode_id)
        with open(runlog_path) as f:
            runlog = json.load(f)

        # Check change_request block
        assert "change_request" in runlog
        assert runlog["change_request"] is not None
        assert runlog["change_request"]["change_request_id"] == sample_cr["change_request_id"]
        assert runlog["change_request"]["previous_episode_id"] == previous_episode
        assert runlog["change_request"]["cr_hash_sha256"] == cr_hash_sha256(sample_cr)

    def test_create_change_runlog_includes_cr_info(self):
        """create_change_runlog function includes change_request block."""
        runlog = create_change_runlog(
            execution_id="exec-002",
            change_request_id="cr-001",
            previous_episode_id="exec-001",
            cr_hash="sha256:" + "a" * 64,
        )

        assert runlog["change_request"]["change_request_id"] == "cr-001"
        assert runlog["change_request"]["previous_episode_id"] == "exec-001"
        assert runlog["change_request"]["cr_hash_sha256"] == "sha256:" + "a" * 64


# =============================================================================
# Test: Determinism - CR Hash Changes Only on Non-Volatile Content
# =============================================================================


class TestCRHashDeterminism:
    """Test that cr_hash_sha256 is deterministic and ignores volatile."""

    def test_cr_hash_is_deterministic(self, sample_cr):
        """Same CR produces same hash."""
        hash1 = cr_hash_sha256(sample_cr)
        hash2 = cr_hash_sha256(sample_cr)
        assert hash1 == hash2

    def test_cr_hash_ignores_volatile(self, sample_cr):
        """CR hash excludes volatile section."""
        from copy import deepcopy

        cr_with_volatile = deepcopy(sample_cr)
        cr_with_volatile["volatile"] = {
            "timestamp": "2024-01-01T00:00:00Z",
        }

        cr_different_volatile = deepcopy(sample_cr)
        cr_different_volatile["volatile"] = {
            "timestamp": "2025-01-01T12:00:00Z",  # Different timestamp
        }

        hash1 = cr_hash_sha256(sample_cr)
        hash2 = cr_hash_sha256(cr_with_volatile)
        hash3 = cr_hash_sha256(cr_different_volatile)

        # All should be the same since volatile is excluded
        assert hash1 == hash2 == hash3

    def test_cr_hash_changes_on_content_change(self, sample_cr):
        """CR hash changes when non-volatile content changes."""
        from copy import deepcopy

        modified_cr = deepcopy(sample_cr)
        modified_cr["reason"] = "Different reason"

        hash1 = cr_hash_sha256(sample_cr)
        hash2 = cr_hash_sha256(modified_cr)

        assert hash1 != hash2

    def test_cr_hash_stable_across_field_order(self, sample_cr):
        """CR hash is stable regardless of field order in input."""
        from copy import deepcopy
        import json

        # Create CR with different field order
        cr_reordered = json.loads(
            json.dumps(sample_cr, sort_keys=True)
        )

        hash1 = cr_hash_sha256(sample_cr)
        hash2 = cr_hash_sha256(cr_reordered)

        assert hash1 == hash2

    def test_cr_hash_stable_across_array_order(self, sample_cr):
        """CR hash is stable with sorted arrays (canonical form)."""
        from copy import deepcopy

        # Create CR with reversed entities order
        cr_reversed = deepcopy(sample_cr)
        cr_reversed["scope"]["entities_affected"] = ["Session", "User"]  # Reversed

        hash1 = cr_hash_sha256(sample_cr)
        hash2 = cr_hash_sha256(cr_reversed)

        # Should be equal because canonicalization sorts arrays
        assert hash1 == hash2


# =============================================================================
# Test: Episode Store Change Request Methods
# =============================================================================


class TestEpisodeStoreChangeRequestMethods:
    """Test the Episode Store methods for change requests."""

    def test_register_change_request_creates_directory(self, temp_store):
        """register_change_request creates the change_request directory."""
        episode_id = "exec-001"
        temp_store.create_episode(
            episode_id=episode_id,
            execution_id=episode_id,
            input_mode="idl",
            input_hash="sha256:" + "a" * 64,
        )

        cr = create_cr(
            change_request_id="cr-001",
            previous_episode_id="exec-000",
            requester_name="John",
            requester_role="Dev",
            reason="Test",
            target="backend",
            summary="Test change",
        )

        temp_store.register_change_request(episode_id, cr)

        cr_dir = temp_store._get_change_request_dir(episode_id)
        assert cr_dir.exists()

    def test_register_change_request_stores_file(self, temp_store):
        """register_change_request stores the CR file."""
        episode_id = "exec-001"
        temp_store.create_episode(
            episode_id=episode_id,
            execution_id=episode_id,
            input_mode="idl",
            input_hash="sha256:" + "a" * 64,
        )

        cr = create_cr(
            change_request_id="cr-001",
            previous_episode_id="exec-000",
            requester_name="John",
            requester_role="Dev",
            reason="Test",
            target="backend",
            summary="Test change",
        )

        temp_store.register_change_request(episode_id, cr)

        cr_path = temp_store._get_change_request_path(episode_id)
        assert cr_path.exists()

    def test_get_change_request_returns_stored_cr(self, temp_store):
        """get_change_request returns the stored CR."""
        episode_id = "exec-001"
        temp_store.create_episode(
            episode_id=episode_id,
            execution_id=episode_id,
            input_mode="idl",
            input_hash="sha256:" + "a" * 64,
        )

        cr = create_cr(
            change_request_id="cr-001",
            previous_episode_id="exec-000",
            requester_name="John",
            requester_role="Dev",
            reason="Test",
            target="backend",
            summary="Test change",
        )

        temp_store.register_change_request(episode_id, cr)

        retrieved_cr = temp_store.get_change_request(episode_id)
        assert retrieved_cr["change_request_id"] == cr["change_request_id"]

    def test_get_change_request_returns_none_if_not_exists(self, temp_store):
        """get_change_request returns None if no CR exists."""
        episode_id = "exec-001"
        temp_store.create_episode(
            episode_id=episode_id,
            execution_id=episode_id,
            input_mode="idl",
            input_hash="sha256:" + "a" * 64,
        )

        assert temp_store.get_change_request(episode_id) is None


# =============================================================================
# Test: Dry Run Mode
# =============================================================================


class TestDryRunMode:
    """Test the dry-run mode of change command."""

    def test_dry_run_validates_without_creating_episode(
        self, temp_store, previous_episode, sample_cr, tmp_path
    ):
        """Dry run validates but doesn't create episode."""
        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(sample_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
            dry_run=True,
        )

        assert result.success
        assert result.data["dry_run"] is True
        assert result.episode_id is None

        # Episode should not exist
        would_be_id = result.data["would_create_episode_id"]
        assert not temp_store.exists(would_be_id)

    def test_dry_run_reports_validation_errors(
        self, temp_store, previous_episode, tmp_path
    ):
        """Dry run reports validation errors."""
        mismatched_cr = create_cr(
            change_request_id="cr-001",
            previous_episode_id="wrong-episode",
            requester_name="John",
            requester_role="Dev",
            reason="Test",
            target="backend",
            summary="Test",
        )

        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(mismatched_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
            dry_run=True,  # Still fails validation
        )

        assert not result.success
        assert "CR_PREVIOUS_MISMATCH" in result.error_codes


# =============================================================================
# Test: Previous Episode Not Found
# =============================================================================


class TestPreviousEpisodeNotFound:
    """Test behavior when previous episode doesn't exist."""

    def test_previous_episode_not_found_fails(self, temp_store, tmp_path):
        """Change fails if previous episode doesn't exist."""
        cr = create_cr(
            change_request_id="cr-001",
            previous_episode_id="nonexistent",
            requester_name="John",
            requester_role="Dev",
            reason="Test",
            target="backend",
            summary="Test",
        )

        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(cr, f)

        result = cmd_change(
            previous_episode_id="nonexistent",
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert not result.success
        assert "PREVIOUS_EPISODE_NOT_FOUND" in result.error_codes
        assert any("GOVERNANCE:" in e for e in result.errors)


# =============================================================================
# Test: Runlog Schema Validation
# =============================================================================


class TestRunlogSchemaValidation:
    """Test that runlog conforms to schema."""

    def test_runlog_has_required_fields(self, temp_store, previous_episode, sample_cr, tmp_path):
        """Runlog has all required fields."""
        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(sample_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        assert result.success

        runlog_path = temp_store._get_runlog_path(result.episode_id)
        with open(runlog_path) as f:
            runlog = json.load(f)

        # Check required fields
        assert "schema_version" in runlog
        assert runlog["schema_version"] == "runlog.v1"
        assert "execution_id" in runlog
        assert "final_status" in runlog
        assert "duration_ms" in runlog

    def test_runlog_change_request_block_complete(
        self, temp_store, previous_episode, sample_cr, tmp_path
    ):
        """Runlog change_request block has all required fields."""
        cr_path = tmp_path / "cr.json"
        with open(cr_path, "w") as f:
            json.dump(sample_cr, f)

        result = cmd_change(
            previous_episode_id=previous_episode,
            cr_path=cr_path,
            base_path=temp_store.base_path,
        )

        runlog_path = temp_store._get_runlog_path(result.episode_id)
        with open(runlog_path) as f:
            runlog = json.load(f)

        cr_block = runlog["change_request"]
        assert "change_request_id" in cr_block
        assert "previous_episode_id" in cr_block
        assert "cr_hash_sha256" in cr_block
        assert cr_block["cr_hash_sha256"].startswith("sha256:")
