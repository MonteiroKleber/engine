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
        }
        self._load()

    def _load(self) -> None:
        """Load state from file."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                # Start fresh if file is corrupted
                self._data = {"expenses": {}, "approval_index": {}}

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

    def reset(self) -> None:
        """Reset state store (for testing)."""
        self._data = {"expenses": {}, "approval_index": {}}
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
