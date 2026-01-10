"""Wizard Export - Generate IDL Draft v1 from wizard session.

Converts a validated wizard_session.v1 into an idl_draft.v1 document.

Key rules:
- open_questions from wizard become open_questions in IDL Draft
- evidence becomes sources/notes in the draft
- Fields not provided use "unknown" or "TBD" as the draft allows
- Uses IDL Draft's own canonicalization (no parallel canonicalization)

Blueprint Integration (E5.3):
- Blueprints only PRE-FILL missing fields (fill-missing-only)
- User input from wizard_session has priority (never overwrite)
- open_questions continue blocking if severity=blocking
- Telemetry in wizard_runlog includes blueprint hash and diff_summary
"""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from idl.idl_draft_v1 import (
    IDLDraftV1,
    DraftSource,
    DraftActor,
    DraftEntity,
    DraftField,
    DraftUseCase,
    DraftFlowStep,
    DraftIntegration,
    DraftNonFunctional,
    UNKNOWN,
)
from idl.idl_draft_schema import DraftSchemaValidator, DraftValidationResult

from .session import (
    get_session_dir,
    validate_session,
    WizardSessionValidationError,
)


# =============================================================================
# Constants
# =============================================================================

EXPORT_DIR = "export"
IDL_DRAFT_JSON = "idl_draft.json"
IDL_DRAFT_MD = "idl_draft.md"


# =============================================================================
# Export Path Helpers
# =============================================================================


def get_export_dir(session_id: str, base_dir: Optional[Path] = None) -> Path:
    """Get the export directory for a session.

    Args:
        session_id: The session ID
        base_dir: Base directory

    Returns:
        Path to export directory
    """
    return get_session_dir(session_id, base_dir) / EXPORT_DIR


def get_draft_json_path(session_id: str, base_dir: Optional[Path] = None) -> Path:
    """Get the path to idl_draft.json.

    Args:
        session_id: The session ID
        base_dir: Base directory

    Returns:
        Path to idl_draft.json
    """
    return get_export_dir(session_id, base_dir) / IDL_DRAFT_JSON


def get_draft_md_path(session_id: str, base_dir: Optional[Path] = None) -> Path:
    """Get the path to idl_draft.md.

    Args:
        session_id: The session ID
        base_dir: Base directory

    Returns:
        Path to idl_draft.md
    """
    return get_export_dir(session_id, base_dir) / IDL_DRAFT_MD


# =============================================================================
# Field Extraction Helpers
# =============================================================================


def _get_step_field_value(
    session: dict,
    step_id: str,
    field_id: str,
    default: Any = None,
) -> Any:
    """Extract a field value from a session step.

    Args:
        session: The session dict
        step_id: The step ID
        field_id: The field ID
        default: Default value if not found

    Returns:
        Field value or default
    """
    for step in session.get("steps", []):
        if step.get("step_id") == step_id:
            for field in step.get("fields", []):
                if field.get("field_id") == field_id:
                    value = field.get("value")
                    return value if value is not None else default
    return default


def _extract_actors(session: dict) -> List[DraftActor]:
    """Extract actors from session.

    Args:
        session: The session dict

    Returns:
        List of DraftActor objects
    """
    actors_list = _get_step_field_value(session, "actors", "actors_list", [])

    actors = []
    for actor_data in actors_list:
        if isinstance(actor_data, str):
            # Simple string actor
            actors.append(DraftActor(id=actor_data, role=actor_data))
        elif isinstance(actor_data, dict):
            # Structured actor
            actors.append(DraftActor(
                id=actor_data.get("id", actor_data.get("name", UNKNOWN)),
                role=actor_data.get("role", actor_data.get("name", UNKNOWN)),
                permissions=actor_data.get("permissions", []),
            ))

    return actors


def _extract_entities(session: dict) -> List[DraftEntity]:
    """Extract entities from session.

    Args:
        session: The session dict

    Returns:
        List of DraftEntity objects
    """
    entities_list = _get_step_field_value(session, "entities", "entities_list", [])

    entities = []
    for entity_data in entities_list:
        if isinstance(entity_data, str):
            # Simple string entity - no fields
            entities.append(DraftEntity(id=entity_data, fields=[]))
        elif isinstance(entity_data, dict):
            # Structured entity
            fields = []
            for field_data in entity_data.get("fields", []):
                if isinstance(field_data, str):
                    fields.append(DraftField(name=field_data))
                elif isinstance(field_data, dict):
                    fields.append(DraftField(
                        name=field_data.get("name", UNKNOWN),
                        type=field_data.get("type", UNKNOWN),
                        required=field_data.get("required", UNKNOWN),
                    ))

            entities.append(DraftEntity(
                id=entity_data.get("id", entity_data.get("name", UNKNOWN)),
                fields=fields,
            ))

    return entities


def _extract_use_cases(session: dict) -> List[DraftUseCase]:
    """Extract use cases from session.

    Args:
        session: The session dict

    Returns:
        List of DraftUseCase objects
    """
    use_cases_list = _get_step_field_value(session, "use_cases", "use_cases_list", [])

    use_cases = []
    for uc_data in use_cases_list:
        if isinstance(uc_data, str):
            # Simple string use case
            use_cases.append(DraftUseCase(id=uc_data))
        elif isinstance(uc_data, dict):
            # Structured use case
            flow = []
            for i, step_data in enumerate(uc_data.get("flow", [])):
                if isinstance(step_data, str):
                    flow.append(DraftFlowStep(step=i + 1, action=step_data))
                elif isinstance(step_data, dict):
                    flow.append(DraftFlowStep(
                        step=step_data.get("step", i + 1),
                        action=step_data.get("action", ""),
                    ))

            use_cases.append(DraftUseCase(
                id=uc_data.get("id", uc_data.get("name", UNKNOWN)),
                actor=uc_data.get("actor", UNKNOWN),
                flow=flow,
            ))

    return use_cases


def _extract_integrations(session: dict) -> List[DraftIntegration]:
    """Extract integrations from session.

    Args:
        session: The session dict

    Returns:
        List of DraftIntegration objects
    """
    integrations_list = _get_step_field_value(
        session, "integrations", "integrations_list", []
    )

    integrations = []
    for integ_data in integrations_list:
        if isinstance(integ_data, str):
            integrations.append(DraftIntegration(system=integ_data))
        elif isinstance(integ_data, dict):
            integrations.append(DraftIntegration(
                system=integ_data.get("system", integ_data.get("name", UNKNOWN)),
                type=integ_data.get("type", UNKNOWN),
            ))

    return integrations


def _extract_nonfunctional(session: dict) -> Optional[DraftNonFunctional]:
    """Extract non-functional requirements from session.

    Args:
        session: The session dict

    Returns:
        DraftNonFunctional object or None
    """
    performance = _get_step_field_value(session, "nonfunctional", "performance")
    security = _get_step_field_value(session, "nonfunctional", "security")

    if performance is None and security is None:
        return None

    return DraftNonFunctional(
        performance=performance if performance else UNKNOWN,
        security=security if security else UNKNOWN,
    )


def _extract_assumptions(session: dict) -> List[str]:
    """Extract assumptions from session evidence notes.

    Args:
        session: The session dict

    Returns:
        List of assumption strings
    """
    assumptions = []

    # Look for evidence of type "note" as assumptions
    for evidence in session.get("evidence", []):
        if evidence.get("kind") == "note":
            desc = evidence.get("description", evidence.get("path", ""))
            if desc:
                assumptions.append(f"[From note {evidence.get('evidence_id')}] {desc}")

    return assumptions


def _extract_open_questions(session: dict) -> List[str]:
    """Extract open questions from session.

    Args:
        session: The session dict

    Returns:
        List of open question strings
    """
    questions = []

    for q in session.get("open_questions", []):
        question_text = q.get("question", "")
        severity = q.get("severity", "non_blocking")
        context = q.get("context", "")

        # Format: [BLOCKING] or [non-blocking] prefix
        prefix = "[BLOCKING]" if severity == "blocking" else "[non-blocking]"
        formatted = f"{prefix} {question_text}"
        if context:
            formatted += f" (Context: {context})"

        questions.append(formatted)

    return questions


# =============================================================================
# Blueprint Merge (Fill-Missing-Only)
# =============================================================================

# Values considered "empty" for fill-missing-only logic
_EMPTY_VALUES = (None, "", [], {}, "unknown", "TBD", UNKNOWN)


def _is_empty(value: Any) -> bool:
    """Check if a value is considered empty for fill-missing-only.

    Args:
        value: The value to check

    Returns:
        True if value is empty
    """
    if value in _EMPTY_VALUES:
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    if isinstance(value, dict) and len(value) == 0:
        return True
    return False


def _fill_nonfunctional(
    draft_nf: Optional[dict],
    blueprint_nf: Optional[dict]
) -> Optional[dict]:
    """Fill missing non-functional fields from blueprint.

    Only fills individual fields that are missing/empty.
    Does NOT replace existing values.

    Args:
        draft_nf: Non-functional from draft (may be None)
        blueprint_nf: Non-functional from blueprint (may be None)

    Returns:
        Merged non-functional dict or None
    """
    if blueprint_nf is None:
        return draft_nf

    if draft_nf is None:
        return deepcopy(blueprint_nf)

    result = deepcopy(draft_nf)

    # Fill only empty fields
    for key in ("performance", "security", "availability", "scalability"):
        if _is_empty(result.get(key)) and not _is_empty(blueprint_nf.get(key)):
            result[key] = blueprint_nf[key]

    return result


def apply_blueprint_to_idl_draft(draft: dict, blueprint: dict) -> dict:
    """Apply blueprint defaults to an IDL Draft (fill-missing-only).

    Rules:
    - Only fills sections that are empty in draft
    - Does NOT merge item-by-item in lists (no heuristics)
    - Exception: nonfunctional fills individual missing fields
    - User input from wizard always has priority

    Args:
        draft: The IDL Draft dict (from session_to_draft)
        blueprint: Validated blueprint dict

    Returns:
        New draft dict with blueprint defaults applied
    """
    result = deepcopy(draft)
    bp_defaults = blueprint.get("defaults", {})

    # Fill empty sections (whole-section replacement only)
    section_mappings = [
        ("actors", "actors"),
        ("entities", "entities"),
        ("use_cases", "usecases"),  # draft uses use_cases, blueprint uses usecases
        ("integrations", "integrations"),
    ]

    for draft_key, bp_key in section_mappings:
        draft_section = result.get(draft_key, [])
        bp_section = bp_defaults.get(bp_key, [])

        # Only fill if draft section is empty
        if _is_empty(draft_section) and not _is_empty(bp_section):
            result[draft_key] = deepcopy(bp_section)

    # Special handling for nonfunctional: fill individual fields
    result["non_functional"] = _fill_nonfunctional(
        result.get("non_functional"),
        bp_defaults.get("nonfunctional")
    )

    return result


def compute_blueprint_diff_summary(before: dict, after: dict) -> dict:
    """Compute a deterministic summary of changes from blueprint application.

    Args:
        before: Draft before blueprint application
        after: Draft after blueprint application

    Returns:
        Diff summary dict with:
        - filled_fields: count of fields that were filled
        - filled_sections: list of section names that were filled
    """
    filled_sections = []
    filled_fields = 0

    # Check list sections
    section_names = ["actors", "entities", "use_cases", "integrations"]
    for section in section_names:
        before_val = before.get(section, [])
        after_val = after.get(section, [])

        if _is_empty(before_val) and not _is_empty(after_val):
            filled_sections.append(section)
            # Count items as filled fields
            filled_fields += len(after_val)

    # Check nonfunctional fields
    before_nf = before.get("non_functional") or {}
    after_nf = after.get("non_functional") or {}

    nf_fields = ["performance", "security", "availability", "scalability"]
    nf_filled = False
    for field in nf_fields:
        if _is_empty(before_nf.get(field)) and not _is_empty(after_nf.get(field)):
            filled_fields += 1
            nf_filled = True

    if nf_filled:
        filled_sections.append("non_functional")

    # Sort sections for deterministic output
    filled_sections.sort()

    return {
        "filled_fields": filled_fields,
        "filled_sections": filled_sections,
    }


# =============================================================================
# IDL Draft Generation
# =============================================================================


def session_to_draft(session: dict) -> IDLDraftV1:
    """Convert a wizard session to an IDL Draft.

    Args:
        session: Validated wizard session dict

    Returns:
        IDLDraftV1 object
    """
    project_name = session.get("project", {}).get("name", UNKNOWN)

    draft = IDLDraftV1(
        project=project_name,
        source=DraftSource.WIZARD,
        actors=_extract_actors(session),
        entities=_extract_entities(session),
        use_cases=_extract_use_cases(session),
        integrations=_extract_integrations(session),
        non_functional=_extract_nonfunctional(session),
        assumptions=_extract_assumptions(session),
        open_questions=_extract_open_questions(session),
    )

    return draft


def validate_draft(draft_dict: dict) -> DraftValidationResult:
    """Validate an IDL Draft dict using GATE 1 validator.

    Args:
        draft_dict: The draft as a dict

    Returns:
        DraftValidationResult with validation status
    """
    validator = DraftSchemaValidator()
    return validator.validate(draft_dict)


# =============================================================================
# Export Functions
# =============================================================================


def export_draft_json(
    session: dict,
    base_dir: Optional[Path] = None,
) -> Tuple[Path, dict]:
    """Export session as IDL Draft JSON.

    Args:
        session: Validated wizard session dict
        base_dir: Base directory

    Returns:
        Tuple of (path to exported file, draft dict)
    """
    session_id = session["session_id"]

    # Convert to draft
    draft = session_to_draft(session)
    draft_dict = draft.to_dict()

    # Validate with GATE 1
    validation = validate_draft(draft_dict)
    if not validation.valid:
        # Include validation errors but still export
        # (draft is allowed to have issues, it's pre-canonical)
        pass

    # Create export directory
    export_dir = get_export_dir(session_id, base_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    draft_path = export_dir / IDL_DRAFT_JSON
    with open(draft_path, "w") as f:
        json.dump(draft_dict, f, indent=2, ensure_ascii=False)

    return draft_path, draft_dict


def export_draft_md(
    session: dict,
    draft_dict: dict,
    base_dir: Optional[Path] = None,
) -> Path:
    """Export IDL Draft as Markdown for human review.

    Args:
        session: The wizard session
        draft_dict: The draft dict
        base_dir: Base directory

    Returns:
        Path to exported markdown file
    """
    session_id = session["session_id"]
    project = session.get("project", {})

    lines = [
        f"# IDL Draft: {project.get('name', 'Unknown')}",
        "",
        f"**Domain:** {project.get('domain', 'Unknown')}",
        f"**Source:** wizard",
        f"**Session ID:** {session_id}",
        "",
    ]

    if project.get("objective"):
        lines.extend([
            "## Objective",
            "",
            project.get("objective"),
            "",
        ])

    # Actors
    actors = draft_dict.get("actors", [])
    if actors:
        lines.extend([
            "## Actors",
            "",
        ])
        for actor in actors:
            lines.append(f"- **{actor.get('id')}**: {actor.get('role', 'unknown')}")
        lines.append("")

    # Entities
    entities = draft_dict.get("entities", [])
    if entities:
        lines.extend([
            "## Entities",
            "",
        ])
        for entity in entities:
            lines.append(f"### {entity.get('id')}")
            lines.append("")
            fields = entity.get("fields", [])
            if fields:
                lines.append("| Field | Type | Required |")
                lines.append("|-------|------|----------|")
                for field in fields:
                    lines.append(
                        f"| {field.get('name')} | {field.get('type', 'unknown')} | {field.get('required', 'unknown')} |"
                    )
                lines.append("")

    # Use Cases
    use_cases = draft_dict.get("use_cases", [])
    if use_cases:
        lines.extend([
            "## Use Cases",
            "",
        ])
        for uc in use_cases:
            lines.append(f"### {uc.get('id')}")
            lines.append(f"**Actor:** {uc.get('actor', 'unknown')}")
            lines.append("")
            flow = uc.get("flow", [])
            if flow:
                lines.append("**Flow:**")
                for step in flow:
                    lines.append(f"{step.get('step')}. {step.get('action')}")
                lines.append("")

    # Integrations
    integrations = draft_dict.get("integrations", [])
    if integrations:
        lines.extend([
            "## Integrations",
            "",
        ])
        for integ in integrations:
            lines.append(f"- **{integ.get('system')}**: {integ.get('type', 'unknown')}")
        lines.append("")

    # Non-Functional
    nfr = draft_dict.get("non_functional")
    if nfr:
        lines.extend([
            "## Non-Functional Requirements",
            "",
            f"- **Performance:** {nfr.get('performance', 'unknown')}",
            f"- **Security:** {nfr.get('security', 'unknown')}",
            "",
        ])

    # Open Questions
    open_questions = draft_dict.get("open_questions", [])
    if open_questions:
        lines.extend([
            "## Open Questions",
            "",
        ])
        for q in open_questions:
            lines.append(f"- {q}")
        lines.append("")

    # Assumptions
    assumptions = draft_dict.get("assumptions", [])
    if assumptions:
        lines.extend([
            "## Assumptions",
            "",
        ])
        for a in assumptions:
            lines.append(f"- {a}")
        lines.append("")

    # Evidence from session
    evidence = session.get("evidence", [])
    if evidence:
        lines.extend([
            "## Evidence/Sources",
            "",
        ])
        for ev in evidence:
            kind = ev.get("kind", "unknown")
            path = ev.get("path", "")
            desc = ev.get("description", "")
            lines.append(f"- [{kind}] {path}" + (f" - {desc}" if desc else ""))
        lines.append("")

    # Write file
    export_dir = get_export_dir(session_id, base_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    md_path = export_dir / IDL_DRAFT_MD
    with open(md_path, "w") as f:
        f.write("\n".join(lines))

    return md_path


def export_session(
    session: dict,
    base_dir: Optional[Path] = None,
    include_md: bool = True,
) -> Tuple[Path, Path, dict, DraftValidationResult]:
    """Full export of session to IDL Draft.

    Args:
        session: The wizard session
        base_dir: Base directory
        include_md: Whether to also export markdown

    Returns:
        Tuple of (json_path, md_path, draft_dict, validation_result)
    """
    # Export JSON
    json_path, draft_dict = export_draft_json(session, base_dir)

    # Validate with GATE 1
    validation = validate_draft(draft_dict)

    # Export MD
    md_path = None
    if include_md:
        md_path = export_draft_md(session, draft_dict, base_dir)

    return json_path, md_path, draft_dict, validation
