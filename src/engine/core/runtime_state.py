"""Runtime state management."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class RuntimeMode(str, Enum):
    """Runtime modes."""
    ACTIVE = "ACTIVE"
    SAFE_MODE = "SAFE_MODE"


@dataclass
class RuntimeState:
    """Global runtime state."""
    mode: RuntimeMode = RuntimeMode.ACTIVE
    reason_code: Optional[str] = None
    details: List[str] = field(default_factory=list)

    def set_active(self) -> None:
        """Set runtime to ACTIVE mode."""
        self.mode = RuntimeMode.ACTIVE
        self.reason_code = None
        self.details = []

    def set_safe_mode(self, reason_code: str, details: Optional[List[str]] = None) -> None:
        """Set runtime to SAFE_MODE."""
        self.mode = RuntimeMode.SAFE_MODE
        self.reason_code = reason_code
        self.details = details or []

    def is_active(self) -> bool:
        """Check if runtime is in ACTIVE mode."""
        return self.mode == RuntimeMode.ACTIVE

    def is_safe_mode(self) -> bool:
        """Check if runtime is in SAFE_MODE."""
        return self.mode == RuntimeMode.SAFE_MODE


# Global singleton
runtime_state = RuntimeState()
