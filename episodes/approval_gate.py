"""Approval Gate - Block release without valid approval.

This module provides the approval gate that ensures no release
can proceed without explicit human approval.

Key rules:
- Every release requires an approval with decision "approve"
- Approval must be in approvals/approval.json within the episode
- approval.episode_id must match the episode's episode_id
- Gate result is deterministic: APPROVED, BLOCKED, or INVALID

Error prefixes:
- GOVERNANCE: for gate-level errors
- SCHEMA: for validation errors (delegated to approval module)

blocked_reason values for runlog:
- APPROVAL_REQUIRED: No approval found
- APPROVAL_INVALID: Approval exists but is invalid or rejected
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from approvals.approval_v1 import (
    validate_approval,
    is_approved as approval_is_approved,
    is_rejected as approval_is_rejected,
    ApprovalValidationError,
)


# =============================================================================
# Constants
# =============================================================================


class GateResult(str, Enum):
    """Result of the approval gate check."""

    APPROVED = "approved"  # Valid approval with decision "approve"
    BLOCKED = "blocked"  # No approval found
    REJECTED = "rejected"  # Approval with decision "reject"
    INVALID = "invalid"  # Approval is invalid or episode_id mismatch


@dataclass
class GateCheckResult:
    """Result of an approval gate check."""

    result: GateResult
    episode_id: str
    has_approval: bool
    decision: Optional[str]
    errors: List[str]
    blocked_reason: Optional[str]  # For runlog integration

    @property
    def can_proceed(self) -> bool:
        """Check if the release can proceed."""
        return self.result == GateResult.APPROVED


# =============================================================================
# Exceptions
# =============================================================================


class ApprovalGateError(Exception):
    """Exception raised when approval gate check fails.

    Error messages are prefixed with "GOVERNANCE: " following project conventions.
    """

    def __init__(self, message: str, error_code: str = "APPROVAL_REQUIRED"):
        self.message = message
        self.error_code = error_code
        super().__init__(f"GOVERNANCE: {message}")


# =============================================================================
# Approval Gate
# =============================================================================


class ApprovalGate:
    """Gate that ensures releases require human approval.

    The gate checks:
    1. Episode exists and has approval.json in approvals/
    2. Approval is valid against approval.v1 schema
    3. approval.episode_id matches the episode
    4. decision is "approve"
    """

    def __init__(self, episode_store):
        """Initialize the approval gate.

        Args:
            episode_store: EpisodeStore instance
        """
        self.episode_store = episode_store

    def check_episode(self, episode_id: str) -> GateCheckResult:
        """Check if an episode is approved for release.

        Args:
            episode_id: Episode identifier

        Returns:
            GateCheckResult with detailed result
        """
        errors = []

        # Check episode exists
        if not self.episode_store.exists(episode_id):
            return GateCheckResult(
                result=GateResult.INVALID,
                episode_id=episode_id,
                has_approval=False,
                decision=None,
                errors=[f"Episode not found: {episode_id}"],
                blocked_reason="APPROVAL_INVALID",
            )

        # Get approval from episode
        try:
            approval = self.episode_store.get_approval(episode_id)
        except Exception as e:
            return GateCheckResult(
                result=GateResult.INVALID,
                episode_id=episode_id,
                has_approval=False,
                decision=None,
                errors=[f"Error reading approval: {e}"],
                blocked_reason="APPROVAL_INVALID",
            )

        # No approval found
        if approval is None:
            return GateCheckResult(
                result=GateResult.BLOCKED,
                episode_id=episode_id,
                has_approval=False,
                decision=None,
                errors=["No approval found - approval required before release"],
                blocked_reason="APPROVAL_REQUIRED",
            )

        # Validate approval schema
        try:
            validate_approval(approval)
        except ApprovalValidationError as e:
            return GateCheckResult(
                result=GateResult.INVALID,
                episode_id=episode_id,
                has_approval=True,
                decision=approval.get("decision"),
                errors=[f"Invalid approval: {e.message}"],
                blocked_reason="APPROVAL_INVALID",
            )

        # Check episode_id matches
        approval_episode_id = approval.get("episode_id")
        if approval_episode_id != episode_id:
            return GateCheckResult(
                result=GateResult.INVALID,
                episode_id=episode_id,
                has_approval=True,
                decision=approval.get("decision"),
                errors=[
                    f"Approval episode_id mismatch: expected {episode_id}, "
                    f"got {approval_episode_id}"
                ],
                blocked_reason="APPROVAL_INVALID",
            )

        # Check decision
        decision = approval.get("decision")

        if approval_is_rejected(approval):
            approver_name = approval.get("approver", {}).get("display_name", "unknown")
            reason = approval.get("reason", "no reason provided")
            return GateCheckResult(
                result=GateResult.REJECTED,
                episode_id=episode_id,
                has_approval=True,
                decision=decision,
                errors=[f"Rejected by {approver_name}: {reason}"],
                blocked_reason="APPROVAL_INVALID",
            )

        if approval_is_approved(approval):
            return GateCheckResult(
                result=GateResult.APPROVED,
                episode_id=episode_id,
                has_approval=True,
                decision=decision,
                errors=[],
                blocked_reason=None,
            )

        # Should not reach here
        return GateCheckResult(
            result=GateResult.INVALID,
            episode_id=episode_id,
            has_approval=True,
            decision=decision,
            errors=["Unknown decision state"],
            blocked_reason="APPROVAL_INVALID",
        )

    def require_approval(self, episode_id: str) -> None:
        """Require that an episode is approved before proceeding.

        Args:
            episode_id: Episode identifier

        Raises:
            ApprovalGateError: If approval is missing or invalid
        """
        result = self.check_episode(episode_id)

        if not result.can_proceed:
            error_msg = "; ".join(result.errors) if result.errors else "Approval required"
            raise ApprovalGateError(
                f"Release blocked for episode {episode_id}: {error_msg}",
                error_code=result.blocked_reason or "APPROVAL_REQUIRED",
            )


# =============================================================================
# Standalone Gate Check
# =============================================================================


def check_release_approval(
    base_path: Path,
    episode_id: str,
) -> GateCheckResult:
    """Check if a release is approved.

    Convenience function for standalone gate checks.

    Args:
        base_path: Base path for .engine directory
        episode_id: Episode identifier

    Returns:
        GateCheckResult with detailed result
    """
    from .episode_store import EpisodeStore

    store = EpisodeStore(base_path)
    gate = ApprovalGate(store)
    return gate.check_episode(episode_id)
