"""Wizard package - Assisted entry for IDL Draft generation.

The wizard provides a structured way to collect system requirements
and export them as IDL Draft v1 for the engine pipeline.

Components:
- session: Session management (create, load, update)
- export: IDL Draft generation from session
- wizard_runlog: Runlog for wizard audit trail
- wizard_cli: CLI commands (start, resume, export)
"""

from .wizard_runlog import (
    new_wizard_runlog,
    finalize_wizard_runlog,
    validate_wizard_runlog,
    WizardRunlogValidationError,
)

__all__ = [
    "new_wizard_runlog",
    "finalize_wizard_runlog",
    "validate_wizard_runlog",
    "WizardRunlogValidationError",
]
