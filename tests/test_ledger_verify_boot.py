"""Tests for Ledger Verification at Boot (Fase 4.5)."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy
from engine.core.approvals import set_approvals_policy
from engine.core.sod import set_sod_policy
from engine.core.invariants import set_invariants_policy
from engine.core.state_store import set_state_store
from engine.core.ledger import set_ledger, VerifyResult, verify_ledger_file, GENESIS_HASH
from engine.core.rate_limit import reset_rate_limiter
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    """Create a temporary state store path."""
    return tmp_path / "state_store.json"


@pytest.fixture(autouse=True)
def reset_state(tmp_path: Path, state_path: Path, monkeypatch):
    """Reset all state before each test."""
    # Reset before test
    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_sod_policy(None)
    set_invariants_policy(None)
    set_state_store(None)
    set_ledger(None)
    reset_rate_limiter()

    # Set state path via env
    monkeypatch.setenv("ENGINE_STATE_PATH", str(state_path))

    yield

    # Reset after test - important for tests that enter SAFE_MODE
    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_sod_policy(None)
    set_invariants_policy(None)
    set_state_store(None)
    set_ledger(None)
    reset_rate_limiter()


def create_rbac_json(bundle_path: Path, roles: list) -> str:
    """Create rbac.json and return its SHA-256 hash."""
    rbac_data = {
        "version": "1.0.0",
        "name": "rbac",
        "roles": roles,
    }
    rbac_path = bundle_path / "rbac.json"
    with open(rbac_path, "w", encoding="utf-8") as f:
        json.dump(rbac_data, f)
    return compute_sha256(rbac_path)


def create_minimal_bundle(bundle_path: Path) -> None:
    """Create a minimal valid bundle."""
    bundle_path.mkdir(parents=True, exist_ok=True)

    # Create RBAC
    rbac_hash = create_rbac_json(bundle_path, [
        {"name": "analyst", "permissions": ["expense.create", "expense.read"]},
    ])

    # Create manifest
    manifest = {
        "name": "test-bundle",
        "version": "1.0.0",
        "contracts": [
            {
                "file": "rbac.json",
                "sha256": f"SHA256:{rbac_hash}",
                "required": True,
            },
        ],
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


def create_valid_ledger_event(
    seq: int,
    prev_hash: str,
    tenant_id: str = "00000000-0000-0000-0000-000000000000",
) -> dict:
    """Create a valid ledger event dict with correct hash."""
    actor_id = str(uuid.uuid4())

    # Create canonical representation (without hash)
    canonical = {
        "bundle_manifest_sha256": "test_manifest_hash",
        "case_id": f"case-{seq}",
        "contract_ledger_sha256": "test_ledger_hash",
        "engine_version": "4.5.0",
        "event_type": "TEST_EVENT",
        "payload": {"test": True},
        "prev_hash": prev_hash,
        "request_id": None,
        "seq": seq,
        "step": "test_step",
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": {
            "id": actor_id,
            "roles": ["analyst"],
        },
    }

    # Compute hash
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    event_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    # Return storage format (with hash)
    storage = dict(canonical)
    storage["hash"] = event_hash

    return storage


def create_valid_ledger(ledger_path: Path, num_events: int = 3) -> None:
    """Create a valid ledger file with proper hash chain."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    prev_hash = GENESIS_HASH
    with open(ledger_path, "w", encoding="utf-8") as f:
        for seq in range(1, num_events + 1):
            event = create_valid_ledger_event(seq, prev_hash)
            f.write(json.dumps(event, sort_keys=True) + "\n")
            prev_hash = event["hash"]


def create_tampered_ledger(ledger_path: Path) -> None:
    """Create a ledger file with tampered content (modified payload)."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    # First create a valid event
    event = create_valid_ledger_event(1, GENESIS_HASH)

    # Tamper with the payload after hash was computed
    event["payload"]["tampered"] = True

    with open(ledger_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def create_invalid_json_ledger(ledger_path: Path) -> None:
    """Create a ledger file with invalid JSON."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    with open(ledger_path, "w", encoding="utf-8") as f:
        f.write('{"valid": "event"}\n')  # This will fail required fields check
        f.write('not valid json at all\n')


def create_fresh_app():
    """Create a fresh app instance to ensure lifespan runs with current env vars."""
    # Import here to avoid module-level app creation issues
    import importlib
    import engine.api.server
    importlib.reload(engine.api.server)
    return engine.api.server.app


class TestLedgerAbsent:
    """Test /health 200 when ledger is absent."""

    def test_no_ledger_health_200(self, tmp_path: Path, monkeypatch):
        """When ledger file doesn't exist, /health should return 200."""
        bundle_path = tmp_path / "bundle"
        ledger_path = tmp_path / "ledger" / "audit_ledger.jsonl"

        create_minimal_bundle(bundle_path)

        # Ensure ledger doesn't exist
        assert not ledger_path.exists()

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

        fresh_app = create_fresh_app()
        # Use context manager to ensure lifespan runs
        with TestClient(fresh_app) as client:
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["mode"] == "ACTIVE"


class TestLedgerValid:
    """Test /health 200 when ledger is valid."""

    def test_valid_ledger_health_200(self, tmp_path: Path, monkeypatch):
        """When ledger file is valid, /health should return 200."""
        bundle_path = tmp_path / "bundle"
        ledger_path = tmp_path / "ledger" / "audit_ledger.jsonl"

        create_minimal_bundle(bundle_path)
        create_valid_ledger(ledger_path, num_events=3)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

        fresh_app = create_fresh_app()
        # Use context manager to ensure lifespan runs
        with TestClient(fresh_app) as client:
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["mode"] == "ACTIVE"


class TestLedgerTampered:
    """Test /health 503 when ledger is tampered."""

    def test_tampered_ledger_health_503(self, tmp_path: Path, monkeypatch):
        """When ledger file is tampered, /health should return 503 SAFE_MODE."""
        bundle_path = tmp_path / "bundle"
        ledger_path = tmp_path / "ledger" / "audit_ledger.jsonl"

        create_minimal_bundle(bundle_path)
        create_tampered_ledger(ledger_path)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

        fresh_app = create_fresh_app()
        # Use context manager to ensure lifespan runs
        with TestClient(fresh_app) as client:
            response = client.get("/health")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["mode"] == "SAFE_MODE"
            assert data["reason_code"] == "LEDGER_TAMPER_DETECTED"


class TestLedgerInvalidJson:
    """Test /health 503 when ledger has invalid JSON."""

    def test_invalid_json_ledger_health_503(self, tmp_path: Path, monkeypatch):
        """When ledger file has invalid JSON, /health should return 503 SAFE_MODE."""
        bundle_path = tmp_path / "bundle"
        ledger_path = tmp_path / "ledger" / "audit_ledger.jsonl"

        create_minimal_bundle(bundle_path)
        create_invalid_json_ledger(ledger_path)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_path))
        monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

        fresh_app = create_fresh_app()
        # Use context manager to ensure lifespan runs
        with TestClient(fresh_app) as client:
            response = client.get("/health")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["mode"] == "SAFE_MODE"
            assert data["reason_code"] == "LEDGER_TAMPER_DETECTED"


class TestVerifyLedgerFileUnit:
    """Unit tests for verify_ledger_file function."""

    def test_verify_nonexistent_ledger_ok(self, tmp_path: Path):
        """Verify non-existent ledger should return ok=True."""
        ledger_path = tmp_path / "nonexistent.jsonl"
        result = verify_ledger_file(ledger_path)
        assert result.ok is True

    def test_verify_valid_ledger_ok(self, tmp_path: Path):
        """Verify valid ledger should return ok=True."""
        ledger_path = tmp_path / "valid.jsonl"
        create_valid_ledger(ledger_path, num_events=5)

        result = verify_ledger_file(ledger_path)
        assert result.ok is True
        assert result.code is None

    def test_verify_tampered_ledger_fails(self, tmp_path: Path):
        """Verify tampered ledger should return ok=False with LEDGER_TAMPER_DETECTED."""
        ledger_path = tmp_path / "tampered.jsonl"
        create_tampered_ledger(ledger_path)

        result = verify_ledger_file(ledger_path)
        assert result.ok is False
        assert result.code == "LEDGER_TAMPER_DETECTED"
        assert result.bad_line == 1

    def test_verify_invalid_json_fails(self, tmp_path: Path):
        """Verify ledger with invalid JSON should return ok=False."""
        ledger_path = tmp_path / "invalid.jsonl"
        create_invalid_json_ledger(ledger_path)

        result = verify_ledger_file(ledger_path)
        assert result.ok is False
        assert result.code == "LEDGER_TAMPER_DETECTED"
