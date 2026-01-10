"""Wizard CLI - Command-line interface for wizard operations.

Provides three commands:
- start: Create a new wizard session
- resume: Resume and update an existing session
- export: Export session as IDL Draft v1

Usage:
    python -m wizard.wizard_cli start --project MyProject --domain healthcare
    python -m wizard.wizard_cli resume <session_id> --set actors.actors_list='["Admin","User"]'
    python -m wizard.wizard_cli export <session_id>
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .session import (
    create_session,
    save_session,
    load_session,
    validate_session,
    update_session_field,
    add_open_question,
    add_evidence,
    update_step_status,
    get_session_stats,
    has_blocking_issues,
    session_exists,
    get_session_dir,
    log_event,
    WizardSessionError,
    WizardSessionValidationError,
    WizardSessionNotFoundError,
)
from .export import (
    export_session,
    validate_draft,
    get_draft_json_path,
    session_to_draft,
    apply_blueprint_to_idl_draft,
    compute_blueprint_diff_summary,
    get_export_dir,
    IDL_DRAFT_JSON,
)
from .wizard_runlog import (
    new_wizard_runlog,
    finalize_wizard_runlog,
    validate_wizard_runlog,
    compute_counts_from_session,
    compute_flags_from_session,
    set_runlog_blueprint,
)


# =============================================================================
# Result Types
# =============================================================================


class WizardResult:
    """Result of a wizard CLI operation."""

    def __init__(
        self,
        success: bool,
        session_id: str,
        runlog: dict,
        message: str = "",
        errors: List[str] = None,
        output_paths: Dict[str, str] = None,
    ):
        self.success = success
        self.session_id = session_id
        self.runlog = runlog
        self.message = message
        self.errors = errors or []
        self.output_paths = output_paths or {}

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "session_id": self.session_id,
            "message": self.message,
            "errors": self.errors,
            "output_paths": self.output_paths,
            "runlog": self.runlog,
        }


# =============================================================================
# Command: start
# =============================================================================


def cmd_start(
    project: str,
    domain: str,
    objective: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> WizardResult:
    """Start a new wizard session.

    Args:
        project: Project name
        domain: Business domain
        objective: Optional project objective
        base_dir: Base directory for sessions

    Returns:
        WizardResult with session info
    """
    start_time = time.time()
    errors = []
    error_codes = []

    # Create session
    session = create_session(
        project_name=project,
        domain=domain,
        objective=objective,
    )
    session_id = session["session_id"]

    # Create runlog
    runlog = new_wizard_runlog(session_id, "start")

    try:
        # Validate session
        validate_session(session)

        # Save session
        session_path = save_session(session, base_dir)

        # Log session creation event
        log_event(
            session_id,
            "session_created",
            {"project": project, "domain": domain},
            base_dir,
        )

        # Compute counts and flags
        counts = compute_counts_from_session(session)
        flags = compute_flags_from_session(session)

        # Finalize runlog
        duration_ms = (time.time() - start_time) * 1000
        finalize_wizard_runlog(
            runlog,
            status="success",
            duration_ms=duration_ms,
            counts=counts,
            flags=flags,
        )

        # Save runlog
        runlog_path = get_session_dir(session_id, base_dir) / "wizard_runlog.json"
        with open(runlog_path, "w") as f:
            json.dump(runlog, f, indent=2)

        return WizardResult(
            success=True,
            session_id=session_id,
            runlog=runlog,
            message=f"Session created: {session_id}",
            output_paths={
                "session": str(session_path),
                "runlog": str(runlog_path),
            },
        )

    except WizardSessionValidationError as e:
        errors.append(str(e))
        error_codes.append("WIZARD_SCHEMA_INVALID")

        duration_ms = (time.time() - start_time) * 1000
        finalize_wizard_runlog(
            runlog,
            status="invalid",
            duration_ms=duration_ms,
            blocked_reason="SCHEMA_INVALID",
            errors=errors,
            error_codes=error_codes,
        )

        return WizardResult(
            success=False,
            session_id=session_id,
            runlog=runlog,
            message="Session creation failed",
            errors=errors,
        )


# =============================================================================
# Command: resume
# =============================================================================


def parse_set_arg(set_arg: str) -> Tuple[str, str, Any]:
    """Parse a --set argument into step_id, field_id, value.

    Format: step_id.field_id=value

    Args:
        set_arg: The --set argument string

    Returns:
        Tuple of (step_id, field_id, value)
    """
    if "=" not in set_arg:
        raise ValueError(f"Invalid --set format: {set_arg}. Expected: step_id.field_id=value")

    path, value_str = set_arg.split("=", 1)

    parts = path.split(".")
    if len(parts) != 2:
        raise ValueError(f"Invalid field path: {path}. Expected: step_id.field_id")

    step_id, field_id = parts

    # Try to parse value as JSON, fallback to string
    try:
        value = json.loads(value_str)
    except json.JSONDecodeError:
        value = value_str

    return step_id, field_id, value


def cmd_resume(
    session_id: str,
    set_fields: Optional[List[str]] = None,
    add_questions: Optional[List[dict]] = None,
    add_evidences: Optional[List[dict]] = None,
    base_dir: Optional[Path] = None,
) -> WizardResult:
    """Resume and optionally update an existing session.

    Args:
        session_id: The session ID to resume
        set_fields: List of field updates (format: step_id.field_id=value)
        add_questions: List of questions to add
        add_evidences: List of evidences to add
        base_dir: Base directory for sessions

    Returns:
        WizardResult with session info
    """
    start_time = time.time()
    errors = []
    error_codes = []

    # Create runlog
    runlog = new_wizard_runlog(session_id, "resume")

    try:
        # Load session
        session = load_session(session_id, base_dir)

        # Apply field updates
        if set_fields:
            for set_arg in set_fields:
                try:
                    step_id, field_id, value = parse_set_arg(set_arg)
                    update_session_field(session, step_id, field_id, value, base_dir)
                except Exception as e:
                    errors.append(f"Failed to set {set_arg}: {e}")
                    error_codes.append("WIZARD_UPDATE_FAILED")

        # Add questions
        if add_questions:
            for q in add_questions:
                add_open_question(
                    session,
                    question_id=q.get("question_id", f"q_{len(session['open_questions'])+1}"),
                    question=q.get("question", ""),
                    severity=q.get("severity", "non_blocking"),
                    context=q.get("context"),
                    base_dir=base_dir,
                )

        # Add evidences
        if add_evidences:
            for ev in add_evidences:
                add_evidence(
                    session,
                    evidence_id=ev.get("evidence_id", f"ev_{len(session['evidence'])+1}"),
                    kind=ev.get("kind", "note"),
                    path=ev.get("path", ""),
                    content_hash_sha256=ev.get("content_hash_sha256"),
                    description=ev.get("description"),
                    base_dir=base_dir,
                )

        # Re-validate
        validate_session(session)

        # Save updated session
        session_path = save_session(session, base_dir)

        # Compute counts and flags
        counts = compute_counts_from_session(session)
        flags = compute_flags_from_session(session)

        # Determine status
        if errors:
            status = "blocked"
            blocked_reason = "INCOMPLETE_STEPS"
        else:
            status = "success"
            blocked_reason = None

        # Finalize runlog
        duration_ms = (time.time() - start_time) * 1000
        finalize_wizard_runlog(
            runlog,
            status=status,
            duration_ms=duration_ms,
            blocked_reason=blocked_reason,
            counts=counts,
            flags=flags,
            errors=errors,
            error_codes=error_codes,
        )

        # Save runlog
        runlog_path = get_session_dir(session_id, base_dir) / "wizard_runlog.json"
        with open(runlog_path, "w") as f:
            json.dump(runlog, f, indent=2)

        return WizardResult(
            success=len(errors) == 0,
            session_id=session_id,
            runlog=runlog,
            message=f"Session resumed: {session_id}",
            errors=errors,
            output_paths={
                "session": str(session_path),
                "runlog": str(runlog_path),
            },
        )

    except WizardSessionNotFoundError as e:
        errors.append(str(e))
        error_codes.append("WIZARD_SESSION_NOT_FOUND")

        duration_ms = (time.time() - start_time) * 1000
        finalize_wizard_runlog(
            runlog,
            status="invalid",
            duration_ms=duration_ms,
            blocked_reason="SCHEMA_INVALID",
            errors=errors,
            error_codes=error_codes,
        )

        return WizardResult(
            success=False,
            session_id=session_id,
            runlog=runlog,
            message="Session not found",
            errors=errors,
        )

    except WizardSessionValidationError as e:
        errors.append(str(e))
        error_codes.append("WIZARD_SCHEMA_INVALID")

        duration_ms = (time.time() - start_time) * 1000
        finalize_wizard_runlog(
            runlog,
            status="invalid",
            duration_ms=duration_ms,
            blocked_reason="SCHEMA_INVALID",
            errors=errors,
            error_codes=error_codes,
        )

        return WizardResult(
            success=False,
            session_id=session_id,
            runlog=runlog,
            message="Session validation failed",
            errors=errors,
        )


# =============================================================================
# Command: export
# =============================================================================


def _load_blueprint_for_export(
    blueprint_id: str,
    registry_dir: Optional[Path] = None,
) -> Tuple[Optional[dict], Optional[str], List[str], List[str]]:
    """Load and verify a blueprint for export.

    Args:
        blueprint_id: ID of the blueprint to load
        registry_dir: Optional registry directory

    Returns:
        Tuple of (blueprint, content_hash, errors, error_codes)
    """
    # Import here to avoid circular imports
    from blueprints.registry_v1 import (
        verify_registry,
        get_blueprint_path,
        load_registry,
        RegistryIntegrityError,
        RegistryValidationError,
    )
    from blueprints.blueprint_v1 import (
        load_blueprint,
        BlueprintValidationError,
    )
    from blueprints.registry_v1 import compute_content_hash

    errors = []
    error_codes = []

    try:
        # Verify registry integrity first
        verify_registry(registry_dir)
    except RegistryIntegrityError as e:
        errors.append(f"Registry integrity check failed: {e}")
        error_codes.append("WIZARD_REGISTRY_INTEGRITY_ERROR")
        return None, None, errors, error_codes
    except FileNotFoundError as e:
        errors.append(f"Registry not found: {e}")
        error_codes.append("WIZARD_REGISTRY_NOT_FOUND")
        return None, None, errors, error_codes

    # Get blueprint path from registry
    blueprint_path = get_blueprint_path(blueprint_id, registry_dir)
    if blueprint_path is None:
        errors.append(f"Blueprint not found in registry: {blueprint_id}")
        error_codes.append("WIZARD_BLUEPRINT_NOT_FOUND")
        return None, None, errors, error_codes

    try:
        blueprint = load_blueprint(blueprint_path)
        content_hash = compute_content_hash(blueprint)
        return blueprint, content_hash, errors, error_codes
    except BlueprintValidationError as e:
        errors.append(f"Blueprint validation failed: {e}")
        error_codes.append("WIZARD_BLUEPRINT_INVALID")
        return None, None, errors, error_codes


def cmd_export(
    session_id: str,
    include_md: bool = True,
    blueprint_id: Optional[str] = None,
    base_dir: Optional[Path] = None,
    registry_dir: Optional[Path] = None,
) -> WizardResult:
    """Export session as IDL Draft v1.

    Args:
        session_id: The session ID to export
        include_md: Whether to also export markdown
        blueprint_id: Optional blueprint ID for pre-filling (overrides session.blueprint_ref)
        base_dir: Base directory for sessions
        registry_dir: Optional registry directory for blueprints

    Returns:
        WizardResult with export info
    """
    start_time = time.time()
    errors = []
    error_codes = []

    # Create runlog
    runlog = new_wizard_runlog(session_id, "export")

    try:
        # Load and validate session
        session = load_session(session_id, base_dir)

        # Determine blueprint to use (CLI arg takes precedence over session.blueprint_ref)
        effective_blueprint_id = blueprint_id
        if effective_blueprint_id is None:
            blueprint_ref = session.get("blueprint_ref")
            if blueprint_ref:
                effective_blueprint_id = blueprint_ref.get("blueprint_id")

        # Load blueprint if specified
        blueprint = None
        content_hash = None
        if effective_blueprint_id:
            blueprint, content_hash, bp_errors, bp_error_codes = _load_blueprint_for_export(
                effective_blueprint_id, registry_dir
            )
            errors.extend(bp_errors)
            error_codes.extend(bp_error_codes)

        # Check for blocking issues
        has_blocking = has_blocking_issues(session)

        # Generate draft from session
        draft_obj = session_to_draft(session)
        draft_dict = draft_obj.to_dict()

        # Apply blueprint if loaded (fill-missing-only)
        diff_summary = None
        if blueprint is not None:
            before_draft = draft_dict.copy()
            draft_dict = apply_blueprint_to_idl_draft(draft_dict, blueprint)
            diff_summary = compute_blueprint_diff_summary(before_draft, draft_dict)

            # Set blueprint info in runlog
            set_runlog_blueprint(
                runlog,
                blueprint_id=effective_blueprint_id,
                content_hash_sha256=content_hash,
                diff_summary=diff_summary,
            )

        # Validate with GATE 1
        validation = validate_draft(draft_dict)
        if not validation.valid:
            for err in validation.errors:
                errors.append(f"GATE1: {err.message} at {err.location}")
                error_codes.append("WIZARD_DRAFT_INVALID")

        # Export draft to file
        export_dir = get_export_dir(session_id, base_dir)
        export_dir.mkdir(parents=True, exist_ok=True)

        json_path = export_dir / IDL_DRAFT_JSON
        with open(json_path, "w") as f:
            json.dump(draft_dict, f, indent=2, ensure_ascii=False)

        # Export markdown if requested
        md_path = None
        if include_md:
            from .export import export_draft_md
            md_path = export_draft_md(session, draft_dict, base_dir)

        # Compute counts and flags
        counts = compute_counts_from_session(session)
        flags = compute_flags_from_session(session)

        # Determine final status
        if has_blocking:
            status = "blocked"
            blocked_reason = "OPEN_QUESTIONS_BLOCKING"
            errors.append(f"Export blocked: {counts['open_questions_blocking']} blocking open questions")
            error_codes.append("WIZARD_BLOCKED_QUESTIONS")
        elif not validation.valid:
            status = "blocked"
            blocked_reason = "SCHEMA_INVALID"
        else:
            status = "success"
            blocked_reason = None

        # Finalize runlog
        duration_ms = (time.time() - start_time) * 1000
        finalize_wizard_runlog(
            runlog,
            status=status,
            duration_ms=duration_ms,
            blocked_reason=blocked_reason,
            counts=counts,
            flags=flags,
            errors=errors,
            error_codes=error_codes,
        )

        # Save runlog
        runlog_path = get_session_dir(session_id, base_dir) / "wizard_runlog.json"
        with open(runlog_path, "w") as f:
            json.dump(runlog, f, indent=2)

        output_paths = {
            "draft_json": str(json_path),
            "runlog": str(runlog_path),
        }
        if md_path:
            output_paths["draft_md"] = str(md_path)

        # Note: Even when blocked, we still export the draft (with open_questions)
        return WizardResult(
            success=(status == "success"),
            session_id=session_id,
            runlog=runlog,
            message=f"Export {'blocked' if has_blocking else 'completed'}: {session_id}",
            errors=errors,
            output_paths=output_paths,
        )

    except WizardSessionNotFoundError as e:
        errors.append(str(e))
        error_codes.append("WIZARD_SESSION_NOT_FOUND")

        duration_ms = (time.time() - start_time) * 1000
        finalize_wizard_runlog(
            runlog,
            status="invalid",
            duration_ms=duration_ms,
            blocked_reason="SCHEMA_INVALID",
            errors=errors,
            error_codes=error_codes,
        )

        return WizardResult(
            success=False,
            session_id=session_id,
            runlog=runlog,
            message="Session not found",
            errors=errors,
        )

    except WizardSessionValidationError as e:
        errors.append(str(e))
        error_codes.append("WIZARD_SCHEMA_INVALID")

        duration_ms = (time.time() - start_time) * 1000
        finalize_wizard_runlog(
            runlog,
            status="invalid",
            duration_ms=duration_ms,
            blocked_reason="SCHEMA_INVALID",
            errors=errors,
            error_codes=error_codes,
        )

        return WizardResult(
            success=False,
            session_id=session_id,
            runlog=runlog,
            message="Session validation failed",
            errors=errors,
        )


# =============================================================================
# CLI Entry Point
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for wizard CLI."""
    parser = argparse.ArgumentParser(
        prog="wizard",
        description="Wizard CLI for IDL Draft generation",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # start command
    start_parser = subparsers.add_parser("start", help="Start a new wizard session")
    start_parser.add_argument("--project", required=True, help="Project name")
    start_parser.add_argument("--domain", required=True, help="Business domain")
    start_parser.add_argument("--objective", help="Project objective")
    start_parser.add_argument("--base-dir", type=Path, help="Base directory")

    # resume command
    resume_parser = subparsers.add_parser("resume", help="Resume an existing session")
    resume_parser.add_argument("session_id", help="Session ID to resume")
    resume_parser.add_argument(
        "--set",
        action="append",
        dest="set_fields",
        metavar="step.field=value",
        help="Set a field value (can be repeated)",
    )
    resume_parser.add_argument("--base-dir", type=Path, help="Base directory")

    # export command
    export_parser = subparsers.add_parser("export", help="Export session as IDL Draft")
    export_parser.add_argument("session_id", help="Session ID to export")
    export_parser.add_argument("--no-md", action="store_true", help="Skip markdown export")
    export_parser.add_argument(
        "--blueprint-id",
        help="Blueprint ID for pre-filling draft (fill-missing-only)",
    )
    export_parser.add_argument("--base-dir", type=Path, help="Base directory")
    export_parser.add_argument("--registry-dir", type=Path, help="Blueprint registry directory")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for wizard CLI.

    Args:
        args: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = create_parser()
    parsed = parser.parse_args(args)

    if parsed.command is None:
        parser.print_help()
        return 1

    result: WizardResult

    if parsed.command == "start":
        result = cmd_start(
            project=parsed.project,
            domain=parsed.domain,
            objective=getattr(parsed, "objective", None),
            base_dir=getattr(parsed, "base_dir", None),
        )

    elif parsed.command == "resume":
        result = cmd_resume(
            session_id=parsed.session_id,
            set_fields=getattr(parsed, "set_fields", None),
            base_dir=getattr(parsed, "base_dir", None),
        )

    elif parsed.command == "export":
        result = cmd_export(
            session_id=parsed.session_id,
            include_md=not getattr(parsed, "no_md", False),
            blueprint_id=getattr(parsed, "blueprint_id", None),
            base_dir=getattr(parsed, "base_dir", None),
            registry_dir=getattr(parsed, "registry_dir", None),
        )

    else:
        parser.print_help()
        return 1

    # Output result
    print(json.dumps(result.to_dict(), indent=2))

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
