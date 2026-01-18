"""Tests for institution creation ledger events."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry
from engine.core.ledger import set_ledger, AuditLedger, get_ledger


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    """Create a temporary ledger path."""
    return tmp_path / "audit_ledger.jsonl"


@pytest.fixture(autouse=True)
def reset_state(tmp_path, ledger_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

    reset_registry()
    set_ledger(None)

    # Initialize ledger
    ledger = AuditLedger(ledger_path)
    set_ledger(ledger)

    yield

    reset_registry()
    set_ledger(None)


class TestInstitutionCreatedEvent:
    """Test INSTITUTION_CREATED ledger event."""

    def test_create_emits_institution_created_event(self, tmp_path, ledger_path, monkeypatch):
        """Creating institution emits INSTITUTION_CREATED event."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "ledger-test-inst", "display_name": "Ledger Test"},
        )
        assert response.status_code == 201
        created_data = response.json()

        # Read ledger
        with open(ledger_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        assert len(lines) >= 1

        # Find INSTITUTION_CREATED event
        events = [json.loads(line) for line in lines]
        created_events = [e for e in events if e["event_type"] == "INSTITUTION_CREATED"]

        assert len(created_events) == 1
        event = created_events[0]

        assert event["event_type"] == "INSTITUTION_CREATED"

    def test_event_has_correct_case_id(self, tmp_path, ledger_path, monkeypatch):
        """INSTITUTION_CREATED event has case_id = institution_id."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "case-id-test", "display_name": "Case ID Test"},
        )
        assert response.status_code == 201
        created_data = response.json()
        institution_id = created_data["institution_id"]

        # Read ledger and find event
        with open(ledger_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        events = [json.loads(line) for line in lines]
        created_events = [e for e in events if e["event_type"] == "INSTITUTION_CREATED"]

        assert len(created_events) == 1
        event = created_events[0]

        # case_id should be the institution_id
        assert event["case_id"] == institution_id

    def test_event_has_correct_step(self, tmp_path, ledger_path, monkeypatch):
        """INSTITUTION_CREATED event has step = ADMIN:institution.create."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "step-test"},
        )
        assert response.status_code == 201

        # Read ledger and find event
        with open(ledger_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        events = [json.loads(line) for line in lines]
        created_events = [e for e in events if e["event_type"] == "INSTITUTION_CREATED"]

        assert len(created_events) == 1
        event = created_events[0]

        assert event["step"] == "ADMIN:institution.create"

    def test_event_payload_contains_slug(self, tmp_path, ledger_path, monkeypatch):
        """INSTITUTION_CREATED event payload contains slug."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "payload-slug-test", "display_name": "Payload Test"},
        )
        assert response.status_code == 201

        # Read ledger and find event
        with open(ledger_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        events = [json.loads(line) for line in lines]
        created_events = [e for e in events if e["event_type"] == "INSTITUTION_CREATED"]

        assert len(created_events) == 1
        event = created_events[0]

        assert event["payload"]["slug"] == "payload-slug-test"

    def test_event_payload_contains_display_name(self, tmp_path, ledger_path, monkeypatch):
        """INSTITUTION_CREATED event payload contains display_name."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "display-name-test", "display_name": "My Display Name"},
        )
        assert response.status_code == 201

        # Read ledger and find event
        with open(ledger_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        events = [json.loads(line) for line in lines]
        created_events = [e for e in events if e["event_type"] == "INSTITUTION_CREATED"]

        assert len(created_events) == 1
        event = created_events[0]

        assert event["payload"]["display_name"] == "My Display Name"

    def test_event_payload_display_name_null_when_not_provided(self, tmp_path, ledger_path, monkeypatch):
        """INSTITUTION_CREATED event payload has display_name=null when not provided."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "no-display-name"},
        )
        assert response.status_code == 201

        # Read ledger and find event
        with open(ledger_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        events = [json.loads(line) for line in lines]
        created_events = [e for e in events if e["event_type"] == "INSTITUTION_CREATED"]

        assert len(created_events) == 1
        event = created_events[0]

        assert event["payload"]["display_name"] is None

    def test_multiple_creates_emit_multiple_events(self, tmp_path, ledger_path, monkeypatch):
        """Creating multiple institutions emits multiple INSTITUTION_CREATED events."""
        client = TestClient(app, raise_server_exceptions=False)

        slugs = ["multi-event-1", "multi-event-2", "multi-event-3"]
        for slug in slugs:
            response = client.post(
                "/admin/institutions",
                headers={"X-Admin-Token": "test-admin-token"},
                json={"slug": slug},
            )
            assert response.status_code == 201

        # Read ledger
        with open(ledger_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        events = [json.loads(line) for line in lines]
        created_events = [e for e in events if e["event_type"] == "INSTITUTION_CREATED"]

        assert len(created_events) == 3

        # Verify each slug has a corresponding event
        event_slugs = [e["payload"]["slug"] for e in created_events]
        assert set(event_slugs) == set(slugs)

    def test_event_has_hash_chain(self, tmp_path, ledger_path, monkeypatch):
        """INSTITUTION_CREATED events are part of ledger hash chain."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create two institutions
        client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "hash-chain-1"},
        )
        client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": "hash-chain-2"},
        )

        # Read ledger
        with open(ledger_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        events = [json.loads(line) for line in lines]

        # All events should have hash and prev_hash
        for event in events:
            assert "hash" in event
            assert "prev_hash" in event
            assert event["hash"]  # Not empty

        # Second event's prev_hash should be first event's hash (if same tenant)
        if len(events) >= 2:
            # Events are in hash chain
            assert events[1]["prev_hash"] == events[0]["hash"]
