"""Contexto de execução do engine."""

from typing import Any, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class ExecutionContext:
    """Mantém o contexto de execução atual."""

    project_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def reset(self) -> None:
        """Reseta o contexto de execução."""
        self.project_id = None
        self.session_id = None
        self.metadata = {}
