"""Unit tests for Bazari MVP dispatcher CRUD operations.

Tests dispatcher and state_store directly for Bazari entities:
- ContentReport: create, read, list
- ChatBlock: create, read, delete
- Multi-tenant isolation

NO HTTP/TestClient - tests dispatcher functions and state_store methods directly.
Uses tmp_path for storage (not var/).
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.core.state_store import (
    StateStore,
    ContentReportState,
    ChatBlockState,
    CONTENT_REPORT_STATUS_PENDING,
    set_state_store,
    reset_all_state_stores,
)
from engine.core.dispatcher import (
    dispatch_create,
    dispatch_read,
    dispatch_list,
    dispatch_delete,
    DispatchResult,
    ENTITY_CONFIG,
)
from engine.core.actor_context import ActorContext
from engine.core.operations import Operation
from engine.core.errors import (
    CONTENT_REPORT_NOT_FOUND,
    CHAT_BLOCK_NOT_FOUND,
)


# Test fixtures

@pytest.fixture
def tmp_state_store(tmp_path: Path):
    """Create a StateStore using tmp_path for isolation."""
    store_path = tmp_path / "state_store.json"
    store = StateStore(path=store_path)
    yield store
    # Cleanup
    reset_all_state_stores()


@pytest.fixture
def mock_actor():
    """Create a mock actor context."""
    return ActorContext(
        actor_id="test-actor-123",
        tenant_id="test-tenant-456",
        roles=["user", "moderator"],
    )


@pytest.fixture
def mock_institution_id():
    """Test institution ID."""
    return "00000000-0000-0000-0000-000000000001"


def create_operation(
    operation_id: str,
    method: str,
    path: str,
    permission: str,
    bind_kind: str,
    entity: str,
) -> Operation:
    """Helper to create Operation objects for testing."""
    return Operation(
        operation_id=operation_id,
        method=method,
        path=path,
        endpoint_sig=f"{method} {path}",
        permission=permission,
        scope="tenant",
        idempotency="none",
        errors=[],
        bind={"kind": bind_kind, "entity": entity},
    )


# Helper to mock all gates (RBAC, Policy, Mandates, Autonomy) to allow
def mock_gates_allow():
    """Returns context managers that mock all dispatcher gates to allow."""
    # RBAC gate
    rbac_mock = patch("engine.core.dispatcher.gate_rbac", return_value=True)

    # Policy gate
    policy_result = MagicMock()
    policy_result.allow = True
    policy_result.violations = []
    policy_mock = patch("engine.core.dispatcher.evaluate_policies", return_value=policy_result)

    # Mandates gate
    mandate_result = MagicMock()
    mandate_result.allow = True
    mandate_result.violations = []
    mandate_mock = patch("engine.core.dispatcher.evaluate_mandates", return_value=mandate_result)

    # Autonomy gate
    autonomy_result = MagicMock()
    autonomy_result.decision = "allow"
    autonomy_result.current_level = 0
    autonomy_result.required_level = 0
    autonomy_result.rule_id = None
    autonomy_result.reason = None
    autonomy_mock = patch("engine.core.dispatcher.evaluate_autonomy", return_value=autonomy_result)

    # Emit functions (no-op)
    emit_policy_mock = patch("engine.core.dispatcher.emit_policy_decision")
    emit_mandate_mock = patch("engine.core.dispatcher.emit_mandate_decision")
    emit_autonomy_mock = patch("engine.core.dispatcher.emit_autonomy_evaluated")
    emit_rbac_mock = patch("engine.core.dispatcher._emit_rbac_decision")

    return [
        rbac_mock,
        policy_mock,
        mandate_mock,
        autonomy_mock,
        emit_policy_mock,
        emit_mandate_mock,
        emit_autonomy_mock,
        emit_rbac_mock,
    ]


# =============================================================================
# State Store Direct Tests
# =============================================================================

class TestStateStoreContentReport:
    """Direct tests for ContentReport state store methods."""

    def test_create_content_report(self, tmp_state_store: StateStore):
        """Test creating a content report."""
        report = tmp_state_store.create_content_report(
            report_id="report-001",
            content_type="POST",
            content_id="post-123",
            reporter_id="user-456",
            reason="spam",
            description="This is spam content",
        )

        assert report.report_id == "report-001"
        assert report.content_type == "POST"
        assert report.content_id == "post-123"
        assert report.reporter_id == "user-456"
        assert report.reason == "spam"
        assert report.description == "This is spam content"
        assert report.status == CONTENT_REPORT_STATUS_PENDING
        assert report.created_at is not None

    def test_get_content_report(self, tmp_state_store: StateStore):
        """Test retrieving a content report by ID."""
        tmp_state_store.create_content_report(
            report_id="report-002",
            content_type="COMMENT",
            content_id="comment-789",
            reporter_id="user-111",
            reason="harassment",
        )

        report = tmp_state_store.get_content_report("report-002")
        assert report is not None
        assert report.report_id == "report-002"
        assert report.content_type == "COMMENT"

    def test_get_nonexistent_content_report(self, tmp_state_store: StateStore):
        """Test retrieving a non-existent content report returns None."""
        report = tmp_state_store.get_content_report("nonexistent-id")
        assert report is None

    def test_list_content_reports(self, tmp_state_store: StateStore):
        """Test listing all content reports."""
        # Create multiple reports
        tmp_state_store.create_content_report(
            report_id="report-a",
            content_type="POST",
            content_id="post-1",
            reporter_id="user-1",
            reason="spam",
        )
        tmp_state_store.create_content_report(
            report_id="report-b",
            content_type="COMMENT",
            content_id="comment-2",
            reporter_id="user-2",
            reason="harassment",
        )

        reports = tmp_state_store.list_content_reports()
        assert len(reports) == 2
        report_ids = [r.report_id for r in reports]
        assert "report-a" in report_ids
        assert "report-b" in report_ids

    def test_list_empty_content_reports(self, tmp_state_store: StateStore):
        """Test listing returns empty list when no reports exist."""
        reports = tmp_state_store.list_content_reports()
        assert reports == []


class TestStateStoreChatBlock:
    """Direct tests for ChatBlock state store methods."""

    def test_create_chat_block(self, tmp_state_store: StateStore):
        """Test creating a chat block."""
        block = tmp_state_store.create_chat_block(
            block_id="block-001",
            blocker_profile_id="profile-111",
            blocked_profile_id="profile-222",
        )

        assert block.block_id == "block-001"
        assert block.blocker_profile_id == "profile-111"
        assert block.blocked_profile_id == "profile-222"
        assert block.created_at is not None

    def test_get_chat_block(self, tmp_state_store: StateStore):
        """Test retrieving a chat block by ID."""
        tmp_state_store.create_chat_block(
            block_id="block-002",
            blocker_profile_id="profile-a",
            blocked_profile_id="profile-b",
        )

        block = tmp_state_store.get_chat_block("block-002")
        assert block is not None
        assert block.block_id == "block-002"

    def test_delete_chat_block(self, tmp_state_store: StateStore):
        """Test deleting a chat block."""
        tmp_state_store.create_chat_block(
            block_id="block-003",
            blocker_profile_id="profile-x",
            blocked_profile_id="profile-y",
        )

        # Verify it exists
        assert tmp_state_store.get_chat_block("block-003") is not None

        # Delete it
        deleted = tmp_state_store.delete_chat_block("block-003")
        assert deleted is True

        # Verify it's gone
        assert tmp_state_store.get_chat_block("block-003") is None

    def test_delete_nonexistent_chat_block(self, tmp_state_store: StateStore):
        """Test deleting a non-existent chat block returns False."""
        deleted = tmp_state_store.delete_chat_block("nonexistent-block")
        assert deleted is False


# =============================================================================
# Dispatcher Tests (with mocked gates)
# =============================================================================

class TestDispatcherContentReport:
    """Tests for dispatcher ContentReport operations."""

    @pytest.mark.asyncio
    async def test_dispatch_create_content_report(
        self, tmp_state_store: StateStore, mock_actor, mock_institution_id
    ):
        """Test dispatcher create for ContentReport."""
        # Setup: register state store for the institution
        set_state_store(tmp_state_store, dept_id=None, institution_id=mock_institution_id)

        operation = create_operation(
            operation_id="create_content_report",
            method="POST",
            path="/reports",
            permission="reports.create",
            bind_kind="create",
            entity="ContentReport",
        )

        request_body = {
            "content_type": "POST",
            "content_id": "post-999",
            "reason": "spam",
            "description": "Spam post",
        }

        # Mock all gates
        mocks = mock_gates_allow()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7]:
            result = await dispatch_create(
                institution_id=mock_institution_id,
                dept_id=None,
                actor=mock_actor,
                operation=operation,
                request_body=request_body,
            )

        assert result.status_code == 200
        assert "id" in result.response_body
        assert result.response_body["content_type"] == "POST"
        assert result.response_body["reason"] == "spam"

        # Verify in state store
        report_id = result.response_body["id"]
        stored = tmp_state_store.get_content_report(report_id)
        assert stored is not None
        assert stored.content_type == "POST"

    @pytest.mark.asyncio
    async def test_dispatch_read_content_report(
        self, tmp_state_store: StateStore, mock_actor, mock_institution_id
    ):
        """Test dispatcher read for ContentReport."""
        set_state_store(tmp_state_store, dept_id=None, institution_id=mock_institution_id)

        # Create a report first
        report = tmp_state_store.create_content_report(
            report_id="read-test-001",
            content_type="COMMENT",
            content_id="comment-123",
            reporter_id="user-abc",
            reason="harassment",
        )

        operation = create_operation(
            operation_id="get_content_report",
            method="GET",
            path="/reports/{report_id}",
            permission="reports.read",
            bind_kind="read",
            entity="ContentReport",
        )

        path_params = {"report_id": "read-test-001"}

        mocks = mock_gates_allow()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7]:
            result = await dispatch_read(
                institution_id=mock_institution_id,
                dept_id=None,
                actor=mock_actor,
                operation=operation,
                path_params=path_params,
            )

        assert result.status_code == 200
        assert result.response_body["id"] == "read-test-001"
        assert result.response_body["content_type"] == "COMMENT"

    @pytest.mark.asyncio
    async def test_dispatch_read_nonexistent_content_report(
        self, tmp_state_store: StateStore, mock_actor, mock_institution_id
    ):
        """Test dispatcher read returns 404 for non-existent ContentReport."""
        set_state_store(tmp_state_store, dept_id=None, institution_id=mock_institution_id)

        operation = create_operation(
            operation_id="get_content_report",
            method="GET",
            path="/reports/{report_id}",
            permission="reports.read",
            bind_kind="read",
            entity="ContentReport",
        )

        path_params = {"report_id": "nonexistent-id"}

        mocks = mock_gates_allow()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7]:
            result = await dispatch_read(
                institution_id=mock_institution_id,
                dept_id=None,
                actor=mock_actor,
                operation=operation,
                path_params=path_params,
            )

        assert result.status_code == 404
        assert result.response_body["code"] == CONTENT_REPORT_NOT_FOUND

    @pytest.mark.asyncio
    async def test_dispatch_list_content_reports(
        self, tmp_state_store: StateStore, mock_actor, mock_institution_id
    ):
        """Test dispatcher list for ContentReports."""
        set_state_store(tmp_state_store, dept_id=None, institution_id=mock_institution_id)

        # Create some reports
        tmp_state_store.create_content_report(
            report_id="list-001",
            content_type="POST",
            content_id="post-1",
            reporter_id="user-1",
            reason="spam",
        )
        tmp_state_store.create_content_report(
            report_id="list-002",
            content_type="COMMENT",
            content_id="comment-2",
            reporter_id="user-2",
            reason="harassment",
        )

        operation = create_operation(
            operation_id="list_content_reports",
            method="GET",
            path="/admin/reports",
            permission="moderation.reports.list",
            bind_kind="read",
            entity="ContentReport",
        )

        mocks = mock_gates_allow()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7]:
            result = await dispatch_list(
                institution_id=mock_institution_id,
                dept_id=None,
                actor=mock_actor,
                operation=operation,
            )

        assert result.status_code == 200
        assert result.response_body["count"] == 2
        assert len(result.response_body["items"]) == 2


class TestDispatcherChatBlock:
    """Tests for dispatcher ChatBlock operations."""

    @pytest.mark.asyncio
    async def test_dispatch_create_chat_block(
        self, tmp_state_store: StateStore, mock_actor, mock_institution_id
    ):
        """Test dispatcher create for ChatBlock."""
        set_state_store(tmp_state_store, dept_id=None, institution_id=mock_institution_id)

        operation = create_operation(
            operation_id="create_chat_block",
            method="POST",
            path="/chat/blocks",
            permission="chat.blocks.write",
            bind_kind="create",
            entity="ChatBlock",
        )

        request_body = {
            "blocked_profile_id": "profile-to-block",
        }

        mocks = mock_gates_allow()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7]:
            result = await dispatch_create(
                institution_id=mock_institution_id,
                dept_id=None,
                actor=mock_actor,
                operation=operation,
                request_body=request_body,
            )

        assert result.status_code == 200
        assert "id" in result.response_body
        assert result.response_body["blocked_profile_id"] == "profile-to-block"
        # blocker_profile_id should be set from actor
        assert result.response_body["blocker_profile_id"] == mock_actor.actor_id

    @pytest.mark.asyncio
    async def test_dispatch_delete_chat_block(
        self, tmp_state_store: StateStore, mock_actor, mock_institution_id
    ):
        """Test dispatcher delete for ChatBlock."""
        set_state_store(tmp_state_store, dept_id=None, institution_id=mock_institution_id)

        # Create a block first
        block = tmp_state_store.create_chat_block(
            block_id="delete-test-001",
            blocker_profile_id="profile-a",
            blocked_profile_id="profile-b",
        )

        operation = create_operation(
            operation_id="delete_chat_block",
            method="DELETE",
            path="/chat/blocks/{block_id}",
            permission="chat.blocks.write",
            bind_kind="delete",
            entity="ChatBlock",
        )

        path_params = {"block_id": "delete-test-001"}

        mocks = mock_gates_allow()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7]:
            result = await dispatch_delete(
                institution_id=mock_institution_id,
                dept_id=None,
                actor=mock_actor,
                operation=operation,
                path_params=path_params,
            )

        assert result.status_code == 200
        assert result.response_body["deleted"] is True
        assert result.response_body["id"] == "delete-test-001"

        # Verify it's gone
        assert tmp_state_store.get_chat_block("delete-test-001") is None

    @pytest.mark.asyncio
    async def test_dispatch_delete_nonexistent_chat_block(
        self, tmp_state_store: StateStore, mock_actor, mock_institution_id
    ):
        """Test dispatcher delete returns 404 for non-existent ChatBlock."""
        set_state_store(tmp_state_store, dept_id=None, institution_id=mock_institution_id)

        operation = create_operation(
            operation_id="delete_chat_block",
            method="DELETE",
            path="/chat/blocks/{block_id}",
            permission="chat.blocks.write",
            bind_kind="delete",
            entity="ChatBlock",
        )

        path_params = {"block_id": "nonexistent-block"}

        mocks = mock_gates_allow()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7]:
            result = await dispatch_delete(
                institution_id=mock_institution_id,
                dept_id=None,
                actor=mock_actor,
                operation=operation,
                path_params=path_params,
            )

        assert result.status_code == 404
        assert result.response_body["code"] == CHAT_BLOCK_NOT_FOUND


class TestTenantIsolation:
    """Tests for multi-tenant isolation."""

    def test_state_store_isolation_by_path(self, tmp_path: Path):
        """Test that different state stores are isolated by path."""
        store_a_path = tmp_path / "tenant_a" / "state_store.json"
        store_b_path = tmp_path / "tenant_b" / "state_store.json"

        store_a = StateStore(path=store_a_path)
        store_b = StateStore(path=store_b_path)

        # Create report in store A
        store_a.create_content_report(
            report_id="report-in-a",
            content_type="POST",
            content_id="post-1",
            reporter_id="user-a",
            reason="spam",
        )

        # Create report in store B
        store_b.create_content_report(
            report_id="report-in-b",
            content_type="COMMENT",
            content_id="comment-1",
            reporter_id="user-b",
            reason="harassment",
        )

        # Verify isolation
        assert store_a.get_content_report("report-in-a") is not None
        assert store_a.get_content_report("report-in-b") is None

        assert store_b.get_content_report("report-in-b") is not None
        assert store_b.get_content_report("report-in-a") is None

        # Verify lists
        list_a = store_a.list_content_reports()
        list_b = store_b.list_content_reports()

        assert len(list_a) == 1
        assert len(list_b) == 1
        assert list_a[0].report_id == "report-in-a"
        assert list_b[0].report_id == "report-in-b"

    @pytest.mark.asyncio
    async def test_dispatcher_uses_institution_store(self, tmp_path: Path, mock_actor):
        """Test that dispatcher uses institution-specific state store."""
        reset_all_state_stores()

        inst_a = "inst-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        inst_b = "inst-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

        # Create stores for each institution
        store_a_path = tmp_path / "inst_a" / "state_store.json"
        store_b_path = tmp_path / "inst_b" / "state_store.json"

        store_a = StateStore(path=store_a_path)
        store_b = StateStore(path=store_b_path)

        set_state_store(store_a, dept_id=None, institution_id=inst_a)
        set_state_store(store_b, dept_id=None, institution_id=inst_b)

        operation = create_operation(
            operation_id="create_content_report",
            method="POST",
            path="/reports",
            permission="reports.create",
            bind_kind="create",
            entity="ContentReport",
        )

        # Create in institution A
        mocks = mock_gates_allow()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7]:
            result_a = await dispatch_create(
                institution_id=inst_a,
                dept_id=None,
                actor=mock_actor,
                operation=operation,
                request_body={
                    "content_type": "POST",
                    "content_id": "post-a",
                    "reason": "spam",
                },
            )

        # Create in institution B
        mocks = mock_gates_allow()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6], mocks[7]:
            result_b = await dispatch_create(
                institution_id=inst_b,
                dept_id=None,
                actor=mock_actor,
                operation=operation,
                request_body={
                    "content_type": "COMMENT",
                    "content_id": "comment-b",
                    "reason": "harassment",
                },
            )

        assert result_a.status_code == 200
        assert result_b.status_code == 200

        # Verify isolation
        assert len(store_a.list_content_reports()) == 1
        assert len(store_b.list_content_reports()) == 1

        report_a = store_a.list_content_reports()[0]
        report_b = store_b.list_content_reports()[0]

        assert report_a.content_type == "POST"
        assert report_b.content_type == "COMMENT"
