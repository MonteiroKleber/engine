"""Wizard RunLog v1 - Deterministic runlog for wizard audit trail.

This module provides helpers for creating and finalizing wizard runlogs.
The wizard_runlog is separate from and precedes the engine runlog.

Key invariants:
- counts and flags are ALWAYS present (zeros/false when empty)
- error_codes is always 1:1 with errors
- blocked_reason is only set when final_status is blocked/invalid
- No timestamps in runlog (deterministic)
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema


# =============================================================================
# Schema Loading
# =============================================================================

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "wizard_runlog.v1.json"
_WIZARD_RUNLOG_SCHEMA: Optional[dict] = None


def _get_schema() -> dict:
    """Load and cache the wizard_runlog schema."""
    global _WIZARD_RUNLOG_SCHEMA
    if _WIZARD_RUNLOG_SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _WIZARD_RUNLOG_SCHEMA = json.load(f)
    return _WIZARD_RUNLOG_SCHEMA


# =============================================================================
# Exceptions
# =============================================================================


class WizardRunlogValidationError(Exception):
    """Exception raised when wizard runlog validation fails.

    Error messages are prefixed with "SCHEMA: " following project conventions.
    """

    def __init__(self, message: str, path: str = ""):
        self.message = message
        self.path = path
        super().__init__(f"SCHEMA: {path}: {message}" if path else f"SCHEMA: {message}")


# =============================================================================
# Default Counts and Flags
# =============================================================================


def _default_counts() -> Dict[str, int]:
    """Return default counts dict with all fields at zero."""
    return {
        "steps_total": 0,
        "steps_complete": 0,
        "open_questions_total": 0,
        "open_questions_blocking": 0,
        "evidence_total": 0,
    }


def _default_flags() -> Dict[str, bool]:
    """Return default flags dict with all fields false."""
    return {
        "has_blocking_open_questions": False,
        "has_evidence": False,
    }


# =============================================================================
# Core Functions
# =============================================================================


def new_wizard_runlog(session_id: str, mode: str) -> dict:
    """Create a new wizard runlog with default values.

    Args:
        session_id: The wizard session identifier
        mode: Operation mode - one of "start", "resume", "export"

    Returns:
        A new wizard runlog dict ready to be finalized

    Raises:
        ValueError: If mode is not valid
    """
    valid_modes = ("start", "resume", "export")
    if mode not in valid_modes:
        raise ValueError(f"Invalid mode '{mode}'. Must be one of: {valid_modes}")

    return {
        "schema_version": "wizard_runlog.v1",
        "session_id": session_id,
        "mode": mode,
        "final_status": "success",  # Default, will be updated by finalize
        "blocked_reason": None,
        "duration_ms": 0,
        "counts": _default_counts(),
        "flags": _default_flags(),
        "errors": [],
        "error_codes": [],
        "blueprint": None,  # Will be set if blueprint is used
        "episode": None,  # Will be set if associated with episode
    }


def finalize_wizard_runlog(
    runlog: dict,
    status: str,
    duration_ms: float,
    counts: Optional[Dict[str, int]] = None,
    flags: Optional[Dict[str, bool]] = None,
    errors: Optional[List[str]] = None,
    error_codes: Optional[List[str]] = None,
    blocked_reason: Optional[str] = None,
) -> dict:
    """Finalize a wizard runlog with execution results.

    Args:
        runlog: The runlog dict to finalize (will be mutated)
        status: Final status - one of "success", "blocked", "invalid"
        duration_ms: Execution duration in milliseconds
        counts: Count metrics (merged with defaults)
        flags: Boolean flags (merged with defaults)
        errors: List of error messages
        error_codes: List of error codes (must match errors length)
        blocked_reason: Reason for blocking (required if status is blocked/invalid)

    Returns:
        The finalized runlog dict

    Raises:
        ValueError: If status is invalid or error_codes don't match errors
        ValueError: If blocked without blocked_reason
    """
    valid_statuses = ("success", "blocked", "invalid")
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {valid_statuses}")

    errors = errors or []
    error_codes = error_codes or []

    # Enforce 1:1 correspondence between errors and error_codes
    if len(errors) != len(error_codes):
        raise ValueError(
            f"error_codes length ({len(error_codes)}) must match errors length ({len(errors)})"
        )

    # Enforce blocked_reason coherence
    if status in ("blocked", "invalid") and blocked_reason is None:
        raise ValueError(f"blocked_reason is required when status is '{status}'")

    if status == "success" and blocked_reason is not None:
        raise ValueError("blocked_reason must be null when status is 'success'")

    # Validate blocked_reason enum
    valid_blocked_reasons = (
        "OPEN_QUESTIONS_BLOCKING",
        "SCHEMA_INVALID",
        "INCOMPLETE_STEPS",
        "APPROVAL_REQUIRED",
        "APPROVAL_INVALID",
        "IMPACT_OUT_OF_SCOPE",
        "IMPACT_TOO_BROAD",
        "IMPACT_FORBIDDEN_PATH",
        "IMPACT_GATE_BLOCKED",
    )
    if blocked_reason is not None and blocked_reason not in valid_blocked_reasons:
        raise ValueError(
            f"Invalid blocked_reason '{blocked_reason}'. Must be one of: {valid_blocked_reasons}"
        )

    # Update runlog
    runlog["final_status"] = status
    runlog["blocked_reason"] = blocked_reason
    runlog["duration_ms"] = duration_ms
    runlog["errors"] = errors
    runlog["error_codes"] = error_codes

    # Merge counts with defaults (ensure all keys present)
    merged_counts = _default_counts()
    if counts:
        for key in merged_counts:
            if key in counts:
                merged_counts[key] = counts[key]
    runlog["counts"] = merged_counts

    # Merge flags with defaults (ensure all keys present)
    merged_flags = _default_flags()
    if flags:
        for key in merged_flags:
            if key in flags:
                merged_flags[key] = flags[key]
    runlog["flags"] = merged_flags

    return runlog


def validate_wizard_runlog(runlog: dict) -> None:
    """Validate a wizard runlog against the schema.

    Args:
        runlog: The runlog dict to validate

    Raises:
        WizardRunlogValidationError: If validation fails (prefixed with "SCHEMA: ...")
    """
    schema = _get_schema()

    # JSON Schema validation
    try:
        jsonschema.validate(instance=runlog, schema=schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else ""
        raise WizardRunlogValidationError(e.message, path)

    # Additional semantic validations

    # 1. error_codes must be 1:1 with errors
    errors = runlog.get("errors", [])
    error_codes = runlog.get("error_codes", [])
    if len(errors) != len(error_codes):
        raise WizardRunlogValidationError(
            f"error_codes length ({len(error_codes)}) must match errors length ({len(errors)})",
            "error_codes",
        )

    # 2. blocked_reason coherence with final_status
    status = runlog.get("final_status")
    blocked_reason = runlog.get("blocked_reason")

    if status in ("blocked", "invalid") and blocked_reason is None:
        raise WizardRunlogValidationError(
            f"blocked_reason cannot be null when final_status is '{status}'",
            "blocked_reason",
        )

    if status == "success" and blocked_reason is not None:
        raise WizardRunlogValidationError(
            "blocked_reason must be null when final_status is 'success'",
            "blocked_reason",
        )

    # 3. Counts coherence with flags
    counts = runlog.get("counts", {})
    flags = runlog.get("flags", {})

    if counts.get("open_questions_blocking", 0) > 0 and not flags.get(
        "has_blocking_open_questions", False
    ):
        raise WizardRunlogValidationError(
            "has_blocking_open_questions must be true when open_questions_blocking > 0",
            "flags.has_blocking_open_questions",
        )

    if counts.get("evidence_total", 0) > 0 and not flags.get("has_evidence", False):
        raise WizardRunlogValidationError(
            "has_evidence must be true when evidence_total > 0",
            "flags.has_evidence",
        )


def set_runlog_blueprint(
    runlog: dict,
    blueprint_id: str,
    content_hash_sha256: str,
    diff_summary: Dict[str, Any],
) -> None:
    """Set the blueprint info in a runlog.

    Args:
        runlog: The runlog dict to update
        blueprint_id: ID of the blueprint used
        content_hash_sha256: SHA256 hash of the canonicalized blueprint
        diff_summary: Summary of changes applied by blueprint
    """
    runlog["blueprint"] = {
        "blueprint_id": blueprint_id,
        "content_hash_sha256": content_hash_sha256,
        "diff_summary": diff_summary,
    }


def compute_counts_from_session(session: dict) -> Dict[str, int]:
    """Compute runlog counts from a wizard session.

    Args:
        session: A valid wizard_session.v1 dict

    Returns:
        Counts dict ready for finalize_wizard_runlog
    """
    steps = session.get("steps", [])
    open_questions = session.get("open_questions", [])
    evidence = session.get("evidence", [])

    return {
        "steps_total": len(steps),
        "steps_complete": sum(1 for s in steps if s.get("status") == "complete"),
        "open_questions_total": len(open_questions),
        "open_questions_blocking": sum(
            1 for q in open_questions if q.get("severity") == "blocking"
        ),
        "evidence_total": len(evidence),
    }


def compute_flags_from_session(session: dict) -> Dict[str, bool]:
    """Compute runlog flags from a wizard session.

    Args:
        session: A valid wizard_session.v1 dict

    Returns:
        Flags dict ready for finalize_wizard_runlog
    """
    open_questions = session.get("open_questions", [])
    evidence = session.get("evidence", [])

    has_blocking = any(q.get("severity") == "blocking" for q in open_questions)

    return {
        "has_blocking_open_questions": has_blocking,
        "has_evidence": len(evidence) > 0,
    }


# =============================================================================
# Episode Audit Functions
# =============================================================================


def canonicalize_approval(approval: dict) -> str:
    """Canonicalize an approval dict for deterministic hashing.

    Removes volatile fields (timestamps) and produces stable JSON output.

    Args:
        approval: Approval dict to canonicalize

    Returns:
        Canonicalized JSON string
    """
    from copy import deepcopy

    # Deep copy to avoid mutating original
    canonical = deepcopy(approval)

    # Remove volatile section if present (contains timestamps)
    canonical.pop("volatile", None)

    # Produce deterministic JSON output
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"))


def compute_approval_hash(approval: dict) -> str:
    """Compute SHA256 hash of canonicalized approval.

    Args:
        approval: Approval dict to hash

    Returns:
        Hash string in format "sha256:<hex>"
    """
    import hashlib

    canonical = canonicalize_approval(approval)
    hash_hex = hashlib.sha256(canonical.encode()).hexdigest()
    return f"sha256:{hash_hex}"


def set_runlog_episode(
    runlog: dict,
    episode_id: str,
    manifest_path: str,
    episode_root_hash: Optional[str] = None,
    approval: Optional[dict] = None,
) -> None:
    """Set the episode audit info in a runlog.

    Args:
        runlog: The runlog dict to update
        episode_id: Episode identifier
        manifest_path: Relative path to episode manifest
        episode_root_hash: Episode root hash (None if not finalized)
        approval: Approval dict (None if no approval present)
    """
    if approval is not None:
        approval_info = {
            "present": True,
            "decision": approval.get("decision"),
            "approval_hash_sha256": compute_approval_hash(approval),
        }
    else:
        approval_info = {
            "present": False,
            "decision": None,
            "approval_hash_sha256": None,
        }

    runlog["episode"] = {
        "episode_id": episode_id,
        "manifest_path": manifest_path,
        "episode_root_hash_sha256": episode_root_hash,
        "approval": approval_info,
    }


def set_runlog_episode_from_store(
    runlog: dict,
    episode_store,
    episode_id: str,
) -> None:
    """Set episode audit info from an EpisodeStore.

    Convenience function that reads episode data from the store.

    Args:
        runlog: The runlog dict to update
        episode_store: EpisodeStore instance
        episode_id: Episode identifier

    Raises:
        EpisodeNotFoundError: If episode not found
    """
    if not episode_store.exists(episode_id):
        # Episode not found - set episode to null
        runlog["episode"] = None
        return

    # Get manifest path (relative)
    manifest_path = str(
        episode_store._get_manifest_path(episode_id).relative_to(
            episode_store.base_path
        )
    )

    # Get manifest to check root hash
    manifest = episode_store.get_manifest(episode_id)
    root_hash = manifest.get("integrity", {}).get("episode_root_hash_sha256")

    # Check if it's a placeholder hash
    placeholder = "sha256:" + "0" * 64
    if root_hash == placeholder:
        root_hash = None

    # Get approval if present
    approval = episode_store.get_approval(episode_id)

    set_runlog_episode(
        runlog=runlog,
        episode_id=episode_id,
        manifest_path=manifest_path,
        episode_root_hash=root_hash,
        approval=approval,
    )
