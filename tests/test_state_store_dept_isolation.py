"""Tests for state store department isolation."""

import json
import os
import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from engine.api.server import app
from engine.loader.load_bundle import (
    _set_bundle_context,
    BundleContext,
    DeptContracts,
)
from engine.core.state_store import (
    StateStore,
    get_state_store,
    set_state_store,
    init_state_store,
    reset_all_state_stores,
    get_state_store_path,
    validate_dept_id,
    STATUS_PENDING_APPROVAL,
)
from engine.core.rbac import set_rbac_policy, RBACPolicy
from engine.core.approvals import set_approvals_policy, ApprovalsPolicy


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def state_dir(tmp_path: Path):
    """Set up temporary state store directory."""
    state_path = tmp_path / "state"
    state_path.mkdir()
    old_env = os.environ.get("ENGINE_STATE_STORE_DIR")
    os.environ["ENGINE_STATE_STORE_DIR"] = str(state_path)
    yield state_path
    if old_env:
        os.environ["ENGINE_STATE_STORE_DIR"] = old_env
    else:
        os.environ.pop("ENGINE_STATE_STORE_DIR", None)


@pytest.fixture
def single_mode_bundle(tmp_path: Path, state_dir: Path):
    """Create a single-department bundle context."""
    ctx = BundleContext(
        mode="single",
        path=tmp_path,
        manifest={"version": "1.0.0"},
    )
    _set_bundle_context(ctx)
    reset_all_state_stores()
    init_state_store()
    yield ctx
    _set_bundle_context(None)
    reset_all_state_stores()


@pytest.fixture
def multi_mode_bundle(tmp_path: Path, state_dir: Path):
    """Create a multi-department bundle with finance and finance2 depts."""
    finance_dept = DeptContracts(
        name="finance",
        path=tmp_path / "departments" / "finance",
    )
    finance2_dept = DeptContracts(
        name="finance2",
        path=tmp_path / "departments" / "finance2",
    )
    ctx = BundleContext(
        mode="multi",
        path=tmp_path,
        manifest={"version": "1.0.0"},
        departments={"finance": finance_dept, "finance2": finance2_dept},
    )
    _set_bundle_context(ctx)
    reset_all_state_stores()
    init_state_store()
    yield ctx
    _set_bundle_context(None)
    reset_all_state_stores()


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


@pytest.fixture
def approvals_policy():
    """Set approvals policy that requires approval for expenses."""
    policy = ApprovalsPolicy({
        "rules": [
            {
                "rule_name": "expense_approval",
                "trigger": {"api": "POST /finance/expenses"},
                "approver_roles": ["manager"],
                "quorum": 1,
            }
        ]
    })
    set_approvals_policy(policy)
    yield
    set_approvals_policy(None)


class TestGetStateStorePath:
    """Tests for get_state_store_path helper."""

    def test_no_dept_returns_default_path(self, state_dir: Path):
        """Without dept_id, should return default state_store.json."""
        path = get_state_store_path(None)
        assert path == state_dir / "state_store.json"

    def test_with_dept_returns_dept_path(self, state_dir: Path):
        """With dept_id, should return state_store.<dept>.json."""
        path = get_state_store_path("finance")
        assert path == state_dir / "state_store.finance.json"

        path = get_state_store_path("hr")
        assert path == state_dir / "state_store.hr.json"

    def test_dept_with_special_chars(self, state_dir: Path):
        """Dept with valid special chars (underscore, hyphen) should work."""
        path = get_state_store_path("dept_one")
        assert path == state_dir / "state_store.dept_one.json"

        path = get_state_store_path("dept-two")
        assert path == state_dir / "state_store.dept-two.json"


class TestValidateDeptId:
    """Tests for validate_dept_id helper."""

    def test_valid_dept_ids(self):
        """Valid dept_ids should not raise."""
        validate_dept_id("finance")
        validate_dept_id("hr")
        validate_dept_id("dept_one")
        validate_dept_id("dept-two")
        validate_dept_id("Finance123")

    def test_invalid_dept_id_with_slash(self):
        """Dept_id with slash should raise RuntimeError."""
        with pytest.raises(RuntimeError) as exc_info:
            validate_dept_id("../etc")
        assert "STATE_STORE_DEPT_INVALID" in str(exc_info.value)

    def test_invalid_dept_id_with_dot(self):
        """Dept_id with dot should raise RuntimeError."""
        with pytest.raises(RuntimeError) as exc_info:
            validate_dept_id("dept.name")
        assert "STATE_STORE_DEPT_INVALID" in str(exc_info.value)

    def test_invalid_dept_id_with_space(self):
        """Dept_id with space should raise RuntimeError."""
        with pytest.raises(RuntimeError) as exc_info:
            validate_dept_id("dept name")
        assert "STATE_STORE_DEPT_INVALID" in str(exc_info.value)


class TestStateStoreCreation:
    """Tests for StateStore creation with dept_id."""

    def test_create_store_no_dept(self, state_dir: Path):
        """Store without dept_id uses default path."""
        store = StateStore(dept_id=None)
        assert store._path == state_dir / "state_store.json"

    def test_create_store_with_dept(self, state_dir: Path):
        """Store with dept_id uses dept-specific path."""
        store = StateStore(dept_id="finance")
        assert store._path == state_dir / "state_store.finance.json"

    def test_explicit_path_overrides_dept(self, state_dir: Path):
        """Explicit path takes precedence over dept_id."""
        explicit_path = state_dir / "custom.json"
        store = StateStore(path=explicit_path, dept_id="finance")
        assert store._path == explicit_path


class TestSingleModeStateStore:
    """Tests for single-mode state store behavior."""

    def test_single_mode_uses_default_store(
        self, client, single_mode_bundle, rbac_policy_allow_all, approvals_policy, state_dir
    ):
        """In single mode, expense is saved to default state_store.json."""
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending_approval"
        expense_id = data["expense_id"]

        # Verify file exists at default location
        default_store_path = state_dir / "state_store.json"
        assert default_store_path.exists()

        # Verify expense is in the store
        with open(default_store_path, "r") as f:
            store_data = json.load(f)
        assert expense_id in store_data["expenses"]

    def test_single_mode_get_expense_from_store(
        self, client, single_mode_bundle, rbac_policy_allow_all, approvals_policy, state_dir
    ):
        """In single mode, can retrieve expense from default store."""
        # Create expense
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 202
        expense_id = response.json()["expense_id"]

        # Verify expense exists in state store
        store = get_state_store()
        expense = store.get_expense(expense_id)
        assert expense is not None
        assert expense.status == STATUS_PENDING_APPROVAL


class TestMultiModeStateStoreIsolation:
    """Tests for multi-mode state store isolation."""

    def test_multi_mode_creates_dept_specific_file(
        self, client, multi_mode_bundle, rbac_policy_allow_all, approvals_policy, state_dir
    ):
        """In multi mode, /d/{dept}/... creates dept-specific state file."""
        response = client.post(
            "/d/finance/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 202
        data = response.json()
        expense_id = data["expense_id"]

        # Verify file exists at dept-specific location
        finance_store_path = state_dir / "state_store.finance.json"
        assert finance_store_path.exists()

        # Verify expense is in the finance store
        with open(finance_store_path, "r") as f:
            store_data = json.load(f)
        assert expense_id in store_data["expenses"]

    def test_multi_mode_different_depts_have_separate_files(
        self, client, multi_mode_bundle, rbac_policy_allow_all, approvals_policy, state_dir
    ):
        """Different departments create separate state files."""
        # Create expense in finance dept
        response1 = client.post(
            "/d/finance/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response1.status_code == 202
        expense_id_finance = response1.json()["expense_id"]

        # Create expense in finance2 dept
        response2 = client.post(
            "/d/finance2/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 200},
        )
        assert response2.status_code == 202
        expense_id_finance2 = response2.json()["expense_id"]

        # Verify both files exist
        finance_store_path = state_dir / "state_store.finance.json"
        finance2_store_path = state_dir / "state_store.finance2.json"
        assert finance_store_path.exists()
        assert finance2_store_path.exists()

        # Verify each expense is in correct store
        with open(finance_store_path, "r") as f:
            finance_data = json.load(f)
        with open(finance2_store_path, "r") as f:
            finance2_data = json.load(f)

        assert expense_id_finance in finance_data["expenses"]
        assert expense_id_finance not in finance2_data["expenses"]
        assert expense_id_finance2 in finance2_data["expenses"]
        assert expense_id_finance2 not in finance_data["expenses"]

    def test_multi_mode_isolation_expense_not_found_cross_dept(
        self, client, multi_mode_bundle, rbac_policy_allow_all, approvals_policy, state_dir
    ):
        """Expense created in one dept is NOT found when querying another dept's store."""
        # Create expense in finance dept
        response = client.post(
            "/d/finance/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 202
        expense_id = response.json()["expense_id"]

        # Verify expense exists in finance store
        finance_store = get_state_store("finance")
        assert finance_store.get_expense(expense_id) is not None

        # Verify expense does NOT exist in finance2 store
        finance2_store = get_state_store("finance2")
        assert finance2_store.get_expense(expense_id) is None


class TestLegacyRouteInMultiMode:
    """Tests for legacy /finance/... route in multi-mode."""

    def test_legacy_route_writes_to_finance_dept_store(
        self, client, multi_mode_bundle, rbac_policy_allow_all, approvals_policy, state_dir
    ):
        """Legacy /finance/expenses in multi mode writes to state_store.finance.json."""
        response = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response.status_code == 202
        expense_id = response.json()["expense_id"]

        # Verify expense is in finance dept store (NOT default store)
        finance_store_path = state_dir / "state_store.finance.json"
        default_store_path = state_dir / "state_store.json"

        assert finance_store_path.exists()

        with open(finance_store_path, "r") as f:
            finance_data = json.load(f)
        assert expense_id in finance_data["expenses"]

        # Default store should not have the expense
        # (it may or may not exist, but if it does, shouldn't have this expense)
        if default_store_path.exists():
            with open(default_store_path, "r") as f:
                default_data = json.load(f)
            assert expense_id not in default_data.get("expenses", {})

    def test_legacy_route_same_as_dept_route(
        self, client, multi_mode_bundle, rbac_policy_allow_all, approvals_policy, state_dir
    ):
        """Legacy and dept route write to same store in multi mode."""
        # Create via legacy route
        response1 = client.post(
            "/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 100},
        )
        assert response1.status_code == 202
        expense_id_legacy = response1.json()["expense_id"]

        # Create via dept route
        response2 = client.post(
            "/d/finance/finance/expenses",
            headers={
                "X-Actor-Id": "550e8400-e29b-41d4-a716-446655440000",
                "X-Actor-Roles": "admin",
            },
            json={"amount": 200},
        )
        assert response2.status_code == 202
        expense_id_dept = response2.json()["expense_id"]

        # Both should be in same finance store
        finance_store_path = state_dir / "state_store.finance.json"
        with open(finance_store_path, "r") as f:
            finance_data = json.load(f)

        assert expense_id_legacy in finance_data["expenses"]
        assert expense_id_dept in finance_data["expenses"]


class TestGetStateStoreFunction:
    """Tests for get_state_store function behavior."""

    def test_get_state_store_no_dept_returns_default(self, state_dir: Path):
        """get_state_store(None) returns default store after init."""
        reset_all_state_stores()
        init_state_store()
        store = get_state_store(None)
        assert store is not None
        assert store._path == state_dir / "state_store.json"
        reset_all_state_stores()

    def test_get_state_store_with_dept_creates_on_demand(self, state_dir: Path):
        """get_state_store(dept_id) creates store on demand."""
        reset_all_state_stores()
        init_state_store()

        # First call creates the store
        store1 = get_state_store("finance")
        assert store1 is not None
        assert store1._path == state_dir / "state_store.finance.json"

        # Second call returns same instance
        store2 = get_state_store("finance")
        assert store2 is store1

        reset_all_state_stores()

    def test_different_depts_get_different_stores(self, state_dir: Path):
        """Different dept_ids return different store instances."""
        reset_all_state_stores()
        init_state_store()

        store_finance = get_state_store("finance")
        store_hr = get_state_store("hr")

        assert store_finance is not store_hr
        assert store_finance._path != store_hr._path

        reset_all_state_stores()
