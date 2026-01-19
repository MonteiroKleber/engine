"""ISE Release - Deploy bundle via lifecycle scripts."""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from .compiler import compile_bundle
from . import errors
from engine.core.data_root import resolve_namespaced_path


# Environment variable names
ENV_ADMIN_TOKEN = "ENGINE_ISE_ADMIN_TOKEN"
ENV_PROD_BUNDLES_ROOT = "ENGINE_PROD_BUNDLES_ROOT"
ENV_VERIFY_SCRIPT = "ENGINE_VERIFY_SCRIPT"
ENV_DEPLOY_SCRIPT = "ENGINE_DEPLOY_SCRIPT"

# Defaults
DEFAULT_BUNDLES_ROOT = "/var/lib/engine/bundles"
DEFAULT_VERIFY_SCRIPT = "/home/bazari/engine/ops/checks/verify_bundle.sh"
DEFAULT_DEPLOY_SCRIPT = "/home/bazari/engine/ops/scripts/deploy_engine_prod.sh"

# Default relative path for bundles under institution root
DEFAULT_BUNDLES_REL_PATH = "bundles"


def get_admin_token() -> Optional[str]:
    """Get admin token from environment."""
    return os.environ.get(ENV_ADMIN_TOKEN)


def get_bundles_root() -> str:
    """Get production bundles root path (legacy, no institution)."""
    return os.environ.get(ENV_PROD_BUNDLES_ROOT, DEFAULT_BUNDLES_ROOT)


def get_bundles_root_for_institution(institution_id: str) -> Path:
    """Get production bundles root path for a specific institution.

    Uses ENV ENGINE_PROD_BUNDLES_ROOT with namespacing rules:
    - If None: use institution_root/bundles
    - If absolute: use absolute path
    - If relative: use institution_root/<relative>

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to bundles root directory.
    """
    env_value = os.environ.get(ENV_PROD_BUNDLES_ROOT)
    return resolve_namespaced_path(institution_id, env_value, DEFAULT_BUNDLES_REL_PATH)


def get_verify_script() -> str:
    """Get verify script path."""
    return os.environ.get(ENV_VERIFY_SCRIPT, DEFAULT_VERIFY_SCRIPT)


def get_deploy_script() -> str:
    """Get deploy script path."""
    return os.environ.get(ENV_DEPLOY_SCRIPT, DEFAULT_DEPLOY_SCRIPT)


@dataclass
class ReleaseResult:
    """Result of release operation."""

    status: str  # "deployed", "rolled_back", "failed"
    release_id: Optional[str] = None
    bundle_name: Optional[str] = None
    bundle_hash: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    exit_code: Optional[int] = None
    script_output: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result: Dict[str, Any] = {"status": self.status}

        if self.release_id:
            result["release_id"] = self.release_id
        if self.bundle_name:
            result["bundle_name"] = self.bundle_name
        if self.bundle_hash:
            result["bundle_hash"] = self.bundle_hash

        if self.status in ("rolled_back", "failed"):
            result["error"] = {}
            if self.error_code:
                result["error"]["code"] = self.error_code
            if self.error_message:
                result["error"]["message"] = self.error_message
            if self.exit_code is not None:
                result["error"]["exit_code"] = self.exit_code
            if self.script_output:
                result["error"]["output"] = self.script_output

        return result


def verify_admin_token(provided_token: Optional[str]) -> bool:
    """Verify admin token matches environment variable.

    Args:
        provided_token: Token provided in request header.

    Returns:
        True if valid, False otherwise.
    """
    expected_token = get_admin_token()

    # If no token configured, deny all
    if not expected_token:
        return False

    # Compare tokens
    if not provided_token:
        return False

    return provided_token == expected_token


def generate_release_id() -> str:
    """Generate release ID as YYYYMMDD-HHMMSS UTC."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d-%H%M%S")


def _handle_deploy_failure(
    institution_id: Optional[str],
    release_id: str,
    bundle_name: str,
    bundle_hash: Optional[str],
    error_code: str,
    error_message: str,
    exit_code: Optional[int] = None,
    script_output: Optional[str] = None,
) -> ReleaseResult:
    """Handle deploy failure with governed rollback.

    If institution_id is provided, executes governed rollback to pinned release.
    If no pinned release exists, activates SAFE_MODE.

    Args:
        institution_id: Institution UUID (None for legacy deploys).
        release_id: Release ID that failed.
        bundle_name: Bundle name.
        bundle_hash: Bundle hash.
        error_code: Error code from failure.
        error_message: Error message from failure.
        exit_code: Exit code from script (optional).
        script_output: Output from script (optional).

    Returns:
        ReleaseResult with rollback status.
    """
    # If no institution_id, fall back to legacy behavior
    if institution_id is None:
        return ReleaseResult(
            status="rolled_back",
            release_id=release_id,
            bundle_name=bundle_name,
            bundle_hash=bundle_hash,
            error_code=error_code,
            error_message=f"{error_message}, rolled back (legacy)",
            exit_code=exit_code,
            script_output=script_output,
        )

    # Execute governed rollback
    from engine.core.ege_rollback import execute_governed_rollback

    rollback_result = execute_governed_rollback(
        institution_id=institution_id,
        failed_release_id=release_id,
        reason=error_message,
    )

    if rollback_result.success:
        # Rollback succeeded
        return ReleaseResult(
            status="rolled_back",
            release_id=release_id,
            bundle_name=bundle_name,
            bundle_hash=bundle_hash,
            error_code=error_code,
            error_message=f"{error_message}, rolled back to {rollback_result.rolled_back_to}",
            exit_code=exit_code,
            script_output=script_output,
        )
    else:
        # Rollback failed - possibly SAFE_MODE activated
        if rollback_result.safe_mode_activated:
            return ReleaseResult(
                status="failed",
                release_id=release_id,
                bundle_name=bundle_name,
                bundle_hash=bundle_hash,
                error_code=rollback_result.error_code or error_code,
                error_message=f"{error_message}; rollback failed: {rollback_result.error_message}; SAFE_MODE activated",
                exit_code=exit_code,
                script_output=script_output,
            )
        else:
            return ReleaseResult(
                status="failed",
                release_id=release_id,
                bundle_name=bundle_name,
                bundle_hash=bundle_hash,
                error_code=rollback_result.error_code or error_code,
                error_message=f"{error_message}; rollback failed: {rollback_result.error_message}",
                exit_code=exit_code,
                script_output=script_output,
            )


def compile_release(
    idl: str,
    bundle_name: str,
    validate_finance_pilot: bool = True,
    institution_id: Optional[str] = None,
) -> ReleaseResult:
    """Compile IDL and deploy via lifecycle scripts.

    Order:
    1. Compile bundle to temp dir
    2. Copy to STAGING
    3. Run verify script
    4. Run deploy script

    Args:
        idl: IDL JSON string.
        bundle_name: Name for the bundle.
        validate_finance_pilot: Validate for finance-pilot MVP.
        institution_id: Institution UUID for namespaced storage. If set, bundles go under institution root.

    Returns:
        ReleaseResult with deployment status.
    """
    release_id = generate_release_id()

    # Determine bundles root
    if institution_id is not None:
        bundles_root = str(get_bundles_root_for_institution(institution_id))
    else:
        bundles_root = get_bundles_root()

    verify_script = get_verify_script()
    deploy_script = get_deploy_script()

    # Check scripts exist
    if not Path(verify_script).exists():
        return ReleaseResult(
            status="failed",
            release_id=release_id,
            bundle_name=bundle_name,
            error_code=errors.ISE_SCRIPT_UNAVAILABLE,
            error_message=f"Verify script not found: {verify_script}",
        )

    if not Path(deploy_script).exists():
        return ReleaseResult(
            status="failed",
            release_id=release_id,
            bundle_name=bundle_name,
            error_code=errors.ISE_SCRIPT_UNAVAILABLE,
            error_message=f"Deploy script not found: {deploy_script}",
        )

    # Step 1: Compile bundle to temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        compile_result = compile_bundle(
            idl=idl,
            bundle_name=bundle_name,
            output_dir=temp_dir,
            validate_finance_pilot=validate_finance_pilot,
        )

        if not compile_result.success:
            return ReleaseResult(
                status="failed",
                release_id=release_id,
                bundle_name=bundle_name,
                error_code=compile_result.error_code,
                error_message=compile_result.error_message,
            )

        bundle_hash = compile_result.bundle_hash
        temp_bundle_path = Path(temp_dir) / bundle_name

        # Step 2: Copy to STAGING
        staging_dir = Path(bundles_root) / "STAGING"
        staging_bundle_path = staging_dir / bundle_name

        try:
            # Create staging directory if needed
            staging_dir.mkdir(parents=True, exist_ok=True)

            # Remove existing staging bundle if present
            if staging_bundle_path.exists():
                shutil.rmtree(staging_bundle_path)

            # Copy bundle to staging
            shutil.copytree(temp_bundle_path, staging_bundle_path)
        except Exception as e:
            return ReleaseResult(
                status="failed",
                release_id=release_id,
                bundle_name=bundle_name,
                bundle_hash=bundle_hash,
                error_code=errors.ISE_RELEASE_WRITE_FAILED,
                error_message=f"Failed to copy bundle to staging: {e}",
            )

        # Step 3: Run verify script
        try:
            verify_result = subprocess.run(
                [verify_script, str(staging_bundle_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if verify_result.returncode != 0:
                # Cleanup staging
                try:
                    shutil.rmtree(staging_bundle_path)
                except Exception:
                    pass

                return ReleaseResult(
                    status="failed",
                    release_id=release_id,
                    bundle_name=bundle_name,
                    bundle_hash=bundle_hash,
                    error_code=errors.ISE_VERIFY_FAILED,
                    error_message="Bundle verification failed",
                    exit_code=verify_result.returncode,
                    script_output=verify_result.stderr or verify_result.stdout,
                )
        except subprocess.TimeoutExpired:
            return ReleaseResult(
                status="failed",
                release_id=release_id,
                bundle_name=bundle_name,
                bundle_hash=bundle_hash,
                error_code=errors.ISE_VERIFY_FAILED,
                error_message="Verify script timed out",
            )
        except Exception as e:
            return ReleaseResult(
                status="failed",
                release_id=release_id,
                bundle_name=bundle_name,
                bundle_hash=bundle_hash,
                error_code=errors.ISE_VERIFY_FAILED,
                error_message=f"Verify script error: {e}",
            )

        # Step 4: Run deploy script
        try:
            deploy_result = subprocess.run(
                [deploy_script],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if deploy_result.returncode != 0:
                # Deploy failed - execute governed rollback
                return _handle_deploy_failure(
                    institution_id=institution_id,
                    release_id=release_id,
                    bundle_name=bundle_name,
                    bundle_hash=bundle_hash,
                    error_code=errors.ISE_DEPLOY_FAILED,
                    error_message="Deploy failed",
                    exit_code=deploy_result.returncode,
                    script_output=deploy_result.stderr or deploy_result.stdout,
                )
        except subprocess.TimeoutExpired:
            return _handle_deploy_failure(
                institution_id=institution_id,
                release_id=release_id,
                bundle_name=bundle_name,
                bundle_hash=bundle_hash,
                error_code=errors.ISE_DEPLOY_FAILED,
                error_message="Deploy script timed out",
            )
        except Exception as e:
            return _handle_deploy_failure(
                institution_id=institution_id,
                release_id=release_id,
                bundle_name=bundle_name,
                bundle_hash=bundle_hash,
                error_code=errors.ISE_DEPLOY_FAILED,
                error_message=f"Deploy script error: {e}",
            )

    # Success
    return ReleaseResult(
        status="deployed",
        release_id=release_id,
        bundle_name=bundle_name,
        bundle_hash=bundle_hash,
    )
