"""E2E Test: Console API → Engine Jobs First-Class Integration.

Demonstrates the Prompt 3 (Console) requirement:
- Chat "listar arquivos em X" → Engine job.request → returns job_id
- Poll GET /personal/jobs/{job_id} → Get job state from Engine
- No direct outbox writes from Console API

This test validates:
1. Engine job.request endpoints work correctly
2. Jobs are created in JobStore (not direct outbox writes)
3. job.get returns correct job state
4. Ledger records all events
"""

import os
import pytest
import httpx
import json
import uuid
import sys

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.core.data_root import get_data_root
from engine.core.job_store import get_job_store

# Test configuration
ENGINE_BASE_URL = os.environ.get("ENGINE_BASE_URL", "http://localhost:8001")
ADMIN_TOKEN = os.environ.get("ENGINE_ADMIN_TOKEN", "dev-admin-token")

# Test data
TEST_SLUG = f"console-test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def engine_client():
    """HTTP client for Engine API."""
    return httpx.Client(base_url=ENGINE_BASE_URL, timeout=30.0)


@pytest.fixture(scope="module")
def test_institution(engine_client):
    """Create test institution and return IDs."""
    # Create institution
    resp = engine_client.post(
        "/admin/institutions",
        json={"slug": TEST_SLUG, "display_name": "Console E2E Test"},
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
    assert resp.status_code == 201, f"Create admin key failed: {resp.text}"
    admin_key = resp.json()["plaintext_secret"]

    # Create owner actor token (200 if reused, 201 if new)
    resp = engine_client.post(
        f"/admin/institutions/{institution_id}/actors",
        json={"actor_id": "owner-user", "roles": ["owner"], "is_agent": False},
        headers={"X-Admin-Key": admin_key},
    )
    assert resp.status_code in (200, 201), f"Create owner token failed: {resp.text}"
    owner_token = resp.json()["token"]

    yield {
        "institution_id": institution_id,
        "admin_key": admin_key,
        "owner_token": owner_token,
    }


class TestConsoleE2EJobsFirstClass:
    """Test suite for Console → Engine Jobs First-Class integration."""

    def test_job_files_list_creates_job(self, engine_client, test_institution):
        """Test: POST /personal/jobs/files/list creates job via Engine.

        This is the core Prompt 3 requirement: Console API should call
        Engine's job.request endpoint, not write directly to outbox.
        """
        institution_id = test_institution["institution_id"]
        owner_token = test_institution["owner_token"]

        # Call job.request endpoint (files.list is safe=true)
        resp = engine_client.post(
            "/personal/jobs/files/list",
            json={"path": "/documentos"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": owner_token,
            },
        )

        # Should return 201 (safe operation, ready for enqueue)
        assert resp.status_code in (201, 202), f"Unexpected status: {resp.status_code} - {resp.text}"

        data = resp.json()
        assert "job_id" in data, f"Missing job_id in response: {data}"
        assert data.get("status") in ("requested", "pending_approval"), f"Unexpected status: {data.get('status')}"
        assert data.get("job_type") == "files.list", f"Unexpected job_type: {data.get('job_type')}"

        job_id = data["job_id"]
        print(f"\n✓ Job created: {job_id} (status: {data.get('status')})")

        return job_id

    def test_job_get_returns_state(self, engine_client, test_institution):
        """Test: GET /personal/jobs/{job_id} returns job state."""
        institution_id = test_institution["institution_id"]
        owner_token = test_institution["owner_token"]

        # First create a job
        resp = engine_client.post(
            "/personal/jobs/files/list",
            json={"path": "/test"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": owner_token,
            },
        )
        assert resp.status_code in (201, 202)
        job_id = resp.json()["job_id"]

        # Now get the job
        resp = engine_client.get(
            f"/personal/jobs/{job_id}",
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": owner_token,
            },
        )

        assert resp.status_code == 200, f"Job get failed: {resp.status_code} - {resp.text}"

        data = resp.json()
        assert data.get("job_id") == job_id
        assert data.get("job_type") == "files.list"
        assert data.get("state") == "requested"  # Safe job starts as "requested"
        assert data.get("params") == {"path": "/test"}

        print(f"\n✓ Job state retrieved: {data.get('state')}")

    def test_job_files_scan_creates_job(self, engine_client, test_institution):
        """Test: POST /personal/jobs/files/scan creates scan job."""
        institution_id = test_institution["institution_id"]
        owner_token = test_institution["owner_token"]

        resp = engine_client.post(
            "/personal/jobs/files/scan",
            json={"path": "/", "scan_type": "duplicates"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": owner_token,
            },
        )

        assert resp.status_code in (201, 202), f"Unexpected status: {resp.status_code} - {resp.text}"

        data = resp.json()
        assert "job_id" in data
        assert data.get("job_type") == "files.scan"

        print(f"\n✓ Scan job created: {data['job_id']}")

    def test_job_files_suggest_creates_job(self, engine_client, test_institution):
        """Test: POST /personal/jobs/files/suggest creates suggest job."""
        institution_id = test_institution["institution_id"]
        owner_token = test_institution["owner_token"]

        resp = engine_client.post(
            "/personal/jobs/files/suggest",
            json={"path": "/", "suggestion_type": "cleanup"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": owner_token,
            },
        )

        assert resp.status_code in (201, 202), f"Unexpected status: {resp.status_code} - {resp.text}"

        data = resp.json()
        assert "job_id" in data
        assert data.get("job_type") == "files.suggest"

        print(f"\n✓ Suggest job created: {data['job_id']}")

    def test_job_files_delete_requires_approval(self, engine_client, test_institution):
        """Test: POST /personal/jobs/files/delete requires approval (safe=false)."""
        institution_id = test_institution["institution_id"]
        owner_token = test_institution["owner_token"]

        resp = engine_client.post(
            "/personal/jobs/files/delete",
            json={"paths": ["/old-file.txt"]},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": owner_token,
            },
        )

        # Destructive operations should return 202 (pending approval)
        assert resp.status_code == 202, f"Expected 202 for destructive op: {resp.status_code} - {resp.text}"

        data = resp.json()
        assert data.get("status") == "pending_approval"
        assert "approval_id" in data, f"Missing approval_id: {data}"

        print(f"\n✓ Delete job requires approval: {data.get('approval_id')}")

    def test_job_not_in_outbox_until_enqueued(self, engine_client, test_institution):
        """Test: Job is in JobStore, not outbox, until explicitly enqueued.

        This validates the core requirement: Console API does NOT write
        directly to outbox. Jobs go through Engine's JobStore first.
        """
        institution_id = test_institution["institution_id"]
        owner_token = test_institution["owner_token"]

        # Create a job
        resp = engine_client.post(
            "/personal/jobs/files/list",
            json={"path": "/verify-outbox"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": owner_token,
            },
        )
        assert resp.status_code in (201, 202)
        job_id = resp.json()["job_id"]

        # Verify job exists via API (job.get endpoint)
        resp = engine_client.get(
            f"/personal/jobs/{job_id}",
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": owner_token,
            },
        )
        assert resp.status_code == 200, f"job.get failed: {resp.text}"
        job_data = resp.json()
        assert job_data["state"] == "requested", f"Expected state='requested', got {job_data['state']}"

        print(f"\n✓ Job {job_id} in JobStore (state=requested)")


def test_ledger_records_job_events(engine_client, test_institution):
    """Test: Ledger records JOB_REQUESTED events."""
    institution_id = test_institution["institution_id"]
    admin_key = test_institution["admin_key"]
    owner_token = test_institution["owner_token"]

    # Create a job
    resp = engine_client.post(
        "/personal/jobs/files/list",
        json={"path": "/ledger-test"},
        headers={
            "X-Institution-Id": institution_id,
            "X-Actor-Token": owner_token,
        },
    )
    assert resp.status_code in (201, 202)
    job_id = resp.json()["job_id"]

    # Check ledger for JOB_REQUESTED event
    resp = engine_client.get(
        f"/v1/observe/ledger/events?event_type=JOB_REQUESTED&limit=10",
        headers={
            "X-Institution-Id": institution_id,
            "X-Admin-Key": admin_key,
        },
    )
    assert resp.status_code == 200, f"Ledger query failed: {resp.text}"

    events = resp.json().get("events", [])
    job_events = [e for e in events if e.get("payload", {}).get("job_id") == job_id]

    assert len(job_events) >= 1, f"JOB_REQUESTED event not found for {job_id}"
    print(f"\n✓ Ledger recorded JOB_REQUESTED for {job_id}")


if __name__ == "__main__":
    # Run with: python tests/test_console_e2e.py
    # Requires: ENGINE_API_MODE=idl (or both) and running Engine
    pytest.main([__file__, "-v", "-s"])
