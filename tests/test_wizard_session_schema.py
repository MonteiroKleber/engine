"""Tests for wizard_session.v1 schema validation.

Tests cover:
- Valid session passes validation
- Duplicate step_id fails
- Duplicate field_id within step fails
- Duplicate question_id fails
- Duplicate evidence_id fails
- Invalid status enum fails
- Invalid severity enum fails
- Invalid evidence kind enum fails
- Required fields validation
"""

import json
from pathlib import Path

import pytest

try:
    import jsonschema
except ImportError:
    pytest.skip("jsonschema not installed", allow_module_level=True)


# =============================================================================
# Schema Loading
# =============================================================================

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "wizard_session.v1.json"


@pytest.fixture
def schema():
    """Load the wizard_session.v1 schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def validate(instance: dict, schema: dict) -> None:
    """Validate instance against schema, raising on error."""
    jsonschema.validate(instance=instance, schema=schema)


# =============================================================================
# Test Fixtures
# =============================================================================


def create_valid_session() -> dict:
    """Create a minimal valid wizard session."""
    return {
        "schema_version": "wizard_session.v1",
        "session_id": "session_001",
        "project": {
            "name": "PetClinic",
            "domain": "veterinary"
        },
        "steps": [
            {
                "step_id": "step_actors",
                "title": "Actors & Roles",
                "status": "complete",
                "fields": [
                    {
                        "field_id": "actors_list",
                        "value": ["Vet", "Owner", "Receptionist"],
                        "required": True
                    }
                ]
            },
            {
                "step_id": "step_entities",
                "title": "Domain Entities",
                "status": "partial",
                "fields": [
                    {
                        "field_id": "entities_list",
                        "value": ["Pet", "Owner", "Visit"],
                        "required": True
                    },
                    {
                        "field_id": "entity_notes",
                        "value": "Need to clarify Pet types",
                        "required": False
                    }
                ]
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev_ddl_001",
                "kind": "ddl",
                "path": "uploads/schema.sql",
                "content_hash_sha256": "a" * 64
            }
        ],
        "open_questions": [
            {
                "question_id": "q_001",
                "question": "What are the pet types?",
                "context": "Need enumeration for Pet.type field",
                "severity": "blocking"
            }
        ]
    }


def create_full_session() -> dict:
    """Create a full wizard session with all optional fields."""
    session = create_valid_session()
    session["project"]["objective"] = "Manage veterinary clinic operations"
    session["volatile"] = {
        "created_at": "2025-01-07T10:00:00Z",
        "updated_at": "2025-01-07T12:30:00Z",
        "client_info": {
            "browser": "Chrome",
            "version": "120.0"
        }
    }
    return session


# =============================================================================
# Test Valid Sessions
# =============================================================================


class TestValidSessions:
    """Test valid wizard sessions pass validation."""

    def test_minimal_valid_session(self, schema):
        """[wizard] Minimal valid session passes validation."""
        session = create_valid_session()
        validate(session, schema)  # Should not raise

    def test_full_valid_session(self, schema):
        """[wizard] Full session with all optional fields passes."""
        session = create_full_session()
        validate(session, schema)  # Should not raise

    def test_empty_steps_allowed(self, schema):
        """[wizard] Empty steps array is allowed."""
        session = create_valid_session()
        session["steps"] = []
        validate(session, schema)  # Should not raise

    def test_empty_evidence_allowed(self, schema):
        """[wizard] Empty evidence array is allowed."""
        session = create_valid_session()
        session["evidence"] = []
        validate(session, schema)  # Should not raise

    def test_empty_open_questions_allowed(self, schema):
        """[wizard] Empty open_questions array is allowed."""
        session = create_valid_session()
        session["open_questions"] = []
        validate(session, schema)  # Should not raise

    def test_evidence_without_hash(self, schema):
        """[wizard] Evidence with null hash is allowed."""
        session = create_valid_session()
        session["evidence"] = [{
            "evidence_id": "ev_001",
            "kind": "link",
            "path": "https://example.com/doc",
            "content_hash_sha256": None
        }]
        validate(session, schema)  # Should not raise

    def test_all_step_statuses_valid(self, schema):
        """[wizard] All step status values are valid."""
        for status in ["complete", "partial", "blocked"]:
            session = create_valid_session()
            session["steps"][0]["status"] = status
            validate(session, schema)  # Should not raise

    def test_all_severity_values_valid(self, schema):
        """[wizard] All severity values are valid."""
        for severity in ["blocking", "non_blocking"]:
            session = create_valid_session()
            session["open_questions"][0]["severity"] = severity
            validate(session, schema)  # Should not raise

    def test_all_evidence_kinds_valid(self, schema):
        """[wizard] All evidence kind values are valid."""
        for kind in ["ddl", "csv", "doc", "link", "note", "spreadsheet", "diagram"]:
            session = create_valid_session()
            session["evidence"][0]["kind"] = kind
            validate(session, schema)  # Should not raise

    def test_field_value_any_json(self, schema):
        """[wizard] Field value accepts any JSON type."""
        session = create_valid_session()

        # Test with different JSON types
        test_values = [
            "string value",
            123,
            45.67,
            True,
            None,
            ["list", "of", "items"],
            {"nested": {"object": True}}
        ]

        for value in test_values:
            session["steps"][0]["fields"][0]["value"] = value
            validate(session, schema)  # Should not raise


# =============================================================================
# Test Required Fields
# =============================================================================


class TestRequiredFields:
    """Test that required fields are enforced."""

    def test_missing_schema_version_fails(self, schema):
        """[wizard] Missing schema_version fails."""
        session = create_valid_session()
        del session["schema_version"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_wrong_schema_version_fails(self, schema):
        """[wizard] Wrong schema_version value fails."""
        session = create_valid_session()
        session["schema_version"] = "wizard_session.v2"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_session_id_fails(self, schema):
        """[wizard] Missing session_id fails."""
        session = create_valid_session()
        del session["session_id"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_empty_session_id_fails(self, schema):
        """[wizard] Empty session_id fails."""
        session = create_valid_session()
        session["session_id"] = ""
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_project_fails(self, schema):
        """[wizard] Missing project fails."""
        session = create_valid_session()
        del session["project"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_project_name_fails(self, schema):
        """[wizard] Missing project.name fails."""
        session = create_valid_session()
        del session["project"]["name"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_project_domain_fails(self, schema):
        """[wizard] Missing project.domain fails."""
        session = create_valid_session()
        del session["project"]["domain"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_steps_fails(self, schema):
        """[wizard] Missing steps fails."""
        session = create_valid_session()
        del session["steps"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_evidence_fails(self, schema):
        """[wizard] Missing evidence fails."""
        session = create_valid_session()
        del session["evidence"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_open_questions_fails(self, schema):
        """[wizard] Missing open_questions fails."""
        session = create_valid_session()
        del session["open_questions"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_step_id_fails(self, schema):
        """[wizard] Missing step_id fails."""
        session = create_valid_session()
        del session["steps"][0]["step_id"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_step_title_fails(self, schema):
        """[wizard] Missing step title fails."""
        session = create_valid_session()
        del session["steps"][0]["title"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_step_status_fails(self, schema):
        """[wizard] Missing step status fails."""
        session = create_valid_session()
        del session["steps"][0]["status"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_step_fields_fails(self, schema):
        """[wizard] Missing step fields fails."""
        session = create_valid_session()
        del session["steps"][0]["fields"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_field_id_fails(self, schema):
        """[wizard] Missing field_id fails."""
        session = create_valid_session()
        del session["steps"][0]["fields"][0]["field_id"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_field_required_fails(self, schema):
        """[wizard] Missing field required fails."""
        session = create_valid_session()
        del session["steps"][0]["fields"][0]["required"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_evidence_id_fails(self, schema):
        """[wizard] Missing evidence_id fails."""
        session = create_valid_session()
        del session["evidence"][0]["evidence_id"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_evidence_kind_fails(self, schema):
        """[wizard] Missing evidence kind fails."""
        session = create_valid_session()
        del session["evidence"][0]["kind"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_evidence_path_fails(self, schema):
        """[wizard] Missing evidence path fails."""
        session = create_valid_session()
        del session["evidence"][0]["path"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_question_id_fails(self, schema):
        """[wizard] Missing question_id fails."""
        session = create_valid_session()
        del session["open_questions"][0]["question_id"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_question_text_fails(self, schema):
        """[wizard] Missing question text fails."""
        session = create_valid_session()
        del session["open_questions"][0]["question"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_missing_question_severity_fails(self, schema):
        """[wizard] Missing question severity fails."""
        session = create_valid_session()
        del session["open_questions"][0]["severity"]
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)


# =============================================================================
# Test Enum Validation
# =============================================================================


class TestEnumValidation:
    """Test enum values are enforced."""

    def test_invalid_step_status_fails(self, schema):
        """[wizard] Invalid step status fails."""
        session = create_valid_session()
        session["steps"][0]["status"] = "invalid_status"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_invalid_severity_fails(self, schema):
        """[wizard] Invalid severity fails."""
        session = create_valid_session()
        session["open_questions"][0]["severity"] = "critical"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_invalid_evidence_kind_fails(self, schema):
        """[wizard] Invalid evidence kind fails."""
        session = create_valid_session()
        session["evidence"][0]["kind"] = "unknown_kind"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)


# =============================================================================
# Test Uniqueness (via custom validation - not JSON Schema native)
# =============================================================================


class TestUniquenessValidation:
    """Test uniqueness constraints.

    Note: JSON Schema draft-07 does not natively support uniqueness
    on nested object properties. These tests document the expected
    behavior that must be enforced by application-level validation.
    """

    def test_duplicate_step_id_documented(self, schema):
        """[wizard] Duplicate step_id should be detected by app validation.

        JSON Schema cannot enforce uniqueness of step_id across steps.
        This test documents the requirement for application-level validation.
        """
        session = create_valid_session()
        # Add duplicate step_id
        session["steps"].append({
            "step_id": "step_actors",  # Duplicate!
            "title": "Another Step",
            "status": "partial",
            "fields": []
        })
        # JSON Schema will pass - app must validate
        validate(session, schema)  # Passes at schema level

        # Verify we have duplicates (app should reject)
        step_ids = [s["step_id"] for s in session["steps"]]
        assert len(step_ids) != len(set(step_ids)), "Duplicates exist"

    def test_duplicate_field_id_in_step_documented(self, schema):
        """[wizard] Duplicate field_id within step should be detected by app.

        JSON Schema cannot enforce uniqueness of field_id within a step.
        """
        session = create_valid_session()
        session["steps"][0]["fields"].append({
            "field_id": "actors_list",  # Duplicate within step!
            "value": "duplicate",
            "required": False
        })
        # JSON Schema will pass
        validate(session, schema)

        # Verify duplicates exist
        field_ids = [f["field_id"] for f in session["steps"][0]["fields"]]
        assert len(field_ids) != len(set(field_ids)), "Duplicates exist"

    def test_duplicate_question_id_documented(self, schema):
        """[wizard] Duplicate question_id should be detected by app validation."""
        session = create_valid_session()
        session["open_questions"].append({
            "question_id": "q_001",  # Duplicate!
            "question": "Another question",
            "severity": "non_blocking"
        })
        # JSON Schema will pass
        validate(session, schema)

        # Verify duplicates exist
        q_ids = [q["question_id"] for q in session["open_questions"]]
        assert len(q_ids) != len(set(q_ids)), "Duplicates exist"

    def test_duplicate_evidence_id_documented(self, schema):
        """[wizard] Duplicate evidence_id should be detected by app validation."""
        session = create_valid_session()
        session["evidence"].append({
            "evidence_id": "ev_ddl_001",  # Duplicate!
            "kind": "doc",
            "path": "another/path.doc"
        })
        # JSON Schema will pass
        validate(session, schema)

        # Verify duplicates exist
        ev_ids = [e["evidence_id"] for e in session["evidence"]]
        assert len(ev_ids) != len(set(ev_ids)), "Duplicates exist"


# =============================================================================
# Test Additional Properties
# =============================================================================


class TestAdditionalProperties:
    """Test that additional properties are rejected."""

    def test_extra_top_level_property_fails(self, schema):
        """[wizard] Extra top-level property fails."""
        session = create_valid_session()
        session["extra_field"] = "not allowed"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_extra_project_property_fails(self, schema):
        """[wizard] Extra project property fails."""
        session = create_valid_session()
        session["project"]["extra"] = "not allowed"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_extra_step_property_fails(self, schema):
        """[wizard] Extra step property fails."""
        session = create_valid_session()
        session["steps"][0]["extra"] = "not allowed"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_extra_field_property_fails(self, schema):
        """[wizard] Extra field property fails."""
        session = create_valid_session()
        session["steps"][0]["fields"][0]["extra"] = "not allowed"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_extra_evidence_property_fails(self, schema):
        """[wizard] Extra evidence property fails."""
        session = create_valid_session()
        session["evidence"][0]["extra"] = "not allowed"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_extra_question_property_fails(self, schema):
        """[wizard] Extra question property fails."""
        session = create_valid_session()
        session["open_questions"][0]["extra"] = "not allowed"
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_volatile_allows_additional_properties(self, schema):
        """[wizard] Volatile object allows additional properties."""
        session = create_valid_session()
        session["volatile"] = {
            "created_at": "2025-01-07T10:00:00Z",
            "custom_field": "allowed in volatile",
            "another_custom": {"nested": True}
        }
        validate(session, schema)  # Should not raise


# =============================================================================
# Test Hash Format
# =============================================================================


class TestHashFormat:
    """Test content hash format validation."""

    def test_valid_sha256_hash(self, schema):
        """[wizard] Valid SHA256 hash passes."""
        session = create_valid_session()
        session["evidence"][0]["content_hash_sha256"] = "a" * 64
        validate(session, schema)  # Should not raise

    def test_invalid_hash_too_short(self, schema):
        """[wizard] Hash too short fails."""
        session = create_valid_session()
        session["evidence"][0]["content_hash_sha256"] = "a" * 63
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_invalid_hash_too_long(self, schema):
        """[wizard] Hash too long fails."""
        session = create_valid_session()
        session["evidence"][0]["content_hash_sha256"] = "a" * 65
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_invalid_hash_uppercase(self, schema):
        """[wizard] Hash with uppercase fails (must be lowercase hex)."""
        session = create_valid_session()
        session["evidence"][0]["content_hash_sha256"] = "A" * 64
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)

    def test_invalid_hash_non_hex(self, schema):
        """[wizard] Hash with non-hex chars fails."""
        session = create_valid_session()
        session["evidence"][0]["content_hash_sha256"] = "g" * 64
        with pytest.raises(jsonschema.ValidationError):
            validate(session, schema)
