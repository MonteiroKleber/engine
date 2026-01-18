"""Security helpers for HTTP hardening."""

import os
from typing import List, Optional

from fastapi import Request
from fastapi.responses import Response


def apply_security_headers(response: Response) -> Response:
    """Apply security headers to response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


def get_client_ip(request: Request) -> str:
    """Get client IP from X-Forwarded-For or request.client.host."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First IP in the chain is the original client
        return forwarded_for.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


def parse_cors_origins() -> Optional[List[str]]:
    """Parse CORS origins from ENGINE_CORS_ORIGINS env var.

    Returns:
        List of origins if set, None if not set.
    """
    origins_str = os.environ.get("ENGINE_CORS_ORIGINS")
    if not origins_str:
        return None

    # Parse CSV
    origins = [origin.strip() for origin in origins_str.split(",") if origin.strip()]
    return origins if origins else None


def get_max_body_bytes() -> int:
    """Get max body size from ENGINE_MAX_BODY_BYTES env var."""
    try:
        return int(os.environ.get("ENGINE_MAX_BODY_BYTES", "262144"))
    except (ValueError, TypeError):
        return 262144
