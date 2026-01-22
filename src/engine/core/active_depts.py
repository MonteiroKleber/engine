"""Active departments management for multi-dept institutions.

This module implements the canonical model for tracking which departments
are active within an institution. It provides:

- Storage: active_depts.json per institution
- Fallback: If file doesn't exist, all bundle depts are considered active
- Events: DEPT_ACTIVATED, DEPT_DEACTIVATED emitted to ledger
- Determinism: Array always sorted alphabetically by dept_id
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from engine.core.data_root import get_institution_root
from engine.core.errors import (
    DEPT_NOT_INSTALLED,
    DEPT_NOT_ACTIVE,
    DEPT_ALREADY_ACTIVE,
    DEPT_ALREADY_INACTIVE,
    CANNOT_DEACTIVATE_LAST_DEPT,
    ACTIVE_DEPTS_UNAVAILABLE,
)


# Schema version for active_depts.json
ACTIVE_DEPTS_SCHEMA_VERSION = "1.0"


@dataclass
class ActiveDeptEntry:
    """Entry for an active department."""

    dept_id: str
    activated_at: str
    activated_by: str
    source_bundle: str
    pinned_contract_sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "dept_id": self.dept_id,
            "activated_at": self.activated_at,
            "activated_by": self.activated_by,
            "source_bundle": self.source_bundle,
            "pinned_contract_sha256": self.pinned_contract_sha256,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActiveDeptEntry":
        """Create from dictionary."""
        return cls(
            dept_id=data["dept_id"],
            activated_at=data["activated_at"],
            activated_by=data["activated_by"],
            source_bundle=data["source_bundle"],
            pinned_contract_sha256=data.get("pinned_contract_sha256"),
        )


@dataclass
class ActiveDeptsState:
    """State of active departments for an institution."""

    schema_version: str
    updated_at: str
    updated_by: str
    active_depts: List[ActiveDeptEntry]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        # Always sort by dept_id for determinism
        sorted_depts = sorted(self.active_depts, key=lambda x: x.dept_id)
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
            "active_depts": [d.to_dict() for d in sorted_depts],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActiveDeptsState":
        """Create from dictionary."""
        return cls(
            schema_version=data.get("schema_version", ACTIVE_DEPTS_SCHEMA_VERSION),
            updated_at=data.get("updated_at", ""),
            updated_by=data.get("updated_by", ""),
            active_depts=[
                ActiveDeptEntry.from_dict(d) for d in data.get("active_depts", [])
            ],
        )


def get_active_depts_path(institution_id: str) -> Path:
    """Get path to active_depts.json for institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to active_depts.json file.
    """
    return get_institution_root(institution_id) / "active_depts.json"


def _get_installed_depts_from_bundle(institution_id: str) -> List[str]:
    """Get list of departments installed in the current bundle.

    Args:
        institution_id: Institution UUID.

    Returns:
        List of dept_ids from the bundle. Empty list if single-mode or error.
    """
    from engine.loader.load_bundle import get_bundle_context

    try:
        bundle_ctx = get_bundle_context()
        if bundle_ctx is None:
            return []

        if bundle_ctx.mode == "multi":
            return sorted(bundle_ctx.departments.keys())
        else:
            # Single mode - return default dept from config
            from engine.core.institution_config import get_effective_config

            config = get_effective_config(institution_id)
            return [config.defaults.default_dept]
    except Exception:
        return []


def _get_current_bundle_name(institution_id: str) -> str:
    """Get name of current bundle for institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Bundle name or "unknown".
    """
    bundles_path = get_institution_root(institution_id) / "bundles"
    current_link = bundles_path / "CURRENT"

    if current_link.is_symlink():
        return current_link.resolve().name
    elif current_link.exists():
        return current_link.name

    return "unknown"


def get_active_depts_state(institution_id: str) -> Optional[ActiveDeptsState]:
    """Get active departments state from file.

    Args:
        institution_id: Institution UUID.

    Returns:
        ActiveDeptsState if file exists, None otherwise.
    """
    path = get_active_depts_path(institution_id)

    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ActiveDeptsState.from_dict(data)
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def get_active_depts(institution_id: str) -> List[str]:
    """Get list of active department IDs for institution.

    If active_depts.json doesn't exist, falls back to all installed depts
    from the bundle (backward compatibility).

    Args:
        institution_id: Institution UUID.

    Returns:
        Sorted list of active dept_ids.
    """
    state = get_active_depts_state(institution_id)

    if state is not None:
        return sorted([d.dept_id for d in state.active_depts])

    # Fallback: all installed depts are active
    return _get_installed_depts_from_bundle(institution_id)


def get_installed_depts(institution_id: str) -> List[str]:
    """Get list of installed department IDs from bundle.

    Args:
        institution_id: Institution UUID.

    Returns:
        Sorted list of installed dept_ids.
    """
    return _get_installed_depts_from_bundle(institution_id)


def is_dept_active(institution_id: str, dept_id: str) -> bool:
    """Check if a department is active.

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID to check.

    Returns:
        True if dept is active, False otherwise.
    """
    active = get_active_depts(institution_id)
    return dept_id in active


def is_dept_installed(institution_id: str, dept_id: str) -> bool:
    """Check if a department is installed in the bundle.

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID to check.

    Returns:
        True if dept is installed, False otherwise.
    """
    installed = get_installed_depts(institution_id)
    return dept_id in installed


def _save_active_depts_state(
    institution_id: str, state: ActiveDeptsState
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Save active departments state to file.

    Args:
        institution_id: Institution UUID.
        state: State to save.

    Returns:
        Tuple of (success, error_code, error_message).
    """
    path = get_active_depts_path(institution_id)

    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically
        data = state.to_dict()
        json_bytes = json.dumps(data, indent=2).encode("utf-8")

        with open(path, "wb") as f:
            f.write(json_bytes)

        return True, None, None
    except OSError as e:
        return False, ACTIVE_DEPTS_UNAVAILABLE, f"Failed to save active_depts: {e}"


def _emit_dept_event(
    institution_id: str,
    event_type: str,
    dept_id: str,
    actor_id: str,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit department event to ledger.

    Args:
        institution_id: Institution UUID.
        event_type: Event type (DEPT_ACTIVATED, DEPT_DEACTIVATED, etc.)
        dept_id: Department ID.
        actor_id: Actor who performed the action.
        extra_payload: Additional payload fields.
    """
    from engine.core.ledger import append_event

    payload = {"dept_id": dept_id}
    if extra_payload:
        payload.update(extra_payload)

    try:
        append_event(
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
            institution_id=institution_id,
        )
    except Exception:
        # Ledger write failure is logged but not fatal
        pass


def activate_dept(
    institution_id: str,
    dept_id: str,
    actor_id: str,
    pinned_contract_sha256: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Activate a department for an institution.

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID to activate.
        actor_id: Actor performing the activation.
        pinned_contract_sha256: Optional contract hash to pin.

    Returns:
        Tuple of (success, error_code, error_message).
    """
    # Check if dept is installed
    if not is_dept_installed(institution_id, dept_id):
        return False, DEPT_NOT_INSTALLED, f"Department '{dept_id}' is not installed in bundle"

    # Get current state or create new
    state = get_active_depts_state(institution_id)
    now = datetime.now(timezone.utc).isoformat()
    bundle_name = _get_current_bundle_name(institution_id)

    if state is None:
        # First activation - create state with all installed depts
        # This is the migration path from "no file" to "explicit file"
        installed = get_installed_depts(institution_id)
        entries = []
        for d in installed:
            entries.append(
                ActiveDeptEntry(
                    dept_id=d,
                    activated_at=now,
                    activated_by=actor_id,
                    source_bundle=bundle_name,
                    pinned_contract_sha256=None,
                )
            )
        state = ActiveDeptsState(
            schema_version=ACTIVE_DEPTS_SCHEMA_VERSION,
            updated_at=now,
            updated_by=actor_id,
            active_depts=entries,
        )

        # If dept was already in installed, it's now active (no error)
        # Update its pin if provided
        for entry in state.active_depts:
            if entry.dept_id == dept_id:
                entry.pinned_contract_sha256 = pinned_contract_sha256
                break

        success, error_code, error_msg = _save_active_depts_state(institution_id, state)
        if success:
            _emit_dept_event(
                institution_id,
                "DEPT_ACTIVATED",
                dept_id,
                actor_id,
                {
                    "source_bundle": bundle_name,
                    "pinned_contract_sha256": pinned_contract_sha256,
                    "note": "Initial activation (migration from implicit state)",
                },
            )
        return success, error_code, error_msg

    # Check if already active
    active_ids = [d.dept_id for d in state.active_depts]
    if dept_id in active_ids:
        return False, DEPT_ALREADY_ACTIVE, f"Department '{dept_id}' is already active"

    # Add new entry
    new_entry = ActiveDeptEntry(
        dept_id=dept_id,
        activated_at=now,
        activated_by=actor_id,
        source_bundle=bundle_name,
        pinned_contract_sha256=pinned_contract_sha256,
    )
    state.active_depts.append(new_entry)
    state.updated_at = now
    state.updated_by = actor_id

    success, error_code, error_msg = _save_active_depts_state(institution_id, state)
    if success:
        _emit_dept_event(
            institution_id,
            "DEPT_ACTIVATED",
            dept_id,
            actor_id,
            {
                "source_bundle": bundle_name,
                "pinned_contract_sha256": pinned_contract_sha256,
            },
        )
    return success, error_code, error_msg


def deactivate_dept(
    institution_id: str,
    dept_id: str,
    actor_id: str,
    reason: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Deactivate a department for an institution.

    Args:
        institution_id: Institution UUID.
        dept_id: Department ID to deactivate.
        actor_id: Actor performing the deactivation.
        reason: Optional reason for deactivation.

    Returns:
        Tuple of (success, error_code, error_message).
    """
    # Get current state
    state = get_active_depts_state(institution_id)
    now = datetime.now(timezone.utc).isoformat()
    bundle_name = _get_current_bundle_name(institution_id)

    if state is None:
        # No explicit state - need to create it first
        # All installed depts are implicitly active
        installed = get_installed_depts(institution_id)

        if dept_id not in installed:
            return False, DEPT_NOT_ACTIVE, f"Department '{dept_id}' is not active"

        # Can't deactivate if it's the only dept
        if len(installed) <= 1:
            return False, CANNOT_DEACTIVATE_LAST_DEPT, "Cannot deactivate the last active department"

        # Create state with all depts except the one being deactivated
        entries = []
        for d in installed:
            if d != dept_id:
                entries.append(
                    ActiveDeptEntry(
                        dept_id=d,
                        activated_at=now,
                        activated_by=actor_id,
                        source_bundle=bundle_name,
                        pinned_contract_sha256=None,
                    )
                )

        state = ActiveDeptsState(
            schema_version=ACTIVE_DEPTS_SCHEMA_VERSION,
            updated_at=now,
            updated_by=actor_id,
            active_depts=entries,
        )

        success, error_code, error_msg = _save_active_depts_state(institution_id, state)
        if success:
            _emit_dept_event(
                institution_id,
                "DEPT_DEACTIVATED",
                dept_id,
                actor_id,
                {"reason": reason or "Manual deactivation"},
            )
        return success, error_code, error_msg

    # Check if dept is active
    active_ids = [d.dept_id for d in state.active_depts]
    if dept_id not in active_ids:
        return False, DEPT_ALREADY_INACTIVE, f"Department '{dept_id}' is not active"

    # Can't deactivate the last dept
    if len(state.active_depts) <= 1:
        return False, CANNOT_DEACTIVATE_LAST_DEPT, "Cannot deactivate the last active department"

    # Remove entry
    state.active_depts = [d for d in state.active_depts if d.dept_id != dept_id]
    state.updated_at = now
    state.updated_by = actor_id

    success, error_code, error_msg = _save_active_depts_state(institution_id, state)
    if success:
        _emit_dept_event(
            institution_id,
            "DEPT_DEACTIVATED",
            dept_id,
            actor_id,
            {"reason": reason or "Manual deactivation"},
        )
    return success, error_code, error_msg


def get_depts_summary(institution_id: str) -> Dict[str, List[str]]:
    """Get summary of departments for an institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Dictionary with installed, active, and inactive dept lists.
    """
    installed = set(get_installed_depts(institution_id))
    active = set(get_active_depts(institution_id))
    inactive = installed - active

    return {
        "installed": sorted(installed),
        "active": sorted(active),
        "inactive": sorted(inactive),
    }


# Cache for active depts (per institution)
_active_depts_cache: Dict[str, List[str]] = {}


def get_cached_active_depts(institution_id: str) -> List[str]:
    """Get active departments with caching.

    Args:
        institution_id: Institution UUID.

    Returns:
        List of active dept_ids.
    """
    if institution_id not in _active_depts_cache:
        _active_depts_cache[institution_id] = get_active_depts(institution_id)
    return _active_depts_cache[institution_id]


def invalidate_active_depts_cache(institution_id: str) -> None:
    """Invalidate cache for institution.

    Args:
        institution_id: Institution UUID.
    """
    _active_depts_cache.pop(institution_id, None)


def reset_active_depts_cache() -> None:
    """Reset entire cache (for testing)."""
    _active_depts_cache.clear()
