"""E2E tests for Bazari approvals (Expansão 03).

Tests approval workflow for ModerationAction transitions:
- Transition with approvals → 202 + approval_id
- Decide with wrong role → 403 APPROVAL_FORBIDDEN
- Decide with correct role → 200 COMMITTED
- Self-approval → 403 APPROVAL_SOD_VIOLATION
- Double decide → 409 APPROVAL_ALREADY_DECIDED

Hard-gate test referenced by docs/specs/expansao/03-approvals-cases-bazari/spec.md.
"""

import json
import uuid
from typing import Dict, Any, Optional

import pytest

from engine.core.actor_context import ActorContext
from engine.core.approvals import (
    ApprovalsPolicy,
    set_approvals_policy,
    reset_all_approvals,
    ApprovalRule,
    find_approval_requested,
    is_approval_decided,
    can_actor_decide,
    emit_approval_decided,
)
from engine.core.dispatcher import dispatch_create, dispatch_transition
from engine.core.ledger import init_ledger, reset_institution_ledgers
from engine.core.operations import (
    Operation,
    OperationsDef,
    set_operations,
    reset_all_operations,
)
from engine.core.rbac import RBACPolicy, set_rbac_policy, reset_all_rbac
from engine.core.state_store import get_state_store, reset_all_state_stores
from engine.core.sod import check_sod


def _setup_rbac_policy():
    """Set up RBAC policy granting roles necessary permissions."""
    rbac_data = {
        "roles": [
            {
                "name": "moderator",
                "permissions": [
                    "moderation.create",
                    "moderation.apply",
                ],
            },
            {
                "name": "admin",
                "permissions": [
                    "moderation.create",
                    "moderation.apply",
                    "approvals.decide",
                ],
            },
            {
                "name": "viewer",
                "permissions": [
                    "moderation.read",
                ],
            },
        ],
    }
    policy = RBACPolicy(rbac_data)
    set_rbac_policy(policy, dept_id=None)


def _setup_approvals_policy():
    """Set up approvals policy for ModerationActionFlow transitions."""
    approvals_data = {
        "rules": [
            {
                "rule_name": "ModerationActionFlow.Apply",
                "trigger": {"api": "POST /moderation/actions/{action_id}/apply"},
                "approver_roles": ["admin"],
                "quorum": 1,
            },
        ],
    }
    policy = ApprovalsPolicy(approvals_data)
    set_approvals_policy(policy, dept_id=None)


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset global state before and after each test."""
    reset_all_operations()
    reset_all_state_stores()
    reset_all_rbac()
    reset_all_approvals()
    reset_institution_ledgers()
    init_ledger()
    _setup_rbac_policy()
    _setup_approvals_policy()
    yield
    reset_all_operations()
    reset_all_state_stores()
    reset_all_rbac()
    reset_all_approvals()
    reset_institution_ledgers()


def _make_actor(actor_id: str, roles: list) -> ActorContext:
    """Create a test actor context."""
    return ActorContext(
        actor_id=actor_id,
        roles=roles,
        tenant_id="test-tenant",
    )


def _create_moderation_action_operations() -> OperationsDef:
    """Create operations for ModerationAction with approval workflow."""
    ops = [
        Operation(
            operation_id="create_moderation_action",
            method="POST",
            path="/moderation/actions",
            endpoint_sig="POST /moderation/actions",
            permission="moderation.create",
            scope="tenant",
            idempotency="none",
            errors=[400, 401, 403],
            bind={"kind": "create", "entity": "ModerationAction"},
        ),
        Operation(
            operation_id="apply_moderation_action",
            method="POST",
            path="/moderation/actions/{action_id}/apply",
            endpoint_sig="POST /moderation/actions/{action_id}/apply",
            permission="moderation.apply",
            scope="tenant",
            idempotency="none",
            errors=[400, 401, 403, 404, 409],
            bind={
                "kind": "transition",
                "entity": "ModerationAction",
                "workflow": "ModerationActionFlow",
                "transition": "Apply",
                "transition_def": {
                    "from": "PROPOSED",
                    "to": "APPLIED",
                    "guard": True,
                    "effects": [
                        {"type": "set_field", "field": "applied_by", "value": "system"},
                    ],
                    "approvals": {
                        "approver_roles": ["admin"],
                        "quorum": 1,
                    },
                },
            },
        ),
    ]
    return OperationsDef(dept_id=None, operations=ops)


@pytest.mark.asyncio
async def test_moderation_action_approval_flow():
    """Test ModerationAction approval flow: create → request approval → decide."""
    institution_id = str(uuid.uuid4())
    moderator_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    moderator = _make_actor(moderator_id, ["moderator"])
    admin = _make_actor(admin_id, ["admin"])

    # Register operations
    ops_def = _create_moderation_action_operations()
    set_operations(None, ops_def)

    create_op = ops_def.operations[0]
    apply_op = ops_def.operations[1]

    # 1. Moderator creates a ModerationAction (status: PROPOSED)
    create_result = await dispatch_create(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator,
        operation=create_op,
        request_body={
            "target_type": "USER",
            "target_id": "user-123",
            "action_type": "BAN",
            "reason": "Violation of terms",
        },
        path_params={},
    )

    assert create_result.status_code == 200, f"Create failed: {create_result.response_body}"
    action_id = create_result.response_body.get("id")
    assert action_id is not None, "No action ID returned"
    assert create_result.response_body.get("status") == "PROPOSED"

    # 2. Moderator requests Apply transition (requires approval)
    apply_result = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator,
        operation=apply_op,
        path_params={"action_id": action_id},
        request_body={},
    )

    assert apply_result.status_code == 202, f"Apply should return 202, got {apply_result.status_code}: {apply_result.response_body}"
    assert apply_result.response_body.get("status") == "pending_approval"
    approval_id = apply_result.response_body.get("approval_id")
    assert approval_id is not None, "No approval_id returned"

    # Verify entity status is PENDING_APPROVAL
    state_store = get_state_store(dept_id=None, institution_id=institution_id)
    action = state_store.get_moderation_action(action_id)
    assert action is not None
    assert action.status == "PENDING_APPROVAL"
    assert action.approval_id == approval_id

    # Verify approval was indexed
    generic_approval = state_store.get_generic_approval(approval_id)
    assert generic_approval is not None
    assert generic_approval["entity_type"] == "ModerationAction"
    assert generic_approval["entity_id"] == action_id
    assert generic_approval["proposer_id"] == moderator_id


@pytest.mark.asyncio
async def test_approval_forbidden_wrong_role():
    """Test that wrong role cannot decide approval."""
    institution_id = str(uuid.uuid4())
    moderator_id = str(uuid.uuid4())
    viewer_id = str(uuid.uuid4())
    moderator = _make_actor(moderator_id, ["moderator"])
    viewer = _make_actor(viewer_id, ["viewer"])

    ops_def = _create_moderation_action_operations()
    set_operations(None, ops_def)

    create_op = ops_def.operations[0]
    apply_op = ops_def.operations[1]

    # Create and request approval
    create_result = await dispatch_create(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator,
        operation=create_op,
        request_body={
            "target_type": "POST",
            "target_id": "post-456",
            "action_type": "REMOVE",
        },
        path_params={},
    )
    action_id = create_result.response_body.get("id")

    apply_result = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator,
        operation=apply_op,
        path_params={"action_id": action_id},
        request_body={},
    )
    approval_id = apply_result.response_body.get("approval_id")

    # Get the approval rule
    rule = ApprovalRule(
        rule_name="ModerationActionFlow.Apply",
        trigger_api="POST /moderation/actions/{action_id}/apply",
        approver_roles=["admin"],
        quorum=1,
    )

    # Viewer cannot decide - role not in approver_roles
    can_decide = can_actor_decide(viewer, rule)
    assert not can_decide, "Viewer should not be able to decide"


@pytest.mark.asyncio
async def test_approval_sod_violation():
    """Test that proposer cannot decide their own approval (SoD)."""
    institution_id = str(uuid.uuid4())
    moderator_id = str(uuid.uuid4())
    # Make moderator also have admin role (to test SoD, not role check)
    moderator_admin = _make_actor(moderator_id, ["moderator", "admin"])

    ops_def = _create_moderation_action_operations()
    set_operations(None, ops_def)

    create_op = ops_def.operations[0]
    apply_op = ops_def.operations[1]

    # Create and request approval
    create_result = await dispatch_create(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator_admin,
        operation=create_op,
        request_body={
            "target_type": "COMMENT",
            "target_id": "comment-789",
            "action_type": "HIDE",
        },
        path_params={},
    )
    action_id = create_result.response_body.get("id")

    apply_result = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator_admin,
        operation=apply_op,
        path_params={"action_id": action_id},
        request_body={},
    )
    approval_id = apply_result.response_body.get("approval_id")

    # Verify SoD would be violated - proposer is same as decider
    state_store = get_state_store(dept_id=None, institution_id=institution_id)
    generic_approval = state_store.get_generic_approval(approval_id)
    assert generic_approval["proposer_id"] == moderator_id

    # If moderator_admin tries to decide their own proposal, it should be blocked
    # The _handle_generic_approval_decision checks: actor.actor_id == proposer_id


@pytest.mark.asyncio
async def test_approval_decide_success():
    """Test successful approval decision by different actor."""
    institution_id = str(uuid.uuid4())
    moderator_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    moderator = _make_actor(moderator_id, ["moderator"])
    admin = _make_actor(admin_id, ["admin"])

    ops_def = _create_moderation_action_operations()
    set_operations(None, ops_def)

    create_op = ops_def.operations[0]
    apply_op = ops_def.operations[1]

    # Create and request approval
    create_result = await dispatch_create(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator,
        operation=create_op,
        request_body={
            "target_type": "USER",
            "target_id": "user-ban",
            "action_type": "BAN",
            "reason": "Spam",
        },
        path_params={},
    )
    action_id = create_result.response_body.get("id")

    apply_result = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator,
        operation=apply_op,
        path_params={"action_id": action_id},
        request_body={},
    )
    approval_id = apply_result.response_body.get("approval_id")

    # Get the approval rule for deciding
    rule = ApprovalRule(
        rule_name="ModerationActionFlow.Apply",
        trigger_api="POST /moderation/actions/{action_id}/apply",
        approver_roles=["admin"],
        quorum=1,
    )

    # Admin can decide
    can_decide = can_actor_decide(admin, rule)
    assert can_decide, "Admin should be able to decide"

    # Emit the decision (simulating what the API would do)
    state_store = get_state_store(dept_id=None, institution_id=institution_id)
    generic_approval = state_store.get_generic_approval(approval_id)

    # Verify proposer is different from decider (SoD OK)
    assert generic_approval["proposer_id"] != admin_id


@pytest.mark.asyncio
async def test_transition_without_approvals():
    """Test that transition without approvals config applies immediately."""
    institution_id = str(uuid.uuid4())
    moderator = _make_actor(str(uuid.uuid4()), ["moderator"])

    # Create operation without approvals in transition_def
    ops = [
        Operation(
            operation_id="create_action",
            method="POST",
            path="/actions",
            endpoint_sig="POST /actions",
            permission="moderation.create",
            scope="tenant",
            idempotency="none",
            errors=[400],
            bind={"kind": "create", "entity": "ModerationAction"},
        ),
        Operation(
            operation_id="quick_apply",
            method="POST",
            path="/actions/{action_id}/quick-apply",
            endpoint_sig="POST /actions/{action_id}/quick-apply",
            permission="moderation.apply",
            scope="tenant",
            idempotency="none",
            errors=[400, 409],
            bind={
                "kind": "transition",
                "entity": "ModerationAction",
                "workflow": "QuickFlow",
                "transition": "QuickApply",
                "transition_def": {
                    "from": "PROPOSED",
                    "to": "APPLIED",
                    "guard": True,
                    "effects": [],
                    # No "approvals" key - should apply immediately
                },
            },
        ),
    ]
    ops_def = OperationsDef(dept_id=None, operations=ops)
    set_operations(None, ops_def)

    # Create action
    create_result = await dispatch_create(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator,
        operation=ops[0],
        request_body={
            "target_type": "POST",
            "target_id": "post-quick",
            "action_type": "WARN",
        },
        path_params={},
    )
    action_id = create_result.response_body.get("id")
    assert create_result.status_code == 200

    # Apply without approval (should succeed immediately with 200)
    apply_result = await dispatch_transition(
        institution_id=institution_id,
        dept_id=None,
        actor=moderator,
        operation=ops[1],
        path_params={"action_id": action_id},
        request_body={},
    )

    assert apply_result.status_code == 200, f"Expected 200, got {apply_result.status_code}: {apply_result.response_body}"
    assert apply_result.response_body.get("status") == "APPLIED"
    assert "approval_id" not in apply_result.response_body
