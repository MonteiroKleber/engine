"""ISE Compiler - IDL to Bundle compilation."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional

from .idl_parser import parse_idl, ParsedIDL
from .manifest import generate_manifest, get_bundle_hash, sha256_str
from .contract_ledger import generate_contract_ledger
from .ircs_adapter import ircs_to_parsed_idl, load_ircs_from_file, get_source_idl_sha256, IRCSAdapterError
from .emit import (
    emit_rbac,
    emit_workflows,
    emit_approvals,
    emit_sod,
    emit_invariants,
    emit_openapi,
    emit_contracts,
    emit_policies_v11,
    emit_policies_json,
    validate_policies_v11,
    ISEPolicyValidationError,
    emit_mandates_json,
    emit_autonomy_json,
    emit_operations_json,
)
from .emit.openapi_emit import emit_openapi_yaml
from .idl_parser import IDLDepartment, IDLParseError
from . import errors


@dataclass
class CompileResult:
    """Result of bundle compilation."""

    success: bool
    bundle_path: Optional[str] = None
    bundle_name: Optional[str] = None
    version: Optional[str] = None
    mode: str = "single"  # "single" or "multi"
    departments: List[str] = field(default_factory=list)
    contracts: List[str] = field(default_factory=list)
    sha256s: Dict[str, str] = field(default_factory=dict)
    bundle_hash: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def compile_bundle(
    idl: str,
    bundle_name: str,
    output_dir: str = "bundles",
    validate_finance_pilot: bool = True,
) -> CompileResult:
    """Compile IDL into executable bundle.

    Args:
        idl: IDL source string (JSON format).
        bundle_name: Name for the bundle.
        output_dir: Directory to write bundle files.
        validate_finance_pilot: If True, validate for finance-pilot MVP requirements.

    Returns:
        CompileResult with bundle details or error info.
    """
    # Parse JSON first to detect format
    try:
        idl_data = json.loads(idl) if isinstance(idl, str) else idl
    except json.JSONDecodeError as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_IDL_INVALID_JSON,
            error_message=f"Invalid JSON in IDL: {e}",
        )

    # Detect IRCS v1 format and use canonical path
    if idl_data.get("ir_version") == "ircs.v1":
        return compile_from_ircs(idl_data, bundle_name, output_dir)

    # Legacy path: Parse IDL
    try:
        parsed = parse_idl(idl_data)
    except IDLParseError as e:
        return CompileResult(
            success=False,
            error_code=e.code,
            error_message=e.message,
        )
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_IDL_PARSE_FAILED,
            error_message=f"Failed to parse IDL: {e}",
        )

    # Branch based on mode
    if parsed.is_multi_dept:
        return _compile_multi_dept(parsed, idl, bundle_name, output_dir)
    else:
        return _compile_single_dept(
            parsed, idl, bundle_name, output_dir, validate_finance_pilot
        )


def _compile_single_dept(
    parsed: ParsedIDL,
    idl: str,
    bundle_name: str,
    output_dir: str,
    validate_finance_pilot: bool,
) -> CompileResult:
    """Compile single-department bundle (original behavior).

    Args:
        parsed: Parsed IDL structure.
        idl: Original IDL source string.
        bundle_name: Name for the bundle.
        output_dir: Directory to write bundle files.
        validate_finance_pilot: If True, validate for finance-pilot MVP requirements.

    Returns:
        CompileResult with bundle details or error info.
    """
    # Validate for finance-pilot MVP if required
    if validate_finance_pilot:
        is_valid, missing = parsed.validate_for_finance_pilot()
        if not is_valid:
            return CompileResult(
                success=False,
                error_code=errors.ISE_IDL_INSUFFICIENT,
                error_message=f"IDL insufficient for finance-pilot MVP. Missing: {', '.join(missing)}",
            )

    # Generate contracts
    try:
        contracts = _emit_all_contracts(parsed)
    except ISEPolicyValidationError as e:
        return CompileResult(
            success=False,
            error_code=e.code,
            error_message=f"Policy validation failed: {e.message}",
        )
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_EMIT_FAILED,
            error_message=f"Failed to emit contracts: {e}",
        )

    # Generate manifest
    try:
        manifest = generate_manifest(
            bundle_name=bundle_name,
            version=parsed.version,
            contracts=contracts,
            system_name=parsed.system_name,
        )
        bundle_hash = get_bundle_hash(manifest)
        manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
        contracts["bundle.manifest.json"] = manifest_json
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_MANIFEST_FAILED,
            error_message=f"Failed to generate manifest: {e}",
        )

    # Generate contract ledger
    try:
        # Extract contract info from manifest for ledger
        contract_hashes = {
            c["file"]: c["sha256"].replace("SHA256:", "")
            for c in manifest["contracts"]
        }
        # Compute manifest_hash as SHA256(manifest_json) per spec 2.3
        manifest_hash = sha256_str(manifest_json)
        ledger_json = generate_contract_ledger(
            bundle_name=bundle_name,
            version=parsed.version,
            contracts=contract_hashes,
            manifest_hash=manifest_hash,
            idl_source=idl,
        )
        ledger_str = json.dumps(ledger_json, indent=2, sort_keys=True)
        contracts["contract_ledger.json"] = ledger_str
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_COMPILE_FAILED,
            error_message=f"Failed to generate contract ledger: {e}",
        )

    # Write bundle to disk
    try:
        bundle_path = _write_bundle(bundle_name, contracts, output_dir)
    except FileExistsError:
        return CompileResult(
            success=False,
            error_code=errors.ISE_BUNDLE_EXISTS,
            error_message=f"Bundle '{bundle_name}' already exists in {output_dir}",
        )
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_BUNDLE_WRITE_FAILED,
            error_message=f"Failed to write bundle: {e}",
        )

    # Build SHA256 map
    sha256s = {filename: sha256_str(content) for filename, content in contracts.items()}

    return CompileResult(
        success=True,
        bundle_path=bundle_path,
        bundle_name=bundle_name,
        version=parsed.version,
        mode="single",
        contracts=sorted(contracts.keys()),
        sha256s=sha256s,
        bundle_hash=bundle_hash,
    )


def _compile_multi_dept(
    parsed: ParsedIDL,
    idl: str,
    bundle_name: str,
    output_dir: str,
) -> CompileResult:
    """Compile multi-department bundle.

    Output structure:
        bundle_name/
            bundle.manifest.json
            contract_ledger.json
            contracts.json           # interdepartmental contracts
            departments/
                <dept_id>/
                    rbac.json
                    workflows.json
                    approvals.json
                    sod.json
                    invariants.json
                    openapi.yaml

    Args:
        parsed: Parsed IDL structure.
        idl: Original IDL source string.
        bundle_name: Name for the bundle.
        output_dir: Directory to write bundle files.

    Returns:
        CompileResult with bundle details or error info.
    """
    all_files: Dict[str, str] = {}
    dept_ids = []

    # Emit contracts for each department
    try:
        for dept in parsed.departments:
            dept_files = _emit_dept_contracts(parsed, dept, ir=ir)
            for filename, content in dept_files.items():
                all_files[f"departments/{dept.dept_id}/{filename}"] = content
            dept_ids.append(dept.dept_id)
    except ISEPolicyValidationError as e:
        return CompileResult(
            success=False,
            error_code=e.code,
            error_message=f"Policy validation failed: {e.message}",
        )
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_EMIT_FAILED,
            error_message=f"Failed to emit department contracts: {e}",
        )

    # Emit interdepartmental contracts at root level
    try:
        contracts_data = emit_contracts(parsed)
        all_files["contracts.json"] = json.dumps(contracts_data, indent=2, sort_keys=True)
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_EMIT_FAILED,
            error_message=f"Failed to emit interdepartmental contracts: {e}",
        )

    # Generate manifest for multi-dept bundle
    try:
        manifest = generate_manifest(
            bundle_name=bundle_name,
            version=parsed.version,
            contracts=all_files,
            system_name=parsed.system_name,
            mode="multi",
            departments=dept_ids,
        )
        bundle_hash = get_bundle_hash(manifest)
        manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
        all_files["bundle.manifest.json"] = manifest_json
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_MANIFEST_FAILED,
            error_message=f"Failed to generate manifest: {e}",
        )

    # Generate contract ledger
    try:
        # Extract contract info from manifest for ledger
        contract_hashes = {
            c["file"]: c["sha256"].replace("SHA256:", "")
            for c in manifest["contracts"]
        }
        # Compute manifest_hash as SHA256(manifest_json) per spec 2.3
        manifest_hash = sha256_str(manifest_json)
        ledger_json = generate_contract_ledger(
            bundle_name=bundle_name,
            version=parsed.version,
            contracts=contract_hashes,
            manifest_hash=manifest_hash,
            idl_source=idl,
        )
        ledger_str = json.dumps(ledger_json, indent=2, sort_keys=True)
        all_files["contract_ledger.json"] = ledger_str
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_COMPILE_FAILED,
            error_message=f"Failed to generate contract ledger: {e}",
        )

    # Write bundle to disk
    try:
        bundle_path = _write_bundle_multi(bundle_name, all_files, output_dir)
    except FileExistsError:
        return CompileResult(
            success=False,
            error_code=errors.ISE_BUNDLE_EXISTS,
            error_message=f"Bundle '{bundle_name}' already exists in {output_dir}",
        )
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_BUNDLE_WRITE_FAILED,
            error_message=f"Failed to write bundle: {e}",
        )

    # Build SHA256 map
    sha256s = {filename: sha256_str(content) for filename, content in all_files.items()}

    return CompileResult(
        success=True,
        bundle_path=bundle_path,
        bundle_name=bundle_name,
        version=parsed.version,
        mode="multi",
        departments=sorted(dept_ids),
        contracts=sorted(all_files.keys()),
        sha256s=sha256s,
        bundle_hash=bundle_hash,
    )


def _emit_dept_contracts(
    parsed: ParsedIDL,
    dept: IDLDepartment,
    ir: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Emit contracts for a specific department.

    Uses department-specific config if provided, otherwise uses global config.
    Per MVP decision (2026-01-17): policies.json, mandates.json, autonomy.json
    are mandatory institutional contracts and are always emitted per department.

    Args:
        parsed: Parsed IDL structure.
        dept: Department definition.

    Returns:
        Dict mapping filename to content string.

    Raises:
        ISEPolicyValidationError: If policy validation fails.
    """
    contracts: Dict[str, str] = {}

    # Create a department-scoped ParsedIDL for emitters
    # If dept has specific config, use it; otherwise use parsed global config
    dept_parsed = _create_dept_parsed(parsed, dept)

    # RBAC contract
    rbac = emit_rbac(dept_parsed)
    contracts["rbac.json"] = json.dumps(rbac, indent=2, sort_keys=True)

    # Workflows contract
    workflows = emit_workflows(dept_parsed)
    contracts["workflows.json"] = json.dumps(workflows, indent=2, sort_keys=True)

    # Approvals contract
    approvals = emit_approvals(dept_parsed)
    contracts["approvals.json"] = json.dumps(approvals, indent=2, sort_keys=True)

    # SoD contract
    sod = emit_sod(dept_parsed)
    contracts["sod.json"] = json.dumps(sod, indent=2, sort_keys=True)

    # Invariants contract
    invariants = emit_invariants(dept_parsed)
    contracts["invariants.json"] = json.dumps(invariants, indent=2, sort_keys=True)

    # OpenAPI spec
    openapi_yaml = emit_openapi_yaml(dept_parsed)
    contracts["openapi.yaml"] = openapi_yaml

    # === MANDATORY INSTITUTIONAL CONTRACTS (MVP decision 2026-01-17) ===

    # Policies contract - ALWAYS emit (use dept policies if defined, else empty)
    dept_policies = parsed.dept_policies.get(dept.dept_id, [])
    if dept_policies:
        # validate_policies_v11 is called inside emit_policies_json and raises on error
        policies_json = emit_policies_json(dept_policies)
    else:
        # Emit empty policies (default-deny behavior in runtime)
        policies_json = json.dumps({
            "policy_schema_version": "1.1",
            "policies": []
        }, indent=2, sort_keys=True)
    contracts["policies.json"] = policies_json

    # Mandates contract - ALWAYS emit (use original parsed to access dept_mandates)
    # For IRCS v1 canonical compilation, pass the IR to allow deterministic bridge defaults.
    mandates_json = emit_mandates_json(parsed, dept_id=dept.dept_id, ir=ir)
    contracts["mandates.json"] = mandates_json

    # Autonomy contract - ALWAYS emit (use original parsed to access dept_autonomy)
    autonomy_json = emit_autonomy_json(parsed, dept_id=dept.dept_id, ir=ir)
    contracts["autonomy.json"] = autonomy_json

    return contracts


def _create_dept_parsed(parsed: ParsedIDL, dept: IDLDepartment) -> ParsedIDL:
    """Create a department-scoped ParsedIDL for emitters.

    If the department has specific configuration (rbac, workflows, etc.),
    that configuration is used. Otherwise, the global configuration is used.

    Args:
        parsed: Original parsed IDL.
        dept: Department definition.

    Returns:
        ParsedIDL scoped to department.
    """
    # For now, use global config - dept-specific override can be enhanced later
    # This allows departments to inherit from global config by default
    return ParsedIDL(
        system_name=parsed.system_name,
        version=parsed.version,
        actors=parsed.actors,
        entities=parsed.entities,
        usecases=parsed.usecases,
        departments=[],  # Don't recurse
        contracts=[],    # Don't include in dept-level
    )


def _emit_all_contracts(
    parsed: ParsedIDL,
    ir: Optional[Dict[str, Any]] = None,
    dept_id: Optional[str] = None,
) -> Dict[str, str]:
    """Emit all contracts from parsed IDL.

    Per MVP decision (2026-01-17): policies.json, mandates.json, autonomy.json
    are mandatory institutional contracts and are always emitted.

    Args:
        parsed: Parsed IDL structure.
        ir: Optional IRCS v1 dict for operations.json emission.
        dept_id: Optional department ID for multi-dept mode.

    Returns:
        Dict mapping filename to content string.

    Raises:
        ISEPolicyValidationError: If policy validation fails.
    """
    contracts: Dict[str, str] = {}

    # RBAC contract
    rbac = emit_rbac(parsed)
    contracts["rbac.json"] = json.dumps(rbac, indent=2, sort_keys=True)

    # Workflows contract
    workflows = emit_workflows(parsed)
    contracts["workflows.json"] = json.dumps(workflows, indent=2, sort_keys=True)

    # Approvals contract
    approvals = emit_approvals(parsed)
    contracts["approvals.json"] = json.dumps(approvals, indent=2, sort_keys=True)

    # SoD contract
    sod = emit_sod(parsed)
    contracts["sod.json"] = json.dumps(sod, indent=2, sort_keys=True)

    # Invariants contract
    invariants = emit_invariants(parsed)
    contracts["invariants.json"] = json.dumps(invariants, indent=2, sort_keys=True)

    # OpenAPI spec
    openapi_yaml = emit_openapi_yaml(parsed)
    contracts["openapi.yaml"] = openapi_yaml

    # === MANDATORY INSTITUTIONAL CONTRACTS (MVP decision 2026-01-17) ===

    # Policies contract - ALWAYS emit (use IDL policies if defined, else empty)
    if parsed.policies:
        # validate_policies_v11 is called inside emit_policies_json and raises on error
        policies_json = emit_policies_json(parsed.policies)
    else:
        # Emit empty policies (default-deny behavior in runtime)
        policies_json = json.dumps({
            "policy_schema_version": "1.1",
            "policies": []
        }, indent=2, sort_keys=True)
    contracts["policies.json"] = policies_json

    # Mandates contract - ALWAYS emit
    mandates_json = emit_mandates_json(parsed, ir=ir)
    contracts["mandates.json"] = mandates_json

    # Autonomy contract - ALWAYS emit
    autonomy_json = emit_autonomy_json(parsed, ir=ir)
    contracts["autonomy.json"] = autonomy_json

    # Operations contract - emit from IRCS if available, otherwise from ParsedIDL
    # This is optional for legacy bundles but emitted when we have the data
    source = ir if ir else parsed
    operations_json = emit_operations_json(source, dept_id)
    contracts["operations.json"] = operations_json

    return contracts


def _write_bundle(bundle_name: str, contracts: Dict[str, str], output_dir: str) -> str:
    """Write bundle files to disk.

    Args:
        bundle_name: Name of the bundle.
        contracts: Dict mapping filename to content.
        output_dir: Base output directory.

    Returns:
        Path to the bundle directory.

    Raises:
        FileExistsError: If bundle directory already exists.
    """
    bundle_dir = Path(output_dir) / bundle_name

    # Create output directory if needed
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Create bundle directory
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Write each contract
    for filename, content in contracts.items():
        file_path = bundle_dir / filename
        file_path.write_text(content, encoding="utf-8")

    return str(bundle_dir)


def _write_bundle_multi(bundle_name: str, files: Dict[str, str], output_dir: str) -> str:
    """Write multi-department bundle files to disk.

    Handles nested paths like departments/<dept>/file.json.

    Args:
        bundle_name: Name of the bundle.
        files: Dict mapping relative path to content.
        output_dir: Base output directory.

    Returns:
        Path to the bundle directory.

    Raises:
        FileExistsError: If bundle directory already exists.
    """
    bundle_dir = Path(output_dir) / bundle_name

    # Create output directory if needed
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Create bundle directory
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Write each file, creating subdirectories as needed
    for filepath, content in files.items():
        file_path = bundle_dir / filepath
        # Create parent directories if needed (e.g., departments/<dept>/)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    return str(bundle_dir)


def compile_bundle_to_memory(
    idl: str,
    bundle_name: str,
    validate_finance_pilot: bool = True,
) -> Dict[str, Any]:
    """Compile IDL into bundle without writing to disk.

    Useful for testing and API responses.

    Args:
        idl: IDL source string (JSON format).
        bundle_name: Name for the bundle.
        validate_finance_pilot: If True, validate for finance-pilot MVP requirements.

    Returns:
        Dict with compilation result including all contract contents.
    """
    # Parse JSON first to detect format
    try:
        idl_data = json.loads(idl) if isinstance(idl, str) else idl
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error_code": errors.ISE_IDL_INVALID_JSON,
            "error_message": f"Invalid JSON in IDL: {e}",
        }

    # Detect IRCS v1 format and use canonical path
    if idl_data.get("ir_version") == "ircs.v1":
        return compile_from_ircs_to_memory(idl_data, bundle_name)

    # Legacy path: Parse IDL
    try:
        parsed = parse_idl(idl_data)
    except Exception as e:
        return {
            "success": False,
            "error_code": errors.ISE_IDL_PARSE_FAILED,
            "error_message": f"Failed to parse IDL: {e}",
        }

    # Validate for finance-pilot MVP if required
    if validate_finance_pilot:
        is_valid, missing = parsed.validate_for_finance_pilot()
        if not is_valid:
            return {
                "success": False,
                "error_code": errors.ISE_IDL_INSUFFICIENT,
                "error_message": f"IDL insufficient for finance-pilot MVP. Missing: {', '.join(missing)}",
            }

    # Generate contracts
    try:
        contracts = _emit_all_contracts(parsed)
    except ISEPolicyValidationError as e:
        return {
            "success": False,
            "error_code": e.code,
            "error_message": f"Policy validation failed: {e.message}",
        }
    except Exception as e:
        return {
            "success": False,
            "error_code": errors.ISE_EMIT_FAILED,
            "error_message": f"Failed to emit contracts: {e}",
        }

    # Generate manifest
    manifest = generate_manifest(
        bundle_name=bundle_name,
        version=parsed.version,
        contracts=contracts,
        system_name=parsed.system_name,
    )
    bundle_hash = get_bundle_hash(manifest)
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
    contracts["bundle.manifest.json"] = manifest_json

    # Generate contract ledger
    # Extract contract info from manifest for ledger
    contract_hashes = {
        c["file"]: c["sha256"].replace("SHA256:", "")
        for c in manifest["contracts"]
    }
    # Compute manifest_hash as SHA256(manifest_json) per spec 2.3
    manifest_hash = sha256_str(manifest_json)
    ledger = generate_contract_ledger(
        bundle_name=bundle_name,
        version=parsed.version,
        contracts=contract_hashes,
        manifest_hash=manifest_hash,
        idl_source=idl,
    )
    ledger_json = json.dumps(ledger, indent=2, sort_keys=True)
    contracts["contract_ledger.json"] = ledger_json

    # Build SHA256 map
    sha256s = {filename: sha256_str(content) for filename, content in contracts.items()}

    return {
        "success": True,
        "bundle_name": bundle_name,
        "version": parsed.version,
        "contracts": contracts,
        "sha256s": sha256s,
        "bundle_hash": bundle_hash,
    }


# =============================================================================
# IRCS v1 Compilation (Canonical Path)
# =============================================================================


def compile_from_ircs(
    ir: Dict[str, Any],
    bundle_name: str,
    output_dir: str = "bundles",
) -> CompileResult:
    """Compile bundle from IRCS v1 canonical JSON.

    This is the canonical compilation path for production:
        DSL v1.2.2 → IRCS v1 → ParsedIDL → Emitters → Bundle

    Args:
        ir: IRCS v1 dict (from parse_dsl or loaded from ir.json)
        bundle_name: Name for the bundle
        output_dir: Directory to write bundle files

    Returns:
        CompileResult with bundle details or error info
    """
    # Convert IRCS v1 → ParsedIDL
    try:
        parsed = ircs_to_parsed_idl(ir)
    except IRCSAdapterError as e:
        return CompileResult(
            success=False,
            error_code=e.code,
            error_message=e.message,
        )
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_IDL_PARSE_FAILED,
            error_message=f"Failed to convert IRCS v1: {e}",
        )

    # Get source_idl_sha256 from IR for ledger
    source_idl_sha256 = get_source_idl_sha256(ir)
    if not source_idl_sha256:
        return CompileResult(
            success=False,
            error_code=errors.ISE_SOURCE_IDL_SHA256_MISSING,
            error_message="IRCS v1 missing required field 'source_idl_sha256'",
        )

    # Generate contracts using existing emitters
    # Pass ir to emit operations.json from IRCS data
    try:
        contracts = _emit_all_contracts(parsed, ir=ir)
    except ISEPolicyValidationError as e:
        return CompileResult(
            success=False,
            error_code=e.code,
            error_message=f"Policy validation failed: {e.message}",
        )
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_EMIT_FAILED,
            error_message=f"Failed to emit contracts: {e}",
        )

    # Generate manifest
    try:
        manifest = generate_manifest(
            bundle_name=bundle_name,
            version=parsed.version,
            contracts=contracts,
            system_name=parsed.system_name,
        )
        bundle_hash = get_bundle_hash(manifest)
        manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
        contracts["bundle.manifest.json"] = manifest_json
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_MANIFEST_FAILED,
            error_message=f"Failed to generate manifest: {e}",
        )

    # Generate contract ledger with source_idl_sha256 preserved
    try:
        contract_hashes = {
            c["file"]: c["sha256"].replace("SHA256:", "")
            for c in manifest["contracts"]
        }

        # Use IRCS v1 JSON as source for ledger hash (deterministic)
        ir_json_str = json.dumps(ir, indent=2, sort_keys=True, ensure_ascii=False)

        # Compute manifest_hash as SHA256(manifest_json) per spec 2.3
        manifest_hash = sha256_str(manifest_json)

        ledger_json = generate_contract_ledger(
            bundle_name=bundle_name,
            version=parsed.version,
            contracts=contract_hashes,
            manifest_hash=manifest_hash,
            idl_source=ir_json_str,
        )

        # Add source_idl_sha256 to ledger for audit trail
        if source_idl_sha256:
            ledger_json["source_idl_sha256"] = source_idl_sha256

        ledger_str = json.dumps(ledger_json, indent=2, sort_keys=True)
        contracts["contract_ledger.json"] = ledger_str
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_COMPILE_FAILED,
            error_message=f"Failed to generate contract ledger: {e}",
        )

    # Write bundle to disk
    try:
        bundle_path = _write_bundle(bundle_name, contracts, output_dir)
    except FileExistsError:
        return CompileResult(
            success=False,
            error_code=errors.ISE_BUNDLE_EXISTS,
            error_message=f"Bundle '{bundle_name}' already exists in {output_dir}",
        )
    except Exception as e:
        return CompileResult(
            success=False,
            error_code=errors.ISE_BUNDLE_WRITE_FAILED,
            error_message=f"Failed to write bundle: {e}",
        )

    # Build SHA256 map
    sha256s = {filename: sha256_str(content) for filename, content in contracts.items()}

    return CompileResult(
        success=True,
        bundle_path=bundle_path,
        bundle_name=bundle_name,
        version=parsed.version,
        mode="single",
        contracts=sorted(contracts.keys()),
        sha256s=sha256s,
        bundle_hash=bundle_hash,
    )


def compile_from_ircs_to_memory(
    ir: Dict[str, Any],
    bundle_name: str,
) -> Dict[str, Any]:
    """Compile bundle from IRCS v1 to memory (no disk write).

    Args:
        ir: IRCS v1 dict (from parse_dsl or loaded from ir.json)
        bundle_name: Name for the bundle

    Returns:
        Dict with compilation result including all contract contents.
    """
    # Convert IRCS v1 → ParsedIDL
    try:
        parsed = ircs_to_parsed_idl(ir)
    except IRCSAdapterError as e:
        return {
            "success": False,
            "error_code": e.code,
            "error_message": e.message,
        }
    except Exception as e:
        return {
            "success": False,
            "error_code": errors.ISE_IDL_PARSE_FAILED,
            "error_message": f"Failed to convert IRCS v1: {e}",
        }

    # Get source_idl_sha256 from IR for ledger
    source_idl_sha256 = get_source_idl_sha256(ir)
    if not source_idl_sha256:
        return {
            "success": False,
            "error_code": errors.ISE_SOURCE_IDL_SHA256_MISSING,
            "error_message": "IRCS v1 missing required field 'source_idl_sha256'",
        }

    # Generate contracts using existing emitters
    try:
        contracts = _emit_all_contracts(parsed, ir=ir)
    except ISEPolicyValidationError as e:
        return {
            "success": False,
            "error_code": e.code,
            "error_message": f"Policy validation failed: {e.message}",
        }
    except Exception as e:
        return {
            "success": False,
            "error_code": errors.ISE_EMIT_FAILED,
            "error_message": f"Failed to emit contracts: {e}",
        }

    # Generate manifest
    try:
        manifest = generate_manifest(
            bundle_name=bundle_name,
            version=parsed.version,
            contracts=contracts,
            system_name=parsed.system_name,
        )
        bundle_hash = get_bundle_hash(manifest)
        manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
        contracts["bundle.manifest.json"] = manifest_json
    except Exception as e:
        return {
            "success": False,
            "error_code": errors.ISE_MANIFEST_FAILED,
            "error_message": f"Failed to generate manifest: {e}",
        }

    # Generate contract ledger
    try:
        contract_hashes = {
            c["file"]: c["sha256"].replace("SHA256:", "")
            for c in manifest["contracts"]
        }
        ir_json_str = json.dumps(ir, indent=2, sort_keys=True, ensure_ascii=False)
        manifest_hash = sha256_str(manifest_json)
        ledger_json = generate_contract_ledger(
            bundle_name=bundle_name,
            version=parsed.version,
            contracts=contract_hashes,
            manifest_hash=manifest_hash,
            idl_source=ir_json_str,
        )
        if source_idl_sha256:
            ledger_json["source_idl_sha256"] = source_idl_sha256
        ledger_str = json.dumps(ledger_json, indent=2, sort_keys=True)
        contracts["contract_ledger.json"] = ledger_str
    except Exception as e:
        return {
            "success": False,
            "error_code": errors.ISE_COMPILE_FAILED,
            "error_message": f"Failed to generate contract ledger: {e}",
        }

    # Build SHA256 map
    sha256s = {filename: sha256_str(content) for filename, content in contracts.items()}

    return {
        "success": True,
        "bundle_name": bundle_name,
        "version": parsed.version,
        "contracts": contracts,
        "sha256s": sha256s,
        "bundle_hash": bundle_hash,
    }


def compile_from_ircs_file(
    ir_path: str,
    bundle_name: str,
    output_dir: str = "bundles",
) -> CompileResult:
    """Compile bundle from IRCS v1 JSON file.

    Convenience function that loads IRCS v1 from file and compiles.

    Args:
        ir_path: Path to ir.json file
        bundle_name: Name for the bundle
        output_dir: Directory to write bundle files

    Returns:
        CompileResult with bundle details or error info
    """
    try:
        ir = load_ircs_from_file(ir_path)
    except IRCSAdapterError as e:
        return CompileResult(
            success=False,
            error_code=e.code,
            error_message=e.message,
        )

    return compile_from_ircs(ir, bundle_name, output_dir)
