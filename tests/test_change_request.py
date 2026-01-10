"""Tests for IDL Change Request v1 schema and helpers.

Tests cover:
- Schema validation (valid CR passes, invalid fails with SCHEMA prefix)
- Enum validation (risk.level, scope.target, invariants[].severity)
- Canonicalization (stable ordering)
- Hash computation (changes with content, not with volatile)
- Helper functions
"""

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from change_requests import (
    CR_SCHEMA_VERSION,
    CRValidationError,
    load_cr,
    validate_cr,
    canonicalize_cr,
    cr_hash_sha256,
    create_cr,
    get_cr_id,
    get_previous_episode_id,
    get_risk_level,
    get_target,
    get_entities_affected,
    get_usecases_affected,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def valid_cr():
    """Return a valid change request dict."""
    return {
        "schema_version": "idl_change_request.v1",
        "change_request_id": "cr-001",
        "previous_episode_id": "ep-001",
        "requested_by": {
            "display_name": "John Doe",
            "role": "Developer",
            "org": "Acme Corp",
        },
        "reason": "Add new field to User entity for compliance",
        "scope": {
            "target": "backend",
            "summary": "Add phone_number field to User entity",
            "entities_affected": ["User", "UserProfile"],
            "usecases_affected": ["UC001-CreateUser", "UC002-UpdateUser"],
        },
        "invariants": [
            {
                "name": "user_email_unique",
                "description": "User email must remain unique",
                "severity": "must",
            },
            {
                "name": "phone_format_valid",
                "description": "Phone number should be in E.164 format",
                "severity": "should",
            },
        ],
        "acceptance_criteria": [
            "Phone number field accepts valid E.164 format",
            "Existing users are not affected",
            "API returns phone in user response",
        ],
        "risk": {
            "level": "low",
            "notes": "Additive change, no breaking changes expected",
        },
        "attachments": [
            {
                "kind": "doc",
                "ref": "RFC-123",
                "content_hash_sha256": None,
            },
        ],
    }


@pytest.fixture
def minimal_cr():
    """Return a minimal valid change request dict."""
    return {
        "schema_version": "idl_change_request.v1",
        "change_request_id": "cr-minimal",
        "previous_episode_id": "ep-base",
        "requested_by": {
            "display_name": "Admin",
            "role": "Admin",
        },
        "reason": "Minor fix",
        "scope": {
            "target": "api",
            "summary": "Fix typo",
            "entities_affected": [],
            "usecases_affected": [],
        },
        "invariants": [],
        "acceptance_criteria": [],
        "risk": {
            "level": "low",
        },
        "attachments": [],
    }


# =============================================================================
# Test Validation - Valid CRs
# =============================================================================


class TestValidCR:
    """Tests for valid change request validation."""

    def test_valid_cr_passes(self, valid_cr):
        """[cr_v1] Valid CR passes validation."""
        validate_cr(valid_cr)  # Should not raise

    def test_minimal_cr_passes(self, minimal_cr):
        """[cr_v1] Minimal valid CR passes validation."""
        validate_cr(minimal_cr)  # Should not raise

    def test_all_targets_valid(self, minimal_cr):
        """[cr_v1] All target enum values are valid."""
        valid_targets = ["frontend", "backend", "db", "api", "rbac", "infra", "docs"]
        for target in valid_targets:
            minimal_cr["scope"]["target"] = target
            validate_cr(minimal_cr)  # Should not raise

    def test_all_risk_levels_valid(self, minimal_cr):
        """[cr_v1] All risk level enum values are valid."""
        valid_levels = ["low", "medium", "high"]
        for level in valid_levels:
            minimal_cr["risk"]["level"] = level
            validate_cr(minimal_cr)  # Should not raise

    def test_all_severity_values_valid(self, minimal_cr):
        """[cr_v1] All invariant severity enum values are valid."""
        valid_severities = ["must", "should"]
        for severity in valid_severities:
            minimal_cr["invariants"] = [
                {"name": "test", "description": "test", "severity": severity}
            ]
            validate_cr(minimal_cr)  # Should not raise

    def test_all_attachment_kinds_valid(self, minimal_cr):
        """[cr_v1] All attachment kind enum values are valid."""
        valid_kinds = ["link", "doc", "diff", "note"]
        for kind in valid_kinds:
            minimal_cr["attachments"] = [{"kind": kind, "ref": "test"}]
            validate_cr(minimal_cr)  # Should not raise

    def test_attachment_with_hash(self, minimal_cr):
        """[cr_v1] Attachment with content_hash_sha256 is valid."""
        minimal_cr["attachments"] = [
            {
                "kind": "doc",
                "ref": "spec.md",
                "content_hash_sha256": "sha256:" + "a" * 64,
            }
        ]
        validate_cr(minimal_cr)  # Should not raise

    def test_volatile_section_allowed(self, minimal_cr):
        """[cr_v1] Volatile section is allowed."""
        minimal_cr["volatile"] = {"timestamp": "2024-01-15T10:30:00Z"}
        validate_cr(minimal_cr)  # Should not raise

    def test_volatile_null_allowed(self, minimal_cr):
        """[cr_v1] Volatile section can be null."""
        minimal_cr["volatile"] = None
        validate_cr(minimal_cr)  # Should not raise


# =============================================================================
# Test Validation - Invalid CRs
# =============================================================================


class TestInvalidCR:
    """Tests for invalid change request validation."""

    def test_missing_schema_version_fails(self, valid_cr):
        """[cr_v1] Missing schema_version fails with SCHEMA prefix."""
        del valid_cr["schema_version"]
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_wrong_schema_version_fails(self, valid_cr):
        """[cr_v1] Wrong schema_version fails."""
        valid_cr["schema_version"] = "idl_change_request.v2"
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_missing_change_request_id_fails(self, valid_cr):
        """[cr_v1] Missing change_request_id fails."""
        del valid_cr["change_request_id"]
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_empty_change_request_id_fails(self, valid_cr):
        """[cr_v1] Empty change_request_id fails."""
        valid_cr["change_request_id"] = ""
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_missing_previous_episode_id_fails(self, valid_cr):
        """[cr_v1] Missing previous_episode_id fails."""
        del valid_cr["previous_episode_id"]
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_missing_reason_fails(self, valid_cr):
        """[cr_v1] Missing reason fails."""
        del valid_cr["reason"]
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_invalid_target_enum_fails(self, valid_cr):
        """[cr_v1] Invalid target enum fails with SCHEMA prefix."""
        valid_cr["scope"]["target"] = "invalid_target"
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_invalid_risk_level_enum_fails(self, valid_cr):
        """[cr_v1] Invalid risk.level enum fails with SCHEMA prefix."""
        valid_cr["risk"]["level"] = "critical"
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_invalid_severity_enum_fails(self, valid_cr):
        """[cr_v1] Invalid invariant severity enum fails with SCHEMA prefix."""
        valid_cr["invariants"][0]["severity"] = "critical"
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_invalid_attachment_kind_fails(self, valid_cr):
        """[cr_v1] Invalid attachment kind enum fails."""
        valid_cr["attachments"] = [{"kind": "invalid", "ref": "test"}]
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_invalid_hash_format_fails(self, valid_cr):
        """[cr_v1] Invalid content_hash_sha256 format fails."""
        valid_cr["attachments"] = [
            {"kind": "doc", "ref": "test", "content_hash_sha256": "invalid"}
        ]
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_extra_top_level_property_fails(self, valid_cr):
        """[cr_v1] Extra top-level property fails (additionalProperties: false)."""
        valid_cr["extra_field"] = "not allowed"
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_missing_requested_by_fails(self, valid_cr):
        """[cr_v1] Missing requested_by fails."""
        del valid_cr["requested_by"]
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)

    def test_missing_requester_display_name_fails(self, valid_cr):
        """[cr_v1] Missing requester display_name fails."""
        del valid_cr["requested_by"]["display_name"]
        with pytest.raises(CRValidationError) as exc:
            validate_cr(valid_cr)
        assert "SCHEMA:" in str(exc.value)


# =============================================================================
# Test Canonicalization
# =============================================================================


class TestCanonicalizeCR:
    """Tests for change request canonicalization."""

    def test_removes_volatile_section(self, valid_cr):
        """[cr_v1] Canonicalization removes volatile section."""
        valid_cr["volatile"] = {"timestamp": "2024-01-15T10:30:00Z"}

        canonical = canonicalize_cr(valid_cr)

        assert "volatile" not in canonical

    def test_sorts_entities_affected(self, valid_cr):
        """[cr_v1] Canonicalization sorts entities_affected."""
        valid_cr["scope"]["entities_affected"] = ["Zebra", "Apple", "Mango"]

        canonical = canonicalize_cr(valid_cr)

        assert canonical["scope"]["entities_affected"] == ["Apple", "Mango", "Zebra"]

    def test_sorts_usecases_affected(self, valid_cr):
        """[cr_v1] Canonicalization sorts usecases_affected."""
        valid_cr["scope"]["usecases_affected"] = ["UC003", "UC001", "UC002"]

        canonical = canonicalize_cr(valid_cr)

        assert canonical["scope"]["usecases_affected"] == ["UC001", "UC002", "UC003"]

    def test_sorts_acceptance_criteria(self, valid_cr):
        """[cr_v1] Canonicalization sorts acceptance_criteria."""
        valid_cr["acceptance_criteria"] = ["Zebra test", "Apple test", "Mango test"]

        canonical = canonicalize_cr(valid_cr)

        assert canonical["acceptance_criteria"] == [
            "Apple test",
            "Mango test",
            "Zebra test",
        ]

    def test_sorts_invariants_by_name(self, valid_cr):
        """[cr_v1] Canonicalization sorts invariants by name."""
        valid_cr["invariants"] = [
            {"name": "z_invariant", "description": "Z", "severity": "must"},
            {"name": "a_invariant", "description": "A", "severity": "should"},
            {"name": "m_invariant", "description": "M", "severity": "must"},
        ]

        canonical = canonicalize_cr(valid_cr)

        assert canonical["invariants"][0]["name"] == "a_invariant"
        assert canonical["invariants"][1]["name"] == "m_invariant"
        assert canonical["invariants"][2]["name"] == "z_invariant"

    def test_sorts_attachments(self, valid_cr):
        """[cr_v1] Canonicalization sorts attachments by kind and ref."""
        valid_cr["attachments"] = [
            {"kind": "note", "ref": "note1"},
            {"kind": "doc", "ref": "doc1"},
            {"kind": "doc", "ref": "doc0"},
        ]

        canonical = canonicalize_cr(valid_cr)

        assert canonical["attachments"][0]["ref"] == "doc0"
        assert canonical["attachments"][1]["ref"] == "doc1"
        assert canonical["attachments"][2]["ref"] == "note1"

    def test_does_not_mutate_original(self, valid_cr):
        """[cr_v1] Canonicalization does not mutate original."""
        valid_cr["volatile"] = {"timestamp": "2024-01-15T10:30:00Z"}
        original_entities = valid_cr["scope"]["entities_affected"].copy()

        canonicalize_cr(valid_cr)

        assert "volatile" in valid_cr  # Original unchanged
        assert valid_cr["scope"]["entities_affected"] == original_entities

    def test_empty_arrays_handled(self, minimal_cr):
        """[cr_v1] Empty arrays are handled correctly."""
        canonical = canonicalize_cr(minimal_cr)

        assert canonical["scope"]["entities_affected"] == []
        assert canonical["scope"]["usecases_affected"] == []
        assert canonical["acceptance_criteria"] == []
        assert canonical["invariants"] == []

    def test_canonical_output_is_deterministic(self, valid_cr):
        """[cr_v1] Canonical output is deterministic across calls."""
        canonical1 = canonicalize_cr(valid_cr)
        canonical2 = canonicalize_cr(valid_cr)

        json1 = json.dumps(canonical1, sort_keys=True)
        json2 = json.dumps(canonical2, sort_keys=True)

        assert json1 == json2


# =============================================================================
# Test Hash Computation
# =============================================================================


class TestCRHash:
    """Tests for change request hash computation."""

    def test_hash_has_sha256_prefix(self, valid_cr):
        """[cr_v1] Hash has sha256: prefix."""
        hash_result = cr_hash_sha256(valid_cr)

        assert hash_result.startswith("sha256:")
        assert len(hash_result) == 7 + 64  # "sha256:" + 64 hex chars

    def test_hash_is_deterministic(self, valid_cr):
        """[cr_v1] Hash is deterministic across calls."""
        hash1 = cr_hash_sha256(valid_cr)
        hash2 = cr_hash_sha256(valid_cr)

        assert hash1 == hash2

    def test_hash_changes_with_content(self, valid_cr):
        """[cr_v1] Hash changes when non-volatile content changes."""
        hash1 = cr_hash_sha256(valid_cr)

        valid_cr["reason"] = "Different reason"
        hash2 = cr_hash_sha256(valid_cr)

        assert hash1 != hash2

    def test_hash_unchanged_with_volatile(self, valid_cr):
        """[cr_v1] Hash does NOT change when only volatile.timestamp changes."""
        hash1 = cr_hash_sha256(valid_cr)

        valid_cr["volatile"] = {"timestamp": "2024-01-15T10:30:00Z"}
        hash2 = cr_hash_sha256(valid_cr)

        valid_cr["volatile"] = {"timestamp": "2024-12-25T00:00:00Z"}
        hash3 = cr_hash_sha256(valid_cr)

        assert hash1 == hash2 == hash3

    def test_hash_unchanged_with_reordering(self, valid_cr):
        """[cr_v1] Hash is stable regardless of array ordering."""
        valid_cr["scope"]["entities_affected"] = ["B", "A", "C"]
        hash1 = cr_hash_sha256(valid_cr)

        valid_cr["scope"]["entities_affected"] = ["C", "A", "B"]
        hash2 = cr_hash_sha256(valid_cr)

        valid_cr["scope"]["entities_affected"] = ["A", "B", "C"]
        hash3 = cr_hash_sha256(valid_cr)

        assert hash1 == hash2 == hash3

    def test_hash_different_for_different_crs(self, valid_cr, minimal_cr):
        """[cr_v1] Different CRs produce different hashes."""
        hash1 = cr_hash_sha256(valid_cr)
        hash2 = cr_hash_sha256(minimal_cr)

        assert hash1 != hash2


# =============================================================================
# Test Load Function
# =============================================================================


class TestLoadCR:
    """Tests for load_cr function."""

    def test_load_valid_cr(self, valid_cr):
        """[cr_v1] Loading valid CR file works."""
        with TemporaryDirectory() as tmpdir:
            cr_path = Path(tmpdir) / "cr.json"
            with open(cr_path, "w") as f:
                json.dump(valid_cr, f)

            loaded = load_cr(cr_path)

            assert loaded["change_request_id"] == valid_cr["change_request_id"]

    def test_load_nonexistent_file_raises(self):
        """[cr_v1] Loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_cr(Path("/nonexistent/path.json"))

    def test_load_invalid_json_raises(self):
        """[cr_v1] Loading invalid JSON raises CRValidationError."""
        with TemporaryDirectory() as tmpdir:
            cr_path = Path(tmpdir) / "invalid.json"
            with open(cr_path, "w") as f:
                f.write("not valid json")

            with pytest.raises(CRValidationError) as exc:
                load_cr(cr_path)
            assert "Invalid JSON" in str(exc.value)

    def test_load_invalid_cr_raises(self):
        """[cr_v1] Loading invalid CR raises CRValidationError."""
        with TemporaryDirectory() as tmpdir:
            cr_path = Path(tmpdir) / "invalid_cr.json"
            with open(cr_path, "w") as f:
                json.dump({"invalid": "cr"}, f)

            with pytest.raises(CRValidationError) as exc:
                load_cr(cr_path)
            assert "SCHEMA:" in str(exc.value)


# =============================================================================
# Test Create Function
# =============================================================================


class TestCreateCR:
    """Tests for create_cr helper function."""

    def test_create_minimal_cr(self):
        """[cr_v1] Creating minimal CR produces valid structure."""
        cr = create_cr(
            change_request_id="cr-test",
            previous_episode_id="ep-base",
            requester_name="Admin",
            requester_role="Admin",
            reason="Test change",
            target="api",
            summary="Test summary",
        )

        validate_cr(cr)  # Should not raise
        assert cr["change_request_id"] == "cr-test"
        assert cr["previous_episode_id"] == "ep-base"
        assert cr["requested_by"]["display_name"] == "Admin"

    def test_create_full_cr(self):
        """[cr_v1] Creating full CR with all options works."""
        cr = create_cr(
            change_request_id="cr-full",
            previous_episode_id="ep-001",
            requester_name="John",
            requester_role="Dev",
            reason="Full test",
            target="backend",
            summary="Full summary",
            risk_level="high",
            requester_org="Acme",
            entities_affected=["User"],
            usecases_affected=["UC001"],
            invariants=[{"name": "test", "description": "test", "severity": "must"}],
            acceptance_criteria=["Criterion 1"],
            risk_notes="High risk notes",
            attachments=[{"kind": "doc", "ref": "test.md"}],
        )

        validate_cr(cr)  # Should not raise
        assert cr["risk"]["level"] == "high"
        assert cr["requested_by"]["org"] == "Acme"
        assert len(cr["scope"]["entities_affected"]) == 1
        assert cr["scope"]["entities_affected"][0] == "User"


# =============================================================================
# Test Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_cr_id(self, valid_cr):
        """[cr_v1] get_cr_id returns correct value."""
        assert get_cr_id(valid_cr) == "cr-001"

    def test_get_previous_episode_id(self, valid_cr):
        """[cr_v1] get_previous_episode_id returns correct value."""
        assert get_previous_episode_id(valid_cr) == "ep-001"

    def test_get_risk_level(self, valid_cr):
        """[cr_v1] get_risk_level returns correct value."""
        assert get_risk_level(valid_cr) == "low"

    def test_get_target(self, valid_cr):
        """[cr_v1] get_target returns correct value."""
        assert get_target(valid_cr) == "backend"

    def test_get_entities_affected(self, valid_cr):
        """[cr_v1] get_entities_affected returns correct list."""
        entities = get_entities_affected(valid_cr)
        assert "User" in entities
        assert "UserProfile" in entities

    def test_get_usecases_affected(self, valid_cr):
        """[cr_v1] get_usecases_affected returns correct list."""
        usecases = get_usecases_affected(valid_cr)
        assert "UC001-CreateUser" in usecases
        assert "UC002-UpdateUser" in usecases

    def test_helpers_handle_missing_fields(self):
        """[cr_v1] Helper functions handle missing fields gracefully."""
        empty_cr = {}

        assert get_cr_id(empty_cr) == ""
        assert get_previous_episode_id(empty_cr) == ""
        assert get_risk_level(empty_cr) == "low"
        assert get_target(empty_cr) == ""
        assert get_entities_affected(empty_cr) == []
        assert get_usecases_affected(empty_cr) == []


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for CR workflow."""

    def test_full_workflow(self, valid_cr):
        """[cr_v1] Full workflow: validate -> canonicalize -> hash."""
        # Validate
        validate_cr(valid_cr)

        # Canonicalize
        canonical = canonicalize_cr(valid_cr)

        # Hash
        hash_result = cr_hash_sha256(valid_cr)

        assert "volatile" not in canonical
        assert hash_result.startswith("sha256:")

    def test_create_validate_hash_workflow(self):
        """[cr_v1] Create -> validate -> hash workflow."""
        cr = create_cr(
            change_request_id="cr-workflow",
            previous_episode_id="ep-base",
            requester_name="Tester",
            requester_role="QA",
            reason="Integration test",
            target="db",
            summary="Test database change",
            risk_level="medium",
            entities_affected=["Table1", "Table2"],
        )

        validate_cr(cr)
        hash1 = cr_hash_sha256(cr)

        # Add volatile - hash should not change
        cr["volatile"] = {"timestamp": "2024-01-15T10:30:00Z"}
        hash2 = cr_hash_sha256(cr)

        assert hash1 == hash2

    def test_save_load_hash_stability(self, valid_cr):
        """[cr_v1] Hash is stable after save/load cycle."""
        hash_before = cr_hash_sha256(valid_cr)

        with TemporaryDirectory() as tmpdir:
            cr_path = Path(tmpdir) / "cr.json"
            with open(cr_path, "w") as f:
                json.dump(valid_cr, f)

            loaded = load_cr(cr_path)
            hash_after = cr_hash_sha256(loaded)

        assert hash_before == hash_after
