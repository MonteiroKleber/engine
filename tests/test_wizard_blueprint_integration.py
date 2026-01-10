"""Tests for Wizard Blueprint Integration (E5.3).

Tests cover:
1) export without blueprint: identical behavior to original
2) export with blueprint and empty draft: draft receives sections from blueprint
3) export with blueprint and draft already filled by user: blueprint does NOT overwrite
4) list ordering in blueprint does not affect final result (canonicalization)
5) wizard_runlog includes blueprint + hash + diff_summary when used
"""

import json
import tempfile
from pathlib import Path

import pytest

from wizard.wizard_cli import cmd_start, cmd_export
from wizard.session import (
    load_session,
    save_session,
    update_session_field,
    add_open_question,
)
from wizard.export import (
    apply_blueprint_to_idl_draft,
    compute_blueprint_diff_summary,
    session_to_draft,
    _is_empty,
)
from wizard.wizard_runlog import validate_wizard_runlog
from blueprints.registry_v1 import (
    register_blueprint,
    create_empty_registry,
    save_registry,
    compute_content_hash,
)
from blueprints.blueprint_v1 import validate_blueprint
from idl.idl_draft_schema import DraftSchemaValidator


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_base_dir():
    """Create a temporary directory for test sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_registry_dir():
    """Create a temporary registry directory with empty registry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_dir = Path(tmpdir) / "registry"
        registry_dir.mkdir()
        (registry_dir / "blueprints").mkdir()
        # Create empty registry
        registry = create_empty_registry()
        save_registry(registry, registry_dir)
        yield registry_dir


@pytest.fixture
def sample_blueprint():
    """Return a sample blueprint dict."""
    return {
        "schema_version": "blueprint.v1",
        "blueprint_id": "healthcare.v1",
        "title": "Healthcare Blueprint",
        "domain": "healthcare",
        "version": "1.0.0",
        "compat": {
            "idl_draft_schema_version": "idl_draft.v1"
        },
        "defaults": {
            "actors": [
                {"id": "doctor", "role": "Medical professional"},
                {"id": "patient", "role": "Healthcare recipient"},
                {"id": "admin", "role": "System administrator"},
            ],
            "entities": [
                {
                    "id": "Patient",
                    "fields": [
                        {"name": "name", "type": "string", "required": True},
                        {"name": "dob", "type": "date", "required": True},
                    ]
                },
                {
                    "id": "Appointment",
                    "fields": [
                        {"name": "date", "type": "datetime", "required": True},
                        {"name": "patient_id", "type": "string", "required": True},
                    ]
                },
            ],
            "usecases": [
                {
                    "id": "schedule_appointment",
                    "actor": "patient",
                    "flow": [
                        {"step": 1, "action": "Select date and time"},
                        {"step": 2, "action": "Confirm appointment"},
                    ]
                }
            ],
            "integrations": [
                {"system": "ehr", "type": "api"},
            ],
            "nonfunctional": {
                "performance": "Response time < 2s",
                "security": "HIPAA compliant",
                "availability": "99.9% uptime",
            }
        }
    }


@pytest.fixture
def registered_blueprint(temp_registry_dir, sample_blueprint):
    """Register a sample blueprint and return its info."""
    # Save blueprint to file
    bp_path = temp_registry_dir / "healthcare.json"
    with open(bp_path, "w") as f:
        json.dump(sample_blueprint, f)

    # Register in registry
    entry = register_blueprint(bp_path, temp_registry_dir)
    return {
        "blueprint_id": entry["blueprint_id"],
        "content_hash": entry["content_hash_sha256"],
        "registry_dir": temp_registry_dir,
    }


# =============================================================================
# Test: _is_empty helper
# =============================================================================


class TestIsEmpty:
    """Test the _is_empty helper function."""

    def test_none_is_empty(self):
        """[export] None is considered empty."""
        assert _is_empty(None) is True

    def test_empty_string_is_empty(self):
        """[export] Empty string is considered empty."""
        assert _is_empty("") is True

    def test_empty_list_is_empty(self):
        """[export] Empty list is considered empty."""
        assert _is_empty([]) is True

    def test_empty_dict_is_empty(self):
        """[export] Empty dict is considered empty."""
        assert _is_empty({}) is True

    def test_unknown_is_empty(self):
        """[export] 'unknown' string is considered empty."""
        assert _is_empty("unknown") is True

    def test_tbd_is_empty(self):
        """[export] 'TBD' string is considered empty."""
        assert _is_empty("TBD") is True

    def test_non_empty_string(self):
        """[export] Non-empty string is not empty."""
        assert _is_empty("hello") is False

    def test_non_empty_list(self):
        """[export] Non-empty list is not empty."""
        assert _is_empty([1, 2, 3]) is False


# =============================================================================
# Test: apply_blueprint_to_idl_draft
# =============================================================================


class TestApplyBlueprintToIdlDraft:
    """Test blueprint application to IDL Draft."""

    def test_fill_empty_actors(self, sample_blueprint):
        """[export] Blueprint fills empty actors section."""
        draft = {
            "schema_version": "idl_draft.v1",
            "project": "Test",
            "source": "wizard",
            "actors": [],
            "entities": [],
            "use_cases": [],
            "integrations": [],
        }

        result = apply_blueprint_to_idl_draft(draft, sample_blueprint)

        assert len(result["actors"]) == 3
        assert result["actors"][0]["id"] == "doctor"

    def test_fill_empty_entities(self, sample_blueprint):
        """[export] Blueprint fills empty entities section."""
        draft = {
            "schema_version": "idl_draft.v1",
            "project": "Test",
            "source": "wizard",
            "actors": [],
            "entities": [],
            "use_cases": [],
            "integrations": [],
        }

        result = apply_blueprint_to_idl_draft(draft, sample_blueprint)

        assert len(result["entities"]) == 2
        assert result["entities"][0]["id"] == "Patient"

    def test_does_not_overwrite_existing_actors(self, sample_blueprint):
        """[export] Blueprint does NOT overwrite existing actors."""
        draft = {
            "schema_version": "idl_draft.v1",
            "project": "Test",
            "source": "wizard",
            "actors": [{"id": "custom_actor", "role": "Custom role"}],
            "entities": [],
            "use_cases": [],
            "integrations": [],
        }

        result = apply_blueprint_to_idl_draft(draft, sample_blueprint)

        # Should keep user's actors, not replace with blueprint
        assert len(result["actors"]) == 1
        assert result["actors"][0]["id"] == "custom_actor"

    def test_does_not_overwrite_existing_entities(self, sample_blueprint):
        """[export] Blueprint does NOT overwrite existing entities."""
        draft = {
            "schema_version": "idl_draft.v1",
            "project": "Test",
            "source": "wizard",
            "actors": [],
            "entities": [{"id": "CustomEntity", "fields": []}],
            "use_cases": [],
            "integrations": [],
        }

        result = apply_blueprint_to_idl_draft(draft, sample_blueprint)

        # Should keep user's entities
        assert len(result["entities"]) == 1
        assert result["entities"][0]["id"] == "CustomEntity"

    def test_fill_nonfunctional_individual_fields(self, sample_blueprint):
        """[export] Blueprint fills individual missing nonfunctional fields."""
        draft = {
            "schema_version": "idl_draft.v1",
            "project": "Test",
            "source": "wizard",
            "actors": [],
            "entities": [],
            "use_cases": [],
            "integrations": [],
            "non_functional": {
                "performance": "Custom performance requirement",
                # security and availability are missing
            }
        }

        result = apply_blueprint_to_idl_draft(draft, sample_blueprint)

        # Performance should be kept (user input)
        assert result["non_functional"]["performance"] == "Custom performance requirement"
        # Security should be filled from blueprint
        assert result["non_functional"]["security"] == "HIPAA compliant"
        # Availability should be filled from blueprint
        assert result["non_functional"]["availability"] == "99.9% uptime"

    def test_does_not_mutate_original_draft(self, sample_blueprint):
        """[export] apply_blueprint does not mutate original draft."""
        draft = {
            "schema_version": "idl_draft.v1",
            "project": "Test",
            "source": "wizard",
            "actors": [],
            "entities": [],
            "use_cases": [],
            "integrations": [],
        }

        original_actors = draft["actors"]
        result = apply_blueprint_to_idl_draft(draft, sample_blueprint)

        # Original should still be empty
        assert len(draft["actors"]) == 0
        assert draft["actors"] is original_actors
        # Result should have actors
        assert len(result["actors"]) == 3


# =============================================================================
# Test: compute_blueprint_diff_summary
# =============================================================================


class TestComputeBlueprintDiffSummary:
    """Test diff summary computation."""

    def test_no_changes_empty_summary(self):
        """[export] No changes produces empty summary."""
        draft = {
            "actors": [{"id": "existing"}],
            "entities": [{"id": "Entity"}],
            "use_cases": [],
            "integrations": [],
        }

        summary = compute_blueprint_diff_summary(draft, draft)

        assert summary["filled_fields"] == 0
        assert summary["filled_sections"] == []

    def test_filled_actors_in_summary(self, sample_blueprint):
        """[export] Filled actors appears in summary."""
        before = {
            "actors": [],
            "entities": [],
            "use_cases": [],
            "integrations": [],
        }
        after = apply_blueprint_to_idl_draft(before, sample_blueprint)

        summary = compute_blueprint_diff_summary(before, after)

        assert "actors" in summary["filled_sections"]
        assert summary["filled_fields"] >= 3  # 3 actors

    def test_filled_nonfunctional_in_summary(self, sample_blueprint):
        """[export] Filled nonfunctional appears in summary."""
        before = {
            "actors": [{"id": "existing"}],  # Not empty, won't be filled
            "entities": [{"id": "Entity"}],  # Not empty
            "use_cases": [],
            "integrations": [],
            "non_functional": None,  # Empty, will be filled
        }
        after = apply_blueprint_to_idl_draft(before, sample_blueprint)

        summary = compute_blueprint_diff_summary(before, after)

        assert "non_functional" in summary["filled_sections"]
        # Should count nonfunctional fields
        assert summary["filled_fields"] >= 3  # performance, security, availability

    def test_summary_sections_sorted(self, sample_blueprint):
        """[export] Summary sections are sorted alphabetically."""
        before = {
            "actors": [],
            "entities": [],
            "use_cases": [],
            "integrations": [],
        }
        after = apply_blueprint_to_idl_draft(before, sample_blueprint)

        summary = compute_blueprint_diff_summary(before, after)

        # Check sections are sorted
        assert summary["filled_sections"] == sorted(summary["filled_sections"])


# =============================================================================
# Test: Export without Blueprint (original behavior)
# =============================================================================


class TestExportWithoutBlueprint:
    """Test that export without blueprint works identically to original."""

    def test_export_without_blueprint_generates_draft(self, temp_base_dir):
        """[wizard_cli] Export without blueprint generates valid draft."""
        # Create session
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Add some data
        session = load_session(session_id, temp_base_dir)
        update_session_field(
            session, "actors", "actors_list",
            [{"id": "user", "role": "End user"}],
            temp_base_dir,
        )
        save_session(session, temp_base_dir)

        # Export without blueprint
        result = cmd_export(
            session_id=session_id,
            base_dir=temp_base_dir,
        )

        assert result.success is True

        # Load and validate draft
        draft_path = Path(result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        assert draft["actors"][0]["id"] == "user"
        assert draft["source"] == "wizard"

        # Runlog should not have blueprint info
        assert result.runlog.get("blueprint") is None

    def test_export_without_blueprint_runlog_valid(self, temp_base_dir):
        """[wizard_cli] Export without blueprint produces valid runlog."""
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
        assert result.runlog["blueprint"] is None


# =============================================================================
# Test: Export with Blueprint (empty draft)
# =============================================================================


class TestExportWithBlueprintEmptyDraft:
    """Test export with blueprint when draft is empty."""

    def test_blueprint_fills_empty_draft(
        self, temp_base_dir, registered_blueprint
    ):
        """[wizard_cli] Blueprint fills empty draft sections."""
        # Create session with no data
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        # Export with blueprint
        result = cmd_export(
            session_id=start_result.session_id,
            blueprint_id=registered_blueprint["blueprint_id"],
            base_dir=temp_base_dir,
            registry_dir=registered_blueprint["registry_dir"],
        )

        assert result.success is True

        # Load draft
        draft_path = Path(result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        # Should have blueprint data
        assert len(draft["actors"]) == 3
        assert len(draft["entities"]) == 2
        # Actors are sorted by id (canonicalized)
        actor_ids = [a["id"] for a in draft["actors"]]
        assert sorted(actor_ids) == ["admin", "doctor", "patient"]

    def test_blueprint_info_in_runlog(
        self, temp_base_dir, registered_blueprint
    ):
        """[wizard_cli] Runlog includes blueprint info when used."""
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        result = cmd_export(
            session_id=start_result.session_id,
            blueprint_id=registered_blueprint["blueprint_id"],
            base_dir=temp_base_dir,
            registry_dir=registered_blueprint["registry_dir"],
        )

        # Check runlog has blueprint info
        assert result.runlog["blueprint"] is not None
        bp_info = result.runlog["blueprint"]

        assert bp_info["blueprint_id"] == "healthcare.v1"
        assert len(bp_info["content_hash_sha256"]) == 64
        assert "diff_summary" in bp_info
        assert bp_info["diff_summary"]["filled_fields"] > 0

    def test_draft_passes_gate1(
        self, temp_base_dir, registered_blueprint
    ):
        """[wizard_cli] Draft with blueprint data passes GATE 1."""
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )

        result = cmd_export(
            session_id=start_result.session_id,
            blueprint_id=registered_blueprint["blueprint_id"],
            base_dir=temp_base_dir,
            registry_dir=registered_blueprint["registry_dir"],
        )

        # Load and validate with GATE 1
        draft_path = Path(result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        validator = DraftSchemaValidator()
        validation = validator.validate(draft)

        assert validation.valid is True, f"GATE 1 errors: {[e.to_dict() for e in validation.errors]}"


# =============================================================================
# Test: Export with Blueprint (draft already filled)
# =============================================================================


class TestExportWithBlueprintFilledDraft:
    """Test that blueprint does NOT overwrite user data."""

    def test_user_actors_not_overwritten(
        self, temp_base_dir, registered_blueprint
    ):
        """[wizard_cli] User actors are NOT overwritten by blueprint."""
        # Create session with user data
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Add user's actors
        session = load_session(session_id, temp_base_dir)
        update_session_field(
            session, "actors", "actors_list",
            [{"id": "my_custom_actor", "role": "My custom role"}],
            temp_base_dir,
        )
        save_session(session, temp_base_dir)

        # Export with blueprint
        result = cmd_export(
            session_id=session_id,
            blueprint_id=registered_blueprint["blueprint_id"],
            base_dir=temp_base_dir,
            registry_dir=registered_blueprint["registry_dir"],
        )

        # Load draft
        draft_path = Path(result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        # User's actors should be preserved
        assert len(draft["actors"]) == 1
        assert draft["actors"][0]["id"] == "my_custom_actor"

    def test_user_entities_not_overwritten(
        self, temp_base_dir, registered_blueprint
    ):
        """[wizard_cli] User entities are NOT overwritten by blueprint."""
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Add user's entities
        session = load_session(session_id, temp_base_dir)
        update_session_field(
            session, "entities", "entities_list",
            [{"id": "MyEntity", "fields": [{"name": "myfield", "type": "string"}]}],
            temp_base_dir,
        )
        save_session(session, temp_base_dir)

        # Export with blueprint
        result = cmd_export(
            session_id=session_id,
            blueprint_id=registered_blueprint["blueprint_id"],
            base_dir=temp_base_dir,
            registry_dir=registered_blueprint["registry_dir"],
        )

        # Load draft
        draft_path = Path(result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        # User's entities should be preserved
        assert len(draft["entities"]) == 1
        assert draft["entities"][0]["id"] == "MyEntity"

    def test_mixed_empty_and_filled_sections(
        self, temp_base_dir, registered_blueprint
    ):
        """[wizard_cli] Blueprint fills only empty sections, not filled ones."""
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Add only actors, leave entities empty
        session = load_session(session_id, temp_base_dir)
        update_session_field(
            session, "actors", "actors_list",
            [{"id": "my_actor", "role": "My role"}],
            temp_base_dir,
        )
        save_session(session, temp_base_dir)

        # Export with blueprint
        result = cmd_export(
            session_id=session_id,
            blueprint_id=registered_blueprint["blueprint_id"],
            base_dir=temp_base_dir,
            registry_dir=registered_blueprint["registry_dir"],
        )

        # Load draft
        draft_path = Path(result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        # Actors should be user's (not overwritten)
        assert len(draft["actors"]) == 1
        assert draft["actors"][0]["id"] == "my_actor"

        # Entities should be from blueprint (was empty)
        assert len(draft["entities"]) == 2
        entity_ids = [e["id"] for e in draft["entities"]]
        assert sorted(entity_ids) == ["Appointment", "Patient"]


# =============================================================================
# Test: Canonicalization (order independence)
# =============================================================================


class TestBlueprintCanonicalization:
    """Test that blueprint ordering does not affect result."""

    def test_actors_order_does_not_affect_hash(self, temp_registry_dir):
        """[export] Actor ordering in blueprint does not affect content hash."""
        # Blueprint with actors in one order
        bp1 = {
            "schema_version": "blueprint.v1",
            "blueprint_id": "test.v1",
            "title": "Test",
            "domain": "test",
            "version": "1.0.0",
            "compat": {"idl_draft_schema_version": "idl_draft.v1"},
            "defaults": {
                "actors": [
                    {"id": "z_actor"},
                    {"id": "a_actor"},
                    {"id": "m_actor"},
                ]
            }
        }

        # Same blueprint with actors in different order
        bp2 = {
            "schema_version": "blueprint.v1",
            "blueprint_id": "test.v1",
            "title": "Test",
            "domain": "test",
            "version": "1.0.0",
            "compat": {"idl_draft_schema_version": "idl_draft.v1"},
            "defaults": {
                "actors": [
                    {"id": "a_actor"},
                    {"id": "m_actor"},
                    {"id": "z_actor"},
                ]
            }
        }

        # Hashes should be the same after canonicalization
        hash1 = compute_content_hash(bp1)
        hash2 = compute_content_hash(bp2)

        assert hash1 == hash2


# =============================================================================
# Test: Blocking Questions Still Block
# =============================================================================


class TestBlockingQuestionsWithBlueprint:
    """Test that blocking questions still block even with blueprint."""

    def test_blocking_questions_block_export(
        self, temp_base_dir, registered_blueprint
    ):
        """[wizard_cli] Blocking questions still block export with blueprint."""
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
            question="What is the main entity?",
            severity="blocking",
            base_dir=temp_base_dir,
        )
        save_session(session, temp_base_dir)

        # Export with blueprint
        result = cmd_export(
            session_id=session_id,
            blueprint_id=registered_blueprint["blueprint_id"],
            base_dir=temp_base_dir,
            registry_dir=registered_blueprint["registry_dir"],
        )

        # Should be blocked
        assert result.success is False
        assert result.runlog["final_status"] == "blocked"
        assert result.runlog["blocked_reason"] == "OPEN_QUESTIONS_BLOCKING"

        # But blueprint info should still be in runlog
        assert result.runlog["blueprint"] is not None

        # And draft should still be exported (with blueprint data)
        assert "draft_json" in result.output_paths


# =============================================================================
# Test: Session blueprint_ref
# =============================================================================


class TestSessionBlueprintRef:
    """Test using blueprint from session.blueprint_ref."""

    def test_uses_session_blueprint_ref(
        self, temp_base_dir, registered_blueprint
    ):
        """[wizard_cli] Export uses session.blueprint_ref if no --blueprint-id."""
        start_result = cmd_start(
            project="TestProject",
            domain="healthcare",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        # Add blueprint_ref to session
        session = load_session(session_id, temp_base_dir)
        session["blueprint_ref"] = {
            "blueprint_id": registered_blueprint["blueprint_id"],
            "registry_hash": None,
        }
        save_session(session, temp_base_dir)

        # Export without --blueprint-id (should use session.blueprint_ref)
        result = cmd_export(
            session_id=session_id,
            base_dir=temp_base_dir,
            registry_dir=registered_blueprint["registry_dir"],
        )

        # Should have used blueprint
        assert result.runlog["blueprint"] is not None
        assert result.runlog["blueprint"]["blueprint_id"] == "healthcare.v1"

    def test_cli_blueprint_overrides_session(
        self, temp_base_dir, temp_registry_dir
    ):
        """[wizard_cli] --blueprint-id overrides session.blueprint_ref."""
        # Register two blueprints
        bp1 = {
            "schema_version": "blueprint.v1",
            "blueprint_id": "bp1.v1",
            "title": "Blueprint 1",
            "domain": "test",
            "version": "1.0.0",
            "compat": {"idl_draft_schema_version": "idl_draft.v1"},
            "defaults": {"actors": [{"id": "bp1_actor"}]}
        }
        bp2 = {
            "schema_version": "blueprint.v1",
            "blueprint_id": "bp2.v1",
            "title": "Blueprint 2",
            "domain": "test",
            "version": "1.0.0",
            "compat": {"idl_draft_schema_version": "idl_draft.v1"},
            "defaults": {"actors": [{"id": "bp2_actor"}]}
        }

        for bp in [bp1, bp2]:
            bp_path = temp_registry_dir / f"{bp['blueprint_id']}.json"
            with open(bp_path, "w") as f:
                json.dump(bp, f)
            register_blueprint(bp_path, temp_registry_dir)

        # Create session with blueprint_ref pointing to bp1
        start_result = cmd_start(
            project="TestProject",
            domain="test",
            base_dir=temp_base_dir,
        )
        session_id = start_result.session_id

        session = load_session(session_id, temp_base_dir)
        session["blueprint_ref"] = {"blueprint_id": "bp1.v1", "registry_hash": None}
        save_session(session, temp_base_dir)

        # Export with --blueprint-id=bp2.v1 (should override)
        result = cmd_export(
            session_id=session_id,
            blueprint_id="bp2.v1",
            base_dir=temp_base_dir,
            registry_dir=temp_registry_dir,
        )

        # Should have used bp2, not bp1
        assert result.runlog["blueprint"]["blueprint_id"] == "bp2.v1"

        # Load draft and verify
        draft_path = Path(result.output_paths["draft_json"])
        with open(draft_path) as f:
            draft = json.load(f)

        assert draft["actors"][0]["id"] == "bp2_actor"


# =============================================================================
# Test: Registry Integrity Verification
# =============================================================================


class TestRegistryIntegrity:
    """Test that registry integrity is verified before using blueprint."""

    def test_export_fails_if_registry_not_found(self, temp_base_dir):
        """[wizard_cli] Export fails gracefully if registry not found."""
        start_result = cmd_start(
            project="TestProject",
            domain="test",
            base_dir=temp_base_dir,
        )

        # Try to export with nonexistent registry
        result = cmd_export(
            session_id=start_result.session_id,
            blueprint_id="nonexistent.v1",
            base_dir=temp_base_dir,
            registry_dir=Path("/nonexistent/registry"),
        )

        # Should still complete but with errors (integrity check fails for missing registry)
        assert any(
            code in result.runlog["error_codes"]
            for code in ["WIZARD_REGISTRY_NOT_FOUND", "WIZARD_REGISTRY_INTEGRITY_ERROR"]
        )

    def test_export_fails_if_blueprint_not_in_registry(
        self, temp_base_dir, temp_registry_dir
    ):
        """[wizard_cli] Export fails gracefully if blueprint not in registry."""
        start_result = cmd_start(
            project="TestProject",
            domain="test",
            base_dir=temp_base_dir,
        )

        # Try to export with blueprint ID that doesn't exist
        result = cmd_export(
            session_id=start_result.session_id,
            blueprint_id="nonexistent.v1",
            base_dir=temp_base_dir,
            registry_dir=temp_registry_dir,
        )

        # Should have error about blueprint not found
        assert "WIZARD_BLUEPRINT_NOT_FOUND" in result.runlog["error_codes"]
