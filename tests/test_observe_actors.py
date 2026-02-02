"""Basic coverage for /v1/observe/* endpoints.

Ensures the observe router is registered and returns deterministic shape.
"""

import importlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.actor_tokens import ActorTokensRegistry
from engine.core.autonomy import reset_all_autonomy
from engine.core.governed_autonomy import invalidate_all_autonomy_cache
from engine.core.governed_mandates import invalidate_all_mandates_cache
from engine.core.governed_policies import invalidate_all_policies_cache
from engine.core.institutions import reset_registry
from engine.core.ledger import reset_institution_ledgers
from engine.core.mandates import clear_all_mandates
from engine.core.operations import reset_all_operations
from engine.core.policy import clear_all_policies
from engine.core.runtime_state import runtime_state
from engine.core.state_store import reset_all_state_stores
from engine.loader.load_bundle import _set_bundle_context


@pytest.fixture(autouse=True)
def _reset_globals():
    runtime_state.set_active()
    reset_all_operations()
    reset_all_state_stores()
    reset_institution_ledgers()
    clear_all_policies()
    clear_all_mandates()
    reset_all_autonomy()
    invalidate_all_policies_cache()
    invalidate_all_mandates_cache()
    invalidate_all_autonomy_cache()
    _set_bundle_context(None)
    reset_registry()
    ActorTokensRegistry.reset_instance()
    yield


def _make_app(monkeypatch, tmp_path: Path, bundle_path: Path):
    data_root = tmp_path / "data_root"
    institutions_dir = tmp_path / "institutions"
    institutions_registry = tmp_path / "institutions_registry.jsonl"

    monkeypatch.setenv("ENGINE_API_MODE", "idl")
    monkeypatch.setenv("ENGINE_AUTH_MODE", "strict")
    monkeypatch.setenv("ENGINE_INSTALL_MODE", "dev")
    monkeypatch.setenv("ENGINE_CONSOLE_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(data_root))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(institutions_dir))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(institutions_registry))
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_path))

    import engine.api.server as server

    importlib.reload(server)
    return server.app


def test_observe_actors_lists_admin_activity(tmp_path: Path, monkeypatch):
    app = _make_app(monkeypatch, tmp_path, Path("bundles/finance-pilot").resolve())

    with TestClient(app) as client:
        # Create institution (emits ADMIN auth events to ledger)
        slug = f"t-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": slug, "display_name": "Test"},
        )
        assert resp.status_code in (200, 201), resp.text
        institution_id = resp.json()["institution_id"]

        # Bootstrap admin key
        resp = client.post(
            f"/admin/institutions/{institution_id}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        assert resp.status_code in (200, 201), resp.text
        admin_key = resp.json()["plaintext_secret"]

        # Create an actor token (generates non-ADMIN ledger events too)
        resp = client.post(
            f"/admin/institutions/{institution_id}/actors",
            headers={"X-Institution-Id": institution_id, "X-Admin-Key": admin_key},
            json={"actor_id": str(uuid.uuid4()), "roles": ["analyst"]},
        )
        assert resp.status_code == 200, resp.text

        # Observe
        resp = client.get(
            "/v1/observe/actors",
            params={"limit": 5},
            headers={"X-Institution-Id": institution_id, "X-Admin-Key": admin_key},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data.get("items"), list)
        assert data.get("next_cursor") is None

        # Should include the legacy admin actor_id used by admin auth telemetry.
        actor_ids = {item.get("actor_id") for item in data["items"]}
        assert "ADMIN" in actor_ids


def test_ledger_events_include_payload(tmp_path: Path, monkeypatch):
    """Test that ledger events include full payload (security-redacted)."""
    app = _make_app(monkeypatch, tmp_path, Path("bundles/finance-pilot").resolve())

    with TestClient(app) as client:
        # Create institution
        slug = f"t-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": slug, "display_name": "Test Payload"},
        )
        assert resp.status_code in (200, 201), resp.text
        institution_id = resp.json()["institution_id"]

        # Bootstrap admin key
        resp = client.post(
            f"/admin/institutions/{institution_id}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        assert resp.status_code in (200, 201), resp.text
        admin_key = resp.json()["plaintext_secret"]

        # Create an actor token (generates ACTOR_TOKEN_CREATED event)
        actor_id = str(uuid.uuid4())
        resp = client.post(
            f"/admin/institutions/{institution_id}/actors",
            headers={"X-Institution-Id": institution_id, "X-Admin-Key": admin_key},
            json={"actor_id": actor_id, "roles": ["owner"]},
        )
        assert resp.status_code == 200, resp.text
        actor_token = resp.json()["token"]

        # Query ledger events
        resp = client.get(
            "/v1/observe/ledger/events",
            params={"limit": 20},
            headers={"X-Institution-Id": institution_id, "X-Admin-Key": admin_key},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Verify payload field is present in all events
        events = data.get("events", [])
        assert len(events) > 0, "Expected at least one event"

        for event in events:
            assert "payload" in event, f"Event missing payload field: {event}"
            assert isinstance(event["payload"], dict), f"Payload should be dict: {event['payload']}"

        # Find ACTOR_TOKEN_CREATED event and verify payload has content
        token_events = [e for e in events if e["event_type"] == "ACTOR_TOKEN_CREATED"]
        assert len(token_events) > 0, "Expected ACTOR_TOKEN_CREATED event"

        token_event = token_events[0]
        # Payload should be non-empty dict
        assert len(token_event["payload"]) > 0, "Payload should have content"
        # Payload should contain institution_id (proves it's real payload data)
        assert "institution_id" in token_event["payload"] or "decision" in token_event["payload"]
        # Token in payload should be redacted for security
        if "token" in token_event["payload"]:
            assert token_event["payload"]["token"] == "[REDACTED]"


def test_payload_redaction_sensitive_keys(tmp_path: Path, monkeypatch):
    """Test that sensitive keys in payload are redacted."""
    from engine.api.observe import _redact_sensitive

    # Test basic sensitive keys
    payload = {
        "token": "secret-token",
        "secret": "my-secret",
        "admin_key": "admin-key-value",
        "password": "my-password",
        "api_key": "api-key-value",
        "plaintext_secret": "plaintext-secret-value",
        "normal_field": "visible",
    }
    redacted = _redact_sensitive(payload)
    assert redacted["token"] == "[REDACTED]"
    assert redacted["secret"] == "[REDACTED]"
    assert redacted["admin_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["plaintext_secret"] == "[REDACTED]"
    assert redacted["normal_field"] == "visible"

    # Test prefix-based redaction
    payload = {
        "encrypted_data": "base64-encrypted",
        "encrypted_token": "encrypted-token-value",
        "other_field": "visible",
    }
    redacted = _redact_sensitive(payload)
    assert redacted["encrypted_data"] == "[REDACTED]"
    assert redacted["encrypted_token"] == "[REDACTED]"
    assert redacted["other_field"] == "visible"

    # Test nested dict redaction
    payload = {
        "user": {
            "name": "John",
            "password": "secret-password",
        },
        "config": {
            "api_key": "nested-api-key",
            "setting": "visible",
        },
    }
    redacted = _redact_sensitive(payload)
    assert redacted["user"]["name"] == "John"
    assert redacted["user"]["password"] == "[REDACTED]"
    assert redacted["config"]["api_key"] == "[REDACTED]"
    assert redacted["config"]["setting"] == "visible"

    # Test empty payload
    assert _redact_sensitive({}) == {}
    assert _redact_sensitive(None) == {}


def test_job_requested_event_has_payload_with_job_id(tmp_path: Path, monkeypatch):
    """Test that JOB_REQUESTED events have job_id in payload."""
    app = _make_app(monkeypatch, tmp_path, Path("bundles/finance-pilot").resolve())

    with TestClient(app) as client:
        # Create institution
        slug = f"t-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": slug, "display_name": "Test Job Payload"},
        )
        assert resp.status_code in (200, 201), resp.text
        institution_id = resp.json()["institution_id"]

        # Bootstrap admin key
        resp = client.post(
            f"/admin/institutions/{institution_id}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        assert resp.status_code in (200, 201), resp.text
        admin_key = resp.json()["plaintext_secret"]

        # Create an owner actor token
        resp = client.post(
            f"/admin/institutions/{institution_id}/actors",
            headers={"X-Institution-Id": institution_id, "X-Admin-Key": admin_key},
            json={"actor_id": "test-owner", "roles": ["owner"]},
        )
        assert resp.status_code == 200, resp.text
        owner_token = resp.json()["token"]

        # Create a job (files.list is safe=true, should create job directly)
        resp = client.post(
            "/personal/jobs/files/list",
            json={"path": "/test"},
            headers={
                "X-Institution-Id": institution_id,
                "X-Actor-Token": owner_token,
            },
        )
        assert resp.status_code in (200, 201, 202), resp.text
        job_id = resp.json().get("job_id")
        assert job_id, "Expected job_id in response"

        # Query ledger for JOB_REQUESTED events
        resp = client.get(
            "/v1/observe/ledger/events",
            params={"event_type": "JOB_REQUESTED", "limit": 10},
            headers={"X-Institution-Id": institution_id, "X-Admin-Key": admin_key},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        events = data.get("events", [])
        assert len(events) > 0, "Expected at least one JOB_REQUESTED event"

        # Find the event for our job_id
        job_events = [e for e in events if e.get("payload", {}).get("job_id") == job_id]
        assert len(job_events) >= 1, f"JOB_REQUESTED event not found for {job_id}"

        # Verify payload structure
        event = job_events[0]
        assert event["event_type"] == "JOB_REQUESTED"
        assert event["payload"]["job_id"] == job_id
        assert "job_type" in event["payload"]

