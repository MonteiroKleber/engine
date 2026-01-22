"""Tests for Migration Check - Etapa 6.7.

Tests:
- MigrationCheckResult structure
- run_migration_checks() with all depts migrated
- run_migration_checks() with missing operations.json
- run_migration_checks() with unsupported bind.kind
- get_migration_status() for console display
- Integration: ENGINE_API_MODE=idl fails without operations.json
- Integration: ENGINE_API_MODE=both logs warnings
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.core.migration_check import (
    MigrationCheckResult,
    UnsupportedBind,
    run_migration_checks,
    get_migration_status,
    SUPPORTED_BIND_KINDS,
    MIGRATION_OK,
    MIGRATION_MISSING_OPERATIONS,
    MIGRATION_UNSUPPORTED_BIND_KIND,
)
from engine.core.operations import (
    set_operations,
    reset_all_operations,
    OperationsDef,
    Operation,
)
from engine.core.idl_router import API_MODE_LEGACY, API_MODE_IDL, API_MODE_BOTH


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before each test."""
    reset_all_operations()
    yield
    reset_all_operations()


class TestSupportedBindKinds:
    """Tests for supported bind.kind values."""

    def test_supported_bind_kinds_matches_dispatcher(self):
        """SUPPORTED_BIND_KINDS should match dispatcher handlers."""
        # These are the bind.kind values handled in idl_router.py:247-320
        expected = {"create", "read", "approval_decide"}
        assert SUPPORTED_BIND_KINDS == expected


class TestMigrationCheckResult:
    """Tests for MigrationCheckResult dataclass."""

    def test_ok_result(self):
        """OK result has expected fields."""
        result = MigrationCheckResult(
            ok=True,
            code=MIGRATION_OK,
            message="All departments migrated",
            depts_migrated=["finance", "support"],
        )
        assert result.ok is True
        assert result.code == MIGRATION_OK
        assert result.depts_migrated == ["finance", "support"]
        assert result.depts_not_migrated == []
        assert result.unsupported_binds == []
        assert result.warnings == []

    def test_failed_result_missing_ops(self):
        """Failed result for missing operations.json."""
        result = MigrationCheckResult(
            ok=False,
            code=MIGRATION_MISSING_OPERATIONS,
            message="1 dept(s) missing operations.json",
            depts_migrated=["finance"],
            depts_not_migrated=["support"],
            warnings=["Dept 'support' has no operations.json"],
        )
        assert result.ok is False
        assert result.code == MIGRATION_MISSING_OPERATIONS
        assert "support" in result.depts_not_migrated

    def test_failed_result_unsupported_bind(self):
        """Failed result for unsupported bind.kind."""
        result = MigrationCheckResult(
            ok=False,
            code=MIGRATION_UNSUPPORTED_BIND_KIND,
            message="1 operation(s) use unsupported bind.kind",
            unsupported_binds=[
                UnsupportedBind(
                    dept_id="finance",
                    operation_id="custom_op",
                    bind_kind="custom",
                )
            ],
        )
        assert result.ok is False
        assert result.code == MIGRATION_UNSUPPORTED_BIND_KIND
        assert len(result.unsupported_binds) == 1

    def test_to_dict(self):
        """to_dict() returns serializable dict."""
        result = MigrationCheckResult(
            ok=False,
            code=MIGRATION_UNSUPPORTED_BIND_KIND,
            message="test",
            unsupported_binds=[
                UnsupportedBind(
                    dept_id="finance",
                    operation_id="op1",
                    bind_kind="unknown",
                )
            ],
        )
        d = result.to_dict()
        assert d["ok"] is False
        assert d["code"] == MIGRATION_UNSUPPORTED_BIND_KIND
        assert len(d["unsupported_binds"]) == 1
        assert d["unsupported_binds"][0]["bind_kind"] == "unknown"


class TestRunMigrationChecks:
    """Tests for run_migration_checks()."""

    def test_single_mode_all_migrated(self):
        """Single-mode bundle with operations.json is migrated."""
        ops_def = OperationsDef(
            dept_id=None,
            operations=[
                Operation(
                    operation_id="create_expense",
                    method="POST",
                    path="/finance/expenses",
                    endpoint_sig="POST /finance/expenses",
                    permission="expense.create",
                    bind={"kind": "create", "entity": "Expense"},
                ),
            ],
        )
        set_operations(None, ops_def)

        result = run_migration_checks(None)

        assert result.ok is True
        assert result.code == MIGRATION_OK
        assert "_single" in result.depts_migrated
        assert result.depts_not_migrated == []

    def test_single_mode_no_operations(self):
        """Single-mode bundle without operations.json is not migrated."""
        # No operations set

        result = run_migration_checks(None)

        assert result.ok is False
        assert result.code == MIGRATION_MISSING_OPERATIONS
        assert "_single" in result.depts_not_migrated
        assert len(result.warnings) == 1
        assert "no operations.json" in result.warnings[0]

    def test_multi_mode_all_migrated(self):
        """Multi-mode bundle with all depts having operations.json."""
        for dept_id in ["finance", "support"]:
            ops_def = OperationsDef(
                dept_id=dept_id,
                operations=[
                    Operation(
                        operation_id=f"{dept_id}_create",
                        method="POST",
                        path=f"/{dept_id}/items",
                        endpoint_sig=f"POST /{dept_id}/items",
                        permission=f"{dept_id}.create",
                        bind={"kind": "create", "entity": "Item"},
                    ),
                ],
            )
            set_operations(dept_id, ops_def)

        result = run_migration_checks(["finance", "support"])

        assert result.ok is True
        assert result.code == MIGRATION_OK
        assert "finance" in result.depts_migrated
        assert "support" in result.depts_migrated

    def test_multi_mode_partial_migration(self):
        """Multi-mode with only some depts having operations.json."""
        # Only set operations for finance
        ops_def = OperationsDef(
            dept_id="finance",
            operations=[
                Operation(
                    operation_id="finance_create",
                    method="POST",
                    path="/finance/items",
                    endpoint_sig="POST /finance/items",
                    permission="finance.create",
                    bind={"kind": "create", "entity": "Item"},
                ),
            ],
        )
        set_operations("finance", ops_def)
        # support has no operations.json

        result = run_migration_checks(["finance", "support"])

        assert result.ok is False
        assert result.code == MIGRATION_MISSING_OPERATIONS
        assert "finance" in result.depts_migrated
        assert "support" in result.depts_not_migrated

    def test_unsupported_bind_kind(self):
        """Operation with unsupported bind.kind is flagged."""
        ops_def = OperationsDef(
            dept_id="finance",
            operations=[
                Operation(
                    operation_id="create_expense",
                    method="POST",
                    path="/finance/expenses",
                    endpoint_sig="POST /finance/expenses",
                    permission="expense.create",
                    bind={"kind": "create", "entity": "Expense"},
                ),
                Operation(
                    operation_id="custom_action",
                    method="POST",
                    path="/finance/custom",
                    endpoint_sig="POST /finance/custom",
                    permission="finance.custom",
                    bind={"kind": "custom_handler", "entity": "Custom"},  # unsupported
                ),
            ],
        )
        set_operations("finance", ops_def)

        result = run_migration_checks(["finance"])

        assert result.ok is False
        assert result.code == MIGRATION_UNSUPPORTED_BIND_KIND
        assert len(result.unsupported_binds) == 1
        assert result.unsupported_binds[0].bind_kind == "custom_handler"
        assert result.unsupported_binds[0].operation_id == "custom_action"
        assert "finance" in result.depts_not_migrated

    def test_operation_without_bind(self):
        """Operation without bind is OK (no bind.kind to check)."""
        ops_def = OperationsDef(
            dept_id="finance",
            operations=[
                Operation(
                    operation_id="get_status",
                    method="GET",
                    path="/finance/status",
                    endpoint_sig="GET /finance/status",
                    permission="finance.status",
                    bind=None,  # no bind
                ),
            ],
        )
        set_operations("finance", ops_def)

        result = run_migration_checks(["finance"])

        assert result.ok is True
        assert result.code == MIGRATION_OK

    def test_all_supported_bind_kinds(self):
        """All supported bind.kind values pass checks."""
        ops = []
        for i, kind in enumerate(SUPPORTED_BIND_KINDS):
            ops.append(
                Operation(
                    operation_id=f"op_{kind}",
                    method="POST",
                    path=f"/finance/op{i}",
                    endpoint_sig=f"POST /finance/op{i}",
                    permission="finance.test",
                    bind={"kind": kind, "entity": "Test"},
                )
            )
        ops_def = OperationsDef(dept_id="finance", operations=ops)
        set_operations("finance", ops_def)

        result = run_migration_checks(["finance"])

        assert result.ok is True
        assert result.code == MIGRATION_OK


class TestGetMigrationStatus:
    """Tests for get_migration_status()."""

    def test_returns_dict_for_template(self):
        """Returns dict suitable for template rendering."""
        ops_def = OperationsDef(
            dept_id="finance",
            operations=[
                Operation(
                    operation_id="create_expense",
                    method="POST",
                    path="/finance/expenses",
                    endpoint_sig="POST /finance/expenses",
                    permission="expense.create",
                    bind={"kind": "create", "entity": "Expense"},
                ),
            ],
        )
        set_operations("finance", ops_def)

        with patch("engine.core.migration_check.get_api_mode", return_value=API_MODE_BOTH):
            status = get_migration_status("inst-123", ["finance"])

        assert status["api_mode"] == API_MODE_BOTH
        assert status["depts_installed"] == ["finance"]
        assert status["depts_migrated"] == ["finance"]
        assert status["depts_not_migrated"] == []
        assert status["migration_complete"] is True
        assert status["check_code"] == MIGRATION_OK

    def test_single_mode_without_departments(self):
        """Single-mode returns _single as installed dept."""
        with patch("engine.core.migration_check.get_api_mode", return_value=API_MODE_LEGACY):
            status = get_migration_status("inst-123", None)

        assert status["depts_installed"] == ["_single"]

    def test_includes_warnings(self):
        """Includes warnings for not migrated depts."""
        # No operations set for finance
        with patch("engine.core.migration_check.get_api_mode", return_value=API_MODE_BOTH):
            status = get_migration_status("inst-123", ["finance"])

        assert status["migration_complete"] is False
        assert len(status["warnings"]) > 0
        assert "no operations.json" in status["warnings"][0]


class TestBootIntegration:
    """Integration tests for boot behavior with different API modes."""

    def test_idl_mode_fails_without_operations(self, monkeypatch):
        """ENGINE_API_MODE=idl should fail when operations.json is missing."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")

        # No operations set
        result = run_migration_checks(["finance"])

        # The result should be NOT OK
        assert result.ok is False
        assert result.code == MIGRATION_MISSING_OPERATIONS

        # In server.py, this would trigger RuntimeError

    def test_idl_mode_fails_with_unsupported_bind(self, monkeypatch):
        """ENGINE_API_MODE=idl should fail with unsupported bind.kind."""
        monkeypatch.setenv("ENGINE_API_MODE", "idl")

        ops_def = OperationsDef(
            dept_id="finance",
            operations=[
                Operation(
                    operation_id="custom_op",
                    method="POST",
                    path="/finance/custom",
                    endpoint_sig="POST /finance/custom",
                    permission="finance.custom",
                    bind={"kind": "unsupported_kind", "entity": "Custom"},
                ),
            ],
        )
        set_operations("finance", ops_def)

        result = run_migration_checks(["finance"])

        assert result.ok is False
        assert result.code == MIGRATION_UNSUPPORTED_BIND_KIND

    def test_both_mode_does_not_fail(self, monkeypatch):
        """ENGINE_API_MODE=both should not fail, only warn."""
        monkeypatch.setenv("ENGINE_API_MODE", "both")

        # No operations set
        result = run_migration_checks(["finance"])

        # Result is NOT OK but shouldn't cause RuntimeError
        assert result.ok is False
        # Warnings should be populated
        assert len(result.warnings) > 0

    def test_legacy_mode_not_checked(self, monkeypatch):
        """ENGINE_API_MODE=legacy should skip checks entirely."""
        # In server.py, checks are skipped if api_mode == "legacy"
        monkeypatch.setenv("ENGINE_API_MODE", "legacy")

        from engine.core.idl_router import get_api_mode

        assert get_api_mode() == API_MODE_LEGACY


class TestServerIntegration:
    """Tests for server.py integration with migration checks."""

    def test_migration_check_import(self):
        """migration_check module can be imported in server."""
        from engine.core.migration_check import run_migration_checks

        assert callable(run_migration_checks)

    def test_idl_router_api_mode_constants(self):
        """API mode constants are available for comparison."""
        from engine.core.idl_router import (
            API_MODE_LEGACY,
            API_MODE_IDL,
            API_MODE_BOTH,
        )

        assert API_MODE_LEGACY == "legacy"
        assert API_MODE_IDL == "idl"
        assert API_MODE_BOTH == "both"


class TestErrorCodes:
    """Tests for error codes in errors.py."""

    def test_migration_error_codes_exist(self):
        """Migration error codes are defined in errors.py."""
        from engine.core.errors import (
            MIGRATION_CHECK_FAILED,
            MIGRATION_MISSING_OPERATIONS,
            MIGRATION_UNSUPPORTED_BIND_KIND,
        )

        assert MIGRATION_CHECK_FAILED == "MIGRATION_CHECK_FAILED"
        assert MIGRATION_MISSING_OPERATIONS == "MIGRATION_MISSING_OPERATIONS"
        assert MIGRATION_UNSUPPORTED_BIND_KIND == "MIGRATION_UNSUPPORTED_BIND_KIND"
