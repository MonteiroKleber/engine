"""Run Diff - Generate unified diff between two runs' IDL files."""

import difflib
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .run_detail import load_idl_final, get_run_dir, DEV_RUN_IDL_NOT_FOUND


# Error codes
RUN_DIFF_TOO_LARGE = "RUN_DIFF_TOO_LARGE"

# Size limit for diff (256KB)
MAX_DIFF_SIZE_BYTES = 262144


@dataclass
class DiffResult:
    """Result of diff operation."""

    success: bool
    run_a: Optional[str] = None
    run_b: Optional[str] = None
    diff: Optional[str] = None
    is_identical: bool = False
    size_a: int = 0
    size_b: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        if not self.success:
            return {
                "success": False,
                "error": {
                    "code": self.error_code,
                    "message": self.error_message,
                },
            }

        return {
            "success": True,
            "run_a": self.run_a,
            "run_b": self.run_b,
            "diff": self.diff,
            "is_identical": self.is_identical,
            "size_a": self.size_a,
            "size_b": self.size_b,
        }


def generate_unified_diff(
    text_a: str,
    text_b: str,
    label_a: str = "a",
    label_b: str = "b",
) -> str:
    """Generate unified diff between two texts.

    Args:
        text_a: First text.
        text_b: Second text.
        label_a: Label for first file.
        label_b: Label for second file.

    Returns:
        Unified diff string.
    """
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    # Ensure last lines have newlines for proper diff
    if lines_a and not lines_a[-1].endswith("\n"):
        lines_a[-1] += "\n"
    if lines_b and not lines_b[-1].endswith("\n"):
        lines_b[-1] += "\n"

    diff_lines = difflib.unified_diff(
        lines_a,
        lines_b,
        fromfile=label_a,
        tofile=label_b,
        lineterm="",
    )

    return "".join(diff_lines)


def diff_runs(
    run_a: str,
    run_b: str,
    bundles_root: Optional[str] = None,
) -> DiffResult:
    """Generate diff between two runs' IDL files.

    Args:
        run_a: UUID of the first run.
        run_b: UUID of the second run.
        bundles_root: Root directory for bundles.

    Returns:
        DiffResult with unified diff or error.
    """
    # Load IDL from run A
    idl_a = load_idl_final(run_a, bundles_root)
    if idl_a is None:
        return DiffResult(
            success=False,
            error_code=DEV_RUN_IDL_NOT_FOUND,
            error_message=f"IDL not found for run {run_a}",
        )

    # Load IDL from run B
    idl_b = load_idl_final(run_b, bundles_root)
    if idl_b is None:
        return DiffResult(
            success=False,
            error_code=DEV_RUN_IDL_NOT_FOUND,
            error_message=f"IDL not found for run {run_b}",
        )

    # Check size limit
    size_a = len(idl_a.encode("utf-8"))
    size_b = len(idl_b.encode("utf-8"))

    if size_a > MAX_DIFF_SIZE_BYTES:
        return DiffResult(
            success=False,
            error_code=RUN_DIFF_TOO_LARGE,
            error_message=f"Run {run_a} IDL exceeds {MAX_DIFF_SIZE_BYTES} bytes",
        )

    if size_b > MAX_DIFF_SIZE_BYTES:
        return DiffResult(
            success=False,
            error_code=RUN_DIFF_TOO_LARGE,
            error_message=f"Run {run_b} IDL exceeds {MAX_DIFF_SIZE_BYTES} bytes",
        )

    # Check if identical
    is_identical = idl_a == idl_b

    # Generate diff
    diff = generate_unified_diff(
        idl_a,
        idl_b,
        label_a=f"run-a/{run_a}/idl_final.idl",
        label_b=f"run-b/{run_b}/idl_final.idl",
    )

    return DiffResult(
        success=True,
        run_a=run_a,
        run_b=run_b,
        diff=diff,
        is_identical=is_identical,
        size_a=size_a,
        size_b=size_b,
    )
