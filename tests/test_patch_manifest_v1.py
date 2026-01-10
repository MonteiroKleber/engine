"""Tests for PatchManifest v1 with Contract Gate.

Validates:
1) PatchManifest creation and serialization
2) PatchEntry and PatchPolicy
3) Contract gate validation (hash integrity)
4) PatchManifestStore save/load
5) Pre-build verification
"""

import json
import pytest
from pathlib import Path

from observability.patch_manifest import (
    PATCH_MANIFEST_SCHEMA_VERSION,
    PatchManifest,
    PatchEntry,
    PatchPolicy,
    PatchManifestStore,
    verify_manifest_prebuild,
    extract_hashable_payload,
    HASHABLE_FIELDS,
    VOLATILE_FIELDS,
)
from observability.canonical_hash import compute_content_hash_sha256


class TestPatchEntry:
    """Tests for PatchEntry dataclass."""

    def test_entry_creation(self):
        """[PatchEntry] Basic creation."""
        entry = PatchEntry(
            path="src/app.tsx",
            op="modify",
            rewrite_ratio=0.15,
            lines_added=10,
            lines_removed=5,
            sha256_after="abc123",
        )

        assert entry.path == "src/app.tsx"
        assert entry.op == "modify"
        assert entry.rewrite_ratio == 0.15
        assert entry.sha256_after == "abc123"

    def test_entry_defaults(self):
        """[PatchEntry] Default values."""
        entry = PatchEntry(path="test.py", op="create")

        assert entry.rewrite_ratio == 0.0
        assert entry.lines_added == 0
        assert entry.lines_removed == 0
        assert entry.sha256_after == ""

    def test_entry_to_dict(self):
        """[PatchEntry] to_dict() format."""
        entry = PatchEntry(
            path="src/main.py",
            op="modify",
            rewrite_ratio=0.25,
            lines_added=5,
            lines_removed=2,
            sha256_after="def456",
        )

        d = entry.to_dict()

        assert d["path"] == "src/main.py"
        assert d["op"] == "modify"
        assert d["rewrite_ratio"] == 0.25
        assert d["sha256_after"] == "def456"

    def test_entry_from_dict(self):
        """[PatchEntry] from_dict() reconstruction."""
        data = {
            "path": "test.tsx",
            "op": "create",
            "rewrite_ratio": 0.0,
            "lines_added": 50,
            "lines_removed": 0,
            "sha256_after": "hash123",
        }

        entry = PatchEntry.from_dict(data)

        assert entry.path == "test.tsx"
        assert entry.op == "create"
        assert entry.lines_added == 50


class TestPatchPolicy:
    """Tests for PatchPolicy dataclass."""

    def test_policy_defaults(self):
        """[PatchPolicy] Default values."""
        policy = PatchPolicy()

        assert policy.max_rewrite_ratio == 0.80
        assert "/home/bazari/engine" in policy.blocked_paths
        assert "/home/bazari/generated" in policy.allowlist_roots

    def test_policy_custom(self):
        """[PatchPolicy] Custom values."""
        policy = PatchPolicy(
            max_rewrite_ratio=0.50,
            blocked_paths=["/custom/blocked"],
            allowlist_roots=["/custom/allowed"],
        )

        assert policy.max_rewrite_ratio == 0.50
        assert policy.blocked_paths == ["/custom/blocked"]

    def test_policy_to_dict(self):
        """[PatchPolicy] to_dict() format."""
        policy = PatchPolicy()

        d = policy.to_dict()

        assert "max_rewrite_ratio" in d
        assert "blocked_paths" in d
        assert "allowlist_roots" in d
        # Should be sorted
        assert d["blocked_paths"] == sorted(d["blocked_paths"])

    def test_policy_from_dict(self):
        """[PatchPolicy] from_dict() reconstruction."""
        data = {
            "max_rewrite_ratio": 0.60,
            "blocked_paths": ["/blocked1", "/blocked2"],
            "allowlist_roots": ["/allowed"],
        }

        policy = PatchPolicy.from_dict(data)

        assert policy.max_rewrite_ratio == 0.60
        assert len(policy.blocked_paths) == 2


class TestPatchManifest:
    """Tests for PatchManifest dataclass."""

    def test_manifest_creation(self):
        """[PatchManifest] Basic creation."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test_project",
            patches=[
                PatchEntry(path="file1.py", op="create"),
                PatchEntry(path="file2.py", op="modify"),
            ],
        )

        assert manifest.execution_id == "exec123"
        assert manifest.project == "test_project"
        assert len(manifest.patches) == 2
        assert manifest.result == "applied"

    def test_manifest_to_hashable_dict(self):
        """[PatchManifest] to_hashable_dict() excludes volatile fields."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
        )

        hashable = manifest.to_hashable_dict()

        assert "schema_version" in hashable
        assert "execution_id" in hashable
        assert "patches" in hashable
        assert "timestamp" not in hashable
        assert "contract_notes" not in hashable

    def test_manifest_to_canonical_dict(self):
        """[PatchManifest] to_canonical_dict() includes hash."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
        )

        canonical = manifest.to_canonical_dict()

        assert "content_hash_sha256" in canonical
        assert "schema_version" in canonical
        assert canonical["schema_version"] == PATCH_MANIFEST_SCHEMA_VERSION
        assert "timestamp" in canonical

    def test_manifest_hash_consistency(self):
        """[PatchManifest] Hash is deterministic."""
        manifest1 = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
            timestamp="2026-01-05T10:00:00",
        )

        manifest2 = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
            timestamp="2026-01-05T11:00:00",  # Different timestamp
        )

        hash1 = manifest1.to_canonical_dict()["content_hash_sha256"]
        hash2 = manifest2.to_canonical_dict()["content_hash_sha256"]

        # Timestamp is volatile, so hashes should be the same
        assert hash1 == hash2

    def test_manifest_hash_changes_with_content(self):
        """[PatchManifest] Hash changes when content changes."""
        manifest1 = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
        )

        manifest2 = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="modify")],  # Different op
        )

        hash1 = manifest1.to_canonical_dict()["content_hash_sha256"]
        hash2 = manifest2.to_canonical_dict()["content_hash_sha256"]

        assert hash1 != hash2

    def test_manifest_contract_notes_not_in_hash(self):
        """[PatchManifest] contract_notes does not affect hash."""
        manifest1 = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
            contract_notes=None,
        )

        manifest2 = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
            contract_notes="This is a note",
        )

        hash1 = manifest1.to_canonical_dict()["content_hash_sha256"]
        hash2 = manifest2.to_canonical_dict()["content_hash_sha256"]

        assert hash1 == hash2

    def test_manifest_to_json(self):
        """[PatchManifest] to_json() produces valid JSON."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
        )

        json_str = manifest.to_json()
        parsed = json.loads(json_str)

        assert parsed["execution_id"] == "exec123"

    def test_manifest_from_dict(self):
        """[PatchManifest] from_dict() reconstruction."""
        data = {
            "execution_id": "exec456",
            "project": "myproject",
            "patches": [{"path": "file.py", "op": "create"}],
            "policy": {"max_rewrite_ratio": 0.80},
            "result": "applied",
            "timestamp": "2026-01-05T10:00:00",
            "attempt": 0,
        }

        manifest = PatchManifest.from_dict(data)

        assert manifest.execution_id == "exec456"
        assert manifest.project == "myproject"
        assert len(manifest.patches) == 1


class TestPatchManifestStore:
    """Tests for PatchManifestStore."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_store_save_creates_file(self, temp_store):
        """[PatchManifestStore] save() creates file."""
        store = PatchManifestStore(str(temp_store))
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
        )

        path = store.save(manifest)

        assert path.exists()
        assert "patch_manifest" in path.name

    def test_store_save_validates_gate(self, temp_store):
        """[PatchManifestStore] save() validates contract gate."""
        store = PatchManifestStore(str(temp_store))
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
        )

        # Should not raise
        path = store.save(manifest)

        # Verify content
        with open(path) as f:
            data = json.load(f)

        hashable = extract_hashable_payload(data)
        recalculated = compute_content_hash_sha256(hashable)

        assert data["content_hash_sha256"] == recalculated

    def test_store_load_validates_gate(self, temp_store):
        """[PatchManifestStore] load() validates contract gate."""
        store = PatchManifestStore(str(temp_store))
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
        )

        path = store.save(manifest)

        # Should not raise
        loaded = store.load(path)

        assert loaded.execution_id == "exec123"

    def test_store_load_fails_on_tampered_file(self, temp_store):
        """[PatchManifestStore] load() fails on tampered file."""
        store = PatchManifestStore(str(temp_store))
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[PatchEntry(path="test.py", op="create")],
        )

        path = store.save(manifest)

        # Tamper with the file
        with open(path) as f:
            data = json.load(f)
        data["result"] = "rolled_back"  # Change content
        with open(path, "w") as f:
            json.dump(data, f)

        # Should raise
        with pytest.raises(RuntimeError) as excinfo:
            store.load(path)

        assert "Contract Gate FAILED" in str(excinfo.value)
        assert "hash mismatch" in str(excinfo.value)

    def test_store_list_manifests(self, temp_store):
        """[PatchManifestStore] list_manifests() returns all manifests."""
        store = PatchManifestStore(str(temp_store))

        # Save two manifests
        m1 = PatchManifest(execution_id="exec1", project="test", patches=[])
        m2 = PatchManifest(execution_id="exec2", project="test", patches=[])

        store.save(m1)
        store.save(m2)

        manifests = store.list_manifests("test")

        assert len(manifests) == 2

    def test_store_get_latest(self, temp_store):
        """[PatchManifestStore] get_latest() returns most recent."""
        store = PatchManifestStore(str(temp_store))

        m1 = PatchManifest(execution_id="exec1", project="test", patches=[])
        store.save(m1)

        m2 = PatchManifest(execution_id="exec2", project="test", patches=[])
        store.save(m2)

        latest = store.get_latest("test")

        assert latest is not None
        # Should be the second one (most recent)

    def test_store_get_latest_by_execution_id(self, temp_store):
        """[PatchManifestStore] get_latest() filters by execution_id."""
        store = PatchManifestStore(str(temp_store))

        m1 = PatchManifest(execution_id="exec1", project="test", patches=[])
        m2 = PatchManifest(execution_id="exec2", project="test", patches=[])

        store.save(m1)
        store.save(m2)

        latest = store.get_latest("test", execution_id="exec1")

        assert latest is not None
        assert "exec1" in latest.name


class TestVerifyManifestPrebuild:
    """Tests for verify_manifest_prebuild() function."""

    def test_verify_passes_valid_manifest(self):
        """[verify_manifest_prebuild] Passes for valid manifest."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[
                PatchEntry(path="src/app.py", op="create", rewrite_ratio=0.0),
                PatchEntry(path="src/main.py", op="modify", rewrite_ratio=0.5),
            ],
        )

        ok, errors = verify_manifest_prebuild(manifest)

        assert ok is True
        assert len(errors) == 0

    def test_verify_fails_path_traversal(self):
        """[verify_manifest_prebuild] Fails on path traversal."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[
                PatchEntry(path="../../../etc/passwd", op="create"),
            ],
        )

        ok, errors = verify_manifest_prebuild(manifest)

        assert ok is False
        assert any("Path traversal" in e for e in errors)

    def test_verify_fails_blocked_path(self):
        """[verify_manifest_prebuild] Fails on blocked path."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[
                PatchEntry(path="/home/bazari/engine/secret.py", op="create"),
            ],
        )

        ok, errors = verify_manifest_prebuild(manifest)

        assert ok is False
        assert any("Blocked path" in e for e in errors)

    def test_verify_fails_high_rewrite_ratio(self):
        """[verify_manifest_prebuild] Fails on high rewrite ratio."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[
                PatchEntry(path="src/app.py", op="modify", rewrite_ratio=0.95),
            ],
        )

        ok, errors = verify_manifest_prebuild(manifest)

        assert ok is False
        assert any("Rewrite ratio exceeded" in e for e in errors)

    def test_verify_multiple_errors(self):
        """[verify_manifest_prebuild] Reports all errors."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[
                PatchEntry(path="../bad.py", op="create"),  # Path traversal
                PatchEntry(path="/home/bazari/engine/x.py", op="modify"),  # Blocked
                PatchEntry(path="ok.py", op="modify", rewrite_ratio=0.99),  # High ratio
            ],
        )

        ok, errors = verify_manifest_prebuild(manifest)

        assert ok is False
        assert len(errors) >= 3


class TestHashableVsVolatileFields:
    """Tests for HASHABLE_FIELDS and VOLATILE_FIELDS constants."""

    def test_hashable_fields_defined(self):
        """[Constants] HASHABLE_FIELDS is defined."""
        assert len(HASHABLE_FIELDS) > 0
        assert "schema_version" in HASHABLE_FIELDS
        assert "execution_id" in HASHABLE_FIELDS
        assert "patches" in HASHABLE_FIELDS

    def test_volatile_fields_defined(self):
        """[Constants] VOLATILE_FIELDS is defined."""
        assert len(VOLATILE_FIELDS) > 0
        assert "timestamp" in VOLATILE_FIELDS
        assert "contract_notes" in VOLATILE_FIELDS
        assert "content_hash_sha256" in VOLATILE_FIELDS

    def test_no_overlap(self):
        """[Constants] HASHABLE_FIELDS and VOLATILE_FIELDS don't overlap."""
        overlap = set(HASHABLE_FIELDS) & set(VOLATILE_FIELDS)
        assert len(overlap) == 0, f"Overlapping fields: {overlap}"


class TestManifestAttemptField:
    """Tests for PatchManifest attempt field (fix loop support)."""

    def test_manifest_default_attempt(self):
        """[PatchManifest] Default attempt is 0."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[],
        )

        assert manifest.attempt == 0

    def test_manifest_with_attempt(self):
        """[PatchManifest] attempt can be set."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[],
            attempt=3,
        )

        assert manifest.attempt == 3

    def test_manifest_attempt_in_canonical(self):
        """[PatchManifest] attempt appears in canonical dict."""
        manifest = PatchManifest(
            execution_id="exec123",
            project="test",
            patches=[],
            attempt=2,
        )

        canonical = manifest.to_canonical_dict()

        assert canonical["attempt"] == 2

    def test_manifest_attempt_is_volatile(self):
        """[PatchManifest] attempt is volatile (not in hash)."""
        # attempt is in VOLATILE_FIELDS
        assert "attempt" in VOLATILE_FIELDS
