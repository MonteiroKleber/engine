"""Actor tokens registry with append-only JSONL storage and folding state.

Implements per-institution actor token management with:
- Cryptographic token generation (secrets.token_urlsafe)
- SHA256 hashing for secure storage (never store token in clear)
- Append-only JSONL for audit trail
- Folding state computation (never edit, always append)

GAP 2: Minimum Identity Not Spoofable
GAP 4: Adds is_agent flag for governed agent actors
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
from engine.core.errors import (
    ACTOR_TOKEN_INVALID,
    ACTOR_TOKEN_REVOKED,
    ACTOR_TOKEN_NOT_FOUND,
)


# File names for actor tokens registry
ACTOR_TOKENS_REGISTRY_FILE = "actors_registry.jsonl"
ACTOR_TOKENS_STATE_FILE = "actors_state.json"
ACTORS_DIR = "actors"

# Hash prefix for stored tokens
HASH_PREFIX = "SHA256:"


@dataclass
class ActorTokenRecord:
    """Record for actor token operations (append-only log entry)."""

    token_sha256: str  # "SHA256:<hex>" format
    actor_id: str  # UUID of the actor
    roles: List[str]  # Roles assigned to this actor
    status: str  # "active", "revoked"
    operation: str  # "create", "revoke"
    created_at: str  # ISO 8601 timestamp
    created_by: Optional[str] = None  # Admin key ID that created this token
    is_agent: bool = False  # GAP 4: True if this actor is a governed agent

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "ActorTokenRecord":
        """Create from dictionary."""
        return cls(
            token_sha256=data["token_sha256"],
            actor_id=data["actor_id"],
            roles=data.get("roles", []),
            status=data["status"],
            operation=data.get("operation", "create"),
            created_at=data["created_at"],
            created_by=data.get("created_by"),
            is_agent=data.get("is_agent", False),
        )


@dataclass
class ActorTokenState:
    """Computed state of a single actor token (folded from records)."""

    token_sha256: str
    actor_id: str
    roles: List[str]
    status: str  # "active", "revoked"
    created_at: str
    created_by: Optional[str]
    is_agent: bool = False  # GAP 4: True if this actor is a governed agent

    def is_valid(self) -> bool:
        """Check if token is currently valid (active)."""
        return self.status == "active"


def _hash_token(plaintext_token: str) -> str:
    """Hash a plaintext token using SHA256.

    Args:
        plaintext_token: The plaintext token to hash.

    Returns:
        Hash string in "SHA256:<hex>" format.
    """
    hash_bytes = hashlib.sha256(plaintext_token.encode("utf-8")).hexdigest()
    return f"{HASH_PREFIX}{hash_bytes}"


def _generate_token() -> str:
    """Generate a cryptographically secure token.

    Returns:
        URL-safe base64 encoded token (43 characters).
    """
    return secrets.token_urlsafe(32)


def _now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ActorTokensRegistry:
    """Registry for per-institution actor tokens with append-only storage."""

    _instance: Optional["ActorTokensRegistry"] = None
    _lock: Lock = Lock()

    def __init__(self):
        """Initialize registry."""
        self._file_locks: Dict[str, Lock] = {}
        self._global_lock = Lock()

    @classmethod
    def get_instance(cls) -> "ActorTokensRegistry":
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

    def _get_actors_dir(self, institution_id: str) -> Path:
        """Get path to actors directory for institution."""
        institution_root = get_institution_root(institution_id)
        return institution_root / ACTORS_DIR

    def _get_registry_path(self, institution_id: str) -> Path:
        """Get path to actor tokens registry file for institution."""
        return self._get_actors_dir(institution_id) / ACTOR_TOKENS_REGISTRY_FILE

    def _get_state_path(self, institution_id: str) -> Path:
        """Get path to actor tokens state file for institution."""
        return self._get_actors_dir(institution_id) / ACTOR_TOKENS_STATE_FILE

    def _ensure_actors_dir(self, institution_id: str) -> Path:
        """Ensure actors directory exists."""
        actors_dir = self._get_actors_dir(institution_id)
        actors_dir.mkdir(parents=True, exist_ok=True)
        return actors_dir

    def _append_record(self, institution_id: str, record: ActorTokenRecord) -> bool:
        """Append a record to the registry file.

        Args:
            institution_id: Institution UUID.
            record: Record to append.

        Returns:
            True if successful.
        """
        lock = self._get_file_lock(institution_id)
        with lock:
            try:
                self._ensure_actors_dir(institution_id)
                registry_path = self._get_registry_path(institution_id)

                with open(registry_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record.to_dict()) + "\n")

                # Recompute state after append
                self._recompute_state(institution_id)
                return True
            except Exception:
                return False

    def _load_records(self, institution_id: str) -> List[ActorTokenRecord]:
        """Load all records from registry file.

        Args:
            institution_id: Institution UUID.

        Returns:
            List of records (oldest first).
        """
        registry_path = self._get_registry_path(institution_id)
        if not registry_path.exists():
            return []

        records = []
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        records.append(ActorTokenRecord.from_dict(data))
        except Exception:
            pass

        return records

    def _recompute_state(self, institution_id: str) -> Dict[str, ActorTokenState]:
        """Recompute state by folding all records.

        Args:
            institution_id: Institution UUID.

        Returns:
            Dict mapping token_sha256 to ActorTokenState.
        """
        records = self._load_records(institution_id)

        # Fold records into state
        state: Dict[str, ActorTokenState] = {}

        for record in records:
            token_sha256 = record.token_sha256

            if record.operation == "create":
                state[token_sha256] = ActorTokenState(
                    token_sha256=token_sha256,
                    actor_id=record.actor_id,
                    roles=record.roles,
                    status=record.status,
                    created_at=record.created_at,
                    created_by=record.created_by,
                    is_agent=record.is_agent,
                )
            elif record.operation == "revoke":
                if token_sha256 in state:
                    state[token_sha256].status = "revoked"

        # Write state file
        state_path = self._get_state_path(institution_id)
        try:
            state_dict = {k: asdict(v) for k, v in state.items()}
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state_dict, f, indent=2)
        except Exception:
            pass

        return state

    def _load_state(self, institution_id: str) -> Dict[str, ActorTokenState]:
        """Load state from state file (or recompute if missing).

        Args:
            institution_id: Institution UUID.

        Returns:
            Dict mapping token_sha256 to ActorTokenState.
        """
        state_path = self._get_state_path(institution_id)

        if not state_path.exists():
            return self._recompute_state(institution_id)

        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_dict = json.load(f)

            return {
                k: ActorTokenState(
                    token_sha256=v["token_sha256"],
                    actor_id=v["actor_id"],
                    roles=v.get("roles", []),
                    status=v["status"],
                    created_at=v["created_at"],
                    created_by=v.get("created_by"),
                    is_agent=v.get("is_agent", False),
                )
                for k, v in state_dict.items()
            }
        except Exception:
            return self._recompute_state(institution_id)

    def create_token(
        self,
        institution_id: str,
        actor_id: str,
        roles: List[str],
        created_by: Optional[str] = None,
        is_agent: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Create a new actor token.

        Args:
            institution_id: Institution UUID.
            actor_id: Actor UUID.
            roles: List of roles to assign.
            created_by: Admin key ID that created this token.
            is_agent: GAP 4 - True if this actor is a governed agent.

        Returns:
            Tuple of (plaintext_token, error_code).
            If successful, error_code is None.
        """
        # Generate token
        plaintext_token = _generate_token()
        token_sha256 = _hash_token(plaintext_token)

        # Create record
        record = ActorTokenRecord(
            token_sha256=token_sha256,
            actor_id=actor_id,
            roles=roles,
            status="active",
            operation="create",
            created_at=_now_iso(),
            created_by=created_by,
            is_agent=is_agent,
        )

        # Append to registry
        if self._append_record(institution_id, record):
            return plaintext_token, None
        else:
            return None, "ACTOR_TOKENS_REGISTRY_UNAVAILABLE"

    def revoke_token(
        self,
        institution_id: str,
        token_sha256: str,
        revoked_by: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Revoke an actor token by its hash.

        Args:
            institution_id: Institution UUID.
            token_sha256: SHA256 hash of the token (with prefix).
            revoked_by: Admin key ID that revoked this token.

        Returns:
            Tuple of (success, error_code).
        """
        # Check if token exists
        state = self._load_state(institution_id)
        if token_sha256 not in state:
            return False, ACTOR_TOKEN_NOT_FOUND

        token_state = state[token_sha256]
        if token_state.status == "revoked":
            return False, ACTOR_TOKEN_REVOKED

        # Create revoke record
        record = ActorTokenRecord(
            token_sha256=token_sha256,
            actor_id=token_state.actor_id,
            roles=token_state.roles,
            status="revoked",
            operation="revoke",
            created_at=_now_iso(),
            created_by=revoked_by,
        )

        # Append to registry
        if self._append_record(institution_id, record):
            return True, None
        else:
            return False, "ACTOR_TOKENS_REGISTRY_UNAVAILABLE"

    def verify_token(
        self,
        institution_id: str,
        plaintext_token: str,
    ) -> Tuple[Optional[str], Optional[List[str]], bool, Optional[str], bool]:
        """Verify a plaintext token and return actor info.

        Args:
            institution_id: Institution UUID.
            plaintext_token: Plaintext token from header.

        Returns:
            Tuple of (actor_id, roles, valid, error_code, is_agent).
            If valid, error_code is None.
            GAP 4: is_agent indicates if this actor is a governed agent.
        """
        token_sha256 = _hash_token(plaintext_token)
        state = self._load_state(institution_id)

        if token_sha256 not in state:
            return None, None, False, ACTOR_TOKEN_INVALID, False

        token_state = state[token_sha256]

        if token_state.status == "revoked":
            return token_state.actor_id, token_state.roles, False, ACTOR_TOKEN_REVOKED, token_state.is_agent

        return token_state.actor_id, token_state.roles, True, None, token_state.is_agent

    def list_actors(self, institution_id: str) -> List[ActorTokenState]:
        """List all actor tokens for an institution.

        Args:
            institution_id: Institution UUID.

        Returns:
            List of ActorTokenState objects.
        """
        state = self._load_state(institution_id)
        return list(state.values())

    def get_actor_by_id(
        self,
        institution_id: str,
        actor_id: str,
    ) -> List[ActorTokenState]:
        """Get all tokens for a specific actor.

        Args:
            institution_id: Institution UUID.
            actor_id: Actor UUID.

        Returns:
            List of ActorTokenState objects for this actor.
        """
        state = self._load_state(institution_id)
        return [s for s in state.values() if s.actor_id == actor_id]


def get_actor_tokens_registry() -> ActorTokensRegistry:
    """Get the singleton actor tokens registry instance."""
    return ActorTokensRegistry.get_instance()
