"""Tests for ledger storage namespacing by institution."""

import json
from pathlib import Path

import pytest

from engine.core.data_root import get_institution_root
from engine.core.ledger import (
    AuditLedger,
    get_ledger_path_for_institution,
    get_ledger_for_institution,
    init_ledger_for_institution,
    reset_institution_ledgers,
    set_ledger,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))

    # Clear any ENV overrides for ledger path
    monkeypatch.delenv("ENGINE_LEDGER_PATH", raising=False)

    set_ledger(None)
    reset_institution_ledgers()

    yield

    set_ledger(None)
    reset_institution_ledgers()


class TestLedgerPathResolution:
    """Test ledger path resolution for institutions."""

    def test_default_path_under_institution_root(self, tmp_path, monkeypatch):
        """Default ledger path is under institution root."""
        institution_id = "11111111-1111-1111-1111-111111111111"

        path = get_ledger_path_for_institution(institution_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "audit_ledger.jsonl"

    def test_absolute_env_path_overrides(self, tmp_path, monkeypatch):
        """Absolute ENGINE_LEDGER_PATH overrides institution namespacing."""
        institution_id = "22222222-2222-2222-2222-222222222222"
        absolute_path = tmp_path / "absolute" / "ledger.jsonl"

        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(absolute_path))

        path = get_ledger_path_for_institution(institution_id)

        assert path == absolute_path

    def test_relative_env_path_under_institution_root(self, tmp_path, monkeypatch):
        """Relative ENGINE_LEDGER_PATH is under institution root."""
        institution_id = "33333333-3333-3333-3333-333333333333"

        monkeypatch.setenv("ENGINE_LEDGER_PATH", "custom/audit.jsonl")

        path = get_ledger_path_for_institution(institution_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "custom" / "audit.jsonl"

    def test_different_institutions_different_paths(self, tmp_path, monkeypatch):
        """Different institutions have different ledger paths."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        path_a = get_ledger_path_for_institution(inst_a)
        path_b = get_ledger_path_for_institution(inst_b)

        assert path_a != path_b
        assert inst_a in str(path_a)
        assert inst_b in str(path_b)


class TestLedgerInstanceIsolation:
    """Test ledger instance isolation per institution."""

    def test_get_ledger_returns_institution_specific_instance(self, tmp_path, monkeypatch):
        """get_ledger_for_institution returns institution-specific ledger."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        ledger_a = get_ledger_for_institution(inst_a)
        ledger_b = get_ledger_for_institution(inst_b)

        assert ledger_a is not ledger_b
        assert str(ledger_a._path) != str(ledger_b._path)

    def test_get_ledger_returns_same_instance_for_same_institution(self, tmp_path, monkeypatch):
        """get_ledger_for_institution returns same instance for same institution."""
        institution_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"

        ledger_1 = get_ledger_for_institution(institution_id)
        ledger_2 = get_ledger_for_institution(institution_id)

        assert ledger_1 is ledger_2

    def test_init_ledger_creates_new_instance(self, tmp_path, monkeypatch):
        """init_ledger_for_institution creates new ledger instance."""
        institution_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"

        ledger = init_ledger_for_institution(institution_id)

        assert ledger is not None
        assert institution_id in str(ledger._path)


class TestLedgerDataIsolation:
    """Test that ledger data is isolated per institution."""

    def test_events_written_to_institution_specific_file(self, tmp_path, monkeypatch):
        """Events are written to institution-specific ledger file."""
        institution_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

        ledger = get_ledger_for_institution(institution_id)

        # Write an event
        ledger.append(
            event_type="TEST_EVENT",
            tenant_id=institution_id,
            actor_id="test-actor",
            actor_roles=["admin"],
            step="test:step",
            case_id="test-case-1",
            payload={"test": "data"},
        )

        # Verify file exists at institution-specific path
        expected_path = get_ledger_path_for_institution(institution_id)
        assert expected_path.exists()

        # Read and verify event
        with open(expected_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        assert len(lines) >= 1
        event = json.loads(lines[-1])
        assert event["event_type"] == "TEST_EVENT"

    def test_events_isolated_between_institutions(self, tmp_path, monkeypatch):
        """Events from different institutions are in different files."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        ledger_a = get_ledger_for_institution(inst_a)
        ledger_b = get_ledger_for_institution(inst_b)

        # Write to institution A
        ledger_a.append(
            event_type="EVENT_A",
            tenant_id=inst_a,
            actor_id="actor-a",
            actor_roles=["admin"],
            step="test:a",
            case_id="case-a",
            payload={"inst": "A"},
        )

        # Write to institution B
        ledger_b.append(
            event_type="EVENT_B",
            tenant_id=inst_b,
            actor_id="actor-b",
            actor_roles=["admin"],
            step="test:b",
            case_id="case-b",
            payload={"inst": "B"},
        )

        # Verify isolation - each file only has its own events
        path_a = get_ledger_path_for_institution(inst_a)
        path_b = get_ledger_path_for_institution(inst_b)

        with open(path_a, "r", encoding="utf-8") as f:
            events_a = [json.loads(l) for l in f.readlines() if l.strip()]

        with open(path_b, "r", encoding="utf-8") as f:
            events_b = [json.loads(l) for l in f.readlines() if l.strip()]

        assert len(events_a) == 1
        assert events_a[0]["event_type"] == "EVENT_A"

        assert len(events_b) == 1
        assert events_b[0]["event_type"] == "EVENT_B"


class TestResetLedgers:
    """Test ledger reset functionality."""

    def test_reset_clears_all_institution_ledgers(self, tmp_path, monkeypatch):
        """reset_institution_ledgers clears all cached ledger instances."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        # Create some ledgers
        ledger_a_1 = get_ledger_for_institution(inst_a)
        ledger_b_1 = get_ledger_for_institution(inst_b)

        # Reset
        reset_institution_ledgers()

        # Get again - should be new instances
        ledger_a_2 = get_ledger_for_institution(inst_a)
        ledger_b_2 = get_ledger_for_institution(inst_b)

        assert ledger_a_1 is not ledger_a_2
        assert ledger_b_1 is not ledger_b_2
