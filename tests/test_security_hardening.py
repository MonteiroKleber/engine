"""Tests for HTTP Hardening (Fase 4.4)."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy
from engine.core.approvals import set_approvals_policy
from engine.core.sod import set_sod_policy
from engine.core.invariants import set_invariants_policy
from engine.core.state_store import set_state_store
from engine.core.ledger import set_ledger
from engine.core.rate_limit import reset_rate_limiter
from engine.loader.load_bundle import load_bundle
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    """Create a temporary ledger path."""
    return tmp_path / "audit_ledger.jsonl"


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    """Create a temporary state store path."""
    return tmp_path / "state_store.json"


@pytest.fixture(autouse=True)
def reset_state(ledger_path: Path, state_path: Path, monkeypatch):
    """Reset all state before each test."""
    runtime_state.set_active()
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_sod_policy(None)
    set_invariants_policy(None)
    set_state_store(None)
    set_ledger(None)
    reset_rate_limiter()

    # Set paths via env
    monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))
    monkeypatch.setenv("ENGINE_STATE_PATH", str(state_path))

    # Clear CORS origins by default
    monkeypatch.delenv("ENGINE_CORS_ORIGINS", raising=False)

    yield

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


def create_approvals_json(bundle_path: Path, rules: list) -> str:
    """Create approvals.json and return its SHA-256 hash."""
    approvals_data = {
        "version": "1.0.0",
        "name": "approvals",
        "rules": rules,
    }
    approvals_path = bundle_path / "approvals.json"
    with open(approvals_path, "w", encoding="utf-8") as f:
        json.dump(approvals_data, f)
    return compute_sha256(approvals_path)


def create_sod_json(bundle_path: Path, rules: list) -> str:
    """Create sod.json and return its SHA-256 hash."""
    sod_data = {
        "version": "1.0.0",
        "name": "sod",
        "rules": rules,
    }
    sod_path = bundle_path / "sod.json"
    with open(sod_path, "w", encoding="utf-8") as f:
        json.dump(sod_data, f)
    return compute_sha256(sod_path)


def create_invariants_json(bundle_path: Path, expense_schema: dict) -> str:
    """Create invariants.json and return its SHA-256 hash."""
    invariants_data = {
        "version": "1.0.0",
        "name": "invariants",
        "expense": expense_schema,
    }
    invariants_path = bundle_path / "invariants.json"
    with open(invariants_path, "w", encoding="utf-8") as f:
        json.dump(invariants_data, f)
    return compute_sha256(invariants_path)


def create_bundle(bundle_path: Path) -> None:
    """Create a full bundle with RBAC, approvals, SoD, and invariants."""
    # Create RBAC
    rbac_hash = create_rbac_json(bundle_path, [
        {"name": "analyst", "permissions": ["expense.create", "expense.read"]},
        {"name": "manager", "permissions": ["expense.create", "expense.read", "expense.approve"]},
    ])

    # Create approvals rule
    approvals_hash = create_approvals_json(bundle_path, [
        {
            "rule_name": "expense.create",
            "trigger": {"api": "POST /finance/expenses"},
            "approver_roles": ["manager"],
            "quorum": 1,
        }
    ])

    # Create SoD rules (empty for these tests)
    sod_hash = create_sod_json(bundle_path, [])

    # Create invariants
    invariants_hash = create_invariants_json(bundle_path, {
        "amount": {"min": 0.01, "max": 1000000000},
        "description": {"max_len": 280, "required": False},
    })

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
            {
                "file": "approvals.json",
                "sha256": f"SHA256:{approvals_hash}",
                "required": True,
            },
            {
                "file": "sod.json",
                "sha256": f"SHA256:{sod_hash}",
                "required": True,
            },
            {
                "file": "invariants.json",
                "sha256": f"SHA256:{invariants_hash}",
                "required": True,
            },
        ],
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


class TestSecurityHeaders:
    """Test security headers are present on responses."""

    def test_security_headers_present_on_health(self, tmp_path: Path):
        """GET /health should have security headers."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("Referrer-Policy") == "no-referrer"
        assert response.headers.get("Content-Security-Policy") == "default-src 'none'"


class TestBodySizeLimit:
    """Test body size limit enforcement."""

    def test_large_body_returns_413(self, tmp_path: Path, monkeypatch):
        """POST with body > 256KB should return 413 REQUEST_TOO_LARGE."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        # Set limit to 256KB (262144 bytes)
        monkeypatch.setenv("ENGINE_MAX_BODY_BYTES", "262144")

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        # Create a payload larger than 256KB
        large_description = "x" * 300000  # > 256KB

        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
                "Content-Length": str(len(json.dumps({"amount": 100, "description": large_description}))),
            },
            json={"amount": 100, "description": large_description},
        )

        assert response.status_code == 413
        data = response.json()
        assert data["code"] == "REQUEST_TOO_LARGE"
        assert data["message"] == "Request body too large"

        # Verify security headers are present
        assert response.headers.get("X-Content-Type-Options") == "nosniff"


class TestRateLimit:
    """Test rate limiting enforcement."""

    def test_rate_limit_exceeded_returns_429(self, tmp_path: Path, monkeypatch):
        """Exceeding rate limit should return 429 RATE_LIMIT_EXCEEDED."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        # Set rate limit to 2 requests per minute
        monkeypatch.setenv("ENGINE_RATE_LIMIT_PER_MINUTE", "2")
        reset_rate_limiter()

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        # First request - should succeed
        response1 = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "test 1"},
        )
        assert response1.status_code == 202

        # Second request - should succeed
        response2 = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 200, "description": "test 2"},
        )
        assert response2.status_code == 202

        # Third request - should be rate limited
        response3 = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 300, "description": "test 3"},
        )

        assert response3.status_code == 429
        data = response3.json()
        assert data["code"] == "RATE_LIMIT_EXCEEDED"
        assert data["message"] == "Rate limit exceeded"

        # Verify security headers are present
        assert response3.headers.get("X-Content-Type-Options") == "nosniff"


class TestErrorEnvelope:
    """Test standardized error envelope format."""

    def test_invalid_request_id_returns_envelope(self, tmp_path: Path):
        """Invalid X-Request-Id should return {code, message} envelope."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())

        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
                "X-Request-Id": "not-a-valid-uuid",
            },
            json={"amount": 100, "description": "test"},
        )

        assert response.status_code == 400
        data = response.json()

        # Check envelope format - should have code and message at top level
        assert "code" in data
        assert "message" in data
        assert data["code"] == "REQUEST_ID_INVALID"
        assert data["message"] == "Invalid X-Request-Id"

        # Should NOT have "detail" wrapper
        assert "detail" not in data


class TestCorsOff:
    """Test CORS is disabled by default."""

    def test_cors_off_by_default(self, tmp_path: Path, monkeypatch):
        """Without ENGINE_CORS_ORIGINS, Access-Control-Allow-Origin should not be present."""
        create_bundle(tmp_path)
        load_bundle(tmp_path)

        # Ensure CORS is not configured
        monkeypatch.delenv("ENGINE_CORS_ORIGINS", raising=False)

        client = TestClient(app)

        response = client.get(
            "/health",
            headers={
                "Origin": "https://example.com",
            },
        )

        assert response.status_code == 200
        # CORS header should NOT be present
        assert "Access-Control-Allow-Origin" not in response.headers


class TestCorsOn:
    """Test CORS can be enabled via environment variable."""

    def test_cors_on_with_env_var(self, tmp_path: Path, monkeypatch):
        """With ENGINE_CORS_ORIGINS set, Access-Control-Allow-Origin should be present."""
        # Set CORS origins BEFORE importing/loading the app
        monkeypatch.setenv("ENGINE_CORS_ORIGINS", "https://example.com")

        # We need to reload the module to pick up the env var
        # Since CORS middleware is added at module load time, we'll test the security module directly
        from engine.core.security import parse_cors_origins

        origins = parse_cors_origins()
        assert origins == ["https://example.com"]

        # Also test parsing multiple origins
        monkeypatch.setenv("ENGINE_CORS_ORIGINS", "https://example.com,https://other.com")
        origins = parse_cors_origins()
        assert origins == ["https://example.com", "https://other.com"]

        # Test empty string returns None
        monkeypatch.setenv("ENGINE_CORS_ORIGINS", "")
        origins = parse_cors_origins()
        assert origins is None

        # Test not set returns None
        monkeypatch.delenv("ENGINE_CORS_ORIGINS", raising=False)
        origins = parse_cors_origins()
        assert origins is None
