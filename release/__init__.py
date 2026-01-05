"""Release module - QA e Release Management.

Este modulo contem agentes para:
- Smoke tests
- Release checklist
- Bundle generation
- Docker Compose validation
"""

from .qa_release_agent import QAReleaseAgent, SmokeTestReport, ChecklistReport
from .smoke_runner import SmokeRunner, LiveSmokeRunner, SmokeReport, SmokeResult, run_smoke
from .docker_compose_validator import (
    DockerComposeValidator,
    DockerComposeValidationResult,
    DockerComposeUpResult,
    validate_docker_compose,
    ensure_docker_compose,
)
from .release_checklist import (
    ReleaseChecklist,
    ReleaseChecklistResult,
    ChecklistItem,
    run_release_checklist,
)
from .release_report import (
    ReleaseReport,
    ReleaseReportGenerator,
    generate_release_report,
)

__all__ = [
    # QA Release Agent
    "QAReleaseAgent",
    "SmokeTestReport",
    "ChecklistReport",
    # Smoke Runner
    "SmokeRunner",
    "LiveSmokeRunner",
    "SmokeReport",
    "SmokeResult",
    "run_smoke",
    # Docker Compose
    "DockerComposeValidator",
    "DockerComposeValidationResult",
    "DockerComposeUpResult",
    "validate_docker_compose",
    "ensure_docker_compose",
    # Release Checklist
    "ReleaseChecklist",
    "ReleaseChecklistResult",
    "ChecklistItem",
    "run_release_checklist",
    # Release Report
    "ReleaseReport",
    "ReleaseReportGenerator",
    "generate_release_report",
]
