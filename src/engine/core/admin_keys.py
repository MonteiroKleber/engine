"""Admin keys registry with append-only JSONL storage and folding state.

Implements per-institution admin key management with:
- Cryptographic key generation (secrets.token_urlsafe)
- SHA256 hashing for secure storage
- Append-only JSONL for audit trail
- Folding state computation (never edit, always append)
"""

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from threading import Lock

from engine.core.data_root import get_institution_root


# File name for admin keys registry
ADMIN_KEYS_FILE = "admin_keys.jsonl"

# Hash prefix for stored keys
HASH_PREFIX = "SHA256:"


@dataclass
class AdminKeyRecord:
    """Record for admin key operations (append-only log entry)."""

    key_id: str  # UUID of the key
    key_hash: str  # "SHA256:<hex>" format
    status: str  # "active", "revoked", "expired"
    created_at: str  # ISO 8601 timestamp
    expires_at: Optional[str]  # ISO 8601 timestamp or None for no expiry
    last_used_at: Optional[str]  # ISO 8601 timestamp of last use
    operation: str  # "create", "revoke", "use" - what operation this record represents

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "AdminKeyRecord":
        """Create from dictionary."""
        return cls(
            key_id=data["key_id"],
            key_hash=data["key_hash"],
            status=data["status"],
            created_at=data["created_at"],
            expires_at=data.get("expires_at"),
            last_used_at=data.get("last_used_at"),
            operation=data.get("operation", "create"),  # Default for old records
        )


@dataclass
class AdminKeyState:
    """Computed state of a single admin key (folded from records)."""

    key_id: str
    key_hash: str
    status: str  # "active", "revoked", "expired"
    created_at: str
    expires_at: Optional[str]
    last_used_at: Optional[str]

    def is_valid(self) -> bool:
        """Check if key is currently valid (active and not expired)."""
        if self.status != "active":
            return False

        if self.expires_at:
            try:
                expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if now >= expires:
                    return False
            except (ValueError, TypeError):
                return False

        return True


def _hash_secret(plaintext_secret: str) -> str:
    """Hash a plaintext secret using SHA256.

    Args:
        plaintext_secret: The plaintext secret to hash.

    Returns:
        Hash string in "SHA256:<hex>" format.
    """
    hash_bytes = hashlib.sha256(plaintext_secret.encode("utf-8")).hexdigest()
    return f"{HASH_PREFIX}{hash_bytes}"


def _generate_secret() -> str:
    """Generate a cryptographically secure secret.

    Returns:
        URL-safe base64 encoded secret (43 characters).
    """
    return secrets.token_urlsafe(32)


def _now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AdminKeysRegistry:
    """Registry for per-institution admin keys with append-only storage."""

    _instance: Optional["AdminKeysRegistry"] = None
    _lock: Lock = Lock()

    def __init__(self):
        """Initialize registry."""
        self._file_locks: Dict[str, Lock] = {}
        self._global_lock = Lock()

    @classmethod
    def get_instance(cls) -> "AdminKeysRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None

    def _get_file_lock(self, institution_id: str) -> Lock:
        """Get or create file lock for institution."""
        with self._global_lock:
            if institution_id not in self._file_locks:
                self._file_locks[institution_id] = Lock()
            return self._file_locks[institution_id]

    def _get_keys_path(self, institution_id: str) -> Path:
        """Get path to admin keys file for institution.

        Args:
            institution_id: Institution UUID.

        Returns:
            Path to admin_keys.jsonl file.
        """
        institution_root = get_institution_root(institution_id)
        return institution_root / ADMIN_KEYS_FILE

    def _ensure_institution_dir(self, institution_id: str) -> Path:
        """Ensure institution directory exists.

        Args:
            institution_id: Institution UUID.

        Returns:
            Path to institution directory.
        """
        institution_root = get_institution_root(institution_id)
        institution_root.mkdir(parents=True, exist_ok=True)
        return institution_root

    def load_records(self, institution_id: str) -> List[AdminKeyRecord]:
        """Load all records from institution's admin keys file.

        Args:
            institution_id: Institution UUID.

        Returns:
            List of all AdminKeyRecord entries (chronological order).
        """
        keys_path = self._get_keys_path(institution_id)

        if not keys_path.exists():
            return []

        records = []
        with open(keys_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        records.append(AdminKeyRecord.from_dict(data))
                    except (json.JSONDecodeError, KeyError):
                        # Skip malformed records
                        continue

        return records

    def load_current_state(self, institution_id: str) -> Dict[str, AdminKeyState]:
        """Compute current state by folding all records.

        Args:
            institution_id: Institution UUID.

        Returns:
            Dictionary mapping key_id to current AdminKeyState.
        """
        records = self.load_records(institution_id)

        # Fold records to compute current state
        states: Dict[str, AdminKeyState] = {}

        for record in records:
            key_id = record.key_id

            if record.operation == "create":
                states[key_id] = AdminKeyState(
                    key_id=key_id,
                    key_hash=record.key_hash,
                    status=record.status,
                    created_at=record.created_at,
                    expires_at=record.expires_at,
                    last_used_at=record.last_used_at,
                )
            elif record.operation == "revoke" and key_id in states:
                states[key_id].status = "revoked"
            elif record.operation == "use" and key_id in states:
                states[key_id].last_used_at = record.last_used_at

        # Check for expiry
        now = datetime.now(timezone.utc)
        for state in states.values():
            if state.status == "active" and state.expires_at:
                try:
                    expires = datetime.fromisoformat(state.expires_at.replace("Z", "+00:00"))
                    if now >= expires:
                        state.status = "expired"
                except (ValueError, TypeError):
                    pass

        return states

    def append_record(self, institution_id: str, record: AdminKeyRecord) -> None:
        """Append a record to the institution's admin keys file.

        Args:
            institution_id: Institution UUID.
            record: AdminKeyRecord to append.
        """
        lock = self._get_file_lock(institution_id)

        with lock:
            self._ensure_institution_dir(institution_id)
            keys_path = self._get_keys_path(institution_id)

            with open(keys_path, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")

    def create_key(
        self,
        institution_id: str,
        expires_at: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Create a new admin key for institution.

        Args:
            institution_id: Institution UUID.
            expires_at: Optional ISO 8601 expiry timestamp.

        Returns:
            Tuple of (key_id, plaintext_secret).
            The plaintext_secret is returned ONLY at creation time.
        """
        key_id = str(uuid.uuid4())
        plaintext_secret = _generate_secret()
        key_hash = _hash_secret(plaintext_secret)

        record = AdminKeyRecord(
            key_id=key_id,
            key_hash=key_hash,
            status="active",
            created_at=_now_iso(),
            expires_at=expires_at,
            last_used_at=None,
            operation="create",
        )

        self.append_record(institution_id, record)

        return key_id, plaintext_secret

    def revoke_key(
        self,
        institution_id: str,
        key_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """Revoke an admin key.

        Args:
            institution_id: Institution UUID.
            key_id: Key UUID to revoke.

        Returns:
            Tuple of (success, error_code).
            error_code is None on success.
        """
        states = self.load_current_state(institution_id)

        if key_id not in states:
            return False, "ADMIN_KEY_NOT_FOUND"

        state = states[key_id]

        if state.status == "revoked":
            return False, "ADMIN_KEY_ALREADY_REVOKED"

        # Append revoke record
        record = AdminKeyRecord(
            key_id=key_id,
            key_hash=state.key_hash,
            status="revoked",
            created_at=state.created_at,
            expires_at=state.expires_at,
            last_used_at=state.last_used_at,
            operation="revoke",
        )

        self.append_record(institution_id, record)

        return True, None

    def verify_key(
        self,
        institution_id: str,
        plaintext_secret: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Verify a plaintext secret against stored keys.

        Args:
            institution_id: Institution UUID.
            plaintext_secret: The plaintext secret to verify.

        Returns:
            Tuple of (valid, key_id, error_code).
            - (True, key_id, None) on success
            - (False, key_id, error_code) on failure with known key
            - (False, None, error_code) on failure with unknown key
        """
        candidate_hash = _hash_secret(plaintext_secret)
        states = self.load_current_state(institution_id)

        # Find key by hash
        for key_id, state in states.items():
            if state.key_hash == candidate_hash:
                # Found matching key - check validity
                if state.status == "revoked":
                    return False, key_id, "ADMIN_KEY_REVOKED"
                elif state.status == "expired":
                    return False, key_id, "ADMIN_KEY_EXPIRED"
                elif state.status == "active":
                    if not state.is_valid():
                        return False, key_id, "ADMIN_KEY_EXPIRED"
                    return True, key_id, None
                else:
                    return False, key_id, "ADMIN_KEY_INVALID"

        # No matching key found
        return False, None, "ADMIN_KEY_INVALID"

    def mark_used(self, institution_id: str, key_id: str) -> None:
        """Record that a key was used.

        Args:
            institution_id: Institution UUID.
            key_id: Key UUID that was used.
        """
        states = self.load_current_state(institution_id)

        if key_id not in states:
            return

        state = states[key_id]

        # Append use record
        record = AdminKeyRecord(
            key_id=key_id,
            key_hash=state.key_hash,
            status=state.status,
            created_at=state.created_at,
            expires_at=state.expires_at,
            last_used_at=_now_iso(),
            operation="use",
        )

        self.append_record(institution_id, record)

    def list_keys(self, institution_id: str) -> List[AdminKeyState]:
        """List all keys for institution with current state.

        Args:
            institution_id: Institution UUID.

        Returns:
            List of AdminKeyState for all keys (active, revoked, expired).
        """
        states = self.load_current_state(institution_id)
        return list(states.values())


def get_admin_keys_registry() -> AdminKeysRegistry:
    """Get the admin keys registry singleton.

    Returns:
        AdminKeysRegistry instance.
    """
    return AdminKeysRegistry.get_instance()


def reset_admin_keys_registry() -> None:
    """Reset the admin keys registry (for testing)."""
    AdminKeysRegistry.reset_instance()
