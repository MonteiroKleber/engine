"""Tests for GAP 4: Agents as governed actors with delegation chain.

Tests cover:
- on_behalf_of header validation
- Agent detection from registry
- Agent request creation on deny
- Ledger events with on_behalf_of
- Admin endpoints for agent requests
"""

import os
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.core.actor_context import ActorContext, get_auth_mode, AuthMode
from engine.core.actor_tokens import (
    ActorTokensRegistry,
    get_actor_tokens_registry,
)
from engine.core.errors import (
    ON_BEHALF_OF_NOT_AGENT,
    ON_BEHALF_OF_INVALID,
)
from engine.agent_ops.agent_requests import (
    AgentRequest,
    AgentRequestsRegistry,
    get_agent_requests_registry,
    AGENT_REQUEST_CREATED,
)
from engine.legacy_bridge.write_registry import LegacyWriteRegistry


# Test fixtures

@pytest.fixture
def temp_data_root(tmp_path):
    """Create a temporary data root for testing."""
    with patch.dict(os.environ, {"ENGINE_DATA_ROOT": str(tmp_path)}):
        yield tmp_path


@pytest.fixture
def institution_id():
    """Test institution UUID."""
    return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def agent_actor_id():
    """Test agent actor UUID."""
    return "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def delegatee_actor_id():
    """Test delegatee (on_behalf_of) actor UUID."""
    return "33333333-3333-3333-3333-333333333333"


# ============================================================================
# ActorContext Tests
# ============================================================================


class TestActorContextWithDelegation:
    """Test ActorContext with on_behalf_of and is_agent fields."""

    def test_actor_context_defaults(self):
        """ActorContext has default values for GAP 4 fields."""
        ctx = ActorContext(actor_id="test-actor")
        assert ctx.is_agent is False
        assert ctx.on_behalf_of is None

    def test_actor_context_with_agent_flag(self):
        """ActorContext can be created with is_agent=True."""
        ctx = ActorContext(actor_id="test-actor", is_agent=True)
        assert ctx.is_agent is True

    def test_actor_context_with_on_behalf_of(self):
        """ActorContext can store on_behalf_of delegation."""
        ctx = ActorContext(
            actor_id="agent-actor",
            is_agent=True,
            on_behalf_of="delegatee-actor",
        )
        assert ctx.on_behalf_of == "delegatee-actor"

    def test_can_delegate_requires_agent(self):
        """can_delegate() returns True only for agents."""
        non_agent = ActorContext(actor_id="user", is_agent=False)
        assert non_agent.can_delegate() is False

        agent = ActorContext(actor_id="agent", is_agent=True)
        assert agent.can_delegate() is True


# ============================================================================
# Actor Tokens Registry Tests (is_agent)
# ============================================================================


class TestActorTokensWithAgent:
    """Test ActorTokensRegistry with is_agent field."""

    def test_create_token_with_is_agent(self, temp_data_root, institution_id):
        """Token can be created with is_agent=True."""
        ActorTokensRegistry.reset_instance()
        registry = get_actor_tokens_registry()

        token, error = registry.create_token(
            institution_id=institution_id,
            actor_id="agent-001",
            roles=["agent"],
            is_agent=True,
        )

        assert error is None
        assert token is not None

        # Verify token returns is_agent
        actor_id, roles, valid, error_code, is_agent = registry.verify_token(
            institution_id=institution_id,
            plaintext_token=token,
        )

        assert valid is True
        assert is_agent is True

    def test_create_token_without_is_agent(self, temp_data_root, institution_id):
        """Token without is_agent defaults to False."""
        ActorTokensRegistry.reset_instance()
        registry = get_actor_tokens_registry()

        token, error = registry.create_token(
            institution_id=institution_id,
            actor_id="user-001",
            roles=["user"],
            # is_agent not specified
        )

        assert error is None

        _, _, valid, _, is_agent = registry.verify_token(
            institution_id=institution_id,
            plaintext_token=token,
        )

        assert valid is True
        assert is_agent is False


# ============================================================================
# Agent Requests Registry Tests
# ============================================================================


class TestAgentRequestsRegistry:
    """Test AgentRequestsRegistry for auto-solicitation storage."""

    def test_create_request(self, temp_data_root, institution_id, agent_actor_id, delegatee_actor_id):
        """Can create an agent request on deny."""
        registry = get_agent_requests_registry(institution_id)

        request = registry.create_request(
            agent_actor_id=agent_actor_id,
            on_behalf_of=delegatee_actor_id,
            endpoint_sig="POST /bridge/write/increase_limit",
            action_type="increase_limit",
            deny_code="MANDATE_DENIED",
            deny_details={"reason": "No valid mandate"},
        )

        assert request.request_id is not None
        assert request.agent_actor_id == agent_actor_id
        assert request.on_behalf_of == delegatee_actor_id
        assert request.action_type == "increase_limit"
        assert request.deny_code == "MANDATE_DENIED"
        assert request.status == "pending"

    def test_get_request(self, temp_data_root, institution_id, agent_actor_id):
        """Can retrieve a request by ID."""
        registry = get_agent_requests_registry(institution_id)

        created = registry.create_request(
            agent_actor_id=agent_actor_id,
            on_behalf_of=None,
            endpoint_sig="POST /bridge/write/decrease_quota",
            action_type="decrease_quota",
            deny_code="POLICY_DENIED",
        )

        retrieved = registry.get_request(created.request_id)

        assert retrieved is not None
        assert retrieved.request_id == created.request_id
        assert retrieved.action_type == "decrease_quota"

    def test_list_requests_by_status(self, temp_data_root, institution_id, agent_actor_id):
        """Can list requests filtered by status."""
        registry = get_agent_requests_registry(institution_id)

        # Create two requests
        registry.create_request(
            agent_actor_id=agent_actor_id,
            on_behalf_of=None,
            endpoint_sig="POST /bridge/write/action1",
            action_type="action1",
            deny_code="MANDATE_DENIED",
        )

        registry.create_request(
            agent_actor_id=agent_actor_id,
            on_behalf_of=None,
            endpoint_sig="POST /bridge/write/action2",
            action_type="action2",
            deny_code="AUTONOMY_INSUFFICIENT",
        )

        # List all pending
        pending = registry.list_requests(status="pending")
        assert len(pending) == 2

        # List resolved (should be empty)
        resolved = registry.list_requests(status="resolved")
        assert len(resolved) == 0

    def test_list_requests_by_agent(self, temp_data_root, institution_id, agent_actor_id):
        """Can list requests filtered by agent ID."""
        registry = get_agent_requests_registry(institution_id)

        other_agent = "44444444-4444-4444-4444-444444444444"

        registry.create_request(
            agent_actor_id=agent_actor_id,
            on_behalf_of=None,
            endpoint_sig="POST /bridge/write/action1",
            action_type="action1",
            deny_code="MANDATE_DENIED",
        )

        registry.create_request(
            agent_actor_id=other_agent,
            on_behalf_of=None,
            endpoint_sig="POST /bridge/write/action2",
            action_type="action2",
            deny_code="POLICY_DENIED",
        )

        # Filter by agent_id
        agent_requests = registry.list_requests(agent_id=agent_actor_id)
        assert len(agent_requests) == 1
        assert agent_requests[0].agent_actor_id == agent_actor_id

    def test_resolve_request(self, temp_data_root, institution_id, agent_actor_id):
        """Can resolve a pending request."""
        registry = get_agent_requests_registry(institution_id)

        request = registry.create_request(
            agent_actor_id=agent_actor_id,
            on_behalf_of=None,
            endpoint_sig="POST /bridge/write/action1",
            action_type="action1",
            deny_code="MANDATE_DENIED",
        )

        assert request.status == "pending"

        # Resolve it
        resolved = registry.resolve_request(
            request_id=request.request_id,
            resolved_by="admin-user",
            status="resolved",
        )

        assert resolved.status == "resolved"
        assert resolved.resolved_by == "admin-user"
        assert resolved.resolved_at is not None


# ============================================================================
# Legacy Write Registry - Agent Auto-Request Tests
# ============================================================================


class TestLegacyWriteAgentAutoRequest:
    """Test that legacy write creates agent requests on deny."""

    def test_agent_deny_creates_request(self, temp_data_root, institution_id, agent_actor_id, delegatee_actor_id):
        """When an agent is denied, an agent request is created."""
        # Set dev mode
        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "dev"}):
            registry = LegacyWriteRegistry(institution_id)

            # Request as agent without admin role - should be denied
            result = registry.request_write(
                action_type="increase_limit",
                params={"customer_id": "cust-123", "new_limit": 5000},
                actor_id=agent_actor_id,
                actor_roles=[],  # No admin role
                is_agent=True,
                on_behalf_of=delegatee_actor_id,
            )

            assert result.success is False
            assert result.denied_by == "NO_ADMIN_ROLE"

            # Check that agent request was created
            agent_registry = get_agent_requests_registry(institution_id)
            requests = agent_registry.list_requests(agent_id=agent_actor_id)

            assert len(requests) == 1
            assert requests[0].agent_actor_id == agent_actor_id
            assert requests[0].on_behalf_of == delegatee_actor_id
            assert requests[0].action_type == "increase_limit"
            assert requests[0].deny_code == "NO_ADMIN_ROLE"

    def test_non_agent_deny_no_request(self, temp_data_root, institution_id):
        """When a non-agent is denied, no agent request is created."""
        user_id = "55555555-5555-5555-5555-555555555555"

        with patch.dict(os.environ, {"ENGINE_INSTALL_MODE": "dev"}):
            registry = LegacyWriteRegistry(institution_id)

            result = registry.request_write(
                action_type="increase_limit",
                params={"customer_id": "cust-123", "new_limit": 5000},
                actor_id=user_id,
                actor_roles=[],
                is_agent=False,  # Not an agent
            )

            assert result.success is False

            # Check that no agent request was created
            agent_registry = get_agent_requests_registry(institution_id)
            requests = agent_registry.list_requests(agent_id=user_id)

            assert len(requests) == 0


# ============================================================================
# Ledger Events Tests
# ============================================================================


class TestLedgerEventsWithDelegation:
    """Test that ledger events include on_behalf_of when present."""

    def test_intent_created_includes_on_behalf_of(self, temp_data_root, institution_id, agent_actor_id, delegatee_actor_id):
        """LEGACY_WRITE_INTENT_CREATED event includes on_behalf_of."""
        from engine.core.ledger import get_ledger_for_institution, reset_institution_ledgers

        # Note: temp_data_root fixture already patches ENGINE_DATA_ROOT
        # Reset ledgers after env is set
        reset_institution_ledgers()

        registry = LegacyWriteRegistry(institution_id)

        registry.request_write(
            action_type="increase_limit",
            params={"customer_id": "cust-123", "new_limit": 5000},
            actor_id=agent_actor_id,
            actor_roles=["admin"],  # Has admin role
            is_agent=True,
            on_behalf_of=delegatee_actor_id,
        )

        # Check ledger events
        ledger = get_ledger_for_institution(institution_id)
        events = ledger.get_all_events()

        # Find INTENT_CREATED event
        intent_events = [e for e in events if e.event_type == "LEGACY_WRITE_INTENT_CREATED"]
        assert len(intent_events) >= 1

        intent_event = intent_events[-1]
        assert intent_event.payload.get("on_behalf_of") == delegatee_actor_id
        assert intent_event.payload.get("is_agent") is True

    def test_denied_includes_on_behalf_of(self, temp_data_root, institution_id, agent_actor_id, delegatee_actor_id):
        """LEGACY_WRITE_DENIED event includes on_behalf_of."""
        from engine.core.ledger import get_ledger_for_institution, reset_institution_ledgers

        reset_institution_ledgers()

        registry = LegacyWriteRegistry(institution_id)

        registry.request_write(
            action_type="increase_limit",
            params={"customer_id": "cust-123", "new_limit": 5000},
            actor_id=agent_actor_id,
            actor_roles=[],  # No admin - will be denied
            is_agent=True,
            on_behalf_of=delegatee_actor_id,
        )

        # Check ledger events
        ledger = get_ledger_for_institution(institution_id)
        events = ledger.get_all_events()

        # Find DENIED event
        denied_events = [e for e in events if e.event_type == "LEGACY_WRITE_DENIED"]
        assert len(denied_events) >= 1

        denied_event = denied_events[-1]
        assert denied_event.payload.get("on_behalf_of") == delegatee_actor_id
        assert denied_event.payload.get("is_agent") is True

    def test_agent_request_created_event(self, temp_data_root, institution_id, agent_actor_id):
        """AGENT_REQUEST_CREATED event is emitted when agent is denied."""
        from engine.core.ledger import get_ledger_for_institution, reset_institution_ledgers

        reset_institution_ledgers()

        registry = LegacyWriteRegistry(institution_id)

        registry.request_write(
            action_type="increase_limit",
            params={"customer_id": "cust-123", "new_limit": 5000},
            actor_id=agent_actor_id,
            actor_roles=[],  # No admin - will be denied
            is_agent=True,
        )

        # Check ledger events
        ledger = get_ledger_for_institution(institution_id)
        events = ledger.get_all_events()

        # Find AGENT_REQUEST_CREATED event
        request_events = [e for e in events if e.event_type == AGENT_REQUEST_CREATED]
        assert len(request_events) >= 1

        request_event = request_events[-1]
        assert request_event.payload.get("agent_actor_id") == agent_actor_id
        assert request_event.payload.get("action_type") == "increase_limit"
        assert request_event.payload.get("deny_code") == "NO_ADMIN_ROLE"


# ============================================================================
# Dependencies Tests (on_behalf_of validation)
# ============================================================================


class TestOnBehalfOfValidation:
    """Test X-On-Behalf-Of header validation in dependencies."""

    def test_on_behalf_of_invalid_uuid(self):
        """on_behalf_of must be a valid UUID."""
        from engine.api.dependencies import _validate_on_behalf_of

        ctx = ActorContext(actor_id="agent-id", is_agent=True)

        with pytest.raises(Exception) as exc_info:
            _validate_on_behalf_of(
                context=ctx,
                on_behalf_of="not-a-uuid",
                auth_mode=AuthMode.DEV,
                institution_id=None,
            )

        # Should raise HTTPException with ON_BEHALF_OF_INVALID
        assert "ON_BEHALF_OF_INVALID" in str(exc_info.value.detail) or exc_info.value.status_code == 400

    def test_on_behalf_of_not_agent_strict_mode(self):
        """In strict mode, non-agents cannot use on_behalf_of."""
        from engine.api.dependencies import _validate_on_behalf_of

        ctx = ActorContext(actor_id="user-id", is_agent=False, identity_verified=True)

        with pytest.raises(Exception) as exc_info:
            _validate_on_behalf_of(
                context=ctx,
                on_behalf_of="33333333-3333-3333-3333-333333333333",
                auth_mode=AuthMode.STRICT,
                institution_id=None,
            )

        # Should raise HTTPException with ON_BEHALF_OF_NOT_AGENT
        assert exc_info.value.status_code == 403

    def test_on_behalf_of_allowed_for_agent(self):
        """Agents can use on_behalf_of."""
        from engine.api.dependencies import _validate_on_behalf_of

        ctx = ActorContext(actor_id="agent-id", is_agent=True)
        delegatee = "33333333-3333-3333-3333-333333333333"

        updated = _validate_on_behalf_of(
            context=ctx,
            on_behalf_of=delegatee,
            auth_mode=AuthMode.STRICT,
            institution_id=None,
        )

        assert updated.on_behalf_of == delegatee

    def test_on_behalf_of_dev_mode_with_agent_role(self):
        """In dev mode, actors with 'agent' role can use on_behalf_of."""
        from engine.api.dependencies import _validate_on_behalf_of

        ctx = ActorContext(actor_id="user-id", roles=["agent"], is_agent=False)
        delegatee = "33333333-3333-3333-3333-333333333333"

        updated = _validate_on_behalf_of(
            context=ctx,
            on_behalf_of=delegatee,
            auth_mode=AuthMode.DEV,
            institution_id=None,
        )

        assert updated.on_behalf_of == delegatee
        assert updated.is_agent is True  # Set from role in dev mode
