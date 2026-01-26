"""Migration check module for Etapa 6.7.

Provides validation that departments are ready to operate in IDL mode:
- operations.json exists for each department
- All bind.kind values are supported by the dispatcher

Used during boot to:
- Fail deterministically if ENGINE_API_MODE=idl and checks fail
- Log warnings if ENGINE_API_MODE=both and checks fail
- Expose migration status to console (read-only)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .operations import get_operations
from .idl_router import get_api_mode, API_MODE_LEGACY, API_MODE_IDL, API_MODE_BOTH


# Bind kinds supported by the dispatcher (Etapas 6.1-6.3 + Expansões)
# These match the handlers in idl_router.py
SUPPORTED_BIND_KINDS = frozenset({"create", "read", "delete", "approval", "approval_decide", "transition"})

# Migration check result codes
MIGRATION_OK = "MIGRATION_OK"
MIGRATION_MISSING_OPERATIONS = "MIGRATION_MISSING_OPERATIONS"
MIGRATION_UNSUPPORTED_BIND_KIND = "MIGRATION_UNSUPPORTED_BIND_KIND"


@dataclass
class UnsupportedBind:
    """Details of an unsupported bind.kind."""

    dept_id: Optional[str]
    operation_id: str
    bind_kind: str


@dataclass
class MigrationCheckResult:
    """Result of migration checks.

    Attributes:
        ok: True if all checks passed.
        code: Result code (MIGRATION_OK, MIGRATION_MISSING_OPERATIONS, etc.)
        message: Human-readable message.
        warnings: List of warning messages.
        depts_migrated: List of department IDs that are fully migrated.
        depts_not_migrated: List of department IDs not migrated.
        unsupported_binds: List of operations with unsupported bind.kind.
    """

    ok: bool
    code: str
    message: str
    warnings: List[str] = field(default_factory=list)
    depts_migrated: List[str] = field(default_factory=list)
    depts_not_migrated: List[str] = field(default_factory=list)
    unsupported_binds: List[UnsupportedBind] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
            "warnings": self.warnings,
            "depts_migrated": self.depts_migrated,
            "depts_not_migrated": self.depts_not_migrated,
            "unsupported_binds": [
                {
                    "dept_id": ub.dept_id,
                    "operation_id": ub.operation_id,
                    "bind_kind": ub.bind_kind,
                }
                for ub in self.unsupported_binds
            ],
        }


def run_migration_checks(departments: Optional[List[str]] = None) -> MigrationCheckResult:
    """Run migration checks for all departments.

    Validates:
    1. Each department has operations.json loaded (get_operations returns non-None)
    2. All operations have supported bind.kind values

    Args:
        departments: List of department IDs to check.
                    If None, checks single-mode (dept_id=None).

    Returns:
        MigrationCheckResult with status and details.
    """
    warnings: List[str] = []
    depts_migrated: List[str] = []
    depts_not_migrated: List[str] = []
    unsupported_binds: List[UnsupportedBind] = []

    # If no departments provided, check single-mode (dept_id=None)
    dept_ids: List[Optional[str]] = list(departments) if departments else [None]

    for dept_id in dept_ids:
        ops_def = get_operations(dept_id)
        dept_label = dept_id or "_single"

        if ops_def is None:
            # No operations.json for this dept
            depts_not_migrated.append(dept_label)
            warnings.append(f"Dept '{dept_label}' has no operations.json")
            continue

        # Check bind.kind coverage for each operation
        dept_has_unsupported = False
        for op in ops_def.operations:
            if op.bind:
                bind_kind = op.bind.get("kind")
                if bind_kind and bind_kind not in SUPPORTED_BIND_KINDS:
                    unsupported_binds.append(
                        UnsupportedBind(
                            dept_id=dept_id,
                            operation_id=op.operation_id,
                            bind_kind=bind_kind,
                        )
                    )
                    dept_has_unsupported = True
                    warnings.append(
                        f"Dept '{dept_label}' op '{op.operation_id}' uses unsupported bind.kind: {bind_kind}"
                    )

        if dept_has_unsupported:
            depts_not_migrated.append(dept_label)
        else:
            depts_migrated.append(dept_label)

    # Determine overall result
    if depts_not_migrated or unsupported_binds:
        if unsupported_binds:
            code = MIGRATION_UNSUPPORTED_BIND_KIND
            message = f"{len(unsupported_binds)} operation(s) use unsupported bind.kind"
        else:
            code = MIGRATION_MISSING_OPERATIONS
            message = f"{len(depts_not_migrated)} dept(s) missing operations.json"

        return MigrationCheckResult(
            ok=False,
            code=code,
            message=message,
            warnings=warnings,
            depts_migrated=depts_migrated,
            depts_not_migrated=depts_not_migrated,
            unsupported_binds=unsupported_binds,
        )

    return MigrationCheckResult(
        ok=True,
        code=MIGRATION_OK,
        message="All departments migrated",
        warnings=[],
        depts_migrated=depts_migrated,
        depts_not_migrated=[],
        unsupported_binds=[],
    )


def get_migration_status(
    institution_id: str, departments: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Get migration status for console display.

    Args:
        institution_id: Institution UUID (for context, not used in checks).
        departments: List of department IDs to check.

    Returns:
        Dict with migration status for template rendering.
    """
    api_mode = get_api_mode()
    result = run_migration_checks(departments)

    # Determine installed depts
    depts_installed = departments if departments else ["_single"]

    return {
        "api_mode": api_mode,
        "depts_installed": depts_installed,
        "depts_migrated": result.depts_migrated,
        "depts_not_migrated": result.depts_not_migrated,
        "unsupported_binds": [
            {
                "dept_id": ub.dept_id,
                "operation_id": ub.operation_id,
                "bind_kind": ub.bind_kind,
            }
            for ub in result.unsupported_binds
        ],
        "migration_complete": result.ok,
        "check_code": result.code,
        "check_message": result.message,
        "warnings": result.warnings,
    }
