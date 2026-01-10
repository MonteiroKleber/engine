"""Tests for wizard_runlog.v1 schema and helpers.

Tests cover:
- Schema validation
- error_codes 1:1 with errors
- blocked_reason coherence with status
- counts/flags always present
- Helper functions
"""

import json
from pathlib import Path

import pytest

from wizard.wizard_runlog import (
    new_wizard_runlog,
    finalize_wizard_runlog,
    validate_wizard_runlog,
    compute_counts_from_session,
    compute_flags_from_session,
    WizardRunlogValidationError,
)

try:
    import jsonschema
except ImportError:
    pytest.skip("jsonschema not installed", allow_module_level=True)


# =============================================================================
# Schema Loading
# =============================================================================

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "wizard_runlog.v1.json"


@pytest.fixture
def schema():
    """Load the wizard_runlog.v1 schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


# =============================================================================
# Test new_wizard_runlog
# =============================================================================


class TestNewWizardRunlog:
    """Test new_wizard_runlog function."""

    def test_creates_valid_runlog(self):
        """[wizard_runlog] new_wizard_runlog creates valid structure."""
        runlog = new_wizard_runlog("session_001", "start")

        assert runlog["schema_version"] == "wizard_runlog.v1"
        assert runlog["session_id"] == "session_001"
        assert runlog["mode"] == "start"
        assert runlog["final_status"] == "success"
        assert runlog["blocked_reason"] is None
        assert runlog["duration_ms"] == 0
        assert runlog["errors"] == []
        assert runlog["error_codes"] == []

    def test_all_modes_valid(self):
        """[wizard_runlog] All mode values create valid runlog."""
        for mode in ["start", "resume", "export"]:
            runlog = new_wizard_runlog("session", mode)
            assert runlog["mode"] == mode
            validate_wizard_runlog(runlog)  # Should not raise

    def test_invalid_mode_raises(self):
        """[wizard_runlog] Invalid mode raises ValueError."""
        with pytest.raises(ValueError) as exc:
            new_wizard_runlog("session", "invalid_mode")
        assert "Invalid mode" in str(exc.value)

    def test_default_counts_present(self):
        """[wizard_runlog] Default counts are all zero."""
        runlog = new_wizard_runlog("session", "start")
        counts = runlog["counts"]

        assert counts["steps_total"] == 0
        assert counts["steps_complete"] == 0
        assert counts["open_questions_total"] == 0
        assert counts["open_questions_blocking"] == 0
        assert counts["evidence_total"] == 0

    def test_default_flags_present(self):
        """[wizard_runlog] Default flags are all false."""
        runlog = new_wizard_runlog("session", "start")
        flags = runlog["flags"]

        assert flags["has_blocking_open_questions"] is False
        assert flags["has_evidence"] is False


# =============================================================================
# Test finalize_wizard_runlog
# =============================================================================


class TestFinalizeWizardRunlog:
    """Test finalize_wizard_runlog function."""

    def test_finalize_success(self):
        """[wizard_runlog] Finalize with success status."""
        runlog = new_wizard_runlog("session", "start")
        finalize_wizard_runlog(
            runlog,
            status="success",
            duration_ms=150.5,
            counts={"steps_total": 5, "steps_complete": 5},
            flags={"has_evidence": True},
        )

        assert runlog["final_status"] == "success"
        assert runlog["blocked_reason"] is None
        assert runlog["duration_ms"] == 150.5
        assert runlog["counts"]["steps_total"] == 5
        assert runlog["counts"]["steps_complete"] == 5
        assert runlog["flags"]["has_evidence"] is True

    def test_finalize_blocked(self):
        """[wizard_runlog] Finalize with blocked status requires blocked_reason."""
        runlog = new_wizard_runlog("session", "export")
        finalize_wizard_runlog(
            runlog,
            status="blocked",
            duration_ms=100,
            blocked_reason="OPEN_QUESTIONS_BLOCKING",
            errors=["Has 2 blocking questions"],
            error_codes=["WIZARD_BLOCKED"],
        )

        assert runlog["final_status"] == "blocked"
        assert runlog["blocked_reason"] == "OPEN_QUESTIONS_BLOCKING"
        assert len(runlog["errors"]) == 1
        assert len(runlog["error_codes"]) == 1

    def test_finalize_invalid(self):
        """[wizard_runlog] Finalize with invalid status."""
        runlog = new_wizard_runlog("session", "start")
        finalize_wizard_runlog(
            runlog,
            status="invalid",
            duration_ms=50,
            blocked_reason="SCHEMA_INVALID",
            errors=["Session validation failed"],
            error_codes=["WIZARD_SCHEMA_INVALID"],
        )

        assert runlog["final_status"] == "invalid"
        assert runlog["blocked_reason"] == "SCHEMA_INVALID"

    def test_invalid_status_raises(self):
        """[wizard_runlog] Invalid status raises ValueError."""
        runlog = new_wizard_runlog("session", "start")
        with pytest.raises(ValueError) as exc:
            finalize_wizard_runlog(runlog, status="unknown", duration_ms=0)
        assert "Invalid status" in str(exc.value)

    def test_blocked_without_reason_raises(self):
        """[wizard_runlog] Blocked status without blocked_reason raises."""
        runlog = new_wizard_runlog("session", "start")
        with pytest.raises(ValueError) as exc:
            finalize_wizard_runlog(runlog, status="blocked", duration_ms=0)
        assert "blocked_reason is required" in str(exc.value)

    def test_success_with_reason_raises(self):
        """[wizard_runlog] Success status with blocked_reason raises."""
        runlog = new_wizard_runlog("session", "start")
        with pytest.raises(ValueError) as exc:
            finalize_wizard_runlog(
                runlog,
                status="success",
                duration_ms=0,
                blocked_reason="SCHEMA_INVALID",
            )
        assert "blocked_reason must be null" in str(exc.value)

    def test_invalid_blocked_reason_raises(self):
        """[wizard_runlog] Invalid blocked_reason raises ValueError."""
        runlog = new_wizard_runlog("session", "start")
        with pytest.raises(ValueError) as exc:
            finalize_wizard_runlog(
                runlog,
                status="blocked",
                duration_ms=0,
                blocked_reason="INVALID_REASON",
            )
        assert "Invalid blocked_reason" in str(exc.value)

    def test_all_blocked_reasons_valid(self):
        """[wizard_runlog] All valid blocked_reason values accepted."""
        for reason in ["OPEN_QUESTIONS_BLOCKING", "SCHEMA_INVALID", "INCOMPLETE_STEPS"]:
            runlog = new_wizard_runlog("session", "start")
            finalize_wizard_runlog(
                runlog, status="blocked", duration_ms=0, blocked_reason=reason
            )
            assert runlog["blocked_reason"] == reason

    def test_error_codes_1_1_with_errors(self):
        """[wizard_runlog] error_codes must match errors length."""
        runlog = new_wizard_runlog("session", "start")
        with pytest.raises(ValueError) as exc:
            finalize_wizard_runlog(
                runlog,
                status="blocked",
                duration_ms=0,
                blocked_reason="SCHEMA_INVALID",
                errors=["error1", "error2"],
                error_codes=["CODE1"],  # Mismatch!
            )
        assert "must match errors length" in str(exc.value)

    def test_counts_merged_with_defaults(self):
        """[wizard_runlog] Partial counts are merged with defaults."""
        runlog = new_wizard_runlog("session", "start")
        finalize_wizard_runlog(
            runlog,
            status="success",
            duration_ms=0,
            counts={"steps_total": 10},  # Only partial
        )

        # Provided value
        assert runlog["counts"]["steps_total"] == 10
        # Default values
        assert runlog["counts"]["steps_complete"] == 0
        assert runlog["counts"]["open_questions_total"] == 0

    def test_flags_merged_with_defaults(self):
        """[wizard_runlog] Partial flags are merged with defaults."""
        runlog = new_wizard_runlog("session", "start")
        finalize_wizard_runlog(
            runlog,
            status="success",
            duration_ms=0,
            flags={"has_evidence": True},  # Only partial
        )

        assert runlog["flags"]["has_evidence"] is True
        assert runlog["flags"]["has_blocking_open_questions"] is False


# =============================================================================
# Test validate_wizard_runlog
# =============================================================================


class TestValidateWizardRunlog:
    """Test validate_wizard_runlog function."""

    def test_valid_runlog_passes(self):
        """[wizard_runlog] Valid runlog passes validation."""
        runlog = new_wizard_runlog("session", "start")
        validate_wizard_runlog(runlog)  # Should not raise

    def test_missing_schema_version_fails(self):
        """[wizard_runlog] Missing schema_version fails with SCHEMA prefix."""
        runlog = new_wizard_runlog("session", "start")
        del runlog["schema_version"]
        with pytest.raises(WizardRunlogValidationError) as exc:
            validate_wizard_runlog(runlog)
        assert "SCHEMA:" in str(exc.value)

    def test_wrong_schema_version_fails(self):
        """[wizard_runlog] Wrong schema_version fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["schema_version"] = "wizard_runlog.v2"
        with pytest.raises(WizardRunlogValidationError) as exc:
            validate_wizard_runlog(runlog)
        assert "SCHEMA:" in str(exc.value)

    def test_invalid_mode_fails(self):
        """[wizard_runlog] Invalid mode enum fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["mode"] = "invalid"
        with pytest.raises(WizardRunlogValidationError):
            validate_wizard_runlog(runlog)

    def test_invalid_status_fails(self):
        """[wizard_runlog] Invalid final_status enum fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["final_status"] = "error"
        with pytest.raises(WizardRunlogValidationError):
            validate_wizard_runlog(runlog)

    def test_invalid_blocked_reason_fails(self):
        """[wizard_runlog] Invalid blocked_reason enum fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["final_status"] = "blocked"
        runlog["blocked_reason"] = "INVALID_REASON"
        with pytest.raises(WizardRunlogValidationError):
            validate_wizard_runlog(runlog)

    def test_error_codes_mismatch_fails(self):
        """[wizard_runlog] error_codes/errors length mismatch fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["errors"] = ["error1", "error2"]
        runlog["error_codes"] = ["CODE1"]
        with pytest.raises(WizardRunlogValidationError) as exc:
            validate_wizard_runlog(runlog)
        assert "must match errors length" in str(exc.value)

    def test_blocked_without_reason_fails(self):
        """[wizard_runlog] blocked status with null blocked_reason fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["final_status"] = "blocked"
        runlog["blocked_reason"] = None
        with pytest.raises(WizardRunlogValidationError) as exc:
            validate_wizard_runlog(runlog)
        assert "blocked_reason cannot be null" in str(exc.value)

    def test_invalid_without_reason_fails(self):
        """[wizard_runlog] invalid status with null blocked_reason fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["final_status"] = "invalid"
        runlog["blocked_reason"] = None
        with pytest.raises(WizardRunlogValidationError) as exc:
            validate_wizard_runlog(runlog)
        assert "blocked_reason cannot be null" in str(exc.value)

    def test_success_with_reason_fails(self):
        """[wizard_runlog] success status with blocked_reason fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["final_status"] = "success"
        runlog["blocked_reason"] = "SCHEMA_INVALID"
        with pytest.raises(WizardRunlogValidationError) as exc:
            validate_wizard_runlog(runlog)
        assert "blocked_reason must be null" in str(exc.value)

    def test_flags_coherence_blocking_questions(self):
        """[wizard_runlog] Flags must be coherent with counts (blocking questions)."""
        runlog = new_wizard_runlog("session", "start")
        runlog["counts"]["open_questions_blocking"] = 2
        runlog["flags"]["has_blocking_open_questions"] = False  # Incoherent!
        with pytest.raises(WizardRunlogValidationError) as exc:
            validate_wizard_runlog(runlog)
        assert "has_blocking_open_questions must be true" in str(exc.value)

    def test_flags_coherence_evidence(self):
        """[wizard_runlog] Flags must be coherent with counts (evidence)."""
        runlog = new_wizard_runlog("session", "start")
        runlog["counts"]["evidence_total"] = 3
        runlog["flags"]["has_evidence"] = False  # Incoherent!
        with pytest.raises(WizardRunlogValidationError) as exc:
            validate_wizard_runlog(runlog)
        assert "has_evidence must be true" in str(exc.value)

    def test_negative_duration_fails(self):
        """[wizard_runlog] Negative duration_ms fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["duration_ms"] = -100
        with pytest.raises(WizardRunlogValidationError):
            validate_wizard_runlog(runlog)

    def test_missing_counts_field_fails(self):
        """[wizard_runlog] Missing counts field fails."""
        runlog = new_wizard_runlog("session", "start")
        del runlog["counts"]["steps_total"]
        with pytest.raises(WizardRunlogValidationError):
            validate_wizard_runlog(runlog)

    def test_missing_flags_field_fails(self):
        """[wizard_runlog] Missing flags field fails."""
        runlog = new_wizard_runlog("session", "start")
        del runlog["flags"]["has_evidence"]
        with pytest.raises(WizardRunlogValidationError):
            validate_wizard_runlog(runlog)

    def test_extra_top_level_property_fails(self):
        """[wizard_runlog] Extra top-level property fails."""
        runlog = new_wizard_runlog("session", "start")
        runlog["extra"] = "not allowed"
        with pytest.raises(WizardRunlogValidationError):
            validate_wizard_runlog(runlog)


# =============================================================================
# Test compute_counts_from_session
# =============================================================================


class TestComputeCountsFromSession:
    """Test compute_counts_from_session function."""

    def test_empty_session(self):
        """[wizard_runlog] Empty session produces zero counts."""
        session = {"steps": [], "open_questions": [], "evidence": []}
        counts = compute_counts_from_session(session)

        assert counts["steps_total"] == 0
        assert counts["steps_complete"] == 0
        assert counts["open_questions_total"] == 0
        assert counts["open_questions_blocking"] == 0
        assert counts["evidence_total"] == 0

    def test_counts_steps(self):
        """[wizard_runlog] Counts steps correctly."""
        session = {
            "steps": [
                {"step_id": "1", "status": "complete"},
                {"step_id": "2", "status": "partial"},
                {"step_id": "3", "status": "complete"},
            ],
            "open_questions": [],
            "evidence": [],
        }
        counts = compute_counts_from_session(session)

        assert counts["steps_total"] == 3
        assert counts["steps_complete"] == 2

    def test_counts_questions(self):
        """[wizard_runlog] Counts open questions correctly."""
        session = {
            "steps": [],
            "open_questions": [
                {"question_id": "1", "severity": "blocking"},
                {"question_id": "2", "severity": "non_blocking"},
                {"question_id": "3", "severity": "blocking"},
            ],
            "evidence": [],
        }
        counts = compute_counts_from_session(session)

        assert counts["open_questions_total"] == 3
        assert counts["open_questions_blocking"] == 2

    def test_counts_evidence(self):
        """[wizard_runlog] Counts evidence correctly."""
        session = {
            "steps": [],
            "open_questions": [],
            "evidence": [
                {"evidence_id": "1"},
                {"evidence_id": "2"},
            ],
        }
        counts = compute_counts_from_session(session)

        assert counts["evidence_total"] == 2


# =============================================================================
# Test compute_flags_from_session
# =============================================================================


class TestComputeFlagsFromSession:
    """Test compute_flags_from_session function."""

    def test_empty_session(self):
        """[wizard_runlog] Empty session produces false flags."""
        session = {"steps": [], "open_questions": [], "evidence": []}
        flags = compute_flags_from_session(session)

        assert flags["has_blocking_open_questions"] is False
        assert flags["has_evidence"] is False

    def test_has_blocking_questions(self):
        """[wizard_runlog] Detects blocking questions."""
        session = {
            "open_questions": [
                {"question_id": "1", "severity": "blocking"},
            ],
            "evidence": [],
        }
        flags = compute_flags_from_session(session)

        assert flags["has_blocking_open_questions"] is True

    def test_no_blocking_questions(self):
        """[wizard_runlog] Non-blocking questions don't set flag."""
        session = {
            "open_questions": [
                {"question_id": "1", "severity": "non_blocking"},
            ],
            "evidence": [],
        }
        flags = compute_flags_from_session(session)

        assert flags["has_blocking_open_questions"] is False

    def test_has_evidence(self):
        """[wizard_runlog] Detects evidence."""
        session = {
            "open_questions": [],
            "evidence": [{"evidence_id": "1"}],
        }
        flags = compute_flags_from_session(session)

        assert flags["has_evidence"] is True


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for wizard runlog workflow."""

    def test_full_workflow_success(self):
        """[wizard_runlog] Full workflow: new -> finalize -> validate (success)."""
        runlog = new_wizard_runlog("session_123", "export")

        finalize_wizard_runlog(
            runlog,
            status="success",
            duration_ms=250,
            counts={
                "steps_total": 5,
                "steps_complete": 5,
                "evidence_total": 2,
            },
            flags={
                "has_evidence": True,
            },
        )

        validate_wizard_runlog(runlog)  # Should not raise

        assert runlog["final_status"] == "success"
        assert runlog["counts"]["steps_total"] == 5
        assert runlog["flags"]["has_evidence"] is True

    def test_full_workflow_blocked(self):
        """[wizard_runlog] Full workflow: new -> finalize -> validate (blocked)."""
        runlog = new_wizard_runlog("session_456", "export")

        finalize_wizard_runlog(
            runlog,
            status="blocked",
            duration_ms=100,
            blocked_reason="OPEN_QUESTIONS_BLOCKING",
            counts={
                "steps_total": 5,
                "steps_complete": 3,
                "open_questions_total": 2,
                "open_questions_blocking": 2,
            },
            flags={
                "has_blocking_open_questions": True,
            },
            errors=["2 blocking open questions remain"],
            error_codes=["WIZARD_BLOCKED_QUESTIONS"],
        )

        validate_wizard_runlog(runlog)  # Should not raise

        assert runlog["final_status"] == "blocked"
        assert runlog["blocked_reason"] == "OPEN_QUESTIONS_BLOCKING"
        assert len(runlog["errors"]) == 1
        assert len(runlog["error_codes"]) == 1

    def test_session_to_runlog_integration(self):
        """[wizard_runlog] Compute counts/flags from session and finalize."""
        session = {
            "schema_version": "wizard_session.v1",
            "session_id": "session_789",
            "project": {"name": "Test", "domain": "test"},
            "steps": [
                {"step_id": "1", "status": "complete", "title": "A", "fields": []},
                {"step_id": "2", "status": "partial", "title": "B", "fields": []},
            ],
            "evidence": [
                {"evidence_id": "ev1", "kind": "ddl", "path": "/a.sql"},
            ],
            "open_questions": [
                {"question_id": "q1", "question": "?", "severity": "blocking"},
            ],
        }

        counts = compute_counts_from_session(session)
        flags = compute_flags_from_session(session)

        runlog = new_wizard_runlog(session["session_id"], "export")
        finalize_wizard_runlog(
            runlog,
            status="blocked",
            duration_ms=50,
            blocked_reason="OPEN_QUESTIONS_BLOCKING",
            counts=counts,
            flags=flags,
            errors=["Blocking questions present"],
            error_codes=["WIZARD_BLOCKED"],
        )

        validate_wizard_runlog(runlog)

        assert runlog["counts"]["steps_total"] == 2
        assert runlog["counts"]["steps_complete"] == 1
        assert runlog["counts"]["open_questions_blocking"] == 1
        assert runlog["counts"]["evidence_total"] == 1
        assert runlog["flags"]["has_blocking_open_questions"] is True
        assert runlog["flags"]["has_evidence"] is True


# =============================================================================
# Episode Audit Tests
# =============================================================================


from wizard.wizard_runlog import (
    canonicalize_approval,
    compute_approval_hash,
    set_runlog_episode,
    set_runlog_episode_from_store,
)
from tempfile import TemporaryDirectory


class TestCanonicalizeApproval:
    """Test canonicalize_approval function."""

    def test_removes_volatile_section(self):
        """[wizard_runlog] Canonicalization removes volatile section."""
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "appr-001",
            "decision": "approve",
            "volatile": {
                "timestamp": "2024-01-15T10:30:00Z",
            },
        }

        canonical = canonicalize_approval(approval)
        parsed = json.loads(canonical)

        assert "volatile" not in parsed
        assert parsed["decision"] == "approve"

    def test_deterministic_key_order(self):
        """[wizard_runlog] Canonicalization produces deterministic order."""
        approval1 = {"z_field": 1, "a_field": 2, "m_field": 3}
        approval2 = {"a_field": 2, "m_field": 3, "z_field": 1}

        canonical1 = canonicalize_approval(approval1)
        canonical2 = canonicalize_approval(approval2)

        assert canonical1 == canonical2

    def test_does_not_mutate_original(self):
        """[wizard_runlog] Canonicalization does not mutate original."""
        approval = {
            "approval_id": "appr-001",
            "volatile": {"timestamp": "2024-01-15T10:30:00Z"},
        }

        canonicalize_approval(approval)

        assert "volatile" in approval  # Original unchanged


class TestComputeApprovalHash:
    """Test compute_approval_hash function."""

    def test_produces_sha256_prefix(self):
        """[wizard_runlog] Approval hash has sha256: prefix."""
        approval = {"approval_id": "appr-001", "decision": "approve"}

        hash_result = compute_approval_hash(approval)

        assert hash_result.startswith("sha256:")
        assert len(hash_result) == 7 + 64  # "sha256:" + 64 hex chars

    def test_deterministic_across_key_order(self):
        """[wizard_runlog] Same content produces same hash regardless of key order."""
        approval1 = {"z": 1, "a": 2}
        approval2 = {"a": 2, "z": 1}

        hash1 = compute_approval_hash(approval1)
        hash2 = compute_approval_hash(approval2)

        assert hash1 == hash2

    def test_volatile_excluded_from_hash(self):
        """[wizard_runlog] Volatile section is excluded from hash."""
        approval = {"approval_id": "appr-001", "decision": "approve"}
        approval_with_volatile = {
            "approval_id": "appr-001",
            "decision": "approve",
            "volatile": {"timestamp": "2024-01-15T10:30:00Z"},
        }

        hash1 = compute_approval_hash(approval)
        hash2 = compute_approval_hash(approval_with_volatile)

        assert hash1 == hash2


class TestSetRunlogEpisode:
    """Test set_runlog_episode function."""

    def test_sets_episode_without_approval(self):
        """[wizard_runlog] Episode without approval sets present=false."""
        runlog = new_wizard_runlog("session", "start")

        set_runlog_episode(
            runlog,
            episode_id="ep-001",
            manifest_path=".engine/episodes/ep-001/manifest.json",
            episode_root_hash="sha256:" + "a" * 64,
            approval=None,
        )

        assert runlog["episode"] is not None
        assert runlog["episode"]["episode_id"] == "ep-001"
        assert runlog["episode"]["approval"]["present"] is False
        assert runlog["episode"]["approval"]["decision"] is None
        assert runlog["episode"]["approval"]["approval_hash_sha256"] is None

    def test_sets_episode_with_approval(self):
        """[wizard_runlog] Episode with approval sets present=true + decision + hash."""
        runlog = new_wizard_runlog("session", "start")

        approval = {
            "schema_version": "approval.v1",
            "approval_id": "appr-001",
            "episode_id": "ep-001",
            "decision": "approve",
            "reason": "LGTM",
        }

        set_runlog_episode(
            runlog,
            episode_id="ep-001",
            manifest_path=".engine/episodes/ep-001/manifest.json",
            episode_root_hash="sha256:" + "b" * 64,
            approval=approval,
        )

        assert runlog["episode"]["approval"]["present"] is True
        assert runlog["episode"]["approval"]["decision"] == "approve"
        assert runlog["episode"]["approval"]["approval_hash_sha256"].startswith("sha256:")

    def test_sets_episode_with_reject(self):
        """[wizard_runlog] Rejected approval has decision=reject."""
        runlog = new_wizard_runlog("session", "start")

        approval = {
            "decision": "reject",
            "reason": "Issues found",
        }

        set_runlog_episode(
            runlog,
            episode_id="ep-001",
            manifest_path=".engine/episodes/ep-001/manifest.json",
            approval=approval,
        )

        assert runlog["episode"]["approval"]["present"] is True
        assert runlog["episode"]["approval"]["decision"] == "reject"

    def test_runlog_validates_with_episode(self):
        """[wizard_runlog] Runlog with episode passes schema validation."""
        runlog = new_wizard_runlog("session", "start")

        set_runlog_episode(
            runlog,
            episode_id="ep-001",
            manifest_path=".engine/episodes/ep-001/manifest.json",
            episode_root_hash="sha256:" + "c" * 64,
            approval={"decision": "approve"},
        )

        validate_wizard_runlog(runlog)  # Should not raise

    def test_runlog_validates_without_episode(self):
        """[wizard_runlog] Runlog with episode=null passes schema validation."""
        runlog = new_wizard_runlog("session", "start")
        runlog["episode"] = None

        validate_wizard_runlog(runlog)  # Should not raise


class TestSetRunlogEpisodeFromStore:
    """Test set_runlog_episode_from_store function."""

    def test_episode_not_found_sets_null(self):
        """[wizard_runlog] Non-existent episode sets episode=null."""
        from episodes import EpisodeStore

        with TemporaryDirectory() as tmpdir:
            store = EpisodeStore(Path(tmpdir))
            runlog = new_wizard_runlog("session", "start")

            set_runlog_episode_from_store(runlog, store, "nonexistent")

            assert runlog["episode"] is None

    def test_episode_without_approval(self):
        """[wizard_runlog] Episode without approval has present=false."""
        from episodes import EpisodeStore

        with TemporaryDirectory() as tmpdir:
            store = EpisodeStore(Path(tmpdir))
            store.create_episode(
                episode_id="ep-001",
                execution_id="ep-001",
                input_mode="natural",
                input_hash="sha256:" + "a" * 64,
            )

            runlog = new_wizard_runlog("session", "start")
            set_runlog_episode_from_store(runlog, store, "ep-001")

            assert runlog["episode"] is not None
            assert runlog["episode"]["episode_id"] == "ep-001"
            assert runlog["episode"]["approval"]["present"] is False
            assert runlog["episode"]["approval"]["decision"] is None

    def test_episode_with_approval(self):
        """[wizard_runlog] Episode with approval has present=true + hash."""
        from episodes import EpisodeStore
        from approvals.approval_v1 import create_approval

        with TemporaryDirectory() as tmpdir:
            store = EpisodeStore(Path(tmpdir))
            store.create_episode(
                episode_id="ep-002",
                execution_id="ep-002",
                input_mode="natural",
                input_hash="sha256:" + "b" * 64,
            )

            approval = create_approval(
                approval_id="appr-001",
                episode_id="ep-002",
                approver_name="Admin",
                approver_role="Owner",
                decision="approve",
                reason="LGTM",
                scope_what="release",
            )
            store.add_approval("ep-002", approval)

            runlog = new_wizard_runlog("session", "start")
            set_runlog_episode_from_store(runlog, store, "ep-002")

            assert runlog["episode"]["approval"]["present"] is True
            assert runlog["episode"]["approval"]["decision"] == "approve"
            assert runlog["episode"]["approval"]["approval_hash_sha256"].startswith("sha256:")

    def test_finalized_episode_has_root_hash(self):
        """[wizard_runlog] Finalized episode includes root hash."""
        from episodes import EpisodeStore

        with TemporaryDirectory() as tmpdir:
            store = EpisodeStore(Path(tmpdir))
            store.create_episode(
                episode_id="ep-003",
                execution_id="ep-003",
                input_mode="natural",
                input_hash="sha256:" + "c" * 64,
            )
            store.finalize_episode("ep-003")

            runlog = new_wizard_runlog("session", "start")
            set_runlog_episode_from_store(runlog, store, "ep-003")

            assert runlog["episode"]["episode_root_hash_sha256"] is not None
            assert runlog["episode"]["episode_root_hash_sha256"].startswith("sha256:")

    def test_unfinalized_episode_has_null_root_hash(self):
        """[wizard_runlog] Unfinalized episode has null root hash."""
        from episodes import EpisodeStore

        with TemporaryDirectory() as tmpdir:
            store = EpisodeStore(Path(tmpdir))
            store.create_episode(
                episode_id="ep-004",
                execution_id="ep-004",
                input_mode="natural",
                input_hash="sha256:" + "d" * 64,
            )
            # Not finalized

            runlog = new_wizard_runlog("session", "start")
            set_runlog_episode_from_store(runlog, store, "ep-004")

            assert runlog["episode"]["episode_root_hash_sha256"] is None


class TestEpisodeApprovalBlockedReason:
    """Test approval blocked reasons in finalize."""

    def test_approval_required_blocked(self):
        """[wizard_runlog] APPROVAL_REQUIRED is valid blocked_reason."""
        runlog = new_wizard_runlog("session", "start")
        finalize_wizard_runlog(
            runlog,
            status="blocked",
            duration_ms=100,
            blocked_reason="APPROVAL_REQUIRED",
            errors=["Approval required before release"],
            error_codes=["APPROVAL_REQUIRED"],
        )

        assert runlog["blocked_reason"] == "APPROVAL_REQUIRED"
        validate_wizard_runlog(runlog)  # Should not raise

    def test_approval_invalid_blocked(self):
        """[wizard_runlog] APPROVAL_INVALID is valid blocked_reason."""
        runlog = new_wizard_runlog("session", "start")
        finalize_wizard_runlog(
            runlog,
            status="blocked",
            duration_ms=100,
            blocked_reason="APPROVAL_INVALID",
            errors=["Approval was rejected"],
            error_codes=["APPROVAL_INVALID"],
        )

        assert runlog["blocked_reason"] == "APPROVAL_INVALID"
        validate_wizard_runlog(runlog)  # Should not raise
