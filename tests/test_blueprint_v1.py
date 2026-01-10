"""Tests for blueprint.v1 schema and module.

Tests cover:
- Valid blueprint passes validation
- Invalid enum/structure fails with "SCHEMA:" prefix
- Canonicalization is stable (same JSON with different order → canonical equal)
- Duplicate ID detection
"""

import json
import tempfile
from pathlib import Path

import pytest

from blueprints.blueprint_v1 import (
    validate_blueprint,
    canonicalize_blueprint,
    load_blueprint,
    get_blueprint_actors,
    get_blueprint_entities,
    get_blueprint_usecases,
    get_blueprint_integrations,
    get_blueprint_nonfunctional,
    is_compatible_with_draft,
    BlueprintValidationError,
    BLUEPRINT_SCHEMA_VERSION,
)


# =============================================================================
# Test Fixtures
# =============================================================================


def create_valid_blueprint() -> dict:
    """Create a minimal valid blueprint."""
    return {
        "schema_version": "blueprint.v1",
        "blueprint_id": "marketplace.v1.core",
        "title": "Marketplace Core Blueprint",
        "domain": "marketplace",
        "version": "1.0.0",
        "compat": {
            "idl_draft_schema_version": "idl_draft.v1",
            "idl_schema_version": "idl.v1"
        },
        "defaults": {
            "actors": [
                {"id": "Buyer", "role": "Customer who purchases products"},
                {"id": "Seller", "role": "Vendor who sells products"}
            ],
            "entities": [
                {
                    "id": "Product",
                    "fields": [
                        {"name": "name", "type": "string", "required": True},
                        {"name": "price", "type": "decimal", "required": True}
                    ]
                },
                {
                    "id": "Order",
                    "fields": [
                        {"name": "total", "type": "decimal"},
                        {"name": "status", "type": "string"}
                    ]
                }
            ],
            "usecases": [
                {
                    "id": "BrowseProducts",
                    "actor": "Buyer",
                    "flow": [
                        {"step": 1, "action": "View product catalog"},
                        {"step": 2, "action": "Filter by category"}
                    ]
                }
            ],
            "integrations": [
                {"system": "PaymentGateway", "type": "api"},
                {"system": "InventoryDB", "type": "db"}
            ],
            "nonfunctional": {
                "performance": "Response time < 200ms",
                "security": "PCI-DSS compliant"
            }
        },
        "notes": "Core marketplace blueprint for e-commerce platforms"
    }


def create_minimal_blueprint() -> dict:
    """Create a minimal valid blueprint with empty defaults."""
    return {
        "schema_version": "blueprint.v1",
        "blueprint_id": "minimal.v1",
        "title": "Minimal Blueprint",
        "domain": "test",
        "version": "1.0.0",
        "compat": {
            "idl_draft_schema_version": "idl_draft.v1"
        },
        "defaults": {}
    }


# =============================================================================
# Test Valid Blueprints
# =============================================================================


class TestValidBlueprints:
    """Test valid blueprints pass validation."""

    def test_valid_blueprint_passes(self):
        """[blueprint] Valid blueprint passes validation."""
        blueprint = create_valid_blueprint()
        validate_blueprint(blueprint)  # Should not raise

    def test_minimal_blueprint_passes(self):
        """[blueprint] Minimal blueprint with empty defaults passes."""
        blueprint = create_minimal_blueprint()
        validate_blueprint(blueprint)  # Should not raise

    def test_blueprint_without_notes(self):
        """[blueprint] Blueprint without notes passes."""
        blueprint = create_valid_blueprint()
        del blueprint["notes"]
        validate_blueprint(blueprint)  # Should not raise

    def test_blueprint_with_null_notes(self):
        """[blueprint] Blueprint with null notes passes."""
        blueprint = create_valid_blueprint()
        blueprint["notes"] = None
        validate_blueprint(blueprint)  # Should not raise

    def test_blueprint_with_only_actors(self):
        """[blueprint] Blueprint with only actors in defaults passes."""
        blueprint = create_minimal_blueprint()
        blueprint["defaults"]["actors"] = [{"id": "Admin", "role": "Administrator"}]
        validate_blueprint(blueprint)  # Should not raise

    def test_blueprint_with_only_entities(self):
        """[blueprint] Blueprint with only entities in defaults passes."""
        blueprint = create_minimal_blueprint()
        blueprint["defaults"]["entities"] = [{"id": "User"}]
        validate_blueprint(blueprint)  # Should not raise

    def test_all_integration_types_valid(self):
        """[blueprint] All integration types are valid."""
        for int_type in ["api", "db", "queue", "unknown"]:
            blueprint = create_minimal_blueprint()
            blueprint["defaults"]["integrations"] = [
                {"system": "External", "type": int_type}
            ]
            validate_blueprint(blueprint)  # Should not raise


# =============================================================================
# Test Required Fields
# =============================================================================


class TestRequiredFields:
    """Test required fields are enforced."""

    def test_missing_schema_version_fails(self):
        """[blueprint] Missing schema_version fails with SCHEMA prefix."""
        blueprint = create_valid_blueprint()
        del blueprint["schema_version"]
        with pytest.raises(BlueprintValidationError) as exc:
            validate_blueprint(blueprint)
        assert "SCHEMA:" in str(exc.value)

    def test_wrong_schema_version_fails(self):
        """[blueprint] Wrong schema_version fails."""
        blueprint = create_valid_blueprint()
        blueprint["schema_version"] = "blueprint.v2"
        with pytest.raises(BlueprintValidationError) as exc:
            validate_blueprint(blueprint)
        assert "SCHEMA:" in str(exc.value)

    def test_missing_blueprint_id_fails(self):
        """[blueprint] Missing blueprint_id fails."""
        blueprint = create_valid_blueprint()
        del blueprint["blueprint_id"]
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_invalid_blueprint_id_pattern_fails(self):
        """[blueprint] Invalid blueprint_id pattern fails."""
        blueprint = create_valid_blueprint()
        blueprint["blueprint_id"] = "Invalid ID With Spaces"
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_missing_title_fails(self):
        """[blueprint] Missing title fails."""
        blueprint = create_valid_blueprint()
        del blueprint["title"]
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_missing_domain_fails(self):
        """[blueprint] Missing domain fails."""
        blueprint = create_valid_blueprint()
        del blueprint["domain"]
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_missing_version_fails(self):
        """[blueprint] Missing version fails."""
        blueprint = create_valid_blueprint()
        del blueprint["version"]
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_invalid_version_format_fails(self):
        """[blueprint] Invalid version format fails."""
        blueprint = create_valid_blueprint()
        blueprint["version"] = "v1.0"  # Must be X.Y.Z
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_missing_compat_fails(self):
        """[blueprint] Missing compat fails."""
        blueprint = create_valid_blueprint()
        del blueprint["compat"]
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_missing_compat_idl_draft_version_fails(self):
        """[blueprint] Missing compat.idl_draft_schema_version fails."""
        blueprint = create_valid_blueprint()
        del blueprint["compat"]["idl_draft_schema_version"]
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_missing_defaults_fails(self):
        """[blueprint] Missing defaults fails."""
        blueprint = create_valid_blueprint()
        del blueprint["defaults"]
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)


# =============================================================================
# Test Enum Validation
# =============================================================================


class TestEnumValidation:
    """Test enum values are enforced."""

    def test_invalid_integration_type_fails(self):
        """[blueprint] Invalid integration type fails with SCHEMA prefix."""
        blueprint = create_valid_blueprint()
        blueprint["defaults"]["integrations"] = [
            {"system": "External", "type": "invalid_type"}
        ]
        with pytest.raises(BlueprintValidationError) as exc:
            validate_blueprint(blueprint)
        assert "SCHEMA:" in str(exc.value)


# =============================================================================
# Test Duplicate Detection
# =============================================================================


class TestDuplicateDetection:
    """Test duplicate ID detection."""

    def test_duplicate_actor_id_fails(self):
        """[blueprint] Duplicate actor id fails."""
        blueprint = create_valid_blueprint()
        blueprint["defaults"]["actors"] = [
            {"id": "Buyer"},
            {"id": "Buyer"},  # Duplicate
        ]
        with pytest.raises(BlueprintValidationError) as exc:
            validate_blueprint(blueprint)
        assert "Duplicate actor id" in str(exc.value)

    def test_duplicate_entity_id_fails(self):
        """[blueprint] Duplicate entity id fails."""
        blueprint = create_valid_blueprint()
        blueprint["defaults"]["entities"] = [
            {"id": "Product"},
            {"id": "Product"},  # Duplicate
        ]
        with pytest.raises(BlueprintValidationError) as exc:
            validate_blueprint(blueprint)
        assert "Duplicate entity id" in str(exc.value)

    def test_duplicate_usecase_id_fails(self):
        """[blueprint] Duplicate usecase id fails."""
        blueprint = create_valid_blueprint()
        blueprint["defaults"]["usecases"] = [
            {"id": "BrowseProducts"},
            {"id": "BrowseProducts"},  # Duplicate
        ]
        with pytest.raises(BlueprintValidationError) as exc:
            validate_blueprint(blueprint)
        assert "Duplicate usecase id" in str(exc.value)

    def test_duplicate_field_name_fails(self):
        """[blueprint] Duplicate field name within entity fails."""
        blueprint = create_valid_blueprint()
        blueprint["defaults"]["entities"] = [
            {
                "id": "Product",
                "fields": [
                    {"name": "price"},
                    {"name": "price"},  # Duplicate
                ]
            }
        ]
        with pytest.raises(BlueprintValidationError) as exc:
            validate_blueprint(blueprint)
        assert "Duplicate field name" in str(exc.value)


# =============================================================================
# Test Additional Properties
# =============================================================================


class TestAdditionalProperties:
    """Test that additional properties are rejected."""

    def test_extra_top_level_property_fails(self):
        """[blueprint] Extra top-level property fails."""
        blueprint = create_valid_blueprint()
        blueprint["extra_field"] = "not allowed"
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_extra_defaults_property_fails(self):
        """[blueprint] Extra defaults property fails."""
        blueprint = create_valid_blueprint()
        blueprint["defaults"]["exotic_field"] = []
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)

    def test_extra_actor_property_fails(self):
        """[blueprint] Extra actor property fails."""
        blueprint = create_valid_blueprint()
        blueprint["defaults"]["actors"] = [
            {"id": "Buyer", "extra": "not allowed"}
        ]
        with pytest.raises(BlueprintValidationError):
            validate_blueprint(blueprint)


# =============================================================================
# Test Canonicalization
# =============================================================================


class TestCanonicalization:
    """Test blueprint canonicalization."""

    def test_canonical_sorts_actors_by_id(self):
        """[blueprint] Canonical sorts actors by id."""
        blueprint = create_valid_blueprint()
        blueprint["defaults"]["actors"] = [
            {"id": "Zebra"},
            {"id": "Alpha"},
            {"id": "Beta"}
        ]

        canonical = canonicalize_blueprint(blueprint)
        actor_ids = [a["id"] for a in canonical["defaults"]["actors"]]

        assert actor_ids == ["Alpha", "Beta", "Zebra"]

    def test_canonical_sorts_entities_by_id(self):
        """[blueprint] Canonical sorts entities by id."""
        blueprint = create_valid_blueprint()
        blueprint["defaults"]["entities"] = [
            {"id": "Zebra"},
            {"id": "Alpha"},
            {"id": "Beta"}
        ]

        canonical = canonicalize_blueprint(blueprint)
        entity_ids = [e["id"] for e in canonical["defaults"]["entities"]]

        assert entity_ids == ["Alpha", "Beta", "Zebra"]

    def test_canonical_sorts_entity_fields_by_name(self):
        """[blueprint] Canonical sorts entity fields by name."""
        blueprint = create_minimal_blueprint()
        blueprint["defaults"]["entities"] = [
            {
                "id": "Product",
                "fields": [
                    {"name": "zebra"},
                    {"name": "alpha"},
                    {"name": "beta"}
                ]
            }
        ]

        canonical = canonicalize_blueprint(blueprint)
        field_names = [f["name"] for f in canonical["defaults"]["entities"][0]["fields"]]

        assert field_names == ["alpha", "beta", "zebra"]

    def test_canonical_sorts_usecases_by_id(self):
        """[blueprint] Canonical sorts usecases by id."""
        blueprint = create_minimal_blueprint()
        blueprint["defaults"]["usecases"] = [
            {"id": "Zebra"},
            {"id": "Alpha"},
            {"id": "Beta"}
        ]

        canonical = canonicalize_blueprint(blueprint)
        usecase_ids = [u["id"] for u in canonical["defaults"]["usecases"]]

        assert usecase_ids == ["Alpha", "Beta", "Zebra"]

    def test_canonical_sorts_flow_steps_by_step_number(self):
        """[blueprint] Canonical sorts flow steps by step number."""
        blueprint = create_minimal_blueprint()
        blueprint["defaults"]["usecases"] = [
            {
                "id": "Test",
                "flow": [
                    {"step": 3, "action": "Third"},
                    {"step": 1, "action": "First"},
                    {"step": 2, "action": "Second"}
                ]
            }
        ]

        canonical = canonicalize_blueprint(blueprint)
        steps = [s["step"] for s in canonical["defaults"]["usecases"][0]["flow"]]

        assert steps == [1, 2, 3]

    def test_canonical_sorts_integrations(self):
        """[blueprint] Canonical sorts integrations by (system, type)."""
        blueprint = create_minimal_blueprint()
        blueprint["defaults"]["integrations"] = [
            {"system": "Zebra", "type": "api"},
            {"system": "Alpha", "type": "db"},
            {"system": "Alpha", "type": "api"}
        ]

        canonical = canonicalize_blueprint(blueprint)
        systems = [(i["system"], i["type"]) for i in canonical["defaults"]["integrations"]]

        assert systems == [("Alpha", "api"), ("Alpha", "db"), ("Zebra", "api")]

    def test_canonical_does_not_mutate_original(self):
        """[blueprint] Canonicalization does not mutate original."""
        blueprint = create_valid_blueprint()
        original_actors = [a["id"] for a in blueprint["defaults"]["actors"]]

        canonicalize_blueprint(blueprint)

        assert [a["id"] for a in blueprint["defaults"]["actors"]] == original_actors

    def test_canonical_is_deterministic(self):
        """[blueprint] Same input produces identical canonical output."""
        blueprint = create_valid_blueprint()

        canonical1 = canonicalize_blueprint(blueprint)
        canonical2 = canonicalize_blueprint(blueprint)

        assert json.dumps(canonical1, sort_keys=True) == json.dumps(canonical2, sort_keys=True)

    def test_different_order_same_canonical(self):
        """[blueprint] Different order produces same canonical result."""
        bp1 = create_minimal_blueprint()
        bp1["defaults"]["actors"] = [
            {"id": "Alpha"},
            {"id": "Beta"},
            {"id": "Gamma"}
        ]

        bp2 = create_minimal_blueprint()
        bp2["defaults"]["actors"] = [
            {"id": "Gamma"},
            {"id": "Alpha"},
            {"id": "Beta"}
        ]

        canonical1 = canonicalize_blueprint(bp1)
        canonical2 = canonicalize_blueprint(bp2)

        assert canonical1["defaults"]["actors"] == canonical2["defaults"]["actors"]


# =============================================================================
# Test Loading
# =============================================================================


class TestLoading:
    """Test blueprint loading from file."""

    def test_load_valid_file(self):
        """[blueprint] Loads valid blueprint from file."""
        blueprint = create_valid_blueprint()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(blueprint, f)
            f.flush()
            path = Path(f.name)

        try:
            loaded = load_blueprint(path)
            assert loaded["blueprint_id"] == "marketplace.v1.core"
            assert loaded["domain"] == "marketplace"
        finally:
            path.unlink()

    def test_file_not_found_raises(self):
        """[blueprint] FileNotFoundError raised for missing file."""
        with pytest.raises(FileNotFoundError):
            load_blueprint(Path("/nonexistent/path.json"))

    def test_invalid_json_raises(self):
        """[blueprint] Invalid JSON raises BlueprintValidationError."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("{invalid json}")
            f.flush()
            path = Path(f.name)

        try:
            with pytest.raises(BlueprintValidationError) as exc:
                load_blueprint(path)
            assert "Invalid JSON" in str(exc.value)
        finally:
            path.unlink()


# =============================================================================
# Test Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_blueprint_actors(self):
        """[blueprint] get_blueprint_actors returns actors."""
        blueprint = create_valid_blueprint()
        actors = get_blueprint_actors(blueprint)

        assert len(actors) == 2
        assert actors[0]["id"] == "Buyer"

    def test_get_blueprint_entities(self):
        """[blueprint] get_blueprint_entities returns entities."""
        blueprint = create_valid_blueprint()
        entities = get_blueprint_entities(blueprint)

        assert len(entities) == 2
        assert entities[0]["id"] == "Product"

    def test_get_blueprint_usecases(self):
        """[blueprint] get_blueprint_usecases returns usecases."""
        blueprint = create_valid_blueprint()
        usecases = get_blueprint_usecases(blueprint)

        assert len(usecases) == 1
        assert usecases[0]["id"] == "BrowseProducts"

    def test_get_blueprint_integrations(self):
        """[blueprint] get_blueprint_integrations returns integrations."""
        blueprint = create_valid_blueprint()
        integrations = get_blueprint_integrations(blueprint)

        assert len(integrations) == 2
        assert integrations[0]["system"] == "PaymentGateway"

    def test_get_blueprint_nonfunctional(self):
        """[blueprint] get_blueprint_nonfunctional returns NFRs."""
        blueprint = create_valid_blueprint()
        nfr = get_blueprint_nonfunctional(blueprint)

        assert nfr is not None
        assert "performance" in nfr
        assert "security" in nfr

    def test_get_blueprint_nonfunctional_empty(self):
        """[blueprint] get_blueprint_nonfunctional returns None when empty."""
        blueprint = create_minimal_blueprint()
        nfr = get_blueprint_nonfunctional(blueprint)

        assert nfr is None

    def test_is_compatible_with_draft(self):
        """[blueprint] is_compatible_with_draft checks compat."""
        blueprint = create_valid_blueprint()

        assert is_compatible_with_draft(blueprint, "idl_draft.v1") is True
        assert is_compatible_with_draft(blueprint, "idl_draft.v2") is False

    def test_schema_version_constant(self):
        """[blueprint] BLUEPRINT_SCHEMA_VERSION is correct."""
        assert BLUEPRINT_SCHEMA_VERSION == "blueprint.v1"
