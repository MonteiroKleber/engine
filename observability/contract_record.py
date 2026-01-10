"""Contract Record - Dataclass for contract ledger entries in RunLog.

Each artifact saved during a pipeline run gets a ContractRecord entry
that tracks its integrity via content hash.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ContractRecord:
    """A single contract record for an artifact in the RunLog ledger.

    Attributes:
        kind: Artifact type (idl|srs|ir|oas|rbac|plan|diagnostic_report|release_report|patch_manifest)
        schema_version: Schema version if artifact has one (e.g., "idl.v1")
        content_hash_sha256: Full SHA256 hash (64 chars)
        path: Filesystem path where artifact is stored
        contract_gate_ok: True if contract gate validation passed
        contract_gate_error: Error message if gate failed
        computed_at: ISO timestamp when this record was computed (volatile, not in artifact hash)
    """

    kind: str
    path: Optional[str] = None
    schema_version: Optional[str] = None
    content_hash_sha256: Optional[str] = None
    contract_gate_ok: bool = True
    contract_gate_error: str = ""
    computed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "kind": self.kind,
            "schema_version": self.schema_version,
            "content_hash_sha256": self.content_hash_sha256,
            "path": self.path,
            "contract_gate_ok": self.contract_gate_ok,
            "contract_gate_error": self.contract_gate_error,
            "computed_at": self.computed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContractRecord":
        """Create from dictionary."""
        return cls(
            kind=data.get("kind", "unknown"),
            schema_version=data.get("schema_version"),
            content_hash_sha256=data.get("content_hash_sha256"),
            path=data.get("path"),
            contract_gate_ok=data.get("contract_gate_ok", True),
            contract_gate_error=data.get("contract_gate_error", ""),
            computed_at=data.get("computed_at", datetime.now().isoformat()),
        )


class ContractLedger:
    """Collection of ContractRecords for a pipeline run.

    Stores records by kind for easy lookup.
    """

    def __init__(self) -> None:
        self._records: Dict[str, ContractRecord] = {}

    def add(self, record: ContractRecord) -> None:
        """Add a contract record to the ledger."""
        self._records[record.kind] = record

    def get(self, kind: str) -> Optional[ContractRecord]:
        """Get a contract record by kind."""
        return self._records.get(kind)

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """Convert ledger to dict format for RunLog."""
        return {kind: record.to_dict() for kind, record in self._records.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Dict[str, Any]]) -> "ContractLedger":
        """Create ledger from dict."""
        ledger = cls()
        for kind, record_dict in data.items():
            record_dict["kind"] = kind  # Ensure kind is set
            ledger.add(ContractRecord.from_dict(record_dict))
        return ledger

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, kind: str) -> bool:
        return kind in self._records

    def kinds(self) -> List[str]:
        """List all artifact kinds in the ledger."""
        return list(self._records.keys())

    def all_ok(self) -> bool:
        """Check if all contract gates passed.

        Returns True if ledger is empty or all records have contract_gate_ok=True.
        """
        return all(record.contract_gate_ok for record in self._records.values())

    def get_errors(self) -> List[ContractRecord]:
        """Get all records where contract gate failed."""
        return [record for record in self._records.values() if not record.contract_gate_ok]
