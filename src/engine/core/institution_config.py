"""Institution configuration management."""

import hashlib
import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.core.data_root import get_institution_root
from engine.core.errors import (
    INSTITUTION_CONFIG_INVALID,
    INSTITUTION_CONFIG_UNAVAILABLE,
    INSTITUTION_CONFIG_HISTORY_UNAVAILABLE,
)


# Config schema version
CONFIG_SCHEMA_VERSION = "1.4"

# Dept ID regex pattern
DEPT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# SHA256 hash pattern (with or without prefix)
HASH_PREFIX = "SHA256:"
HASH_HEX_LENGTH = 64  # 256 bits = 64 hex chars
HASH_HEX_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


def _get_default_rate_limit() -> int:
    """Get default rate limit from ENV or fallback."""
    try:
        return int(os.environ.get("ENGINE_RATE_LIMIT_PER_MINUTE", "100"))
    except (ValueError, TypeError):
        return 100


def _get_default_max_body_bytes() -> int:
    """Get default max body bytes from ENV or fallback."""
    try:
        return int(os.environ.get("ENGINE_MAX_BODY_BYTES", "262144"))
    except (ValueError, TypeError):
        return 262144


@dataclass
class ConfigFlags:
    """Configuration flags.

    Note: Default values are permissive (dev-friendly).
    Use get_secure_config_flags() for production defaults.
    """

    require_institution_header_for_runtime: bool = False
    allow_legacy_routes: bool = True
    enable_contracts_stub: bool = True


def get_secure_config_flags() -> ConfigFlags:
    """Get secure configuration flags for production mode.

    GAP 5: Production mode should use secure defaults:
    - require_institution_header_for_runtime=True (multi-tenant isolation)
    - allow_legacy_routes=False (prevent legacy route bypass)
    - enable_contracts_stub=False (require real contract verification)

    Returns:
        ConfigFlags with secure production defaults.
    """
    return ConfigFlags(
        require_institution_header_for_runtime=True,
        allow_legacy_routes=False,
        enable_contracts_stub=False,
    )


@dataclass
class ConfigLimits:
    """Configuration limits."""

    rate_limit_per_minute: int = field(default_factory=_get_default_rate_limit)
    max_body_bytes: int = field(default_factory=_get_default_max_body_bytes)


@dataclass
class ConfigDefaults:
    """Configuration defaults."""

    default_dept: str = "finance"
    default_bundle_name: str = "finance-pilot"


@dataclass
class EmergencyStopConfig:
    """Emergency stop configuration."""

    enabled: bool = False
    blocked_endpoints: List[str] = field(default_factory=list)


@dataclass
class InstitutionConfig:
    """Institution configuration."""

    schema_version: str = CONFIG_SCHEMA_VERSION
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    flags: ConfigFlags = field(default_factory=ConfigFlags)
    limits: ConfigLimits = field(default_factory=ConfigLimits)
    defaults: ConfigDefaults = field(default_factory=ConfigDefaults)
    freeze_mode: bool = False
    emergency_stop: EmergencyStopConfig = field(default_factory=EmergencyStopConfig)
    # EGE v1.2 fields
    pinned_bundle_manifest_sha256: Optional[str] = None
    pinned_contract_ledger_sha256: Optional[str] = None
    ege_enforce_drift: bool = True
    # EGE v1.3 fields - Pin on Deploy
    auto_propose_pin_on_deploy: bool = True
    auto_accept_pin_on_deploy: bool = False
    # EGE v1.4 fields - Governed Rollback (Etapa 2.4)
    pinned_release_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
            "flags": asdict(self.flags),
            "limits": asdict(self.limits),
            "defaults": asdict(self.defaults),
            "freeze_mode": self.freeze_mode,
            "emergency_stop": asdict(self.emergency_stop),
            "pinned_bundle_manifest_sha256": self.pinned_bundle_manifest_sha256,
            "pinned_contract_ledger_sha256": self.pinned_contract_ledger_sha256,
            "ege_enforce_drift": self.ege_enforce_drift,
            "auto_propose_pin_on_deploy": self.auto_propose_pin_on_deploy,
            "auto_accept_pin_on_deploy": self.auto_accept_pin_on_deploy,
            "pinned_release_id": self.pinned_release_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstitutionConfig":
        """Create config from dictionary."""
        flags_data = data.get("flags", {})
        limits_data = data.get("limits", {})
        defaults_data = data.get("defaults", {})
        emergency_stop_data = data.get("emergency_stop", {})

        # Build flags with defaults
        flags = ConfigFlags(
            require_institution_header_for_runtime=flags_data.get("require_institution_header_for_runtime", False),
            allow_legacy_routes=flags_data.get("allow_legacy_routes", True),
            enable_contracts_stub=flags_data.get("enable_contracts_stub", True),
        )

        # Build limits with defaults
        limits = ConfigLimits(
            rate_limit_per_minute=limits_data.get("rate_limit_per_minute", _get_default_rate_limit()),
            max_body_bytes=limits_data.get("max_body_bytes", _get_default_max_body_bytes()),
        )

        # Build defaults with defaults
        defaults = ConfigDefaults(
            default_dept=defaults_data.get("default_dept", "finance"),
            default_bundle_name=defaults_data.get("default_bundle_name", "finance-pilot"),
        )

        # Build emergency_stop with defaults
        emergency_stop = EmergencyStopConfig(
            enabled=emergency_stop_data.get("enabled", False),
            blocked_endpoints=emergency_stop_data.get("blocked_endpoints", []),
        )

        return cls(
            schema_version=data.get("schema_version", CONFIG_SCHEMA_VERSION),
            updated_at=data.get("updated_at"),
            updated_by=data.get("updated_by"),
            flags=flags,
            limits=limits,
            defaults=defaults,
            freeze_mode=data.get("freeze_mode", False),
            emergency_stop=emergency_stop,
            # EGE v1.2 fields with backward-compatible defaults
            pinned_bundle_manifest_sha256=data.get("pinned_bundle_manifest_sha256"),
            pinned_contract_ledger_sha256=data.get("pinned_contract_ledger_sha256"),
            ege_enforce_drift=data.get("ege_enforce_drift", True),
            # EGE v1.3 fields with backward-compatible defaults
            auto_propose_pin_on_deploy=data.get("auto_propose_pin_on_deploy", True),
            auto_accept_pin_on_deploy=data.get("auto_accept_pin_on_deploy", False),
            # EGE v1.4 fields with backward-compatible defaults
            pinned_release_id=data.get("pinned_release_id"),
        )


def get_config_dir(institution_id: str) -> Path:
    """Get config directory for institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to config directory: <institution_root>/config/
    """
    return get_institution_root(institution_id) / "config"


def get_active_config_path(institution_id: str) -> Path:
    """Get path to active config file.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to ACTIVE.json file.
    """
    return get_config_dir(institution_id) / "ACTIVE.json"


def get_history_path(institution_id: str) -> Path:
    """Get path to config history file.

    Args:
        institution_id: Institution UUID.

    Returns:
        Path to history.jsonl file.
    """
    return get_config_dir(institution_id) / "history.jsonl"


def _get_next_seq(institution_id: str) -> int:
    """Get next sequence number for history entry.

    Args:
        institution_id: Institution UUID.

    Returns:
        Next sequence number (starting at 1).
    """
    history_path = get_history_path(institution_id)
    if not history_path.exists():
        return 1

    try:
        count = 0
        with open(history_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count + 1
    except OSError:
        return 1


def _normalize_hash(value: str) -> str:
    """Normalize hash value to canonical format.

    Accepts either "SHA256:<hex>" or "<hex>" format.
    Returns "SHA256:<hex>" format.

    Args:
        value: Hash string.

    Returns:
        Normalized hash string.
    """
    if value.startswith(HASH_PREFIX):
        return value
    return f"{HASH_PREFIX}{value}"


def _validate_hash_format(value: str, field_name: str) -> Tuple[bool, Optional[str]]:
    """Validate hash format.

    Args:
        value: Hash string to validate.
        field_name: Field name for error message.

    Returns:
        Tuple of (is_valid, error_message).
    """
    # Strip prefix if present
    hex_part = value
    if value.startswith(HASH_PREFIX):
        hex_part = value[len(HASH_PREFIX):]

    if not HASH_HEX_PATTERN.match(hex_part):
        return False, f"{field_name} must be 'SHA256:<64 hex chars>' or '<64 hex chars>'"

    return True, None


def _validate_config(config_dict: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate config dictionary against schema.

    Args:
        config_dict: Config dictionary to validate.

    Returns:
        Tuple of (is_valid, error_code, error_message).
    """
    # Check top-level fields
    allowed_top_level = {
        "schema_version", "updated_at", "updated_by", "flags", "limits",
        "defaults", "freeze_mode", "emergency_stop",
        # EGE v1.2 fields
        "pinned_bundle_manifest_sha256", "pinned_contract_ledger_sha256", "ege_enforce_drift",
        # EGE v1.3 fields
        "auto_propose_pin_on_deploy", "auto_accept_pin_on_deploy",
        # EGE v1.4 fields
        "pinned_release_id",
    }
    for key in config_dict:
        if key not in allowed_top_level:
            return False, INSTITUTION_CONFIG_INVALID, f"Unknown top-level field: {key}"

    # Validate schema_version (accept 1.0, 1.1, 1.2, 1.3, or 1.4)
    if "schema_version" in config_dict and config_dict["schema_version"] not in ("1.0", "1.1", "1.2", "1.3", "1.4"):
        return False, INSTITUTION_CONFIG_INVALID, "schema_version must be '1.0', '1.1', '1.2', '1.3', or '1.4'"

    # Validate flags
    if "flags" in config_dict:
        flags = config_dict["flags"]
        if not isinstance(flags, dict):
            return False, INSTITUTION_CONFIG_INVALID, "flags must be an object"
        allowed_flags = {"require_institution_header_for_runtime", "allow_legacy_routes", "enable_contracts_stub"}
        for key in flags:
            if key not in allowed_flags:
                return False, INSTITUTION_CONFIG_INVALID, f"Unknown flag: {key}"
        # Type validation - must be exactly 3 keys if flags is provided
        for key in allowed_flags:
            if key in flags and not isinstance(flags[key], bool):
                return False, INSTITUTION_CONFIG_INVALID, f"flags.{key} must be a boolean"

    # Validate limits
    if "limits" in config_dict:
        limits = config_dict["limits"]
        if not isinstance(limits, dict):
            return False, INSTITUTION_CONFIG_INVALID, "limits must be an object"
        allowed_limits = {"rate_limit_per_minute", "max_body_bytes"}
        for key in limits:
            if key not in allowed_limits:
                return False, INSTITUTION_CONFIG_INVALID, f"Unknown limit: {key}"

        # Validate rate_limit_per_minute
        if "rate_limit_per_minute" in limits:
            rate = limits["rate_limit_per_minute"]
            if not isinstance(rate, int):
                return False, INSTITUTION_CONFIG_INVALID, "limits.rate_limit_per_minute must be an integer"
            if rate < 1 or rate > 100000:
                return False, INSTITUTION_CONFIG_INVALID, "limits.rate_limit_per_minute must be between 1 and 100000"

        # Validate max_body_bytes
        if "max_body_bytes" in limits:
            max_bytes = limits["max_body_bytes"]
            if not isinstance(max_bytes, int):
                return False, INSTITUTION_CONFIG_INVALID, "limits.max_body_bytes must be an integer"
            if max_bytes < 1024:
                return False, INSTITUTION_CONFIG_INVALID, "limits.max_body_bytes must be >= 1024"

    # Validate defaults
    if "defaults" in config_dict:
        defaults = config_dict["defaults"]
        if not isinstance(defaults, dict):
            return False, INSTITUTION_CONFIG_INVALID, "defaults must be an object"
        allowed_defaults = {"default_dept", "default_bundle_name"}
        for key in defaults:
            if key not in allowed_defaults:
                return False, INSTITUTION_CONFIG_INVALID, f"Unknown default: {key}"

        # Validate default_dept
        if "default_dept" in defaults:
            dept = defaults["default_dept"]
            if not isinstance(dept, str):
                return False, INSTITUTION_CONFIG_INVALID, "defaults.default_dept must be a string"
            if not DEPT_ID_PATTERN.match(dept):
                return False, INSTITUTION_CONFIG_INVALID, "defaults.default_dept must match pattern [a-zA-Z0-9_-]+"

        # Validate default_bundle_name
        if "default_bundle_name" in defaults:
            bundle_name = defaults["default_bundle_name"]
            if not isinstance(bundle_name, str):
                return False, INSTITUTION_CONFIG_INVALID, "defaults.default_bundle_name must be a string"
            if len(bundle_name) < 1 or len(bundle_name) > 64:
                return False, INSTITUTION_CONFIG_INVALID, "defaults.default_bundle_name must have length 1..64"

    # Validate freeze_mode (v1.1)
    if "freeze_mode" in config_dict:
        if not isinstance(config_dict["freeze_mode"], bool):
            return False, INSTITUTION_CONFIG_INVALID, "freeze_mode must be a boolean"

    # Validate emergency_stop (v1.1)
    if "emergency_stop" in config_dict:
        es = config_dict["emergency_stop"]
        if not isinstance(es, dict):
            return False, INSTITUTION_CONFIG_INVALID, "emergency_stop must be an object"
        allowed_es_fields = {"enabled", "blocked_endpoints"}
        for key in es:
            if key not in allowed_es_fields:
                return False, INSTITUTION_CONFIG_INVALID, f"Unknown emergency_stop field: {key}"

        # Validate enabled
        if "enabled" in es and not isinstance(es["enabled"], bool):
            return False, INSTITUTION_CONFIG_INVALID, "emergency_stop.enabled must be a boolean"

        # Validate blocked_endpoints
        if "blocked_endpoints" in es:
            endpoints = es["blocked_endpoints"]
            if not isinstance(endpoints, list):
                return False, INSTITUTION_CONFIG_INVALID, "emergency_stop.blocked_endpoints must be an array"

            # Check for duplicates
            if len(endpoints) != len(set(endpoints)):
                return False, INSTITUTION_CONFIG_INVALID, "emergency_stop.blocked_endpoints must not contain duplicates"

            # Validate each endpoint is a string
            for endpoint in endpoints:
                if not isinstance(endpoint, str):
                    return False, INSTITUTION_CONFIG_INVALID, "emergency_stop.blocked_endpoints items must be strings"

    # Validate EGE v1.2 fields
    if "pinned_bundle_manifest_sha256" in config_dict:
        value = config_dict["pinned_bundle_manifest_sha256"]
        if value is not None:
            if not isinstance(value, str):
                return False, INSTITUTION_CONFIG_INVALID, "pinned_bundle_manifest_sha256 must be a string or null"
            is_valid, error_msg = _validate_hash_format(value, "pinned_bundle_manifest_sha256")
            if not is_valid:
                return False, INSTITUTION_CONFIG_INVALID, error_msg

    if "pinned_contract_ledger_sha256" in config_dict:
        value = config_dict["pinned_contract_ledger_sha256"]
        if value is not None:
            if not isinstance(value, str):
                return False, INSTITUTION_CONFIG_INVALID, "pinned_contract_ledger_sha256 must be a string or null"
            is_valid, error_msg = _validate_hash_format(value, "pinned_contract_ledger_sha256")
            if not is_valid:
                return False, INSTITUTION_CONFIG_INVALID, error_msg

    if "ege_enforce_drift" in config_dict:
        if not isinstance(config_dict["ege_enforce_drift"], bool):
            return False, INSTITUTION_CONFIG_INVALID, "ege_enforce_drift must be a boolean"

    # Validate EGE v1.3 fields
    if "auto_propose_pin_on_deploy" in config_dict:
        if not isinstance(config_dict["auto_propose_pin_on_deploy"], bool):
            return False, INSTITUTION_CONFIG_INVALID, "auto_propose_pin_on_deploy must be a boolean"

    if "auto_accept_pin_on_deploy" in config_dict:
        if not isinstance(config_dict["auto_accept_pin_on_deploy"], bool):
            return False, INSTITUTION_CONFIG_INVALID, "auto_accept_pin_on_deploy must be a boolean"

    # Validation rule: if auto_accept_pin_on_deploy is True, auto_propose_pin_on_deploy MUST also be True
    auto_propose = config_dict.get("auto_propose_pin_on_deploy", True)  # default True
    auto_accept = config_dict.get("auto_accept_pin_on_deploy", False)  # default False
    if auto_accept and not auto_propose:
        return False, INSTITUTION_CONFIG_INVALID, "auto_accept_pin_on_deploy requires auto_propose_pin_on_deploy to be True"

    # Validate EGE v1.4 fields
    if "pinned_release_id" in config_dict:
        value = config_dict["pinned_release_id"]
        if value is not None:
            if not isinstance(value, str):
                return False, INSTITUTION_CONFIG_INVALID, "pinned_release_id must be a string or null"
            # Release ID format: YYYYMMDD-HHMMSS
            if len(value) != 15 or value[8] != "-":
                return False, INSTITUTION_CONFIG_INVALID, "pinned_release_id must be in format YYYYMMDD-HHMMSS"

    return True, None, None


def get_effective_config(institution_id: str) -> InstitutionConfig:
    """Get effective config for institution.

    If ACTIVE.json exists and is valid, returns that config.
    Otherwise, returns deterministic defaults.

    Args:
        institution_id: Institution UUID.

    Returns:
        InstitutionConfig instance.
    """
    active_path = get_active_config_path(institution_id)

    if active_path.exists():
        try:
            with open(active_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return InstitutionConfig.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError):
            # Invalid config - return defaults
            pass

    # Return default config
    return InstitutionConfig()


def compute_config_hash(config_bytes: bytes) -> str:
    """Compute SHA256 hash of config bytes.

    Args:
        config_bytes: Config JSON bytes.

    Returns:
        SHA256 hash as hex string.
    """
    return hashlib.sha256(config_bytes).hexdigest()


def save_active_config(
    institution_id: str,
    config_dict: Dict[str, Any],
    updated_by: str,
) -> Tuple[Optional[InstitutionConfig], Optional[str], Optional[str], Optional[str]]:
    """Save active config for institution.

    Validates config, sets metadata, writes ACTIVE.json, appends to history.jsonl.

    Args:
        institution_id: Institution UUID.
        config_dict: Config dictionary to save.
        updated_by: Actor ID who updated the config.

    Returns:
        Tuple of (config, error_code, error_message, config_hash).
        On success: (InstitutionConfig, None, None, hash)
        On failure: (None, error_code, error_message, None)
    """
    # Validate config
    is_valid, error_code, error_message = _validate_config(config_dict)
    if not is_valid:
        return None, error_code, error_message, None

    # Set metadata
    config_dict["schema_version"] = CONFIG_SCHEMA_VERSION
    config_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    config_dict["updated_by"] = updated_by

    # Create config instance
    try:
        config = InstitutionConfig.from_dict(config_dict)
    except (TypeError, KeyError) as e:
        return None, INSTITUTION_CONFIG_INVALID, str(e), None

    # Ensure config directory exists
    config_dir = get_config_dir(institution_id)
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return None, INSTITUTION_CONFIG_UNAVAILABLE, f"Failed to create config directory: {e}", None

    # Write ACTIVE.json
    active_path = get_active_config_path(institution_id)
    config_json_bytes = json.dumps(config.to_dict(), indent=2).encode("utf-8")
    config_hash = compute_config_hash(config_json_bytes)

    try:
        with open(active_path, "wb") as f:
            f.write(config_json_bytes)
    except OSError as e:
        return None, INSTITUTION_CONFIG_UNAVAILABLE, f"Failed to write config: {e}", None

    # Append to history.jsonl with seq
    history_path = get_history_path(institution_id)
    seq = _get_next_seq(institution_id)
    history_entry = config.to_dict()
    history_entry["seq"] = seq

    try:
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(history_entry) + "\n")
    except OSError:
        # History write failure is non-fatal - config is already saved
        pass

    return config, None, None, config_hash


def get_config_history(
    institution_id: str,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], Optional[str]]:
    """Get config history for institution.

    Args:
        institution_id: Institution UUID.

    Returns:
        Tuple of (history_list, error_code, error_message).
        On success: ([config_dicts], None, None)
        On failure: (None, error_code, error_message)
    """
    history_path = get_history_path(institution_id)

    if not history_path.exists():
        return [], None, None

    try:
        history = []
        with open(history_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    history.append(json.loads(line))
        return history, None, None
    except (json.JSONDecodeError, OSError) as e:
        return None, INSTITUTION_CONFIG_HISTORY_UNAVAILABLE, str(e)


# Cache for effective configs
_config_cache: Dict[str, InstitutionConfig] = {}


def get_cached_config(institution_id: str) -> InstitutionConfig:
    """Get effective config with caching.

    Args:
        institution_id: Institution UUID.

    Returns:
        InstitutionConfig instance.
    """
    if institution_id not in _config_cache:
        _config_cache[institution_id] = get_effective_config(institution_id)
    return _config_cache[institution_id]


def invalidate_config_cache(institution_id: str) -> None:
    """Invalidate cached config for institution.

    Args:
        institution_id: Institution UUID.
    """
    _config_cache.pop(institution_id, None)


def reset_config_cache() -> None:
    """Reset entire config cache (for testing)."""
    _config_cache.clear()


def get_secure_defaults_for_prod() -> Dict[str, Any]:
    """Get secure default config for production mode.

    GAP 5: When ENGINE_INSTALL_MODE=prod, new institutions should be
    created with secure defaults rather than permissive dev defaults.

    Secure defaults include:
    - require_institution_header_for_runtime=True (multi-tenant isolation)
    - allow_legacy_routes=False (prevent legacy route bypass)
    - enable_contracts_stub=False (require real contract verification)

    Returns:
        Config dict with secure production defaults.
    """
    secure_flags = get_secure_config_flags()

    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "flags": {
            "require_institution_header_for_runtime": secure_flags.require_institution_header_for_runtime,
            "allow_legacy_routes": secure_flags.allow_legacy_routes,
            "enable_contracts_stub": secure_flags.enable_contracts_stub,
        },
        "limits": {
            "rate_limit_per_minute": _get_default_rate_limit(),
            "max_body_bytes": _get_default_max_body_bytes(),
        },
        "defaults": {
            "default_dept": "finance",
            "default_bundle_name": "finance-pilot",
        },
        "freeze_mode": False,
        "emergency_stop": {
            "enabled": False,
            "blocked_endpoints": [],
        },
    }


def create_secure_config_for_institution(
    institution_id: str,
    updated_by: str = "system:secure_defaults",
) -> Tuple[Optional[InstitutionConfig], Optional[str], Optional[str]]:
    """Create secure config for a new institution in production mode.

    GAP 5: Called when creating institutions in ENGINE_INSTALL_MODE=prod
    to ensure they start with secure defaults.

    Args:
        institution_id: Institution UUID.
        updated_by: Actor ID for audit trail.

    Returns:
        Tuple of (config, error_code, error_message).
        On success: (InstitutionConfig, None, None)
        On failure: (None, error_code, error_message)
    """
    secure_config = get_secure_defaults_for_prod()
    config, error_code, error_message, _ = save_active_config(
        institution_id=institution_id,
        config_dict=secure_config,
        updated_by=updated_by,
    )
    return config, error_code, error_message
