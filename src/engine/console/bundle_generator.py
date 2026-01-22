"""Bundle generator for onboarding.

Generates institution-specific bundles from templates by:
1. Copying template files to institution bundles directory
2. Updating contract_ledger.json with new timestamps
3. Recalculating manifest hashes
4. Running proof verification
5. Creating CURRENT symlink if proof passes

Etapa 4.2: Onboarding + Templates
"""

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.console.templates_registry import (
    get_template,
    get_template_path,
    get_seed_dsl_path,
    get_repo_root,
)
from engine.core.data_root import get_institution_root
from engine.core.errors import (
    INSTITUTION_NOT_FOUND,
    SEED_DSL_NOT_FOUND,
    SEED_DSL_MISSING_FOR_DEPT,
)
from engine.core.institutions import get_registry as get_institutions_registry
from engine.proof import verify_bundle_offline, ProofResult


# Error codes for bundle generation
TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
BUNDLE_GENERATION_FAILED = "BUNDLE_GENERATION_FAILED"
BUNDLE_COPY_FAILED = "BUNDLE_COPY_FAILED"
BUNDLE_ALREADY_EXISTS = "BUNDLE_ALREADY_EXISTS"


@dataclass
class BundleGenerationResult:
    """Result of bundle generation from template.

    Attributes:
        success: Whether generation succeeded.
        bundle_path: Path to generated bundle (if successful).
        proof_result: Proof verification result.
        error_code: Error code if failed.
        error_message: Human-readable error message.
    """

    success: bool
    bundle_path: Optional[Path] = None
    proof_result: Optional[ProofResult] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        file_path: Path to file.

    Returns:
        Hex-encoded SHA256 hash.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _update_contract_ledger(
    ledger_path: Path,
    bundle_name: str,
    manifest_hash: str,
    institution_id: str,
    manifest_contracts: List[Dict[str, Any]],
    source_idl_sha256: str,
    source_idl_version: str,
    source_idl_by_dept: Optional[Dict[str, str]] = None,
) -> bool:
    """Update contract_ledger.json with new timestamps and metadata.

    Args:
        ledger_path: Path to contract_ledger.json.
        bundle_name: Name of the bundle.
        manifest_hash: SHA256 hash of the manifest.
        institution_id: Institution UUID.
        manifest_contracts: Contracts list from bundle.manifest.json (post-normalization).
        source_idl_sha256: Real SHA256 hash of the source IDL (no placeholder allowed).
        source_idl_version: Version of the IDL DSL (e.g., "idl.v1.2.2").
        source_idl_by_dept: For multi-dept, mapping of dept_id to sha256 of seed.

    Returns:
        True if update succeeded.
    """
    try:
        with open(ledger_path, "r") as f:
            ledger = json.load(f)

        # Update timestamps and metadata
        now = datetime.now(timezone.utc).isoformat()
        ledger["created_at"] = now
        ledger["manifest_hash"] = f"SHA256:{manifest_hash}"

        # Set source_idl_sha256 from real computed hash (no placeholder!)
        ledger["source_idl_sha256"] = source_idl_sha256
        ledger["source_idl_version"] = source_idl_version

        # For multi-dept bundles, include per-dept hashes
        if source_idl_by_dept:
            ledger["source_idl_by_dept"] = source_idl_by_dept

        # Update ledger_id to be unique for this institution
        ledger["ledger_id"] = f"{bundle_name}-{institution_id[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # Ensure contracts[] exists and matches manifest (proof requires 1:1 cross-check).
        # The manifest used for proof intentionally excludes contract_ledger.json to avoid circular hashing.
        if not isinstance(ledger.get("contracts"), list):
            ledger["contracts"] = []

        contracts_out: List[Dict[str, Any]] = []
        for c in manifest_contracts:
            file_name = c.get("file")
            sha = c.get("sha256")
            if not file_name or not sha:
                continue
            contracts_out.append(
                {
                    "contract_name": file_name,
                    "content_hash": sha,
                    "status": "active",
                }
            )

        ledger["contracts"] = contracts_out

        # Add audit trail entry
        if "audit_trail" not in ledger:
            ledger["audit_trail"] = []

        ledger["audit_trail"].append({
            "event": "bundle_generated",
            "timestamp": now,
            "details": {
                "institution_id": institution_id,
                "template_name": bundle_name,
                "generation_method": "onboarding_wizard",
                "source_idl_sha256": source_idl_sha256,
            }
        })

        with open(ledger_path, "w") as f:
            json.dump(ledger, f, indent=2)

        return True
    except Exception:
        return False


def _copy_seed_dsl_to_bundle(
    template_id: str,
    bundle_path: Path,
    departments: List[str],
) -> Tuple[bool, Dict[str, str], Optional[str]]:
    """Copy seed DSL files into the bundle and compute hashes.

    For single-dept: copies to bundle_path/source.idl
    For multi-dept: copies to bundle_path/departments/<dept_id>/source.idl

    Args:
        template_id: Template identifier.
        bundle_path: Path to the target bundle directory.
        departments: List of department IDs.

    Returns:
        Tuple of (success, dept_hashes, error_message).
        dept_hashes maps dept_id -> sha256 of that dept's seed.
    """
    is_multi = len(departments) > 1
    dept_hashes: Dict[str, str] = {}
    repo_root = get_repo_root()
    template = get_template(template_id)

    if not template:
        return False, {}, f"Template not found: {template_id}"

    for dept_id in departments:
        # Get seed DSL path from template registry
        seed_rel_path = template.seed_dsl_paths.get(dept_id)
        if not seed_rel_path:
            return False, {}, f"No seed DSL path declared for department: {dept_id}"

        seed_src = repo_root / seed_rel_path
        if not seed_src.exists():
            return False, {}, f"Seed DSL file not found: {seed_src}"

        # Determine destination path
        if is_multi:
            dest_dir = bundle_path / "departments" / dept_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / "source.idl"
        else:
            dest_path = bundle_path / "source.idl"

        # Copy seed to bundle
        try:
            shutil.copy2(seed_src, dest_path)
        except Exception as e:
            return False, {}, f"Failed to copy seed DSL for {dept_id}: {e}"

        # Compute hash
        dept_hashes[dept_id] = _compute_sha256(dest_path)

    return True, dept_hashes, None


def _compute_aggregated_source_idl_hash(dept_hashes: Dict[str, str]) -> str:
    """Compute aggregated source_idl_sha256 for multi-dept bundles.

    Formula: sha256("<dept_id>:<sha256(seed_bytes)>\n" concatenated, sorted by dept_id)

    Args:
        dept_hashes: Mapping of dept_id to sha256 of that dept's seed.

    Returns:
        Aggregated SHA256 hash.
    """
    if len(dept_hashes) == 1:
        # Single dept: return the hash directly
        return list(dept_hashes.values())[0]

    # Multi-dept: deterministic concatenation
    sorted_depts = sorted(dept_hashes.keys())
    lines = [f"{dept_id}:{dept_hashes[dept_id]}\n" for dept_id in sorted_depts]
    concat_str = "".join(lines)
    return hashlib.sha256(concat_str.encode("utf-8")).hexdigest()


def _add_seed_dsl_to_manifest(
    manifest_path: Path,
    bundle_path: Path,
    departments: List[str],
    dept_hashes: Dict[str, str],
) -> bool:
    """Add seed DSL files to manifest as contracts with required=false.

    Args:
        manifest_path: Path to bundle.manifest.json.
        bundle_path: Path to bundle directory.
        departments: List of department IDs.
        dept_hashes: Mapping of dept_id to sha256 of that dept's seed.

    Returns:
        True if successful.
    """
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        contracts = manifest.get("contracts", [])
        is_multi = len(departments) > 1

        for dept_id in departments:
            if is_multi:
                file_path = f"departments/{dept_id}/source.idl"
            else:
                file_path = "source.idl"

            # Add to contracts with required=false
            contracts.append({
                "file": file_path,
                "sha256": f"SHA256:{dept_hashes[dept_id]}",
                "required": False,
            })

        manifest["contracts"] = contracts

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return True
    except Exception:
        return False


def _update_manifest_hashes(bundle_path: Path) -> Tuple[bool, Optional[str]]:
    """Update bundle.manifest.json with recalculated hashes.

    Removes contract_ledger.json from the manifest to avoid circular
    dependency (manifest hashes ledger, ledger contains manifest_hash).

    Args:
        bundle_path: Path to bundle directory.

    Returns:
        Tuple of (success, manifest_hash).
    """
    manifest_path = bundle_path / "bundle.manifest.json"

    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # Filter out contract_ledger.json to avoid circular dependency
        # The ledger is verified separately by the proof system
        contracts = manifest.get("contracts", [])
        contracts = [c for c in contracts if c.get("file") != "contract_ledger.json"]

        # Recalculate hashes for remaining contracts
        for contract in contracts:
            file_name = contract.get("file")
            if not file_name:
                continue

            file_path = bundle_path / file_name
            if file_path.exists():
                hash_value = _compute_sha256(file_path)
                contract["sha256"] = f"SHA256:{hash_value}"

        manifest["contracts"] = contracts

        # Write updated manifest
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Compute manifest hash (SHA256 of the manifest file bytes)
        manifest_hash = _compute_sha256(manifest_path)
        return True, manifest_hash

    except Exception:
        return False, None


def generate_bundle_from_template(
    institution_id: str,
    template_id: str,
    overwrite: bool = False,
) -> BundleGenerationResult:
    """Generate a bundle for an institution from a template.

    Process:
    1. Validate institution exists
    2. Validate template exists and has seed DSL paths declared
    3. Copy template to institution's bundles directory
    4. Copy seed DSL files into bundle (source.idl or departments/<dept>/source.idl)
    5. Add seed DSL files to manifest as contracts (required=false)
    6. Update manifest hashes
    7. Calculate real source_idl_sha256 (single or aggregated for multi)
    8. Update contract_ledger.json with real hash (no placeholder!)
    9. Run proof verification
    10. Create CURRENT symlink if proof passes

    Args:
        institution_id: Institution UUID.
        template_id: Template identifier.
        overwrite: If True, overwrite existing bundle.

    Returns:
        BundleGenerationResult with success status and details.
    """
    # Validate institution exists
    registry = get_institutions_registry()
    institution, error_code, error_msg = registry.get_by_id(institution_id)
    if not institution:
        return BundleGenerationResult(
            success=False,
            error_code=error_code or INSTITUTION_NOT_FOUND,
            error_message=error_msg or f"Institution not found: {institution_id}",
        )

    # Validate template exists
    template = get_template(template_id)
    if not template:
        return BundleGenerationResult(
            success=False,
            error_code=TEMPLATE_NOT_FOUND,
            error_message=f"Template not found: {template_id}",
        )

    # Validate template has seed DSL paths declared (production: no placeholder)
    if not template.seed_dsl_paths:
        return BundleGenerationResult(
            success=False,
            error_code=SEED_DSL_NOT_FOUND,
            error_message=f"Template {template_id} has no seed_dsl_paths declared",
        )

    # Validate all departments have seed DSL paths
    for dept_id in template.departments:
        if dept_id not in template.seed_dsl_paths:
            return BundleGenerationResult(
                success=False,
                error_code=SEED_DSL_MISSING_FOR_DEPT,
                error_message=f"No seed DSL path declared for department: {dept_id}",
            )

    # Get template path
    template_path = get_template_path(template_id)
    if not template_path or not template_path.exists():
        return BundleGenerationResult(
            success=False,
            error_code=TEMPLATE_NOT_FOUND,
            error_message=f"Template path not found: {template_id}",
        )

    # Create institution bundles directory
    institution_root = get_institution_root(institution_id)
    bundles_root = institution_root / "bundles"
    target_bundle_path = bundles_root / template_id

    # Check if bundle already exists
    if target_bundle_path.exists():
        if not overwrite:
            return BundleGenerationResult(
                success=False,
                error_code=BUNDLE_ALREADY_EXISTS,
                error_message=f"Bundle already exists at {target_bundle_path}. Use overwrite=True to replace.",
            )
        # Remove existing bundle
        shutil.rmtree(target_bundle_path)

    # Create directories
    bundles_root.mkdir(parents=True, exist_ok=True)

    # Copy template to target
    try:
        shutil.copytree(template_path, target_bundle_path)
    except Exception as e:
        return BundleGenerationResult(
            success=False,
            error_code=BUNDLE_COPY_FAILED,
            error_message=f"Failed to copy template: {e}",
        )

    # Copy seed DSL files into bundle and compute hashes
    success, dept_hashes, error_msg = _copy_seed_dsl_to_bundle(
        template_id, target_bundle_path, template.departments
    )
    if not success:
        shutil.rmtree(target_bundle_path, ignore_errors=True)
        return BundleGenerationResult(
            success=False,
            error_code=SEED_DSL_NOT_FOUND,
            error_message=error_msg or "Failed to copy seed DSL files",
        )

    # Compute aggregated source_idl_sha256
    source_idl_sha256 = _compute_aggregated_source_idl_hash(dept_hashes)
    is_multi = len(template.departments) > 1
    source_idl_by_dept = dept_hashes if is_multi else None

    # Update manifest: recalculate contract hashes and remove contract_ledger.json
    # from manifest (to avoid circular dependency with ledger's manifest_hash field)
    success, manifest_hash = _update_manifest_hashes(target_bundle_path)
    if not success:
        shutil.rmtree(target_bundle_path, ignore_errors=True)
        return BundleGenerationResult(
            success=False,
            error_code=BUNDLE_GENERATION_FAILED,
            error_message="Failed to update manifest hashes",
        )

    # Add seed DSL files to manifest as contracts (required=false)
    manifest_path = target_bundle_path / "bundle.manifest.json"
    if not _add_seed_dsl_to_manifest(
        manifest_path, target_bundle_path, template.departments, dept_hashes
    ):
        shutil.rmtree(target_bundle_path, ignore_errors=True)
        return BundleGenerationResult(
            success=False,
            error_code=BUNDLE_GENERATION_FAILED,
            error_message="Failed to add seed DSL to manifest",
        )

    # Recompute manifest hash after adding seed DSL entries
    manifest_hash = _compute_sha256(manifest_path)

    # Load normalized manifest contracts (now including source.idl)
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_obj = json.load(f)
        manifest_contracts = manifest_obj.get("contracts", [])
        if not isinstance(manifest_contracts, list):
            manifest_contracts = []
    except Exception:
        shutil.rmtree(target_bundle_path, ignore_errors=True)
        return BundleGenerationResult(
            success=False,
            error_code=BUNDLE_GENERATION_FAILED,
            error_message="Failed to read updated bundle.manifest.json",
        )

    # Update contract_ledger.json with final manifest_hash, contracts list, and real source_idl_sha256
    ledger_path = target_bundle_path / "contract_ledger.json"
    if ledger_path.exists() and manifest_hash:
        if not _update_contract_ledger(
            ledger_path,
            template_id,
            manifest_hash,
            institution_id,
            manifest_contracts=manifest_contracts,
            source_idl_sha256=source_idl_sha256,
            source_idl_version=template.seed_dsl_version,
            source_idl_by_dept=source_idl_by_dept,
        ):
            shutil.rmtree(target_bundle_path, ignore_errors=True)
            return BundleGenerationResult(
                success=False,
                error_code=BUNDLE_GENERATION_FAILED,
                error_message="Failed to update contract ledger",
            )

    # Run proof verification
    proof_result = verify_bundle_offline(target_bundle_path)

    if proof_result.passed:
        # Create CURRENT symlink
        current_symlink = bundles_root / "CURRENT"
        if current_symlink.is_symlink() or current_symlink.exists():
            current_symlink.unlink()
        current_symlink.symlink_to(template_id)

        return BundleGenerationResult(
            success=True,
            bundle_path=target_bundle_path,
            proof_result=proof_result,
        )
    else:
        # Proof failed - do NOT create CURRENT symlink
        # But keep the bundle for debugging
        return BundleGenerationResult(
            success=False,
            bundle_path=target_bundle_path,
            proof_result=proof_result,
            error_code=proof_result.error_code or "PROOF_FAILED",
            error_message=proof_result.error_message or "Proof verification failed",
        )


def get_institution_bundle_path(institution_id: str) -> Optional[Path]:
    """Get the current bundle path for an institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to current bundle, or None if not found.
    """
    institution_root = get_institution_root(institution_id)
    bundles_root = institution_root / "bundles"
    current_symlink = bundles_root / "CURRENT"

    if current_symlink.is_symlink():
        target = current_symlink.resolve()
        if target.exists():
            return target

    return None
