"""Wizard Session Management.

Handles creation, loading, updating, and validation of wizard sessions.
Sessions are stored in .engine/wizard_sessions/<session_id>/.

Key features:
- Deterministic session creation
- Append-only event logging for all updates
- Schema validation on load/save
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema

from .wizard_runlog import WizardRunlogValidationError


# =============================================================================
# Constants
# =============================================================================

WIZARD_SESSIONS_DIR = ".engine/wizard_sessions"
SESSION_FILENAME = "session.json"
EVENTS_FILENAME = "events.log"

WIZARD_SESSION_SCHEMA_VERSION = "wizard_session.v1"


# =============================================================================
# Schema Loading
# =============================================================================

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "wizard_session.v1.json"
_SESSION_SCHEMA: Optional[dict] = None


def _get_schema() -> dict:
    """Load and cache the wizard_session schema."""
    global _SESSION_SCHEMA
    if _SESSION_SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _SESSION_SCHEMA = json.load(f)
    return _SESSION_SCHEMA


# =============================================================================
# Exceptions
# =============================================================================


class WizardSessionError(Exception):
    """Base exception for wizard session errors."""
    pass


class WizardSessionValidationError(WizardSessionError):
    """Exception raised when session validation fails.

    Error messages are prefixed with "SCHEMA: " following project conventions.
    """

    def __init__(self, message: str, path: str = ""):
        self.message = message
        self.path = path
        super().__init__(f"SCHEMA: {path}: {message}" if path else f"SCHEMA: {message}")


class WizardSessionNotFoundError(WizardSessionError):
    """Exception raised when session is not found."""
    pass


# =============================================================================
# Session Validation
# =============================================================================


def validate_session(session: dict) -> None:
    """Validate a wizard session against the schema.

    Args:
        session: The session dict to validate

    Raises:
        WizardSessionValidationError: If validation fails (prefixed with "SCHEMA: ...")
    """
    schema = _get_schema()

    try:
        jsonschema.validate(instance=session, schema=schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else ""
        raise WizardSessionValidationError(e.message, path)

    # Additional semantic validations

    # 1. Check for duplicate step_id
    step_ids = [s.get("step_id") for s in session.get("steps", [])]
    if len(step_ids) != len(set(step_ids)):
        duplicates = [sid for sid in step_ids if step_ids.count(sid) > 1]
        raise WizardSessionValidationError(
            f"Duplicate step_id: {duplicates[0]}", "steps"
        )

    # 2. Check for duplicate field_id within each step
    for i, step in enumerate(session.get("steps", [])):
        field_ids = [f.get("field_id") for f in step.get("fields", [])]
        if len(field_ids) != len(set(field_ids)):
            duplicates = [fid for fid in field_ids if field_ids.count(fid) > 1]
            raise WizardSessionValidationError(
                f"Duplicate field_id: {duplicates[0]}", f"steps[{i}].fields"
            )

    # 3. Check for duplicate question_id
    question_ids = [q.get("question_id") for q in session.get("open_questions", [])]
    if len(question_ids) != len(set(question_ids)):
        duplicates = [qid for qid in question_ids if question_ids.count(qid) > 1]
        raise WizardSessionValidationError(
            f"Duplicate question_id: {duplicates[0]}", "open_questions"
        )

    # 4. Check for duplicate evidence_id
    evidence_ids = [e.get("evidence_id") for e in session.get("evidence", [])]
    if len(evidence_ids) != len(set(evidence_ids)):
        duplicates = [eid for eid in evidence_ids if evidence_ids.count(eid) > 1]
        raise WizardSessionValidationError(
            f"Duplicate evidence_id: {duplicates[0]}", "evidence"
        )


# =============================================================================
# Session Path Helpers
# =============================================================================


def get_sessions_root(base_dir: Optional[Path] = None) -> Path:
    """Get the root directory for wizard sessions.

    Args:
        base_dir: Base directory (defaults to current working directory)

    Returns:
        Path to wizard sessions root
    """
    base = base_dir or Path.cwd()
    return base / WIZARD_SESSIONS_DIR


def get_session_dir(session_id: str, base_dir: Optional[Path] = None) -> Path:
    """Get the directory for a specific session.

    Args:
        session_id: The session ID
        base_dir: Base directory (defaults to current working directory)

    Returns:
        Path to session directory
    """
    return get_sessions_root(base_dir) / session_id


def get_session_path(session_id: str, base_dir: Optional[Path] = None) -> Path:
    """Get the path to session.json for a session.

    Args:
        session_id: The session ID
        base_dir: Base directory

    Returns:
        Path to session.json
    """
    return get_session_dir(session_id, base_dir) / SESSION_FILENAME


def get_events_path(session_id: str, base_dir: Optional[Path] = None) -> Path:
    """Get the path to events.log for a session.

    Args:
        session_id: The session ID
        base_dir: Base directory

    Returns:
        Path to events.log
    """
    return get_session_dir(session_id, base_dir) / EVENTS_FILENAME


# =============================================================================
# Session Creation
# =============================================================================


def generate_session_id() -> str:
    """Generate a deterministic session ID.

    Returns:
        A unique session ID (UUID4 format)
    """
    return str(uuid.uuid4())


def create_default_steps() -> List[dict]:
    """Create the default wizard steps structure.

    Returns:
        List of default step definitions
    """
    return [
        {
            "step_id": "system_info",
            "title": "System Information",
            "status": "partial",
            "fields": [
                {"field_id": "system_name", "value": None, "required": True},
                {"field_id": "domain", "value": None, "required": True},
                {"field_id": "objective", "value": None, "required": False},
            ],
        },
        {
            "step_id": "actors",
            "title": "Actors & Roles",
            "status": "partial",
            "fields": [
                {"field_id": "actors_list", "value": [], "required": True},
            ],
        },
        {
            "step_id": "entities",
            "title": "Domain Entities",
            "status": "partial",
            "fields": [
                {"field_id": "entities_list", "value": [], "required": True},
            ],
        },
        {
            "step_id": "use_cases",
            "title": "Use Cases",
            "status": "partial",
            "fields": [
                {"field_id": "use_cases_list", "value": [], "required": False},
            ],
        },
        {
            "step_id": "integrations",
            "title": "Integrations",
            "status": "partial",
            "fields": [
                {"field_id": "integrations_list", "value": [], "required": False},
            ],
        },
        {
            "step_id": "nonfunctional",
            "title": "Non-Functional Requirements",
            "status": "partial",
            "fields": [
                {"field_id": "performance", "value": None, "required": False},
                {"field_id": "security", "value": None, "required": False},
            ],
        },
    ]


def create_session(
    project_name: str,
    domain: str,
    session_id: Optional[str] = None,
    objective: Optional[str] = None,
) -> dict:
    """Create a new wizard session.

    Args:
        project_name: Name of the project
        domain: Business domain
        session_id: Optional session ID (generated if not provided)
        objective: Optional project objective

    Returns:
        New wizard session dict
    """
    sid = session_id or generate_session_id()

    session = {
        "schema_version": WIZARD_SESSION_SCHEMA_VERSION,
        "session_id": sid,
        "project": {
            "name": project_name,
            "domain": domain,
        },
        "steps": create_default_steps(),
        "evidence": [],
        "open_questions": [],
    }

    if objective:
        session["project"]["objective"] = objective

    # Set system_name field from project name
    for step in session["steps"]:
        if step["step_id"] == "system_info":
            for field in step["fields"]:
                if field["field_id"] == "system_name":
                    field["value"] = project_name
                elif field["field_id"] == "domain":
                    field["value"] = domain
                elif field["field_id"] == "objective" and objective:
                    field["value"] = objective

    return session


# =============================================================================
# Session Persistence
# =============================================================================


def save_session(
    session: dict,
    base_dir: Optional[Path] = None,
    validate: bool = True,
) -> Path:
    """Save a wizard session to disk.

    Args:
        session: The session dict to save
        base_dir: Base directory for sessions
        validate: Whether to validate before saving

    Returns:
        Path to saved session.json

    Raises:
        WizardSessionValidationError: If validation fails
    """
    if validate:
        validate_session(session)

    session_id = session["session_id"]
    session_dir = get_session_dir(session_id, base_dir)
    session_path = session_dir / SESSION_FILENAME

    # Create directory if needed
    session_dir.mkdir(parents=True, exist_ok=True)

    # Save session
    with open(session_path, "w") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)

    return session_path


def load_session(
    session_id: str,
    base_dir: Optional[Path] = None,
    validate: bool = True,
) -> dict:
    """Load a wizard session from disk.

    Args:
        session_id: The session ID to load
        base_dir: Base directory for sessions
        validate: Whether to validate after loading

    Returns:
        Loaded session dict

    Raises:
        WizardSessionNotFoundError: If session not found
        WizardSessionValidationError: If validation fails
    """
    session_path = get_session_path(session_id, base_dir)

    if not session_path.exists():
        raise WizardSessionNotFoundError(f"Session not found: {session_id}")

    with open(session_path) as f:
        session = json.load(f)

    if validate:
        validate_session(session)

    return session


def session_exists(session_id: str, base_dir: Optional[Path] = None) -> bool:
    """Check if a session exists.

    Args:
        session_id: The session ID to check
        base_dir: Base directory for sessions

    Returns:
        True if session exists
    """
    return get_session_path(session_id, base_dir).exists()


# =============================================================================
# Event Logging
# =============================================================================


def log_event(
    session_id: str,
    event_type: str,
    data: Dict[str, Any],
    base_dir: Optional[Path] = None,
) -> None:
    """Log an event to the session's events.log.

    Events are append-only JSON lines for audit trail.

    Args:
        session_id: The session ID
        event_type: Type of event (e.g., "update", "add_evidence", "add_question")
        data: Event data
        base_dir: Base directory for sessions
    """
    events_path = get_events_path(session_id, base_dir)

    # Ensure directory exists
    events_path.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "event_type": event_type,
        "data": data,
        # Note: timestamp is for audit trail only, not used in deterministic processing
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(events_path, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_events(
    session_id: str,
    base_dir: Optional[Path] = None,
) -> List[dict]:
    """Load all events for a session.

    Args:
        session_id: The session ID
        base_dir: Base directory for sessions

    Returns:
        List of event dicts
    """
    events_path = get_events_path(session_id, base_dir)

    if not events_path.exists():
        return []

    events = []
    with open(events_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    return events


# =============================================================================
# Session Updates
# =============================================================================


def update_session_field(
    session: dict,
    step_id: str,
    field_id: str,
    value: Any,
    base_dir: Optional[Path] = None,
) -> dict:
    """Update a field in the session.

    Also logs the update event.

    Args:
        session: The session dict
        step_id: The step ID containing the field
        field_id: The field ID to update
        value: New value
        base_dir: Base directory for sessions

    Returns:
        Updated session dict

    Raises:
        WizardSessionError: If step or field not found
    """
    session_id = session["session_id"]

    # Find and update field
    field_found = False
    for step in session["steps"]:
        if step["step_id"] == step_id:
            for field in step["fields"]:
                if field["field_id"] == field_id:
                    old_value = field["value"]
                    field["value"] = value
                    field_found = True

                    # Log the event
                    log_event(
                        session_id,
                        "update_field",
                        {
                            "step_id": step_id,
                            "field_id": field_id,
                            "old_value": old_value,
                            "new_value": value,
                        },
                        base_dir,
                    )
                    break
            break

    if not field_found:
        raise WizardSessionError(f"Field not found: {step_id}.{field_id}")

    return session


def add_open_question(
    session: dict,
    question_id: str,
    question: str,
    severity: str = "non_blocking",
    context: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> dict:
    """Add an open question to the session.

    Args:
        session: The session dict
        question_id: Unique question ID
        question: The question text
        severity: "blocking" or "non_blocking"
        context: Optional context
        base_dir: Base directory for sessions

    Returns:
        Updated session dict
    """
    session_id = session["session_id"]

    question_obj = {
        "question_id": question_id,
        "question": question,
        "severity": severity,
    }
    if context:
        question_obj["context"] = context

    session["open_questions"].append(question_obj)

    log_event(
        session_id,
        "add_open_question",
        question_obj,
        base_dir,
    )

    return session


def add_evidence(
    session: dict,
    evidence_id: str,
    kind: str,
    path: str,
    content_hash_sha256: Optional[str] = None,
    description: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> dict:
    """Add evidence to the session.

    Args:
        session: The session dict
        evidence_id: Unique evidence ID
        kind: Evidence type (ddl, csv, doc, link, note, spreadsheet, diagram)
        path: Path or reference
        content_hash_sha256: Optional hash
        description: Optional description
        base_dir: Base directory for sessions

    Returns:
        Updated session dict
    """
    session_id = session["session_id"]

    evidence_obj: Dict[str, Any] = {
        "evidence_id": evidence_id,
        "kind": kind,
        "path": path,
    }
    if content_hash_sha256:
        evidence_obj["content_hash_sha256"] = content_hash_sha256
    if description:
        evidence_obj["description"] = description

    session["evidence"].append(evidence_obj)

    log_event(
        session_id,
        "add_evidence",
        evidence_obj,
        base_dir,
    )

    return session


def update_step_status(
    session: dict,
    step_id: str,
    status: str,
    base_dir: Optional[Path] = None,
) -> dict:
    """Update a step's status.

    Args:
        session: The session dict
        step_id: The step ID
        status: New status ("complete", "partial", "blocked")
        base_dir: Base directory for sessions

    Returns:
        Updated session dict
    """
    session_id = session["session_id"]

    for step in session["steps"]:
        if step["step_id"] == step_id:
            old_status = step["status"]
            step["status"] = status

            log_event(
                session_id,
                "update_step_status",
                {
                    "step_id": step_id,
                    "old_status": old_status,
                    "new_status": status,
                },
                base_dir,
            )
            break

    return session


# =============================================================================
# Session Analysis
# =============================================================================


def get_session_stats(session: dict) -> dict:
    """Get statistics about a session.

    Args:
        session: The session dict

    Returns:
        Dict with session statistics
    """
    steps = session.get("steps", [])
    open_questions = session.get("open_questions", [])
    evidence = session.get("evidence", [])

    return {
        "steps_total": len(steps),
        "steps_complete": sum(1 for s in steps if s.get("status") == "complete"),
        "steps_partial": sum(1 for s in steps if s.get("status") == "partial"),
        "steps_blocked": sum(1 for s in steps if s.get("status") == "blocked"),
        "open_questions_total": len(open_questions),
        "open_questions_blocking": sum(
            1 for q in open_questions if q.get("severity") == "blocking"
        ),
        "evidence_total": len(evidence),
    }


def has_blocking_issues(session: dict) -> bool:
    """Check if session has blocking issues.

    Args:
        session: The session dict

    Returns:
        True if there are blocking open questions
    """
    for q in session.get("open_questions", []):
        if q.get("severity") == "blocking":
            return True
    return False
