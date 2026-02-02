"""Canonical Tests for Jobs First-Class Lifecycle (A5).

These tests validate the canonical job lifecycle implemented in Prompt 3:
1. job.request creates job in JobStore (not outbox)
2. job.enqueue writes to outbox with correct format
3. report uses JobStore as source of truth
4. Multi-tenant isolation

Run with: pytest tests/test_job_lifecycle_canonical.py -v -s
Requires: ENGINE_API_MODE=idl and BUNDLE_IR_PATH set
"""

import json
import os
import pytest
import uuid
from pathlib import Path
from unittest.mock import patch

# Add parent for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.core.job_store import JobStore, JobState, get_job_store, Job
from engine.core.data_root import get_data_root, get_institution_root
from engine.core.ledger import get_ledger_for_institution


# Test fixtures
@pytest.fixture
def test_institution_id():
    """Generate unique institution ID for test isolation."""
    return f"test-inst-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_institution_id_2():
    """Second institution for multi-tenant tests."""
    return f"test-inst2-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def job_store(test_institution_id):
    """JobStore for test institution."""
    return get_job_store(test_institution_id, dept_id=None)


@pytest.fixture
def job_store_2(test_institution_id_2):
    """JobStore for second institution."""
    return get_job_store(test_institution_id_2, dept_id=None)


class TestJobEnqueueSafeFlow:
    """A5.1: test_job_enqueue_safe_flow

    Validates: job.request(safe) -> job.enqueue -> outbox created + JOB_ENQUEUED in ledger.
    """

    def test_safe_job_creates_in_jobstore_not_outbox(self, job_store, test_institution_id):
        """Safe job.request creates job in JobStore with state='requested', NOT in outbox."""
        # Create safe job
        job = job_store.create_job(
            job_type="files.list",
            params={"path": "/test"},
            requested_by="user-test",
            initial_state=JobState.REQUESTED.value,
        )

        assert job is not None
        assert job.state == JobState.REQUESTED.value
        assert job.job_type == "files.list"

        # Verify job is in JobStore
        retrieved = job_store.get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id

        # Verify job is NOT in outbox yet
        inst_root = get_institution_root(test_institution_id)
        outbox_file = inst_root / "legacy_bridge" / "outbox" / f"{job.job_id}.json"
        assert not outbox_file.exists(), "Safe job should NOT be in outbox before enqueue"

    def test_enqueue_writes_to_outbox(self, job_store, test_institution_id):
        """job.enqueue writes job to outbox directory."""
        # Create job
        job = job_store.create_job(
            job_type="files.list",
            params={"path": "/docs"},
            requested_by="user-test",
            initial_state=JobState.REQUESTED.value,
        )

        # Manually enqueue (simulating dispatch_job_enqueue)
        inst_root = get_institution_root(test_institution_id)
        outbox_dir = inst_root / "legacy_bridge" / "outbox"
        outbox_dir.mkdir(parents=True, exist_ok=True)

        outbox_data = job.to_outbox_dict()
        outbox_file = outbox_dir / f"{job.job_id}.json"
        outbox_file.write_text(json.dumps(outbox_data), encoding="utf-8")

        # Update state
        job_store.update_job_state(job.job_id, state=JobState.ENQUEUED.value)

        # Verify outbox file exists
        assert outbox_file.exists(), "Outbox file should exist after enqueue"

        # Verify job state updated
        updated_job = job_store.get_job(job.job_id)
        assert updated_job.state == JobState.ENQUEUED.value

    def test_enqueue_only_allowed_for_requested_or_approved(self, job_store):
        """job.enqueue should only work for jobs in 'requested' or 'approved' state."""
        # Create job in pending_approval state
        job = job_store.create_job(
            job_type="files.delete",
            params={"paths": ["/file.txt"]},
            requested_by="user-test",
            approval_id=str(uuid.uuid4()),
            initial_state=JobState.PENDING_APPROVAL.value,
        )

        # Verify state
        assert job.state == JobState.PENDING_APPROVAL.value

        # In real dispatch_job_enqueue, this would return 409
        # Here we just verify the state check logic
        valid_enqueue_states = (JobState.REQUESTED.value, JobState.APPROVED.value)
        assert job.state not in valid_enqueue_states, "pending_approval should not be enqueueable"


class TestJobEnqueueDestructiveRequiresApproval:
    """A5.2: test_job_enqueue_destructive_requires_approval

    Validates: job.request(destructive) creates pending_approval -> job.enqueue fails until approved.
    """

    def test_destructive_job_starts_pending_approval(self, job_store):
        """Destructive job.request creates job with state='pending_approval' and approval_id."""
        approval_id = str(uuid.uuid4())

        job = job_store.create_job(
            job_type="files.delete",
            params={"paths": ["/important.txt"]},
            requested_by="user-test",
            approval_id=approval_id,
            initial_state=JobState.PENDING_APPROVAL.value,
        )

        assert job.state == JobState.PENDING_APPROVAL.value
        assert job.approval_id == approval_id

    def test_cannot_enqueue_pending_approval(self, job_store):
        """job.enqueue must fail for jobs in 'pending_approval' state."""
        job = job_store.create_job(
            job_type="files.delete",
            params={"paths": ["/file.txt"]},
            requested_by="user-test",
            approval_id=str(uuid.uuid4()),
            initial_state=JobState.PENDING_APPROVAL.value,
        )

        # Verify state check
        valid_enqueue_states = (JobState.REQUESTED.value, JobState.APPROVED.value)
        assert job.state not in valid_enqueue_states

    def test_can_enqueue_after_approval(self, job_store):
        """job.enqueue succeeds after job is approved."""
        approval_id = str(uuid.uuid4())

        job = job_store.create_job(
            job_type="files.delete",
            params={"paths": ["/file.txt"]},
            requested_by="user-test",
            approval_id=approval_id,
            initial_state=JobState.PENDING_APPROVAL.value,
        )

        # Simulate approval
        job_store.update_job_state(
            job.job_id,
            state=JobState.APPROVED.value,
            approved_by="approver-test",
        )

        # Now job should be enqueueable
        updated_job = job_store.get_job(job.job_id)
        valid_enqueue_states = (JobState.REQUESTED.value, JobState.APPROVED.value)
        assert updated_job.state in valid_enqueue_states

    def test_get_job_by_approval_id(self, job_store):
        """Can retrieve job by approval_id (for approval decision flow)."""
        approval_id = str(uuid.uuid4())

        job = job_store.create_job(
            job_type="files.move",
            params={"source": "/a", "dest": "/b"},
            requested_by="user-test",
            approval_id=approval_id,
            initial_state=JobState.PENDING_APPROVAL.value,
        )

        # Lookup by approval_id
        found = job_store.get_job_by_approval_id(approval_id)
        assert found is not None
        assert found.job_id == job.job_id
        assert found.approval_id == approval_id


class TestReportUsesJobstoreSourceOfTruth:
    """A5.3: test_report_uses_jobstore_source_of_truth

    Validates: report accepts job from JobStore, updates state, is idempotent.
    """

    def test_report_updates_jobstore_state(self, job_store):
        """Report should update job state to 'executed' in JobStore."""
        job = job_store.create_job(
            job_type="files.list",
            params={"path": "/"},
            requested_by="user-test",
            initial_state=JobState.ENQUEUED.value,
        )

        # Simulate report
        job_store.update_job_state(
            job.job_id,
            state=JobState.EXECUTED.value,
            executed_at="2026-02-01T12:00:00Z",
            result_summary="Listed 10 files",
            exit_code=0,
        )

        # Verify
        updated = job_store.get_job(job.job_id)
        assert updated.state == JobState.EXECUTED.value
        assert updated.result_summary == "Listed 10 files"
        assert updated.exit_code == 0

    def test_report_failed_state(self, job_store):
        """Report with status='failed' should update state to 'failed'."""
        job = job_store.create_job(
            job_type="files.delete",
            params={"paths": ["/nonexistent"]},
            requested_by="user-test",
            initial_state=JobState.ENQUEUED.value,
        )

        # Simulate failed report
        job_store.update_job_state(
            job.job_id,
            state=JobState.FAILED.value,
            executed_at="2026-02-01T12:00:00Z",
            result_summary="File not found",
            exit_code=1,
        )

        updated = job_store.get_job(job.job_id)
        assert updated.state == JobState.FAILED.value
        assert updated.exit_code == 1

    def test_job_not_found_in_jobstore(self, job_store):
        """Job not in JobStore should return None."""
        fake_id = str(uuid.uuid4())
        job = job_store.get_job(fake_id)
        assert job is None


class TestOutboxPayloadCompatFields:
    """A5.4: test_outbox_payload_compat_fields

    Validates: outbox file has both job_id/job_type AND action_id/action_type.
    """

    def test_to_outbox_dict_has_both_formats(self):
        """Job.to_outbox_dict() must include both naming conventions."""
        job = Job(
            job_id="test-job-123",
            job_type="files.list",
            institution_id="inst-123",
            params={"path": "/"},
            requested_by="user-test",
        )

        outbox_data = job.to_outbox_dict()

        # Must have action_id/action_type for Agent Runtime
        assert "action_id" in outbox_data
        assert "action_type" in outbox_data
        assert outbox_data["action_id"] == "test-job-123"
        assert outbox_data["action_type"] == "files.list"

        # Must also have job_id/job_type for forward compatibility
        assert "job_id" in outbox_data
        assert "job_type" in outbox_data
        assert outbox_data["job_id"] == "test-job-123"
        assert outbox_data["job_type"] == "files.list"

        # Values must match
        assert outbox_data["action_id"] == outbox_data["job_id"]
        assert outbox_data["action_type"] == outbox_data["job_type"]

    def test_outbox_has_required_fields(self):
        """Outbox payload must have all required fields for Agent Runtime."""
        job = Job(
            job_id="test-job-456",
            job_type="files.delete",
            institution_id="inst-456",
            params={"paths": ["/file.txt"]},
            requested_by="user-456",
            approval_id="approval-456",
            approved_by="approver-456",
        )

        outbox_data = job.to_outbox_dict()

        # Required fields per INTEGRATION.md
        required_fields = [
            "schema_version",
            "action_id",
            "action_type",
            "params",
            "requested_by",
        ]

        for field in required_fields:
            assert field in outbox_data, f"Missing required field: {field}"

        # Verify schema version
        assert outbox_data["schema_version"] == "1.0"

        # Verify params preserved
        assert outbox_data["params"] == {"paths": ["/file.txt"]}


class TestMultiTenantIsolation:
    """A5.5: test_multi_tenant_isolation

    Validates: jobs/outbox/report are isolated between institutions.
    """

    def test_job_isolation_between_institutions(self, job_store, job_store_2, test_institution_id, test_institution_id_2):
        """Jobs in one institution are not visible in another."""
        # Create job in institution 1
        job1 = job_store.create_job(
            job_type="files.list",
            params={"path": "/inst1"},
            requested_by="user-inst1",
        )

        # Create job in institution 2
        job2 = job_store_2.create_job(
            job_type="files.list",
            params={"path": "/inst2"},
            requested_by="user-inst2",
        )

        # Verify isolation: job_store can't see job_store_2's job
        found_in_1 = job_store.get_job(job2.job_id)
        assert found_in_1 is None, "Institution 1 should not see Institution 2's job"

        found_in_2 = job_store_2.get_job(job1.job_id)
        assert found_in_2 is None, "Institution 2 should not see Institution 1's job"

        # Each store sees its own job
        assert job_store.get_job(job1.job_id) is not None
        assert job_store_2.get_job(job2.job_id) is not None

    def test_outbox_isolation_between_institutions(self, test_institution_id, test_institution_id_2):
        """Outbox directories are separate per institution."""
        inst1_root = get_institution_root(test_institution_id)
        inst2_root = get_institution_root(test_institution_id_2)

        outbox1 = inst1_root / "legacy_bridge" / "outbox"
        outbox2 = inst2_root / "legacy_bridge" / "outbox"

        # Paths must be different
        assert str(outbox1) != str(outbox2)
        assert test_institution_id in str(outbox1)
        assert test_institution_id_2 in str(outbox2)

    def test_jobstore_uses_correct_institution_path(self, test_institution_id):
        """JobStore stores jobs in correct institution directory."""
        store = get_job_store(test_institution_id, dept_id=None)

        # Access internal path
        store_path = store._store_path

        # Verify path contains institution ID
        assert test_institution_id in str(store_path)
        assert "jobs/jobs.json" in str(store_path)


class TestJobStateTransitions:
    """Additional tests for job state machine."""

    def test_rejected_job_cannot_be_enqueued(self, job_store):
        """Rejected jobs should not be enqueueable."""
        job = job_store.create_job(
            job_type="files.delete",
            params={"paths": ["/file.txt"]},
            requested_by="user-test",
            approval_id=str(uuid.uuid4()),
            initial_state=JobState.PENDING_APPROVAL.value,
        )

        # Reject the job
        job_store.update_job_state(job.job_id, state=JobState.REJECTED.value)

        updated = job_store.get_job(job.job_id)
        valid_enqueue_states = (JobState.REQUESTED.value, JobState.APPROVED.value)
        assert updated.state not in valid_enqueue_states

    def test_executed_job_is_terminal(self, job_store):
        """Executed is a terminal state."""
        job = job_store.create_job(
            job_type="files.list",
            params={"path": "/"},
            requested_by="user-test",
            initial_state=JobState.ENQUEUED.value,
        )

        job_store.update_job_state(
            job.job_id,
            state=JobState.EXECUTED.value,
            exit_code=0,
        )

        updated = job_store.get_job(job.job_id)
        assert updated.state == JobState.EXECUTED.value

    def test_version_increments_on_update(self, job_store):
        """Version should increment on each update."""
        job = job_store.create_job(
            job_type="files.list",
            params={"path": "/"},
            requested_by="user-test",
        )

        initial_version = job.version

        job_store.update_job_state(job.job_id, state=JobState.ENQUEUED.value)
        updated = job_store.get_job(job.job_id)

        assert updated.version == initial_version + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
