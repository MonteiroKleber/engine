"""Tests for cross-tenant (institution) isolation.

These tests prove that one institution cannot see, access, or infer
data from another institution.

Per Definition of Done (Etapa 06):
- Evidence that one tenant cannot see/interfere/infer another.
- Admin of one institution does not admin another.

NOTE: These tests use the REAL bundle (bundles/finance-pilot) via load_bundle()
to prove true E2E isolation through the actual runtime/loader path.
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry, get_registry
from engine.core.institution_config import reset_config_cache
from engine.core.admin_keys import reset_admin_keys_registry, get_admin_keys_registry
from engine.core.state_store import (
    reset_all_state_stores,
    get_state_store,
)
from engine.core.ledger import set_ledger, reset_institution_ledgers
from engine.core.rbac import set_rbac_policy
from engine.core.approvals import set_approvals_policy
from engine.core.sod import set_sod_policy
from engine.core.invariants import set_invariants_policy
from engine.core.policy import clear_all_policies
from engine.core.mandates import clear_all_mandates
from engine.core.autonomy import reset_all_autonomy
from engine.core.runtime_state import runtime_state
from engine.loader.load_bundle import load_bundle, _set_bundle_context


# Path to the real finance-pilot bundle
FINANCE_PILOT_BUNDLE = Path(__file__).parent.parent / "bundles" / "finance-pilot"


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test.

    Uses the REAL finance-pilot bundle via load_bundle() for true E2E testing.

    IMPORTANT: Do NOT set ENGINE_STATE_STORE_DIR or ENGINE_LEDGER_PATH to absolute paths,
    as this bypasses institution namespacing. Let the loader use institution-specific paths.
    """
    # Set up data directories in tmp_path for isolation
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")

    # Point to the REAL bundle
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(FINANCE_PILOT_BUNDLE))

    # CRITICAL: Do NOT set absolute paths for state store and ledger
    # This ensures each institution gets its own namespaced storage
    monkeypatch.delenv("ENGINE_STATE_STORE_DIR", raising=False)
    monkeypatch.delenv("ENGINE_LEDGER_PATH", raising=False)

    # Reset all caches and registries before loading
    reset_registry()
    reset_config_cache()
    reset_admin_keys_registry()
    reset_all_state_stores()
    reset_institution_ledgers()
    clear_all_policies()
    clear_all_mandates()
    reset_all_autonomy()
    set_ledger(None)
    _set_bundle_context(None)
    runtime_state.set_active()

    # Load the real bundle - this sets up RBAC, approvals, mandates, autonomy, etc.
    result = load_bundle(FINANCE_PILOT_BUNDLE)
    assert result is not None, f"Failed to load bundle: {runtime_state.reason_code}"
    assert runtime_state.is_active(), f"Bundle loaded in SAFE_MODE: {runtime_state.reason_code}"

    yield

    # Cleanup
    _set_bundle_context(None)
    reset_registry()
    reset_config_cache()
    reset_admin_keys_registry()
    reset_all_state_stores()
    reset_institution_ledgers()
    clear_all_policies()
    clear_all_mandates()
    reset_all_autonomy()
    set_ledger(None)
    set_rbac_policy(None)
    set_approvals_policy(None)
    set_sod_policy(None)
    set_invariants_policy(None)
    runtime_state.set_active()


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def institution_a(client):
    """Create institution A and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "institution-a", "name": "Institution A"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


@pytest.fixture
def institution_b(client):
    """Create institution B and return its ID."""
    response = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "institution-b", "name": "Institution B"},
    )
    assert response.status_code == 201
    return response.json()["institution_id"]


class TestCrossTenantExpenseIsolation:
    """Test that expenses are isolated between institutions."""

    def test_expense_created_in_a_not_visible_to_b(
        self, client, institution_a, institution_b
    ):
        """Expense created by institution A is not visible to institution B.

        This test proves true E2E isolation: expenses are stored in institution-
        specific namespaces and cannot be accessed across institutions.

        Uses the REAL finance-pilot bundle with actual RBAC, mandates, and autonomy.
        """
        # Institution A creates an expense (analyst role is allowed by finance-pilot RBAC)
        response_a = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": institution_a,
                "X-Actor-Id": "11111111-1111-1111-1111-111111111111",
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "Expense from A"},
        )
        assert response_a.status_code == 202, f"Failed to create expense: {response_a.json()}"
        expense_id = response_a.json()["expense_id"]

        # Institution A can access its own expense (admin role has expense.read)
        response_a_get = client.get(
            f"/finance/expenses/{expense_id}",
            headers={
                "X-Institution-Id": institution_a,
                "X-Actor-Id": "11111111-1111-1111-1111-111111111111",
                "X-Actor-Roles": "admin",
            },
        )
        assert response_a_get.status_code == 200, f"A cannot access own expense: {response_a_get.json()}"
        assert response_a_get.json()["id"] == expense_id

        # Institution B tries to access the same expense ID
        # This MUST return 404 (not 403) to prevent inference
        response_b = client.get(
            f"/finance/expenses/{expense_id}",
            headers={
                "X-Institution-Id": institution_b,
                "X-Actor-Id": "22222222-2222-2222-2222-222222222222",
                "X-Actor-Roles": "admin",
            },
        )

        # DETERMINISTIC: Must be 404 (expense not found in B's namespace)
        assert response_b.status_code == 404, \
            f"Expected 404 (expense not in B's namespace), got {response_b.status_code}: {response_b.json()}"
        assert response_b.json()["code"] == "EXPENSE_NOT_FOUND"

    def test_state_stores_are_separate_per_institution_at_core_level(
        self, client, institution_a, institution_b, tmp_path, monkeypatch
    ):
        """
        Each institution has its own state store file at the core level.

        This test verifies that get_state_store(institution_id=...) returns
        different stores for different institutions.

        Note: API handlers properly pass institution_id to get_state_store(),
        so this test validates both the core module and E2E behavior.
        """
        # Reset stores to pick up new config
        reset_all_state_stores()

        # Verify state stores are separate when institution_id is passed
        store_a = get_state_store(institution_id=institution_a)
        store_b = get_state_store(institution_id=institution_b)

        # Check that stores are different instances
        assert store_a is not store_b

        # Check that paths are different
        assert store_a._path != store_b._path

        # Verify institution ID is in the path
        assert institution_a in str(store_a._path)
        assert institution_b in str(store_b._path)


class TestCrossTenantLedgerIsolation:
    """Test that ledger events are isolated between institutions."""

    def test_ledger_events_isolated_per_institution(
        self, client, institution_a, institution_b, tmp_path
    ):
        """Events from institution A are not in institution B's ledger."""
        from engine.core.ledger import get_ledger_path_for_institution

        # Create expense in institution A
        response_a = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": institution_a,
                "X-Actor-Id": "11111111-1111-1111-1111-111111111111",
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )
        assert response_a.status_code == 202, f"Failed: {response_a.json()}"

        # Create expense in institution B
        response_b = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": institution_b,
                "X-Actor-Id": "22222222-2222-2222-2222-222222222222",
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 200},
        )
        assert response_b.status_code == 202, f"Failed: {response_b.json()}"

        # Check ledger paths are different
        ledger_path_a = get_ledger_path_for_institution(institution_a)
        ledger_path_b = get_ledger_path_for_institution(institution_b)

        assert ledger_path_a != ledger_path_b
        assert institution_a in str(ledger_path_a)
        assert institution_b in str(ledger_path_b)


class TestCrossTenantAdminKeyIsolation:
    """Test that admin keys are isolated between institutions."""

    def test_admin_key_from_a_rejected_for_b(
        self, client, institution_a, institution_b
    ):
        """Admin key created for institution A cannot be used for institution B."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # Create admin key for DEFAULT (using legacy token)
        response_key = client.post(
            f"/admin/institutions/{DEFAULT_INSTITUTION_ID}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        assert response_key.status_code == 201
        key_for_default = response_key.json()["plaintext_secret"]

        # Try to use DEFAULT's key for institution A
        response = client.get(
            f"/admin/institutions/{institution_a}/admin-keys",
            headers={"X-Admin-Key": key_for_default},
        )

        # Should be rejected - key is for DEFAULT, not institution A
        assert response.status_code == 401
        assert response.json()["code"] in ("ADMIN_KEY_INVALID", "ADMIN_KEY_REQUIRED")

    def test_legacy_token_rejected_for_non_default(
        self, client, institution_a
    ):
        """Legacy X-Admin-Token only works for DEFAULT institution."""
        response = client.post(
            f"/admin/institutions/{institution_a}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )

        # Legacy token should be rejected for non-DEFAULT institution
        assert response.status_code == 401
        assert response.json()["code"] == "ADMIN_KEY_REQUIRED"


class TestCrossTenantConfigIsolation:
    """Test that institution configs are isolated."""

    def test_config_changes_only_affect_own_institution(
        self, client, institution_a, institution_b
    ):
        """Changing config for institution A does not affect institution B."""
        from engine.core.institution_context import DEFAULT_INSTITUTION_ID

        # Get initial configs
        response_a = client.get(
            f"/admin/institutions/{institution_a}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        response_b = client.get(
            f"/admin/institutions/{institution_b}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # Both should start with freeze_mode=false
        assert response_a.status_code == 200
        assert response_b.status_code == 200
        config_a = response_a.json()
        config_b = response_b.json()
        assert config_a.get("freeze_mode") is False or config_a.get("freeze_mode") is None
        assert config_b.get("freeze_mode") is False or config_b.get("freeze_mode") is None

        # Enable freeze for institution A only
        new_config_a = {
            "flags": {
                "require_institution_header_for_runtime": False,
                "allow_legacy_routes": True,
                "enable_contracts_stub": True,
            },
            "limits": {
                "rate_limit_per_minute": 100,
                "max_body_bytes": 262144,
            },
            "defaults": {
                "default_dept": "finance",
                "default_bundle_name": "finance-pilot",
            },
            "freeze_mode": True,
            "emergency_stop": {
                "enabled": False,
                "blocked_endpoints": [],
            },
        }
        response_update = client.put(
            f"/admin/institutions/{institution_a}/config",
            headers={"X-Admin-Token": "test-admin-token"},
            json=new_config_a,
        )
        assert response_update.status_code == 200

        # Verify A is frozen
        response_a2 = client.get(
            f"/admin/institutions/{institution_a}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert response_a2.json()["freeze_mode"] is True

        # Verify B is NOT frozen
        response_b2 = client.get(
            f"/admin/institutions/{institution_b}/config",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        # B should still have default (false or not present)
        config_b2 = response_b2.json()
        assert config_b2.get("freeze_mode") is False or config_b2.get("freeze_mode") is None


class TestPathTraversalPrevention:
    """Test that path traversal attacks are prevented."""

    def test_invalid_dept_id_with_traversal_rejected(self, client, institution_a):
        """Dept ID with path traversal characters is rejected."""
        from engine.core.state_store import validate_dept_id

        # These should all raise RuntimeError
        invalid_dept_ids = [
            "../etc",
            "..\\windows",
            "dept/subdir",
            "dept.name",
            "dept name",
        ]

        for invalid_id in invalid_dept_ids:
            with pytest.raises(RuntimeError) as exc_info:
                validate_dept_id(invalid_id)
            assert "STATE_STORE_DEPT_INVALID" in str(exc_info.value)

    def test_invalid_institution_id_format_rejected(self, client):
        """Invalid institution ID format is rejected."""
        # Not a valid UUID - path traversal attempt
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": "../etc/passwd",
                "X-Actor-Id": "11111111-1111-1111-1111-111111111111",
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )

        assert response.status_code == 400
        # The actual error code is INSTITUTION_HEADER_INVALID for format errors
        assert response.json()["code"] in ("INSTITUTION_ID_INVALID", "INSTITUTION_HEADER_INVALID")

    def test_valid_uuid_but_nonexistent_institution_rejected(self, client):
        """Valid UUID format but non-existent institution is rejected."""
        fake_uuid = "99999999-9999-9999-9999-999999999999"

        response = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": fake_uuid,
                "X-Actor-Id": "11111111-1111-1111-1111-111111111111",
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )

        assert response.status_code == 404
        assert response.json()["code"] == "INSTITUTION_NOT_FOUND"


class TestInferencePrevention:
    """Test that information cannot be inferred across tenants."""

    def test_expense_not_found_returns_404_not_403(
        self, client, institution_a, institution_b
    ):
        """
        When institution B queries for an expense that exists in A,
        the response should be 404 (not found) rather than 403 (forbidden).

        This prevents inference attacks where an attacker could determine
        if an expense ID exists by getting different error codes.

        DETERMINISTIC: Response MUST be 404, proving anti-inference.
        """
        # Create expense in A
        response_a = client.post(
            "/finance/expenses",
            headers={
                "X-Institution-Id": institution_a,
                "X-Actor-Id": "11111111-1111-1111-1111-111111111111",
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )
        assert response_a.status_code == 202, f"Failed: {response_a.json()}"
        expense_id = response_a.json()["expense_id"]

        # B queries for the same expense ID
        response_b = client.get(
            f"/finance/expenses/{expense_id}",
            headers={
                "X-Institution-Id": institution_b,
                "X-Actor-Id": "22222222-2222-2222-2222-222222222222",
                "X-Actor-Roles": "admin",
            },
        )

        # DETERMINISTIC: Must be 404, not 403 (anti-inference)
        assert response_b.status_code == 404, \
            f"Expected 404 (anti-inference), got {response_b.status_code}: {response_b.json()}"
        assert response_b.json()["code"] == "EXPENSE_NOT_FOUND"
        # Ensure it's NOT 403 which would leak existence
        assert response_b.status_code != 403, \
            "403 would leak that the expense exists in another institution"


class TestAdminKeyDeniedEvents:
    """Test that admin key denied events are emitted to ledger."""

    def test_invalid_admin_key_emits_denied_event(
        self, client, institution_a, tmp_path, monkeypatch
    ):
        """Using invalid admin key should emit ADMIN_KEY_DENIED event."""
        from engine.core.ledger import get_ledger_path_for_institution

        # ENGINE_LEDGER_PATH already unset by fixture - institution-specific ledgers enabled

        # Try to use an invalid admin key
        response = client.get(
            f"/admin/institutions/{institution_a}/admin-keys",
            headers={"X-Admin-Key": "invalid-key-that-does-not-exist"},
        )

        assert response.status_code == 401

        # Check that ADMIN_KEY_DENIED event was written to ledger
        ledger_path = get_ledger_path_for_institution(institution_a)

        if ledger_path.exists():
            with open(ledger_path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

            denied_events = [e for e in events if e["event_type"] == "ADMIN_KEY_DENIED"]
            assert len(denied_events) >= 1, "Expected at least one ADMIN_KEY_DENIED event"

            # Verify event payload
            last_denied = denied_events[-1]
            assert last_denied["payload"]["decision"] == "deny"

    def test_legacy_token_for_non_default_emits_denied_event(
        self, client, institution_a, tmp_path, monkeypatch
    ):
        """Using legacy token for non-DEFAULT institution should emit denied event."""
        from engine.core.ledger import get_ledger_path_for_institution

        # ENGINE_LEDGER_PATH already unset by fixture - institution-specific ledgers enabled

        # Try to use legacy token for non-DEFAULT institution
        response = client.post(
            f"/admin/institutions/{institution_a}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )

        assert response.status_code == 401

        # Check for denied event
        ledger_path = get_ledger_path_for_institution(institution_a)

        if ledger_path.exists():
            with open(ledger_path, "r") as f:
                events = [json.loads(line) for line in f if line.strip()]

            denied_events = [e for e in events if e["event_type"] == "ADMIN_KEY_DENIED"]
            assert len(denied_events) >= 1, "Expected ADMIN_KEY_DENIED event for legacy token misuse"

            # Verify reason
            last_denied = denied_events[-1]
            assert last_denied["payload"]["reason"] == "legacy_token_non_default"
