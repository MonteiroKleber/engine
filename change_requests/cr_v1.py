"""IDL Change Request v1 - Governed changes over generated systems.

This module provides validation and canonicalization for IDL Change Requests.
Change Requests document proposed modifications to systems that were generated
from a previous episode.

Key rules:
- schema_version is fixed at "idl_change_request.v1"
- change_request_id is unique and required
- previous_episode_id links to the base system being modified
- Canonicalization sorts: entities_affected, usecases_affected, acceptance_criteria, invariants
- volatile section is excluded from hash computation

Schema Version: idl_change_request.v1
"""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Optional

import jsonschema


# =============================================================================
# Constants
# =============================================================================

CR_SCHEMA_VERSION = "idl_change_request.v1"

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "idl_change_request.v1.json"
_CR_SCHEMA: Optional[dict] = None


# =============================================================================
# Schema Loading
# =============================================================================


def _get_schema() -> dict:
    """Load and cache the change request schema."""
    global _CR_SCHEMA
    if _CR_SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _CR_SCHEMA = json.load(f)
    return _CR_SCHEMA


# =============================================================================
# Exceptions
# =============================================================================


class CRValidationError(Exception):
    """Exception raised when change request validation fails.

    Error messages are prefixed with "SCHEMA: " following project conventions.
    """

    def __init__(self, message: str, path: str = ""):
        self.message = message
        self.path = path
        super().__init__(f"SCHEMA: {path}: {message}" if path else f"SCHEMA: {message}")


# =============================================================================
# Core Functions
# =============================================================================


def load_cr(path: Path) -> dict:
    """Load and validate a change request from a JSON file.

    Args:
        path: Path to the change request JSON file

    Returns:
        Validated change request dict

    Raises:
        FileNotFoundError: If the file does not exist
        CRValidationError: If the change request is invalid
    """
    if not path.exists():
        raise FileNotFoundError(f"Change request not found: {path}")

    try:
        with open(path) as f:
            cr = json.load(f)
    except json.JSONDecodeError as e:
        raise CRValidationError(f"Invalid JSON: {e}")

    validate_cr(cr)

    return cr


def validate_cr(obj: dict) -> None:
    """Validate a change request against the schema.

    Args:
        obj: The change request dict to validate

    Raises:
        CRValidationError: If validation fails (prefixed with "SCHEMA: ...")
    """
    schema = _get_schema()

    # JSON Schema validation
    try:
        jsonschema.validate(instance=obj, schema=schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else ""
        raise CRValidationError(e.message, path)


def canonicalize_cr(obj: dict) -> dict:
    """Canonicalize a change request for deterministic comparison/hashing.

    Applies stable ordering to:
    - scope.entities_affected: sorted lexicographically
    - scope.usecases_affected: sorted lexicographically
    - acceptance_criteria: sorted lexicographically
    - invariants: sorted by name

    Removes volatile section (contains timestamps).

    Does NOT modify values, only ordering.

    Args:
        obj: The change request dict to canonicalize

    Returns:
        A new dict with canonical ordering (original is not mutated)
    """
    result = deepcopy(obj)

    # Remove volatile section (not part of canonical form)
    result.pop("volatile", None)

    # Sort scope arrays
    if "scope" in result and result["scope"]:
        scope = result["scope"]

        if "entities_affected" in scope and scope["entities_affected"]:
            scope["entities_affected"] = sorted(scope["entities_affected"])

        if "usecases_affected" in scope and scope["usecases_affected"]:
            scope["usecases_affected"] = sorted(scope["usecases_affected"])

    # Sort acceptance_criteria
    if "acceptance_criteria" in result and result["acceptance_criteria"]:
        result["acceptance_criteria"] = sorted(result["acceptance_criteria"])

    # Sort invariants by name
    if "invariants" in result and result["invariants"]:
        result["invariants"] = sorted(
            result["invariants"],
            key=lambda x: x.get("name", "")
        )

    # Sort attachments by ref for determinism
    if "attachments" in result and result["attachments"]:
        result["attachments"] = sorted(
            result["attachments"],
            key=lambda x: (x.get("kind", ""), x.get("ref", ""))
        )

    return result


def cr_hash_sha256(obj: dict) -> str:
    """Compute SHA256 hash of canonicalized change request.

    The hash is computed from the canonical JSON representation,
    excluding the volatile section.

    Args:
        obj: The change request dict to hash

    Returns:
        Hash string in format "sha256:<hex>"
    """
    canonical = canonicalize_cr(obj)

    # Produce deterministic JSON output
    json_str = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    hash_hex = hashlib.sha256(json_str.encode()).hexdigest()

    return f"sha256:{hash_hex}"


# =============================================================================
# Helper Functions
# =============================================================================


def create_cr(
    change_request_id: str,
    previous_episode_id: str,
    requester_name: str,
    requester_role: str,
    reason: str,
    target: str,
    summary: str,
    risk_level: str = "low",
    requester_org: Optional[str] = None,
    entities_affected: Optional[list] = None,
    usecases_affected: Optional[list] = None,
    invariants: Optional[list] = None,
    acceptance_criteria: Optional[list] = None,
    risk_notes: Optional[str] = None,
    attachments: Optional[list] = None,
) -> dict:
    """Create a new change request dict.

    Args:
        change_request_id: Unique identifier for the CR
        previous_episode_id: Episode ID of the base system
        requester_name: Name of the requester
        requester_role: Role of the requester
        reason: Justification for the change
        target: Target area (frontend, backend, db, api, rbac, infra, docs)
        summary: Summary of the change
        risk_level: Risk level (low, medium, high)
        requester_org: Optional organization
        entities_affected: Optional list of affected entities
        usecases_affected: Optional list of affected use cases
        invariants: Optional list of invariants
        acceptance_criteria: Optional list of acceptance criteria
        risk_notes: Optional risk notes
        attachments: Optional list of attachments

    Returns:
        Change request dict (NOT validated - call validate_cr to validate)
    """
    return {
        "schema_version": CR_SCHEMA_VERSION,
        "change_request_id": change_request_id,
        "previous_episode_id": previous_episode_id,
        "requested_by": {
            "display_name": requester_name,
            "role": requester_role,
            "org": requester_org,
        },
        "reason": reason,
        "scope": {
            "target": target,
            "summary": summary,
            "entities_affected": entities_affected or [],
            "usecases_affected": usecases_affected or [],
        },
        "invariants": invariants or [],
        "acceptance_criteria": acceptance_criteria or [],
        "risk": {
            "level": risk_level,
            "notes": risk_notes,
        },
        "attachments": attachments or [],
    }


def get_cr_id(obj: dict) -> str:
    """Get the change request ID from a CR dict.

    Args:
        obj: Change request dict

    Returns:
        Change request ID
    """
    return obj.get("change_request_id", "")


def get_previous_episode_id(obj: dict) -> str:
    """Get the previous episode ID from a CR dict.

    Args:
        obj: Change request dict

    Returns:
        Previous episode ID
    """
    return obj.get("previous_episode_id", "")


def get_risk_level(obj: dict) -> str:
    """Get the risk level from a CR dict.

    Args:
        obj: Change request dict

    Returns:
        Risk level (low, medium, high)
    """
    return obj.get("risk", {}).get("level", "low")


def get_target(obj: dict) -> str:
    """Get the target area from a CR dict.

    Args:
        obj: Change request dict

    Returns:
        Target area
    """
    return obj.get("scope", {}).get("target", "")


def get_entities_affected(obj: dict) -> list:
    """Get the list of affected entities from a CR dict.

    Args:
        obj: Change request dict

    Returns:
        List of affected entities
    """
    return obj.get("scope", {}).get("entities_affected", [])


def get_usecases_affected(obj: dict) -> list:
    """Get the list of affected use cases from a CR dict.

    Args:
        obj: Change request dict

    Returns:
        List of affected use cases
    """
    return obj.get("scope", {}).get("usecases_affected", [])
