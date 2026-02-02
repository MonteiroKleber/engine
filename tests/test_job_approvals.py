"""Tests for job-based approvals (Jobs First-Class spec).

Tests the generic approval flow for job_ref targets:
- Job request creates APPROVAL_REQUESTED with target_kind: "job"
- Approving releases job.enqueue (writes to outbox)
- Rejecting sets job state to REJECTED
"""

import pytest
import uuid
from pathlib import Path
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport

from engine.api.server import app
from engine.core.actor_context import ActorContext
from engine.core.approvals import (
    ApprovalTargetKind,
    JobRef,
    ApprovalTarget,
    emit_approval_requested_generic,
    extract_target_from_event,
    get_job_ref_from_approval,
    find_approval_requested,
    reset_all_approvals,
)
from engine.core.job_store import Job, JobState, JobStore, get_job_store
from engine.core.ledger import AuditLedger, set_ledger, get_ledger, reset_institution_ledgers
from engine.core.institution_context import DEFAULT_INSTITUTION_ID
from engine.core.state_store import reset_all_state_stores


@pytest.fixture
def actor():
    """Create a test actor."""
    return ActorContext(
        actor_id="test-actor-001",
        roles=["owner"],
        tenant_id=DEFAULT_INSTITUTION_ID,  # Use default so ledger lookup works
    )


@pytest.fixture
def approver():
    """Create a different actor for approvals (SoD)."""
    return ActorContext(
        actor_id="approver-001",
        roles=["owner", "executive_admin"],
        tenant_id=DEFAULT_INSTITUTION_ID,  # Use default so ledger lookup works
    )


@pytest.fixture
def ledger(tmp_path):
    """Create a test ledger."""
    ledger_path = tmp_path / "test_ledger.jsonl"
    ledger = AuditLedger(ledger_path)
    set_ledger(ledger)
    yield ledger
    reset_institution_ledgers()


@pytest.fixture
def job_store(tmp_path):
    """Create a test job store."""
    institution_id = "test-institution"
    store = JobStore(institution_id)
    # Point store to tmp_path
    store._store_dir = tmp_path / "jobs"
    store._store_path = store._store_dir / "jobs.json"
    store._data = {}
    return store


@pytest.fixture
def cleanup():
    """Clean up after tests."""
    yield
    reset_all_approvals()
    reset_institution_ledgers()
    reset_all_state_stores()


class TestEmitApprovalRequestedGeneric:
    """Test the generic approval request emission."""

    def test_emit_job_approval_request(self, ledger, actor):
        """Test emitting APPROVAL_REQUESTED with job_ref target."""
        approval_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        job_ref = JobRef(job_id=job_id, action="enqueue")
        target = ApprovalTarget(kind=ApprovalTargetKind.JOB, ref=job_ref)

        event = emit_approval_requested_generic(
            approval_id=approval_id,
            rule_name="job.files.delete",
            target=target,
            actor=actor,
            approver_roles=["owner", "executive_admin"],
            payload_sha256="test-hash",
        )

        assert event is not None
        assert event.event_type == "APPROVAL_REQUESTED"
        assert event.case_id == approval_id

        # Check payload has generic target format
        payload = event.payload
        assert payload["target_kind"] == "job"
        assert payload["target_ref"]["job_id"] == job_id
        assert payload["target_ref"]["action"] == "enqueue"
        assert payload["required_roles"] == ["owner", "executive_admin"]

    def test_emit_entity_approval_request(self, ledger, actor):
        """Test emitting APPROVAL_REQUESTED with entity_ref target."""
        from engine.core.approvals import EntityRef

        approval_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        entity_ref = EntityRef(
            entity_type="ModerationAction",
            entity_id=entity_id,
            transition="Apply",
            workflow="ModerationFlow",
        )
        target = ApprovalTarget(kind=ApprovalTargetKind.ENTITY, ref=entity_ref)

        event = emit_approval_requested_generic(
            approval_id=approval_id,
            rule_name="ModerationFlow.Apply",
            target=target,
            actor=actor,
            approver_roles=["moderator"],
        )

        assert event is not None
        payload = event.payload
        assert payload["target_kind"] == "entity"
        assert payload["target_ref"]["entity_type"] == "ModerationAction"
        assert payload["target_ref"]["entity_id"] == entity_id
        assert payload["target_ref"]["transition"] == "Apply"


class TestExtractTargetFromEvent:
    """Test extracting target from approval events."""

    def test_extract_job_target(self, ledger, actor):
        """Test extracting job_ref from event."""
        approval_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        job_ref = JobRef(job_id=job_id, action="enqueue")
        target = ApprovalTarget(kind=ApprovalTargetKind.JOB, ref=job_ref)

        event = emit_approval_requested_generic(
            approval_id=approval_id,
            rule_name="job.test",
            target=target,
            actor=actor,
            approver_roles=["admin"],
        )

        extracted = extract_target_from_event(event)

        assert extracted is not None
        assert extracted.kind == ApprovalTargetKind.JOB
        assert isinstance(extracted.ref, JobRef)
        assert extracted.ref.job_id == job_id
        assert extracted.ref.action == "enqueue"

    def test_extract_entity_target(self, ledger, actor):
        """Test extracting entity_ref from event."""
        from engine.core.approvals import EntityRef

        approval_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        entity_ref = EntityRef(
            entity_type="ContentReport",
            entity_id=entity_id,
            transition="Approve",
        )
        target = ApprovalTarget(kind=ApprovalTargetKind.ENTITY, ref=entity_ref)

        event = emit_approval_requested_generic(
            approval_id=approval_id,
            rule_name="ContentReportFlow.Approve",
            target=target,
            actor=actor,
            approver_roles=["moderator"],
        )

        extracted = extract_target_from_event(event)

        assert extracted is not None
        assert extracted.kind == ApprovalTargetKind.ENTITY
        assert isinstance(extracted.ref, EntityRef)
        assert extracted.ref.entity_type == "ContentReport"
        assert extracted.ref.entity_id == entity_id

    def test_extract_legacy_target(self, ledger, actor):
        """Test extracting legacy API-based target."""
        # Simulate legacy event with api target
        ledger.append(
            event_type="APPROVAL_REQUESTED",
            tenant_id="test",
            actor_id=actor.actor_id,
            actor_roles=actor.roles,
            case_id="legacy-approval-123",
            step="APPROVAL:expense.create",
            payload={
                "target": {"api": "POST /finance/expense"},
                "required_roles": ["manager"],
            },
        )

        events = ledger.get_all_events()
        event = events[-1]

        extracted = extract_target_from_event(event)

        assert extracted is not None
        assert extracted.kind == ApprovalTargetKind.LEGACY_API
        assert extracted.ref["api"] == "POST /finance/expense"


class TestGetJobRefFromApproval:
    """Test getting job ref from approval ID."""

    def test_get_job_ref_success(self, ledger, actor):
        """Test getting job_ref from a job approval."""
        approval_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        job_ref = JobRef(job_id=job_id, action="enqueue")
        target = ApprovalTarget(kind=ApprovalTargetKind.JOB, ref=job_ref)

        emit_approval_requested_generic(
            approval_id=approval_id,
            rule_name="job.test",
            target=target,
            actor=actor,
            approver_roles=["admin"],
        )

        result = get_job_ref_from_approval(approval_id)

        assert result is not None
        assert result.job_id == job_id
        assert result.action == "enqueue"

    def test_get_job_ref_not_job_approval(self, ledger, actor):
        """Test that get_job_ref returns None for non-job approvals."""
        from engine.core.approvals import EntityRef

        approval_id = str(uuid.uuid4())

        entity_ref = EntityRef(entity_type="Test", entity_id="123")
        target = ApprovalTarget(kind=ApprovalTargetKind.ENTITY, ref=entity_ref)

        emit_approval_requested_generic(
            approval_id=approval_id,
            rule_name="entity.test",
            target=target,
            actor=actor,
            approver_roles=["admin"],
        )

        result = get_job_ref_from_approval(approval_id)

        assert result is None

    def test_get_job_ref_not_found(self, ledger):
        """Test that get_job_ref returns None for nonexistent approval."""
        result = get_job_ref_from_approval("nonexistent-id")
        assert result is None


class TestJobApprovalTarget:
    """Test JobRef and ApprovalTarget dataclasses."""

    def test_job_ref_to_dict(self):
        """Test JobRef serialization."""
        job_ref = JobRef(job_id="job-123", action="enqueue")
        result = job_ref.to_dict()

        assert result == {"job_id": "job-123", "action": "enqueue"}

    def test_job_ref_default_action(self):
        """Test JobRef default action is enqueue."""
        job_ref = JobRef(job_id="job-456")
        assert job_ref.action == "enqueue"

    def test_approval_target_job_to_dict(self):
        """Test ApprovalTarget with JobRef serialization."""
        job_ref = JobRef(job_id="job-789", action="enqueue")
        target = ApprovalTarget(kind=ApprovalTargetKind.JOB, ref=job_ref)

        result = target.to_dict()

        assert result["kind"] == "job"
        assert result["ref"]["job_id"] == "job-789"
        assert result["ref"]["action"] == "enqueue"

    def test_approval_target_entity_to_dict(self):
        """Test ApprovalTarget with EntityRef serialization."""
        from engine.core.approvals import EntityRef

        entity_ref = EntityRef(
            entity_type="ModerationAction",
            entity_id="action-123",
            transition="Apply",
            workflow="ModerationFlow",
        )
        target = ApprovalTarget(kind=ApprovalTargetKind.ENTITY, ref=entity_ref)

        result = target.to_dict()

        assert result["kind"] == "entity"
        assert result["ref"]["entity_type"] == "ModerationAction"
        assert result["ref"]["entity_id"] == "action-123"
        assert result["ref"]["transition"] == "Apply"
        assert result["ref"]["workflow"] == "ModerationFlow"


class TestApprovalTargetKind:
    """Test ApprovalTargetKind enum."""

    def test_job_kind(self):
        assert ApprovalTargetKind.JOB.value == "job"

    def test_entity_kind(self):
        assert ApprovalTargetKind.ENTITY.value == "entity"

    def test_legacy_api_kind(self):
        assert ApprovalTargetKind.LEGACY_API.value == "legacy_api"

    def test_kind_from_string(self):
        """Test creating kind from string value."""
        kind = ApprovalTargetKind("job")
        assert kind == ApprovalTargetKind.JOB
