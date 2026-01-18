"""Tests for institutions registry append-only behavior."""

import json
from pathlib import Path

import pytest

from engine.core.institutions import (
    InstitutionsRegistry,
    reset_registry,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before each test."""
    reset_registry()
    yield
    reset_registry()


class TestRegistryAppendOnly:
    """Test that registry is append-only."""

    def test_create_appends_single_line(self, tmp_path):
        """Creating institution appends exactly one line to registry."""
        registry_path = tmp_path / "registry.jsonl"
        institutions_dir = tmp_path / "institutions"

        registry = InstitutionsRegistry(
            registry_path=registry_path,
            institutions_dir=institutions_dir,
        )

        # Create first institution
        inst1, err_code, err_msg = registry.create(slug="first-inst")
        assert err_code is None

        # Check registry has exactly 1 line
        with open(registry_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]
        assert len(lines) == 1

        # Parse line
        entry1 = json.loads(lines[0])
        assert entry1["slug"] == "first-inst"
        assert entry1["institution_id"] == inst1.institution_id

    def test_create_appends_new_line_without_modifying_previous(self, tmp_path):
        """Creating another institution appends a new line without modifying previous."""
        registry_path = tmp_path / "registry.jsonl"
        institutions_dir = tmp_path / "institutions"

        registry = InstitutionsRegistry(
            registry_path=registry_path,
            institutions_dir=institutions_dir,
        )

        # Create first institution
        inst1, _, _ = registry.create(slug="first-inst")

        # Read first line
        with open(registry_path, "r", encoding="utf-8") as f:
            first_line_original = f.readline()

        # Create second institution
        inst2, err_code, _ = registry.create(slug="second-inst")
        assert err_code is None

        # Read registry again
        with open(registry_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        # Should have 2 lines
        assert len(lines) == 2

        # First line should be unchanged (append-only)
        assert lines[0].strip() == first_line_original.strip()

        # Second line should be the new entry
        entry2 = json.loads(lines[1])
        assert entry2["slug"] == "second-inst"
        assert entry2["institution_id"] == inst2.institution_id

    def test_multiple_creates_preserve_order(self, tmp_path):
        """Multiple creates preserve chronological order in registry."""
        registry_path = tmp_path / "registry.jsonl"
        institutions_dir = tmp_path / "institutions"

        registry = InstitutionsRegistry(
            registry_path=registry_path,
            institutions_dir=institutions_dir,
        )

        slugs = ["alpha-inst", "beta-inst", "gamma-inst", "delta-inst"]
        created_ids = []

        for slug in slugs:
            inst, _, _ = registry.create(slug=slug)
            created_ids.append(inst.institution_id)

        # Read registry
        with open(registry_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        assert len(lines) == 4

        # Verify order matches creation order
        for i, line in enumerate(lines):
            entry = json.loads(line)
            assert entry["slug"] == slugs[i]
            assert entry["institution_id"] == created_ids[i]

    def test_registry_reload_preserves_entries(self, tmp_path):
        """Reloading registry from disk preserves all entries."""
        registry_path = tmp_path / "registry.jsonl"
        institutions_dir = tmp_path / "institutions"

        # Create with first registry instance
        registry1 = InstitutionsRegistry(
            registry_path=registry_path,
            institutions_dir=institutions_dir,
        )
        inst1, _, _ = registry1.create(slug="first-inst")
        inst2, _, _ = registry1.create(slug="second-inst")

        # Create new registry instance (simulates restart)
        registry2 = InstitutionsRegistry(
            registry_path=registry_path,
            institutions_dir=institutions_dir,
        )

        # Should be able to look up both by slug and id
        found1, _, _ = registry2.get_by_slug("first-inst")
        assert found1 is not None
        assert found1.institution_id == inst1.institution_id

        found2, _, _ = registry2.get_by_id(inst2.institution_id)
        assert found2 is not None
        assert found2.slug == "second-inst"

        # Add a third via the new instance
        inst3, _, _ = registry2.create(slug="third-inst")

        # Registry should now have 3 lines
        with open(registry_path, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]
        assert len(lines) == 3

    def test_registry_never_modifies_existing_lines(self, tmp_path):
        """Registry never modifies existing lines (true append-only)."""
        registry_path = tmp_path / "registry.jsonl"
        institutions_dir = tmp_path / "institutions"

        registry = InstitutionsRegistry(
            registry_path=registry_path,
            institutions_dir=institutions_dir,
        )

        # Create 3 institutions
        registry.create(slug="inst-one")
        registry.create(slug="inst-two")
        registry.create(slug="inst-three")

        # Read all lines and their hashes
        with open(registry_path, "r", encoding="utf-8") as f:
            original_lines = f.readlines()

        original_content = "".join(original_lines)

        # Create one more
        registry.create(slug="inst-four")

        # Read again
        with open(registry_path, "r", encoding="utf-8") as f:
            new_lines = f.readlines()

        # First 3 lines should be identical
        for i in range(3):
            assert new_lines[i] == original_lines[i], f"Line {i} was modified!"

        # New content should start with original content
        with open(registry_path, "r", encoding="utf-8") as f:
            new_content = f.read()

        assert new_content.startswith(original_content)
