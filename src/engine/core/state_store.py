"""State Store - mutable JSON file for runtime state."""

import base64
import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .errors import STATE_STORE_UNAVAILABLE, STATE_STORE_DEPT_INVALID
from .data_root import resolve_namespaced_path


DEFAULT_STATE_DIR = "var"
DEFAULT_STATE_FILENAME = "state_store.json"

# Pattern for valid dept_id: only alphanumeric, underscore, hyphen
VALID_DEPT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def get_state_store_dir() -> Path:
    """Get state store directory from ENV or default (legacy, no institution)."""
    env_dir = os.environ.get("ENGINE_STATE_STORE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(DEFAULT_STATE_DIR)


def validate_dept_id(dept_id: str) -> None:
    """Validate dept_id contains only safe characters.

    Args:
        dept_id: Department ID to validate.

    Raises:
        RuntimeError: If dept_id contains invalid characters.
    """
    if not VALID_DEPT_PATTERN.match(dept_id):
        raise RuntimeError(
            f"{STATE_STORE_DEPT_INVALID}: Invalid dept_id '{dept_id}' - "
            "only alphanumeric, underscore, and hyphen allowed"
        )


def get_state_store_path(dept_id: Optional[str] = None) -> Path:
    """Get state store file path for given department (legacy, no institution).

    Args:
        dept_id: Department ID, or None for single-mode/default store.

    Returns:
        Path to state store JSON file.

    Raises:
        RuntimeError: If dept_id contains invalid characters.
    """
    state_dir = get_state_store_dir()

    if dept_id is None:
        # Single mode or no dept context
        return state_dir / DEFAULT_STATE_FILENAME

    # Multi mode with dept - validate and create dept-specific path
    validate_dept_id(dept_id)
    return state_dir / f"state_store.{dept_id}.json"


def get_state_store_path_for_institution(
    institution_id: str,
    dept_id: Optional[str] = None,
) -> Path:
    """Get state store file path for institution and optional department.

    Uses ENV ENGINE_STATE_STORE_DIR with namespacing rules:
    - If None: use institution_root/<filename>
    - If absolute: use absolute path/<filename>
    - If relative: use institution_root/<relative>/<filename>

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID, or None for single-mode/default store.

    Returns:
        Path to state store JSON file.

    Raises:
        RuntimeError: If dept_id contains invalid characters.
    """
    env_value = os.environ.get("ENGINE_STATE_STORE_DIR")

    # Determine filename based on dept_id
    if dept_id is None:
        filename = DEFAULT_STATE_FILENAME
    else:
        validate_dept_id(dept_id)
        filename = f"state_store.{dept_id}.json"

    # Resolve base directory
    if env_value is None:
        # No env - use institution root directly for file
        base_path = resolve_namespaced_path(institution_id, None, "")
    elif Path(env_value).is_absolute():
        # Absolute path - use as-is
        base_path = Path(env_value)
    else:
        # Relative path - under institution root
        base_path = resolve_namespaced_path(institution_id, None, env_value)

    return base_path / filename

# Expense statuses
STATUS_PENDING_APPROVAL = "PENDING_APPROVAL"
STATUS_COMMITTED = "COMMITTED"
STATUS_REJECTED = "REJECTED"

# Ticket statuses
TICKET_STATUS_OPEN = "OPEN"
TICKET_STATUS_CLOSED = "CLOSED"

# ContentReport statuses
CONTENT_REPORT_STATUS_PENDING = "PENDING"
CONTENT_REPORT_STATUS_UNDER_REVIEW = "UNDER_REVIEW"
CONTENT_REPORT_STATUS_RESOLVED = "RESOLVED"
CONTENT_REPORT_STATUS_DISMISSED = "DISMISSED"

# ChatReport statuses
CHAT_REPORT_STATUS_PENDING = "PENDING"
CHAT_REPORT_STATUS_UNDER_REVIEW = "UNDER_REVIEW"
CHAT_REPORT_STATUS_RESOLVED = "RESOLVED"
CHAT_REPORT_STATUS_DISMISSED = "DISMISSED"

# ModerationAction statuses
MOD_ACTION_STATUS_PROPOSED = "PROPOSED"
MOD_ACTION_STATUS_PENDING_APPROVAL = "PENDING_APPROVAL"
MOD_ACTION_STATUS_APPROVED = "APPROVED"
MOD_ACTION_STATUS_REJECTED = "REJECTED"
MOD_ACTION_STATUS_APPLIED = "APPLIED"


@dataclass
class ExpenseState:
    """State of an expense in the store."""
    expense_id: str
    status: str
    approval_id: str
    payload_sha256: str
    payload_raw: str  # base64 encoded
    created_at: str
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExpenseState":
        """Create from dictionary."""
        return cls(
            expense_id=data["expense_id"],
            status=data["status"],
            approval_id=data["approval_id"],
            payload_sha256=data["payload_sha256"],
            payload_raw=data["payload_raw"],
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
        )


@dataclass
class TicketState:
    """State of a support ticket in the store."""
    ticket_id: str
    subject: str
    status: str
    payload_raw: str  # base64 encoded
    created_at: str
    description: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TicketState":
        """Create from dictionary."""
        return cls(
            ticket_id=data["ticket_id"],
            subject=data["subject"],
            status=data["status"],
            payload_raw=data["payload_raw"],
            created_at=data["created_at"],
            description=data.get("description"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ContentReportState:
    """State of a content report (social moderation)."""
    report_id: str
    content_type: str  # POST | COMMENT | PROFILE
    content_id: str
    reporter_id: str
    reason: str
    status: str
    created_at: str
    description: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentReportState":
        """Create from dictionary."""
        return cls(
            report_id=data["report_id"],
            content_type=data["content_type"],
            content_id=data["content_id"],
            reporter_id=data["reporter_id"],
            reason=data["reason"],
            status=data["status"],
            created_at=data["created_at"],
            description=data.get("description"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ChatReportState:
    """State of a chat message report."""
    report_id: str
    message_id: str
    thread_id: str
    reporter_id: str
    reason: str
    status: str
    created_at: str
    description: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatReportState":
        """Create from dictionary."""
        return cls(
            report_id=data["report_id"],
            message_id=data["message_id"],
            thread_id=data["thread_id"],
            reporter_id=data["reporter_id"],
            reason=data["reason"],
            status=data["status"],
            created_at=data["created_at"],
            description=data.get("description"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ChatBlockState:
    """State of a chat block (profile-level blocking)."""
    block_id: str
    blocker_profile_id: str
    blocked_profile_id: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatBlockState":
        """Create from dictionary."""
        return cls(
            block_id=data["block_id"],
            blocker_profile_id=data["blocker_profile_id"],
            blocked_profile_id=data["blocked_profile_id"],
            created_at=data["created_at"],
        )


@dataclass
class ModerationActionState:
    """State of a moderation action proposal."""
    action_id: str
    report_id: Optional[str]  # May be null if not from a report
    target_type: str  # USER | POST | COMMENT | PROFILE | MESSAGE
    target_id: str
    action_type: str  # WARN | HIDE | REMOVE | BAN | MUTE | SHADOWBAN
    proposed_by: str
    status: str
    created_at: str
    reason: Optional[str] = None
    approval_id: Optional[str] = None
    applied_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModerationActionState":
        """Create from dictionary."""
        return cls(
            action_id=data["action_id"],
            report_id=data.get("report_id"),
            target_type=data["target_type"],
            target_id=data["target_id"],
            action_type=data["action_type"],
            proposed_by=data["proposed_by"],
            status=data["status"],
            created_at=data["created_at"],
            reason=data.get("reason"),
            approval_id=data.get("approval_id"),
            applied_at=data.get("applied_at"),
            updated_at=data.get("updated_at"),
        )


class StateStore:
    """JSON file-based state store."""

    def __init__(
        self,
        path: Optional[Path] = None,
        dept_id: Optional[str] = None,
        institution_id: Optional[str] = None,
    ) -> None:
        """Initialize state store.

        Args:
            path: Path to state store file. If provided, takes precedence.
            dept_id: Department ID for multi-mode isolation. Ignored if path is set.
            institution_id: Institution UUID for namespacing. Ignored if path is set.
        """
        if path is not None:
            # Explicit path takes precedence (for testing or backward compat)
            self._path = path
        elif institution_id is not None:
            # Use institution-namespaced path
            self._path = get_state_store_path_for_institution(institution_id, dept_id)
        else:
            # Use legacy dept-aware path resolution (no institution)
            self._path = get_state_store_path(dept_id)

        self._dept_id = dept_id
        self._institution_id = institution_id
        self._data: Dict[str, Any] = {
            "expenses": {},
            "approval_index": {},
            "tickets": {},
            "content_reports": {},
            "chat_reports": {},
            "chat_blocks": {},
            "moderation_actions": {},
        }
        self._load()

    def _load(self) -> None:
        """Load state from file."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                # Ensure all keys exist for backward compat
                for key in ["tickets", "content_reports", "chat_reports", "chat_blocks", "moderation_actions"]:
                    if key not in self._data:
                        self._data[key] = {}
            except Exception:
                # Start fresh if file is corrupted
                self._data = {
                    "expenses": {},
                    "approval_index": {},
                    "tickets": {},
                    "content_reports": {},
                    "chat_reports": {},
                    "chat_blocks": {},
                    "moderation_actions": {},
                }

    def _save(self) -> None:
        """Save state to file."""
        # Ensure parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            raise RuntimeError(f"Failed to save state store: {e}")

    def create_expense(
        self,
        expense_id: str,
        approval_id: str,
        payload_sha256: str,
        payload_raw: bytes,
    ) -> ExpenseState:
        """Create a new expense in PENDING_APPROVAL status.
        
        Args:
            expense_id: The expense UUID.
            approval_id: The approval UUID.
            payload_sha256: SHA256 of the raw payload.
            payload_raw: Raw payload bytes.
            
        Returns:
            The created expense state.
        """
        now = datetime.now(timezone.utc).isoformat()
        
        expense = ExpenseState(
            expense_id=expense_id,
            status=STATUS_PENDING_APPROVAL,
            approval_id=approval_id,
            payload_sha256=payload_sha256,
            payload_raw=base64.b64encode(payload_raw).decode("utf-8"),
            created_at=now,
        )
        
        self._data["expenses"][expense_id] = expense.to_dict()
        self._data["approval_index"][approval_id] = expense_id
        self._save()
        
        return expense

    def get_expense(self, expense_id: str) -> Optional[ExpenseState]:
        """Get expense by ID."""
        data = self._data["expenses"].get(expense_id)
        if data:
            return ExpenseState.from_dict(data)
        return None

    def get_expense_by_approval_id(self, approval_id: str) -> Optional[ExpenseState]:
        """Get expense by approval ID."""
        expense_id = self._data["approval_index"].get(approval_id)
        if expense_id:
            return self.get_expense(expense_id)
        return None

    def get_expense_payload(self, expense_id: str) -> Optional[Dict[str, Any]]:
        """Get decoded expense payload."""
        expense = self.get_expense(expense_id)
        if expense:
            try:
                payload_bytes = base64.b64decode(expense.payload_raw)
                return json.loads(payload_bytes)
            except Exception:
                return None
        return None

    def update_expense_status(self, expense_id: str, status: str) -> Optional[ExpenseState]:
        """Update expense status.
        
        Args:
            expense_id: The expense ID.
            status: New status.
            
        Returns:
            Updated expense state, or None if not found.
        """
        if expense_id not in self._data["expenses"]:
            return None
        
        now = datetime.now(timezone.utc).isoformat()
        self._data["expenses"][expense_id]["status"] = status
        self._data["expenses"][expense_id]["updated_at"] = now
        self._save()
        
        return self.get_expense(expense_id)

    # Ticket methods (support department)

    def create_ticket(
        self,
        ticket_id: str,
        subject: str,
        description: str = "",
        payload_raw: bytes = b"",
    ) -> TicketState:
        """Create a new support ticket.

        Args:
            ticket_id: The ticket UUID.
            subject: Ticket subject line.
            description: Ticket description.
            payload_raw: Raw payload bytes.

        Returns:
            The created ticket state.
        """
        now = datetime.now(timezone.utc).isoformat()

        ticket = TicketState(
            ticket_id=ticket_id,
            subject=subject,
            status=TICKET_STATUS_OPEN,
            payload_raw=base64.b64encode(payload_raw).decode("utf-8"),
            created_at=now,
            description=description,
        )

        self._data["tickets"][ticket_id] = ticket.to_dict()
        self._save()

        return ticket

    def get_ticket(self, ticket_id: str) -> Optional[TicketState]:
        """Get ticket by ID."""
        data = self._data["tickets"].get(ticket_id)
        if data:
            return TicketState.from_dict(data)
        return None

    def update_ticket_status(self, ticket_id: str, status: str) -> Optional[TicketState]:
        """Update ticket status.

        Args:
            ticket_id: The ticket ID.
            status: New status.

        Returns:
            Updated ticket state, or None if not found.
        """
        if ticket_id not in self._data["tickets"]:
            return None

        now = datetime.now(timezone.utc).isoformat()
        self._data["tickets"][ticket_id]["status"] = status
        self._data["tickets"][ticket_id]["updated_at"] = now
        self._save()

        return self.get_ticket(ticket_id)

    # ContentReport methods (Bazari social moderation)

    def create_content_report(
        self,
        report_id: str,
        content_type: str,
        content_id: str,
        reporter_id: str,
        reason: str,
        description: str = "",
    ) -> ContentReportState:
        """Create a new content report.

        Args:
            report_id: The report UUID.
            content_type: Type of content (POST, COMMENT, PROFILE).
            content_id: ID of the reported content.
            reporter_id: ID of the user reporting.
            reason: Reason for the report.
            description: Optional additional description.

        Returns:
            The created content report state.
        """
        now = datetime.now(timezone.utc).isoformat()

        report = ContentReportState(
            report_id=report_id,
            content_type=content_type,
            content_id=content_id,
            reporter_id=reporter_id,
            reason=reason,
            status=CONTENT_REPORT_STATUS_PENDING,
            created_at=now,
            description=description if description else None,
        )

        self._data["content_reports"][report_id] = report.to_dict()
        self._save()

        return report

    def get_content_report(self, report_id: str) -> Optional[ContentReportState]:
        """Get content report by ID."""
        data = self._data["content_reports"].get(report_id)
        if data:
            return ContentReportState.from_dict(data)
        return None

    def list_content_reports(self) -> list:
        """List all content reports."""
        return [
            ContentReportState.from_dict(data)
            for data in self._data["content_reports"].values()
        ]

    def update_content_report_status(
        self, report_id: str, status: str
    ) -> Optional[ContentReportState]:
        """Update content report status."""
        if report_id not in self._data["content_reports"]:
            return None

        now = datetime.now(timezone.utc).isoformat()
        self._data["content_reports"][report_id]["status"] = status
        self._data["content_reports"][report_id]["updated_at"] = now
        self._save()

        return self.get_content_report(report_id)

    # ChatReport methods (Bazari chat moderation)

    def create_chat_report(
        self,
        report_id: str,
        message_id: str,
        thread_id: str,
        reporter_id: str,
        reason: str,
        description: str = "",
    ) -> ChatReportState:
        """Create a new chat report.

        Args:
            report_id: The report UUID.
            message_id: ID of the reported message.
            thread_id: ID of the thread containing the message.
            reporter_id: ID of the user reporting.
            reason: Reason for the report.
            description: Optional additional description.

        Returns:
            The created chat report state.
        """
        now = datetime.now(timezone.utc).isoformat()

        report = ChatReportState(
            report_id=report_id,
            message_id=message_id,
            thread_id=thread_id,
            reporter_id=reporter_id,
            reason=reason,
            status=CHAT_REPORT_STATUS_PENDING,
            created_at=now,
            description=description if description else None,
        )

        self._data["chat_reports"][report_id] = report.to_dict()
        self._save()

        return report

    def get_chat_report(self, report_id: str) -> Optional[ChatReportState]:
        """Get chat report by ID."""
        data = self._data["chat_reports"].get(report_id)
        if data:
            return ChatReportState.from_dict(data)
        return None

    def list_chat_reports(self) -> list:
        """List all chat reports."""
        return [
            ChatReportState.from_dict(data)
            for data in self._data["chat_reports"].values()
        ]

    def update_chat_report_status(
        self, report_id: str, status: str
    ) -> Optional[ChatReportState]:
        """Update chat report status."""
        if report_id not in self._data["chat_reports"]:
            return None

        now = datetime.now(timezone.utc).isoformat()
        self._data["chat_reports"][report_id]["status"] = status
        self._data["chat_reports"][report_id]["updated_at"] = now
        self._save()

        return self.get_chat_report(report_id)

    # ChatBlock methods (Bazari chat blocking)

    def create_chat_block(
        self,
        block_id: str,
        blocker_profile_id: str,
        blocked_profile_id: str,
    ) -> ChatBlockState:
        """Create a new chat block.

        Args:
            block_id: The block UUID.
            blocker_profile_id: ID of the profile doing the blocking.
            blocked_profile_id: ID of the profile being blocked.

        Returns:
            The created chat block state.
        """
        now = datetime.now(timezone.utc).isoformat()

        block = ChatBlockState(
            block_id=block_id,
            blocker_profile_id=blocker_profile_id,
            blocked_profile_id=blocked_profile_id,
            created_at=now,
        )

        self._data["chat_blocks"][block_id] = block.to_dict()
        self._save()

        return block

    def get_chat_block(self, block_id: str) -> Optional[ChatBlockState]:
        """Get chat block by ID."""
        data = self._data["chat_blocks"].get(block_id)
        if data:
            return ChatBlockState.from_dict(data)
        return None

    def delete_chat_block(self, block_id: str) -> bool:
        """Delete a chat block.

        Args:
            block_id: The block UUID.

        Returns:
            True if deleted, False if not found.
        """
        if block_id not in self._data["chat_blocks"]:
            return False

        del self._data["chat_blocks"][block_id]
        self._save()
        return True

    def list_chat_blocks(self) -> list:
        """List all chat blocks."""
        return [
            ChatBlockState.from_dict(data)
            for data in self._data["chat_blocks"].values()
        ]

    # ModerationAction methods (Bazari moderation actions)

    def create_moderation_action(
        self,
        action_id: str,
        target_type: str,
        target_id: str,
        action_type: str,
        proposed_by: str,
        report_id: Optional[str] = None,
        reason: Optional[str] = None,
        approval_id: Optional[str] = None,
    ) -> ModerationActionState:
        """Create a new moderation action proposal.

        Args:
            action_id: The action UUID.
            target_type: Type of target (USER, POST, COMMENT, PROFILE, MESSAGE).
            target_id: ID of the target.
            action_type: Type of action (WARN, HIDE, REMOVE, BAN, MUTE, SHADOWBAN).
            proposed_by: ID of the moderator proposing.
            report_id: Optional linked report ID.
            reason: Optional reason for the action.
            approval_id: Optional approval ID if requiring approval.

        Returns:
            The created moderation action state.
        """
        now = datetime.now(timezone.utc).isoformat()

        status = MOD_ACTION_STATUS_PENDING_APPROVAL if approval_id else MOD_ACTION_STATUS_PROPOSED

        action = ModerationActionState(
            action_id=action_id,
            report_id=report_id,
            target_type=target_type,
            target_id=target_id,
            action_type=action_type,
            proposed_by=proposed_by,
            status=status,
            created_at=now,
            reason=reason,
            approval_id=approval_id,
        )

        self._data["moderation_actions"][action_id] = action.to_dict()
        self._save()

        return action

    def get_moderation_action(self, action_id: str) -> Optional[ModerationActionState]:
        """Get moderation action by ID."""
        data = self._data["moderation_actions"].get(action_id)
        if data:
            return ModerationActionState.from_dict(data)
        return None

    def list_moderation_actions(self) -> list:
        """List all moderation actions."""
        return [
            ModerationActionState.from_dict(data)
            for data in self._data["moderation_actions"].values()
        ]

    def update_moderation_action_status(
        self, action_id: str, status: str, applied_at: Optional[str] = None
    ) -> Optional[ModerationActionState]:
        """Update moderation action status.

        Args:
            action_id: The action ID.
            status: New status.
            applied_at: Optional timestamp when applied.

        Returns:
            Updated action state, or None if not found.
        """
        if action_id not in self._data["moderation_actions"]:
            return None

        now = datetime.now(timezone.utc).isoformat()
        self._data["moderation_actions"][action_id]["status"] = status
        self._data["moderation_actions"][action_id]["updated_at"] = now
        if applied_at:
            self._data["moderation_actions"][action_id]["applied_at"] = applied_at
        self._save()

        return self.get_moderation_action(action_id)

    def reset(self) -> None:
        """Reset state store (for testing)."""
        self._data = {
            "expenses": {},
            "approval_index": {},
            "tickets": {},
            "content_reports": {},
            "chat_reports": {},
            "chat_blocks": {},
            "moderation_actions": {},
        }
        if self._path.exists():
            self._path.unlink()


# Global state stores: (institution_id, dept_id) key for namespaced stores
# Key format: (institution_id, dept_id) where either can be None
_state_stores: Dict[Tuple[Optional[str], Optional[str]], StateStore] = {}
# Default store reference for backward compatibility (no institution context)
_default_store: Optional[StateStore] = None


def init_state_store(path: Optional[Path] = None) -> StateStore:
    """Initialize the default (single-mode) state store."""
    global _default_store
    _default_store = StateStore(path)
    _state_stores[(None, None)] = _default_store
    return _default_store


def get_state_store(
    dept_id: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> Optional[StateStore]:
    """Get state store for given institution and department.

    Args:
        dept_id: Department ID, or None for single-mode default store.
        institution_id: Institution UUID for namespacing, or None for legacy.

    Returns:
        StateStore instance for the (institution, department), or None if not initialized.
    """
    key = (institution_id, dept_id)

    # Legacy behavior: if no institution, use default store for dept_id=None
    if institution_id is None and dept_id is None:
        return _default_store

    # Get or create store for this (institution, dept) pair
    if key not in _state_stores:
        _state_stores[key] = StateStore(dept_id=dept_id, institution_id=institution_id)

    return _state_stores[key]


def set_state_store(
    store: Optional[StateStore],
    dept_id: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> None:
    """Set state store for given institution and department (for testing).

    Args:
        store: StateStore instance, or None to clear.
        dept_id: Department ID, or None for default store.
        institution_id: Institution UUID for namespacing, or None for legacy.
    """
    global _default_store

    key = (institution_id, dept_id)

    if institution_id is None and dept_id is None:
        _default_store = store
        if store is not None:
            _state_stores[key] = store
        elif key in _state_stores:
            del _state_stores[key]
    else:
        if store is not None:
            _state_stores[key] = store
        elif key in _state_stores:
            del _state_stores[key]


def reset_all_state_stores() -> None:
    """Reset all state stores (for testing)."""
    global _default_store, _state_stores
    _default_store = None
    _state_stores = {}
