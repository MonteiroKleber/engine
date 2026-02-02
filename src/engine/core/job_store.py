"""JobStore - First-class job storage for governed async operations.

Provides per-institution job state management for the job-based execution model:
- job.request: Create job with params, apply governance gates
- job.enqueue: Write to outbox for runtime execution
- job.get: Retrieve job state and result

This module is bundle-agnostic - all job types are defined in the IDL bundle,
not hardcoded in the Engine.

Jobs First-Class Spec: docs/specs/core-generico/02-jobs-first-class.md
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.core.data_root import get_institution_root


class JobState(str, Enum):
    """Job lifecycle states."""

    REQUESTED = "requested"  # Created, gates passed, awaiting enqueue
    PENDING_APPROVAL = "pending_approval"  # Requires approval before enqueue
    APPROVED = "approved"  # Approval granted, ready for enqueue
    REJECTED = "rejected"  # Approval denied (terminal)
    ENQUEUED = "enqueued"  # Written to outbox, awaiting runtime
    EXECUTED = "executed"  # Runtime reported success (terminal)
    FAILED = "failed"  # Runtime reported failure (terminal)


@dataclass
class Job:
    """Job state record.

    Represents a governed async operation that will be executed by the runtime.
    All fields are bundle-agnostic - job_type comes from the IDL bundle.
    """

    # Identification
    job_id: str  # UUID
    job_type: str  # From bundle (e.g., "file.list", "file.delete")
    institution_id: str
    dept_id: Optional[str] = None

    # State
    state: str = JobState.REQUESTED.value

    # Parameters (from request body, validated against bundle schema)
    params: Dict[str, Any] = field(default_factory=dict)
    params_sha256: str = ""  # Hash for audit/idempotency

    # Governance tracking
    requested_by: str = ""  # Actor ID
    approval_id: Optional[str] = None  # If approval required
    approved_by: Optional[str] = None  # Actor who approved
    mandate_id: Optional[str] = None  # Mandate that allowed

    # Result (from runtime report)
    result_json: Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    exit_code: int = 0
    artifacts: List[str] = field(default_factory=list)  # Paths to result files

    # Timestamps
    created_at: str = ""
    enqueued_at: Optional[str] = None
    executed_at: Optional[str] = None

    # Version for optimistic locking
    version: int = 1

    def __post_init__(self) -> None:
        """Set defaults on creation."""
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.job_id:
            self.job_id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to storage dict."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "institution_id": self.institution_id,
            "dept_id": self.dept_id,
            "state": self.state,
            "params": self.params,
            "params_sha256": self.params_sha256,
            "requested_by": self.requested_by,
            "approval_id": self.approval_id,
            "approved_by": self.approved_by,
            "mandate_id": self.mandate_id,
            "result_json": self.result_json,
            "result_summary": self.result_summary,
            "exit_code": self.exit_code,
            "artifacts": self.artifacts,
            "created_at": self.created_at,
            "enqueued_at": self.enqueued_at,
            "executed_at": self.executed_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Job":
        """Create from storage dict."""
        return cls(
            job_id=d.get("job_id", ""),
            job_type=d.get("job_type", ""),
            institution_id=d.get("institution_id", ""),
            dept_id=d.get("dept_id"),
            state=d.get("state", JobState.REQUESTED.value),
            params=d.get("params", {}),
            params_sha256=d.get("params_sha256", ""),
            requested_by=d.get("requested_by", ""),
            approval_id=d.get("approval_id"),
            approved_by=d.get("approved_by"),
            mandate_id=d.get("mandate_id"),
            result_json=d.get("result_json"),
            result_summary=d.get("result_summary"),
            exit_code=d.get("exit_code", 0),
            artifacts=d.get("artifacts", []),
            created_at=d.get("created_at", ""),
            enqueued_at=d.get("enqueued_at"),
            executed_at=d.get("executed_at"),
            version=d.get("version", 1),
        )

    def to_outbox_dict(self) -> Dict[str, Any]:
        """Convert to outbox file format (for runtime consumption).

        This is the payload the runtime reads from the outbox.
        Uses action_id/action_type for compatibility with Agent Runtime.
        See: libervia-agent-runtime/docs/INTEGRATION.md
        """
        return {
            "schema_version": "1.0",
            # Agent Runtime expects action_id/action_type (not job_id/job_type)
            "action_id": self.job_id,
            "action_type": self.job_type,
            # Also include job_id/job_type for forward compatibility
            "job_id": self.job_id,
            "job_type": self.job_type,
            "institution_id": self.institution_id,
            "dept_id": self.dept_id,
            "params": self.params,
            "requested_by": self.requested_by,
            "requested_at": self.created_at,
            "mandate_id": self.mandate_id,
            "approval_id": self.approval_id,
            "approved_by": self.approved_by,
        }


class JobStore:
    """Per-institution job state storage.

    Stores jobs in a JSON file per institution, similar to StateStore pattern.
    Thread-safe within a single process via file-based locking pattern.

    Directory structure:
        var/institutions/{uuid}/jobs/jobs.json
        var/institutions/{uuid}/depts/{dept_id}/jobs/jobs.json
    """

    def __init__(self, institution_id: str, dept_id: Optional[str] = None):
        """Initialize JobStore.

        Args:
            institution_id: Institution UUID.
            dept_id: Optional department ID for multi-dept isolation.
        """
        self._institution_id = institution_id
        self._dept_id = dept_id

        # Resolve storage path with dept isolation
        inst_root = get_institution_root(institution_id)
        if dept_id:
            self._store_dir = inst_root / "depts" / dept_id / "jobs"
        else:
            self._store_dir = inst_root / "jobs"

        self._store_path = self._store_dir / "jobs.json"

        # In-memory cache
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load jobs from disk."""
        if self._store_path.exists():
            try:
                content = self._store_path.read_text(encoding="utf-8")
                data = json.loads(content)
                self._data = data.get("jobs", {})
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        """Persist jobs to disk."""
        self._store_dir.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {"jobs": self._data},
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )
        self._store_path.write_text(content, encoding="utf-8")

    def create_job(
        self,
        job_type: str,
        params: Dict[str, Any],
        requested_by: str,
        params_sha256: str = "",
        approval_id: Optional[str] = None,
        mandate_id: Optional[str] = None,
        initial_state: str = JobState.REQUESTED.value,
    ) -> Job:
        """Create a new job.

        Args:
            job_type: Job type from bundle (e.g., "file.list").
            params: Job parameters.
            requested_by: Actor ID who requested.
            params_sha256: Hash of params for audit.
            approval_id: Approval ID if pending approval.
            mandate_id: Mandate ID that allowed.
            initial_state: Initial job state.

        Returns:
            Created Job.
        """
        job = Job(
            job_id=str(uuid.uuid4()),
            job_type=job_type,
            institution_id=self._institution_id,
            dept_id=self._dept_id,
            state=initial_state,
            params=params,
            params_sha256=params_sha256,
            requested_by=requested_by,
            approval_id=approval_id,
            mandate_id=mandate_id,
        )

        self._data[job.job_id] = job.to_dict()
        self._save()
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID.

        Args:
            job_id: Job UUID.

        Returns:
            Job if found, None otherwise.
        """
        data = self._data.get(job_id)
        if data:
            return Job.from_dict(data)
        return None

    def update_job_state(
        self,
        job_id: str,
        state: str,
        approved_by: Optional[str] = None,
        enqueued_at: Optional[str] = None,
        executed_at: Optional[str] = None,
        result_json: Optional[Dict[str, Any]] = None,
        result_summary: Optional[str] = None,
        exit_code: Optional[int] = None,
        artifacts: Optional[List[str]] = None,
    ) -> Optional[Job]:
        """Update job state and related fields.

        Args:
            job_id: Job UUID.
            state: New state.
            approved_by: Actor who approved (if transitioning to approved).
            enqueued_at: Timestamp when enqueued.
            executed_at: Timestamp when executed.
            result_json: Result from runtime.
            result_summary: Summary text.
            exit_code: Exit code from runtime.
            artifacts: List of artifact paths.

        Returns:
            Updated Job if found, None otherwise.
        """
        data = self._data.get(job_id)
        if not data:
            return None

        data["state"] = state
        data["version"] = data.get("version", 1) + 1

        if approved_by is not None:
            data["approved_by"] = approved_by
        if enqueued_at is not None:
            data["enqueued_at"] = enqueued_at
        if executed_at is not None:
            data["executed_at"] = executed_at
        if result_json is not None:
            data["result_json"] = result_json
        if result_summary is not None:
            data["result_summary"] = result_summary
        if exit_code is not None:
            data["exit_code"] = exit_code
        if artifacts is not None:
            data["artifacts"] = artifacts

        self._data[job_id] = data
        self._save()
        return Job.from_dict(data)

    def list_jobs(
        self,
        state: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Job]:
        """List jobs with optional filters.

        Args:
            state: Filter by state.
            job_type: Filter by job type.
            limit: Max results.

        Returns:
            List of matching Jobs.
        """
        jobs = []
        for data in self._data.values():
            if state and data.get("state") != state:
                continue
            if job_type and data.get("job_type") != job_type:
                continue
            jobs.append(Job.from_dict(data))
            if len(jobs) >= limit:
                break
        return jobs

    def get_job_by_approval_id(self, approval_id: str) -> Optional[Job]:
        """Get job by approval ID.

        Args:
            approval_id: Approval UUID.

        Returns:
            Job if found, None otherwise.
        """
        for data in self._data.values():
            if data.get("approval_id") == approval_id:
                return Job.from_dict(data)
        return None


def get_job_store(institution_id: str, dept_id: Optional[str] = None) -> JobStore:
    """Get JobStore for institution.

    Factory function for creating JobStore instances.

    Args:
        institution_id: Institution UUID.
        dept_id: Optional department ID.

    Returns:
        JobStore instance.
    """
    return JobStore(institution_id, dept_id)
