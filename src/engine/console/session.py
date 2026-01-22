"""Console session management with signed cookies.

Provides browser-based authentication via signed session cookies,
while maintaining compatibility with X-Admin-Token header for API clients.

Etapa 4.1: Auth no Browser (Sessão/Cookie)
"""

import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Optional, Tuple

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


# Environment variable names
ENV_SESSION_SECRET = "ENGINE_CONSOLE_SESSION_SECRET"
ENV_SESSION_TTL_HOURS = "ENGINE_CONSOLE_SESSION_TTL_HOURS"
ENV_SECURE_COOKIE = "ENGINE_CONSOLE_SECURE_COOKIE"

# Cookie configuration
COOKIE_NAME = "console_session"
COOKIE_PATH = "/console/"
DEFAULT_TTL_HOURS = 8

# Error codes
SESSION_SECRET_MISSING = "SESSION_SECRET_MISSING"


def get_session_secret() -> Optional[str]:
    """Get session secret from environment.

    Returns:
        Session secret string, or None if not configured.
    """
    return os.environ.get(ENV_SESSION_SECRET)


def get_session_ttl_seconds() -> int:
    """Get session TTL in seconds.

    Returns:
        TTL in seconds (default 8 hours).
    """
    try:
        hours = int(os.environ.get(ENV_SESSION_TTL_HOURS, DEFAULT_TTL_HOURS))
        return hours * 3600
    except (ValueError, TypeError):
        return DEFAULT_TTL_HOURS * 3600


def should_use_secure_cookie() -> bool:
    """Determine if Secure flag should be set on cookie.

    Returns:
        True if Secure flag should be set.
    """
    value = os.environ.get(ENV_SECURE_COOKIE, "auto").lower()
    if value == "true":
        return True
    if value == "false":
        return False
    # Auto: assume HTTPS in production
    return os.environ.get("ENGINE_ENV", "development") == "production"


def _get_serializer() -> URLSafeTimedSerializer:
    """Get configured serializer for signing cookies.

    Returns:
        Configured URLSafeTimedSerializer.

    Raises:
        RuntimeError: If session secret is not configured.
    """
    secret = get_session_secret()
    if not secret:
        raise RuntimeError(
            f"Console session requires {ENV_SESSION_SECRET} environment variable. "
            "Set a secure random string (32+ characters)."
        )
    return URLSafeTimedSerializer(secret, salt="console_session")


@dataclass
class SessionData:
    """Data stored in session cookie."""

    token_hash: str  # sha256(admin_token)[:16]
    csrf_token: str  # Random CSRF token
    nonce: str       # Random nonce for uniqueness


def create_session_cookie(admin_token: str) -> Tuple[str, str]:
    """Create signed session cookie value.

    Args:
        admin_token: Valid admin token to create session for.

    Returns:
        Tuple of (cookie_value, csrf_token).

    Raises:
        RuntimeError: If session secret is not configured.
    """
    serializer = _get_serializer()

    # Hash the token (don't store full token in cookie)
    token_hash = hashlib.sha256(admin_token.encode()).hexdigest()[:16]

    # Generate CSRF token and nonce
    csrf_token = secrets.token_hex(16)
    nonce = secrets.token_hex(8)

    # Create signed cookie
    data = {
        "th": token_hash,
        "csrf": csrf_token,
        "n": nonce,
    }
    cookie_value = serializer.dumps(data)

    return cookie_value, csrf_token


def verify_session_cookie(cookie_value: str, expected_admin_token: str) -> Optional[SessionData]:
    """Verify session cookie is valid and matches expected token.

    Args:
        cookie_value: Signed cookie value from request.
        expected_admin_token: Current admin token from environment.

    Returns:
        SessionData if valid, None if invalid or expired.
    """
    if not cookie_value or not expected_admin_token:
        return None

    try:
        serializer = _get_serializer()
        max_age = get_session_ttl_seconds()
        data = serializer.loads(cookie_value, max_age=max_age)

        # Verify token hash matches current admin token
        expected_hash = hashlib.sha256(expected_admin_token.encode()).hexdigest()[:16]
        if not secrets.compare_digest(data.get("th", ""), expected_hash):
            return None

        return SessionData(
            token_hash=data["th"],
            csrf_token=data.get("csrf", ""),
            nonce=data.get("n", ""),
        )
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        return None


def get_csrf_from_cookie(cookie_value: str) -> Optional[str]:
    """Extract CSRF token from session cookie without full validation.

    Used for CSRF validation where we need the token but not full session check.

    Args:
        cookie_value: Signed cookie value from request.

    Returns:
        CSRF token if extractable, None otherwise.
    """
    if not cookie_value:
        return None

    try:
        serializer = _get_serializer()
        max_age = get_session_ttl_seconds()
        data = serializer.loads(cookie_value, max_age=max_age)
        return data.get("csrf")
    except (BadSignature, SignatureExpired, KeyError, TypeError, RuntimeError):
        return None


def check_session_secret_configured() -> Tuple[bool, Optional[str]]:
    """Check if session secret is properly configured.

    Used in preflight checks to fail fast if not configured.

    Returns:
        Tuple of (ok, error_message).
    """
    secret = get_session_secret()
    if not secret:
        return False, (
            f"{ENV_SESSION_SECRET} environment variable is required for console browser auth. "
            "Set a secure random string (32+ characters). "
            "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    if len(secret) < 32:
        return False, (
            f"{ENV_SESSION_SECRET} is too short ({len(secret)} chars). "
            "Must be at least 32 characters for security."
        )
    return True, None
