"""Tests for admin_keys registry (core/admin_keys.py)."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from engine.core.admin_keys import (
    AdminKeysRegistry,
    AdminKeyRecord,
    AdminKeyState,
    get_admin_keys_registry,
    reset_admin_keys_registry,
    _hash_secret,
    _generate_secret,
    HASH_PREFIX,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry singleton before each test."""
    reset_admin_keys_registry()
    yield
    reset_admin_keys_registry()


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """Create a registry with temp data root."""
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    return get_admin_keys_registry()


class TestHashAndSecretGeneration:
    """Test cryptographic helpers."""

    def test_generate_secret_length(self):
        """Generated secret should be URL-safe base64."""
        secret = _generate_secret()
        # secrets.token_urlsafe(32) produces 43 characters
        assert len(secret) == 43
        # Should be URL-safe (no +, /, =)
        assert "+" not in secret
        assert "/" not in secret

    def test_generate_secret_unique(self):
        """Each generated secret should be unique."""
        secrets = [_generate_secret() for _ in range(100)]
        assert len(set(secrets)) == 100

    def test_hash_secret_format(self):
        """Hash should have SHA256: prefix."""
        secret = "test-secret-123"
        hashed = _hash_secret(secret)
        assert hashed.startswith(HASH_PREFIX)
        # SHA256 hex is 64 characters
        assert len(hashed) == len(HASH_PREFIX) + 64

    def test_hash_secret_deterministic(self):
        """Same input should produce same hash."""
        secret = "test-secret-abc"
        hash1 = _hash_secret(secret)
        hash2 = _hash_secret(secret)
        assert hash1 == hash2

    def test_hash_secret_different_inputs(self):
        """Different inputs should produce different hashes."""
        hash1 = _hash_secret("secret-1")
        hash2 = _hash_secret("secret-2")
        assert hash1 != hash2


class TestAdminKeyRecord:
    """Test AdminKeyRecord dataclass."""

    def test_to_dict(self):
        """Convert record to dictionary."""
        record = AdminKeyRecord(
            key_id="key-123",
            key_hash="SHA256:abc123",
            status="active",
            created_at="2024-01-01T00:00:00Z",
            expires_at="2025-01-01T00:00:00Z",
            last_used_at=None,
            operation="create",
        )
        d = record.to_dict()
        assert d["key_id"] == "key-123"
        assert d["key_hash"] == "SHA256:abc123"
        assert d["status"] == "active"
        assert d["operation"] == "create"

    def test_from_dict(self):
        """Create record from dictionary."""
        d = {
            "key_id": "key-456",
            "key_hash": "SHA256:def456",
            "status": "revoked",
            "created_at": "2024-01-01T00:00:00Z",
            "expires_at": None,
            "last_used_at": "2024-06-01T00:00:00Z",
            "operation": "revoke",
        }
        record = AdminKeyRecord.from_dict(d)
        assert record.key_id == "key-456"
        assert record.status == "revoked"
        assert record.operation == "revoke"


class TestAdminKeyState:
    """Test AdminKeyState and is_valid()."""

    def test_active_key_is_valid(self):
        """Active key without expiry is valid."""
        state = AdminKeyState(
            key_id="key-1",
            key_hash="SHA256:abc",
            status="active",
            created_at="2024-01-01T00:00:00Z",
            expires_at=None,
            last_used_at=None,
        )
        assert state.is_valid() is True

    def test_revoked_key_is_not_valid(self):
        """Revoked key is not valid."""
        state = AdminKeyState(
            key_id="key-1",
            key_hash="SHA256:abc",
            status="revoked",
            created_at="2024-01-01T00:00:00Z",
            expires_at=None,
            last_used_at=None,
        )
        assert state.is_valid() is False

    def test_expired_status_is_not_valid(self):
        """Key with expired status is not valid."""
        state = AdminKeyState(
            key_id="key-1",
            key_hash="SHA256:abc",
            status="expired",
            created_at="2024-01-01T00:00:00Z",
            expires_at=None,
            last_used_at=None,
        )
        assert state.is_valid() is False

    def test_active_key_past_expiry_is_not_valid(self):
        """Active key past expiry date is not valid."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        state = AdminKeyState(
            key_id="key-1",
            key_hash="SHA256:abc",
            status="active",
            created_at="2024-01-01T00:00:00Z",
            expires_at=past,
            last_used_at=None,
        )
        assert state.is_valid() is False

    def test_active_key_future_expiry_is_valid(self):
        """Active key with future expiry is valid."""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        state = AdminKeyState(
            key_id="key-1",
            key_hash="SHA256:abc",
            status="active",
            created_at="2024-01-01T00:00:00Z",
            expires_at=future,
            last_used_at=None,
        )
        assert state.is_valid() is True


class TestAdminKeysRegistry:
    """Test AdminKeysRegistry operations."""

    def test_singleton_pattern(self, tmp_path, monkeypatch):
        """Registry uses singleton pattern."""
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
        reset_admin_keys_registry()

        reg1 = get_admin_keys_registry()
        reg2 = get_admin_keys_registry()
        assert reg1 is reg2

    def test_create_key_returns_id_and_secret(self, registry):
        """create_key returns key_id and plaintext_secret."""
        key_id, secret = registry.create_key("inst-001")

        assert key_id is not None
        assert len(key_id) == 36  # UUID format
        assert secret is not None
        assert len(secret) == 43  # token_urlsafe(32)

    def test_create_key_writes_to_file(self, registry, tmp_path, monkeypatch):
        """create_key writes record to JSONL file."""
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
        inst_id = "inst-002"

        key_id, _ = registry.create_key(inst_id)

        keys_path = tmp_path / "data" / "institutions" / inst_id / "admin_keys.jsonl"
        assert keys_path.exists()

        with open(keys_path) as f:
            lines = f.readlines()

        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["key_id"] == key_id
        assert record["operation"] == "create"
        assert record["status"] == "active"

    def test_create_key_with_expiry(self, registry):
        """create_key with expires_at stores expiry."""
        expires = "2025-12-31T23:59:59Z"
        key_id, _ = registry.create_key("inst-003", expires_at=expires)

        states = registry.load_current_state("inst-003")
        assert key_id in states
        assert states[key_id].expires_at == expires

    def test_verify_key_valid(self, registry):
        """verify_key returns True for valid key."""
        key_id, secret = registry.create_key("inst-004")

        valid, found_key_id, error = registry.verify_key("inst-004", secret)

        assert valid is True
        assert found_key_id == key_id
        assert error is None

    def test_verify_key_invalid_secret(self, registry):
        """verify_key returns False for wrong secret."""
        registry.create_key("inst-005")

        valid, key_id, error = registry.verify_key("inst-005", "wrong-secret")

        assert valid is False
        assert key_id is None
        assert error == "ADMIN_KEY_INVALID"

    def test_verify_key_wrong_institution(self, registry):
        """verify_key returns False for key from different institution."""
        _, secret = registry.create_key("inst-006")

        valid, key_id, error = registry.verify_key("inst-007", secret)

        assert valid is False
        assert key_id is None
        assert error == "ADMIN_KEY_INVALID"

    def test_revoke_key_success(self, registry):
        """revoke_key marks key as revoked."""
        key_id, _ = registry.create_key("inst-008")

        success, error = registry.revoke_key("inst-008", key_id)

        assert success is True
        assert error is None

        states = registry.load_current_state("inst-008")
        assert states[key_id].status == "revoked"

    def test_revoke_key_not_found(self, registry):
        """revoke_key returns error for unknown key."""
        registry.create_key("inst-009")

        success, error = registry.revoke_key("inst-009", "unknown-key-id")

        assert success is False
        assert error == "ADMIN_KEY_NOT_FOUND"

    def test_revoke_key_already_revoked(self, registry):
        """revoke_key returns error if already revoked."""
        key_id, _ = registry.create_key("inst-010")
        registry.revoke_key("inst-010", key_id)

        success, error = registry.revoke_key("inst-010", key_id)

        assert success is False
        assert error == "ADMIN_KEY_ALREADY_REVOKED"

    def test_verify_revoked_key_fails(self, registry):
        """verify_key returns False for revoked key."""
        key_id, secret = registry.create_key("inst-011")
        registry.revoke_key("inst-011", key_id)

        valid, found_key_id, error = registry.verify_key("inst-011", secret)

        assert valid is False
        assert found_key_id == key_id
        assert error == "ADMIN_KEY_REVOKED"

    def test_verify_expired_key_fails(self, registry):
        """verify_key returns False for expired key."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        key_id, secret = registry.create_key("inst-012", expires_at=past)

        valid, found_key_id, error = registry.verify_key("inst-012", secret)

        assert valid is False
        assert found_key_id == key_id
        assert error == "ADMIN_KEY_EXPIRED"

    def test_mark_used_updates_last_used(self, registry):
        """mark_used updates last_used_at."""
        key_id, _ = registry.create_key("inst-013")

        # Initially no last_used_at
        states = registry.load_current_state("inst-013")
        assert states[key_id].last_used_at is None

        registry.mark_used("inst-013", key_id)

        states = registry.load_current_state("inst-013")
        assert states[key_id].last_used_at is not None

    def test_list_keys_returns_all(self, registry):
        """list_keys returns all keys for institution."""
        key1, _ = registry.create_key("inst-014")
        key2, _ = registry.create_key("inst-014")
        registry.revoke_key("inst-014", key1)

        keys = registry.list_keys("inst-014")

        assert len(keys) == 2
        key_ids = {k.key_id for k in keys}
        assert key1 in key_ids
        assert key2 in key_ids

    def test_list_keys_empty_institution(self, registry):
        """list_keys returns empty list for new institution."""
        keys = registry.list_keys("inst-015")
        assert keys == []

    def test_load_current_state_folds_records(self, registry):
        """load_current_state correctly folds create/revoke/use records."""
        key_id, _ = registry.create_key("inst-016")
        registry.mark_used("inst-016", key_id)
        registry.revoke_key("inst-016", key_id)

        states = registry.load_current_state("inst-016")

        assert len(states) == 1
        assert states[key_id].status == "revoked"
        assert states[key_id].last_used_at is not None


class TestAppendOnlyStorage:
    """Test append-only JSONL storage properties."""

    def test_records_never_modified(self, registry, tmp_path, monkeypatch):
        """Records are appended, never modified."""
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
        inst_id = "inst-append-001"

        key_id, _ = registry.create_key(inst_id)
        registry.mark_used(inst_id, key_id)
        registry.revoke_key(inst_id, key_id)

        keys_path = tmp_path / "data" / "institutions" / inst_id / "admin_keys.jsonl"
        with open(keys_path) as f:
            lines = f.readlines()

        # Should have 3 separate records, not 1 modified record
        assert len(lines) == 3

        records = [json.loads(line) for line in lines]
        operations = [r["operation"] for r in records]
        assert operations == ["create", "use", "revoke"]

    def test_multiple_keys_same_file(self, registry, tmp_path, monkeypatch):
        """Multiple keys for same institution go in same file."""
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
        inst_id = "inst-append-002"

        registry.create_key(inst_id)
        registry.create_key(inst_id)
        registry.create_key(inst_id)

        keys_path = tmp_path / "data" / "institutions" / inst_id / "admin_keys.jsonl"
        with open(keys_path) as f:
            lines = f.readlines()

        assert len(lines) == 3
