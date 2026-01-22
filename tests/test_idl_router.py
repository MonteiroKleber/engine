"""Tests for IDL Router (Etapa 6.4) - Dynamic route registration.

Tests:
1. ENGINE_API_MODE=idl registers routes from OperationRegistry
2. POST /finance/expenses via IDL returns pending_approval
3. POST /approvals/{id}/decide via IDL returns COMMITTED
4. Multi-dept route /d/{dept_id}/finance/expenses works
5. Collision detection: idl mode fails, both mode skips
6. Full approval flow via IDL routes
"""

import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.rbac import set_rbac_policy, reset_all_rbac
from engine.core.approvals import set_approvals_policy, reset_all_approvals
from engine.core.sod import set_sod_policy, reset_all_sod
from engine.core.invariants import set_invariants_policy, reset_all_invariants
from engine.core.ledger import set_ledger, get_ledger, reset_institution_ledgers, AuditLedger
from engine.core.state_store import reset_all_state_stores, init_state_store
from engine.core.operations import (
    Operation,
    OperationsDef,
    set_operations,
    reset_all_operations,
    get_operations,
)
from engine.core.idl_router import (
    register_idl_routes,
    get_api_mode,
    API_MODE_LEGACY,
    API_MODE_IDL,
    API_MODE_BOTH,
    _has_collision,
    _normalize_path_for_collision,
)
from engine.loader.load_bundle import load_bundle, _set_bundle_context, BundleContext
from engine.loader.verify_hashes import compute_sha256
from engine.core.policy import clear_all_policies
from engine.core.mandates import clear_all_mandates
from engine.core.autonomy import reset_all_autonomy
from engine.core.governed_mandates import invalidate_all_mandates_cache
from engine.core.governed_autonomy import invalidate_all_autonomy_cache
from engine.core.governed_policies import invalidate_all_policies_cache


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    """Create a temporary ledger path."""
    return tmp_path / "audit_ledger.jsonl"


@pytest.fixture(autouse=True)
def reset_state(ledger_path: Path, monkeypatch):
    """Reset all state before each test."""
    # Clear env vars
    monkeypatch.delenv("ENGINE_API_MODE", raising=False)

    # Reset runtime state
    runtime_state.set_active()

    # Reset all global state
    reset_all_operations()
    reset_all_rbac()
    reset_all_approvals()
    reset_all_sod()
    reset_all_invariants()
    reset_all_state_stores()
    reset_institution_ledgers()
    clear_all_policies()
    clear_all_mandates()
    reset_all_autonomy()
    invalidate_all_policies_cache()
    invalidate_all_mandates_cache()
    invalidate_all_autonomy_cache()
    _set_bundle_context(None)
    set_ledger(None)

    # Set ledger path env
    monkeypatch.setenv("ENGINE_LEDGER_PATH", str(ledger_path))

    yield

    # Cleanup
    runtime_state.set_active()
    reset_all_operations()
    reset_all_rbac()
    reset_all_approvals()
    reset_all_sod()
    reset_all_invariants()
    reset_all_state_stores()
    reset_institution_ledgers()
    clear_all_policies()
    clear_all_mandates()
    reset_all_autonomy()
    invalidate_all_policies_cache()
    invalidate_all_mandates_cache()
    invalidate_all_autonomy_cache()
    _set_bundle_context(None)
    set_ledger(None)


# =============================================================================
# Bundle Creation Helpers
# =============================================================================


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


def create_invariants_json(bundle_path: Path, invariants: dict) -> str:
    """Create invariants.json and return its SHA-256 hash."""
    invariants_data = {
        "version": "1.0.0",
        "name": "invariants",
        "invariants": invariants,
    }
    invariants_path = bundle_path / "invariants.json"
    with open(invariants_path, "w", encoding="utf-8") as f:
        json.dump(invariants_data, f)
    return compute_sha256(invariants_path)


def create_workflows_json(bundle_path: Path) -> str:
    """Create minimal workflows.json."""
    workflows_data = {
        "version": "1.0.0",
        "workflows": [],
    }
    workflows_path = bundle_path / "workflows.json"
    with open(workflows_path, "w", encoding="utf-8") as f:
        json.dump(workflows_data, f)
    return compute_sha256(workflows_path)


def create_operations_json(bundle_path: Path, operations: list) -> str:
    """Create operations.json and return its SHA-256 hash."""
    ops_data = {
        "operations_schema_version": "1.0",
        "operations": operations,
    }
    ops_path = bundle_path / "operations.json"
    with open(ops_path, "w", encoding="utf-8") as f:
        json.dump(ops_data, f)
    return compute_sha256(ops_path)


def create_bundle_with_operations(bundle_path: Path) -> None:
    """Create a bundle with RBAC, approvals, SoD, invariants, and operations.

    Operations:
    - POST /finance/expenses (expense.create)
    - GET /finance/expenses/{expense_id} (expense.read)
    - POST /approvals/{approval_id}/decide (approval_decide)
    """
    # Create RBAC
    rbac_hash = create_rbac_json(bundle_path, [
        {"name": "analyst", "permissions": ["expense.create", "expense.read"]},
        {"name": "manager", "permissions": ["expense.create", "expense.read", "expense.approve"]},
    ])

    # Create approvals
    approvals_hash = create_approvals_json(bundle_path, [
        {
            "rule_name": "expense.create",
            "trigger": {"api": "POST /finance/expenses"},
            "approver_roles": ["manager"],
            "quorum": 1,
        }
    ])

    # Create SoD
    sod_hash = create_sod_json(bundle_path, [
        {
            "rule_name": "expense.sod",
            "case_step": "APPROVAL:expense.create",
            "constraint": "REQUESTER_NEQ_DECIDER",
        }
    ])

    # Create invariants
    invariants_hash = create_invariants_json(bundle_path, {
        "expense": {
            "amount_positive": {
                "field": "amount",
                "type": "number",
                "constraint": "positive",
            }
        }
    })

    # Create workflows (minimal)
    workflows_hash = create_workflows_json(bundle_path)

    # Create operations
    ops_hash = create_operations_json(bundle_path, [
        {
            "operation_id": "expense_create",
            "method": "POST",
            "path": "/finance/expenses",
            "endpoint_sig": "POST /finance/expenses",
            "permission": "expense.create",
            "scope": "tenant",
            "idempotency": "required",
            "errors": [400, 401, 403],
            "bind": {"kind": "create", "entity": "Expense"},
        },
        {
            "operation_id": "expense_get",
            "method": "GET",
            "path": "/finance/expenses/{expense_id}",
            "endpoint_sig": "GET /finance/expenses/{expense_id}",
            "permission": "expense.read",
            "scope": "tenant",
            "bind": {"kind": "read", "entity": "Expense"},
        },
        {
            "operation_id": "approval_decide",
            "method": "POST",
            "path": "/approvals/{approval_id}/decide",
            "endpoint_sig": "POST /approvals/{approval_id}/decide",
            "permission": "expense.approve",
            "scope": "tenant",
            "bind": {"kind": "approval_decide"},
        },
    ])

    # Create manifest
    manifest = {
        "name": "test-idl-bundle",
        "version": "1.0.0",
        "contracts": [
            {"file": "rbac.json", "sha256": f"SHA256:{rbac_hash}", "required": True},
            {"file": "approvals.json", "sha256": f"SHA256:{approvals_hash}", "required": True},
            {"file": "sod.json", "sha256": f"SHA256:{sod_hash}", "required": True},
            {"file": "invariants.json", "sha256": f"SHA256:{invariants_hash}", "required": True},
            {"file": "workflows.json", "sha256": f"SHA256:{workflows_hash}", "required": True},
            {"file": "operations.json", "sha256": f"SHA256:{ops_hash}", "required": False},
        ],
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)


# =============================================================================
# Unit Tests: Path Normalization and Collision Detection
# =============================================================================


class TestPathNormalization:
    """Test path normalization for collision detection."""

    def test_normalize_single_param(self):
        """Single path param is normalized."""
        assert _normalize_path_for_collision("/expenses/{expense_id}") == "/expenses/{param}"

    def test_normalize_multiple_params(self):
        """Multiple path params are normalized."""
        path = "/d/{dept_id}/expenses/{expense_id}"
        expected = "/d/{param}/expenses/{param}"
        assert _normalize_path_for_collision(path) == expected

    def test_normalize_different_param_names(self):
        """{expense_id} and {id} normalize to same value."""
        assert _normalize_path_for_collision("/expenses/{expense_id}") == \
               _normalize_path_for_collision("/expenses/{id}")


class TestCollisionDetection:
    """Test route collision detection."""

    def test_no_collision_different_paths(self):
        """Different paths don't collide."""
        app = FastAPI()
        app.add_api_route("/finance/expenses", lambda: None, methods=["POST"])

        assert not _has_collision(app, "POST", "/support/tickets")

    def test_no_collision_different_methods(self):
        """Same path with different method doesn't collide."""
        app = FastAPI()
        app.add_api_route("/finance/expenses", lambda: None, methods=["GET"])

        assert not _has_collision(app, "POST", "/finance/expenses")

    def test_collision_same_route(self):
        """Same path and method collides."""
        app = FastAPI()
        app.add_api_route("/finance/expenses", lambda: None, methods=["POST"])

        assert _has_collision(app, "POST", "/finance/expenses")

    def test_collision_normalized_params(self):
        """Routes with different param names collide after normalization."""
        app = FastAPI()
        app.add_api_route("/expenses/{expense_id}", lambda: None, methods=["GET"])

        # Different param name but same structure
        assert _has_collision(app, "GET", "/expenses/{id}")


# =============================================================================
# Integration Tests: IDL Route Registration
# =============================================================================


class TestApiModeEnvVar:
    """Test ENGINE_API_MODE environment variable handling."""

    def test_default_mode_is_legacy(self, monkeypatch):
        """Default API mode is legacy."""
        monkeypatch.delenv("ENGINE_API_MODE", raising=False)
        assert get_api_mode() == API_MODE_LEGACY

    def test_mode_idl(self, monkeypatch):
        """ENGINE_API_MODE=idl is recognized."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")
        assert get_api_mode() == API_MODE_IDL

    def test_mode_both(self, monkeypatch):
        """ENGINE_API_MODE=both is recognized."""
        monkeypatch.setenv("ENGINE_API_MODE", "both")
        assert get_api_mode() == API_MODE_BOTH

    def test_invalid_mode_falls_back_to_legacy(self, monkeypatch):
        """Invalid mode falls back to legacy."""
        monkeypatch.setenv("ENGINE_API_MODE", "invalid")
        assert get_api_mode() == API_MODE_LEGACY


class TestIdlRouteRegistration:
    """Test IDL route registration."""

    def test_legacy_mode_registers_no_routes(self, tmp_path: Path, monkeypatch):
        """In legacy mode, no IDL routes are registered."""
        monkeypatch.setenv("ENGINE_API_MODE", "legacy")

        # Setup operations
        ops_def = OperationsDef(
            dept_id=None,
            operations=[
                Operation(
                    operation_id="expense_create",
                    method="POST",
                    path="/finance/expenses",
                    endpoint_sig="POST /finance/expenses",
                    permission="expense.create",
                    bind={"kind": "create", "entity": "Expense"},
                )
            ],
        )
        set_operations(None, ops_def)

        app = FastAPI()
        routes_count = register_idl_routes(app)

        assert routes_count == 0

    def test_idl_mode_registers_routes(self, tmp_path: Path, monkeypatch, ledger_path: Path):
        """In idl mode, routes are registered from OperationRegistry."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")

        # Setup operations
        ops_def = OperationsDef(
            dept_id=None,
            operations=[
                Operation(
                    operation_id="expense_create",
                    method="POST",
                    path="/idl/expenses",  # Use different path to avoid collision
                    endpoint_sig="POST /idl/expenses",
                    permission="expense.create",
                    bind={"kind": "create", "entity": "Expense"},
                )
            ],
        )
        set_operations(None, ops_def)

        app = FastAPI()
        routes_count = register_idl_routes(app)

        assert routes_count == 1

        # Verify route exists
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/idl/expenses" in route_paths

    def test_idl_mode_fails_on_collision(self, tmp_path: Path, monkeypatch):
        """In idl mode, collision with existing route fails startup."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")

        # Setup operations with colliding path
        ops_def = OperationsDef(
            dept_id=None,
            operations=[
                Operation(
                    operation_id="expense_create",
                    method="POST",
                    path="/finance/expenses",
                    endpoint_sig="POST /finance/expenses",
                    permission="expense.create",
                    bind={"kind": "create", "entity": "Expense"},
                )
            ],
        )
        set_operations(None, ops_def)

        # Create app with existing route
        app = FastAPI()
        app.add_api_route("/finance/expenses", lambda: None, methods=["POST"])

        # Should raise RuntimeError on collision
        with pytest.raises(RuntimeError, match="IDL route collision detected"):
            register_idl_routes(app)

    def test_both_mode_skips_collision(self, tmp_path: Path, monkeypatch):
        """In both mode, colliding routes are skipped with warning."""
        monkeypatch.setenv("ENGINE_API_MODE", "both")

        # Setup operations with colliding path
        ops_def = OperationsDef(
            dept_id=None,
            operations=[
                Operation(
                    operation_id="expense_create",
                    method="POST",
                    path="/finance/expenses",
                    endpoint_sig="POST /finance/expenses",
                    permission="expense.create",
                    bind={"kind": "create", "entity": "Expense"},
                ),
                Operation(
                    operation_id="ticket_create",
                    method="POST",
                    path="/support/tickets",  # Non-colliding
                    endpoint_sig="POST /support/tickets",
                    permission="ticket.create",
                    bind={"kind": "create", "entity": "Ticket"},
                ),
            ],
        )
        set_operations(None, ops_def)

        # Create app with existing route
        app = FastAPI()
        app.add_api_route("/finance/expenses", lambda: None, methods=["POST"])

        # Should skip collision, register non-colliding
        routes_count = register_idl_routes(app)

        # Only ticket_create should be registered
        assert routes_count == 1

        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/support/tickets" in route_paths

    def test_multi_dept_registers_both_variants(self, tmp_path: Path, monkeypatch):
        """In multi-dept mode, both base and /d/{dept_id}/ variants are registered."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")

        # Setup operations
        ops_def = OperationsDef(
            dept_id="finance",
            operations=[
                Operation(
                    operation_id="expense_create",
                    method="POST",
                    path="/idl/expenses",  # Avoid collision
                    endpoint_sig="POST /idl/expenses",
                    permission="expense.create",
                    bind={"kind": "create", "entity": "Expense"},
                )
            ],
        )
        set_operations("finance", ops_def)

        app = FastAPI()
        routes_count = register_idl_routes(app, departments=["finance"])

        # Should register 2 routes: base + dept variant
        assert routes_count == 2

        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/idl/expenses" in route_paths
        assert "/d/{dept_id}/idl/expenses" in route_paths


# =============================================================================
# Integration Tests: Full Flow via IDL Routes
# =============================================================================


class TestIdlRouteExecution:
    """Test IDL route execution with full approval flow."""

    def test_idl_expense_create_returns_202(self, tmp_path: Path, monkeypatch, ledger_path: Path):
        """POST to IDL route returns 202 with pending_approval."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))

        # Create bundle with operations
        create_bundle_with_operations(tmp_path)
        load_bundle(tmp_path)

        # Create a fresh FastAPI app and register IDL routes
        app = FastAPI()
        routes_count = register_idl_routes(app)
        assert routes_count == 3  # expense_create, expense_get, approval_decide

        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        # POST expense as analyst
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100, "description": "test via IDL"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending_approval"
        assert "approval_id" in data
        assert "expense_id" in data

    def test_idl_approval_decide_returns_committed(self, tmp_path: Path, monkeypatch, ledger_path: Path):
        """POST /approvals/{id}/decide via IDL returns COMMITTED."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))

        # Create bundle
        create_bundle_with_operations(tmp_path)
        load_bundle(tmp_path)

        # Create fresh app
        app = FastAPI()
        register_idl_routes(app)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # 1. Create expense as analyst
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 50, "description": "test approval"},
        )
        assert response.status_code == 202
        approval_id = response.json()["approval_id"]
        expense_id = response.json()["expense_id"]

        # 2. Approve as manager (different actor for SoD)
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "decided"
        assert data["decision"] == "approve"
        assert data["case_status"] == "COMMITTED"
        assert data["expense_id"] == expense_id

    def test_idl_self_approve_blocked_by_sod(self, tmp_path: Path, monkeypatch, ledger_path: Path):
        """Self-approve via IDL is blocked by SoD."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))

        # Create bundle
        create_bundle_with_operations(tmp_path)
        load_bundle(tmp_path)

        # Create fresh app
        app = FastAPI()
        register_idl_routes(app)

        client = TestClient(app)
        manager_id = str(uuid.uuid4())

        # Manager creates expense
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"amount": 100},
        )
        assert response.status_code == 202
        approval_id = response.json()["approval_id"]

        # Same manager tries to approve (SoD violation)
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )

        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "SOD_VIOLATION"

    def test_idl_full_approval_flow(self, tmp_path: Path, monkeypatch, ledger_path: Path):
        """Full flow: create → pending → approve → COMMITTED via IDL."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))

        # Create bundle
        create_bundle_with_operations(tmp_path)
        load_bundle(tmp_path)

        # Create fresh app
        app = FastAPI()
        register_idl_routes(app)

        client = TestClient(app)
        analyst_id = str(uuid.uuid4())
        manager_id = str(uuid.uuid4())

        # Step 1: Create expense (analyst)
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 75, "description": "full flow test"},
        )
        assert response.status_code == 202
        create_data = response.json()
        assert create_data["status"] == "pending_approval"
        approval_id = create_data["approval_id"]
        expense_id = create_data["expense_id"]

        # Step 2: Read expense (should exist)
        response = client.get(
            f"/finance/expenses/{expense_id}",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
        )
        assert response.status_code == 200
        read_data = response.json()
        assert read_data["id"] == expense_id
        assert read_data["status"] == "PENDING_APPROVAL"

        # Step 3: Approve (manager)
        response = client.post(
            f"/approvals/{approval_id}/decide",
            headers={
                "X-Actor-Id": manager_id,
                "X-Actor-Roles": "manager",
            },
            json={"decision": "approve"},
        )
        assert response.status_code == 200
        decide_data = response.json()
        assert decide_data["case_status"] == "COMMITTED"

        # Step 4: Read expense again (status should be COMMITTED)
        response = client.get(
            f"/finance/expenses/{expense_id}",
            headers={
                "X-Actor-Id": analyst_id,
                "X-Actor-Roles": "analyst",
            },
        )
        assert response.status_code == 200
        final_data = response.json()
        assert final_data["status"] == "COMMITTED"


class TestIdlMultiDeptRoutes:
    """Test multi-dept IDL routes with /d/{dept_id}/ prefix."""

    def test_dept_route_resolves_dept_id(self, tmp_path: Path, monkeypatch, ledger_path: Path):
        """POST /d/{dept_id}/... correctly resolves dept_id from path."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path))

        # Create multi-dept bundle structure
        bundle_path = tmp_path
        depts_path = bundle_path / "departments"
        finance_path = depts_path / "finance"
        finance_path.mkdir(parents=True)

        # Create finance dept contracts
        rbac_hash = create_rbac_json(finance_path, [
            {"name": "analyst", "permissions": ["expense.create", "expense.read"]},
            {"name": "manager", "permissions": ["expense.create", "expense.read", "expense.approve"]},
        ])
        approvals_hash = create_approvals_json(finance_path, [
            {
                "rule_name": "expense.create",
                "trigger": {"api": "POST /finance/expenses"},
                "approver_roles": ["manager"],
                "quorum": 1,
            }
        ])
        sod_hash = create_sod_json(finance_path, [
            {
                "rule_name": "expense.sod",
                "case_step": "APPROVAL:expense.create",
                "constraint": "REQUESTER_NEQ_DECIDER",
            }
        ])
        invariants_hash = create_invariants_json(finance_path, {
            "expense": {
                "amount_positive": {
                    "field": "amount",
                    "type": "number",
                    "constraint": "positive",
                }
            }
        })
        workflows_hash = create_workflows_json(finance_path)

        # Create openapi.yaml (minimal)
        openapi_path = finance_path / "openapi.yaml"
        with open(openapi_path, "w") as f:
            f.write("openapi: '3.0.0'\ninfo:\n  title: Finance\n  version: '1.0'\npaths: {}")

        # Create operations.json for finance dept
        ops_hash = create_operations_json(finance_path, [
            {
                "operation_id": "expense_create",
                "method": "POST",
                "path": "/finance/expenses",
                "endpoint_sig": "POST /finance/expenses",
                "permission": "expense.create",
                "scope": "tenant",
                "bind": {"kind": "create", "entity": "Expense"},
            },
        ])

        # Create contracts.json for multi-dept
        contracts_path = bundle_path / "contracts.json"
        with open(contracts_path, "w") as f:
            json.dump({"departments": ["finance"]}, f)

        # Create bundle manifest
        manifest = {
            "name": "multi-dept-test",
            "version": "1.0.0",
            "contracts": [],
        }
        manifest_path = bundle_path / "bundle.manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        # Load bundle
        load_bundle(bundle_path)

        # Create fresh app and register with departments
        app = FastAPI()
        routes_count = register_idl_routes(app, departments=["finance"])

        # Should have 2 routes: base + dept variant
        assert routes_count == 2

        # Verify dept variant exists
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/finance/expenses" in route_paths
        assert "/d/{dept_id}/finance/expenses" in route_paths

        # Test dept route works
        client = TestClient(app)
        actor_id = str(uuid.uuid4())

        response = client.post(
            "/d/finance/finance/expenses",
            headers={
                "X-Actor-Id": actor_id,
                "X-Actor-Roles": "analyst",
            },
            json={"amount": 100},
        )

        # Should work and resolve dept_id="finance" from path
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending_approval"
