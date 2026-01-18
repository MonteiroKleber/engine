"""Structured JSON logging for production."""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from engine.core.request_context import get_request_id


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }

        # Always include request_id (null if not in request context)
        log_entry["request_id"] = get_request_id()

        # Add extra fields if present
        if hasattr(record, "method"):
            log_entry["method"] = record.method
        if hasattr(record, "path"):
            log_entry["path"] = record.path
        if hasattr(record, "tenant_id"):
            log_entry["tenant_id"] = record.tenant_id
        if hasattr(record, "actor_id"):
            log_entry["actor_id"] = record.actor_id
        if hasattr(record, "status_code"):
            log_entry["status_code"] = record.status_code

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging() -> logging.Logger:
    """Setup logging based on ENGINE_LOG_FORMAT environment variable.
    
    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("engine")
    logger.setLevel(logging.INFO)

    # Clear existing handlers
    logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    # Check log format
    log_format = os.environ.get("ENGINE_LOG_FORMAT", "text")
    
    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        # Default text format
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )

    logger.addHandler(handler)
    
    return logger


def get_logger() -> logging.Logger:
    """Get the engine logger."""
    return logging.getLogger("engine")


def log_request(
    method: str,
    path: str,
    status_code: int,
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> None:
    """Log an HTTP request.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: Response status code
        tenant_id: Optional tenant ID
        actor_id: Optional actor ID
    """
    logger = get_logger()
    
    extra = {
        "method": method,
        "path": path,
        "status_code": status_code,
    }
    if tenant_id:
        extra["tenant_id"] = tenant_id
    if actor_id:
        extra["actor_id"] = actor_id
    
    logger.info(
        f"{method} {path} -> {status_code}",
        extra=extra,
    )
