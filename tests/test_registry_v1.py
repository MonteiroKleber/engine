"""Tests for Blueprint Registry v1.

Tests cover:
1) Registry schema validation
2) Blueprint registration with hash computation
3) Integrity verification (INTEGRITY: prefix)
4) Deterministic ordering (sorted by blueprint_id)
5) Load/save operations
"""

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from blueprints.registry_v1 import (
    REGISTRY_SCHEMA_VERSION,
    compute_content_hash,
    validate_registry,
    load_registry,
    save_registry,
    create_empty_registry,
    register_blueprint,
    unregister_blueprint,
    verify_registry,
    verify_blueprint,
    get_blueprint_entry,
    list_blueprints,
    get_blueprint_path,
    RegistryValidationError,
    RegistryIntegrityError,
)
from blueprints.blueprint_v1 import canonicalize_blueprint


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_registry_dir():
    """Create a temporary registry directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_dir = Path(tmpdir) / "registry"
        registry_dir.mkdir()
        (registry_dir / "blueprints").mkdir()
        yield registry_dir


@pytest.fixture
def valid_blueprint():
    """Return a valid blueprint dict."""
    return {
        "schema_version": "blueprint.v1",
        "blueprint_id": "test.v1",
        "title": "Test Blueprint",
        "domain": "test",
        "version": "1.0.0",
        "compat": {
            "idl_draft_schema_version": "idl_draft.v1"
        },
        "defaults": {
            "actors": [
                {"id": "admin", "role": "Administrator"}
            ],
            "entities": [
                {"id": "User", "fields": [{"name": "name", "type": "string"}]}
            ]
        }
    }


@pytest.fixture
def valid_blueprint_file(temp_registry_dir, valid_blueprint):
    """Create a valid blueprint file and return its path."""
    blueprint_path = temp_registry_dir / "test_blueprint.json"
    with open(blueprint_path, "w") as f:
        json.dump(valid_blueprint, f, indent=2)
    return blueprint_path


@pytest.fixture
def empty_registry(temp_registry_dir):
    """Create an empty registry and return the registry dict."""
    registry = create_empty_registry()
    save_registry(registry, temp_registry_dir)
    return registry


# =============================================================================
# Test: Schema Version
# =============================================================================


class TestSchemaVersion:
    """Test schema version constant."""

    def test_schema_version_is_correct(self):
        """[registry_v1] Schema version is blueprint_registry.v1."""
        assert REGISTRY_SCHEMA_VERSION == "blueprint_registry.v1"


# =============================================================================
# Test: Registry Validation
# =============================================================================


class TestValidateRegistry:
    """Test registry schema validation."""

    def test_valid_empty_registry(self):
        """[registry_v1] Empty registry is valid."""
        registry = {
            "schema_version": "blueprint_registry.v1",
            "blueprints": []
        }
        validate_registry(registry)  # Should not raise

    def test_valid_registry_with_blueprints(self):
        """[registry_v1] Registry with blueprints is valid."""
        registry = {
            "schema_version": "blueprint_registry.v1",
            "blueprints": [
                {
                    "blueprint_id": "a.v1",
                    "path": "blueprints/a.v1.json",
                    "content_hash_sha256": "a" * 64,
                    "domain": "test",
                    "version": "1.0.0"
                },
                {
                    "blueprint_id": "b.v1",
                    "path": "blueprints/b.v1.json",
                    "content_hash_sha256": "b" * 64,
                    "domain": "test",
                    "version": "1.0.0"
                }
            ]
        }
        validate_registry(registry)  # Should not raise

    def test_missing_schema_version_fails(self):
        """[registry_v1] Missing schema_version fails with SCHEMA: prefix."""
        registry = {"blueprints": []}
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(registry)
        assert "SCHEMA:" in str(exc_info.value)

    def test_wrong_schema_version_fails(self):
        """[registry_v1] Wrong schema_version fails with SCHEMA: prefix."""
        registry = {
            "schema_version": "wrong.v1",
            "blueprints": []
        }
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(registry)
        assert "SCHEMA:" in str(exc_info.value)

    def test_duplicate_blueprint_id_fails(self):
        """[registry_v1] Duplicate blueprint_id fails with SCHEMA: prefix."""
        registry = {
            "schema_version": "blueprint_registry.v1",
            "blueprints": [
                {
                    "blueprint_id": "test.v1",
                    "path": "blueprints/test.v1.json",
                    "content_hash_sha256": "a" * 64,
                    "domain": "test",
                    "version": "1.0.0"
                },
                {
                    "blueprint_id": "test.v1",  # Duplicate
                    "path": "blueprints/test.v1.json",
                    "content_hash_sha256": "b" * 64,
                    "domain": "test",
                    "version": "2.0.0"
                }
            ]
        }
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(registry)
        assert "SCHEMA:" in str(exc_info.value)
        assert "Duplicate blueprint_id" in str(exc_info.value)

    def test_unsorted_blueprints_fails(self):
        """[registry_v1] Unsorted blueprints fails with SCHEMA: prefix."""
        registry = {
            "schema_version": "blueprint_registry.v1",
            "blueprints": [
                {
                    "blueprint_id": "z.v1",  # Should come after a.v1
                    "path": "blueprints/z.v1.json",
                    "content_hash_sha256": "a" * 64,
                    "domain": "test",
                    "version": "1.0.0"
                },
                {
                    "blueprint_id": "a.v1",
                    "path": "blueprints/a.v1.json",
                    "content_hash_sha256": "b" * 64,
                    "domain": "test",
                    "version": "1.0.0"
                }
            ]
        }
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(registry)
        assert "SCHEMA:" in str(exc_info.value)
        assert "not sorted" in str(exc_info.value)

    def test_invalid_blueprint_id_pattern_fails(self):
        """[registry_v1] Invalid blueprint_id pattern fails."""
        registry = {
            "schema_version": "blueprint_registry.v1",
            "blueprints": [
                {
                    "blueprint_id": "Invalid-ID",  # Must start with lowercase
                    "path": "blueprints/invalid-id.json",
                    "content_hash_sha256": "a" * 64,
                    "domain": "test",
                    "version": "1.0.0"
                }
            ]
        }
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(registry)
        assert "SCHEMA:" in str(exc_info.value)

    def test_invalid_hash_pattern_fails(self):
        """[registry_v1] Invalid hash pattern fails."""
        registry = {
            "schema_version": "blueprint_registry.v1",
            "blueprints": [
                {
                    "blueprint_id": "test.v1",
                    "path": "blueprints/test.v1.json",
                    "content_hash_sha256": "not-a-hash",  # Invalid
                    "domain": "test",
                    "version": "1.0.0"
                }
            ]
        }
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(registry)
        assert "SCHEMA:" in str(exc_info.value)


# =============================================================================
# Test: Content Hash
# =============================================================================


class TestContentHash:
    """Test content hash computation."""

    def test_hash_is_deterministic(self, valid_blueprint):
        """[registry_v1] Hash computation is deterministic."""
        hash1 = compute_content_hash(valid_blueprint)
        hash2 = compute_content_hash(valid_blueprint)
        assert hash1 == hash2

    def test_hash_is_64_hex_chars(self, valid_blueprint):
        """[registry_v1] Hash is 64 hex characters (SHA256)."""
        hash_value = compute_content_hash(valid_blueprint)
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_hash_uses_canonicalized_form(self, valid_blueprint):
        """[registry_v1] Hash uses canonicalized blueprint."""
        # Create unsorted version
        unsorted = valid_blueprint.copy()
        unsorted["defaults"] = {
            "entities": valid_blueprint["defaults"]["entities"],
            "actors": valid_blueprint["defaults"]["actors"],  # Different order
        }

        # Hashes should be the same after canonicalization
        hash1 = compute_content_hash(valid_blueprint)
        hash2 = compute_content_hash(unsorted)
        assert hash1 == hash2

    def test_different_content_different_hash(self, valid_blueprint):
        """[registry_v1] Different content produces different hash."""
        hash1 = compute_content_hash(valid_blueprint)

        modified = valid_blueprint.copy()
        modified["title"] = "Modified Title"
        hash2 = compute_content_hash(modified)

        assert hash1 != hash2


# =============================================================================
# Test: Load/Save Registry
# =============================================================================


class TestLoadSaveRegistry:
    """Test registry load and save operations."""

    def test_save_and_load_registry(self, temp_registry_dir):
        """[registry_v1] Registry can be saved and loaded."""
        registry = {
            "schema_version": "blueprint_registry.v1",
            "blueprints": [
                {
                    "blueprint_id": "test.v1",
                    "path": "blueprints/test.v1.json",
                    "content_hash_sha256": "a" * 64,
                    "domain": "test",
                    "version": "1.0.0"
                }
            ]
        }

        save_registry(registry, temp_registry_dir)
        loaded = load_registry(temp_registry_dir)

        assert loaded == registry

    def test_load_nonexistent_registry_fails(self, temp_registry_dir):
        """[registry_v1] Loading nonexistent registry raises FileNotFoundError."""
        # Remove any existing index.json
        index_path = temp_registry_dir / "index.json"
        if index_path.exists():
            index_path.unlink()

        with pytest.raises(FileNotFoundError):
            load_registry(temp_registry_dir)

    def test_save_validates_registry(self, temp_registry_dir):
        """[registry_v1] Save validates registry before writing."""
        invalid_registry = {"blueprints": []}  # Missing schema_version

        with pytest.raises(RegistryValidationError):
            save_registry(invalid_registry, temp_registry_dir)

    def test_create_empty_registry(self):
        """[registry_v1] create_empty_registry returns valid structure."""
        registry = create_empty_registry()

        assert registry["schema_version"] == "blueprint_registry.v1"
        assert registry["blueprints"] == []

        # Should be valid
        validate_registry(registry)


# =============================================================================
# Test: Blueprint Registration
# =============================================================================


class TestRegisterBlueprint:
    """Test blueprint registration."""

    def test_register_creates_entry(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] register_blueprint creates registry entry."""
        entry = register_blueprint(valid_blueprint_file, temp_registry_dir)

        assert entry["blueprint_id"] == "test.v1"
        assert entry["domain"] == "test"
        assert entry["version"] == "1.0.0"
        assert len(entry["content_hash_sha256"]) == 64

    def test_register_copies_blueprint_to_registry(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] register_blueprint copies file to registry/blueprints/."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        copied_path = temp_registry_dir / "blueprints" / "test.v1.json"
        assert copied_path.exists()

        with open(copied_path) as f:
            copied = json.load(f)

        assert copied["blueprint_id"] == "test.v1"

    def test_register_updates_index(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] register_blueprint updates index.json."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        registry = load_registry(temp_registry_dir)

        assert len(registry["blueprints"]) == 1
        assert registry["blueprints"][0]["blueprint_id"] == "test.v1"

    def test_register_multiple_sorted(self, temp_registry_dir, empty_registry):
        """[registry_v1] Multiple registrations maintain sorted order."""
        # Create blueprints with different IDs
        for bp_id in ["z.v1", "a.v1", "m.v1"]:
            blueprint = {
                "schema_version": "blueprint.v1",
                "blueprint_id": bp_id,
                "title": f"Blueprint {bp_id}",
                "domain": "test",
                "version": "1.0.0",
                "compat": {"idl_draft_schema_version": "idl_draft.v1"},
                "defaults": {}
            }
            bp_path = temp_registry_dir / f"{bp_id}.json"
            with open(bp_path, "w") as f:
                json.dump(blueprint, f)
            register_blueprint(bp_path, temp_registry_dir)

        registry = load_registry(temp_registry_dir)
        ids = [b["blueprint_id"] for b in registry["blueprints"]]

        assert ids == ["a.v1", "m.v1", "z.v1"]  # Sorted

    def test_register_updates_existing(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] Registering existing ID updates the entry."""
        # Register first time
        entry1 = register_blueprint(valid_blueprint_file, temp_registry_dir)
        hash1 = entry1["content_hash_sha256"]

        # Modify blueprint and re-register
        with open(valid_blueprint_file) as f:
            blueprint = json.load(f)
        blueprint["version"] = "2.0.0"
        blueprint["title"] = "Updated Title"
        with open(valid_blueprint_file, "w") as f:
            json.dump(blueprint, f)

        entry2 = register_blueprint(valid_blueprint_file, temp_registry_dir)

        # Hash should be different, version updated
        assert entry2["version"] == "2.0.0"
        assert entry2["content_hash_sha256"] != hash1

        # Registry should still have only one entry
        registry = load_registry(temp_registry_dir)
        assert len(registry["blueprints"]) == 1


# =============================================================================
# Test: Blueprint Unregistration
# =============================================================================


class TestUnregisterBlueprint:
    """Test blueprint unregistration."""

    def test_unregister_removes_entry(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] unregister_blueprint removes entry from index."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        result = unregister_blueprint("test.v1", temp_registry_dir)

        assert result is True
        registry = load_registry(temp_registry_dir)
        assert len(registry["blueprints"]) == 0

    def test_unregister_removes_file(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] unregister_blueprint removes blueprint file."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        blueprint_path = temp_registry_dir / "blueprints" / "test.v1.json"
        assert blueprint_path.exists()

        unregister_blueprint("test.v1", temp_registry_dir)

        assert not blueprint_path.exists()

    def test_unregister_nonexistent_returns_false(
        self, temp_registry_dir, empty_registry
    ):
        """[registry_v1] unregister_blueprint returns False for nonexistent ID."""
        result = unregister_blueprint("nonexistent.v1", temp_registry_dir)
        assert result is False


# =============================================================================
# Test: Integrity Verification
# =============================================================================


class TestVerifyRegistry:
    """Test registry integrity verification."""

    def test_verify_empty_registry_passes(self, temp_registry_dir, empty_registry):
        """[registry_v1] verify_registry passes for empty registry."""
        errors = verify_registry(temp_registry_dir)
        assert errors == []

    def test_verify_valid_registry_passes(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] verify_registry passes for valid registry."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        errors = verify_registry(temp_registry_dir)
        assert errors == []

    def test_verify_detects_missing_file(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] verify_registry detects missing blueprint file."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        # Delete the blueprint file
        blueprint_path = temp_registry_dir / "blueprints" / "test.v1.json"
        blueprint_path.unlink()

        with pytest.raises(RegistryIntegrityError) as exc_info:
            verify_registry(temp_registry_dir)

        assert "INTEGRITY:" in str(exc_info.value)
        assert "file not found" in str(exc_info.value)

    def test_verify_detects_hash_mismatch(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] verify_registry detects hash mismatch."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        # Modify the blueprint file directly
        blueprint_path = temp_registry_dir / "blueprints" / "test.v1.json"
        with open(blueprint_path) as f:
            blueprint = json.load(f)
        blueprint["title"] = "Tampered Title"
        with open(blueprint_path, "w") as f:
            json.dump(blueprint, f)

        with pytest.raises(RegistryIntegrityError) as exc_info:
            verify_registry(temp_registry_dir)

        assert "INTEGRITY:" in str(exc_info.value)
        assert "hash mismatch" in str(exc_info.value)

    def test_verify_detects_id_mismatch(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] verify_registry detects blueprint_id mismatch."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        # Modify the blueprint_id in the file
        blueprint_path = temp_registry_dir / "blueprints" / "test.v1.json"
        with open(blueprint_path) as f:
            blueprint = json.load(f)
        blueprint["blueprint_id"] = "wrong.v1"
        with open(blueprint_path, "w") as f:
            json.dump(blueprint, f)

        with pytest.raises(RegistryIntegrityError) as exc_info:
            verify_registry(temp_registry_dir)

        # Could be hash mismatch or id mismatch depending on order
        assert "INTEGRITY:" in str(exc_info.value)


class TestVerifyBlueprint:
    """Test single blueprint verification."""

    def test_verify_valid_blueprint_passes(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] verify_blueprint passes for valid blueprint."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        result = verify_blueprint("test.v1", temp_registry_dir)
        assert result is True

    def test_verify_nonexistent_blueprint_raises_keyerror(
        self, temp_registry_dir, empty_registry
    ):
        """[registry_v1] verify_blueprint raises KeyError for nonexistent ID."""
        with pytest.raises(KeyError) as exc_info:
            verify_blueprint("nonexistent.v1", temp_registry_dir)

        assert "not found in registry" in str(exc_info.value)

    def test_verify_missing_file_raises_integrity_error(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] verify_blueprint raises IntegrityError for missing file."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        # Delete the file
        blueprint_path = temp_registry_dir / "blueprints" / "test.v1.json"
        blueprint_path.unlink()

        with pytest.raises(RegistryIntegrityError) as exc_info:
            verify_blueprint("test.v1", temp_registry_dir)

        assert "INTEGRITY:" in str(exc_info.value)
        assert "test.v1" in str(exc_info.value)


# =============================================================================
# Test: Query Functions
# =============================================================================


class TestQueryFunctions:
    """Test registry query functions."""

    def test_get_blueprint_entry_found(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] get_blueprint_entry returns entry for existing ID."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        entry = get_blueprint_entry("test.v1", temp_registry_dir)

        assert entry is not None
        assert entry["blueprint_id"] == "test.v1"

    def test_get_blueprint_entry_not_found(
        self, temp_registry_dir, empty_registry
    ):
        """[registry_v1] get_blueprint_entry returns None for nonexistent ID."""
        entry = get_blueprint_entry("nonexistent.v1", temp_registry_dir)
        assert entry is None

    def test_list_blueprints_all(self, temp_registry_dir, empty_registry):
        """[registry_v1] list_blueprints returns all blueprints."""
        # Register multiple blueprints with different domains
        for i, domain in enumerate(["test", "prod", "test"]):
            blueprint = {
                "schema_version": "blueprint.v1",
                "blueprint_id": f"bp{i}.v1",
                "title": f"Blueprint {i}",
                "domain": domain,
                "version": "1.0.0",
                "compat": {"idl_draft_schema_version": "idl_draft.v1"},
                "defaults": {}
            }
            bp_path = temp_registry_dir / f"bp{i}.json"
            with open(bp_path, "w") as f:
                json.dump(blueprint, f)
            register_blueprint(bp_path, temp_registry_dir)

        blueprints = list_blueprints(registry_dir=temp_registry_dir)
        assert len(blueprints) == 3

    def test_list_blueprints_filter_by_domain(self, temp_registry_dir, empty_registry):
        """[registry_v1] list_blueprints filters by domain."""
        # Register blueprints with different domains
        for i, domain in enumerate(["test", "prod", "test"]):
            blueprint = {
                "schema_version": "blueprint.v1",
                "blueprint_id": f"bp{i}.v1",
                "title": f"Blueprint {i}",
                "domain": domain,
                "version": "1.0.0",
                "compat": {"idl_draft_schema_version": "idl_draft.v1"},
                "defaults": {}
            }
            bp_path = temp_registry_dir / f"bp{i}.json"
            with open(bp_path, "w") as f:
                json.dump(blueprint, f)
            register_blueprint(bp_path, temp_registry_dir)

        test_blueprints = list_blueprints(domain="test", registry_dir=temp_registry_dir)
        assert len(test_blueprints) == 2
        assert all(b["domain"] == "test" for b in test_blueprints)

    def test_get_blueprint_path_found(
        self, temp_registry_dir, valid_blueprint_file, empty_registry
    ):
        """[registry_v1] get_blueprint_path returns path for existing ID."""
        register_blueprint(valid_blueprint_file, temp_registry_dir)

        path = get_blueprint_path("test.v1", temp_registry_dir)

        assert path is not None
        assert path.exists()
        assert path.name == "test.v1.json"

    def test_get_blueprint_path_not_found(
        self, temp_registry_dir, empty_registry
    ):
        """[registry_v1] get_blueprint_path returns None for nonexistent ID."""
        path = get_blueprint_path("nonexistent.v1", temp_registry_dir)
        assert path is None


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_register_invalid_blueprint_fails(self, temp_registry_dir, empty_registry):
        """[registry_v1] Registering invalid blueprint fails."""
        # Create invalid blueprint (missing required fields)
        invalid_blueprint = {"schema_version": "blueprint.v1"}
        bp_path = temp_registry_dir / "invalid.json"
        with open(bp_path, "w") as f:
            json.dump(invalid_blueprint, f)

        from blueprints.blueprint_v1 import BlueprintValidationError

        with pytest.raises(BlueprintValidationError):
            register_blueprint(bp_path, temp_registry_dir)

    def test_register_nonexistent_file_fails(self, temp_registry_dir, empty_registry):
        """[registry_v1] Registering nonexistent file fails."""
        nonexistent = temp_registry_dir / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            register_blueprint(nonexistent, temp_registry_dir)

    def test_canonicalized_blueprint_stored(
        self, temp_registry_dir, empty_registry
    ):
        """[registry_v1] Stored blueprint is canonicalized."""
        # Create blueprint with unsorted fields
        blueprint = {
            "schema_version": "blueprint.v1",
            "blueprint_id": "test.v1",
            "title": "Test",
            "domain": "test",
            "version": "1.0.0",
            "compat": {"idl_draft_schema_version": "idl_draft.v1"},
            "defaults": {
                "actors": [
                    {"id": "z_actor"},
                    {"id": "a_actor"}
                ]
            }
        }
        bp_path = temp_registry_dir / "test.json"
        with open(bp_path, "w") as f:
            json.dump(blueprint, f)

        register_blueprint(bp_path, temp_registry_dir)

        # Check stored blueprint is canonicalized
        stored_path = temp_registry_dir / "blueprints" / "test.v1.json"
        with open(stored_path) as f:
            stored = json.load(f)

        # Actors should be sorted by id
        actor_ids = [a["id"] for a in stored["defaults"]["actors"]]
        assert actor_ids == ["a_actor", "z_actor"]
