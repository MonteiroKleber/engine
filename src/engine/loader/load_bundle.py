"""Bundle loader - loads and validates bundle manifest and contracts."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from engine.core.runtime_state import runtime_state
from engine.core.errors import (
    BUNDLE_MANIFEST_MISSING,
    BUNDLE_MANIFEST_INVALID_JSON,
    BUNDLE_CONTRACT_MISSING,
    BUNDLE_CONTRACT_HASH_MISMATCH,
    BUNDLE_CONTRACT_INVALID_JSON,
    BUNDLE_UNKNOWN_ERROR,
    BUNDLE_MULTI_DEPT_MISSING_CONTRACTS,
    BUNDLE_DEPT_ARTIFACT_MISSING,
    BUNDLE_DEPT_ARTIFACT_INVALID,
    MANDATE_INVALID,
    AUTONOMY_INVALID,
)
from engine.core.rbac import RBACPolicy, set_rbac_policy
from engine.core.ledger import init_ledger, get_ledger
from engine.core.approvals import ApprovalsPolicy, set_approvals_policy
from engine.core.sod import SodPolicy, set_sod_policy
from engine.core.invariants import InvariantsPolicy, set_invariants_policy
from engine.core.state_store import init_state_store
from engine.core.policy import (
    set_policies,
    clear_all_policies,
    load_policies_from_file,
)
from engine.core.mandates import (
    set_mandates,
    clear_all_mandates,
    load_mandates_from_file,
    MandateSchemaError,
)
from engine.core.autonomy import (
    set_autonomy_for_dept,
    reset_all_autonomy,
    load_autonomy_from_file,
    AutonomySchemaError,
)
from .safe_mode import enter_safe_mode
from .verify_hashes import verify_contract_hash, compute_sha256


DEFAULT_BUNDLE_PATH = "bundles/finance-pilot"
DEFAULT_LEDGER_PATH = "var/audit_ledger.jsonl"

# Required artifacts per department in multi-mode
DEPT_REQUIRED_ARTIFACTS = [
    "rbac.json",
    "approvals.json",
    "workflows.json",
    "sod.json",
    "invariants.json",
    "openapi.yaml",
]


@dataclass
class DeptContracts:
    """Contracts for a single department."""

    name: str
    path: Path
    rbac: Optional[Dict[str, Any]] = None
    approvals: Optional[Dict[str, Any]] = None
    workflows: Optional[Dict[str, Any]] = None
    sod: Optional[Dict[str, Any]] = None
    invariants: Optional[Dict[str, Any]] = None
    openapi: Optional[str] = None


@dataclass
class BundleContext:
    """Context representing a loaded bundle."""

    mode: str  # "single" or "multi"
    path: Path
    manifest: Dict[str, Any]
    departments: Dict[str, DeptContracts] = field(default_factory=dict)
    contracts_catalog: Optional[Dict[str, Any]] = None


# Global bundle context
_bundle_context: Optional[BundleContext] = None


def get_bundle_context() -> Optional[BundleContext]:
    """Get the current bundle context."""
    return _bundle_context


def _set_bundle_context(ctx: Optional[BundleContext]) -> None:
    """Set the bundle context (internal use)."""
    global _bundle_context
    _bundle_context = ctx


def get_bundle_path() -> Path:
    """Get the bundle path from ENV or default.

    Returns:
        Path to the bundle directory.
    """
    env_path = os.environ.get("ENGINE_BUNDLE_PATH")
    if env_path:
        return Path(env_path)
    return Path(DEFAULT_BUNDLE_PATH)


def get_ledger_path() -> Path:
    """Get the ledger path from ENV or default.

    Returns:
        Path to the ledger file.
    """
    env_path = os.environ.get("ENGINE_LEDGER_PATH")
    if env_path:
        return Path(env_path)
    return Path(DEFAULT_LEDGER_PATH)


def _is_multi_dept_bundle(bundle_path: Path) -> bool:
    """Check if bundle is multi-department mode.

    Args:
        bundle_path: Path to the bundle directory.

    Returns:
        True if bundle has departments/ directory.
    """
    return (bundle_path / "departments").is_dir()


def _load_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Load and parse a JSON file.

    Args:
        file_path: Path to the JSON file.

    Returns:
        Parsed JSON content, or None if file doesn't exist.

    Raises:
        json.JSONDecodeError: If JSON is invalid.
    """
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_yaml_file(file_path: Path) -> Optional[str]:
    """Load a YAML file as string.

    Args:
        file_path: Path to the YAML file.

    Returns:
        YAML content as string, or None if file doesn't exist.

    Raises:
        yaml.YAMLError: If YAML is invalid.
    """
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        # Validate YAML syntax
        yaml.safe_load(content)
        return content


def _validate_dept_artifacts(
    bundle_path: Path, dept_name: str, dept_path: Path
) -> Optional[tuple[str, str]]:
    """Validate all required artifacts exist and are valid for a department.

    Args:
        bundle_path: Root bundle path.
        dept_name: Department name.
        dept_path: Path to department directory.

    Returns:
        None if valid, or tuple of (error_code, error_message) if invalid.
    """
    for artifact in DEPT_REQUIRED_ARTIFACTS:
        artifact_path = dept_path / artifact

        # Check existence
        if not artifact_path.exists():
            return (
                BUNDLE_DEPT_ARTIFACT_MISSING,
                f"Missing artifact in department '{dept_name}': {artifact}",
            )

        # Validate JSON/YAML syntax
        try:
            if artifact.endswith(".json"):
                with open(artifact_path, "r", encoding="utf-8") as f:
                    json.load(f)
            elif artifact.endswith(".yaml") or artifact.endswith(".yml"):
                with open(artifact_path, "r", encoding="utf-8") as f:
                    yaml.safe_load(f.read())
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            return (
                BUNDLE_DEPT_ARTIFACT_INVALID,
                f"Invalid {artifact} in department '{dept_name}': {e}",
            )

    return None


def _load_multi_dept_bundle(
    bundle_path: Path, manifest: Dict[str, Any]
) -> Optional[BundleContext]:
    """Load a multi-department bundle.

    Args:
        bundle_path: Path to the bundle directory.
        manifest: Parsed bundle manifest.

    Returns:
        BundleContext if successful, None if safe mode was entered.
    """
    departments_path = bundle_path / "departments"
    contracts_json_path = bundle_path / "contracts.json"

    # 1. Validate contracts.json exists
    if not contracts_json_path.exists():
        enter_safe_mode(
            BUNDLE_MULTI_DEPT_MISSING_CONTRACTS,
            [f"Multi-department bundle missing contracts.json: {contracts_json_path}"],
        )
        return None

    # 2. Parse contracts.json
    try:
        with open(contracts_json_path, "r", encoding="utf-8") as f:
            contracts_catalog = json.load(f)
    except json.JSONDecodeError as e:
        enter_safe_mode(
            BUNDLE_DEPT_ARTIFACT_INVALID,
            [f"Invalid JSON in contracts.json: {e}"],
        )
        return None

    # 3. Discover departments (subdirs in departments/)
    dept_dirs = [d for d in departments_path.iterdir() if d.is_dir()]
    if not dept_dirs:
        # No departments found - this is an error for multi mode
        enter_safe_mode(
            BUNDLE_DEPT_ARTIFACT_MISSING,
            ["Multi-department bundle has no departments in departments/"],
        )
        return None

    # 4. Validate and load each department
    departments: Dict[str, DeptContracts] = {}
    for dept_dir in sorted(dept_dirs):  # Sort for determinism
        dept_name = dept_dir.name

        # Validate all required artifacts
        validation_error = _validate_dept_artifacts(bundle_path, dept_name, dept_dir)
        if validation_error:
            error_code, error_msg = validation_error
            enter_safe_mode(error_code, [error_msg])
            return None

        # Load department contracts
        try:
            dept_contracts = DeptContracts(
                name=dept_name,
                path=dept_dir,
                rbac=_load_json_file(dept_dir / "rbac.json"),
                approvals=_load_json_file(dept_dir / "approvals.json"),
                workflows=_load_json_file(dept_dir / "workflows.json"),
                sod=_load_json_file(dept_dir / "sod.json"),
                invariants=_load_json_file(dept_dir / "invariants.json"),
                openapi=_load_yaml_file(dept_dir / "openapi.yaml"),
            )
            departments[dept_name] = dept_contracts
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            enter_safe_mode(
                BUNDLE_DEPT_ARTIFACT_INVALID,
                [f"Failed to load artifacts for department '{dept_name}': {e}"],
            )
            return None

    # 5. Verify hashes from manifest for multi-dept files
    contracts = manifest.get("contracts", [])
    for contract in contracts:
        contract_file = contract.get("file")
        contract_hash = contract.get("sha256")
        required = contract.get("required", True)

        if not contract_file:
            continue

        contract_path = bundle_path / contract_file

        # Check if required contract exists
        if not contract_path.exists():
            if required:
                enter_safe_mode(
                    BUNDLE_CONTRACT_MISSING,
                    [f"Required contract missing: {contract_file}"],
                )
                return None
            continue

        # Verify hash if provided
        if contract_hash:
            if not verify_contract_hash(contract_path, contract_hash):
                enter_safe_mode(
                    BUNDLE_CONTRACT_HASH_MISMATCH,
                    [f"Hash mismatch for: {contract_file}"],
                )
                return None

    # Create bundle context
    return BundleContext(
        mode="multi",
        path=bundle_path,
        manifest=manifest,
        departments=departments,
        contracts_catalog=contracts_catalog,
    )


def _load_single_dept_bundle(
    bundle_path: Path, manifest: Dict[str, Any]
) -> Optional[BundleContext]:
    """Load a single-department (traditional) bundle.

    Args:
        bundle_path: Path to the bundle directory.
        manifest: Parsed bundle manifest.

    Returns:
        BundleContext if successful, None if safe mode was entered.
    """
    # Validate contracts from manifest
    contracts = manifest.get("contracts", [])
    for contract in contracts:
        contract_file = contract.get("file")
        contract_hash = contract.get("sha256")
        required = contract.get("required", True)

        if not contract_file:
            continue

        contract_path = bundle_path / contract_file

        # Check if required contract exists
        if not contract_path.exists():
            if required:
                enter_safe_mode(
                    BUNDLE_CONTRACT_MISSING,
                    [f"Required contract missing: {contract_file}"],
                )
                return None
            continue

        # Verify hash if provided
        if contract_hash:
            if not verify_contract_hash(contract_path, contract_hash):
                enter_safe_mode(
                    BUNDLE_CONTRACT_HASH_MISMATCH,
                    [f"Hash mismatch for: {contract_file}"],
                )
                return None

        # Validate JSON files are parseable
        if contract_file.endswith(".json"):
            try:
                with open(contract_path, "r", encoding="utf-8") as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                enter_safe_mode(
                    BUNDLE_CONTRACT_INVALID_JSON,
                    [f"Invalid JSON in contract {contract_file}: {e}"],
                )
                return None

    return BundleContext(
        mode="single",
        path=bundle_path,
        manifest=manifest,
    )


def _load_policies_single_mode(bundle_path: Path) -> None:
    """Load policies for single-department mode (from root).

    Args:
        bundle_path: Path to the bundle directory.
    """
    # Load RBAC policy from rbac.json
    rbac_path = bundle_path / "rbac.json"
    if rbac_path.exists():
        try:
            with open(rbac_path, "r", encoding="utf-8") as f:
                rbac_data = json.load(f)
            policy = RBACPolicy(rbac_data)
            set_rbac_policy(policy)
        except Exception:
            set_rbac_policy(None)
    else:
        set_rbac_policy(None)

    # Load approvals policy from approvals.json
    approvals_path = bundle_path / "approvals.json"
    if approvals_path.exists():
        try:
            with open(approvals_path, "r", encoding="utf-8") as f:
                approvals_data = json.load(f)
            approvals_policy = ApprovalsPolicy(approvals_data)
            set_approvals_policy(approvals_policy)
        except Exception:
            set_approvals_policy(None)
    else:
        set_approvals_policy(None)

    # Load SoD policy from sod.json
    sod_path = bundle_path / "sod.json"
    if sod_path.exists():
        try:
            with open(sod_path, "r", encoding="utf-8") as f:
                sod_data = json.load(f)
            sod_policy = SodPolicy(sod_data)
            set_sod_policy(sod_policy)
        except Exception:
            set_sod_policy(None)
    else:
        set_sod_policy(None)

    # Load invariants policy from invariants.json
    invariants_path = bundle_path / "invariants.json"
    if invariants_path.exists():
        try:
            with open(invariants_path, "r", encoding="utf-8") as f:
                invariants_data = json.load(f)
            invariants_policy = InvariantsPolicy(invariants_data)
            set_invariants_policy(invariants_policy)
        except Exception:
            set_invariants_policy(None)
    else:
        set_invariants_policy(None)

    # Load policies from policies.json (optional)
    # If invalid JSON, enter SAFE_MODE per spec
    policies_path = bundle_path / "policies.json"
    if policies_path.exists():
        policy_def = load_policies_from_file(policies_path)
        if policy_def is None:
            # Invalid JSON - enter safe mode
            enter_safe_mode(
                "POLICY_INVALID",
                [f"Invalid JSON in policies.json: {policies_path}"],
            )
        else:
            set_policies(None, policy_def)  # None = single mode key
    else:
        set_policies(None, None)  # No policies = allow all


def _load_policies_multi_mode(bundle_path: Path, bundle_ctx: BundleContext) -> None:
    """Load policies for multi-department mode (per department).

    For multi-mode:
    - Each dept may have departments/<dept_id>/policies.json
    - If a dept doesn't have policies.json, assume empty (allow all)

    Args:
        bundle_path: Path to the bundle directory.
        bundle_ctx: The loaded bundle context with departments.
    """
    for dept_id, dept_contracts in bundle_ctx.departments.items():
        policies_path = dept_contracts.path / "policies.json"
        if policies_path.exists():
            policy_def = load_policies_from_file(policies_path)
            if policy_def is None:
                # Invalid JSON - enter safe mode
                enter_safe_mode(
                    "POLICY_INVALID",
                    [f"Invalid JSON in policies.json for department '{dept_id}': {policies_path}"],
                )
                return
            set_policies(dept_id, policy_def)
        else:
            # No policies.json for this dept - allow all
            set_policies(dept_id, None)


def _load_mandates_single_mode(bundle_path: Path) -> bool:
    """Load mandates for single-department mode (from root).

    Args:
        bundle_path: Path to the bundle directory.

    Returns:
        True if successful (or no mandates file), False if SAFE_MODE entered.
    """
    mandates_path = bundle_path / "mandates.json"
    if mandates_path.exists():
        try:
            mandate_def = load_mandates_from_file(mandates_path)
            set_mandates(None, mandate_def)  # None = single mode key
        except MandateSchemaError as e:
            # Invalid JSON or schema - enter safe mode
            enter_safe_mode(
                MANDATE_INVALID,
                [f"Invalid mandates.json: {e.message}"],
            )
            return False
    else:
        set_mandates(None, None)  # No mandates = allow all (mandates are optional)
    return True


def _load_mandates_multi_mode(bundle_path: Path, bundle_ctx: BundleContext) -> bool:
    """Load mandates for multi-department mode (per department).

    For multi-mode:
    - Each dept may have departments/<dept_id>/mandates.json
    - If a dept doesn't have mandates.json, assume empty (allow all)

    Args:
        bundle_path: Path to the bundle directory.
        bundle_ctx: The loaded bundle context with departments.

    Returns:
        True if successful, False if SAFE_MODE entered.
    """
    for dept_id, dept_contracts in bundle_ctx.departments.items():
        mandates_path = dept_contracts.path / "mandates.json"
        if mandates_path.exists():
            try:
                mandate_def = load_mandates_from_file(mandates_path)
                set_mandates(dept_id, mandate_def)
            except MandateSchemaError as e:
                # Invalid JSON or schema - enter safe mode
                enter_safe_mode(
                    MANDATE_INVALID,
                    [f"Invalid mandates.json for department '{dept_id}': {e.message}"],
                )
                return False
        else:
            # No mandates.json for this dept - allow all
            set_mandates(dept_id, None)
    return True


def _load_autonomy_single_mode(bundle_path: Path) -> bool:
    """Load autonomy for single-department mode (from root).

    Args:
        bundle_path: Path to the bundle directory.

    Returns:
        True if successful (or no autonomy file), False if SAFE_MODE entered.
    """
    autonomy_path = bundle_path / "autonomy.json"
    if autonomy_path.exists():
        try:
            autonomy_def = load_autonomy_from_file(autonomy_path)
            set_autonomy_for_dept(None, autonomy_def)  # None = single mode key
        except AutonomySchemaError as e:
            # Invalid JSON or schema - enter safe mode
            enter_safe_mode(
                AUTONOMY_INVALID,
                [f"Invalid autonomy.json: {e.message}"],
            )
            return False
    else:
        set_autonomy_for_dept(None, None)  # No autonomy = allow all (autonomy is optional)
    return True


def _load_autonomy_multi_mode(bundle_path: Path, bundle_ctx: BundleContext) -> bool:
    """Load autonomy for multi-department mode (per department).

    For multi-mode:
    - Each dept may have departments/<dept_id>/autonomy.json
    - If a dept doesn't have autonomy.json, assume allow-all defaults

    Args:
        bundle_path: Path to the bundle directory.
        bundle_ctx: The loaded bundle context with departments.

    Returns:
        True if successful, False if SAFE_MODE entered.
    """
    for dept_id, dept_contracts in bundle_ctx.departments.items():
        autonomy_path = dept_contracts.path / "autonomy.json"
        if autonomy_path.exists():
            try:
                autonomy_def = load_autonomy_from_file(autonomy_path)
                set_autonomy_for_dept(dept_id, autonomy_def)
            except AutonomySchemaError as e:
                # Invalid JSON or schema - enter safe mode
                enter_safe_mode(
                    AUTONOMY_INVALID,
                    [f"Invalid autonomy.json for department '{dept_id}': {e.message}"],
                )
                return False
        else:
            # No autonomy.json for this dept - allow all
            set_autonomy_for_dept(dept_id, None)
    return True


def load_bundle(bundle_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load and validate a bundle.

    Supports both single-department (traditional) and multi-department bundles.
    Multi-department bundles are detected by presence of departments/ directory.

    Args:
        bundle_path: Optional path to the bundle. If None, uses get_bundle_path().

    Returns:
        The loaded manifest if successful, None if safe mode was entered.
    """
    if bundle_path is None:
        bundle_path = get_bundle_path()

    manifest_path = bundle_path / "bundle.manifest.json"

    # 1. Check if manifest exists
    if not manifest_path.exists():
        enter_safe_mode(
            BUNDLE_MANIFEST_MISSING,
            [f"Manifest not found: {manifest_path}"],
        )
        return None

    # 2. Try to parse manifest JSON
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        enter_safe_mode(
            BUNDLE_MANIFEST_INVALID_JSON,
            [f"Invalid JSON in manifest: {e}"],
        )
        return None
    except Exception as e:
        enter_safe_mode(
            BUNDLE_UNKNOWN_ERROR,
            [f"Error reading manifest: {e}"],
        )
        return None

    # 3. Detect bundle mode and load accordingly
    if _is_multi_dept_bundle(bundle_path):
        bundle_ctx = _load_multi_dept_bundle(bundle_path, manifest)
    else:
        bundle_ctx = _load_single_dept_bundle(bundle_path, manifest)

    if bundle_ctx is None:
        # Safe mode was entered during loading
        return None

    # Store bundle context
    _set_bundle_context(bundle_ctx)

    # 4. Load policies (single mode loads from root, multi mode loads per dept)
    clear_all_policies()  # Clear any previously loaded policies
    if bundle_ctx.mode == "single":
        _load_policies_single_mode(bundle_path)
    else:
        # For multi-mode, we currently set policies to None
        # Future: could merge policies from departments or use a primary dept
        set_rbac_policy(None)
        set_approvals_policy(None)
        set_sod_policy(None)
        set_invariants_policy(None)

        # Load policies per department (if policies.json exists)
        _load_policies_multi_mode(bundle_path, bundle_ctx)

    # 5. Load mandates (single mode loads from root, multi mode loads per dept)
    clear_all_mandates()  # Clear any previously loaded mandates
    if bundle_ctx.mode == "single":
        if not _load_mandates_single_mode(bundle_path):
            return None  # SAFE_MODE entered
    else:
        if not _load_mandates_multi_mode(bundle_path, bundle_ctx):
            return None  # SAFE_MODE entered

    # 6. Load autonomy (single mode loads from root, multi mode loads per dept)
    reset_all_autonomy()  # Clear any previously loaded autonomy
    if bundle_ctx.mode == "single":
        if not _load_autonomy_single_mode(bundle_path):
            return None  # SAFE_MODE entered
    else:
        if not _load_autonomy_multi_mode(bundle_path, bundle_ctx):
            return None  # SAFE_MODE entered

    # 7. Initialize state store
    init_state_store()

    # 8. Initialize ledger and set bundle hashes
    ledger = init_ledger()

    # Compute bundle hashes for ledger events
    bundle_manifest_sha256 = compute_sha256(manifest_path)
    contract_ledger_path = bundle_path / "contract_ledger.json"
    contract_ledger_sha256 = ""
    if contract_ledger_path.exists():
        contract_ledger_sha256 = compute_sha256(contract_ledger_path)

    ledger.set_bundle_hashes(bundle_manifest_sha256, contract_ledger_sha256)

    # All validations passed - set ACTIVE mode (unless already in SAFE_MODE from ledger verification)
    if not runtime_state.is_safe_mode():
        runtime_state.set_active()
    return manifest
