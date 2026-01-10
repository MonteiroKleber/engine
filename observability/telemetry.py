"""Telemetry - Deterministic structured logging for pipeline observability.

Emits JSON events to stdout for each pipeline stage:
- stage_start: When a stage begins
- stage_end: When a stage completes (with duration_ms)

Events include:
- execution_id, project, stage, event type
- counts (requirements, entities, operations, tasks, patches)
- flags (srs_ok, ir_ok, contracts_ok, plan_ok, policy_ok, build_ok, release_ok)
- blocked_reason (when pipeline is blocked)
"""

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Generator, Optional


# Canonical blocked reasons
class BlockedReason:
    GATE1_FAILED = "GATE1_FAILED"
    GATE2_BLOCKED = "GATE2_BLOCKED"
    SRS_BLOCKED_QUESTIONS = "SRS_BLOCKED_QUESTIONS"
    IR_EMPTY = "IR_EMPTY"
    IR_VALIDATION_FAILED = "IR_VALIDATION_FAILED"
    POLICY_FAILED = "POLICY_FAILED"
    CONTRACTS_POLICY_FAILED = "CONTRACTS_POLICY_FAILED"
    CONTRACT_GATE_FAILED = "CONTRACT_GATE_FAILED"  # ContractLedger integrity failure
    PLAN_POLICY_FAILED = "PLAN_POLICY_FAILED"
    PATCH_SECURITY = "PATCH_SECURITY"
    PATCH_FAILED = "PATCH_FAILED"
    BUILD_FAILED = "BUILD_FAILED"
    LEGACY_CONTRACT_GATE_FAILED = "LEGACY_CONTRACT_GATE_FAILED"
    LEGACY_SCHEMA_INVALID = "LEGACY_SCHEMA_INVALID"
    FIX_LOOP_EXHAUSTED = "FIX_LOOP_EXHAUSTED"
    DOCKER_UP_FAILED = "DOCKER_UP_FAILED"
    SMOKE_FAILED = "SMOKE_FAILED"
    READINESS_FAILED = "READINESS_FAILED"


@dataclass
class TelemetryCounts:
    """Counts tracked during pipeline execution."""

    requirements_count: int = 0
    entities_count: int = 0
    operations_count: int = 0
    tasks_count: int = 0
    patch_count: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "requirements_count": self.requirements_count,
            "entities_count": self.entities_count,
            "operations_count": self.operations_count,
            "tasks_count": self.tasks_count,
            "patch_count": self.patch_count,
        }


@dataclass
class TelemetryFlags:
    """Flags tracked during pipeline execution."""

    srs_ok: bool = False
    ir_ok: bool = False
    contracts_ok: bool = False
    plan_ok: bool = False
    policy_ok: bool = False
    build_ok: bool = False
    release_ok: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return {
            "srs_ok": self.srs_ok,
            "ir_ok": self.ir_ok,
            "contracts_ok": self.contracts_ok,
            "plan_ok": self.plan_ok,
            "policy_ok": self.policy_ok,
            "build_ok": self.build_ok,
            "release_ok": self.release_ok,
        }


@dataclass
class TelemetryEvent:
    """A single telemetry event."""

    execution_id: str
    project: str
    stage: str
    event: str  # "start" or "end"
    ts_iso: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: Optional[float] = None
    counts: Optional[TelemetryCounts] = None
    flags: Optional[TelemetryFlags] = None
    blocked_reason: str = ""
    input_mode_detected: str = ""
    input_mode_used: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "execution_id": self.execution_id,
            "project": self.project,
            "stage": self.stage,
            "event": self.event,
            "ts_iso": self.ts_iso,
        }

        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms

        if self.counts is not None:
            result["counts"] = self.counts.to_dict()

        if self.flags is not None:
            result["flags"] = self.flags.to_dict()

        if self.blocked_reason:
            result["blocked_reason"] = self.blocked_reason

        if self.input_mode_detected:
            result["input_mode_detected"] = self.input_mode_detected

        if self.input_mode_used:
            result["input_mode_used"] = self.input_mode_used

        return result

    def to_json(self) -> str:
        """Serialize to canonical JSON (single line)."""
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
        )


class TelemetryEmitter:
    """Emits telemetry events to stdout.

    Usage:
        emitter = TelemetryEmitter("exec_123", "myproject")

        with emitter.stage("intake"):
            # do work
            emitter.update_counts(requirements_count=5)

        emitter.set_blocked("SRS_BLOCKED_QUESTIONS")
    """

    def __init__(
        self,
        execution_id: str,
        project: str,
        enabled: bool = True,
    ) -> None:
        self.execution_id = execution_id
        self.project = project
        self.enabled = enabled
        self.counts = TelemetryCounts()
        self.flags = TelemetryFlags()
        self._blocked_reason = ""
        self._input_mode_detected = ""
        self._input_mode_used = ""

    def emit(self, event: TelemetryEvent) -> None:
        """Emit a telemetry event to stdout."""
        if self.enabled:
            print(event.to_json())

    def emit_start(self, stage: str) -> None:
        """Emit a stage start event."""
        event = TelemetryEvent(
            execution_id=self.execution_id,
            project=self.project,
            stage=stage,
            event="start",
            input_mode_detected=self._input_mode_detected,
            input_mode_used=self._input_mode_used,
        )
        self.emit(event)

    def emit_end(self, stage: str, duration_ms: float) -> None:
        """Emit a stage end event."""
        event = TelemetryEvent(
            execution_id=self.execution_id,
            project=self.project,
            stage=stage,
            event="end",
            duration_ms=duration_ms,
            counts=self.counts,
            flags=self.flags,
            blocked_reason=self._blocked_reason,
            input_mode_detected=self._input_mode_detected,
            input_mode_used=self._input_mode_used,
        )
        self.emit(event)

    def set_blocked(self, reason: str) -> None:
        """Set the blocked reason."""
        self._blocked_reason = reason

    def set_input_mode(self, detected: str, used: str) -> None:
        """Set the input mode information."""
        self._input_mode_detected = detected
        self._input_mode_used = used

    def update_counts(
        self,
        requirements_count: Optional[int] = None,
        entities_count: Optional[int] = None,
        operations_count: Optional[int] = None,
        tasks_count: Optional[int] = None,
        patch_count: Optional[int] = None,
    ) -> None:
        """Update counts."""
        if requirements_count is not None:
            self.counts.requirements_count = requirements_count
        if entities_count is not None:
            self.counts.entities_count = entities_count
        if operations_count is not None:
            self.counts.operations_count = operations_count
        if tasks_count is not None:
            self.counts.tasks_count = tasks_count
        if patch_count is not None:
            self.counts.patch_count = patch_count

    def update_flags(
        self,
        srs_ok: Optional[bool] = None,
        ir_ok: Optional[bool] = None,
        contracts_ok: Optional[bool] = None,
        plan_ok: Optional[bool] = None,
        policy_ok: Optional[bool] = None,
        build_ok: Optional[bool] = None,
        release_ok: Optional[bool] = None,
    ) -> None:
        """Update flags."""
        if srs_ok is not None:
            self.flags.srs_ok = srs_ok
        if ir_ok is not None:
            self.flags.ir_ok = ir_ok
        if contracts_ok is not None:
            self.flags.contracts_ok = contracts_ok
        if plan_ok is not None:
            self.flags.plan_ok = plan_ok
        if policy_ok is not None:
            self.flags.policy_ok = policy_ok
        if build_ok is not None:
            self.flags.build_ok = build_ok
        if release_ok is not None:
            self.flags.release_ok = release_ok

    @contextmanager
    def stage(self, stage_name: str) -> Generator[None, None, None]:
        """Context manager for timing a stage.

        Usage:
            with emitter.stage("intake"):
                # do work here
        """
        self.emit_start(stage_name)
        start_time = time.perf_counter()
        try:
            yield
        finally:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            self.emit_end(stage_name, duration_ms)


# Global singleton for convenience (optional use)
_global_emitter: Optional[TelemetryEmitter] = None


def init_telemetry(execution_id: str, project: str, enabled: bool = True) -> TelemetryEmitter:
    """Initialize global telemetry emitter."""
    global _global_emitter
    _global_emitter = TelemetryEmitter(execution_id, project, enabled)
    return _global_emitter


def get_telemetry() -> Optional[TelemetryEmitter]:
    """Get global telemetry emitter."""
    return _global_emitter
