"""Audit Ledger - append-only JSONL with hash-chain."""

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from engine import __version__ as ENGINE_VERSION
from engine.core.request_context import get_request_id
from engine.core.data_root import resolve_namespaced_path


DEFAULT_LEDGER_REL_PATH = "audit_ledger.jsonl"
DEFAULT_LEDGER_PATH = "var/audit_ledger.jsonl"  # Legacy for backward compatibility
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"
GENESIS_HASH = "GENESIS"


def get_ledger_path_for_institution(institution_id: str) -> Path:
    """Get ledger path for a specific institution.

    Uses ENV ENGINE_LEDGER_PATH with namespacing rules:
    - If None: use institution_root/audit_ledger.jsonl
    - If absolute: use absolute path
    - If relative: use institution_root/<relative>

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to ledger file.
    """
    env_value = os.environ.get("ENGINE_LEDGER_PATH")
    return resolve_namespaced_path(institution_id, env_value, DEFAULT_LEDGER_REL_PATH)


@dataclass
class LedgerEvent:
    """Audit ledger event."""
    event_type: str
    tenant_id: str
    actor_id: str
    actor_roles: List[str]
    case_id: str
    step: str
    payload: Dict[str, Any]
    bundle_manifest_sha256: str
    contract_ledger_sha256: str
    engine_version: str
    seq: int = 0
    prev_hash: str = GENESIS_HASH
    hash: str = ""
    timestamp: str = ""
    request_id: Optional[str] = None

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Convert to canonical dict for hashing (sorted keys, sorted roles)."""
        return {
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "case_id": self.case_id,
            "contract_ledger_sha256": self.contract_ledger_sha256,
            "engine_version": self.engine_version,
            "event_type": self.event_type,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "request_id": self.request_id,
            "seq": self.seq,
            "step": self.step,
            "tenant_id": self.tenant_id,
            "timestamp": self.timestamp,
            "actor": {
                "id": self.actor_id,
                "roles": sorted(self.actor_roles),
            },
        }

    def to_storage_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage (includes hash)."""
        d = self.to_canonical_dict()
        d["hash"] = self.hash
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LedgerEvent":
        """Create from storage dict."""
        actor = d.get("actor", {})
        return cls(
            event_type=d.get("event_type", ""),
            tenant_id=d.get("tenant_id", ""),
            actor_id=actor.get("id", ""),
            actor_roles=actor.get("roles", []),
            case_id=d.get("case_id", ""),
            step=d.get("step", ""),
            payload=d.get("payload", {}),
            bundle_manifest_sha256=d.get("bundle_manifest_sha256", ""),
            contract_ledger_sha256=d.get("contract_ledger_sha256", ""),
            engine_version=d.get("engine_version", ""),
            seq=d.get("seq", 0),
            prev_hash=d.get("prev_hash", GENESIS_HASH),
            hash=d.get("hash", ""),
            timestamp=d.get("timestamp", ""),
            request_id=d.get("request_id"),  # None for old events without request_id
        )


def compute_event_hash(event: LedgerEvent) -> str:
    """Compute SHA-256 hash of canonical event representation."""
    canonical = event.to_canonical_dict()
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def verify_event_hash(event: LedgerEvent) -> bool:
    """Verify that event hash matches its content."""
    expected = compute_event_hash(event)
    return event.hash == expected


@dataclass
class VerifyResult:
    """Result of ledger verification."""
    ok: bool
    code: Optional[str] = None
    message: Optional[str] = None
    bad_line: Optional[int] = None
    bad_seq: Optional[int] = None
    bad_event_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for logging/API."""
        return {
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
            "bad_line": self.bad_line,
            "bad_seq": self.bad_seq,
            "bad_event_id": self.bad_event_id,
        }


@dataclass
class HistoryResult:
    """Result of history query."""
    actors: Set[str] = field(default_factory=set)
    count: int = 0
    last_actor: Optional[str] = None
    last_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API response."""
        return {
            "actors": list(self.actors),
            "count": self.count,
            "last_actor": self.last_actor,
            "last_at": self.last_at,
        }


class AuditLedger:
    """Append-only audit ledger with hash-chain."""

    def __init__(self, ledger_path: Optional[Path] = None) -> None:
        """Initialize ledger.

        Args:
            ledger_path: Path to JSONL file. Uses ENV or default if None.
        """
        if ledger_path is None:
            env_path = os.environ.get("ENGINE_LEDGER_PATH")
            ledger_path = Path(env_path) if env_path else Path(DEFAULT_LEDGER_PATH)

        self._path = ledger_path
        self._lock = threading.Lock()

        # Per-tenant state: {tenant_id: (seq, last_hash)}
        self._tenant_state: Dict[str, tuple[int, str]] = {}

        # Bundle hashes (set by loader)
        self._bundle_manifest_sha256: str = ""
        self._contract_ledger_sha256: str = ""

        # Load existing events to rebuild state
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing events to rebuild tenant state."""
        if not self._path.exists():
            return

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        event = LedgerEvent.from_dict(d)
                        tenant_id = event.tenant_id
                        self._tenant_state[tenant_id] = (event.seq, event.hash)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            pass

    def set_bundle_hashes(
        self,
        bundle_manifest_sha256: str,
        contract_ledger_sha256: str,
    ) -> None:
        """Set bundle hashes for new events."""
        self._bundle_manifest_sha256 = bundle_manifest_sha256
        self._contract_ledger_sha256 = contract_ledger_sha256

    def _get_tenant_state(self, tenant_id: str) -> tuple[int, str]:
        """Get current (seq, prev_hash) for tenant."""
        return self._tenant_state.get(tenant_id, (0, GENESIS_HASH))

    def append(
        self,
        event_type: str,
        tenant_id: str,
        actor_id: str,
        actor_roles: List[str],
        case_id: str,
        step: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[LedgerEvent]:
        """Append event to ledger.

        Args:
            event_type: Type of event (e.g., RBAC_DECISION).
            tenant_id: Tenant UUID.
            actor_id: Actor UUID.
            actor_roles: Actor's roles.
            case_id: Case identifier.
            step: Step identifier.
            payload: Event-specific payload.

        Returns:
            The appended event, or None if append failed.
        """
        with self._lock:
            # Get tenant state
            current_seq, prev_hash = self._get_tenant_state(tenant_id)
            new_seq = current_seq + 1

            # Create event
            event = LedgerEvent(
                event_type=event_type,
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_roles=list(actor_roles),
                case_id=case_id,
                step=step,
                payload=payload or {},
                bundle_manifest_sha256=self._bundle_manifest_sha256,
                contract_ledger_sha256=self._contract_ledger_sha256,
                engine_version=ENGINE_VERSION,
                seq=new_seq,
                prev_hash=prev_hash,
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=get_request_id(),  # from contextvar
            )

            # Compute hash
            event.hash = compute_event_hash(event)

            # Ensure directory exists
            self._path.parent.mkdir(parents=True, exist_ok=True)

            # Append to file
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    line = json.dumps(event.to_storage_dict(), sort_keys=True)
                    f.write(line + "\n")
            except Exception:
                return None

            # Update tenant state
            self._tenant_state[tenant_id] = (new_seq, event.hash)

            return event

    def history(self, case_id: str, step: str) -> HistoryResult:
        """Query history for a case/step.

        Args:
            case_id: Case identifier.
            step: Step identifier.

        Returns:
            HistoryResult with actors, count, last_actor, last_at.
        """
        result = HistoryResult()

        if not self._path.exists():
            return result

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        if d.get("case_id") == case_id and d.get("step") == step:
                            event = LedgerEvent.from_dict(d)
                            result.actors.add(event.actor_id)
                            result.count += 1
                            result.last_actor = event.actor_id
                            result.last_at = event.timestamp
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            pass

        return result

    def verify_chain(self, tenant_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """Verify hash-chain integrity.

        Args:
            tenant_id: Optional tenant to verify. If None, verifies all.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not self._path.exists():
            return True, None

        # Track per-tenant state for verification
        tenant_chains: Dict[str, tuple[int, str]] = {}

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        d = json.loads(line)
                        event = LedgerEvent.from_dict(d)
                    except (json.JSONDecodeError, KeyError) as e:
                        return False, f"Line {line_num}: Invalid JSON - {e}"

                    # Filter by tenant if specified
                    if tenant_id and event.tenant_id != tenant_id:
                        continue

                    # Verify hash
                    if not verify_event_hash(event):
                        return False, f"Line {line_num}: Hash mismatch for event seq={event.seq}"

                    # Verify chain
                    expected_seq, expected_prev = tenant_chains.get(
                        event.tenant_id, (0, GENESIS_HASH)
                    )

                    if event.seq != expected_seq + 1:
                        return False, f"Line {line_num}: Seq gap - expected {expected_seq + 1}, got {event.seq}"

                    if event.prev_hash != expected_prev:
                        return False, f"Line {line_num}: Chain broken - prev_hash mismatch"

                    # Update tenant chain
                    tenant_chains[event.tenant_id] = (event.seq, event.hash)

        except Exception as e:
            return False, f"Failed to read ledger: {e}"

        return True, None

    def get_all_events(self) -> List[LedgerEvent]:
        """Get all events (for testing)."""
        events = []
        if not self._path.exists():
            return events

        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    events.append(LedgerEvent.from_dict(d))
                except (json.JSONDecodeError, KeyError):
                    continue

        return events


# Global ledger instance (default institution)
_ledger: Optional[AuditLedger] = None

# Per-institution ledger instances
_institution_ledgers: Dict[str, AuditLedger] = {}
_institution_ledgers_lock = threading.Lock()


def get_ledger() -> Optional[AuditLedger]:
    """Get the global ledger instance (default institution)."""
    return _ledger


def set_ledger(ledger: Optional[AuditLedger]) -> None:
    """Set the global ledger instance (default institution)."""
    global _ledger
    _ledger = ledger


def get_ledger_for_institution(institution_id: str) -> AuditLedger:
    """Get or create ledger for a specific institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        AuditLedger instance for the institution.
    """
    # Import here to avoid circular dependency
    from engine.core.institution_context import DEFAULT_INSTITUTION_ID

    # For default institution, use the global ledger if set
    if institution_id == DEFAULT_INSTITUTION_ID:
        if _ledger is not None:
            return _ledger

    with _institution_ledgers_lock:
        if institution_id not in _institution_ledgers:
            ledger_path = get_ledger_path_for_institution(institution_id)
            _institution_ledgers[institution_id] = AuditLedger(ledger_path)
        return _institution_ledgers[institution_id]


def reset_institution_ledgers() -> None:
    """Reset all per-institution ledgers (for testing)."""
    global _institution_ledgers
    with _institution_ledgers_lock:
        _institution_ledgers = {}


def init_ledger(ledger_path: Optional[Path] = None) -> AuditLedger:
    """Initialize and set the global ledger (default institution)."""
    ledger = AuditLedger(ledger_path)
    set_ledger(ledger)
    return ledger


def init_ledger_for_institution(institution_id: str) -> AuditLedger:
    """Initialize ledger for a specific institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Initialized AuditLedger instance.
    """
    ledger_path = get_ledger_path_for_institution(institution_id)
    ledger = AuditLedger(ledger_path)

    # Import here to avoid circular dependency
    from engine.core.institution_context import DEFAULT_INSTITUTION_ID

    # If default institution, also set as global ledger
    if institution_id == DEFAULT_INSTITUTION_ID:
        set_ledger(ledger)

    with _institution_ledgers_lock:
        _institution_ledgers[institution_id] = ledger

    return ledger


def verify_ledger_file(ledger_path: Path) -> VerifyResult:
    """Verify ledger file integrity before loading.

    This is a standalone function that can be called before initializing
    the full AuditLedger, suitable for boot-time verification.

    Args:
        ledger_path: Path to the ledger file.

    Returns:
        VerifyResult with details about verification outcome.
    """
    from engine.core.errors import LEDGER_TAMPER_DETECTED, LEDGER_VERIFY_UNAVAILABLE

    if not ledger_path.exists():
        # No ledger file is OK
        return VerifyResult(ok=True)

    # Track per-tenant state for verification
    tenant_chains: Dict[str, tuple[int, str]] = {}

    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                # Parse JSON
                try:
                    d = json.loads(line)
                except json.JSONDecodeError as e:
                    return VerifyResult(
                        ok=False,
                        code=LEDGER_TAMPER_DETECTED,
                        message=f"Invalid JSON at line {line_num}: {e}",
                        bad_line=line_num,
                    )

                # Check required fields
                required_fields = ["event_type", "tenant_id", "seq", "prev_hash", "hash", "actor"]
                missing = [f for f in required_fields if f not in d]
                if missing:
                    return VerifyResult(
                        ok=False,
                        code=LEDGER_TAMPER_DETECTED,
                        message=f"Missing fields at line {line_num}: {missing}",
                        bad_line=line_num,
                    )

                # Create event and verify hash
                try:
                    event = LedgerEvent.from_dict(d)
                except Exception as e:
                    return VerifyResult(
                        ok=False,
                        code=LEDGER_TAMPER_DETECTED,
                        message=f"Invalid event structure at line {line_num}: {e}",
                        bad_line=line_num,
                    )

                # Verify hash matches content
                expected_hash = compute_event_hash(event)
                if event.hash != expected_hash:
                    return VerifyResult(
                        ok=False,
                        code=LEDGER_TAMPER_DETECTED,
                        message=f"Hash mismatch at line {line_num}",
                        bad_line=line_num,
                        bad_seq=event.seq,
                        bad_event_id=event.case_id,
                    )

                # Verify chain continuity
                expected_seq, expected_prev = tenant_chains.get(
                    event.tenant_id, (0, GENESIS_HASH)
                )

                if event.seq != expected_seq + 1:
                    return VerifyResult(
                        ok=False,
                        code=LEDGER_TAMPER_DETECTED,
                        message=f"Sequence gap at line {line_num}: expected {expected_seq + 1}, got {event.seq}",
                        bad_line=line_num,
                        bad_seq=event.seq,
                    )

                if event.prev_hash != expected_prev:
                    return VerifyResult(
                        ok=False,
                        code=LEDGER_TAMPER_DETECTED,
                        message=f"Chain broken at line {line_num}: prev_hash mismatch",
                        bad_line=line_num,
                        bad_seq=event.seq,
                    )

                # Update chain state
                tenant_chains[event.tenant_id] = (event.seq, event.hash)

    except IOError as e:
        return VerifyResult(
            ok=False,
            code=LEDGER_VERIFY_UNAVAILABLE,
            message=f"Failed to read ledger: {e}",
        )
    except Exception as e:
        return VerifyResult(
            ok=False,
            code=LEDGER_VERIFY_UNAVAILABLE,
            message=f"Unexpected error verifying ledger: {e}",
        )

    return VerifyResult(ok=True)
