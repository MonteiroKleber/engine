"""ISE Compiler API Router."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from engine.ise import (
    compile_bundle_to_memory,
    errors,
)
from engine.ise.release import (
    compile_release,
    verify_admin_token,
    ReleaseResult,
)


router = APIRouter(prefix="/ise", tags=["ise"])


# Request/Response Models

class CompileBundleRequest(BaseModel):
    """Request for bundle compilation."""
    idl: str = Field(..., min_length=1, description="IDL JSON string to compile")
    bundle_name: str = Field(..., min_length=1, max_length=64, description="Name for the bundle")
    validate_finance_pilot: bool = Field(
        default=True,
        description="Validate for finance-pilot MVP requirements (expense entity required)",
    )


class CompileBundleResponse(BaseModel):
    """Response from bundle compilation."""
    success: bool
    bundle_name: str
    version: str
    bundle_hash: str
    contracts: List[str]
    sha256s: Dict[str, str]


class CompileBundleErrorResponse(BaseModel):
    """Error response from bundle compilation."""
    success: bool = False
    error_code: str
    error_message: str


class BundleContentsResponse(BaseModel):
    """Response with full bundle contents."""
    success: bool
    bundle_name: str
    version: str
    bundle_hash: str
    contracts: Dict[str, str]
    sha256s: Dict[str, str]


def _error_response(status_code: int, code: str, message: str) -> HTTPException:
    """Create standard error response."""
    return HTTPException(
        status_code=status_code,
        detail={
            "success": False,
            "error_code": code,
            "error_message": message,
        },
    )


@router.post("/compile/bundle", response_model=CompileBundleResponse)
async def compile_bundle_endpoint(request: CompileBundleRequest) -> CompileBundleResponse:
    """Compile IDL into executable bundle.

    Takes an IDL JSON string and bundle name, generates all contract files:
    - bundle.manifest.json: Bundle metadata with SHA256 hashes
    - contract_ledger.json: Audit trail for contracts
    - rbac.json: Role-based access control rules
    - workflows.json: Workflow definitions
    - approvals.json: Approval rules (if applicable)
    - sod.json: Segregation of duties rules (if applicable)
    - invariants.json: Data validation constraints
    - openapi.yaml: API specification

    Returns bundle metadata and SHA256 hashes of all files.
    """
    result = compile_bundle_to_memory(
        idl=request.idl,
        bundle_name=request.bundle_name,
        validate_finance_pilot=request.validate_finance_pilot,
    )

    if not result["success"]:
        error_code = result.get("error_code", errors.ISE_COMPILE_FAILED)
        error_message = result.get("error_message", "Unknown error")

        # Map error codes to HTTP status codes
        status_map = {
            errors.ISE_IDL_INVALID_JSON: 400,
            errors.ISE_IDL_PARSE_FAILED: 400,
            errors.ISE_IDL_MISSING_FIELD: 400,
            errors.ISE_IDL_INSUFFICIENT: 409,
            errors.ISE_APPROVAL_UNMAPPED: 422,
            errors.ISE_SOD_UNMAPPED: 422,
            errors.ISE_ENTITY_MISSING: 422,
            errors.ISE_EMIT_FAILED: 500,
            errors.ISE_MANIFEST_FAILED: 500,
            errors.ISE_COMPILE_FAILED: 500,
        }
        status_code = status_map.get(error_code, 500)

        raise _error_response(status_code, error_code, error_message)

    return CompileBundleResponse(
        success=True,
        bundle_name=result["bundle_name"],
        version=result["version"],
        bundle_hash=result["bundle_hash"],
        contracts=sorted(result["contracts"].keys()),
        sha256s=result["sha256s"],
    )


@router.post("/compile/bundle/full", response_model=BundleContentsResponse)
async def compile_bundle_full_endpoint(request: CompileBundleRequest) -> BundleContentsResponse:
    """Compile IDL and return full bundle contents.

    Same as /compile/bundle but includes the actual content of each contract file.
    Useful for testing and debugging.
    """
    result = compile_bundle_to_memory(
        idl=request.idl,
        bundle_name=request.bundle_name,
        validate_finance_pilot=request.validate_finance_pilot,
    )

    if not result["success"]:
        error_code = result.get("error_code", errors.ISE_COMPILE_FAILED)
        error_message = result.get("error_message", "Unknown error")

        status_map = {
            errors.ISE_IDL_INVALID_JSON: 400,
            errors.ISE_IDL_PARSE_FAILED: 400,
            errors.ISE_IDL_MISSING_FIELD: 400,
            errors.ISE_IDL_INSUFFICIENT: 409,
            errors.ISE_APPROVAL_UNMAPPED: 422,
            errors.ISE_SOD_UNMAPPED: 422,
            errors.ISE_ENTITY_MISSING: 422,
            errors.ISE_EMIT_FAILED: 500,
            errors.ISE_MANIFEST_FAILED: 500,
            errors.ISE_COMPILE_FAILED: 500,
        }
        status_code = status_map.get(error_code, 500)

        raise _error_response(status_code, error_code, error_message)

    return BundleContentsResponse(
        success=True,
        bundle_name=result["bundle_name"],
        version=result["version"],
        bundle_hash=result["bundle_hash"],
        contracts=result["contracts"],
        sha256s=result["sha256s"],
    )


# Release Models

class CompileReleaseRequest(BaseModel):
    """Request for compile and release."""
    idl: str = Field(..., min_length=1, description="IDL JSON string to compile")
    bundle_name: str = Field(..., min_length=1, max_length=64, description="Name for the bundle")
    validate_finance_pilot: bool = Field(
        default=True,
        description="Validate for finance-pilot MVP requirements",
    )


class CompileReleaseResponse(BaseModel):
    """Response from compile and release."""
    status: str
    release_id: Optional[str] = None
    bundle_name: Optional[str] = None
    bundle_hash: Optional[str] = None
    error: Optional[Dict[str, Any]] = None


@router.post("/compile/release", response_model=CompileReleaseResponse)
async def compile_release_endpoint(
    request: CompileReleaseRequest,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> CompileReleaseResponse:
    """Compile IDL and deploy via lifecycle scripts.

    Requires X-Admin-Token header matching ENGINE_ISE_ADMIN_TOKEN env var.

    Steps:
    1. Compile bundle to temp directory
    2. Copy to STAGING
    3. Run verify script (verify_bundle.sh)
    4. Run deploy script (deploy_engine_prod.sh)

    Returns:
    - status: "deployed" on success
    - status: "rolled_back" if deploy fails (with error details)
    - status: "failed" if compilation or verification fails
    """
    # Verify admin token
    if not verify_admin_token(x_admin_token):
        raise _error_response(
            401,
            errors.ISE_ADMIN_UNAUTHORIZED,
            "Invalid or missing admin token",
        )

    # Compile and release
    result = compile_release(
        idl=request.idl,
        bundle_name=request.bundle_name,
        validate_finance_pilot=request.validate_finance_pilot,
    )

    # Map failed status to HTTP errors
    if result.status == "failed":
        status_map = {
            errors.ISE_IDL_INVALID_JSON: 400,
            errors.ISE_IDL_PARSE_FAILED: 400,
            errors.ISE_IDL_INSUFFICIENT: 409,
            errors.ISE_VERIFY_FAILED: 409,
            errors.ISE_SCRIPT_UNAVAILABLE: 500,
            errors.ISE_RELEASE_WRITE_FAILED: 500,
        }
        status_code = status_map.get(result.error_code, 500)

        raise HTTPException(
            status_code=status_code,
            detail=result.to_dict(),
        )

    # Return success or rolled_back (both are 200)
    return CompileReleaseResponse(**result.to_dict())
