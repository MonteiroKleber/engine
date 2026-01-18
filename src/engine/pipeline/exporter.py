"""Pipeline Exporter - Deterministic ZIP export for sandbox bundles."""

import hashlib
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .registry import get_registry, get_dev_runs_dir_for_institution


# Fixed timestamp for deterministic ZIP (1980-01-01 00:00:00)
# This is the minimum date supported by ZIP format
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

# Fixed permissions for deterministic ZIP
FIXED_FILE_PERMISSIONS = 0o644

# Error codes
PIPELINE_RUN_NOT_FOUND = "PIPELINE_RUN_NOT_FOUND"
PIPELINE_BUNDLE_NOT_FOUND = "PIPELINE_BUNDLE_NOT_FOUND"
PIPELINE_EXPORT_FAILED = "PIPELINE_EXPORT_FAILED"
PIPELINE_DOWNLOAD_NOT_FOUND = "PIPELINE_DOWNLOAD_NOT_FOUND"


@dataclass
class ExportResult:
    """Result of bundle export."""

    success: bool
    zip_path: Optional[str] = None
    zip_sha256: Optional[str] = None
    download_url: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        if self.success:
            return {
                "status": "EXPORTED",
                "zip_path": self.zip_path,
                "zip_sha256": self.zip_sha256,
                "download_url": self.download_url,
            }
        else:
            return {
                "status": "FAILED",
                "error": {
                    "code": self.error_code,
                    "message": self.error_message,
                },
            }


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def export_bundle_zip(
    run_id: str,
    bundle_name: str,
    bundles_root: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> ExportResult:
    """Export bundle from dev-runs sandbox to deterministic ZIP.

    Creates a ZIP file at: <dev_runs_dir>/<run_id>/exports/<bundle_name>.zip
    The ZIP contains: <bundle_name>/... with all bundle files.

    Deterministic properties:
    - Paths are sorted alphabetically
    - Timestamp is fixed to 1980-01-01 00:00:00
    - Permissions are fixed to 0644
    - Uses ZIP_DEFLATED compression

    Args:
        run_id: UUID of the build run.
        bundle_name: Name of the bundle.
        bundles_root: Root directory for bundles (default: from env or "bundles"). Ignored if institution_id is set.
        institution_id: Institution UUID for namespaced storage. If set, dev-runs are under institution root.

    Returns:
        ExportResult with zip_path, zip_sha256, and download_url on success.
    """
    # Determine dev-runs directory
    if institution_id is not None:
        dev_runs_dir = get_dev_runs_dir_for_institution(institution_id)
    else:
        root = bundles_root or os.environ.get("ENGINE_PROD_BUNDLES_ROOT", "bundles")
        dev_runs_dir = Path(root) / "dev-runs"

    # Check run directory exists
    run_path = dev_runs_dir / run_id
    if not run_path.exists():
        return ExportResult(
            success=False,
            error_code=PIPELINE_RUN_NOT_FOUND,
            error_message=f"Run {run_id} not found",
        )

    # Check bundle directory exists
    bundle_path = run_path / bundle_name
    if not bundle_path.exists():
        return ExportResult(
            success=False,
            error_code=PIPELINE_BUNDLE_NOT_FOUND,
            error_message=f"Bundle {bundle_name} not found in run {run_id}",
        )

    # Create exports directory
    exports_path = run_path / "exports"
    exports_path.mkdir(parents=True, exist_ok=True)

    # ZIP output path
    zip_path = exports_path / f"{bundle_name}.zip"

    try:
        # Create deterministic ZIP
        _create_deterministic_zip(bundle_path, zip_path, bundle_name)

        # Compute SHA256
        zip_sha256 = compute_sha256(zip_path)

        # Build download URL
        download_url = f"/pipeline/build/download?run_id={run_id}&bundle_name={bundle_name}"

        # Emit DEV_RUN_EXPORTED to registry
        try:
            registry = get_registry(institution_id=institution_id)
            registry.emit_exported(
                run_id=run_id,
                bundle_name=bundle_name,
                zip_path=str(zip_path),
                zip_sha256=zip_sha256,
            )
        except Exception:
            # Registry errors are non-fatal - log but continue
            pass

        return ExportResult(
            success=True,
            zip_path=str(zip_path),
            zip_sha256=zip_sha256,
            download_url=download_url,
        )

    except Exception as e:
        return ExportResult(
            success=False,
            error_code=PIPELINE_EXPORT_FAILED,
            error_message=f"Failed to create ZIP: {e}",
        )


def _create_deterministic_zip(
    source_dir: Path,
    zip_path: Path,
    archive_root: str,
) -> None:
    """Create a deterministic ZIP file from a directory.

    Args:
        source_dir: Directory to archive.
        zip_path: Output ZIP file path.
        archive_root: Root directory name inside the ZIP.
    """
    # Collect all files with relative paths
    files_to_add = []
    for file_path in source_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(source_dir)
            archive_name = f"{archive_root}/{rel_path}"
            files_to_add.append((file_path, archive_name))

    # Sort by archive name for deterministic order
    files_to_add.sort(key=lambda x: x[1])

    # Create ZIP with deterministic settings
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path, archive_name in files_to_add:
            # Read file content
            content = file_path.read_bytes()

            # Create ZipInfo with fixed timestamp and permissions
            info = zipfile.ZipInfo(archive_name, date_time=FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            # External attributes: high 16 bits are Unix permissions
            info.external_attr = (FIXED_FILE_PERMISSIONS | 0o100000) << 16

            zf.writestr(info, content)


def get_zip_path(
    run_id: str,
    bundle_name: str,
    bundles_root: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> Optional[Path]:
    """Get path to exported ZIP file if it exists.

    Args:
        run_id: UUID of the build run.
        bundle_name: Name of the bundle.
        bundles_root: Root directory for bundles. Ignored if institution_id is set.
        institution_id: Institution UUID for namespaced storage.

    Returns:
        Path to ZIP file if exists, None otherwise.
    """
    if institution_id is not None:
        dev_runs_dir = get_dev_runs_dir_for_institution(institution_id)
    else:
        root = bundles_root or os.environ.get("ENGINE_PROD_BUNDLES_ROOT", "bundles")
        dev_runs_dir = Path(root) / "dev-runs"

    zip_path = dev_runs_dir / run_id / "exports" / f"{bundle_name}.zip"

    if zip_path.exists():
        return zip_path
    return None
