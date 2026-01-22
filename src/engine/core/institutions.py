"""Institution Identity + Registry (append-only)."""

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.core.errors import (
    INSTITUTION_SLUG_INVALID,
    INSTITUTION_SLUG_TAKEN,
    INSTITUTION_NOT_FOUND,
    INSTITUTION_ID_INVALID,
    INSTITUTIONS_REGISTRY_UNAVAILABLE,
    INSTITUTION_META_UNAVAILABLE,
    INSTITUTION_SECURE_CONFIG_REQUIRED,
)
from engine.core.ledger import get_ledger
from engine.core.actor_context import DEFAULT_TENANT_ID


# Default paths
DEFAULT_REGISTRY_PATH = "var/institutions_registry.jsonl"
DEFAULT_INSTITUTIONS_DIR = "var/institutions"

# Slug validation regex: lowercase, numbers, hyphen; 3-63 chars; no start/end hyphen
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$|^[a-z0-9]{3}$")

# Institution schema version
INSTITUTION_SCHEMA_VERSION = "1.0"


@dataclass
class Institution:
    """Institution metadata."""

    institution_id: str
    slug: str
    display_name: Optional[str]
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API/storage."""
        return {
            "schema_version": INSTITUTION_SCHEMA_VERSION,
            "institution_id": self.institution_id,
            "slug": self.slug,
            "display_name": self.display_name,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Institution":
        """Create from dict."""
        return cls(
            institution_id=d.get("institution_id", ""),
            slug=d.get("slug", ""),
            display_name=d.get("display_name"),
            created_at=d.get("created_at", ""),
        )


@dataclass
class RegistryEntry:
    """Registry entry for append-only JSONL."""

    institution_id: str
    slug: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "institution_id": self.institution_id,
            "slug": self.slug,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RegistryEntry":
        """Create from dict."""
        return cls(
            institution_id=d.get("institution_id", ""),
            slug=d.get("slug", ""),
            created_at=d.get("created_at", ""),
        )


def get_registry_path() -> Path:
    """Get registry JSONL path from ENV or default."""
    env_path = os.environ.get("ENGINE_INSTITUTIONS_REGISTRY_PATH")
    if env_path:
        return Path(env_path)
    return Path(DEFAULT_REGISTRY_PATH)


def get_institutions_dir() -> Path:
    """Get institutions base directory from ENV or default."""
    env_dir = os.environ.get("ENGINE_INSTITUTIONS_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(DEFAULT_INSTITUTIONS_DIR)


def validate_slug(slug: str) -> tuple[bool, Optional[str]]:
    """Validate institution slug.

    Slug rules:
    - regex: ^[a-z0-9][a-z0-9-]{2,62}$
    - lowercase only, numbers, hyphen
    - min length 3, max length 63
    - cannot start/end with hyphen

    Args:
        slug: The slug to validate.

    Returns:
        (True, None) if valid, (False, error_message) if invalid.
    """
    if not slug:
        return False, "Slug cannot be empty"

    if len(slug) < 3:
        return False, "Slug must be at least 3 characters"

    if len(slug) > 63:
        return False, "Slug must be at most 63 characters"

    if slug.startswith("-"):
        return False, "Slug cannot start with hyphen"

    if slug.endswith("-"):
        return False, "Slug cannot end with hyphen"

    if not SLUG_PATTERN.match(slug):
        return False, "Slug must be lowercase alphanumeric with hyphens only"

    return True, None


def validate_uuid(value: str) -> bool:
    """Validate UUID format."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


class InstitutionsRegistry:
    """Append-only institutions registry."""

    def __init__(
        self,
        registry_path: Optional[Path] = None,
        institutions_dir: Optional[Path] = None,
    ) -> None:
        """Initialize registry.

        Args:
            registry_path: Path to JSONL registry file.
            institutions_dir: Base directory for institution metadata files.
        """
        self._registry_path = registry_path or get_registry_path()
        self._institutions_dir = institutions_dir or get_institutions_dir()
        self._lock = threading.Lock()

        # In-memory index (rebuilt from registry on init)
        self._by_slug: Dict[str, RegistryEntry] = {}
        self._by_id: Dict[str, RegistryEntry] = {}
        self._entries_ordered: List[RegistryEntry] = []

        self._load_registry()

    def _load_registry(self) -> None:
        """Load registry from JSONL file."""
        if not self._registry_path.exists():
            return

        try:
            with open(self._registry_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        entry = RegistryEntry.from_dict(d)
                        self._by_slug[entry.slug] = entry
                        self._by_id[entry.institution_id] = entry
                        self._entries_ordered.append(entry)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            pass

    def _append_to_registry(self, entry: RegistryEntry) -> bool:
        """Append entry to registry JSONL (append-only).

        Args:
            entry: Registry entry to append.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Ensure parent directory exists
            self._registry_path.parent.mkdir(parents=True, exist_ok=True)

            # Append to file
            with open(self._registry_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), separators=(",", ":")) + "\n")

            return True
        except Exception:
            return False

    def _save_institution_meta(self, institution: Institution) -> bool:
        """Save institution.json metadata file.

        Args:
            institution: Institution metadata.

        Returns:
            True if successful, False otherwise.
        """
        try:
            inst_dir = self._institutions_dir / institution.institution_id
            inst_dir.mkdir(parents=True, exist_ok=True)

            meta_path = inst_dir / "institution.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(institution.to_dict(), f, indent=2)

            return True
        except Exception:
            return False

    def _load_institution_meta(self, institution_id: str) -> Optional[Institution]:
        """Load institution.json metadata file.

        Args:
            institution_id: Institution UUID.

        Returns:
            Institution if found and valid, None otherwise.
        """
        try:
            meta_path = self._institutions_dir / institution_id / "institution.json"
            if not meta_path.exists():
                return None

            with open(meta_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                return Institution.from_dict(d)
        except Exception:
            return None

    def slug_exists(self, slug: str) -> bool:
        """Check if slug already exists."""
        with self._lock:
            return slug in self._by_slug

    def id_exists(self, institution_id: str) -> bool:
        """Check if institution_id already exists."""
        with self._lock:
            return institution_id in self._by_id

    def create(
        self,
        slug: str,
        display_name: Optional[str] = None,
    ) -> tuple[Optional[Institution], Optional[str], Optional[str]]:
        """Create a new institution.

        GAP 5: In ENGINE_INSTALL_MODE=prod, automatically creates
        config/ACTIVE.json with secure defaults. Fails if config cannot
        be created (GAP 5.3 - non-silent prod).

        Args:
            slug: Unique slug for the institution.
            display_name: Optional display name.

        Returns:
            (Institution, None, None) on success.
            (None, error_code, error_message) on failure.
        """
        # Validate slug
        valid, err_msg = validate_slug(slug)
        if not valid:
            return None, INSTITUTION_SLUG_INVALID, err_msg

        with self._lock:
            # Check slug uniqueness
            if slug in self._by_slug:
                return None, INSTITUTION_SLUG_TAKEN, f"Slug '{slug}' already exists"

            # Generate UUID and timestamp
            institution_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()

            # Create registry entry
            entry = RegistryEntry(
                institution_id=institution_id,
                slug=slug,
                created_at=created_at,
            )

            # Append to registry (append-only)
            if not self._append_to_registry(entry):
                return None, INSTITUTIONS_REGISTRY_UNAVAILABLE, "Failed to write to registry"

            # Update in-memory index
            self._by_slug[slug] = entry
            self._by_id[institution_id] = entry
            self._entries_ordered.append(entry)

            # Create institution metadata
            institution = Institution(
                institution_id=institution_id,
                slug=slug,
                display_name=display_name,
                created_at=created_at,
            )

            # Save metadata file
            if not self._save_institution_meta(institution):
                return None, INSTITUTION_META_UNAVAILABLE, "Failed to save institution metadata"

            # GAP 5/5.3: Create secure config in production mode (mandatory)
            ok, error_code, error_message = self._create_secure_config_if_prod(institution_id)
            if not ok:
                # In prod mode, secure config is required - fail creation
                return None, error_code, error_message

            # Emit ledger event
            self._emit_created_event(institution)

            return institution, None, None

    def _create_secure_config_if_prod(
        self, institution_id: str
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Create secure config for institution if in production mode.

        GAP 5: In ENGINE_INSTALL_MODE=prod, new institutions must start
        with secure defaults (require_institution_header_for_runtime=True,
        allow_legacy_routes=False, enable_contracts_stub=False).

        GAP 5.3: In prod mode, failure to create secure config is a hard
        error that fails institution creation (non-silent).
        In dev mode, failure is logged but does not fail creation.

        Args:
            institution_id: Institution UUID.

        Returns:
            (True, None, None) on success or dev mode.
            (False, error_code, error_message) on prod mode failure.
        """
        from engine.core.install_mode import is_prod_mode

        prod_mode = is_prod_mode()

        if not prod_mode:
            return True, None, None  # Dev mode - skip secure config creation

        try:
            from engine.core.institution_config import create_secure_config_for_institution

            config, error_code, error_message = create_secure_config_for_institution(
                institution_id=institution_id,
                updated_by="system:secure_defaults",
            )

            if error_code:
                # GAP 5.3: In prod mode, this is a hard failure
                return (
                    False,
                    INSTITUTION_SECURE_CONFIG_REQUIRED,
                    f"Production mode requires secure config creation. "
                    f"Failed: [{error_code}] {error_message}",
                )

            return True, None, None

        except Exception as e:
            # GAP 5.3: In prod mode, exceptions are hard failures
            import logging
            logging.getLogger(__name__).error(
                "Exception creating secure config for institution %s: %s",
                institution_id,
                str(e),
            )
            return (
                False,
                INSTITUTION_SECURE_CONFIG_REQUIRED,
                f"Production mode requires secure config creation. "
                f"Exception: {str(e)}",
            )

    def get_by_slug(self, slug: str) -> tuple[Optional[Institution], Optional[str], Optional[str]]:
        """Get institution by slug.

        Args:
            slug: Institution slug.

        Returns:
            (Institution, None, None) on success.
            (None, error_code, error_message) on failure.
        """
        with self._lock:
            entry = self._by_slug.get(slug)
            if not entry:
                return None, INSTITUTION_NOT_FOUND, f"Institution with slug '{slug}' not found"

            institution = self._load_institution_meta(entry.institution_id)
            if not institution:
                return None, INSTITUTION_META_UNAVAILABLE, "Failed to load institution metadata"

            return institution, None, None

    def get_by_id(self, institution_id: str) -> tuple[Optional[Institution], Optional[str], Optional[str]]:
        """Get institution by ID.

        Args:
            institution_id: Institution UUID.

        Returns:
            (Institution, None, None) on success.
            (None, error_code, error_message) on failure.
        """
        # Validate UUID format
        if not validate_uuid(institution_id):
            return None, INSTITUTION_ID_INVALID, "Invalid institution ID format"

        with self._lock:
            entry = self._by_id.get(institution_id)
            if not entry:
                return None, INSTITUTION_NOT_FOUND, f"Institution with ID '{institution_id}' not found"

            institution = self._load_institution_meta(entry.institution_id)
            if not institution:
                return None, INSTITUTION_META_UNAVAILABLE, "Failed to load institution metadata"

            return institution, None, None

    def list_institutions(self, limit: int = 50) -> List[Institution]:
        """List institutions in creation order.

        Args:
            limit: Maximum number of institutions to return.

        Returns:
            List of institutions (newest last, creation order).
        """
        with self._lock:
            # Get last N entries in creation order
            entries = self._entries_ordered[-limit:] if limit else self._entries_ordered

            institutions = []
            for entry in entries:
                inst = self._load_institution_meta(entry.institution_id)
                if inst:
                    institutions.append(inst)

            return institutions

    def _emit_created_event(self, institution: Institution) -> None:
        """Emit INSTITUTION_CREATED ledger event.

        Args:
            institution: The created institution.
        """
        ledger = get_ledger()
        if ledger:
            ledger.append(
                event_type="INSTITUTION_CREATED",
                tenant_id=DEFAULT_TENANT_ID,
                actor_id="system",
                actor_roles=["admin"],
                case_id=institution.institution_id,
                step="ADMIN:institution.create",
                payload={
                    "slug": institution.slug,
                    "display_name": institution.display_name,
                },
            )


# Global registry instance
_registry: Optional[InstitutionsRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> InstitutionsRegistry:
    """Get or create global registry instance."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = InstitutionsRegistry()
        return _registry


def reset_registry() -> None:
    """Reset global registry (for testing)."""
    global _registry
    with _registry_lock:
        _registry = None
