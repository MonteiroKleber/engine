"""Approval v1 - Human approval contract for enterprise governance.

This module provides validation and canonicalization for approval records.
Every release requires explicit human approval - no invisible updates.

Key rules:
- schema_version is fixed at "approval.v1"
- decision is restricted enum (approve/reject)
- reason is mandatory (enterprise audit trail)
- signatures list must exist (can be empty)
- volatile block does NOT affect hash/canonicalization

Schema Version: approval.v1
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema


# =============================================================================
# Constants
# =============================================================================

APPROVAL_SCHEMA_VERSION = "approval.v1"

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "approval.v1.json"
_APPROVAL_SCHEMA: Optional[dict] = None


# =============================================================================
# Schema Loading
# =============================================================================


def _get_schema() -> dict:
    """Load and cache the approval schema."""
    global _APPROVAL_SCHEMA
    if _APPROVAL_SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _APPROVAL_SCHEMA = json.load(f)
    return _APPROVAL_SCHEMA


# =============================================================================
# Exceptions
# =============================================================================


class ApprovalValidationError(Exception):
    """Exception raised when approval validation fails.

    Error messages are prefixed with "SCHEMA: " following project conventions.
    """

    def __init__(self, message: str, path: str = ""):
        self.message = message
        self.path = path
        super().__init__(f"SCHEMA: {path}: {message}" if path else f"SCHEMA: {message}")


# =============================================================================
# Validation
# =============================================================================


def validate_approval(approval: dict) -> None:
    """Validate an approval against the schema.

    Args:
        approval: The approval dict to validate

    Raises:
        ApprovalValidationError: If validation fails (prefixed with "SCHEMA: ...")
    """
    schema = _get_schema()

    # JSON Schema validation
    try:
        jsonschema.validate(instance=approval, schema=schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else ""
        raise ApprovalValidationError(e.message, path)

    # Additional semantic validations

    # 1. Check for duplicate signature schemes with same public_key_id
    signatures = approval.get("signatures", [])
    seen_sigs = set()
    for sig in signatures:
        key = (sig.get("scheme"), sig.get("public_key_id"))
        if key in seen_sigs:
            raise ApprovalValidationError(
                f"Duplicate signature: scheme={key[0]}, public_key_id={key[1]}",
                "signatures"
            )
        seen_sigs.add(key)

    # 2. If artifact_hashes exists, check for duplicates
    scope = approval.get("scope", {})
    artifact_hashes = scope.get("artifact_hashes", [])
    if len(artifact_hashes) != len(set(artifact_hashes)):
        duplicates = [h for h in artifact_hashes if artifact_hashes.count(h) > 1]
        raise ApprovalValidationError(
            f"Duplicate artifact_hash: {duplicates[0]}",
            "scope.artifact_hashes"
        )


# =============================================================================
# Canonicalization
# =============================================================================


def _sort_signatures(signatures: List[dict]) -> List[dict]:
    """Sort signatures by (scheme, public_key_id).

    Args:
        signatures: List of signature dicts

    Returns:
        Sorted list of signatures
    """
    return sorted(
        signatures,
        key=lambda s: (s.get("scheme", ""), s.get("public_key_id") or "")
    )


def _sort_artifact_hashes(hashes: List[str]) -> List[str]:
    """Sort artifact hashes alphabetically.

    Args:
        hashes: List of hash strings

    Returns:
        Sorted list of hashes
    """
    return sorted(hashes)


def canonicalize_approval(approval: dict) -> dict:
    """Canonicalize an approval for deterministic comparison/hashing.

    Applies stable ordering to:
    - signatures: sorted by (scheme, public_key_id)
    - artifact_hashes: sorted alphabetically

    Does NOT modify values, only ordering.
    Excludes volatile block from canonicalization considerations.

    Args:
        approval: The approval dict to canonicalize

    Returns:
        A new dict with canonical ordering (original is not mutated)
    """
    result = deepcopy(approval)

    # Sort signatures
    if "signatures" in result:
        result["signatures"] = _sort_signatures(result["signatures"])

    # Sort artifact_hashes in scope
    if "scope" in result and "artifact_hashes" in result["scope"]:
        result["scope"]["artifact_hashes"] = _sort_artifact_hashes(
            result["scope"]["artifact_hashes"]
        )

    # Note: volatile block is kept as-is (not excluded, just not sorted)
    # It will be excluded when computing content hashes in the release flow

    return result


# =============================================================================
# Loading
# =============================================================================


def load_approval(path: Path) -> dict:
    """Load and validate an approval from a JSON file.

    Args:
        path: Path to the approval JSON file

    Returns:
        Validated approval dict

    Raises:
        FileNotFoundError: If the file does not exist
        ApprovalValidationError: If the approval is invalid
    """
    if not path.exists():
        raise FileNotFoundError(f"Approval not found: {path}")

    try:
        with open(path) as f:
            approval = json.load(f)
    except json.JSONDecodeError as e:
        raise ApprovalValidationError(f"Invalid JSON: {e}")

    validate_approval(approval)

    return approval


# =============================================================================
# Helper Functions
# =============================================================================


def get_approval_decision(approval: dict) -> str:
    """Get the decision from an approval.

    Args:
        approval: Validated approval dict

    Returns:
        Decision string ("approve" or "reject")
    """
    return approval.get("decision", "")


def get_approval_approver(approval: dict) -> dict:
    """Get the approver info from an approval.

    Args:
        approval: Validated approval dict

    Returns:
        Approver dict
    """
    return approval.get("approver", {})


def get_approval_scope(approval: dict) -> dict:
    """Get the scope from an approval.

    Args:
        approval: Validated approval dict

    Returns:
        Scope dict
    """
    return approval.get("scope", {})


def is_approved(approval: dict) -> bool:
    """Check if an approval has decision "approve".

    Args:
        approval: Validated approval dict

    Returns:
        True if decision is "approve"
    """
    return approval.get("decision") == "approve"


def is_rejected(approval: dict) -> bool:
    """Check if an approval has decision "reject".

    Args:
        approval: Validated approval dict

    Returns:
        True if decision is "reject"
    """
    return approval.get("decision") == "reject"


def create_approval(
    approval_id: str,
    episode_id: str,
    approver_name: str,
    approver_role: str,
    decision: str,
    reason: str,
    scope_what: str,
    approver_org: Optional[str] = None,
    artifact_hashes: Optional[List[str]] = None,
    signatures: Optional[List[dict]] = None,
) -> dict:
    """Create a new approval dict.

    Args:
        approval_id: Unique approval identifier
        episode_id: Episode being approved
        approver_name: Display name of approver
        approver_role: Role of approver
        decision: "approve" or "reject"
        reason: Justification for decision
        scope_what: Type of artifact ("release", "plan", "contracts", "idl")
        approver_org: Optional organization
        artifact_hashes: Optional list of artifact hashes
        signatures: Optional list of signatures

    Returns:
        Approval dict (validated)

    Raises:
        ApprovalValidationError: If the created approval is invalid
    """
    approval = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_id": approval_id,
        "episode_id": episode_id,
        "approver": {
            "display_name": approver_name,
            "role": approver_role,
            "org": approver_org,
        },
        "decision": decision,
        "reason": reason,
        "scope": {
            "what": scope_what,
        },
        "signatures": signatures or [],
    }

    if artifact_hashes:
        approval["scope"]["artifact_hashes"] = artifact_hashes

    # Validate before returning
    validate_approval(approval)

    return approval
