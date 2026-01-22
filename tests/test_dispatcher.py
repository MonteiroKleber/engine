"""Tests for Dispatcher v2 - Generic operation execution.

Tests:
1. dispatch_create - Expense via finance-pilot
2. dispatch_create - Ticket via support
3. dispatch_read - Expense (found and 404)
4. dispatch_read - Ticket (found and 404)
5. RBAC gate enforcement
6. Policy gate enforcement
7. Mandates gate enforcement
8. Autonomy gate enforcement
9. Multi-tenant isolation (2 institutions x 2 depts)
10. dispatch_approval_request - create with approval pending
11. dispatch_approval_decide - approve/reject with SoD
12. Full approval flow: create → pending → decide
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.core.dispatcher import (
    dispatch_create,
    dispatch_read,
    dispatch_approval_request,
    dispatch_approval_decide,
    DispatchResult,
)
from engine.core.operations import (
    Operation,
    OperationsDef,
    set_operations,
    reset_all_operations,
)
from engine.core.actor_context import ActorContext
from engine.core.rbac import RBACPolicy, set_rbac_policy, reset_all_rbac
from engine.core.policy import PolicyDef, PolicyRule, set_policies, clear_all_policies
from engine.core.mandates import MandateDef, Mandate, set_mandates, clear_all_mandates
from engine.core.governed_mandates import invalidate_all_mandates_cache
from engine.core.governed_autonomy import invalidate_all_autonomy_cache
from engine.core.governed_policies import invalidate_all_policies_cache
from engine.core.autonomy import AutonomyDef, AutonomyRule, set_autonomy_for_dept, reset_all_autonomy
from engine.core.state_store import StateStore, set_state_store, reset_all_state_stores
from engine.core.ledger import AuditLedger, set_ledger, reset_institution_ledgers
from engine.core.errors import (
    POLICY_DENIED,
    MANDATE_DENIED,
    AUTONOMY_INSUFFICIENT,
    EXPENSE_NOT_FOUND,
    TICKET_NOT_FOUND,
    SOD_VIOLATION,
    INVARIANT_VIOLATION,
)
from engine.core.approvals import (
    ApprovalsPolicy,
    set_approvals_policy,
    reset_all_approvals,
)
from engine.core.sod import (
    SodPolicy,
    set_sod_policy,
    reset_all_sod,
)
from engine.core.invariants import (
    InvariantsPolicy,
    set_invariants_policy,
    reset_all_invariants,
)
from engine.core.state_store import STATUS_PENDING_APPROVAL, STATUS_COMMITTED, STATUS_REJECTED


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def clean_all():
    """Clean all global state before and after each test."""
    reset_all_operations()
    reset_all_rbac()
    clear_all_policies()
    invalidate_all_policies_cache()
    clear_all_mandates()
    invalidate_all_mandates_cache()
    reset_all_autonomy()
    invalidate_all_autonomy_cache()
    reset_all_state_stores()
    reset_institution_ledgers()
    reset_all_approvals()
    reset_all_sod()
    reset_all_invariants()
    yield
    reset_all_operations()
    reset_all_rbac()
    clear_all_policies()
    invalidate_all_policies_cache()
    clear_all_mandates()
    invalidate_all_mandates_cache()
    reset_all_autonomy()
    invalidate_all_autonomy_cache()
    reset_all_state_stores()
    reset_institution_ledgers()
    reset_all_approvals()
    reset_all_sod()
    reset_all_invariants()


@pytest.fixture
def temp_dir():
    """Temporary directory for state stores."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def expense_create_operation():
    """Operation for expense create."""
    return Operation(
        operation_id="expense_create",
        method="POST",
        path="/finance/expenses",
        endpoint_sig="POST /finance/expenses",
        permission="expense.create",
        scope="tenant",
        idempotency="required",
        errors=[400, 401, 403],
        bind={"kind": "create", "entity": "Expense"},
    )


@pytest.fixture
def expense_read_operation():
    """Operation for expense read."""
    return Operation(
        operation_id="expense_get",
        method="GET",
        path="/finance/expenses/{expense_id}",
        endpoint_sig="GET /finance/expenses/{expense_id}",
        permission="expense.read",
        scope="tenant",
        bind={"kind": "read", "entity": "Expense"},
    )


@pytest.fixture
def ticket_create_operation():
    """Operation for ticket create."""
    return Operation(
        operation_id="ticket_create",
        method="POST",
        path="/support/tickets",
        endpoint_sig="POST /support/tickets",
        permission="ticket.create",
        scope="tenant",
        bind={"kind": "create", "entity": "Ticket"},
    )


@pytest.fixture
def ticket_read_operation():
    """Operation for ticket read."""
    return Operation(
        operation_id="ticket_get",
        method="GET",
        path="/support/tickets/{ticket_id}",
        endpoint_sig="GET /support/tickets/{ticket_id}",
        permission="ticket.read",
        scope="tenant",
        bind={"kind": "read", "entity": "Ticket"},
    )


@pytest.fixture
def actor_with_expense_perms():
    """Actor with expense permissions."""
    return ActorContext(
        tenant_id="test-tenant",
        actor_id="user-001",
        roles=["finance_user"],
    )


@pytest.fixture
def actor_with_ticket_perms():
    """Actor with ticket permissions."""
    return ActorContext(
        tenant_id="test-tenant",
        actor_id="user-002",
        roles=["support_user"],
    )


@pytest.fixture
def actor_without_perms():
    """Actor without any permissions."""
    return ActorContext(
        tenant_id="test-tenant",
        actor_id="user-003",
        roles=["guest"],
    )


@pytest.fixture
def rbac_finance():
    """RBAC policy for finance operations."""
    return RBACPolicy({
        "roles": [
            {
                "name": "finance_user",
                "permissions": ["expense.create", "expense.read"],
            },
        ],
    })


@pytest.fixture
def rbac_support():
    """RBAC policy for support operations."""
    return RBACPolicy({
        "roles": [
            {
                "name": "support_user",
                "permissions": ["ticket.create", "ticket.read"],
            },
        ],
    })


def setup_state_store(temp_dir: Path, institution_id: str, dept_id: str = None):
    """Setup a state store for testing."""
    store_path = temp_dir / f"state_{institution_id}_{dept_id or 'single'}.json"
    store = StateStore(path=store_path)
    set_state_store(store, dept_id=dept_id, institution_id=institution_id)
    return store


# =============================================================================
# Basic Create Tests
# =============================================================================

class TestDispatchCreateExpense:
    """Test dispatch_create for Expense entity."""

    @pytest.mark.asyncio
    async def test_create_expense_success(
        self,
        temp_dir,
        expense_create_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Successful expense creation via dispatcher."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_finance, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        # Execute
        result = await dispatch_create(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_create_operation,
            request_body={"amount": 100, "description": "Test expense"},
        )

        # Assert
        assert result.status_code == 200
        assert "id" in result.response_body
        assert result.response_body["status"] == "PENDING_APPROVAL"
        assert "approval_id" in result.response_body
        assert result.response_body["actor_id"] == "user-001"
        assert result.error_code is None

    @pytest.mark.asyncio
    async def test_create_expense_rbac_denied(
        self,
        temp_dir,
        expense_create_operation,
        actor_without_perms,
        rbac_finance,
    ):
        """Expense creation denied by RBAC."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_finance, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        # Execute
        result = await dispatch_create(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_without_perms,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )

        # Assert
        assert result.status_code == 403
        assert result.error_code == "RBAC_DENIED"


class TestDispatchCreateTicket:
    """Test dispatch_create for Ticket entity."""

    @pytest.mark.asyncio
    async def test_create_ticket_success(
        self,
        temp_dir,
        ticket_create_operation,
        actor_with_ticket_perms,
        rbac_support,
    ):
        """Successful ticket creation via dispatcher."""
        institution_id = "inst-001"
        dept_id = "support"

        # Setup
        set_rbac_policy(rbac_support, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        # Execute
        result = await dispatch_create(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_ticket_perms,
            operation=ticket_create_operation,
            request_body={"subject": "Help needed", "description": "Test ticket"},
        )

        # Assert
        assert result.status_code == 200
        assert "id" in result.response_body
        assert result.response_body["status"] == "OPEN"
        assert result.response_body["subject"] == "Help needed"
        assert result.response_body["actor_id"] == "user-002"


# =============================================================================
# Read Tests
# =============================================================================

class TestDispatchReadExpense:
    """Test dispatch_read for Expense entity."""

    @pytest.mark.asyncio
    async def test_read_expense_success(
        self,
        temp_dir,
        expense_create_operation,
        expense_read_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Successful expense read via dispatcher."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_finance, dept_id=dept_id)
        store = setup_state_store(temp_dir, institution_id, dept_id)

        # Create expense first
        create_result = await dispatch_create(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        assert create_result.status_code == 200
        expense_id = create_result.response_body["id"]

        # Read expense
        read_result = await dispatch_read(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_read_operation,
            path_params={"expense_id": expense_id},
        )

        # Assert
        assert read_result.status_code == 200
        assert read_result.response_body["id"] == expense_id
        assert read_result.response_body["status"] == "PENDING_APPROVAL"

    @pytest.mark.asyncio
    async def test_read_expense_not_found(
        self,
        temp_dir,
        expense_read_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Expense read returns 404 when not found."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_finance, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        # Read non-existent expense
        result = await dispatch_read(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_read_operation,
            path_params={"expense_id": "non-existent-id"},
        )

        # Assert
        assert result.status_code == 404
        assert result.error_code == EXPENSE_NOT_FOUND


class TestDispatchReadTicket:
    """Test dispatch_read for Ticket entity."""

    @pytest.mark.asyncio
    async def test_read_ticket_not_found(
        self,
        temp_dir,
        ticket_read_operation,
        actor_with_ticket_perms,
        rbac_support,
    ):
        """Ticket read returns 404 when not found."""
        institution_id = "inst-001"
        dept_id = "support"

        # Setup
        set_rbac_policy(rbac_support, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        # Read non-existent ticket
        result = await dispatch_read(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_ticket_perms,
            operation=ticket_read_operation,
            path_params={"ticket_id": "non-existent-id"},
        )

        # Assert
        assert result.status_code == 404
        assert result.error_code == TICKET_NOT_FOUND


# =============================================================================
# Gate Enforcement Tests
# =============================================================================

class TestPolicyGateEnforcement:
    """Test Policy gate enforcement in dispatcher."""

    @pytest.mark.asyncio
    async def test_policy_denies_over_limit(
        self,
        temp_dir,
        expense_create_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Policy gate denies request over limit."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup RBAC
        set_rbac_policy(rbac_finance, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        # Setup Policy with max limit
        policy_def = PolicyDef(policies=[
            PolicyRule(
                policy_id="max_amount",
                rule_type="numeric_max",
                field_path="amount",
                field_path_tokens=["amount"],
                phase="pre",
                endpoint_sig="POST /finance/expenses",
                value=500,
                message="Amount exceeds maximum 500",
            ),
        ])
        set_policies(dept_id, policy_def)

        # Execute with amount over limit
        result = await dispatch_create(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_create_operation,
            request_body={"amount": 1000},  # Over limit
        )

        # Assert
        assert result.status_code == 403
        assert result.error_code == POLICY_DENIED


class TestMandatesGateEnforcement:
    """Test Mandates gate enforcement in dispatcher."""

    @pytest.mark.asyncio
    async def test_mandates_denies_no_matching_mandate(
        self,
        temp_dir,
        expense_create_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Mandates gate denies when no mandate matches."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup RBAC
        set_rbac_policy(rbac_finance, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        # Setup Mandates with different endpoint
        mandate_def = MandateDef(mandates=[
            Mandate(
                mandate_id="other_mandate",
                endpoint_sig="POST /other/endpoint",  # Different endpoint
                phase="pre",
                allowed_roles=["finance_user"],
            ),
        ])
        set_mandates(dept_id, mandate_def)

        # Execute - no mandate matches our endpoint
        result = await dispatch_create(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )

        # Assert
        assert result.status_code == 403
        assert result.error_code == MANDATE_DENIED


class TestAutonomyGateEnforcement:
    """Test Autonomy gate enforcement in dispatcher."""

    @pytest.mark.asyncio
    async def test_autonomy_denies_insufficient_level(
        self,
        temp_dir,
        expense_create_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Autonomy gate denies when level is insufficient."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup RBAC
        set_rbac_policy(rbac_finance, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        # Setup Mandate that allows (so we reach autonomy gate)
        mandate_def = MandateDef(mandates=[
            Mandate(
                mandate_id="expense_mandate",
                endpoint_sig="POST /finance/expenses",
                phase="pre",
                allowed_roles=["finance_user"],
            ),
        ])
        set_mandates(dept_id, mandate_def)

        # Setup Autonomy with low current level
        autonomy_def = AutonomyDef(
            current_level=1,  # Low level
            rules=[
                AutonomyRule(
                    rule_id="expense_rule",
                    endpoint_sig="POST /finance/expenses",
                    phase="pre",
                    required_level=3,  # Requires level 3
                ),
            ],
        )
        set_autonomy_for_dept(dept_id, autonomy_def)

        # Execute
        result = await dispatch_create(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )

        # Assert
        assert result.status_code == 403
        assert result.error_code == AUTONOMY_INSUFFICIENT


# =============================================================================
# Multi-Tenant Isolation Tests
# =============================================================================

class TestMultiTenantIsolation:
    """Test isolation between institutions and departments."""

    @pytest.mark.asyncio
    async def test_isolation_between_institutions(
        self,
        temp_dir,
        expense_create_operation,
        expense_read_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Expenses are isolated between institutions."""
        dept_id = "finance"
        inst_a = "institution-A"
        inst_b = "institution-B"

        # Setup both institutions
        set_rbac_policy(rbac_finance, dept_id=dept_id)
        setup_state_store(temp_dir, inst_a, dept_id)
        setup_state_store(temp_dir, inst_b, dept_id)

        # Create expense in institution A
        create_result = await dispatch_create(
            institution_id=inst_a,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        assert create_result.status_code == 200
        expense_id = create_result.response_body["id"]

        # Try to read from institution B - should not find it
        read_result = await dispatch_read(
            institution_id=inst_b,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_read_operation,
            path_params={"expense_id": expense_id},
        )

        # Assert - expense not visible in institution B
        assert read_result.status_code == 404
        assert read_result.error_code == EXPENSE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_isolation_between_departments(
        self,
        temp_dir,
        expense_create_operation,
        expense_read_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Expenses are isolated between departments."""
        institution_id = "inst-001"
        dept_finance = "finance"
        dept_hr = "hr"

        # Setup both departments with RBAC
        set_rbac_policy(rbac_finance, dept_id=dept_finance)
        set_rbac_policy(rbac_finance, dept_id=dept_hr)  # Same policy for test
        setup_state_store(temp_dir, institution_id, dept_finance)
        setup_state_store(temp_dir, institution_id, dept_hr)

        # Create expense in finance dept
        create_result = await dispatch_create(
            institution_id=institution_id,
            dept_id=dept_finance,
            actor=actor_with_expense_perms,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        assert create_result.status_code == 200
        expense_id = create_result.response_body["id"]

        # Try to read from HR dept - should not find it
        read_result = await dispatch_read(
            institution_id=institution_id,
            dept_id=dept_hr,
            actor=actor_with_expense_perms,
            operation=expense_read_operation,
            path_params={"expense_id": expense_id},
        )

        # Assert - expense not visible in HR dept
        assert read_result.status_code == 404
        assert read_result.error_code == EXPENSE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_full_isolation_matrix(
        self,
        temp_dir,
        expense_create_operation,
        expense_read_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Full isolation test: 2 institutions x 2 departments."""
        institutions = ["inst-A", "inst-B"]
        departments = ["finance", "support"]

        # Setup all combinations
        for inst in institutions:
            for dept in departments:
                set_rbac_policy(rbac_finance, dept_id=dept)
                setup_state_store(temp_dir, inst, dept)

        # Create expense in inst-A/finance
        create_result = await dispatch_create(
            institution_id="inst-A",
            dept_id="finance",
            actor=actor_with_expense_perms,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        assert create_result.status_code == 200
        expense_id = create_result.response_body["id"]

        # Verify expense is ONLY visible in inst-A/finance
        test_cases = [
            ("inst-A", "finance", 200),    # Should find
            ("inst-A", "support", 404),    # Different dept
            ("inst-B", "finance", 404),    # Different inst
            ("inst-B", "support", 404),    # Different inst and dept
        ]

        for inst, dept, expected_status in test_cases:
            read_result = await dispatch_read(
                institution_id=inst,
                dept_id=dept,
                actor=actor_with_expense_perms,
                operation=expense_read_operation,
                path_params={"expense_id": expense_id},
            )
            assert read_result.status_code == expected_status, \
                f"Expected {expected_status} for {inst}/{dept}, got {read_result.status_code}"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_unsupported_entity_type(
        self,
        temp_dir,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Dispatcher returns error for unsupported entity type."""
        institution_id = "inst-001"
        dept_id = "finance"

        set_rbac_policy(rbac_finance, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        # Create operation with unsupported entity
        operation = Operation(
            operation_id="unknown_create",
            method="POST",
            path="/unknown/entities",
            endpoint_sig="POST /unknown/entities",
            permission="unknown.create",
            bind={"kind": "create", "entity": "Unknown"},
        )

        result = await dispatch_create(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=operation,
            request_body={},
        )

        assert result.status_code == 500
        assert result.error_code == "ENTITY_TYPE_UNSUPPORTED"

    @pytest.mark.asyncio
    async def test_missing_path_param_for_read(
        self,
        temp_dir,
        expense_read_operation,
        actor_with_expense_perms,
        rbac_finance,
    ):
        """Read operation fails when path param is missing."""
        institution_id = "inst-001"
        dept_id = "finance"

        set_rbac_policy(rbac_finance, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)

        result = await dispatch_read(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_with_expense_perms,
            operation=expense_read_operation,
            path_params={},  # Missing expense_id
        )

        assert result.status_code == 400
        assert result.error_code == "PATH_PARAM_MISSING"


# =============================================================================
# Dispatcher v2: Approvals Tests
# =============================================================================


@pytest.fixture
def approvals_policy():
    """Approvals policy with expense.create rule."""
    return ApprovalsPolicy({
        "version": "1.0.0",
        "rules": [
            {
                "rule_name": "expense.create",
                "trigger": {"api": "POST /finance/expenses"},
                "approver_roles": ["manager"],
                "quorum": 1,
            }
        ],
    })


@pytest.fixture
def sod_policy():
    """SoD policy with requester != decider rule."""
    return SodPolicy({
        "version": "1.0.0",
        "rules": [
            {
                "rule_name": "expense.create.requester_not_approver",
                "case_step": "APPROVAL:expense.create",
                "constraint": "REQUESTER_NEQ_DECIDER",
            }
        ],
    })


@pytest.fixture
def invariants_policy():
    """Invariants policy for expense validation."""
    return InvariantsPolicy({
        "version": "1.0.0",
        "expense": {
            "amount": {"min": 0.01, "max": 1000000},
            "description": {"max_len": 280, "required": False},
        },
    })


@pytest.fixture
def actor_analyst():
    """Actor with analyst role (can create expense)."""
    return ActorContext(
        tenant_id="test-tenant",
        actor_id="analyst-001",
        roles=["analyst"],
    )


@pytest.fixture
def actor_manager():
    """Actor with manager role (can approve expense)."""
    return ActorContext(
        tenant_id="test-tenant",
        actor_id="manager-001",
        roles=["manager"],
    )


@pytest.fixture
def rbac_with_approvals():
    """RBAC policy with analyst and manager roles."""
    return RBACPolicy({
        "roles": [
            {
                "name": "analyst",
                "permissions": ["expense.create", "expense.read"],
            },
            {
                "name": "manager",
                "permissions": ["expense.create", "expense.read", "expense.approve"],
            },
        ],
    })


def setup_ledger_for_test(temp_dir: Path, institution_id: str = None):
    """Setup ledger for testing."""
    ledger_path = temp_dir / f"ledger_{institution_id or 'single'}.jsonl"
    ledger = AuditLedger(ledger_path=ledger_path)
    set_ledger(ledger)
    return ledger


class TestDispatchApprovalRequest:
    """Test dispatch_approval_request function."""

    @pytest.mark.asyncio
    async def test_create_with_approval_returns_202(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        rbac_with_approvals,
        approvals_policy,
    ):
        """Create expense with approval rule returns 202 pending_approval."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Execute
        result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100, "description": "Test expense"},
        )

        # Assert
        assert result.status_code == 202
        assert result.response_body["status"] == "pending_approval"
        assert "expense_id" in result.response_body
        assert "approval_id" in result.response_body
        assert "APPROVAL:expense.create" in result.response_body["step"]

    @pytest.mark.asyncio
    async def test_create_without_approval_returns_200(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        rbac_with_approvals,
    ):
        """Create expense without approval rule returns 200."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup - no approvals policy
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Execute
        result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )

        # Assert
        assert result.status_code == 200
        assert "id" in result.response_body
        assert result.response_body["status"] == STATUS_PENDING_APPROVAL


class TestDispatchApprovalDecide:
    """Test dispatch_approval_decide function."""

    @pytest.mark.asyncio
    async def test_manager_approve_returns_committed(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
        sod_policy,
        invariants_policy,
    ):
        """Manager can approve expense and status becomes COMMITTED."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        set_sod_policy(sod_policy, dept_id=dept_id)
        set_invariants_policy(invariants_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Create expense (as analyst)
        create_result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100, "description": "Test expense"},
        )
        assert create_result.status_code == 202
        approval_id = create_result.response_body["approval_id"]

        # Approve (as manager)
        decide_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id=approval_id,
            decision="approve",
            reason="Approved for Q1 budget",
        )

        # Assert
        assert decide_result.status_code == 200
        assert decide_result.response_body["status"] == "decided"
        assert decide_result.response_body["decision"] == "approve"
        assert decide_result.response_body["case_status"] == STATUS_COMMITTED

    @pytest.mark.asyncio
    async def test_manager_reject_returns_rejected(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
        sod_policy,
    ):
        """Manager can reject expense and status becomes REJECTED."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        set_sod_policy(sod_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Create expense
        create_result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        approval_id = create_result.response_body["approval_id"]

        # Reject
        decide_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id=approval_id,
            decision="reject",
            reason="Over budget",
        )

        # Assert
        assert decide_result.status_code == 200
        assert decide_result.response_body["decision"] == "reject"
        assert decide_result.response_body["case_status"] == STATUS_REJECTED

    @pytest.mark.asyncio
    async def test_self_approve_denied_by_sod(
        self,
        temp_dir,
        expense_create_operation,
        rbac_with_approvals,
        approvals_policy,
        sod_policy,
    ):
        """Self-approve is blocked by SoD constraint."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Actor with both analyst and manager roles
        actor_both_roles = ActorContext(
            tenant_id="test-tenant",
            actor_id="user-both-roles",
            roles=["analyst", "manager"],
        )

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        set_sod_policy(sod_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Create expense
        create_result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_both_roles,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        approval_id = create_result.response_body["approval_id"]

        # Try to self-approve (same actor)
        decide_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_both_roles,  # Same actor!
            approval_id=approval_id,
            decision="approve",
        )

        # Assert - SoD violation
        assert decide_result.status_code == 409
        assert decide_result.error_code == SOD_VIOLATION

    @pytest.mark.asyncio
    async def test_analyst_cannot_approve(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        rbac_with_approvals,
        approvals_policy,
    ):
        """Analyst without manager role cannot approve."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Another analyst (different from creator)
        another_analyst = ActorContext(
            tenant_id="test-tenant",
            actor_id="analyst-002",
            roles=["analyst"],
        )

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Create expense
        create_result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        approval_id = create_result.response_body["approval_id"]

        # Try to approve as analyst (no manager role)
        decide_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=another_analyst,
            approval_id=approval_id,
            decision="approve",
        )

        # Assert - forbidden
        assert decide_result.status_code == 403
        assert decide_result.error_code == "APPROVAL_FORBIDDEN"

    @pytest.mark.asyncio
    async def test_invalid_decision_returns_400(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
    ):
        """Invalid decision value returns 400."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Create expense
        create_result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        approval_id = create_result.response_body["approval_id"]

        # Try invalid decision
        decide_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id=approval_id,
            decision="maybe",  # Invalid!
        )

        # Assert
        assert decide_result.status_code == 400
        assert decide_result.error_code == "APPROVAL_DECISION_INVALID"

    @pytest.mark.asyncio
    async def test_approve_nonexistent_returns_404(
        self,
        temp_dir,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
    ):
        """Approve nonexistent approval returns 404."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Try to approve non-existent
        decide_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id="non-existent-id",
            decision="approve",
        )

        # Assert
        assert decide_result.status_code == 404
        assert decide_result.error_code == "APPROVAL_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_re_decide_returns_409(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
        sod_policy,
        invariants_policy,
    ):
        """Re-deciding on already decided approval returns 409."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        set_sod_policy(sod_policy, dept_id=dept_id)
        set_invariants_policy(invariants_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Create expense
        create_result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        approval_id = create_result.response_body["approval_id"]

        # First decision - approve
        first_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id=approval_id,
            decision="approve",
        )
        assert first_result.status_code == 200

        # Second decision - should fail
        second_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id=approval_id,
            decision="reject",
        )

        # Assert
        assert second_result.status_code == 409
        assert second_result.error_code == "APPROVAL_ALREADY_DECIDED"


class TestFullApprovalFlow:
    """Test complete approval flows."""

    @pytest.mark.asyncio
    async def test_finance_complete_flow_approve(
        self,
        temp_dir,
        expense_create_operation,
        expense_read_operation,
        actor_analyst,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
        sod_policy,
        invariants_policy,
    ):
        """Complete flow: create → pending → approve → COMMITTED."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        set_sod_policy(sod_policy, dept_id=dept_id)
        set_invariants_policy(invariants_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Step 1: Create expense (analyst)
        create_result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 250, "description": "Q1 supplies"},
        )
        assert create_result.status_code == 202
        expense_id = create_result.response_body["expense_id"]
        approval_id = create_result.response_body["approval_id"]

        # Step 2: Read expense - should be PENDING_APPROVAL
        read_result = await dispatch_read(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_read_operation,
            path_params={"expense_id": expense_id},
        )
        assert read_result.status_code == 200
        assert read_result.response_body["status"] == STATUS_PENDING_APPROVAL

        # Step 3: Self-approve attempt (should fail)
        self_approve_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,  # Same as creator
            approval_id=approval_id,
            decision="approve",
        )
        assert self_approve_result.status_code == 403  # No manager role

        # Step 4: Manager approves
        approve_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id=approval_id,
            decision="approve",
            reason="Approved for Q1",
        )
        assert approve_result.status_code == 200
        assert approve_result.response_body["case_status"] == STATUS_COMMITTED

        # Step 5: Read expense - should be COMMITTED
        final_read = await dispatch_read(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_read_operation,
            path_params={"expense_id": expense_id},
        )
        assert final_read.status_code == 200
        assert final_read.response_body["status"] == STATUS_COMMITTED

    @pytest.mark.asyncio
    async def test_finance_complete_flow_reject(
        self,
        temp_dir,
        expense_create_operation,
        expense_read_operation,
        actor_analyst,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
        sod_policy,
    ):
        """Complete flow: create → pending → reject → REJECTED."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup
        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        set_sod_policy(sod_policy, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Create expense
        create_result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        expense_id = create_result.response_body["expense_id"]
        approval_id = create_result.response_body["approval_id"]

        # Manager rejects
        reject_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id=approval_id,
            decision="reject",
            reason="Over budget",
        )
        assert reject_result.status_code == 200
        assert reject_result.response_body["case_status"] == STATUS_REJECTED

        # Read expense - should be REJECTED
        final_read = await dispatch_read(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_read_operation,
            path_params={"expense_id": expense_id},
        )
        assert final_read.response_body["status"] == STATUS_REJECTED


class TestApprovalMultiTenantIsolation:
    """Test approval isolation between institutions and departments."""

    @pytest.mark.asyncio
    async def test_approval_isolated_between_institutions(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
        sod_policy,
        invariants_policy,
    ):
        """Approvals are isolated between institutions."""
        inst_a = "institution-A"
        inst_b = "institution-B"
        dept_id = "finance"

        # Setup both institutions
        for inst in [inst_a, inst_b]:
            set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
            set_approvals_policy(approvals_policy, dept_id=dept_id)
            set_sod_policy(sod_policy, dept_id=dept_id)
            set_invariants_policy(invariants_policy, dept_id=dept_id)
            setup_state_store(temp_dir, inst, dept_id)

        # Need separate ledgers per institution
        ledger_a = AuditLedger(ledger_path=temp_dir / "ledger_a.jsonl")
        set_ledger(ledger_a)

        # Create expense in institution A
        create_result = await dispatch_approval_request(
            institution_id=inst_a,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        approval_id_a = create_result.response_body["approval_id"]

        # Try to decide from institution B - should fail (approval not found)
        decide_result = await dispatch_approval_decide(
            institution_id=inst_b,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id=approval_id_a,
            decision="approve",
        )

        # Approval event is in ledger A, not visible from B's perspective
        # The approval_id itself won't be found since different state stores
        assert decide_result.status_code == 404
        assert decide_result.error_code == "CASE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_full_isolation_matrix_approvals(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
        sod_policy,
        invariants_policy,
    ):
        """Full isolation test: 2 institutions x 2 departments for approvals."""
        institutions = ["inst-A", "inst-B"]
        departments = ["finance", "hr"]

        # Setup all combinations
        for inst in institutions:
            for dept in departments:
                set_rbac_policy(rbac_with_approvals, dept_id=dept)
                set_approvals_policy(approvals_policy, dept_id=dept)
                set_sod_policy(sod_policy, dept_id=dept)
                set_invariants_policy(invariants_policy, dept_id=dept)
                setup_state_store(temp_dir, inst, dept)

        setup_ledger_for_test(temp_dir)

        # Create expense in inst-A/finance
        create_result = await dispatch_approval_request(
            institution_id="inst-A",
            dept_id="finance",
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 100},
        )
        assert create_result.status_code == 202
        approval_id = create_result.response_body["approval_id"]
        expense_id = create_result.response_body["expense_id"]

        # Approve in correct context (inst-A/finance)
        approve_result = await dispatch_approval_decide(
            institution_id="inst-A",
            dept_id="finance",
            actor=actor_manager,
            approval_id=approval_id,
            decision="approve",
        )
        assert approve_result.status_code == 200

        # Verify expense state in correct context
        from engine.core.state_store import get_state_store
        store_a_finance = get_state_store("finance", institution_id="inst-A")
        expense = store_a_finance.get_expense(expense_id)
        assert expense.status == STATUS_COMMITTED

        # Verify expense not visible in other contexts
        store_a_hr = get_state_store("hr", institution_id="inst-A")
        assert store_a_hr.get_expense(expense_id) is None

        store_b_finance = get_state_store("finance", institution_id="inst-B")
        assert store_b_finance.get_expense(expense_id) is None

        store_b_hr = get_state_store("hr", institution_id="inst-B")
        assert store_b_hr.get_expense(expense_id) is None


class TestInvariantsValidation:
    """Test invariants validation during approval."""

    @pytest.mark.asyncio
    async def test_approve_with_invalid_amount_fails(
        self,
        temp_dir,
        expense_create_operation,
        actor_analyst,
        actor_manager,
        rbac_with_approvals,
        approvals_policy,
        sod_policy,
    ):
        """Approve fails when invariants are violated."""
        institution_id = "inst-001"
        dept_id = "finance"

        # Setup with strict invariants
        strict_invariants = InvariantsPolicy({
            "expense": {
                "amount": {"min": 10, "max": 100},  # Strict limits
            },
        })

        set_rbac_policy(rbac_with_approvals, dept_id=dept_id)
        set_approvals_policy(approvals_policy, dept_id=dept_id)
        set_sod_policy(sod_policy, dept_id=dept_id)
        set_invariants_policy(strict_invariants, dept_id=dept_id)
        setup_state_store(temp_dir, institution_id, dept_id)
        setup_ledger_for_test(temp_dir)

        # Create expense with amount over limit
        create_result = await dispatch_approval_request(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_analyst,
            operation=expense_create_operation,
            request_body={"amount": 500},  # Over max 100
        )
        approval_id = create_result.response_body["approval_id"]

        # Try to approve - should fail on invariants
        decide_result = await dispatch_approval_decide(
            institution_id=institution_id,
            dept_id=dept_id,
            actor=actor_manager,
            approval_id=approval_id,
            decision="approve",
        )

        # Assert - invariant violation
        assert decide_result.status_code == 422
        assert decide_result.error_code == INVARIANT_VIOLATION
        assert "violations" in decide_result.response_body
