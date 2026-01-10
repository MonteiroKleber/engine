"""Tests for Telemetry events and TelemetryEmitter.

Validates:
1) TelemetryEvent creation and serialization
2) TelemetryCounts and TelemetryFlags
3) TelemetryEmitter stage timing
4) JSON output format
"""

import json
import pytest
import time
import sys
from io import StringIO

from observability.telemetry import (
    TelemetryEmitter,
    TelemetryEvent,
    TelemetryCounts,
    TelemetryFlags,
    BlockedReason,
    init_telemetry,
    get_telemetry,
)


class TestTelemetryEvent:
    """Tests for TelemetryEvent dataclass."""

    def test_event_creation(self):
        """[TelemetryEvent] Basic event creation."""
        event = TelemetryEvent(
            execution_id="exec123",
            project="test",
            stage="intake",
            event="start",
        )

        assert event.execution_id == "exec123"
        assert event.project == "test"
        assert event.stage == "intake"
        assert event.event == "start"
        assert event.ts_iso is not None

    def test_event_with_duration(self):
        """[TelemetryEvent] Event with duration_ms."""
        event = TelemetryEvent(
            execution_id="exec123",
            project="test",
            stage="processing",
            event="end",
            duration_ms=150.5,
        )

        assert event.duration_ms == 150.5

    def test_event_with_counts(self):
        """[TelemetryEvent] Event with counts."""
        counts = TelemetryCounts(
            requirements_count=5,
            entities_count=3,
            operations_count=10,
        )
        event = TelemetryEvent(
            execution_id="exec123",
            project="test",
            stage="processing",
            event="end",
            counts=counts,
        )

        assert event.counts.requirements_count == 5
        assert event.counts.entities_count == 3
        assert event.counts.operations_count == 10

    def test_event_with_flags(self):
        """[TelemetryEvent] Event with flags."""
        flags = TelemetryFlags(
            srs_ok=True,
            ir_ok=True,
            policy_ok=False,
        )
        event = TelemetryEvent(
            execution_id="exec123",
            project="test",
            stage="validation",
            event="end",
            flags=flags,
        )

        assert event.flags.srs_ok is True
        assert event.flags.policy_ok is False

    def test_event_to_dict(self):
        """[TelemetryEvent] to_dict() format."""
        event = TelemetryEvent(
            execution_id="exec123",
            project="test",
            stage="intake",
            event="start",
        )

        d = event.to_dict()

        assert d["execution_id"] == "exec123"
        assert d["project"] == "test"
        assert d["stage"] == "intake"
        assert d["event"] == "start"
        assert "ts_iso" in d

    def test_event_to_json(self):
        """[TelemetryEvent] to_json() produces valid JSON."""
        event = TelemetryEvent(
            execution_id="exec123",
            project="test",
            stage="build",
            event="end",
            duration_ms=200.0,
        )

        json_str = event.to_json()
        parsed = json.loads(json_str)

        assert parsed["event"] == "end"
        assert parsed["duration_ms"] == 200.0


class TestTelemetryCounts:
    """Tests for TelemetryCounts."""

    def test_counts_defaults(self):
        """[TelemetryCounts] Default values are 0."""
        counts = TelemetryCounts()

        assert counts.requirements_count == 0
        assert counts.entities_count == 0
        assert counts.operations_count == 0
        assert counts.tasks_count == 0
        assert counts.patch_count == 0

    def test_counts_to_dict(self):
        """[TelemetryCounts] to_dict() includes all values."""
        counts = TelemetryCounts(requirements_count=5, entities_count=3)

        d = counts.to_dict()

        assert d["requirements_count"] == 5
        assert d["entities_count"] == 3
        # All values should be present
        assert "operations_count" in d

    def test_counts_all_values(self):
        """[TelemetryCounts] All values can be set."""
        counts = TelemetryCounts(
            requirements_count=10,
            entities_count=5,
            operations_count=20,
            tasks_count=15,
            patch_count=8,
        )

        assert counts.requirements_count == 10
        assert counts.patch_count == 8


class TestTelemetryFlags:
    """Tests for TelemetryFlags."""

    def test_flags_defaults(self):
        """[TelemetryFlags] Default values are False."""
        flags = TelemetryFlags()

        assert flags.srs_ok is False
        assert flags.ir_ok is False
        assert flags.policy_ok is False
        assert flags.build_ok is False

    def test_flags_to_dict(self):
        """[TelemetryFlags] to_dict() includes all flags."""
        flags = TelemetryFlags(srs_ok=True, ir_ok=True)

        d = flags.to_dict()

        assert d["srs_ok"] is True
        assert d["ir_ok"] is True
        assert d["policy_ok"] is False


class TestBlockedReason:
    """Tests for BlockedReason constants."""

    def test_blocked_reason_values(self):
        """[BlockedReason] Constants have expected values."""
        assert BlockedReason.BUILD_FAILED == "BUILD_FAILED"
        assert BlockedReason.SMOKE_FAILED == "SMOKE_FAILED"
        assert BlockedReason.DOCKER_UP_FAILED == "DOCKER_UP_FAILED"
        assert BlockedReason.POLICY_FAILED == "POLICY_FAILED"


class TestTelemetryEmitter:
    """Tests for TelemetryEmitter."""

    def test_emitter_creation(self):
        """[TelemetryEmitter] Basic creation."""
        emitter = TelemetryEmitter(
            execution_id="exec123",
            project="test",
        )

        assert emitter.execution_id == "exec123"
        assert emitter.project == "test"

    def test_emitter_emit_start(self, capsys):
        """[TelemetryEmitter] emit_start() writes JSON to stdout."""
        emitter = TelemetryEmitter(
            execution_id="exec123",
            project="test",
        )

        emitter.emit_start("intake")

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["event"] == "start"
        assert event["stage"] == "intake"

    def test_emitter_emit_end(self, capsys):
        """[TelemetryEmitter] emit_end() includes duration."""
        emitter = TelemetryEmitter(
            execution_id="exec123",
            project="test",
        )

        emitter.emit_end("processing", duration_ms=100.5)

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["event"] == "end"
        assert event["stage"] == "processing"
        assert event["duration_ms"] == 100.5

    def test_emitter_stage_context(self, capsys):
        """[TelemetryEmitter] stage() context manager times correctly."""
        emitter = TelemetryEmitter(
            execution_id="exec123",
            project="test",
        )

        with emitter.stage("processing"):
            time.sleep(0.01)  # 10ms

        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')

        assert len(lines) == 2

        start_event = json.loads(lines[0])
        end_event = json.loads(lines[1])

        assert start_event["event"] == "start"
        assert end_event["event"] == "end"
        assert end_event["duration_ms"] >= 10.0

    def test_emitter_update_counts(self, capsys):
        """[TelemetryEmitter] update_counts() affects emitted events."""
        emitter = TelemetryEmitter(
            execution_id="exec123",
            project="test",
        )

        emitter.update_counts(requirements_count=5, entities_count=3)
        emitter.emit_end("processing", duration_ms=50.0)

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert "counts" in event
        assert event["counts"]["requirements_count"] == 5
        assert event["counts"]["entities_count"] == 3

    def test_emitter_set_blocked(self, capsys):
        """[TelemetryEmitter] set_blocked() adds blocked_reason to events."""
        emitter = TelemetryEmitter(
            execution_id="exec123",
            project="test",
        )

        emitter.set_blocked(BlockedReason.BUILD_FAILED)
        emitter.emit_end("build", duration_ms=100.0)

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert event["blocked_reason"] == "BUILD_FAILED"

    def test_emitter_disabled(self, capsys):
        """[TelemetryEmitter] disabled emitter produces no output."""
        emitter = TelemetryEmitter(
            execution_id="exec123",
            project="test",
            enabled=False,
        )

        emitter.emit_start("intake")
        emitter.emit_end("intake", duration_ms=100.0)

        captured = capsys.readouterr()
        assert captured.out == ""


class TestTelemetryInitialization:
    """Tests for telemetry init/get functions."""

    def test_init_and_get_telemetry(self):
        """[init_telemetry/get_telemetry] Basic usage."""
        init_telemetry("exec456", "myproject")

        emitter = get_telemetry()

        assert emitter is not None
        assert emitter.execution_id == "exec456"
        assert emitter.project == "myproject"

    def test_init_telemetry_returns_emitter(self):
        """[init_telemetry] Returns the created emitter."""
        emitter = init_telemetry("exec789", "testproject")

        assert emitter is not None
        assert emitter.execution_id == "exec789"


class TestTelemetryEventWithBlockedReason:
    """Tests for TelemetryEvent with blocked_reason."""

    def test_event_with_blocked_reason(self):
        """[TelemetryEvent] Event with blocked_reason."""
        event = TelemetryEvent(
            execution_id="exec123",
            project="test",
            stage="validation",
            event="end",
            blocked_reason="POLICY_FAILED",
        )

        d = event.to_dict()

        assert d["blocked_reason"] == "POLICY_FAILED"

    def test_event_blocked_reason_in_json(self):
        """[TelemetryEvent] blocked_reason in JSON output."""
        event = TelemetryEvent(
            execution_id="exec123",
            project="test",
            stage="build",
            event="end",
            blocked_reason="BUILD_FAILED",
        )

        json_str = event.to_json()
        parsed = json.loads(json_str)

        assert parsed["blocked_reason"] == "BUILD_FAILED"


class TestTelemetryEmitterFlags:
    """Tests for TelemetryEmitter flag updates."""

    def test_update_flags(self, capsys):
        """[TelemetryEmitter] update_flags() affects emitted events."""
        emitter = TelemetryEmitter(
            execution_id="exec123",
            project="test",
        )

        emitter.update_flags(srs_ok=True, ir_ok=True, policy_ok=False)
        emitter.emit_end("validation", duration_ms=50.0)

        captured = capsys.readouterr()
        event = json.loads(captured.out.strip())

        assert "flags" in event
        assert event["flags"]["srs_ok"] is True
        assert event["flags"]["ir_ok"] is True
        assert event["flags"]["policy_ok"] is False
