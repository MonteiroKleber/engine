"""Data models for Legacy Bridge Write-Mode.

This module defines the core data structures for governed legacy writes:
- LegacyWriteAction: Represents a write action to be applied to legacy system
- ActionStatus: Status of a write action in the outbox

Etapa 4.3: Legacy Bridge Write-Mode (Governado)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ActionStatus(str, Enum):
    """Status of a legacy write action."""

    PENDING = "pending"  # Created but not yet allowed
    PENDING_APPROVAL = "pending_approval"  # Awaiting formal approval decision
    ENQUEUED = "enqueued"  # Allowed and written to outbox
    ACKED = "acked"  # Acknowledged by external applier (optional)
    FAILED = "failed"  # Failed during processing
    DENIED = "denied"  # Denied by governance gates


# Action type schemas for validation
ACTION_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "increase_limit": {
        "type": "object",
        "required": ["customer_id", "new_limit"],
        "properties": {
            "customer_id": {"type": "string"},
            "new_limit": {"type": "number", "minimum": 0},
            "reason": {"type": "string"},
        },
    },
}


def compute_intent_sha256(params: Dict[str, Any]) -> str:
    """Compute SHA256 hash of params in canonical JSON format.

    Args:
        params: Action parameters.

    Returns:
        Hex-encoded SHA256 hash.
    """
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_action_params(action_type: str, params: Dict[str, Any]) -> List[str]:
    """Validate action params against schema.

    Args:
        action_type: Type of action.
        params: Parameters to validate.

    Returns:
        List of validation errors (empty if valid).
    """
    schema = ACTION_SCHEMAS.get(action_type)
    if not schema:
        return [f"Unknown action type: {action_type}"]

    errors: List[str] = []

    # Check required fields
    required = schema.get("required", [])
    for field_name in required:
        if field_name not in params:
            errors.append(f"Missing required field: {field_name}")

    # Check property types
    properties = schema.get("properties", {})
    for field_name, value in params.items():
        if field_name not in properties:
            continue  # Extra fields are allowed

        prop_schema = properties[field_name]
        expected_type = prop_schema.get("type")

        # Type checking
        if expected_type == "string" and not isinstance(value, str):
            errors.append(f"Field '{field_name}' must be string")
        elif expected_type == "number" and not isinstance(value, (int, float)):
            errors.append(f"Field '{field_name}' must be number")

        # Range checking for numbers
        if isinstance(value, (int, float)):
            minimum = prop_schema.get("minimum")
            if minimum is not None and value < minimum:
                errors.append(f"Field '{field_name}' must be >= {minimum}")

    return errors


@dataclass
class LegacyWriteAction:
    """Governed write action for legacy system.

    A LegacyWriteAction represents a command to be applied to a legacy
    system, with full governance trail (mandates, policies, approvals).
    """

    # Identification
    action_id: str  # UUID v4
    action_type: str  # e.g., "increase_limit"

    # Parameters
    params: Dict[str, Any] = field(default_factory=dict)

    # Integrity
    intent_sha256: str = ""  # Hash of canonical params JSON

    # Audit
    requested_by: str = ""  # Actor ID who requested
    approved_by: Optional[str] = None  # Actor who approved (if approval flow)
    mandate_id: Optional[str] = None  # Mandate that allowed action

    # Timestamps (ISO8601 UTC)
    created_at: str = ""
    enqueued_at: Optional[str] = None
    acked_at: Optional[str] = None

    # Tracking
    case_id: str = ""  # = action_id for full trail
    institution_id: str = ""
    dept_id: Optional[str] = None

    # Status
    status: str = ActionStatus.PENDING.value

    # Approval tracking (GAP 3)
    approval_id: Optional[str] = None  # Approval ID if pending approval

    # Governance results
    denied_by: Optional[str] = None  # MANDATE | AUTONOMY | POLICY
    denied_reason: Optional[str] = None

    def __post_init__(self) -> None:
        """Compute intent_sha256 if not set."""
        if not self.intent_sha256 and self.params:
            self.intent_sha256 = compute_intent_sha256(self.params)
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.case_id:
            self.case_id = self.action_id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "params": self.params,
            "intent_sha256": self.intent_sha256,
            "requested_by": self.requested_by,
            "approved_by": self.approved_by,
            "mandate_id": self.mandate_id,
            "created_at": self.created_at,
            "enqueued_at": self.enqueued_at,
            "acked_at": self.acked_at,
            "case_id": self.case_id,
            "institution_id": self.institution_id,
            "dept_id": self.dept_id,
            "status": self.status,
            "approval_id": self.approval_id,
            "denied_by": self.denied_by,
            "denied_reason": self.denied_reason,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LegacyWriteAction":
        """Create from storage dict."""
        return cls(
            action_id=d.get("action_id", ""),
            action_type=d.get("action_type", ""),
            params=d.get("params", {}),
            intent_sha256=d.get("intent_sha256", ""),
            requested_by=d.get("requested_by", ""),
            approved_by=d.get("approved_by"),
            mandate_id=d.get("mandate_id"),
            created_at=d.get("created_at", ""),
            enqueued_at=d.get("enqueued_at"),
            acked_at=d.get("acked_at"),
            case_id=d.get("case_id", ""),
            institution_id=d.get("institution_id", ""),
            dept_id=d.get("dept_id"),
            status=d.get("status", ActionStatus.PENDING.value),
            approval_id=d.get("approval_id"),
            denied_by=d.get("denied_by"),
            denied_reason=d.get("denied_reason"),
        )

    def to_outbox_dict(self) -> Dict[str, Any]:
        """Convert to outbox file format (deterministic JSON).

        Returns:
            Dict suitable for outbox file (external applier).
        """
        return {
            "schema_version": "1.0",
            "action_id": self.action_id,
            "action_type": self.action_type,
            "params": self.params,
            "intent_sha256": self.intent_sha256,
            "requested_by": self.requested_by,
            "approved_by": self.approved_by,
            "mandate_id": self.mandate_id,
            "created_at": self.created_at,
            "case_id": self.case_id,
        }
