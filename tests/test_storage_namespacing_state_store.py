"""Tests for state store namespacing by institution."""

from pathlib import Path

import pytest

from engine.core.state_store import (
    StateStore,
    get_state_store_path_for_institution,
    get_state_store,
    set_state_store,
    reset_all_state_stores,
)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))

    # Clear any ENV overrides for state store
    monkeypatch.delenv("ENGINE_STATE_STORE_DIR", raising=False)

    reset_all_state_stores()

    yield

    reset_all_state_stores()


class TestStateStorePathResolution:
    """Test state store path resolution for institutions."""

    def test_default_path_under_institution_root(self, tmp_path, monkeypatch):
        """Default state store path is under institution root."""
        institution_id = "11111111-1111-1111-1111-111111111111"

        path = get_state_store_path_for_institution(institution_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "state_store.json"

    def test_dept_specific_path_under_institution_root(self, tmp_path, monkeypatch):
        """Department-specific state store path is under institution root."""
        institution_id = "22222222-2222-2222-2222-222222222222"
        dept_id = "finance"

        path = get_state_store_path_for_institution(institution_id, dept_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "state_store.finance.json"

    def test_absolute_env_path_overrides(self, tmp_path, monkeypatch):
        """Absolute ENGINE_STATE_STORE_DIR overrides institution namespacing."""
        institution_id = "33333333-3333-3333-3333-333333333333"
        absolute_dir = tmp_path / "absolute" / "state"

        monkeypatch.setenv("ENGINE_STATE_STORE_DIR", str(absolute_dir))

        path = get_state_store_path_for_institution(institution_id)

        assert path == absolute_dir / "state_store.json"

    def test_relative_env_path_under_institution_root(self, tmp_path, monkeypatch):
        """Relative ENGINE_STATE_STORE_DIR is under institution root."""
        institution_id = "44444444-4444-4444-4444-444444444444"

        monkeypatch.setenv("ENGINE_STATE_STORE_DIR", "custom/state")

        path = get_state_store_path_for_institution(institution_id)

        expected_root = tmp_path / "data" / "institutions" / institution_id
        assert path == expected_root / "custom" / "state" / "state_store.json"

    def test_different_institutions_different_paths(self, tmp_path, monkeypatch):
        """Different institutions have different state store paths."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        path_a = get_state_store_path_for_institution(inst_a)
        path_b = get_state_store_path_for_institution(inst_b)

        assert path_a != path_b
        assert inst_a in str(path_a)
        assert inst_b in str(path_b)


class TestStateStoreInstanceIsolation:
    """Test state store instance isolation per institution."""

    def test_get_state_store_returns_institution_specific_instance(self, tmp_path, monkeypatch):
        """get_state_store with institution_id returns institution-specific store."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        store_a = get_state_store(institution_id=inst_a)
        store_b = get_state_store(institution_id=inst_b)

        assert store_a is not store_b
        assert str(store_a._path) != str(store_b._path)

    def test_get_state_store_returns_same_instance_for_same_institution(self, tmp_path, monkeypatch):
        """get_state_store returns same instance for same institution."""
        institution_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"

        store_1 = get_state_store(institution_id=institution_id)
        store_2 = get_state_store(institution_id=institution_id)

        assert store_1 is store_2

    def test_state_store_init_with_institution_id(self, tmp_path, monkeypatch):
        """StateStore initialized with institution_id uses correct path."""
        institution_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"

        store = StateStore(institution_id=institution_id)

        expected_path = get_state_store_path_for_institution(institution_id)
        assert store._path == expected_path


class TestStateStoreDataIsolation:
    """Test that state store data is isolated per institution."""

    def test_expenses_isolated_between_institutions(self, tmp_path, monkeypatch):
        """Expenses created in one institution are not visible in another."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        store_a = get_state_store(institution_id=inst_a)
        store_b = get_state_store(institution_id=inst_b)

        # Create expense in institution A
        store_a.create_expense(
            expense_id="exp-a-001",
            approval_id="appr-a-001",
            payload_sha256="sha256-a",
            payload_raw=b'{"amount": 100}',
        )

        # Verify expense exists in A
        expense_a = store_a.get_expense("exp-a-001")
        assert expense_a is not None
        assert expense_a.expense_id == "exp-a-001"

        # Verify expense does NOT exist in B
        expense_b = store_b.get_expense("exp-a-001")
        assert expense_b is None

    def test_expenses_in_same_institution_are_visible(self, tmp_path, monkeypatch):
        """Expenses created in an institution are visible to same institution."""
        institution_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

        store_1 = get_state_store(institution_id=institution_id)

        # Create expense
        store_1.create_expense(
            expense_id="exp-e-001",
            approval_id="appr-e-001",
            payload_sha256="sha256-e",
            payload_raw=b'{"amount": 200}',
        )

        # Get another reference to same store
        store_2 = get_state_store(institution_id=institution_id)

        # Expense should be visible
        expense = store_2.get_expense("exp-e-001")
        assert expense is not None


class TestStateStoreDeptIsolation:
    """Test department isolation within institution."""

    def test_dept_stores_isolated_within_institution(self, tmp_path, monkeypatch):
        """Different departments have isolated state stores within same institution."""
        institution_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"

        store_finance = get_state_store(dept_id="finance", institution_id=institution_id)
        store_hr = get_state_store(dept_id="hr", institution_id=institution_id)

        assert store_finance is not store_hr
        assert store_finance._path != store_hr._path

        # Create expense in finance
        store_finance.create_expense(
            expense_id="exp-fin-001",
            approval_id="appr-fin-001",
            payload_sha256="sha256-fin",
            payload_raw=b'{"dept": "finance"}',
        )

        # Not visible in HR
        expense_hr = store_hr.get_expense("exp-fin-001")
        assert expense_hr is None


class TestResetStateStores:
    """Test state store reset functionality."""

    def test_reset_clears_all_institution_stores(self, tmp_path, monkeypatch):
        """reset_all_state_stores clears all cached store instances."""
        inst_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        # Create some stores
        store_a_1 = get_state_store(institution_id=inst_a)
        store_b_1 = get_state_store(institution_id=inst_b)

        # Reset
        reset_all_state_stores()

        # Get again - should be new instances
        store_a_2 = get_state_store(institution_id=inst_a)
        store_b_2 = get_state_store(institution_id=inst_b)

        assert store_a_1 is not store_a_2
        assert store_b_1 is not store_b_2
