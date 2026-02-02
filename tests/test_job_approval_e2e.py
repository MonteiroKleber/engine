"""E2E test for destructive job with approval flow.

Tests the complete flow:
1. job.request (approval_required) - creates pending approval
2. /approvals/pending - shows the approval
3. POST /approvals/{id}/decide - approves the job
4. job is enqueued to outbox
5. runtime reports completion
6. job.get shows final state
7. ledger has all events
"""

import os
import pytest
import uuid
from pathlib import Path
from httpx import AsyncClient, ASGITransport

# Set environment before importing the app
os.environ["ENGINE_ISE_ADMIN_TOKEN"] = "test-admin-token"
os.environ["ENGINE_BUNDLE_PATH"] = "/home/bazari/libervia-console/idl/personal_ops"
os.environ["ENGINE_API_MODE"] = "both"  # Enable IDL routes alongside legacy
os.environ["ENGINE_AUTH_MODE"] = "strict"  # Require token-based auth

from engine.api.server import app
from engine.core.ledger import reset_institution_ledgers
from engine.core.state_store import reset_all_state_stores
from engine.core.approvals import reset_all_approvals


@pytest.fixture
def cleanup():
    """Clean up after test."""
    yield
    reset_institution_ledgers()
    reset_all_state_stores()
    reset_all_approvals()


@pytest.mark.asyncio
async def test_destructive_job_approval_flow(cleanup, tmp_path):
    """Test full E2E flow for destructive job requiring approval."""

    # Force register IDL routes if not already registered
    from engine.core.idl_router import register_idl_routes
    from engine.loader.load_bundle import load_bundle
    from engine.core.operations import get_operations

    # Load bundle and register routes
    load_bundle()

    # Debug: Check operations registry (None = single-mode key)
    ops_def = get_operations(None)
    if ops_def:
        print(f"\nOperations in registry: {len(ops_def.operations)}")
        for op in ops_def.operations[:5]:
            print(f"  {op.operation_id}: {op.endpoint_sig} (bind: {op.bind})")
    else:
        print("\nNo operations loaded in registry")

    route_count = register_idl_routes(app)
    print(f"\nRegistered {route_count} IDL routes")

    # Debug: Print job routes
    print("\nJob routes:")
    job_routes = [r for r in app.routes if hasattr(r, "path") and "job" in r.path]
    for route in job_routes:
        print(f"  {getattr(route, 'methods', 'N/A')} {route.path}")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:

        # === 1. CREATE INSTITUTION ===
        print("\n=== 1. CREATE INSTITUTION ===")
        inst_resp = await client.post(
            "/admin/institutions",
            json={"name": "Test Corp E2E", "slug": f"test-corp-{uuid.uuid4().hex[:8]}"},
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert inst_resp.status_code == 201, f"Failed: {inst_resp.json()}"
        institution_id = inst_resp.json()["institution_id"]
        print(f"Created institution: {institution_id}")

        # === 2. CREATE ADMIN KEY (bootstrap) ===
        print("\n=== 2. CREATE ADMIN KEY (bootstrap) ===")
        key_resp = await client.post(
            f"/admin/institutions/{institution_id}/admin-keys",
            json={},
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert key_resp.status_code == 201, f"Failed: {key_resp.json()}"
        admin_key = key_resp.json()["plaintext_secret"]
        print(f"Admin key: {admin_key[:20]}...")

        # === 3. CREATE AGENT ACTOR (proposer) ===
        print("\n=== 3. CREATE AGENT ACTOR ===")
        agent_resp = await client.post(
            f"/admin/institutions/{institution_id}/actors",
            json={"actor_id": "agent-001", "roles": ["agent"], "is_agent": True},
            headers={"X-Admin-Key": admin_key},
        )
        assert agent_resp.status_code in (200, 201), f"Failed: {agent_resp.json()}"
        agent_token = agent_resp.json()["token"]
        print(f"Agent token: {agent_token[:20]}...")

        # === 4. CREATE OWNER ACTOR (approver) ===
        print("\n=== 4. CREATE OWNER ACTOR ===")
        owner_resp = await client.post(
            f"/admin/institutions/{institution_id}/actors",
            json={"actor_id": "owner-001", "roles": ["owner", "executive_admin"]},
            headers={"X-Admin-Key": admin_key},
        )
        assert owner_resp.status_code in (200, 201), f"Failed: {owner_resp.json()}"
        owner_token = owner_resp.json()["token"]
        print(f"Owner token: {owner_token[:20]}...")

        # === 5. CREATE DESTRUCTIVE JOB (requires approval) ===
        print("\n=== 5. CREATE DESTRUCTIVE JOB (files.delete) ===")
        job_resp = await client.post(
            "/personal/jobs/files/delete",
            json={"paths": ["/tmp/test-file.txt"]},
            headers={
                "X-Actor-Token": agent_token,
                "X-Institution-Id": institution_id,
                "X-Idempotency-Key": str(uuid.uuid4()),
            },
        )
        print(f"Job response: {job_resp.status_code} - {job_resp.json()}")
        assert job_resp.status_code == 202, f"Expected 202 (pending approval), got: {job_resp.status_code}"

        job_data = job_resp.json()
        assert job_data["status"] == "pending_approval"
        job_id = job_data["job_id"]
        approval_id = job_data["approval_id"]
        print(f"Job ID: {job_id}")
        print(f"Approval ID: {approval_id}")

        # === 6. CHECK APPROVALS/PENDING ===
        print("\n=== 6. CHECK /approvals/pending ===")
        pending_resp = await client.get(
            "/approvals/pending",
            headers={
                "X-Admin-Key": admin_key,
                "X-Institution-Id": institution_id,
            },
        )
        assert pending_resp.status_code == 200
        pending_data = pending_resp.json()
        print(f"Pending approvals: {pending_data['total']}")
        assert pending_data["total"] >= 1

        # Find our approval
        our_approval = None
        for appr in pending_data["approvals"]:
            if appr["approval_id"] == approval_id:
                our_approval = appr
                break
        assert our_approval is not None, "Our approval should be in pending list"
        print(f"Found approval: {our_approval}")

        # === 7. APPROVE THE JOB ===
        print("\n=== 7. APPROVE THE JOB ===")
        decide_resp = await client.post(
            f"/approvals/{approval_id}/decide",
            json={"decision": "approve", "reason": "E2E test approval"},
            headers={
                "X-Actor-Token": owner_token,
                "X-Institution-Id": institution_id,
            },
        )
        print(f"Decide response: {decide_resp.status_code} - {decide_resp.json()}")
        assert decide_resp.status_code == 200, f"Failed: {decide_resp.json()}"

        decide_data = decide_resp.json()
        assert decide_data["decision"] == "approve"
        assert decide_data["job_state"] == "enqueued"
        outbox_path = decide_data.get("outbox_path")
        print(f"Job enqueued to: {outbox_path}")

        # === 8. CHECK JOB.GET (should be enqueued) ===
        print("\n=== 8. CHECK JOB.GET (enqueued) ===")
        job_get_resp = await client.get(
            f"/personal/jobs/{job_id}",
            headers={
                "X-Actor-Token": agent_token,
                "X-Institution-Id": institution_id,
            },
        )
        assert job_get_resp.status_code == 200
        job_state = job_get_resp.json()
        print(f"Job state: {job_state['state']}")
        assert job_state["state"] == "enqueued"
        assert job_state["approved_by"] == "owner-001"

        # === 9. SIMULATE RUNTIME REPORT ===
        print("\n=== 9. SIMULATE RUNTIME REPORT ===")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        report_resp = await client.post(
            f"/runtime/jobs/{job_id}/report",
            json={
                "status": "executed",
                "started_at": now,
                "finished_at": now,
                "exit_code": 0,
                "summary": "Deleted 1 file",
            },
            headers={
                "X-Actor-Token": agent_token,  # Agent token required for runtime report
                "X-Institution-Id": institution_id,
            },
        )
        print(f"Report response: {report_resp.status_code} - {report_resp.json()}")
        assert report_resp.status_code == 200

        # === 10. CHECK JOB.GET (final state) ===
        print("\n=== 10. CHECK JOB.GET (final state) ===")
        job_final_resp = await client.get(
            f"/personal/jobs/{job_id}",
            headers={
                "X-Actor-Token": agent_token,
                "X-Institution-Id": institution_id,
            },
        )
        assert job_final_resp.status_code == 200
        job_final = job_final_resp.json()
        print(f"Final job state: {job_final['state']}")
        print(f"Result: {job_final.get('result_summary')}")
        assert job_final["state"] == "executed"
        assert job_final["exit_code"] == 0

        # === 11. CHECK LEDGER ===
        print("\n=== 11. CHECK LEDGER ===")
        from engine.core.ledger import get_ledger_for_institution

        ledger = get_ledger_for_institution(institution_id)
        events = ledger.get_all_events()

        event_types = [e.event_type for e in events]
        print(f"Ledger events: {event_types}")

        # Verify all expected events are present
        assert "JOB_REQUESTED" in event_types, "Missing JOB_REQUESTED"
        assert "APPROVAL_REQUESTED" in event_types, "Missing APPROVAL_REQUESTED"
        assert "APPROVAL_DECIDED" in event_types, "Missing APPROVAL_DECIDED"
        assert "JOB_ENQUEUED" in event_types, "Missing JOB_ENQUEUED"
        assert "RUNTIME_JOB_REPORTED" in event_types, "Missing RUNTIME_JOB_REPORTED"

        # Check APPROVAL_REQUESTED has job target
        appr_req_event = next(e for e in events if e.event_type == "APPROVAL_REQUESTED")
        assert appr_req_event.payload.get("target_kind") == "job", "Should have target_kind: job"
        assert appr_req_event.payload.get("target_ref", {}).get("job_id") == job_id

        print("\n=== E2E TEST PASSED ===")
        print(f"Full flow verified:")
        print(f"  - Job created: {job_id}")
        print(f"  - Approval requested: {approval_id}")
        print(f"  - Approval decided: approve")
        print(f"  - Job enqueued: {outbox_path}")
        print(f"  - Runtime reported: executed")
        print(f"  - Ledger events: {len(events)}")
