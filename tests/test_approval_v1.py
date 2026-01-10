"""Tests for Approval v1 - Human approval contract.

Tests cover:
1) Valid approval passes validation
2) Invalid decision fails with SCHEMA: prefix
3) Canonicalization is stable (same content different order => same canonical)
4) Required fields validation
5) Helper functions
"""

import json
import tempfile
from pathlib import Path

import pytest

from approvals.approval_v1 import (
    APPROVAL_SCHEMA_VERSION,
    load_approval,
    validate_approval,
    canonicalize_approval,
    create_approval,
    is_approved,
    is_rejected,
    get_approval_decision,
    get_approval_approver,
    get_approval_scope,
    ApprovalValidationError,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def valid_approval():
    """Return a valid approval dict."""
    return {
        "schema_version": "approval.v1",
        "approval_id": "approval-001",
        "episode_id": "episode-123",
        "approver": {
            "display_name": "John Doe",
            "role": "Tech Lead",
            "org": "Engineering"
        },
        "decision": "approve",
        "reason": "All tests pass, code review completed",
        "scope": {
            "what": "release",
            "artifact_hashes": [
                "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
                "sha256:def456abc123def456abc123def456abc123def456abc123def456abc123def4"
            ]
        },
        "signatures": [
            {
                "scheme": "manual",
                "signature": None,
                "public_key_id": None
            }
        ]
    }


@pytest.fixture
def temp_approval_file(valid_approval):
    """Create a temporary approval file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(valid_approval, f)
        return Path(f.name)


# =============================================================================
# Test: Schema Version
# =============================================================================


class TestSchemaVersion:
    """Test schema version constant."""

    def test_schema_version_is_correct(self):
        """[approval_v1] Schema version is approval.v1."""
        assert APPROVAL_SCHEMA_VERSION == "approval.v1"


# =============================================================================
# Test: Valid Approval
# =============================================================================


class TestValidApproval:
    """Test valid approval scenarios."""

    def test_valid_approval_passes(self, valid_approval):
        """[approval_v1] Valid approval passes validation."""
        validate_approval(valid_approval)  # Should not raise

    def test_minimal_valid_approval(self):
        """[approval_v1] Minimal valid approval (no optional fields)."""
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "a1",
            "episode_id": "e1",
            "approver": {
                "display_name": "Alice",
                "role": "Manager"
            },
            "decision": "approve",
            "reason": "Looks good",
            "scope": {
                "what": "plan"
            },
            "signatures": []
        }
        validate_approval(approval)  # Should not raise

    def test_reject_decision_valid(self):
        """[approval_v1] Reject decision is valid."""
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "a1",
            "episode_id": "e1",
            "approver": {
                "display_name": "Bob",
                "role": "Security"
            },
            "decision": "reject",
            "reason": "Security concerns not addressed",
            "scope": {
                "what": "contracts"
            },
            "signatures": []
        }
        validate_approval(approval)  # Should not raise

    def test_all_scope_types_valid(self):
        """[approval_v1] All scope.what types are valid."""
        for scope_type in ["release", "plan", "contracts", "idl"]:
            approval = {
                "schema_version": "approval.v1",
                "approval_id": "a1",
                "episode_id": "e1",
                "approver": {"display_name": "User", "role": "Dev"},
                "decision": "approve",
                "reason": "OK",
                "scope": {"what": scope_type},
                "signatures": []
            }
            validate_approval(approval)  # Should not raise

    def test_all_signature_schemes_valid(self):
        """[approval_v1] All signature schemes are valid."""
        for scheme in ["attestation", "pgp", "x509", "manual"]:
            approval = {
                "schema_version": "approval.v1",
                "approval_id": "a1",
                "episode_id": "e1",
                "approver": {"display_name": "User", "role": "Dev"},
                "decision": "approve",
                "reason": "OK",
                "scope": {"what": "release"},
                "signatures": [{"scheme": scheme}]
            }
            validate_approval(approval)  # Should not raise

    def test_volatile_block_allowed(self, valid_approval):
        """[approval_v1] Volatile block with timestamp is allowed."""
        valid_approval["volatile"] = {
            "timestamp": "2024-01-15T10:30:00Z",
            "client_info": {"browser": "Chrome", "version": "120"}
        }
        validate_approval(valid_approval)  # Should not raise


# =============================================================================
# Test: Invalid Decision
# =============================================================================


class TestInvalidDecision:
    """Test invalid decision values."""

    def test_invalid_decision_fails_schema(self, valid_approval):
        """[approval_v1] Invalid decision fails with SCHEMA: prefix."""
        valid_approval["decision"] = "maybe"

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_empty_decision_fails(self, valid_approval):
        """[approval_v1] Empty decision fails."""
        valid_approval["decision"] = ""

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)


# =============================================================================
# Test: Required Fields
# =============================================================================


class TestRequiredFields:
    """Test required fields validation."""

    def test_missing_schema_version_fails(self, valid_approval):
        """[approval_v1] Missing schema_version fails."""
        del valid_approval["schema_version"]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_wrong_schema_version_fails(self, valid_approval):
        """[approval_v1] Wrong schema_version fails."""
        valid_approval["schema_version"] = "approval.v2"

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_missing_approval_id_fails(self, valid_approval):
        """[approval_v1] Missing approval_id fails."""
        del valid_approval["approval_id"]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_missing_episode_id_fails(self, valid_approval):
        """[approval_v1] Missing episode_id fails."""
        del valid_approval["episode_id"]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_missing_approver_fails(self, valid_approval):
        """[approval_v1] Missing approver fails."""
        del valid_approval["approver"]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_missing_reason_fails(self, valid_approval):
        """[approval_v1] Missing reason fails (enterprise audit)."""
        del valid_approval["reason"]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_empty_reason_fails(self, valid_approval):
        """[approval_v1] Empty reason fails."""
        valid_approval["reason"] = ""

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_missing_signatures_fails(self, valid_approval):
        """[approval_v1] Missing signatures list fails."""
        del valid_approval["signatures"]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)


# =============================================================================
# Test: Approver Validation
# =============================================================================


class TestApproverValidation:
    """Test approver field validation."""

    def test_missing_display_name_fails(self, valid_approval):
        """[approval_v1] Missing approver.display_name fails."""
        del valid_approval["approver"]["display_name"]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_missing_role_fails(self, valid_approval):
        """[approval_v1] Missing approver.role fails."""
        del valid_approval["approver"]["role"]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_null_org_allowed(self, valid_approval):
        """[approval_v1] Null org is allowed."""
        valid_approval["approver"]["org"] = None
        validate_approval(valid_approval)  # Should not raise


# =============================================================================
# Test: Scope Validation
# =============================================================================


class TestScopeValidation:
    """Test scope field validation."""

    def test_invalid_scope_what_fails(self, valid_approval):
        """[approval_v1] Invalid scope.what fails."""
        valid_approval["scope"]["what"] = "unknown"

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_invalid_artifact_hash_pattern_fails(self, valid_approval):
        """[approval_v1] Invalid artifact_hash pattern fails."""
        valid_approval["scope"]["artifact_hashes"] = ["not-a-valid-hash"]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_duplicate_artifact_hashes_fails(self, valid_approval):
        """[approval_v1] Duplicate artifact_hashes fails."""
        hash_val = "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456abc1"
        valid_approval["scope"]["artifact_hashes"] = [hash_val, hash_val]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)
        assert "Duplicate" in str(exc_info.value)


# =============================================================================
# Test: Signature Validation
# =============================================================================


class TestSignatureValidation:
    """Test signature field validation."""

    def test_invalid_scheme_fails(self, valid_approval):
        """[approval_v1] Invalid signature scheme fails."""
        valid_approval["signatures"] = [{"scheme": "invalid"}]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)

    def test_duplicate_signature_fails(self, valid_approval):
        """[approval_v1] Duplicate signatures fail."""
        valid_approval["signatures"] = [
            {"scheme": "manual", "public_key_id": "key1"},
            {"scheme": "manual", "public_key_id": "key1"}  # Duplicate
        ]

        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval(valid_approval)

        assert "SCHEMA:" in str(exc_info.value)
        assert "Duplicate signature" in str(exc_info.value)


# =============================================================================
# Test: Canonicalization
# =============================================================================


class TestCanonicalization:
    """Test approval canonicalization."""

    def test_canonical_is_deterministic(self, valid_approval):
        """[approval_v1] Canonicalization is deterministic."""
        canonical1 = canonicalize_approval(valid_approval)
        canonical2 = canonicalize_approval(valid_approval)

        assert canonical1 == canonical2

    def test_canonical_sorts_signatures_by_scheme(self):
        """[approval_v1] Signatures are sorted by scheme."""
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "a1",
            "episode_id": "e1",
            "approver": {"display_name": "User", "role": "Dev"},
            "decision": "approve",
            "reason": "OK",
            "scope": {"what": "release"},
            "signatures": [
                {"scheme": "x509", "public_key_id": "k1"},
                {"scheme": "attestation", "public_key_id": "k2"},
                {"scheme": "manual", "public_key_id": "k3"},
                {"scheme": "pgp", "public_key_id": "k4"},
            ]
        }

        canonical = canonicalize_approval(approval)

        schemes = [s["scheme"] for s in canonical["signatures"]]
        assert schemes == ["attestation", "manual", "pgp", "x509"]

    def test_canonical_sorts_signatures_by_public_key_id(self):
        """[approval_v1] Signatures with same scheme sorted by public_key_id."""
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "a1",
            "episode_id": "e1",
            "approver": {"display_name": "User", "role": "Dev"},
            "decision": "approve",
            "reason": "OK",
            "scope": {"what": "release"},
            "signatures": [
                {"scheme": "pgp", "public_key_id": "z-key"},
                {"scheme": "pgp", "public_key_id": "a-key"},
                {"scheme": "pgp", "public_key_id": "m-key"},
            ]
        }

        canonical = canonicalize_approval(approval)

        key_ids = [s["public_key_id"] for s in canonical["signatures"]]
        assert key_ids == ["a-key", "m-key", "z-key"]

    def test_canonical_sorts_artifact_hashes(self):
        """[approval_v1] Artifact hashes are sorted alphabetically."""
        approval = {
            "schema_version": "approval.v1",
            "approval_id": "a1",
            "episode_id": "e1",
            "approver": {"display_name": "User", "role": "Dev"},
            "decision": "approve",
            "reason": "OK",
            "scope": {
                "what": "release",
                "artifact_hashes": [
                    "sha256:zzz000zzz000zzz000zzz000zzz000zzz000zzz000zzz000zzz000zzz000zzz0",
                    "sha256:aaa111aaa111aaa111aaa111aaa111aaa111aaa111aaa111aaa111aaa111aaa1",
                    "sha256:mmm222mmm222mmm222mmm222mmm222mmm222mmm222mmm222mmm222mmm222mmm2",
                ]
            },
            "signatures": []
        }

        canonical = canonicalize_approval(approval)

        hashes = canonical["scope"]["artifact_hashes"]
        assert hashes[0].startswith("sha256:aaa")
        assert hashes[1].startswith("sha256:mmm")
        assert hashes[2].startswith("sha256:zzz")

    def test_different_order_same_canonical(self):
        """[approval_v1] Different input order produces same canonical."""
        # Approval 1: signatures in one order
        approval1 = {
            "schema_version": "approval.v1",
            "approval_id": "a1",
            "episode_id": "e1",
            "approver": {"display_name": "User", "role": "Dev"},
            "decision": "approve",
            "reason": "OK",
            "scope": {"what": "release"},
            "signatures": [
                {"scheme": "x509", "public_key_id": "k1"},
                {"scheme": "attestation", "public_key_id": "k2"},
            ]
        }

        # Approval 2: signatures in different order
        approval2 = {
            "schema_version": "approval.v1",
            "approval_id": "a1",
            "episode_id": "e1",
            "approver": {"display_name": "User", "role": "Dev"},
            "decision": "approve",
            "reason": "OK",
            "scope": {"what": "release"},
            "signatures": [
                {"scheme": "attestation", "public_key_id": "k2"},
                {"scheme": "x509", "public_key_id": "k1"},
            ]
        }

        canonical1 = canonicalize_approval(approval1)
        canonical2 = canonicalize_approval(approval2)

        assert canonical1 == canonical2

    def test_canonical_does_not_mutate_original(self, valid_approval):
        """[approval_v1] Canonicalization does not mutate original."""
        original_signatures = valid_approval["signatures"].copy()

        canonicalize_approval(valid_approval)

        assert valid_approval["signatures"] == original_signatures


# =============================================================================
# Test: Loading
# =============================================================================


class TestLoading:
    """Test approval loading from file."""

    def test_load_valid_file(self, temp_approval_file):
        """[approval_v1] Load valid approval file."""
        approval = load_approval(temp_approval_file)

        assert approval["approval_id"] == "approval-001"
        assert approval["decision"] == "approve"

    def test_load_nonexistent_file_fails(self):
        """[approval_v1] Loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_approval(Path("/nonexistent/approval.json"))

    def test_load_invalid_json_fails(self):
        """[approval_v1] Loading invalid JSON raises ApprovalValidationError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json")
            temp_path = Path(f.name)

        with pytest.raises(ApprovalValidationError) as exc_info:
            load_approval(temp_path)

        assert "SCHEMA:" in str(exc_info.value)
        assert "Invalid JSON" in str(exc_info.value)


# =============================================================================
# Test: Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Test helper functions."""

    def test_is_approved(self, valid_approval):
        """[approval_v1] is_approved returns True for approve decision."""
        assert is_approved(valid_approval) is True

    def test_is_approved_false_for_reject(self, valid_approval):
        """[approval_v1] is_approved returns False for reject decision."""
        valid_approval["decision"] = "reject"
        assert is_approved(valid_approval) is False

    def test_is_rejected(self, valid_approval):
        """[approval_v1] is_rejected returns True for reject decision."""
        valid_approval["decision"] = "reject"
        assert is_rejected(valid_approval) is True

    def test_is_rejected_false_for_approve(self, valid_approval):
        """[approval_v1] is_rejected returns False for approve decision."""
        assert is_rejected(valid_approval) is False

    def test_get_approval_decision(self, valid_approval):
        """[approval_v1] get_approval_decision returns decision."""
        assert get_approval_decision(valid_approval) == "approve"

    def test_get_approval_approver(self, valid_approval):
        """[approval_v1] get_approval_approver returns approver dict."""
        approver = get_approval_approver(valid_approval)

        assert approver["display_name"] == "John Doe"
        assert approver["role"] == "Tech Lead"

    def test_get_approval_scope(self, valid_approval):
        """[approval_v1] get_approval_scope returns scope dict."""
        scope = get_approval_scope(valid_approval)

        assert scope["what"] == "release"
        assert len(scope["artifact_hashes"]) == 2


# =============================================================================
# Test: Create Approval
# =============================================================================


class TestCreateApproval:
    """Test approval creation helper."""

    def test_create_minimal_approval(self):
        """[approval_v1] Create minimal approval."""
        approval = create_approval(
            approval_id="a1",
            episode_id="e1",
            approver_name="Alice",
            approver_role="Manager",
            decision="approve",
            reason="Looks good",
            scope_what="plan",
        )

        assert approval["schema_version"] == "approval.v1"
        assert approval["approval_id"] == "a1"
        assert approval["decision"] == "approve"
        assert approval["approver"]["display_name"] == "Alice"

    def test_create_full_approval(self):
        """[approval_v1] Create approval with all fields."""
        approval = create_approval(
            approval_id="a2",
            episode_id="e2",
            approver_name="Bob",
            approver_role="Security",
            decision="reject",
            reason="Needs more tests",
            scope_what="release",
            approver_org="Security Team",
            artifact_hashes=[
                "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456abc1"
            ],
            signatures=[{"scheme": "manual"}]
        )

        assert approval["approver"]["org"] == "Security Team"
        assert len(approval["scope"]["artifact_hashes"]) == 1
        assert len(approval["signatures"]) == 1

    def test_create_invalid_decision_fails(self):
        """[approval_v1] Creating approval with invalid decision fails."""
        with pytest.raises(ApprovalValidationError):
            create_approval(
                approval_id="a1",
                episode_id="e1",
                approver_name="Alice",
                approver_role="Manager",
                decision="maybe",  # Invalid
                reason="Not sure",
                scope_what="plan",
            )
