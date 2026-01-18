"""Tests for pipeline ZIP export with multi-department bundles."""

import json
import os
import zipfile
import pytest
from pathlib import Path

from engine.ise.compiler import compile_bundle
from engine.pipeline.exporter import (
    export_bundle_zip,
    compute_sha256,
    _create_deterministic_zip,
)


# Sample multi-department IDL
MULTI_DEPT_IDL = {
    "system": "MultiDeptExportTest",
    "version": "1.0.0",
    "departments": [
        {"dept_id": "finance"},
        {"dept_id": "hr"},
    ],
    "contracts": [
        {
            "contract_id": "budget-request",
            "provider_dept": "finance",
            "consumers": ["hr"],
        },
    ],
    "entities": [
        {"name": "Expense", "entity_type": "expense"},
    ],
    "rbac": {
        "roles": [
            {"name": "admin", "permissions": ["expense.create"]},
        ]
    },
}


class TestExportZipMultiDept:
    """Tests for ZIP export with multi-department bundles."""

    @pytest.fixture
    def setup_bundle(self, tmp_path: Path):
        """Create a multi-dept bundle for testing."""
        run_id = "test-export-run"
        bundle_name = "multi-export-test"

        # Create dev-runs structure
        bundles_root = tmp_path / "bundles"
        run_dir = bundles_root / "dev-runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Compile bundle
        idl = json.dumps(MULTI_DEPT_IDL)
        result = compile_bundle(
            idl=idl,
            bundle_name=bundle_name,
            output_dir=str(run_dir),
            validate_finance_pilot=False,
        )
        assert result.success is True

        return {
            "bundles_root": str(bundles_root),
            "run_id": run_id,
            "bundle_name": bundle_name,
            "bundle_path": result.bundle_path,
        }

    def test_export_multi_dept_zip_success(self, setup_bundle):
        """export_bundle_zip should succeed for multi-dept bundle."""
        result = export_bundle_zip(
            run_id=setup_bundle["run_id"],
            bundle_name=setup_bundle["bundle_name"],
            bundles_root=setup_bundle["bundles_root"],
        )

        assert result.success is True
        assert result.zip_path is not None
        assert Path(result.zip_path).exists()
        assert result.zip_sha256 is not None

    def test_export_zip_contains_contracts_json(self, setup_bundle):
        """Exported ZIP should contain contracts.json."""
        result = export_bundle_zip(
            run_id=setup_bundle["run_id"],
            bundle_name=setup_bundle["bundle_name"],
            bundles_root=setup_bundle["bundles_root"],
        )

        with zipfile.ZipFile(result.zip_path, "r") as zf:
            names = zf.namelist()

        # Should have contracts.json at root level inside archive
        expected_path = f"{setup_bundle['bundle_name']}/contracts.json"
        assert expected_path in names

    def test_export_zip_contains_departments(self, setup_bundle):
        """Exported ZIP should contain departments/ subdirectories."""
        result = export_bundle_zip(
            run_id=setup_bundle["run_id"],
            bundle_name=setup_bundle["bundle_name"],
            bundles_root=setup_bundle["bundles_root"],
        )

        with zipfile.ZipFile(result.zip_path, "r") as zf:
            names = zf.namelist()

        bundle_name = setup_bundle["bundle_name"]

        # Check department artifacts
        for dept_id in ["finance", "hr"]:
            assert f"{bundle_name}/departments/{dept_id}/rbac.json" in names
            assert f"{bundle_name}/departments/{dept_id}/workflows.json" in names
            assert f"{bundle_name}/departments/{dept_id}/approvals.json" in names
            assert f"{bundle_name}/departments/{dept_id}/sod.json" in names
            assert f"{bundle_name}/departments/{dept_id}/invariants.json" in names
            assert f"{bundle_name}/departments/{dept_id}/openapi.yaml" in names

    def test_export_zip_deterministic(self, setup_bundle):
        """Exporting same bundle twice should produce identical ZIPs."""
        # First export
        result1 = export_bundle_zip(
            run_id=setup_bundle["run_id"],
            bundle_name=setup_bundle["bundle_name"],
            bundles_root=setup_bundle["bundles_root"],
        )

        # Get hash
        hash1 = result1.zip_sha256

        # Delete and re-export
        Path(result1.zip_path).unlink()

        result2 = export_bundle_zip(
            run_id=setup_bundle["run_id"],
            bundle_name=setup_bundle["bundle_name"],
            bundles_root=setup_bundle["bundles_root"],
        )

        hash2 = result2.zip_sha256

        # Hashes should be identical
        assert hash1 == hash2, "ZIP hashes should be deterministic"

    def test_export_zip_sorted_paths(self, setup_bundle):
        """ZIP entries should be sorted alphabetically."""
        result = export_bundle_zip(
            run_id=setup_bundle["run_id"],
            bundle_name=setup_bundle["bundle_name"],
            bundles_root=setup_bundle["bundles_root"],
        )

        with zipfile.ZipFile(result.zip_path, "r") as zf:
            names = zf.namelist()

        # Names should be sorted
        assert names == sorted(names), "ZIP entries should be sorted"

    def test_export_zip_fixed_timestamp(self, setup_bundle):
        """ZIP entries should have fixed timestamp (1980-01-01)."""
        result = export_bundle_zip(
            run_id=setup_bundle["run_id"],
            bundle_name=setup_bundle["bundle_name"],
            bundles_root=setup_bundle["bundles_root"],
        )

        with zipfile.ZipFile(result.zip_path, "r") as zf:
            for info in zf.infolist():
                # date_time should be (1980, 1, 1, 0, 0, 0)
                assert info.date_time == (1980, 1, 1, 0, 0, 0), \
                    f"Entry {info.filename} has wrong timestamp: {info.date_time}"


class TestDeterministicZipMultiDept:
    """Tests for _create_deterministic_zip with nested directories."""

    def test_create_zip_with_nested_dirs(self, tmp_path: Path):
        """_create_deterministic_zip should handle nested directories."""
        # Create source directory with nested structure
        source = tmp_path / "source"
        source.mkdir()

        # Root files
        (source / "manifest.json").write_text('{"version": "1.0"}')
        (source / "contracts.json").write_text('{"contracts": []}')

        # Nested department files
        dept_finance = source / "departments" / "finance"
        dept_finance.mkdir(parents=True)
        (dept_finance / "rbac.json").write_text('{"roles": []}')
        (dept_finance / "openapi.yaml").write_text("openapi: 3.0.0")

        dept_hr = source / "departments" / "hr"
        dept_hr.mkdir(parents=True)
        (dept_hr / "rbac.json").write_text('{"roles": []}')

        # Create ZIP
        zip_path = tmp_path / "test.zip"
        _create_deterministic_zip(source, zip_path, "test-bundle")

        # Verify contents
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        assert "test-bundle/manifest.json" in names
        assert "test-bundle/contracts.json" in names
        assert "test-bundle/departments/finance/rbac.json" in names
        assert "test-bundle/departments/finance/openapi.yaml" in names
        assert "test-bundle/departments/hr/rbac.json" in names

    def test_deterministic_zip_same_hash(self, tmp_path: Path):
        """Creating ZIP twice from same source should give same hash."""
        # Create source
        source = tmp_path / "source"
        source.mkdir()
        (source / "file1.json").write_text('{"a": 1}')

        nested = source / "nested"
        nested.mkdir()
        (nested / "file2.json").write_text('{"b": 2}')

        # Create ZIP twice
        zip1 = tmp_path / "test1.zip"
        zip2 = tmp_path / "test2.zip"

        _create_deterministic_zip(source, zip1, "bundle")
        _create_deterministic_zip(source, zip2, "bundle")

        # Compare hashes
        hash1 = compute_sha256(zip1)
        hash2 = compute_sha256(zip2)

        assert hash1 == hash2
