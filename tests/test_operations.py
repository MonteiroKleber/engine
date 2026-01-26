"""Tests for OperationRegistry - operations.json contract and runtime registry.

Tests:
1. Schema validation (parse_operations_data)
2. Emit from IRCS (emit_operations_from_ircs)
3. Emit from ParsedIDL (emit_operations_from_parsed)
4. Loader integration (load_operations_from_file)
5. Registry lookup (get_operation_by_endpoint_sig, get_operation_by_method_path)
6. Legacy bundle compatibility (no operations.json)
7. Deterministic output (sorted operations)
"""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.core.operations import (
    Operation,
    OperationsDef,
    OperationsSchemaError,
    OPERATIONS_SCHEMA_VERSION,
    parse_operations_data,
    load_operations_from_file,
    set_operations,
    get_operations,
    get_operation_by_endpoint_sig,
    get_operation_by_method_path,
    reset_all_operations,
)
from engine.ise.emit.operations_emit import (
    emit_operations_from_ircs,
    emit_operations_from_parsed,
    emit_operations,
    emit_operations_json,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def clean_registry():
    """Clean registry before and after each test."""
    reset_all_operations()
    yield
    reset_all_operations()


@pytest.fixture
def sample_ircs():
    """Sample IRCS v1 with operations."""
    return {
        "ir_version": "ircs.v1",
        "system": {"name": "Finance System", "version": "1.0.0"},
        "operations": {
            "api": [
                {
                    "id": "expense_create",
                    "method": "POST",
                    "path": "/finance/expenses",
                    "permission": "expense.create",
                    "scope": "tenant",
                    "idempotency": "required",
                    "errors": [400, 401, 403],
                    "bind": {"kind": "create", "entity": "Expense"},
                },
                {
                    "id": "approval_decide",
                    "method": "POST",
                    "path": "/approvals/{approval_id}/decide",
                    "permission": "approval.decide",
                    "scope": "tenant",
                    "idempotency": "none",
                    "errors": [400, 401, 403, 404],
                    "bind": {"kind": "action", "entity": "Approval"},
                },
                {
                    "id": "expense_list",
                    "method": "GET",
                    "path": "/finance/expenses",
                    "permission": "expense.read",
                    "scope": "tenant",
                },
            ]
        },
    }


@pytest.fixture
def sample_ircs_with_transition_workflow():
    """IRCS v1 including workflow transitions for bind.kind=transition enrichment."""
    return {
        "ir_version": "ircs.v1",
        "system": {"name": "Bazari MVP", "version": "1.0.0"},
        "workflows": [
            {
                "name": "ReportFlow",
                "on_entity": "ContentReport",
                "state_field": "state",
                "transitions": [
                    {
                        "name": "Triage",
                        "from": "Pending",
                        "to": "Triaged",
                        "guard": {"lit": True, "type": "bool"},
                        "effects": [
                            {"kind": "set_state", "value": "Triaged"},
                            {"kind": "bump_version", "field": "version", "by": 1},
                        ],
                        "approvals": None,
                    }
                ],
            }
        ],
        "operations": {
            "api": [
                {
                    "id": "report_triage",
                    "method": "POST",
                    "path": "/moderation/reports/{report_id}/triage",
                    "permission": "reports.triage",
                    "scope": "tenant",
                    "idempotency": "required",
                    "errors": [400, 401, 403, 404, 409],
                    "bind": {
                        "kind": "transition",
                        "entity": "ContentReport",
                        "workflow": "ReportFlow",
                        "transition": "Triage",
                    },
                }
            ]
        },
    }


@pytest.fixture
def sample_operations_data():
    """Sample valid operations.json data."""
    return {
        "operations_schema_version": "1.0",
        "operations": [
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
                "operation_id": "approval_decide",
                "method": "POST",
                "path": "/approvals/{approval_id}/decide",
                "endpoint_sig": "POST /approvals/{approval_id}/decide",
                "permission": "approval.decide",
                "scope": "tenant",
                "idempotency": "none",
                "errors": [400, 401, 403, 404],
            },
        ],
    }


# =============================================================================
# Schema Validation Tests
# =============================================================================

class TestSchemaValidation:
    """Test parse_operations_data validation."""

    def test_valid_operations(self, sample_operations_data):
        """Valid operations data parses successfully."""
        ops_def = parse_operations_data(sample_operations_data)

        assert ops_def.dept_id is None
        assert len(ops_def.operations) == 2

        op = ops_def.operations[0]
        assert op.operation_id == "expense_create"
        assert op.method == "POST"
        assert op.path == "/finance/expenses"
        assert op.endpoint_sig == "POST /finance/expenses"
        assert op.permission == "expense.create"
        assert op.scope == "tenant"
        assert op.idempotency == "required"
        assert op.errors == [400, 401, 403]
        assert op.bind == {"kind": "create", "entity": "Expense"}

    def test_with_dept_id(self, sample_operations_data):
        """Operations with dept_id are parsed correctly."""
        sample_operations_data["dept_id"] = "finance"
        ops_def = parse_operations_data(sample_operations_data)
        assert ops_def.dept_id == "finance"

    def test_dept_id_override(self, sample_operations_data):
        """dept_id parameter overrides data value."""
        sample_operations_data["dept_id"] = "finance"
        ops_def = parse_operations_data(sample_operations_data, dept_id="support")
        assert ops_def.dept_id == "support"

    def test_invalid_schema_version(self):
        """Invalid schema version raises error."""
        data = {"operations_schema_version": "2.0", "operations": []}
        with pytest.raises(OperationsSchemaError) as exc:
            parse_operations_data(data)
        assert "2.0" in str(exc.value)

    def test_missing_operation_id(self):
        """Missing operation_id raises error."""
        data = {
            "operations_schema_version": "1.0",
            "operations": [
                {"method": "POST", "path": "/test", "endpoint_sig": "POST /test", "permission": "test"}
            ],
        }
        with pytest.raises(OperationsSchemaError) as exc:
            parse_operations_data(data)
        assert "operation_id" in str(exc.value).lower()

    def test_invalid_method(self):
        """Invalid HTTP method raises error."""
        data = {
            "operations_schema_version": "1.0",
            "operations": [
                {
                    "operation_id": "test",
                    "method": "INVALID",
                    "path": "/test",
                    "endpoint_sig": "INVALID /test",
                    "permission": "test",
                }
            ],
        }
        with pytest.raises(OperationsSchemaError) as exc:
            parse_operations_data(data)
        assert "method" in str(exc.value).lower()

    def test_relative_path_rejected(self):
        """Relative path (not starting with /) raises error."""
        data = {
            "operations_schema_version": "1.0",
            "operations": [
                {
                    "operation_id": "test",
                    "method": "POST",
                    "path": "test/path",
                    "endpoint_sig": "POST test/path",
                    "permission": "test",
                }
            ],
        }
        with pytest.raises(OperationsSchemaError) as exc:
            parse_operations_data(data)
        assert "absolute" in str(exc.value).lower()

    def test_path_traversal_rejected(self):
        """Path with .. is rejected."""
        data = {
            "operations_schema_version": "1.0",
            "operations": [
                {
                    "operation_id": "test",
                    "method": "POST",
                    "path": "/test/../secret",
                    "endpoint_sig": "POST /test/../secret",
                    "permission": "test",
                }
            ],
        }
        with pytest.raises(OperationsSchemaError) as exc:
            parse_operations_data(data)
        assert ".." in str(exc.value)

    def test_endpoint_sig_mismatch(self):
        """endpoint_sig must match method + path."""
        data = {
            "operations_schema_version": "1.0",
            "operations": [
                {
                    "operation_id": "test",
                    "method": "POST",
                    "path": "/test",
                    "endpoint_sig": "GET /test",  # Wrong method
                    "permission": "test",
                }
            ],
        }
        with pytest.raises(OperationsSchemaError) as exc:
            parse_operations_data(data)
        assert "doesn't match" in str(exc.value)

    def test_invalid_scope(self):
        """Invalid scope raises error."""
        data = {
            "operations_schema_version": "1.0",
            "operations": [
                {
                    "operation_id": "test",
                    "method": "POST",
                    "path": "/test",
                    "endpoint_sig": "POST /test",
                    "permission": "test",
                    "scope": "invalid",
                }
            ],
        }
        with pytest.raises(OperationsSchemaError) as exc:
            parse_operations_data(data)
        assert "scope" in str(exc.value).lower()


# =============================================================================
# Emit Tests
# =============================================================================

class TestEmitOperations:
    """Test operations emitters."""

    def test_emit_from_ircs(self, sample_ircs):
        """Emit operations from IRCS v1 data."""
        result = emit_operations_from_ircs(sample_ircs)

        assert result["operations_schema_version"] == OPERATIONS_SCHEMA_VERSION
        assert len(result["operations"]) == 3

        # Check operations are sorted by (method, path, operation_id)
        ops = result["operations"]
        # GET /finance/expenses should come before POST /approvals/* (GET < POST)
        assert ops[0]["method"] == "GET"
        assert ops[0]["operation_id"] == "expense_list"

    def test_emit_from_ircs_with_dept_id(self, sample_ircs):
        """Emit operations with dept_id."""
        result = emit_operations_from_ircs(sample_ircs, dept_id="finance")
        assert result["dept_id"] == "finance"

    def test_emit_transition_includes_transition_def(self, sample_ircs_with_transition_workflow):
        """Transitions include a transition_def usable by the dispatcher."""
        result = emit_operations_from_ircs(sample_ircs_with_transition_workflow)
        assert len(result["operations"]) == 1
        op = result["operations"][0]
        bind = op["bind"]
        assert bind["kind"] == "transition"
        assert bind["workflow"] == "ReportFlow"
        assert bind["transition"] == "Triage"
        transition_def = bind["transition_def"]
        assert transition_def["guard"] is True
        assert transition_def["from"] == "PENDING"
        assert transition_def["to"] == "TRIAGED"
        assert transition_def["effects"] == [
            {"type": "set_state", "value": "TRIAGED"},
            {"type": "bump_version", "value": 1},
        ]

    def test_emit_operations_json_deterministic(self, sample_ircs):
        """JSON output is deterministic (sorted keys)."""
        json1 = emit_operations_json(sample_ircs)
        json2 = emit_operations_json(sample_ircs)
        assert json1 == json2

    def test_emit_skips_invalid_operations(self):
        """Operations without required fields are skipped."""
        ir = {
            "ir_version": "ircs.v1",
            "operations": {
                "api": [
                    {"id": "valid", "method": "POST", "path": "/test", "permission": "test"},
                    {"id": "", "method": "POST", "path": "/invalid"},  # No id
                    {"id": "no_path", "method": "GET", "path": ""},  # No path
                    {"id": "relative", "method": "GET", "path": "relative"},  # Relative path
                ]
            },
        }
        result = emit_operations_from_ircs(ir)
        assert len(result["operations"]) == 1
        assert result["operations"][0]["operation_id"] == "valid"


# =============================================================================
# Registry Tests
# =============================================================================

class TestOperationsRegistry:
    """Test runtime registry functions."""

    def test_set_and_get_single_mode(self, sample_operations_data):
        """Set and get operations for single mode."""
        ops_def = parse_operations_data(sample_operations_data)
        set_operations(None, ops_def)

        retrieved = get_operations(None)
        assert retrieved is not None
        assert len(retrieved.operations) == 2

    def test_set_and_get_multi_mode(self, sample_operations_data):
        """Set and get operations for multi-dept mode."""
        ops_def = parse_operations_data(sample_operations_data, dept_id="finance")
        set_operations("finance", ops_def)

        retrieved = get_operations("finance")
        assert retrieved is not None
        assert retrieved.dept_id == "finance"

        # Other dept should return None
        assert get_operations("support") is None

    def test_lookup_by_endpoint_sig(self, sample_operations_data):
        """Lookup operation by endpoint_sig."""
        ops_def = parse_operations_data(sample_operations_data)
        set_operations(None, ops_def)

        op = get_operation_by_endpoint_sig(None, "POST /finance/expenses")
        assert op is not None
        assert op.operation_id == "expense_create"

        op2 = get_operation_by_endpoint_sig(None, "POST /approvals/{approval_id}/decide")
        assert op2 is not None
        assert op2.operation_id == "approval_decide"

        # Non-existent
        op3 = get_operation_by_endpoint_sig(None, "DELETE /nonexistent")
        assert op3 is None

    def test_lookup_by_method_path(self, sample_operations_data):
        """Lookup operation by method + path."""
        ops_def = parse_operations_data(sample_operations_data)
        set_operations(None, ops_def)

        op = get_operation_by_method_path(None, "POST", "/finance/expenses")
        assert op is not None
        assert op.operation_id == "expense_create"

        # Case insensitive method
        op2 = get_operation_by_method_path(None, "post", "/finance/expenses")
        assert op2 is not None
        assert op2.operation_id == "expense_create"

    def test_lookup_no_registry(self):
        """Lookup returns None when no registry is set."""
        op = get_operation_by_endpoint_sig(None, "POST /finance/expenses")
        assert op is None

        op2 = get_operation_by_method_path(None, "POST", "/finance/expenses")
        assert op2 is None

    def test_clear_operations(self, sample_operations_data):
        """Clear operations for a dept."""
        ops_def = parse_operations_data(sample_operations_data)
        set_operations(None, ops_def)
        assert get_operations(None) is not None

        set_operations(None, None)  # Clear
        assert get_operations(None) is None


# =============================================================================
# File Loading Tests
# =============================================================================

class TestLoadOperationsFromFile:
    """Test loading operations from file."""

    def test_load_valid_file(self, sample_operations_data):
        """Load valid operations.json file."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "operations.json"
            path.write_text(json.dumps(sample_operations_data))

            ops_def = load_operations_from_file(path)
            assert ops_def is not None
            assert len(ops_def.operations) == 2

    def test_load_missing_file(self):
        """Missing file returns None (not error)."""
        path = Path("/nonexistent/operations.json")
        ops_def = load_operations_from_file(path)
        assert ops_def is None

    def test_load_invalid_json(self):
        """Invalid JSON raises error."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "operations.json"
            path.write_text("{invalid json")

            with pytest.raises(OperationsSchemaError):
                load_operations_from_file(path)


# =============================================================================
# Legacy Compatibility Tests
# =============================================================================

class TestLegacyCompatibility:
    """Test backward compatibility with bundles without operations.json."""

    def test_no_operations_returns_none(self):
        """Without operations.json, get_operations returns None."""
        # Don't set anything - simulates legacy bundle
        assert get_operations(None) is None
        assert get_operations("finance") is None

    def test_lookup_gracefully_handles_no_registry(self):
        """Lookups work when no registry is set (return None, no crash)."""
        op = get_operation_by_endpoint_sig(None, "POST /finance/expenses")
        assert op is None

        op2 = get_operation_by_method_path(None, "POST", "/finance/expenses")
        assert op2 is None

    def test_to_dict_serialization(self, sample_operations_data):
        """OperationsDef.to_dict() produces valid output."""
        ops_def = parse_operations_data(sample_operations_data)
        result = ops_def.to_dict()

        # Should be valid for re-parsing
        reparsed = parse_operations_data(result)
        assert len(reparsed.operations) == len(ops_def.operations)


# =============================================================================
# Integration Test
# =============================================================================

class TestIntegration:
    """Integration tests with full emit → parse → lookup cycle."""

    def test_emit_parse_lookup_cycle(self, sample_ircs):
        """Full cycle: emit from IRCS → parse → lookup."""
        # Emit
        operations_data = emit_operations_from_ircs(sample_ircs)

        # Parse
        ops_def = parse_operations_data(operations_data)

        # Load into registry
        set_operations(None, ops_def)

        # Lookup
        op = get_operation_by_endpoint_sig(None, "POST /finance/expenses")
        assert op is not None
        assert op.operation_id == "expense_create"
        assert op.permission == "expense.create"

        op2 = get_operation_by_endpoint_sig(None, "POST /approvals/{approval_id}/decide")
        assert op2 is not None
        assert op2.operation_id == "approval_decide"
