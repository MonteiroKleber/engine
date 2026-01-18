"""Rate limiting with fixed window per minute."""

import os
import threading
from datetime import datetime, timezone
from typing import Dict


def get_rate_limit_per_minute() -> int:
    """Get rate limit from ENGINE_RATE_LIMIT_PER_MINUTE env var."""
    try:
        return int(os.environ.get("ENGINE_RATE_LIMIT_PER_MINUTE", "100"))
    except (ValueError, TypeError):
        return 100


class RateLimiter:
    """In-memory rate limiter with fixed window per minute."""

    def __init__(self, limit_per_minute: int = 100) -> None:
        """Initialize rate limiter.

        Args:
            limit_per_minute: Max requests per minute per IP per path.
        """
        self._limit = limit_per_minute
        self._lock = threading.Lock()
        # Storage: {bucket_key: count}
        # bucket_key = f"{ip}:{path}:{minute_bucket}"
        self._buckets: Dict[str, int] = {}

    def _get_bucket_key(self, ip: str, path: str, now: datetime) -> str:
        """Get bucket key for the current minute."""
        minute_bucket = now.strftime("%Y%m%d%H%M")
        return f"{ip}:{path}:{minute_bucket}"

    def _cleanup_old_buckets(self, current_bucket_suffix: str) -> None:
        """Remove buckets from previous minutes."""
        # Only keep buckets that end with current minute
        keys_to_remove = [
            key for key in self._buckets
            if not key.endswith(f":{current_bucket_suffix}")
        ]
        for key in keys_to_remove:
            del self._buckets[key]

    def check(
        self,
        ip: str,
        path: str,
        limit_override: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Check if request is allowed.

        Args:
            ip: Client IP address.
            path: Request path.
            limit_override: Per-request limit override (uses default if None).
            now: Current time (for testing).

        Returns:
            True if allowed, False if rate limited.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        limit = limit_override if limit_override is not None else self._limit

        bucket_key = self._get_bucket_key(ip, path, now)
        minute_bucket = now.strftime("%Y%m%d%H%M")

        with self._lock:
            # Cleanup old buckets periodically
            self._cleanup_old_buckets(minute_bucket)

            current_count = self._buckets.get(bucket_key, 0)

            if current_count >= limit:
                return False

            # Increment counter
            self._buckets[bucket_key] = current_count + 1
            return True


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(get_rate_limit_per_minute())
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the global rate limiter (for testing)."""
    global _rate_limiter
    _rate_limiter = None
