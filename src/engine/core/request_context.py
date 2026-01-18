"""Request context using contextvars for request_id propagation."""

from contextvars import ContextVar
from typing import Optional

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(request_id: Optional[str]) -> None:
    """Set the current request_id in context."""
    _request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """Get the current request_id from context, or None if not set."""
    return _request_id_var.get()
