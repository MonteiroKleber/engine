"""Tests for wizard CLI commands (start, resume, export).

Tests cover:
1) start creates valid session and runlog
2) resume with invalid session fails SCHEMA
3) export with blocking open_questions => blocked status
4) export generates idl_draft.json that passes GATE 1
"""

import json
import tempfile
from pathlib import Path

import pytest

from wizard.wizard_cli import cmd_start, cmd_resume, cmd_export
from wizard.session import (
    load_session,
    save_session,
    validate_session,
    add_open_question,
    update_session_field,
    get_session_path,
    WizardSessionValidationError,
)
from wizard.wizard_runlog import validate_wizard_runlog
from wizard.export import get_draft_json_path
from idl.idl_draft_schema import DraftSchemaValidator


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_base_dir():
    """Create a temporary directory for test sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# =============================================================================
# Test: start command
# =============================================================================


class TestCmdStart:
    """Test wizard start command."""

    def test_start_creates_valid_session(self, temp_base_dir):
        """[wizard_cli] start creates a valid session file."""
        result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        assert result.success is True
        assert result.session_id is not None

        # Verify session exists and is valid
        session = load_session(result.session_id, temp_base_dir)
        assert session["project"]["name"] == "TestProject"
        assert session["project"]["domain"] == "healthcare"
        assert session["schema_version"] == "wizard_session.v1"

    def test_start_creates_valid_runlog(self, temp_base_dir):
        """[wizard_cli] start creates a valid runlog."""
        result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        assert result.success is True
        runlog = result.runlog

        # Validate runlog
        validate_wizard_runlog(runlog)

        assert runlog["schema_version"] == "wizard_runlog.v1"
        assert runlog["mode"] == "start"
        assert runlog["final_status"] == "success"
        assert runlog["blocked_reason"] is None

    def test_start_with_objective(self, temp_base_dir):
        """[wizard_cli] start with objective includes it in session."""
        result = cmd_start(
            project="TestProject",
            domain="healthcare",
            objective="Build a patient management system",
            base_dir=temp_base_dir,
        )

        assert result.success is True
        session = load_session(result.session_id, temp_base_dir)
        assert session["project"].get("objective") == "Build a patient management system"

    def test_start_creates_output_files(self, temp_base_dir):
        """[wizard_cli] start creates session and runlog files."""
        result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        assert "session" in result.output_paths
        assert "runlog" in result.output_paths

        session_path = Path(result.output_paths["session"])
        runlog_path = Path(result.output_paths["runlog"])

        assert session_path.exists()
        assert runlog_path.exists()

    def test_start_runlog_counts_correct(self, temp_base_dir):
        """[wizard_cli] start runlog has correct initial counts."""
        result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        runlog = result.runlog
        counts = runlog["counts"]

        # Default session has 6 steps
        assert counts["steps_total"] == 6
        assert counts["steps_complete"] == 0
        assert counts["open_questions_total"] == 0
        assert counts["evidence_total"] == 0


# =============================================================================
# Test: resume command
# =============================================================================


class TestCmdResume:
    """Test wizard resume command."""

    def test_resume_loads_existing_session(self, temp_base_dir):
        """[wizard_cli] resume loads an existing session."""
        # First create a session
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Resume it
        result = cmd_resume(
            session_id=session_id,
            base_dir=temp_base_dir,
        )

        assert result.success is True
        assert result.session_id == session_id
        assert result.runlog["mode"] == "resume"

    def test_resume_with_set_fields(self, temp_base_dir):
        """[wizard_cli] resume with --set updates fields."""
        # Create session
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Resume with field update
        result = cmd_resume(
            session_id=session_id,
            set_fields=['actors.actors_list=["Admin", "Doctor", "Patient"]'],
            base_dir=temp_base_dir,
        )

        assert result.success is True

        # Verify field was updated
        session = load_session(session_id, temp_base_dir)
        actors_list = None
        for step in session["steps"]:
            if step["step_id"] == "actors":
                for field in step["fields"]:
                    if field["field_id"] == "actors_list":
                        actors_list = field["value"]
                        break

        assert actors_list == ["Admin", "Doctor", "Patient"]

    def test_resume_nonexistent_session_fails(self, temp_base_dir):
        """[wizard_cli] resume with nonexistent session fails."""
        result = cmd_resume(
            session_id="nonexistent-session-id",
            base_dir=temp_base_dir,
        )

        assert result.success is False
        assert result.runlog["final_status"] == "invalid"
        assert "WIZARD_SESSION_NOT_FOUND" in result.runlog["error_codes"]

    def test_resume_invalid_session_fails_schema(self, temp_base_dir):
        """[wizard_cli] resume with invalid session fails with SCHEMA prefix."""
        # Create a session
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Corrupt the session file
        session_path = get_session_path(session_id, temp_base_dir)
        with open(session_path, "w") as f:
            json.dump({"invalid": "session"}, f)

        # Try to resume
        result = cmd_resume(
            session_id=session_id,
            base_dir=temp_base_dir,
        )

        assert result.success is False
        assert result.runlog["final_status"] == "invalid"
        assert result.runlog["blocked_reason"] == "SCHEMA_INVALID"

        # Check for SCHEMA: prefix in errors
        assert any("SCHEMA:" in err for err in result.errors)

    def test_resume_creates_valid_runlog(self, temp_base_dir):
        """[wizard_cli] resume creates a valid runlog."""
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        result = cmd_resume(
            session_id=start_result.session_id,
            base_dir=temp_base_dir,
        )

        # Validate runlog
        validate_wizard_runlog(result.runlog)


# =============================================================================
# Test: export command
# =============================================================================


class TestCmdExport:
    """Test wizard export command."""

    def test_export_generates_draft_json(self, temp_base_dir):
        """[wizard_cli] export generates idl_draft.json."""
        # Create session
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Export
        result = cmd_export(
            session_id=session_id,
            base_dir=temp_base_dir,
        )

        assert "draft_json" in result.output_paths
        draft_path = Path(result.output_paths["draft_json"])
        assert draft_path.exists()

        # Verify it's valid JSON
        with open(draft_path) as f:
            draft = json.load(f)

        assert draft["schema_version"] == "idl_draft.v1"
        assert draft["source"] == "wizard"
        assert draft["project"] == "TestProject"

    def test_export_draft_passes_gate1(self, temp_base_dir):
        """[wizard_cli] export generates idl_draft.json that passes GATE 1."""
        # Create session with some data
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Add some entities
        session = load_session(session_id, temp_base_dir)
        update_session_field(
            session, "entities", "entities_list",
            [{"id": "Patient", "fields": [{"name": "name", "type": "string"}]}],
            temp_base_dir,
        )
        save_session(session, temp_base_dir)

        # Export
        result = cmd_export(
            session_id=session_id,
            base_dir=temp_base_dir,
        )

        # Load draft and validate with GATE 1
        draft_path = Path(result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        validator = DraftSchemaValidator()
        validation = validator.validate(draft)

        assert validation.valid is True, f"GATE 1 errors: {[e.to_dict() for e in validation.errors]}"

    def test_export_with_blocking_questions_blocked(self, temp_base_dir):
        """[wizard_cli] export with blocking open_questions => blocked status."""
        # Create session
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Add blocking question
        session = load_session(session_id, temp_base_dir)
        add_open_question(
            session,
            question_id="q1",
            question="What are the patient data fields?",
            severity="blocking",
            base_dir=temp_base_dir,
        )
        save_session(session, temp_base_dir)

        # Export
        result = cmd_export(
            session_id=session_id,
            base_dir=temp_base_dir,
        )

        # Should be blocked
        assert result.success is False
        assert result.runlog["final_status"] == "blocked"
        assert result.runlog["blocked_reason"] == "OPEN_QUESTIONS_BLOCKING"
        assert result.runlog["flags"]["has_blocking_open_questions"] is True

        # But draft should still be exported
        assert "draft_json" in result.output_paths
        draft_path = Path(result.output_paths["draft_json"])
        assert draft_path.exists()

    def test_export_includes_open_questions_in_draft(self, temp_base_dir):
        """[wizard_cli] export includes open_questions in draft."""
        # Create session
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Add questions
        session = load_session(session_id, temp_base_dir)
        add_open_question(
            session,
            question_id="q1",
            question="What are the patient data fields?",
            severity="blocking",
            context="For the Patient entity",
            base_dir=temp_base_dir,
        )
        add_open_question(
            session,
            question_id="q2",
            question="Is appointment scheduling needed?",
            severity="non_blocking",
            base_dir=temp_base_dir,
        )
        save_session(session, temp_base_dir)

        # Export
        result = cmd_export(
            session_id=session_id,
            base_dir=temp_base_dir,
        )

        # Check draft has questions
        draft_path = Path(result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        assert len(draft.get("open_questions", [])) == 2
        assert any("BLOCKING" in q for q in draft["open_questions"])

    def test_export_with_nonblocking_questions_success(self, temp_base_dir):
        """[wizard_cli] export with only non-blocking questions succeeds."""
        # Create session
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Add non-blocking question
        session = load_session(session_id, temp_base_dir)
        add_open_question(
            session,
            question_id="q1",
            question="Should we add audit logging?",
            severity="non_blocking",
            base_dir=temp_base_dir,
        )
        save_session(session, temp_base_dir)

        # Export
        result = cmd_export(
            session_id=session_id,
            base_dir=temp_base_dir,
        )

        # Should succeed (non-blocking questions don't block export)
        assert result.success is True
        assert result.runlog["final_status"] == "success"

    def test_export_creates_markdown(self, temp_base_dir):
        """[wizard_cli] export creates markdown file."""
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        result = cmd_export(
            session_id=start_result.session_id,
            include_md=True,
            base_dir=temp_base_dir,
        )

        assert "draft_md" in result.output_paths
        md_path = Path(result.output_paths["draft_md"])
        assert md_path.exists()

        content = md_path.read_text()
        assert "# IDL Draft: TestProject" in content

    def test_export_nonexistent_session_fails(self, temp_base_dir):
        """[wizard_cli] export nonexistent session fails."""
        result = cmd_export(
            session_id="nonexistent-session-id",
            base_dir=temp_base_dir,
        )

        assert result.success is False
        assert result.runlog["final_status"] == "invalid"

    def test_export_creates_valid_runlog(self, temp_base_dir):
        """[wizard_cli] export creates a valid runlog."""
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        result = cmd_export(
            session_id=start_result.session_id,
            base_dir=temp_base_dir,
        )

        # Validate runlog
        validate_wizard_runlog(result.runlog)


# =============================================================================
# Integration Tests
# =============================================================================


class TestWizardIntegration:
    """Integration tests for full wizard workflow."""

    def test_full_workflow_start_resume_export(self, temp_base_dir):
        """[wizard_cli] Full workflow: start -> resume -> export."""
        # 1. Start
        start_result = cmd_start(
            project="PetClinic",
            domain="veterinary",
            objective="Veterinary clinic management",
            base_dir=temp_base_dir,
        )
        assert start_result.success is True
        session_id = start_result.session_id

        # 2. Resume with updates
        resume_result = cmd_resume(
            session_id=session_id,
            set_fields=[
                'actors.actors_list=["Vet", "Owner", "Receptionist"]',
                'entities.entities_list=[{"id": "Pet"}, {"id": "Owner"}, {"id": "Visit"}]',
            ],
            base_dir=temp_base_dir,
        )
        assert resume_result.success is True

        # 3. Export
        export_result = cmd_export(
            session_id=session_id,
            base_dir=temp_base_dir,
        )
        assert export_result.success is True

        # Verify draft content
        draft_path = Path(export_result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        assert draft["project"] == "PetClinic"
        assert draft["source"] == "wizard"
        assert len(draft["actors"]) == 3
        assert len(draft["entities"]) == 3

        # Verify GATE 1 passes
        validator = DraftSchemaValidator()
        validation = validator.validate(draft)
        assert validation.valid is True

    def test_draft_usable_by_engine(self, temp_base_dir):
        """[wizard_cli] Exported draft can be used by engine (--input-mode draft)."""
        # Create and export
        start_result = cmd_start(
            project="TestProject",
            domain="test",
            base_dir=temp_base_dir,
        )

        # Add minimal content
        session = load_session(start_result.session_id, temp_base_dir)
        update_session_field(
            session, "actors", "actors_list",
            [{"id": "Admin", "role": "Administrator"}],
            temp_base_dir,
        )
        update_session_field(
            session, "entities", "entities_list",
            [{"id": "User", "fields": [{"name": "name", "type": "string"}]}],
            temp_base_dir,
        )
        save_session(session, temp_base_dir)

        export_result = cmd_export(
            session_id=start_result.session_id,
            base_dir=temp_base_dir,
        )

        # Verify draft is compatible with engine input
        draft_path = Path(export_result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        # Must have schema_version and source
        assert "schema_version" in draft
        assert draft["schema_version"] == "idl_draft.v1"
        assert "source" in draft
        assert "project" in draft

        # This draft would be accepted by main.py --input-mode draft
