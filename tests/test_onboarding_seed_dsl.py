"""Tests for GAP 1: Real decision anchor (source_idl_sha256) in onboarding.

Verifies that:
1. Seed DSL files are copied into the bundle (source.idl or departments/<dept>/source.idl)
2. Seed DSL files are added to manifest as contracts with required=false
3. source_idl_sha256 is computed from real seed(s), not placeholder
4. Multi-dept bundles have source_idl_by_dept and aggregated hash
5. Proof passes with real hash
6. Onboarding fails deterministically if seed is missing
"""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.console.bundle_generator import (
    generate_bundle_from_template,
    _compute_sha256,
    _compute_aggregated_source_idl_hash,
    _copy_seed_dsl_to_bundle,
    SEED_DSL_NOT_FOUND,
)
from engine.console.templates_registry import (
    BundleTemplate,
    get_template,
    AVAILABLE_TEMPLATES,
)
from engine.core.errors import SEED_DSL_MISSING_FOR_DEPT


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def mock_institution():
    """Mock institution for tests."""
    inst = MagicMock()
    inst.id = "test-inst-1234-5678-9abc-def0"
    inst.slug = "test-institution"
    return inst


@pytest.fixture
def mock_registry(mock_institution):
    """Mock institutions registry."""
    registry = MagicMock()
    registry.get_by_id.return_value = (mock_institution, None, None)
    return registry


class TestSeedDslHashCalculation:
    """Test hash calculation for single and multi-dept bundles."""

    def test_single_dept_hash_is_direct(self):
        """Single dept hash is the hash of the seed file directly."""
        dept_hashes = {"finance": "abc123def456"}
        result = _compute_aggregated_source_idl_hash(dept_hashes)
        assert result == "abc123def456"

    def test_multi_dept_hash_is_aggregated(self):
        """Multi-dept hash is sha256 of concatenated dept:hash lines."""
        dept_hashes = {
            "finance": "abc123",
            "support": "def456",
        }
        result = _compute_aggregated_source_idl_hash(dept_hashes)

        # Verify formula: sha256("<dept_id>:<hash>\n" sorted by dept_id)
        expected_str = "finance:abc123\nsupport:def456\n"
        expected_hash = hashlib.sha256(expected_str.encode("utf-8")).hexdigest()
        assert result == expected_hash

    def test_multi_dept_hash_is_deterministic_sorted(self):
        """Multi-dept hash is sorted by dept_id for determinism."""
        # Order shouldn't matter - result should be the same
        dept_hashes_1 = {"support": "def456", "finance": "abc123"}
        dept_hashes_2 = {"finance": "abc123", "support": "def456"}

        result_1 = _compute_aggregated_source_idl_hash(dept_hashes_1)
        result_2 = _compute_aggregated_source_idl_hash(dept_hashes_2)

        assert result_1 == result_2


class TestCopySeedDslToBundle:
    """Test copying seed DSL files into bundles."""

    def test_single_dept_copies_to_bundle_root(self, temp_dir):
        """Single dept copies source.idl to bundle root."""
        # Create a mock seed file
        seeds_dir = temp_dir / "seeds"
        seeds_dir.mkdir()
        seed_file = seeds_dir / "finance.idl"
        seed_file.write_text("// Finance IDL\n")

        bundle_dir = temp_dir / "bundle"
        bundle_dir.mkdir()

        # Create mock template
        with patch("engine.console.bundle_generator.get_template") as mock_get:
            with patch("engine.console.bundle_generator.get_repo_root") as mock_root:
                mock_root.return_value = temp_dir
                mock_template = MagicMock()
                mock_template.seed_dsl_paths = {"finance": "seeds/finance.idl"}
                mock_get.return_value = mock_template

                success, dept_hashes, error = _copy_seed_dsl_to_bundle(
                    "finance-pilot", bundle_dir, ["finance"]
                )

        assert success is True
        assert error is None
        assert "finance" in dept_hashes

        # Verify file was copied to bundle root
        source_idl = bundle_dir / "source.idl"
        assert source_idl.exists()
        assert source_idl.read_text() == "// Finance IDL\n"

    def test_multi_dept_copies_to_departments_dir(self, temp_dir):
        """Multi dept copies source.idl to departments/<dept>/."""
        # Create mock seed files
        seeds_dir = temp_dir / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "finance.idl").write_text("// Finance IDL\n")
        (seeds_dir / "support.idl").write_text("// Support IDL\n")

        bundle_dir = temp_dir / "bundle"
        bundle_dir.mkdir()

        # Create mock template
        with patch("engine.console.bundle_generator.get_template") as mock_get:
            with patch("engine.console.bundle_generator.get_repo_root") as mock_root:
                mock_root.return_value = temp_dir
                mock_template = MagicMock()
                mock_template.seed_dsl_paths = {
                    "finance": "seeds/finance.idl",
                    "support": "seeds/support.idl",
                }
                mock_get.return_value = mock_template

                success, dept_hashes, error = _copy_seed_dsl_to_bundle(
                    "multi-pilot", bundle_dir, ["finance", "support"]
                )

        assert success is True
        assert error is None
        assert "finance" in dept_hashes
        assert "support" in dept_hashes

        # Verify files were copied to departments dirs
        finance_idl = bundle_dir / "departments" / "finance" / "source.idl"
        support_idl = bundle_dir / "departments" / "support" / "source.idl"
        assert finance_idl.exists()
        assert support_idl.exists()
        assert finance_idl.read_text() == "// Finance IDL\n"
        assert support_idl.read_text() == "// Support IDL\n"

    def test_fails_if_seed_file_missing(self, temp_dir):
        """Fails deterministically if seed file doesn't exist."""
        bundle_dir = temp_dir / "bundle"
        bundle_dir.mkdir()

        with patch("engine.console.bundle_generator.get_template") as mock_get:
            with patch("engine.console.bundle_generator.get_repo_root") as mock_root:
                mock_root.return_value = temp_dir
                mock_template = MagicMock()
                mock_template.seed_dsl_paths = {"finance": "seeds/nonexistent.idl"}
                mock_get.return_value = mock_template

                success, dept_hashes, error = _copy_seed_dsl_to_bundle(
                    "finance-pilot", bundle_dir, ["finance"]
                )

        assert success is False
        assert "not found" in error.lower()


class TestTemplateRegistryHasSeedPaths:
    """Test that template registry declares seed DSL paths."""

    def test_finance_pilot_has_seed_path(self):
        """finance-pilot template has seed_dsl_paths declared."""
        template = get_template("finance-pilot")
        assert template is not None
        assert template.seed_dsl_paths is not None
        assert "finance" in template.seed_dsl_paths

    def test_multi_pilot_has_seed_paths(self):
        """multi-pilot template has seed_dsl_paths for all depts."""
        template = get_template("multi-pilot")
        assert template is not None
        assert template.seed_dsl_paths is not None
        assert "finance" in template.seed_dsl_paths
        assert "support" in template.seed_dsl_paths

    def test_all_templates_have_seed_paths_for_all_depts(self):
        """All templates have seed_dsl_paths for all their departments."""
        for template in AVAILABLE_TEMPLATES:
            for dept in template.departments:
                assert dept in template.seed_dsl_paths, (
                    f"Template {template.id} missing seed_dsl_paths for {dept}"
                )


class TestSeedFilesExist:
    """Test that declared seed DSL files exist in the repo."""

    def test_finance_seed_exists(self):
        """seeds/finance.idl exists."""
        from engine.console.templates_registry import get_repo_root
        seed_path = get_repo_root() / "seeds" / "finance.idl"
        assert seed_path.exists(), f"Seed file not found: {seed_path}"

    def test_support_seed_exists(self):
        """seeds/support.idl exists."""
        from engine.console.templates_registry import get_repo_root
        seed_path = get_repo_root() / "seeds" / "support.idl"
        assert seed_path.exists(), f"Seed file not found: {seed_path}"


class TestOnboardingWithRealHash:
    """Integration tests for onboarding with real hash."""

    @pytest.fixture
    def mock_env(self, temp_dir, mock_registry):
        """Set up mocked environment for onboarding tests."""
        # Create template bundle structure
        template_dir = temp_dir / "bundles" / "finance-pilot"
        template_dir.mkdir(parents=True)

        # Create minimal manifest
        manifest = {
            "name": "finance-pilot",
            "version": "1.0.0",
            "contracts": [
                {"file": "contracts/expense.json", "sha256": "SHA256:abc123"},
            ],
        }
        (template_dir / "bundle.manifest.json").write_text(json.dumps(manifest))

        # Create contract file
        contracts_dir = template_dir / "contracts"
        contracts_dir.mkdir()
        (contracts_dir / "expense.json").write_text('{"type": "expense"}')

        # Create ledger
        ledger = {
            "ledger_id": "test",
            "contracts": [],
        }
        (template_dir / "contract_ledger.json").write_text(json.dumps(ledger))

        # Create seed file
        seeds_dir = temp_dir / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "finance.idl").write_text("// Finance IDL v1.2.2\n")

        # Institution data root
        inst_root = temp_dir / "institutions" / "test-inst"
        inst_root.mkdir(parents=True)

        return {
            "temp_dir": temp_dir,
            "template_dir": template_dir,
            "seeds_dir": seeds_dir,
            "inst_root": inst_root,
            "registry": mock_registry,
        }

    def test_onboarding_generates_real_hash(self, mock_env):
        """Onboarding generates bundle with real source_idl_sha256."""
        with patch("engine.console.bundle_generator.get_institutions_registry") as mock_reg:
            with patch("engine.console.bundle_generator.get_template_path") as mock_path:
                with patch("engine.console.bundle_generator.get_institution_root") as mock_root:
                    with patch("engine.console.bundle_generator.get_repo_root") as mock_repo:
                        with patch("engine.console.bundle_generator.verify_bundle_offline") as mock_proof:
                            mock_reg.return_value = mock_env["registry"]
                            mock_path.return_value = mock_env["template_dir"]
                            mock_root.return_value = mock_env["inst_root"]
                            mock_repo.return_value = mock_env["temp_dir"]

                            # Mock proof to pass
                            proof_result = MagicMock()
                            proof_result.passed = True
                            mock_proof.return_value = proof_result

                            result = generate_bundle_from_template(
                                "test-inst-1234", "finance-pilot"
                            )

        assert result.success is True
        assert result.bundle_path is not None

        # Verify ledger has real hash (not placeholder)
        ledger_path = result.bundle_path / "contract_ledger.json"
        with open(ledger_path) as f:
            ledger = json.load(f)

        assert "source_idl_sha256" in ledger
        assert ledger["source_idl_sha256"] != "0" * 64  # Not placeholder
        assert len(ledger["source_idl_sha256"]) == 64  # Valid SHA256

        # Verify hash matches actual seed file
        source_idl_path = result.bundle_path / "source.idl"
        assert source_idl_path.exists()
        actual_hash = _compute_sha256(source_idl_path)
        assert ledger["source_idl_sha256"] == actual_hash

    def test_onboarding_includes_seed_in_manifest(self, mock_env):
        """Onboarding adds source.idl to manifest with required=false."""
        with patch("engine.console.bundle_generator.get_institutions_registry") as mock_reg:
            with patch("engine.console.bundle_generator.get_template_path") as mock_path:
                with patch("engine.console.bundle_generator.get_institution_root") as mock_root:
                    with patch("engine.console.bundle_generator.get_repo_root") as mock_repo:
                        with patch("engine.console.bundle_generator.verify_bundle_offline") as mock_proof:
                            mock_reg.return_value = mock_env["registry"]
                            mock_path.return_value = mock_env["template_dir"]
                            mock_root.return_value = mock_env["inst_root"]
                            mock_repo.return_value = mock_env["temp_dir"]

                            proof_result = MagicMock()
                            proof_result.passed = True
                            mock_proof.return_value = proof_result

                            result = generate_bundle_from_template(
                                "test-inst-1234", "finance-pilot"
                            )

        assert result.success is True

        # Verify manifest includes source.idl
        manifest_path = result.bundle_path / "bundle.manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        source_idl_entry = None
        for c in manifest["contracts"]:
            if c.get("file") == "source.idl":
                source_idl_entry = c
                break

        assert source_idl_entry is not None
        assert source_idl_entry.get("required") is False

    def test_onboarding_fails_without_seed_paths(self, mock_env):
        """Onboarding fails if template has no seed_dsl_paths."""
        # Create template without seed paths
        with patch("engine.console.bundle_generator.get_institutions_registry") as mock_reg:
            with patch("engine.console.bundle_generator.get_template") as mock_get:
                mock_reg.return_value = mock_env["registry"]

                mock_template = MagicMock()
                mock_template.seed_dsl_paths = {}  # Empty!
                mock_template.departments = ["finance"]
                mock_get.return_value = mock_template

                result = generate_bundle_from_template(
                    "test-inst-1234", "finance-pilot"
                )

        assert result.success is False
        assert result.error_code == SEED_DSL_NOT_FOUND

    def test_onboarding_fails_if_dept_missing_seed_path(self, mock_env):
        """Onboarding fails if a department has no seed path."""
        with patch("engine.console.bundle_generator.get_institutions_registry") as mock_reg:
            with patch("engine.console.bundle_generator.get_template") as mock_get:
                mock_reg.return_value = mock_env["registry"]

                mock_template = MagicMock()
                mock_template.seed_dsl_paths = {"finance": "seeds/finance.idl"}
                mock_template.departments = ["finance", "support"]  # support missing!
                mock_get.return_value = mock_template

                result = generate_bundle_from_template(
                    "test-inst-1234", "multi-pilot"
                )

        assert result.success is False
        assert result.error_code == SEED_DSL_MISSING_FOR_DEPT


class TestMultiDeptOnboarding:
    """Test multi-department bundle onboarding."""

    @pytest.fixture
    def mock_multi_env(self, temp_dir, mock_registry):
        """Set up mocked environment for multi-dept onboarding tests."""
        # Create template bundle structure
        template_dir = temp_dir / "bundles" / "multi-pilot"
        template_dir.mkdir(parents=True)

        # Create minimal manifest
        manifest = {
            "name": "multi-pilot",
            "version": "1.0.0",
            "contracts": [],
        }
        (template_dir / "bundle.manifest.json").write_text(json.dumps(manifest))

        # Create ledger
        ledger = {"ledger_id": "test", "contracts": []}
        (template_dir / "contract_ledger.json").write_text(json.dumps(ledger))

        # Create seed files
        seeds_dir = temp_dir / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "finance.idl").write_text("// Finance IDL\n")
        (seeds_dir / "support.idl").write_text("// Support IDL\n")

        # Institution data root
        inst_root = temp_dir / "institutions" / "test-inst"
        inst_root.mkdir(parents=True)

        return {
            "temp_dir": temp_dir,
            "template_dir": template_dir,
            "seeds_dir": seeds_dir,
            "inst_root": inst_root,
            "registry": mock_registry,
        }

    def test_multi_dept_has_source_idl_by_dept(self, mock_multi_env):
        """Multi-dept bundle has source_idl_by_dept in ledger."""
        with patch("engine.console.bundle_generator.get_institutions_registry") as mock_reg:
            with patch("engine.console.bundle_generator.get_template_path") as mock_path:
                with patch("engine.console.bundle_generator.get_institution_root") as mock_root:
                    with patch("engine.console.bundle_generator.get_repo_root") as mock_repo:
                        with patch("engine.console.bundle_generator.verify_bundle_offline") as mock_proof:
                            mock_reg.return_value = mock_multi_env["registry"]
                            mock_path.return_value = mock_multi_env["template_dir"]
                            mock_root.return_value = mock_multi_env["inst_root"]
                            mock_repo.return_value = mock_multi_env["temp_dir"]

                            proof_result = MagicMock()
                            proof_result.passed = True
                            mock_proof.return_value = proof_result

                            result = generate_bundle_from_template(
                                "test-inst-1234", "multi-pilot"
                            )

        assert result.success is True

        # Verify ledger has source_idl_by_dept
        ledger_path = result.bundle_path / "contract_ledger.json"
        with open(ledger_path) as f:
            ledger = json.load(f)

        assert "source_idl_by_dept" in ledger
        assert "finance" in ledger["source_idl_by_dept"]
        assert "support" in ledger["source_idl_by_dept"]

    def test_multi_dept_has_departments_source_idl_files(self, mock_multi_env):
        """Multi-dept bundle has departments/<dept>/source.idl files."""
        with patch("engine.console.bundle_generator.get_institutions_registry") as mock_reg:
            with patch("engine.console.bundle_generator.get_template_path") as mock_path:
                with patch("engine.console.bundle_generator.get_institution_root") as mock_root:
                    with patch("engine.console.bundle_generator.get_repo_root") as mock_repo:
                        with patch("engine.console.bundle_generator.verify_bundle_offline") as mock_proof:
                            mock_reg.return_value = mock_multi_env["registry"]
                            mock_path.return_value = mock_multi_env["template_dir"]
                            mock_root.return_value = mock_multi_env["inst_root"]
                            mock_repo.return_value = mock_multi_env["temp_dir"]

                            proof_result = MagicMock()
                            proof_result.passed = True
                            mock_proof.return_value = proof_result

                            result = generate_bundle_from_template(
                                "test-inst-1234", "multi-pilot"
                            )

        assert result.success is True

        # Verify department source.idl files exist
        finance_idl = result.bundle_path / "departments" / "finance" / "source.idl"
        support_idl = result.bundle_path / "departments" / "support" / "source.idl"
        assert finance_idl.exists()
        assert support_idl.exists()

    def test_multi_dept_aggregated_hash_is_correct(self, mock_multi_env):
        """Multi-dept source_idl_sha256 is correctly aggregated."""
        with patch("engine.console.bundle_generator.get_institutions_registry") as mock_reg:
            with patch("engine.console.bundle_generator.get_template_path") as mock_path:
                with patch("engine.console.bundle_generator.get_institution_root") as mock_root:
                    with patch("engine.console.bundle_generator.get_repo_root") as mock_repo:
                        with patch("engine.console.bundle_generator.verify_bundle_offline") as mock_proof:
                            mock_reg.return_value = mock_multi_env["registry"]
                            mock_path.return_value = mock_multi_env["template_dir"]
                            mock_root.return_value = mock_multi_env["inst_root"]
                            mock_repo.return_value = mock_multi_env["temp_dir"]

                            proof_result = MagicMock()
                            proof_result.passed = True
                            mock_proof.return_value = proof_result

                            result = generate_bundle_from_template(
                                "test-inst-1234", "multi-pilot"
                            )

        assert result.success is True

        ledger_path = result.bundle_path / "contract_ledger.json"
        with open(ledger_path) as f:
            ledger = json.load(f)

        # Compute expected aggregated hash
        finance_hash = ledger["source_idl_by_dept"]["finance"]
        support_hash = ledger["source_idl_by_dept"]["support"]

        expected_str = f"finance:{finance_hash}\nsupport:{support_hash}\n"
        expected_hash = hashlib.sha256(expected_str.encode("utf-8")).hexdigest()

        assert ledger["source_idl_sha256"] == expected_hash
