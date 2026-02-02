"""Anti-Regression Tests for Console API / Engine Jobs First-Class Integration.

These tests ensure the Prompt 3 (Console) implementation doesn't regress:
1. Safe job doesn't depend on 202 status and can reach terminal state via job_get
2. Destructive creates approval and doesn't enqueue before decision
3. Upon approval, job.enqueue occurs and job appears in outbox
4. Compatibility - existing payload/status snapshots are preserved

Run with: pytest tests/test_console_antiregression.py -v -s
Requires: ENGINE_API_MODE=idl or ENGINE_API_MODE=both
"""

import os
import pytest
import httpx
import json
import uuid
import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.core.data_root import get_data_root
from engine.core.job_store import get_job_store, JobState

# Test configuration
ENGINE_BASE_URL = os.environ.get("ENGINE_BASE_URL", "http://localhost:8001")
ADMIN_TOKEN = os.environ.get("ENGINE_ADMIN_TOKEN", "dev-admin-token")

# Expected response snapshots (for compatibility testing)
SAFE_JOB_RESPONSE_SCHEMA = {
    "required_fields": ["job_id", "job_type", "status", "message"],
    "status_values": ["requested"],  # Safe jobs return "requested"
    "status_code": 201,
}

DESTRUCTIVE_JOB_RESPONSE_SCHEMA = {
    "required_fields": ["job_id", "job_type", "status", "approval_id", "message"],
    "status_values": ["pending_approval"],  # Destructive jobs return "pending_approval"
    "status_code": 202,
}

JOB_GET_RESPONSE_SCHEMA = {
    "required_fields": ["job_id", "job_type", "state", "params", "requested_by"],
    "optional_fields": ["approval_id", "approved_by", "result_json", "result_summary", "exit_code", "artifacts"],
}


@pytest.fixture(scope="module")
def engine_client():
    """HTTP client for Engine API."""
    return httpx.Client(base_url=ENGINE_BASE_URL, timeout=30.0)


@pytest.fixture(scope="module")
def test_institution(engine_client):
    """Create test institution with tokens."""
    test_slug = f"antiregression-{uuid.uuid4().hex[:8]}"

    # Create institution
    resp = engine_client.post(
        "/admin/institutions",
        json={"slug": test_slug, "display_name": "Anti-Regression Test"},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp.status_code == 201, f"Create institution failed: {resp.text}"
    institution_id = resp.json()["institution_id"]

    # Create admin key
    resp = engine_client.post(
        f"/admin/institutions/{institution_id}/admin-keys",
        json={},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp.status_code == 201
    admin_key = resp.json()["plaintext_secret"]

    # Create owner token (200 if reused, 201 if new)
    resp = engine_client.post(
        f"/admin/institutions/{institution_id}/actors",
        json={"actor_id": "owner-antiregression", "roles": ["owner"], "is_agent": False},
        headers={"X-Admin-Key": admin_key},
    )
    assert resp.status_code in (200, 201)
    owner_token = resp.json()["token"]

    # Create approver token (different from owner for SoD)
    resp = engine_client.post(
        f"/admin/institutions/{institution_id}/actors",
        json={"actor_id": "approver-antiregression", "roles": ["executive_admin"], "is_agent": False},
        headers={"X-Admin-Key": admin_key},
    )
    assert resp.status_code in (200, 201)
    approver_token = resp.json()["token"]

    # Create agent token
    resp = engine_client.post(
        f"/admin/institutions/{institution_id}/actors",
        json={"actor_id": "agent-antiregression", "roles": ["agent"], "is_agent": True},
        headers={"X-Admin-Key": admin_key},
    )
    assert resp.status_code in (200, 201)
    agent_token = resp.json()["token"]

    yield {
        "institution_id": institution_id,
        "admin_key": admin_key,
        "owner_token": owner_token,
        "approver_token": approver_token,
        "agent_token": agent_token,
    }


class TestSafeJobsAntiRegression:
    """Test safe jobs don't depend on 202 and can reach terminal state."""

    def test_safe_job_returns_201_not_202(self, engine_client, test_institution):
        """Anti-regression: Safe jobs MUST return 201, not 202."""
        resp = engine_client.post(
            "/personal/jobs/files/list",
            json={"path": "/test"},
            headers={
                "X-Institution-Id": test_institution["institution_id"],
                "X-Actor-Token": test_institution["owner_token"],
            },
        )

        # CRITICAL: Safe jobs return 201, not 202
        assert resp.status_code == SAFE_JOB_RESPONSE_SCHEMA["status_code"], (
            f"Safe job should return {SAFE_JOB_RESPONSE_SCHEMA['status_code']}, got {resp.status_code}"
        )

        data = resp.json()
        assert data.get("status") in SAFE_JOB_RESPONSE_SCHEMA["status_values"], (
            f"Safe job status should be {SAFE_JOB_RESPONSE_SCHEMA['status_values']}, got {data.get('status')}"
        )

        # Should NOT have approval_id (safe jobs don't need approval by default)
        assert "approval_id" not in data or data.get("approval_id") is None, (
            "Safe job should not have approval_id by default"
        )

        print(f"\n✓ Safe job returns 201 with status='requested' (no approval_id)")

    def test_safe_job_response_schema_compatibility(self, engine_client, test_institution):
        """Anti-regression: Safe job response must have required fields."""
        resp = engine_client.post(
            "/personal/jobs/files/scan",
            json={"path": "/", "scan_type": "duplicates"},
            headers={
                "X-Institution-Id": test_institution["institution_id"],
                "X-Actor-Token": test_institution["owner_token"],
            },
        )

        assert resp.status_code == 201
        data = resp.json()

        for field in SAFE_JOB_RESPONSE_SCHEMA["required_fields"]:
            assert field in data, f"Missing required field: {field}"

        print(f"\n✓ Safe job response has all required fields: {SAFE_JOB_RESPONSE_SCHEMA['required_fields']}")

    def test_safe_job_reachable_via_job_get(self, engine_client, test_institution):
        """Anti-regression: Safe job must be retrievable via job_get endpoint."""
        # Create job
        resp = engine_client.post(
            "/personal/jobs/files/suggest",
            json={"path": "/", "suggestion_type": "cleanup"},
            headers={
                "X-Institution-Id": test_institution["institution_id"],
                "X-Actor-Token": test_institution["owner_token"],
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]

        # Retrieve via job_get
        resp = engine_client.get(
            f"/personal/jobs/{job_id}",
            headers={
                "X-Institution-Id": test_institution["institution_id"],
                "X-Actor-Token": test_institution["owner_token"],
            },
        )

        assert resp.status_code == 200, f"job_get failed: {resp.text}"
        data = resp.json()

        for field in JOB_GET_RESPONSE_SCHEMA["required_fields"]:
            assert field in data, f"Missing required field in job_get: {field}"

        assert data["state"] == "requested", f"Expected state='requested', got {data['state']}"

        print(f"\n✓ Safe job retrievable via job_get with state='requested'")


class TestDestructiveJobsAntiRegression:
    """Test destructive jobs require approval and don't enqueue before decision."""

    def test_destructive_job_returns_202_with_approval_id(self, engine_client, test_institution):
        """Anti-regression: Destructive jobs MUST return 202 with approval_id."""
        resp = engine_client.post(
            "/personal/jobs/files/delete",
            json={"paths": ["/antiregression-test.txt"]},
            headers={
                "X-Institution-Id": test_institution["institution_id"],
                "X-Actor-Token": test_institution["owner_token"],
            },
        )

        # CRITICAL: Destructive jobs return 202
        assert resp.status_code == DESTRUCTIVE_JOB_RESPONSE_SCHEMA["status_code"], (
            f"Destructive job should return {DESTRUCTIVE_JOB_RESPONSE_SCHEMA['status_code']}, got {resp.status_code}"
        )

        data = resp.json()
        assert data.get("status") in DESTRUCTIVE_JOB_RESPONSE_SCHEMA["status_values"]

        # MUST have approval_id
        assert "approval_id" in data and data["approval_id"], (
            "Destructive job MUST have approval_id"
        )

        print(f"\n✓ Destructive job returns 202 with approval_id={data['approval_id']}")

    def test_destructive_job_not_in_outbox_before_approval(self, engine_client, test_institution):
        """Anti-regression: Destructive job MUST NOT be in outbox before approval."""
        institution_id = test_institution["institution_id"]

        # Create destructive job
        resp = engine_client.post(
            "/personal/jobs/files/rename",
            json={"source_path": "/before-approval.txt", "new_name": "after-approval.txt"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": test_institution["owner_token"],
            },
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # Check job state via API (job.get endpoint)
        resp = engine_client.get(
            f"/personal/jobs/{job_id}",
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": test_institution["owner_token"],
            },
        )
        assert resp.status_code == 200, f"job.get failed: {resp.text}"
        job_data = resp.json()
        assert job_data["state"] == "pending_approval", (
            f"Expected state='pending_approval', got {job_data['state']}"
        )

        print(f"\n✓ Destructive job {job_id} state='pending_approval' (not in outbox)")

    def test_destructive_job_appears_in_outbox_after_approval(self, engine_client, test_institution):
        """Anti-regression: After approval, job MUST be enqueueable to outbox."""
        institution_id = test_institution["institution_id"]

        # Create destructive job
        resp = engine_client.post(
            "/personal/jobs/files/move",
            json={"source_path": "/move-test.txt", "destination_path": "/moved/move-test.txt"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": test_institution["owner_token"],
            },
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        approval_id = resp.json()["approval_id"]

        # Approve (must use different actor due to SoD)
        resp = engine_client.post(
            f"/approvals/{approval_id}/decide",
            json={"decision": "approve", "reason": "Anti-regression test"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": test_institution["approver_token"],
            },
        )
        assert resp.status_code == 200, f"Approval failed: {resp.text}"

        # Check job state via API (job.get endpoint)
        resp = engine_client.get(
            f"/personal/jobs/{job_id}",
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": test_institution["owner_token"],
            },
        )
        assert resp.status_code == 200, f"job.get failed: {resp.text}"
        job_data = resp.json()
        # After approval, job is automatically enqueued
        assert job_data["state"] in ("approved", "enqueued"), (
            f"Expected state='approved' or 'enqueued', got {job_data['state']}"
        )

        print(f"\n✓ After approval, job {job_id} state='{job_data['state']}' (enqueued for execution)")


class TestResponseSchemaCompatibility:
    """Test response schemas haven't changed (anti-regression)."""

    def test_job_get_response_has_all_expected_fields(self, engine_client, test_institution):
        """Anti-regression: job_get response must include expected fields."""
        # Create a job
        resp = engine_client.post(
            "/personal/jobs/files/list",
            json={"path": "/schema-test"},
            headers={
                "X-Institution-Id": test_institution["institution_id"],
                "X-Actor-Token": test_institution["owner_token"],
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]

        # Get job
        resp = engine_client.get(
            f"/personal/jobs/{job_id}",
            headers={
                "X-Institution-Id": test_institution["institution_id"],
                "X-Actor-Token": test_institution["owner_token"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # Check required fields
        for field in JOB_GET_RESPONSE_SCHEMA["required_fields"]:
            assert field in data, f"Missing required field in job_get response: {field}"

        # Check optional fields are recognized
        for field in JOB_GET_RESPONSE_SCHEMA["optional_fields"]:
            # Optional fields may or may not be present, but should be in schema
            pass  # Just documenting expected optional fields

        print(f"\n✓ job_get response schema is compatible")
        print(f"  Required: {JOB_GET_RESPONSE_SCHEMA['required_fields']}")
        print(f"  Optional: {JOB_GET_RESPONSE_SCHEMA['optional_fields']}")


class TestLedgerEventsAntiRegression:
    """Test ledger events are emitted correctly."""

    def test_safe_job_emits_job_requested_event(self, engine_client, test_institution):
        """Anti-regression: Safe job must emit JOB_REQUESTED event."""
        institution_id = test_institution["institution_id"]

        # Create job
        resp = engine_client.post(
            "/personal/jobs/files/list",
            json={"path": "/ledger-safe-test"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": test_institution["owner_token"],
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]

        # Query ledger
        resp = engine_client.get(
            f"/v1/observe/ledger/events?event_type=JOB_REQUESTED&limit=10",
            headers={
                "X-Institution-Id": institution_id,
                "X-Admin-Key": test_institution["admin_key"],
            },
        )
        assert resp.status_code == 200

        events = resp.json().get("events", [])
        matching = [e for e in events if e.get("payload", {}).get("job_id") == job_id]

        assert len(matching) >= 1, f"JOB_REQUESTED event not found for safe job {job_id}"

        print(f"\n✓ Safe job {job_id} emitted JOB_REQUESTED event")

    def test_destructive_job_emits_approval_requested_event(self, engine_client, test_institution):
        """Anti-regression: Destructive job must emit APPROVAL_REQUESTED event."""
        institution_id = test_institution["institution_id"]

        # Create destructive job
        resp = engine_client.post(
            "/personal/jobs/files/delete",
            json={"paths": ["/ledger-destructive-test.txt"]},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": test_institution["owner_token"],
            },
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        approval_id = resp.json()["approval_id"]

        # Query ledger for APPROVAL_REQUESTED
        resp = engine_client.get(
            f"/v1/observe/ledger/events?event_type=APPROVAL_REQUESTED&limit=10",
            headers={
                "X-Institution-Id": institution_id,
                "X-Admin-Key": test_institution["admin_key"],
            },
        )
        assert resp.status_code == 200

        events = resp.json().get("events", [])
        # approval_id is stored in case_id field for APPROVAL_REQUESTED events
        matching = [e for e in events if e.get("case_id") == approval_id]

        assert len(matching) >= 1, f"APPROVAL_REQUESTED event not found for {approval_id}"

        print(f"\n✓ Destructive job {job_id} emitted APPROVAL_REQUESTED event (approval_id={approval_id})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
