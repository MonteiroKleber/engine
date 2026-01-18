"""Tests for department routing functionality."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from engine.api.server import app
from engine.loader.load_bundle import (
    _set_bundle_context,
    BundleContext,
    DeptContracts,
)
from engine.core.dept_context import (
    resolve_dept_from_path,
    get_ledger_step_name,
    validate_legacy_finance_route,
)
from engine.core.rbac import set_rbac_policy, RBACPolicy


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def single_mode_bundle(tmp_path: Path):
    """Create a single-department bundle context."""
    ctx = BundleContext(
        mode="single",
        path=tmp_path,
        manifest={"version": "1.0.0"},
    )
    _set_bundle_context(ctx)
    yield ctx
    _set_bundle_context(None)


@pytest.fixture
def multi_mode_bundle(tmp_path: Path):
    """Create a multi-department bundle context with finance dept."""
    finance_dept = DeptContracts(
        name="finance",
        path=tmp_path / "departments" / "finance",
    )
    hr_dept = DeptContracts(
        name="hr",
        path=tmp_path / "departments" / "hr",
    )
    ctx = BundleContext(
        mode="multi",
        path=tmp_path,
        manifest={"version": "1.0.0"},
        departments={"finance": finance_dept, "hr": hr_dept},
    )
    _set_bundle_context(ctx)
    yield ctx
    _set_bundle_context(None)


@pytest.fixture
def multi_mode_no_finance(tmp_path: Path):
    """Create a multi-department bundle without finance dept."""
    hr_dept = DeptContracts(
        name="hr",
        path=tmp_path / "departments" / "hr",
    )
    ctx = BundleContext(
        mode="multi",
        path=tmp_path,
        manifest={"version": "1.0.0"},
        departments={"hr": hr_dept},
    )
    _set_bundle_context(ctx)
    yield ctx
    _set_bundle_context(None)


@pytest.fixture
def rbac_policy_allow_all():
    """Set RBAC policy that allows all."""
    policy = RBACPolicy({
        "roles": [
            {
                "name": "admin",
                "permissions": ["expense.create", "expense.read"]
            }
        ]
    })
    set_rbac_policy(policy)
    yield
    set_rbac_policy(None)


class TestResolveDeptFromPath:
    """Tests for resolve_dept_from_path helper."""

    def test_extracts_dept_from_valid_path(self):
        """Should extract department from /d/{dept}/... path."""
        assert resolve_dept_from_path("/d/finance/expenses") == "finance"
        assert resolve_dept_from_path("/d/hr/employees") == "hr"
        assert resolve_dept_from_path("/d/sales/orders/123") == "sales"

    def test_returns_none_for_non_dept_path(self):
        """Should return None for paths without /d/ prefix."""
        assert resolve_dept_from_path("/finance/expenses") is None
        assert resolve_dept_from_path("/health") is None
        assert resolve_dept_from_path("/api/v1/users") is None

    def test_returns_none_for_incomplete_dept_path(self):
        """Should return None for incomplete /d/ paths."""
        assert resolve_dept_from_path("/d/") is None
        assert resolve_dept_from_path("/d") is None


class TestGetLedgerStepName:
    """Tests for get_ledger_step_name helper."""

    def test_no_dept_returns_base_step(self):
        """Without dept_id, should return base step unchanged."""
        assert get_ledger_step_name("RBAC:expense.create", None) == "RBAC:expense.create"

    def test_with_dept_prefixes_step(self):
        """With dept_id, should prefix step with DEPT:{dept}:"""
        assert get_ledger_step_name("RBAC:expense.create", "finance") == "DEPT:finance:RBAC:expense.create"
        assert get_ledger_step_name("RBAC:expense.read", "hr") == "DEPT:hr:RBAC:expense.read"


class TestValidateLegacyFinanceRoute:
    """Tests for validate_legacy_finance_route helper."""

    def test_single_mode_returns_none(self, single_mode_bundle):
        """In single mode, should return None (legacy behavior)."""
        result = validate_legacy_finance_route()
        assert result is None

    def test_multi_mode_with_finance_returns_finance(self, multi_mode_bundle):
        """In multi mode with finance dept, should return 'finance'."""
        result = validate_legacy_finance_route()
        assert result == "finance"

    def test_multi_mode_without_finance_raises_409(self, multi_mode_no_finance):
        """In multi mode without finance dept, should raise 409."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_legacy_finance_route()
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DEPT_MODE_REQUIRED"


class TestDeptRoutingMiddleware:
    """Tests for department routing middleware."""

    def test_single_mode_dept_route_returns_409(
        self, client, single_mode_bundle, rbac_policy_allow_all
    ):
        """In single mode, /d/{dept}/... should return 409 DEPT_MODE_REQUIRED."""
        response = client.post(
            "/d/finance/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "DEPT_MODE_REQUIRED"

    def test_multi_mode_unknown_dept_returns_400(
        self, client, multi_mode_bundle, rbac_policy_allow_all
    ):
        """In multi mode, unknown dept should return 400 DEPT_UNKNOWN."""
        response = client.post(
            "/d/unknown/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "DEPT_UNKNOWN"
        assert "unknown" in data["message"]

    def test_multi_mode_valid_dept_route_works(
        self, client, multi_mode_bundle, rbac_policy_allow_all
    ):
        """In multi mode, valid dept route should work."""
        response = client.post(
            "/d/finance/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        # Should succeed (200) since RBAC allows it
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"


class TestLegacyFinanceRoutes:
    """Tests for legacy /finance/... routes."""

    def test_single_mode_legacy_route_works(
        self, client, single_mode_bundle, rbac_policy_allow_all
    ):
        """In single mode, legacy /finance/expenses should work."""
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"

    def test_multi_mode_legacy_route_works_with_finance_dept(
        self, client, multi_mode_bundle, rbac_policy_allow_all
    ):
        """In multi mode with finance dept, legacy route is alias for finance."""
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"

    def test_multi_mode_legacy_route_fails_without_finance_dept(
        self, client, multi_mode_no_finance, rbac_policy_allow_all
    ):
        """In multi mode without finance dept, legacy route returns 409."""
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "DEPT_MODE_REQUIRED"


class TestLedgerStepNaming:
    """Tests for ledger step naming with department prefix."""

    def test_single_mode_no_dept_prefix_in_step(
        self, client, single_mode_bundle, rbac_policy_allow_all
    ):
        """In single mode, ledger step should not have dept prefix."""
        # This is tested via the helper function
        step = get_ledger_step_name("RBAC:expense.create", None)
        assert not step.startswith("DEPT:")
        assert step == "RBAC:expense.create"

    def test_multi_mode_dept_route_has_prefix(
        self, client, multi_mode_bundle, rbac_policy_allow_all
    ):
        """In multi mode via /d/{dept}/, step should have DEPT: prefix."""
        step = get_ledger_step_name("RBAC:expense.create", "finance")
        assert step == "DEPT:finance:RBAC:expense.create"

    def test_multi_mode_legacy_route_has_prefix(
        self, client, multi_mode_bundle, rbac_policy_allow_all
    ):
        """In multi mode via legacy route, step should have DEPT:finance: prefix."""
        # Legacy route in multi mode resolves to finance dept
        dept_id = validate_legacy_finance_route()
        step = get_ledger_step_name("RBAC:expense.create", dept_id)
        assert step == "DEPT:finance:RBAC:expense.create"


class TestGetExpenseRoutes:
    """Tests for GET /expenses/{id} routes."""

    def test_single_mode_legacy_get_works(
        self, client, single_mode_bundle, rbac_policy_allow_all
    ):
        """In single mode, GET /finance/expenses/{id} should work."""
        response = client.get(
            "/finance/expenses/exp-123",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "exp-123"
        assert data["status"] == "retrieved"

    def test_multi_mode_dept_get_works(
        self, client, multi_mode_bundle, rbac_policy_allow_all
    ):
        """In multi mode, GET /d/{dept}/finance/expenses/{id} should work."""
        response = client.get(
            "/d/finance/finance/expenses/exp-456",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "exp-456"
        assert data["status"] == "retrieved"
