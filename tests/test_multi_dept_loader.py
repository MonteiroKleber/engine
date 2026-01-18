"""Tests for Multi-Department Bundle Loader."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.runtime_state import runtime_state
from engine.core.errors import (
    BUNDLE_CONTRACT_HASH_MISMATCH,
    BUNDLE_MULTI_DEPT_MISSING_CONTRACTS,
    BUNDLE_DEPT_ARTIFACT_MISSING,
    BUNDLE_DEPT_ARTIFACT_INVALID,
)
from engine.loader.load_bundle import (
    load_bundle,
    get_bundle_context,
    _set_bundle_context,
    DEPT_REQUIRED_ARTIFACTS,
)
from engine.loader.verify_hashes import compute_sha256
from engine.api.server import app


# Path to existing single-dept bundle
FINANCE_PILOT_PATH = Path("bundles/finance-pilot")


@pytest.fixture(autouse=True)
def reset_runtime_state():
    """Reset runtime state before each test."""
    runtime_state.set_active()
    _set_bundle_context(None)
    yield
    runtime_state.set_active()
    _set_bundle_context(None)


def create_manifest(bundle_path: Path, contracts: list, name: str = "test-bundle") -> str:
    """Create a bundle manifest with given contracts. Returns manifest hash."""
    manifest = {
        "name": name,
        "version": "1.0.0",
        "contracts": contracts,
    }
    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return compute_sha256(manifest_path)


def create_contract_ledger(bundle_path: Path, entries: list) -> str:
    """Create a contract_ledger.json. Returns hash."""
    ledger_path = bundle_path / "contract_ledger.json"
    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, indent=2)
    return compute_sha256(ledger_path)


def create_contracts_json(bundle_path: Path, departments: list) -> str:
    """Create contracts.json for multi-dept bundle. Returns hash."""
    contracts = {
        "version": "1.0.0",
        "departments": departments,
    }
    contracts_path = bundle_path / "contracts.json"
    with open(contracts_path, "w", encoding="utf-8") as f:
        json.dump(contracts, f, indent=2)
    return compute_sha256(contracts_path)


def copy_finance_pilot_artifacts(dest_path: Path) -> dict:
    """Copy finance-pilot artifacts to destination. Returns dict of hashes."""
    hashes = {}
    for artifact in DEPT_REQUIRED_ARTIFACTS:
        src = FINANCE_PILOT_PATH / artifact
        dst = dest_path / artifact
        if src.exists():
            shutil.copy(src, dst)
            hashes[artifact] = compute_sha256(dst)
    return hashes


def create_minimal_dept_artifacts(dept_path: Path) -> dict:
    """Create minimal valid artifacts for a department. Returns dict of hashes."""
    dept_path.mkdir(parents=True, exist_ok=True)
    hashes = {}

    # rbac.json
    rbac = {"version": "1.0.0", "roles": [], "permissions": []}
    rbac_path = dept_path / "rbac.json"
    with open(rbac_path, "w", encoding="utf-8") as f:
        json.dump(rbac, f, indent=2)
    hashes["rbac.json"] = compute_sha256(rbac_path)

    # approvals.json
    approvals = {"version": "1.0.0", "rules": []}
    approvals_path = dept_path / "approvals.json"
    with open(approvals_path, "w", encoding="utf-8") as f:
        json.dump(approvals, f, indent=2)
    hashes["approvals.json"] = compute_sha256(approvals_path)

    # workflows.json
    workflows = {"version": "1.0.0", "workflows": []}
    workflows_path = dept_path / "workflows.json"
    with open(workflows_path, "w", encoding="utf-8") as f:
        json.dump(workflows, f, indent=2)
    hashes["workflows.json"] = compute_sha256(workflows_path)

    # sod.json
    sod = {"version": "1.0.0", "constraints": []}
    sod_path = dept_path / "sod.json"
    with open(sod_path, "w", encoding="utf-8") as f:
        json.dump(sod, f, indent=2)
    hashes["sod.json"] = compute_sha256(sod_path)

    # invariants.json
    invariants = {"version": "1.0.0", "rules": []}
    invariants_path = dept_path / "invariants.json"
    with open(invariants_path, "w", encoding="utf-8") as f:
        json.dump(invariants, f, indent=2)
    hashes["invariants.json"] = compute_sha256(invariants_path)

    # openapi.yaml
    openapi = """openapi: "3.0.0"
info:
  title: Test API
  version: "1.0.0"
paths: {}
"""
    openapi_path = dept_path / "openapi.yaml"
    with open(openapi_path, "w", encoding="utf-8") as f:
        f.write(openapi)
    hashes["openapi.yaml"] = compute_sha256(openapi_path)

    return hashes


class TestSingleDeptBundleIntact:
    """Test 1: Existing single-dept bundle (finance-pilot) continues to work."""

    def test_single_dept_bundle_loads_active(self, tmp_path: Path):
        """Single-dept bundle should load and result in ACTIVE mode."""
        # Copy finance-pilot to tmp_path
        bundle_path = tmp_path / "finance-pilot"
        shutil.copytree(FINANCE_PILOT_PATH, bundle_path)

        # Load bundle
        result = load_bundle(bundle_path)

        # Verify ACTIVE mode
        assert result is not None
        assert runtime_state.is_active()
        assert runtime_state.reason_code is None

        # Verify bundle context
        ctx = get_bundle_context()
        assert ctx is not None
        assert ctx.mode == "single"
        assert len(ctx.departments) == 0

    def test_single_dept_health_200(self, tmp_path: Path):
        """Single-dept bundle should return 200 on /health."""
        bundle_path = tmp_path / "finance-pilot"
        shutil.copytree(FINANCE_PILOT_PATH, bundle_path)

        load_bundle(bundle_path)

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["mode"] == "ACTIVE"


class TestMultiDeptBundleValid:
    """Test 2: Valid multi-dept bundle loads correctly."""

    def test_multi_dept_bundle_loads_active(self, tmp_path: Path):
        """Multi-dept bundle with all valid artifacts should load and result in ACTIVE."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        # Create departments directory
        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        # Create finance department with artifacts
        finance_dept = departments_path / "finance"
        dept_hashes = create_minimal_dept_artifacts(finance_dept)

        # Create contracts.json
        contracts_hash = create_contracts_json(bundle_path, ["finance"])

        # Create contract_ledger.json with hashes
        ledger_entries = [
            {"file": "contracts.json", "sha256": contracts_hash},
        ]
        for artifact, hash_val in dept_hashes.items():
            ledger_entries.append({
                "file": f"departments/finance/{artifact}",
                "sha256": hash_val,
            })
        create_contract_ledger(bundle_path, ledger_entries)

        # Create manifest with contracts
        manifest_contracts = [
            {"file": "contracts.json", "sha256": contracts_hash, "required": True},
        ]
        for artifact, hash_val in dept_hashes.items():
            manifest_contracts.append({
                "file": f"departments/finance/{artifact}",
                "sha256": hash_val,
                "required": True,
            })
        create_manifest(bundle_path, manifest_contracts, "multi-bundle")

        # Load bundle
        result = load_bundle(bundle_path)

        # Verify ACTIVE mode
        assert result is not None
        assert runtime_state.is_active()

        # Verify bundle context
        ctx = get_bundle_context()
        assert ctx is not None
        assert ctx.mode == "multi"
        assert "finance" in ctx.departments
        assert ctx.contracts_catalog is not None

    def test_multi_dept_with_multiple_departments(self, tmp_path: Path):
        """Multi-dept bundle with multiple departments should load correctly."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        # Create two departments
        all_hashes = {}
        for dept_name in ["finance", "hr"]:
            dept_path = departments_path / dept_name
            dept_hashes = create_minimal_dept_artifacts(dept_path)
            all_hashes[dept_name] = dept_hashes

        # Create contracts.json
        contracts_hash = create_contracts_json(bundle_path, ["finance", "hr"])

        # Create manifest with all artifacts
        manifest_contracts = [
            {"file": "contracts.json", "sha256": contracts_hash, "required": True},
        ]
        for dept_name, dept_hashes in all_hashes.items():
            for artifact, hash_val in dept_hashes.items():
                manifest_contracts.append({
                    "file": f"departments/{dept_name}/{artifact}",
                    "sha256": hash_val,
                    "required": True,
                })

        create_contract_ledger(bundle_path, [])
        create_manifest(bundle_path, manifest_contracts)

        # Load bundle
        result = load_bundle(bundle_path)

        assert result is not None
        assert runtime_state.is_active()

        ctx = get_bundle_context()
        assert ctx.mode == "multi"
        assert "finance" in ctx.departments
        assert "hr" in ctx.departments


class TestMultiDeptMissingContractsJson:
    """Test 3: Multi-dept without contracts.json enters SAFE_MODE."""

    def test_missing_contracts_json_safe_mode(self, tmp_path: Path):
        """Multi-dept bundle without contracts.json should enter SAFE_MODE."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        # Create departments directory (makes it multi-mode)
        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        # Create a department
        finance_dept = departments_path / "finance"
        create_minimal_dept_artifacts(finance_dept)

        # Create manifest but NO contracts.json
        create_contract_ledger(bundle_path, [])
        create_manifest(bundle_path, [])

        # Load bundle
        result = load_bundle(bundle_path)

        # Verify SAFE_MODE
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_MULTI_DEPT_MISSING_CONTRACTS

    def test_missing_contracts_json_health_503(self, tmp_path: Path):
        """Missing contracts.json should result in /health 503."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        finance_dept = departments_path / "finance"
        create_minimal_dept_artifacts(finance_dept)

        create_contract_ledger(bundle_path, [])
        create_manifest(bundle_path, [])

        load_bundle(bundle_path)

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["mode"] == "SAFE_MODE"
        assert data["reason_code"] == BUNDLE_MULTI_DEPT_MISSING_CONTRACTS


class TestMultiDeptMissingArtifact:
    """Test 4: Multi-dept missing required artifact enters SAFE_MODE."""

    def test_missing_rbac_json_safe_mode(self, tmp_path: Path):
        """Multi-dept bundle missing rbac.json in department should enter SAFE_MODE."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        # Create finance department but delete rbac.json
        finance_dept = departments_path / "finance"
        create_minimal_dept_artifacts(finance_dept)
        (finance_dept / "rbac.json").unlink()  # Remove rbac.json

        # Create contracts.json
        contracts_hash = create_contracts_json(bundle_path, ["finance"])

        create_contract_ledger(bundle_path, [])
        create_manifest(bundle_path, [
            {"file": "contracts.json", "sha256": contracts_hash, "required": True},
        ])

        # Load bundle
        result = load_bundle(bundle_path)

        # Verify SAFE_MODE
        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_DEPT_ARTIFACT_MISSING
        assert "finance" in runtime_state.details[0]
        assert "rbac.json" in runtime_state.details[0]

    def test_missing_openapi_yaml_safe_mode(self, tmp_path: Path):
        """Multi-dept bundle missing openapi.yaml should enter SAFE_MODE."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        finance_dept = departments_path / "finance"
        create_minimal_dept_artifacts(finance_dept)
        (finance_dept / "openapi.yaml").unlink()

        contracts_hash = create_contracts_json(bundle_path, ["finance"])
        create_contract_ledger(bundle_path, [])
        create_manifest(bundle_path, [
            {"file": "contracts.json", "sha256": contracts_hash, "required": True},
        ])

        result = load_bundle(bundle_path)

        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_DEPT_ARTIFACT_MISSING
        assert "openapi.yaml" in runtime_state.details[0]


class TestMultiDeptInvalidArtifact:
    """Test 5: Multi-dept with invalid artifact JSON enters SAFE_MODE."""

    def test_invalid_approvals_json_safe_mode(self, tmp_path: Path):
        """Multi-dept bundle with invalid approvals.json should enter SAFE_MODE."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        finance_dept = departments_path / "finance"
        create_minimal_dept_artifacts(finance_dept)

        # Corrupt approvals.json
        approvals_path = finance_dept / "approvals.json"
        with open(approvals_path, "w", encoding="utf-8") as f:
            f.write("{invalid json content")

        contracts_hash = create_contracts_json(bundle_path, ["finance"])
        create_contract_ledger(bundle_path, [])
        create_manifest(bundle_path, [
            {"file": "contracts.json", "sha256": contracts_hash, "required": True},
        ])

        result = load_bundle(bundle_path)

        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_DEPT_ARTIFACT_INVALID
        assert "approvals.json" in runtime_state.details[0]
        assert "finance" in runtime_state.details[0]

    def test_invalid_contracts_json_safe_mode(self, tmp_path: Path):
        """Multi-dept bundle with invalid contracts.json should enter SAFE_MODE."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        finance_dept = departments_path / "finance"
        create_minimal_dept_artifacts(finance_dept)

        # Create invalid contracts.json
        contracts_path = bundle_path / "contracts.json"
        with open(contracts_path, "w", encoding="utf-8") as f:
            f.write("{invalid json")

        create_contract_ledger(bundle_path, [])
        create_manifest(bundle_path, [])

        result = load_bundle(bundle_path)

        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_DEPT_ARTIFACT_INVALID


class TestMultiDeptHashMismatch:
    """Test 6: Multi-dept with hash mismatch enters SAFE_MODE."""

    def test_hash_mismatch_dept_artifact_safe_mode(self, tmp_path: Path):
        """Hash mismatch in department artifact should enter SAFE_MODE."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        finance_dept = departments_path / "finance"
        dept_hashes = create_minimal_dept_artifacts(finance_dept)

        contracts_hash = create_contracts_json(bundle_path, ["finance"])

        # Create manifest with WRONG hash for rbac.json
        wrong_hash = "0" * 64
        manifest_contracts = [
            {"file": "contracts.json", "sha256": contracts_hash, "required": True},
            {
                "file": "departments/finance/rbac.json",
                "sha256": wrong_hash,  # Wrong hash
                "required": True,
            },
        ]
        create_contract_ledger(bundle_path, [])
        create_manifest(bundle_path, manifest_contracts)

        result = load_bundle(bundle_path)

        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_CONTRACT_HASH_MISMATCH
        assert "rbac.json" in runtime_state.details[0]

    def test_hash_mismatch_contracts_json_safe_mode(self, tmp_path: Path):
        """Hash mismatch in contracts.json should enter SAFE_MODE."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        finance_dept = departments_path / "finance"
        create_minimal_dept_artifacts(finance_dept)

        create_contracts_json(bundle_path, ["finance"])

        # Create manifest with WRONG hash for contracts.json
        wrong_hash = "0" * 64
        manifest_contracts = [
            {"file": "contracts.json", "sha256": wrong_hash, "required": True},
        ]
        create_contract_ledger(bundle_path, [])
        create_manifest(bundle_path, manifest_contracts)

        result = load_bundle(bundle_path)

        assert result is None
        assert runtime_state.is_safe_mode()
        assert runtime_state.reason_code == BUNDLE_CONTRACT_HASH_MISMATCH


class TestBundleContextApi:
    """Test BundleContext API."""

    def test_get_bundle_context_single(self, tmp_path: Path):
        """get_bundle_context should return correct context for single-dept."""
        bundle_path = tmp_path / "finance-pilot"
        shutil.copytree(FINANCE_PILOT_PATH, bundle_path)

        load_bundle(bundle_path)

        ctx = get_bundle_context()
        assert ctx is not None
        assert ctx.mode == "single"
        assert ctx.path == bundle_path
        assert ctx.manifest is not None
        assert "name" in ctx.manifest

    def test_get_bundle_context_multi(self, tmp_path: Path):
        """get_bundle_context should return correct context for multi-dept."""
        bundle_path = tmp_path / "multi-bundle"
        bundle_path.mkdir(parents=True)

        departments_path = bundle_path / "departments"
        departments_path.mkdir()

        finance_dept = departments_path / "finance"
        dept_hashes = create_minimal_dept_artifacts(finance_dept)

        contracts_hash = create_contracts_json(bundle_path, ["finance"])
        create_contract_ledger(bundle_path, [])

        manifest_contracts = [
            {"file": "contracts.json", "sha256": contracts_hash, "required": True},
        ]
        for artifact, hash_val in dept_hashes.items():
            manifest_contracts.append({
                "file": f"departments/finance/{artifact}",
                "sha256": hash_val,
                "required": True,
            })
        create_manifest(bundle_path, manifest_contracts)

        load_bundle(bundle_path)

        ctx = get_bundle_context()
        assert ctx is not None
        assert ctx.mode == "multi"
        assert "finance" in ctx.departments
        assert ctx.departments["finance"].rbac is not None
        assert ctx.departments["finance"].approvals is not None
        assert ctx.contracts_catalog is not None
