"""Máquina de estados do engine."""

from enum import Enum
from typing import Optional


class State(Enum):
    """Estados possíveis do engine."""
    IDLE = "idle"
    INTAKE = "intake"
    PROCESSING = "processing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    ERROR = "error"


class StateMachine:
    """Gerencia transições de estado do engine."""

    def __init__(self) -> None:
        self.current_state: State = State.IDLE
        self.previous_state: Optional[State] = None

    def transition(self, new_state: State) -> None:
        """Transiciona para um novo estado."""
        self.previous_state = self.current_state
        self.current_state = new_state
