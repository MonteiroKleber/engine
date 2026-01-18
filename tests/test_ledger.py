"""Tests for Audit Ledger (Etapa 3.3)."""

import json
import uuid
from pathlib import Path

import pytest

from engine.core.ledger import (
    AuditLedger,
    LedgerEvent,
    HistoryResult,
    compute_event_hash,
    verify_event_hash,
    GENESIS_HASH,
    set_ledger,
    get_ledger,
)
from engine.core.actor_context import DEFAULT_TENANT_ID


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    """Create a temporary ledger path."""
    return tmp_path / "audit_ledger.jsonl"


@pytest.fixture
def ledger(ledger_path: Path) -> AuditLedger:
    """Create a fresh ledger instance."""
    return AuditLedger(ledger_path)


@pytest.fixture(autouse=True)
def reset_global_ledger():
    """Reset global ledger before each test."""
    set_ledger(None)
    yield
    set_ledger(None)


class TestAppendOnly:
    """Test append-only behavior."""

    def test_append_creates_file(self, ledger: AuditLedger, ledger_path: Path):
        """Append should create the ledger file."""
        assert not ledger_path.exists()

        event = ledger.append(
            event_type="TEST_EVENT",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=str(uuid.uuid4()),
            actor_roles=["admin"],
            case_id="case-001",
            step="step-001",
            payload={"test": "data"},
        )

        assert event is not None
        assert ledger_path.exists()

    def test_append_adds_to_file(self, ledger: AuditLedger, ledger_path: Path):
        """Each append should add a new line."""
        actor_id = str(uuid.uuid4())

        # Append multiple events
        for i in range(3):
            ledger.append(
                event_type="TEST_EVENT",
                tenant_id=DEFAULT_TENANT_ID,
                actor_id=actor_id,
                actor_roles=["admin"],
                case_id=f"case-{i}",
                step="step",
            )

        # Count lines
        with open(ledger_path, "r") as f:
            lines = [l for l in f.readlines() if l.strip()]

        assert len(lines) == 3

    def test_append_does_not_modify_existing(self, ledger: AuditLedger, ledger_path: Path):
        """Append should not modify existing entries."""
        actor_id = str(uuid.uuid4())

        # Append first event
        ledger.append(
            event_type="FIRST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor_id,
            actor_roles=["admin"],
            case_id="case-001",
            step="step",
        )

        # Read first line
        with open(ledger_path, "r") as f:
            first_line = f.readline()

        # Append second event
        ledger.append(
            event_type="SECOND",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor_id,
            actor_roles=["admin"],
            case_id="case-002",
            step="step",
        )

        # First line should be unchanged
        with open(ledger_path, "r") as f:
            new_first_line = f.readline()

        assert first_line == new_first_line


class TestSeqMonotonic:
    """Test seq is monotonic per tenant."""

    def test_seq_starts_at_1(self, ledger: AuditLedger):
        """First event should have seq=1."""
        event = ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=str(uuid.uuid4()),
            actor_roles=[],
            case_id="case",
            step="step",
        )

        assert event is not None
        assert event.seq == 1

    def test_seq_increments(self, ledger: AuditLedger):
        """Seq should increment for same tenant."""
        tenant_id = str(uuid.uuid4())
        actor_id = str(uuid.uuid4())

        events = []
        for _ in range(5):
            event = ledger.append(
                event_type="TEST",
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_roles=[],
                case_id="case",
                step="step",
            )
            events.append(event)

        seqs = [e.seq for e in events]
        assert seqs == [1, 2, 3, 4, 5]

    def test_seq_independent_per_tenant(self, ledger: AuditLedger):
        """Each tenant should have independent seq."""
        tenant_a = str(uuid.uuid4())
        tenant_b = str(uuid.uuid4())
        actor_id = str(uuid.uuid4())

        # Interleave events from two tenants
        event_a1 = ledger.append(
            event_type="TEST",
            tenant_id=tenant_a,
            actor_id=actor_id,
            actor_roles=[],
            case_id="case",
            step="step",
        )

        event_b1 = ledger.append(
            event_type="TEST",
            tenant_id=tenant_b,
            actor_id=actor_id,
            actor_roles=[],
            case_id="case",
            step="step",
        )

        event_a2 = ledger.append(
            event_type="TEST",
            tenant_id=tenant_a,
            actor_id=actor_id,
            actor_roles=[],
            case_id="case",
            step="step",
        )

        event_b2 = ledger.append(
            event_type="TEST",
            tenant_id=tenant_b,
            actor_id=actor_id,
            actor_roles=[],
            case_id="case",
            step="step",
        )

        assert event_a1.seq == 1
        assert event_a2.seq == 2
        assert event_b1.seq == 1
        assert event_b2.seq == 2


class TestHashChain:
    """Test hash-chain validity."""

    def test_first_event_has_genesis_prev_hash(self, ledger: AuditLedger):
        """First event should have prev_hash=GENESIS."""
        event = ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=str(uuid.uuid4()),
            actor_roles=[],
            case_id="case",
            step="step",
        )

        assert event.prev_hash == GENESIS_HASH

    def test_chain_links_correctly(self, ledger: AuditLedger):
        """Each event's prev_hash should equal previous event's hash."""
        tenant_id = str(uuid.uuid4())
        actor_id = str(uuid.uuid4())

        events = []
        for _ in range(5):
            event = ledger.append(
                event_type="TEST",
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_roles=[],
                case_id="case",
                step="step",
            )
            events.append(event)

        # Verify chain
        assert events[0].prev_hash == GENESIS_HASH
        for i in range(1, len(events)):
            assert events[i].prev_hash == events[i - 1].hash

    def test_event_hash_is_deterministic(self, ledger: AuditLedger):
        """Same event content should produce same hash."""
        event = LedgerEvent(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id="550e8400-e29b-41d4-a716-446655440000",
            actor_roles=["admin", "viewer"],
            case_id="case-001",
            step="step-001",
            payload={"key": "value"},
            bundle_manifest_sha256="abc123",
            contract_ledger_sha256="def456",
            engine_version="3.3.0",
            seq=1,
            prev_hash=GENESIS_HASH,
            timestamp="2024-01-01T00:00:00+00:00",
        )

        hash1 = compute_event_hash(event)
        hash2 = compute_event_hash(event)

        assert hash1 == hash2

    def test_roles_sorted_in_hash(self, ledger: AuditLedger):
        """Roles should be sorted for canonical hashing."""
        event1 = LedgerEvent(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id="550e8400-e29b-41d4-a716-446655440000",
            actor_roles=["viewer", "admin"],  # Unsorted
            case_id="case-001",
            step="step-001",
            payload={},
            bundle_manifest_sha256="",
            contract_ledger_sha256="",
            engine_version="3.3.0",
            seq=1,
            prev_hash=GENESIS_HASH,
            timestamp="2024-01-01T00:00:00+00:00",
        )

        event2 = LedgerEvent(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id="550e8400-e29b-41d4-a716-446655440000",
            actor_roles=["admin", "viewer"],  # Already sorted
            case_id="case-001",
            step="step-001",
            payload={},
            bundle_manifest_sha256="",
            contract_ledger_sha256="",
            engine_version="3.3.0",
            seq=1,
            prev_hash=GENESIS_HASH,
            timestamp="2024-01-01T00:00:00+00:00",
        )

        # Both should produce same hash due to canonical sorting
        assert compute_event_hash(event1) == compute_event_hash(event2)

    def test_verify_chain_valid(self, ledger: AuditLedger):
        """verify_chain should return True for valid chain."""
        tenant_id = str(uuid.uuid4())
        actor_id = str(uuid.uuid4())

        for _ in range(5):
            ledger.append(
                event_type="TEST",
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_roles=[],
                case_id="case",
                step="step",
            )

        is_valid, error = ledger.verify_chain()
        assert is_valid is True
        assert error is None


class TestTamperDetection:
    """Test tamper detection."""

    def test_tampered_hash_detected(self, ledger: AuditLedger, ledger_path: Path):
        """Modified hash should be detected."""
        actor_id = str(uuid.uuid4())

        # Add events
        for _ in range(3):
            ledger.append(
                event_type="TEST",
                tenant_id=DEFAULT_TENANT_ID,
                actor_id=actor_id,
                actor_roles=[],
                case_id="case",
                step="step",
            )

        # Tamper with the file - modify hash
        with open(ledger_path, "r") as f:
            lines = f.readlines()

        # Modify the hash in second line
        event = json.loads(lines[1])
        event["hash"] = "0" * 64
        lines[1] = json.dumps(event) + "\n"

        with open(ledger_path, "w") as f:
            f.writelines(lines)

        # Create new ledger to verify
        new_ledger = AuditLedger(ledger_path)
        is_valid, error = new_ledger.verify_chain()

        assert is_valid is False
        assert "Hash mismatch" in error

    def test_tampered_content_detected(self, ledger: AuditLedger, ledger_path: Path):
        """Modified content should be detected via hash mismatch."""
        actor_id = str(uuid.uuid4())

        ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor_id,
            actor_roles=[],
            case_id="case",
            step="step",
            payload={"amount": 100},
        )

        # Tamper with payload
        with open(ledger_path, "r") as f:
            line = f.readline()

        event = json.loads(line)
        event["payload"]["amount"] = 999  # Tamper
        # Keep the original hash - this will cause mismatch

        with open(ledger_path, "w") as f:
            f.write(json.dumps(event) + "\n")

        new_ledger = AuditLedger(ledger_path)
        is_valid, error = new_ledger.verify_chain()

        assert is_valid is False

    def test_broken_chain_detected(self, ledger: AuditLedger, ledger_path: Path):
        """Broken chain (wrong prev_hash) should be detected."""
        actor_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        # Add events
        for _ in range(3):
            ledger.append(
                event_type="TEST",
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_roles=[],
                case_id="case",
                step="step",
            )

        # Read all lines
        with open(ledger_path, "r") as f:
            lines = f.readlines()

        # Break the chain - wrong prev_hash in third event
        event = json.loads(lines[2])
        event["prev_hash"] = "wrong_hash"
        # Recompute hash for consistency
        temp_event = LedgerEvent.from_dict(event)
        temp_event.prev_hash = "wrong_hash"
        event["hash"] = compute_event_hash(temp_event)
        lines[2] = json.dumps(event) + "\n"

        with open(ledger_path, "w") as f:
            f.writelines(lines)

        new_ledger = AuditLedger(ledger_path)
        is_valid, error = new_ledger.verify_chain()

        assert is_valid is False
        assert "Chain broken" in error


class TestHistoryEmpty:
    """Test history with no events."""

    def test_history_empty_ledger(self, ledger: AuditLedger):
        """History on empty ledger should return empty result."""
        result = ledger.history("case-001", "step-001")

        assert result.count == 0
        assert len(result.actors) == 0
        assert result.last_actor is None
        assert result.last_at is None

    def test_history_no_matching_events(self, ledger: AuditLedger):
        """History with no matching events should return empty result."""
        actor_id = str(uuid.uuid4())

        # Add events with different case_id
        ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor_id,
            actor_roles=[],
            case_id="other-case",
            step="other-step",
        )

        result = ledger.history("case-001", "step-001")

        assert result.count == 0
        assert len(result.actors) == 0


class TestHistoryMultipleEvents:
    """Test history with multiple events."""

    def test_history_counts_matching_events(self, ledger: AuditLedger):
        """History should count matching events."""
        actor_id = str(uuid.uuid4())

        # Add 3 matching events
        for _ in range(3):
            ledger.append(
                event_type="TEST",
                tenant_id=DEFAULT_TENANT_ID,
                actor_id=actor_id,
                actor_roles=[],
                case_id="case-001",
                step="step-001",
            )

        # Add 2 non-matching events
        for _ in range(2):
            ledger.append(
                event_type="TEST",
                tenant_id=DEFAULT_TENANT_ID,
                actor_id=actor_id,
                actor_roles=[],
                case_id="case-001",
                step="step-other",
            )

        result = ledger.history("case-001", "step-001")

        assert result.count == 3

    def test_history_collects_unique_actors(self, ledger: AuditLedger):
        """History should collect unique actors."""
        actor1 = str(uuid.uuid4())
        actor2 = str(uuid.uuid4())
        actor3 = str(uuid.uuid4())

        # Actor1 twice
        ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor1,
            actor_roles=[],
            case_id="case-001",
            step="step-001",
        )
        ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor1,
            actor_roles=[],
            case_id="case-001",
            step="step-001",
        )

        # Actor2 once
        ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor2,
            actor_roles=[],
            case_id="case-001",
            step="step-001",
        )

        # Actor3 once
        ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor3,
            actor_roles=[],
            case_id="case-001",
            step="step-001",
        )

        result = ledger.history("case-001", "step-001")

        assert result.count == 4
        assert len(result.actors) == 3
        assert actor1 in result.actors
        assert actor2 in result.actors
        assert actor3 in result.actors

    def test_history_tracks_last_actor_and_time(self, ledger: AuditLedger):
        """History should track last actor and timestamp."""
        actor1 = str(uuid.uuid4())
        actor2 = str(uuid.uuid4())

        ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor1,
            actor_roles=[],
            case_id="case-001",
            step="step-001",
        )

        event2 = ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor2,
            actor_roles=[],
            case_id="case-001",
            step="step-001",
        )

        result = ledger.history("case-001", "step-001")

        assert result.last_actor == actor2
        assert result.last_at == event2.timestamp

    def test_history_result_to_dict(self, ledger: AuditLedger):
        """HistoryResult.to_dict should return proper structure."""
        actor_id = str(uuid.uuid4())

        event = ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor_id,
            actor_roles=[],
            case_id="case-001",
            step="step-001",
        )

        result = ledger.history("case-001", "step-001")
        d = result.to_dict()

        assert "actors" in d
        assert "count" in d
        assert "last_actor" in d
        assert "last_at" in d
        assert d["count"] == 1
        assert d["last_actor"] == actor_id


class TestLedgerPersistence:
    """Test ledger state persistence across instances."""

    def test_state_persisted_on_reload(self, ledger_path: Path):
        """Ledger state should persist when reloaded."""
        tenant_id = str(uuid.uuid4())
        actor_id = str(uuid.uuid4())

        # Create first ledger and add events
        ledger1 = AuditLedger(ledger_path)
        for _ in range(3):
            ledger1.append(
                event_type="TEST",
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_roles=[],
                case_id="case",
                step="step",
            )

        # Create second ledger instance
        ledger2 = AuditLedger(ledger_path)

        # Add more events - should continue from seq 4
        event = ledger2.append(
            event_type="TEST",
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_roles=[],
            case_id="case",
            step="step",
        )

        assert event.seq == 4

        # Chain should still be valid
        is_valid, _ = ledger2.verify_chain()
        assert is_valid is True


class TestTenantInvalid:
    """Test TENANT_INVALID error handling."""

    def test_invalid_tenant_id_error(self):
        """Invalid tenant_id should cause TENANT_INVALID error."""
        from engine.core.actor_context import parse_actor_context

        actor_id = str(uuid.uuid4())

        # Valid actor, invalid tenant
        context, error_code, error_message = parse_actor_context(
            actor_id=actor_id,
            actor_roles="admin",
            tenant_id="not-a-valid-uuid",
        )

        assert context is None
        assert error_code == "TENANT_INVALID"
        assert error_message == "Tenant is invalid"

    def test_missing_tenant_uses_default(self):
        """Missing tenant_id should use default."""
        from engine.core.actor_context import parse_actor_context

        actor_id = str(uuid.uuid4())

        context, error_code, _ = parse_actor_context(
            actor_id=actor_id,
            actor_roles="admin",
            tenant_id=None,
        )

        assert context is not None
        assert error_code is None
        assert context.tenant_id == DEFAULT_TENANT_ID


class TestEventSchema:
    """Test event schema compliance."""

    def test_event_has_required_fields(self, ledger: AuditLedger):
        """Event should have all required fields."""
        actor_id = str(uuid.uuid4())

        ledger.set_bundle_hashes("manifest_hash", "ledger_hash")

        event = ledger.append(
            event_type="RBAC_DECISION",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor_id,
            actor_roles=["admin", "viewer"],
            case_id="case-001",
            step="step-001",
            payload={"permission": "expense.create", "decision": "allow"},
        )

        assert event.event_type == "RBAC_DECISION"
        assert event.tenant_id == DEFAULT_TENANT_ID
        assert event.actor_id == actor_id
        assert sorted(event.actor_roles) == ["admin", "viewer"]
        assert event.case_id == "case-001"
        assert event.step == "step-001"
        assert event.payload == {"permission": "expense.create", "decision": "allow"}
        assert event.bundle_manifest_sha256 == "manifest_hash"
        assert event.contract_ledger_sha256 == "ledger_hash"
        assert event.engine_version == "8.1.1"
        assert event.seq >= 1
        assert event.prev_hash
        assert event.hash
        assert event.timestamp

    def test_event_storage_format(self, ledger: AuditLedger, ledger_path: Path):
        """Stored event should have correct JSON structure."""
        actor_id = str(uuid.uuid4())

        ledger.append(
            event_type="TEST",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id=actor_id,
            actor_roles=["admin"],
            case_id="case-001",
            step="step-001",
            payload={"key": "value"},
        )

        with open(ledger_path, "r") as f:
            stored = json.loads(f.readline())

        # Check structure
        assert "event_type" in stored
        assert "tenant_id" in stored
        assert "actor" in stored
        assert "id" in stored["actor"]
        assert "roles" in stored["actor"]
        assert "case_id" in stored
        assert "step" in stored
        assert "payload" in stored
        assert "seq" in stored
        assert "prev_hash" in stored
        assert "hash" in stored
        assert "timestamp" in stored
        assert "bundle_manifest_sha256" in stored
        assert "contract_ledger_sha256" in stored
        assert "engine_version" in stored
