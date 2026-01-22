"""Outbox File Connector for Legacy Bridge Write-Mode.

Writes governed action commands to outbox files for external consumption.
An external applier (outside the engine) reads these files and applies
the actions to the legacy system.

Etapa 4.3: Legacy Bridge Write-Mode (Governado)
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engine.core.data_root import get_institution_root
from engine.legacy_bridge.write_models import LegacyWriteAction


@dataclass
class OutboxWriteResult:
    """Result of writing an action to the outbox."""

    success: bool
    outbox_path: Optional[str] = None  # Relative path within institution
    outbox_sha256: Optional[str] = None  # Hash of the outbox file
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class OutboxConnector:
    """Connector for writing governed actions to outbox files.

    Outbox files are written in deterministic JSON format for:
    - Hash reproducibility (audit trail)
    - External applier consumption
    - Per-institution/dept isolation

    Directory structure:
        var/institutions/{uuid}/legacy_bridge/outbox/{action_id}.json
        var/institutions/{uuid}/depts/{dept_id}/legacy_bridge/outbox/{action_id}.json
    """

    def __init__(self, institution_id: str, dept_id: Optional[str] = None):
        """Initialize OutboxConnector.

        Args:
            institution_id: Institution UUID.
            dept_id: Optional department ID for multi-dept isolation.
        """
        self._institution_id = institution_id
        self._dept_id = dept_id

        # Resolve outbox directory with dept isolation
        inst_root = get_institution_root(institution_id)
        if dept_id:
            self._outbox_root = inst_root / "depts" / dept_id / "legacy_bridge" / "outbox"
        else:
            self._outbox_root = inst_root / "legacy_bridge" / "outbox"

    @property
    def outbox_root(self) -> Path:
        """Get the outbox root directory."""
        return self._outbox_root

    def _compute_file_sha256(self, content: bytes) -> str:
        """Compute SHA256 hash of content.

        Args:
            content: File content bytes.

        Returns:
            Hex-encoded SHA256 hash.
        """
        return hashlib.sha256(content).hexdigest()

    def write_action(self, action: LegacyWriteAction) -> OutboxWriteResult:
        """Write an action to the outbox.

        Creates a deterministic JSON file for the action.

        Args:
            action: The LegacyWriteAction to write.

        Returns:
            OutboxWriteResult with path and hash.
        """
        try:
            # Ensure outbox directory exists
            self._outbox_root.mkdir(parents=True, exist_ok=True)

            # Generate outbox file path
            file_name = f"{action.action_id}.json"
            file_path = self._outbox_root / file_name

            # Convert to outbox format (deterministic)
            outbox_data = action.to_outbox_dict()

            # Serialize with deterministic format
            content = json.dumps(
                outbox_data,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            content_bytes = content.encode("utf-8")

            # Compute hash before writing
            file_sha256 = self._compute_file_sha256(content_bytes)

            # Write file
            file_path.write_bytes(content_bytes)

            # Compute relative path for audit trail
            inst_root = get_institution_root(self._institution_id)
            relative_path = str(file_path.relative_to(inst_root))

            return OutboxWriteResult(
                success=True,
                outbox_path=relative_path,
                outbox_sha256=file_sha256,
            )

        except Exception as e:
            return OutboxWriteResult(
                success=False,
                error_code="LEGACY_WRITE_OUTBOX_FAILED",
                error_message=str(e),
            )

    def action_exists(self, action_id: str) -> bool:
        """Check if an action file exists in the outbox.

        Args:
            action_id: The action ID to check.

        Returns:
            True if the action file exists.
        """
        file_path = self._outbox_root / f"{action_id}.json"
        return file_path.exists()

    def read_action(self, action_id: str) -> Optional[LegacyWriteAction]:
        """Read an action from the outbox.

        Args:
            action_id: The action ID to read.

        Returns:
            LegacyWriteAction if found, None otherwise.
        """
        file_path = self._outbox_root / f"{action_id}.json"
        if not file_path.exists():
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return LegacyWriteAction.from_dict(data)
        except Exception:
            return None

    def list_actions(self) -> list:
        """List all action IDs in the outbox.

        Returns:
            List of action IDs.
        """
        if not self._outbox_root.exists():
            return []

        action_ids = []
        for file_path in self._outbox_root.glob("*.json"):
            action_id = file_path.stem  # filename without extension
            action_ids.append(action_id)

        return sorted(action_ids)
