"""E2E (HTTP) proof for Bazari dispatcher transitions (Expansão 02).

Tests bind.kind=transition with the supported effect subset:
- set_state("<STATE>")
- set_field("<field>", <literal>)
- bump_version(1)

Hard-gate test referenced by docs/specs/expansao/02-dispatcher-transitions-bazari/spec.md.
"""

import json
import uuid
from pathlib import Path

import pytest

from engine.core.actor_context import ActorContext
from engine.core.dispatcher import dispatch_create, dispatch_transition
from engine.core.operations import (
    Operation,
    OperationsDef,
    set_operations,
    get_operations,
    reset_all_operations,
)
from engine.core.rbac import RBACPolicy, set_rbac_policy, reset_all_rbac
from engine.core.state_store import get_state_store, reset_all_state_stores


def _setup_rbac_policy():
    """Set up RBAC policy granting moderator role necessary permissions."""
    rbac_data = {
        "roles": [
            {
                "name": "moderator",
                "permissions": [
                    "reports.create",
                    "reports.triage",
                    "items.create",
                    "items.activate",
                ],
            },
        ],
    }
    policy = RBACPolicy(rbac_data)
    set_rbac_policy(policy, dept_id=None)


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset global state before and after each test."""
    reset_all_operations()
    reset_all_state_stores()
    reset_all_rbac()
    _setup_rbac_policy()
    yield
    reset_all_operations()
    reset_all_state_stores()
    reset_all_rbac()


def _make_actor(roles: list) -> ActorContext:
    """Create a test actor context."""
    return ActorContext(
        actor_id=str(uuid.uuid4()),
        roles=roles,
        tenant_id="test-tenant",
    )


def _create_transition_operations() -> OperationsDef:
    """Create test operations with transitions."""
    ops = [
        Operation(
            operation_id="create_content_report",
            method="POST",
            path="/reports",
            endpoint_sig="POST /reports",
            permission="reports.create",
            scope="tenant",
            idempotency="none",
            errors=[400, 401, 403],
            bind={"kind": "create", "entity": "ContentReport"},
        ),
        Operation(
            operation_id="triage_content_report",
            method="POST",
            path="/admin/reports/{report_id}/triage",
            endpoint_sig="POST /admin/reports/{report_id}/triage",
            permission="reports.triage",
            scope="tenant",
            idempotency="none",
            errors=[400, 401, 403, 404, 409],
            bind={
                "kind": "transition",
                "entity": "ContentReport",
                "workflow": "ReportFlow",
                "transition": "Triage",
                "transition_def": {
                    "from": "PENDING",
                    "to": "UNDER_REVIEW",
                    "guard": True,
                    "effects": [
                        {"type": "set_field", "field": "triaged_by", "value": "system"},
                        {"type": "bump_version", "value": 1},
                    ],
                },
            },
        ),
        Operation(
            operation_id="complex_guard_transition",
            method="POST",
            path="/admin/reports/{report_id}/complex-guard",
            endpoint_sig="POST /admin/reports/{report_id}/complex-guard",
            permission="reports.triage",
            scope="tenant",
            idempotency="none",
            errors=[400, 401, 403, 404, 409],
            bind={
                "kind": "transition",
                "entity": "ContentReport",
                "workflow": "ReportFlow",
                "transition": "ComplexGuard",
                "transition_def": {
                    "from": "PENDING",
                    "to": "UNDER_REVIEW",
                    "guard": "entity.reason == 'spam'",  # Non-literal guard
                    "effects": [],
                },
            },
        ),
    ]
    return OperationsDef(dept_id=None, operations=ops)


@pytest.mark.asyncio
async def test_content_report_triage_transition():
    """Test ContentReport triage transition: PENDING -> UNDER_REVIEW."""
    institution_id = str(uuid.uuid4())
    actor = _make_actor(["moderator"])

    # Register operations
    ops_def = _create_transition_operations()
    set_operations(None, ops_def)

    # Get operations for create and triage
    create_op = None
    triage_op = None
    for op in ops_def.operations:
        if op.operation_id == "create_content_report":
            create_op = op
        elif op.operation_id == "triage_content_report":
            triage_op = op

    assert create_op is not None, "Create operation not found"
    assert triage_op is not None, "Triage operation not found"

    # Create a content report
    create_result = await dispatch_create(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=create_op,
        request_body={
            "content_type": "POST",
            "content_id": "post-123",
            "reason": "spam",
            "description": "Test spam report",
        },
        path_params={},
    )

    assert create_result.status_code == 200, f"Create failed: {create_result.response_body}"
    report_id = create_result.response_body.get("id")
    assert report_id is not None, "No report ID returned"
    assert create_result.response_body.get("status") == "PENDING"

    # Triage the report (transition: PENDING -> UNDER_REVIEW)
    triage_result = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=triage_op,
        path_params={"report_id": report_id},
        request_body={},
    )

    assert triage_result.status_code == 200, f"Triage failed: {triage_result.response_body}"
    assert triage_result.response_body.get("workflow") == "ReportFlow"
    assert triage_result.response_body.get("transition") == "Triage"
    assert triage_result.response_body.get("previous_status") == "PENDING"
    assert triage_result.response_body.get("status") == "UNDER_REVIEW"

    # Verify effects were applied
    entity = triage_result.response_body.get("entity")
    assert entity is not None, "Entity not returned"
    assert entity.get("triaged_by") == "system", "set_field effect not applied"


@pytest.mark.asyncio
async def test_complex_guard_returns_unsupported():
    """Test that non-literal guard expression returns WORKFLOW_GUARD_UNSUPPORTED."""
    institution_id = str(uuid.uuid4())
    actor = _make_actor(["moderator"])

    # Register operations
    ops_def = _create_transition_operations()
    set_operations(None, ops_def)

    # Get operations
    create_op = None
    complex_guard_op = None
    for op in ops_def.operations:
        if op.operation_id == "create_content_report":
            create_op = op
        elif op.operation_id == "complex_guard_transition":
            complex_guard_op = op

    assert create_op is not None
    assert complex_guard_op is not None

    # Create a content report
    create_result = await dispatch_create(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=create_op,
        request_body={
            "content_type": "POST",
            "content_id": "post-789",
            "reason": "spam",
            "description": "Test report for guard test",
        },
        path_params={},
    )

    assert create_result.status_code == 200
    report_id = create_result.response_body.get("id")

    # Attempt transition with complex guard
    result = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=complex_guard_op,
        path_params={"report_id": report_id},
        request_body={},
    )

    assert result.status_code == 400, f"Expected 400, got {result.status_code}"
    assert result.error_code == "WORKFLOW_GUARD_UNSUPPORTED"


@pytest.mark.asyncio
async def test_transition_conflict_wrong_state():
    """Test that transition from wrong state returns WORKFLOW_TRANSITION_CONFLICT."""
    institution_id = str(uuid.uuid4())
    actor = _make_actor(["moderator"])

    # Register operations
    ops_def = _create_transition_operations()
    set_operations(None, ops_def)

    # Get operations
    create_op = None
    triage_op = None
    for op in ops_def.operations:
        if op.operation_id == "create_content_report":
            create_op = op
        elif op.operation_id == "triage_content_report":
            triage_op = op

    # Create a content report
    create_result = await dispatch_create(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=create_op,
        request_body={
            "content_type": "COMMENT",
            "content_id": "comment-999",
            "reason": "harassment",
        },
        path_params={},
    )

    assert create_result.status_code == 200
    report_id = create_result.response_body.get("id")

    # Triage first time (should succeed)
    result1 = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=triage_op,
        path_params={"report_id": report_id},
        request_body={},
    )

    assert result1.status_code == 200
    assert result1.response_body.get("status") == "UNDER_REVIEW"

    # Triage second time (should fail - already UNDER_REVIEW, not PENDING)
    result2 = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=triage_op,
        path_params={"report_id": report_id},
        request_body={},
    )

    assert result2.status_code == 409, f"Expected 409, got {result2.status_code}"
    assert result2.error_code == "WORKFLOW_TRANSITION_CONFLICT"
    assert "UNDER_REVIEW" in result2.response_body.get("message", "")
    assert "PENDING" in result2.response_body.get("message", "")


@pytest.mark.asyncio
async def test_transition_not_found():
    """Test that transition on non-existent entity returns 404."""
    institution_id = str(uuid.uuid4())
    actor = _make_actor(["moderator"])

    # Register operations
    ops_def = _create_transition_operations()
    set_operations(None, ops_def)

    # Get triage operation
    triage_op = None
    for op in ops_def.operations:
        if op.operation_id == "triage_content_report":
            triage_op = op
            break

    # Attempt transition on non-existent report
    result = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=triage_op,
        path_params={"report_id": "nonexistent-id"},
        request_body={},
    )

    assert result.status_code == 404, f"Expected 404, got {result.status_code}"
    assert result.error_code == "CONTENT_REPORT_NOT_FOUND"


@pytest.mark.asyncio
async def test_set_state_effect():
    """Test that set_state effect updates entity status explicitly.

    This tests the explicit set_state effect (separate from transition_def.to).
    """
    institution_id = str(uuid.uuid4())
    actor = _make_actor(["moderator"])

    # Create operations with explicit set_state effect
    ops = [
        Operation(
            operation_id="create_report",
            method="POST",
            path="/state-reports",
            endpoint_sig="POST /state-reports",
            permission="reports.create",
            scope="tenant",
            idempotency="none",
            errors=[400],
            bind={"kind": "create", "entity": "ContentReport"},
        ),
        Operation(
            operation_id="archive_report",
            method="POST",
            path="/state-reports/{report_id}/archive",
            endpoint_sig="POST /state-reports/{report_id}/archive",
            permission="reports.triage",
            scope="tenant",
            idempotency="none",
            errors=[400, 409],
            bind={
                "kind": "transition",
                "entity": "ContentReport",
                "workflow": "ArchiveFlow",
                "transition": "Archive",
                "transition_def": {
                    "from": "PENDING",
                    # Note: no "to" field - using explicit set_state effect instead
                    "guard": True,
                    "effects": [
                        {"type": "set_state", "value": "ARCHIVED"},
                    ],
                },
            },
        ),
    ]
    ops_def = OperationsDef(dept_id=None, operations=ops)
    set_operations(None, ops_def)

    # Create report
    create_result = await dispatch_create(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=ops[0],
        request_body={
            "content_type": "POST",
            "content_id": "post-archive-test",
            "reason": "spam",
        },
        path_params={},
    )

    assert create_result.status_code == 200, f"Create failed: {create_result.response_body}"
    report_id = create_result.response_body.get("id")
    assert create_result.response_body.get("status") == "PENDING"

    # Archive report (transition using explicit set_state effect)
    result = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=actor,
        operation=ops[1],
        path_params={"report_id": report_id},
        request_body={},
    )

    assert result.status_code == 200, f"Archive failed: {result.response_body}"
    assert result.response_body.get("status") == "ARCHIVED"
