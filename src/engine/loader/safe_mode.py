"""Safe mode management."""

from typing import List, Optional

from engine.core.runtime_state import runtime_state
from engine.core.ledger import get_ledger
from engine.core.actor_context import DEFAULT_TENANT_ID


def enter_safe_mode(reason_code: str, details: Optional[List[str]] = None) -> None:
    """Enter safe mode with a reason code.

    Args:
        reason_code: The reason code for entering safe mode.
        details: Optional list of detail messages.
    """
    runtime_state.set_safe_mode(reason_code, details)

    # Emit SAFE_MODE_ENTERED event to ledger
    ledger = get_ledger()
    if ledger:
        ledger.append(
            event_type="SAFE_MODE_ENTERED",
            tenant_id=DEFAULT_TENANT_ID,
            actor_id="00000000-0000-0000-0000-000000000000",  # System actor
            actor_roles=["system"],
            case_id="runtime",
            step="safe_mode",
            payload={
                "reason_code": reason_code,
                "details": details or [],
            },
        )
