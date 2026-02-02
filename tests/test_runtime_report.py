"""Tests for Runtime Job Report endpoint.

Fase 2.2: Runtime Ack/Result endpoint.

Tests cover:
- Successful first report
- Idempotency (second report returns recorded=false)
- Job not found (404)
- Auth validation (401/403)
- Invalid status value
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry, get_registry
from engine.core.runtime_state import runtime_state, RuntimeMode
from engine.core.actor_tokens import get_actor_tokens_registry, ActorTokensRegistry
from engine.core.ledger import reset_institution_ledgers, get_ledger_for_institution
from engine.legacy_bridge.connectors.outbox_connector import OutboxConnector
from engine.legacy_bridge.write_models import LegacyWriteAction, ActionStatus
from engine.core.job_store import get_job_store, JobState


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    """Setup test environment with proper paths."""
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("ENGINE_CONSOLE_SESSION_SECRET", "a" * 32)
    monkeypatch.setenv("ENGINE_AUTH_MODE", "dev")  # Allow dev mode for easier testing

    reset_registry()
    reset_institution_ledgers()
    ActorTokensRegistry.reset_instance()

    runtime_state.mode = RuntimeMode.ACTIVE
    runtime_state.reason_code = None
    runtime_state.details = []

    yield tmp_path

    reset_registry()
    reset_institution_ledgers()
    ActorTokensRegistry.reset_instance()
    runtime_state.mode = RuntimeMode.ACTIVE


@pytest.fixture
def client(test_env):
    """Test client - depends on test_env to ensure env is set first."""
    return TestClient(app)


@pytest.fixture
def institution_with_job(test_env):
    """Create institution with a job in outbox."""
    tmp_path = test_env  # Use the same tmp_path from test_env
    job_id = "job-abc-123"

    # Register institution in the registry
    registry = get_registry()
    inst, err_code, err_msg = registry.create(slug="test-runtime", display_name="Test Runtime")
    assert inst is not None, f"Failed to create institution: {err_code} - {err_msg}"
    institution_id = inst.institution_id

    # Create agent actor token
    token_registry = get_actor_tokens_registry()
    agent_token, _ = token_registry.create_token(
        institution_id=institution_id,
        actor_id="agent-runtime-001",
        roles=["agent"],
        created_by="test",
        is_agent=True,
    )

    # Create a job in outbox
    outbox = OutboxConnector(institution_id)
    action = LegacyWriteAction(
        action_id=job_id,
        action_type="increase_limit",
        params={"customer_id": "cust-001", "new_limit": 5000},
        institution_id=institution_id,
        status=ActionStatus.ENQUEUED.value,
        requested_by="user-001",
    )
    outbox.write_action(action)

    # Initialize ledger
    ledger = get_ledger_for_institution(institution_id)
    ledger.set_bundle_hashes("manifest-hash", "contract-hash")

    return {
        "institution_id": institution_id,
        "job_id": job_id,
        "agent_token": agent_token,
        "tmp_path": tmp_path,
    }


@pytest.fixture
def institution_with_jobstore_result(test_env):
    """Create institution with a Jobs First-Class job and a legacy results file.

    This fixture covers the canonical UI expectation: `job.get` must return
    `result_json` after the runtime reports completion, without the UI reading
    Engine filesystem directly.
    """
    tmp_path = test_env

    # Register institution
    registry = get_registry()
    inst, err_code, err_msg = registry.create(slug="test-runtime-jobstore", display_name="Test Runtime JobStore")
    assert inst is not None, f"Failed to create institution: {err_code} - {err_msg}"
    institution_id = inst.institution_id

    # Create agent actor token
    token_registry = get_actor_tokens_registry()
    agent_token, _ = token_registry.create_token(
        institution_id=institution_id,
        actor_id="agent-runtime-002",
        roles=["agent"],
        created_by="test",
        is_agent=True,
    )

    # Initialize ledger hashes
    ledger = get_ledger_for_institution(institution_id)
    ledger.set_bundle_hashes("manifest-hash", "contract-hash")

    # Create job in JobStore
    job_store = get_job_store(institution_id, None)
    job = job_store.create_job(
        job_type="files.list",
        params={"path": "bazari", "recursive": False},
        requested_by="owner-001",
        params_sha256="params-sha",
        approval_id=None,
        mandate_id="job-files-list-pre",
        initial_state=JobState.ENQUEUED.value,  # realistic: enqueued before runtime reports
    )

    # Write legacy results file expected by runtime.py loader
    results_dir = tmp_path / "institutions" / institution_id / "legacy_bridge" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    result_payload = {
        "entries": [{"name": "README.md", "type": "file", "size": 1}],
        "path": "bazari",
        "total": 1,
        "truncated": False,
    }
    result_sha256 = __import__("hashlib").sha256(
        json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    results_obj = {
        "executed_at": "2026-02-02T00:00:00Z",
        "exit_code": 0,
        "job_id": job.job_id,
        "status": "executed",
        "summary": "Listed 1 entries in bazari",
        "result": result_payload,
        "result_sha256": result_sha256,
    }
    (results_dir / f"{job.job_id}.json").write_text(json.dumps(results_obj, indent=2), encoding="utf-8")

    return {
        "institution_id": institution_id,
        "job_id": job.job_id,
        "agent_token": agent_token,
        "result_sha256": result_sha256,
        "tmp_path": tmp_path,
    }


class TestRuntimeReportSuccess:
    """Test successful job report."""

    def test_first_report_success(self, client, institution_with_job):
        """First report should succeed and record=True."""
        ctx = institution_with_job

        response = client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Actor-Token": ctx["agent_token"],
                "X-Institution-Id": ctx["institution_id"],
            },
            json={
                "status": "executed",
                "started_at": "2024-01-15T10:00:00Z",
                "finished_at": "2024-01-15T10:05:00Z",
                "exit_code": 0,
                "summary": "Job completed successfully",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == ctx["job_id"]
        assert data["recorded"] is True

    def test_ack_file_created(self, client, institution_with_job):
        """Ack file should be created in outbox-acks."""
        ctx = institution_with_job

        client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Actor-Token": ctx["agent_token"],
                "X-Institution-Id": ctx["institution_id"],
            },
            json={
                "status": "executed",
                "started_at": "2024-01-15T10:00:00Z",
                "finished_at": "2024-01-15T10:05:00Z",
                "exit_code": 0,
            },
        )

        # Check ack file exists
        ack_path = (
            ctx["tmp_path"]
            / "institutions"
            / ctx["institution_id"]
            / "legacy_bridge"
            / "outbox-acks"
            / f"{ctx['job_id']}.json"
        )
        assert ack_path.exists()

        # Verify content
        ack_data = json.loads(ack_path.read_text())
        assert ack_data["job_id"] == ctx["job_id"]
        assert ack_data["status"] == "executed"
        assert ack_data["exit_code"] == 0

    def test_ledger_event_emitted(self, client, institution_with_job):
        """RUNTIME_JOB_REPORTED event should be in ledger."""
        ctx = institution_with_job

        client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Actor-Token": ctx["agent_token"],
                "X-Institution-Id": ctx["institution_id"],
            },
            json={
                "status": "executed",
                "started_at": "2024-01-15T10:00:00Z",
                "finished_at": "2024-01-15T10:05:00Z",
                "exit_code": 0,
            },
        )

        # Check ledger
        ledger = get_ledger_for_institution(ctx["institution_id"])
        events = [e for e in ledger.get_all_events() if e.event_type == "RUNTIME_JOB_REPORTED"]
        assert len(events) == 1
        assert events[0].case_id == ctx["job_id"]
        assert events[0].payload["status"] == "executed"

    def test_jobstore_result_json_populated_from_results_file(self, client, institution_with_jobstore_result):
        """When job exists in JobStore and legacy results file exists, report should store result_json."""
        ctx = institution_with_jobstore_result

        response = client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Actor-Token": ctx["agent_token"],
                "X-Institution-Id": ctx["institution_id"],
            },
            json={
                "status": "executed",
                "started_at": "2026-02-02T00:00:00Z",
                "finished_at": "2026-02-02T00:00:01Z",
                "exit_code": 0,
                "summary": "Listed 1 entries in bazari",
                "artifacts": {
                    "result_sha256": ctx["result_sha256"],
                },
            },
        )

        assert response.status_code == 200

        job_store = get_job_store(ctx["institution_id"], None)
        job = job_store.get_job(ctx["job_id"])
        assert job is not None
        assert job.state == "executed"
        assert job.result_json is not None
        assert job.result_json.get("total") == 1
        assert job.result_json.get("path") == "bazari"
        assert isinstance(job.result_json.get("entries"), list)


class TestRuntimeReportIdempotency:
    """Test idempotency of job report."""

    def test_second_report_returns_recorded_false(self, client, institution_with_job):
        """Second report should return recorded=False."""
        ctx = institution_with_job
        report_data = {
            "status": "executed",
            "started_at": "2024-01-15T10:00:00Z",
            "finished_at": "2024-01-15T10:05:00Z",
            "exit_code": 0,
        }

        # First report
        resp1 = client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Actor-Token": ctx["agent_token"],
                "X-Institution-Id": ctx["institution_id"],
            },
            json=report_data,
        )
        assert resp1.json()["recorded"] is True

        # Second report
        resp2 = client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Actor-Token": ctx["agent_token"],
                "X-Institution-Id": ctx["institution_id"],
            },
            json=report_data,
        )
        assert resp2.status_code == 200
        assert resp2.json()["recorded"] is False
        assert "idempotent" in resp2.json()["message"].lower()

    def test_no_duplicate_ledger_events(self, client, institution_with_job):
        """Multiple reports should not duplicate ledger events."""
        ctx = institution_with_job
        report_data = {
            "status": "executed",
            "started_at": "2024-01-15T10:00:00Z",
            "finished_at": "2024-01-15T10:05:00Z",
            "exit_code": 0,
        }

        # Report 3 times
        for _ in range(3):
            client.post(
                f"/runtime/jobs/{ctx['job_id']}/report",
                headers={
                    "X-Actor-Token": ctx["agent_token"],
                    "X-Institution-Id": ctx["institution_id"],
                },
                json=report_data,
            )

        # Should only have 1 event
        ledger = get_ledger_for_institution(ctx["institution_id"])
        events = [e for e in ledger.get_all_events() if e.event_type == "RUNTIME_JOB_REPORTED"]
        assert len(events) == 1


class TestRuntimeReportErrors:
    """Test error cases."""

    def test_job_not_found(self, client, institution_with_job):
        """Non-existent job should return 404."""
        ctx = institution_with_job

        response = client.post(
            "/runtime/jobs/non-existent-job/report",
            headers={
                "X-Actor-Token": ctx["agent_token"],
                "X-Institution-Id": ctx["institution_id"],
            },
            json={
                "status": "executed",
                "started_at": "2024-01-15T10:00:00Z",
                "finished_at": "2024-01-15T10:05:00Z",
                "exit_code": 0,
            },
        )

        assert response.status_code == 404
        assert response.json()["code"] == "JOB_NOT_FOUND"

    def test_missing_token(self, client, institution_with_job):
        """Missing token should return 401."""
        ctx = institution_with_job

        response = client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Institution-Id": ctx["institution_id"],
            },
            json={
                "status": "executed",
                "started_at": "2024-01-15T10:00:00Z",
                "finished_at": "2024-01-15T10:05:00Z",
                "exit_code": 0,
            },
        )

        assert response.status_code == 401

    def test_invalid_token(self, client, institution_with_job):
        """Invalid token should return 401."""
        ctx = institution_with_job

        response = client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Actor-Token": "invalid-token",
                "X-Institution-Id": ctx["institution_id"],
            },
            json={
                "status": "executed",
                "started_at": "2024-01-15T10:00:00Z",
                "finished_at": "2024-01-15T10:05:00Z",
                "exit_code": 0,
            },
        )

        assert response.status_code == 401

    def test_invalid_status(self, client, institution_with_job):
        """Invalid status value should return 400."""
        ctx = institution_with_job

        response = client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Actor-Token": ctx["agent_token"],
                "X-Institution-Id": ctx["institution_id"],
            },
            json={
                "status": "invalid_status",
                "started_at": "2024-01-15T10:00:00Z",
                "finished_at": "2024-01-15T10:05:00Z",
                "exit_code": 0,
            },
        )

        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_STATUS"

    def test_non_agent_token_rejected(self, client, test_env):
        """Non-agent token should return 403."""
        # Create institution
        registry = get_registry()
        inst, _, _ = registry.create(slug="test-non-agent", display_name="Test Non-Agent")
        institution_id = inst.institution_id

        # Create NON-agent token (is_agent=False)
        token_registry = get_actor_tokens_registry()
        user_token, _ = token_registry.create_token(
            institution_id=institution_id,
            actor_id="human-user-001",
            roles=["operator"],
            created_by="test",
            is_agent=False,  # NOT an agent
        )

        # Create a job in outbox
        outbox = OutboxConnector(institution_id)
        action = LegacyWriteAction(
            action_id="job-non-agent-test",
            action_type="increase_limit",
            params={"customer_id": "cust-001", "new_limit": 5000},
            institution_id=institution_id,
            status=ActionStatus.ENQUEUED.value,
            requested_by="user-001",
        )
        outbox.write_action(action)

        # Initialize ledger
        ledger = get_ledger_for_institution(institution_id)
        ledger.set_bundle_hashes("manifest-hash", "contract-hash")

        response = client.post(
            "/runtime/jobs/job-non-agent-test/report",
            headers={
                "X-Actor-Token": user_token,
                "X-Institution-Id": institution_id,
            },
            json={
                "status": "executed",
                "started_at": "2024-01-15T10:00:00Z",
                "finished_at": "2024-01-15T10:05:00Z",
                "exit_code": 0,
            },
        )

        assert response.status_code == 403
        assert response.json()["code"] == "AGENT_REQUIRED"


class TestRuntimeReportWithArtifacts:
    """Test report with artifact hashes."""

    def test_artifacts_stored(self, client, institution_with_job):
        """Artifact hashes should be stored in ack file."""
        ctx = institution_with_job

        client.post(
            f"/runtime/jobs/{ctx['job_id']}/report",
            headers={
                "X-Actor-Token": ctx["agent_token"],
                "X-Institution-Id": ctx["institution_id"],
            },
            json={
                "status": "executed",
                "started_at": "2024-01-15T10:00:00Z",
                "finished_at": "2024-01-15T10:05:00Z",
                "exit_code": 0,
                "artifacts": {
                    "stdout_sha256": "abc123",
                    "stderr_sha256": "def456",
                    "result_sha256": "ghi789",
                },
            },
        )

        # Verify in ack file
        ack_path = (
            ctx["tmp_path"]
            / "institutions"
            / ctx["institution_id"]
            / "legacy_bridge"
            / "outbox-acks"
            / f"{ctx['job_id']}.json"
        )
        ack_data = json.loads(ack_path.read_text())
        assert ack_data["artifacts"]["stdout_sha256"] == "abc123"
        assert ack_data["artifacts"]["result_sha256"] == "ghi789"
