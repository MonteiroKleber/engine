"""Tests for Console read-only endpoints.

Etapa 3.1: Console mínimo (read-only)
Etapa 3.2: Institutional Explorer (contracts, proof)
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.institutions import reset_registry, get_registry
from engine.core.runtime_state import runtime_state, RuntimeMode


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    """Reset state before each test."""
    # Set temp paths to avoid polluting real directories
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")

    # Reset global registry
    reset_registry()

    # Ensure runtime is ACTIVE
    runtime_state.mode = RuntimeMode.ACTIVE
    runtime_state.reason_code = None
    runtime_state.details = []

    yield

    reset_registry()
    runtime_state.mode = RuntimeMode.ACTIVE
    runtime_state.reason_code = None
    runtime_state.details = []


class TestConsoleAuth:
    """Test console authentication requirements."""

    def test_console_home_without_token_returns_401(self):
        """GET /console/ without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_console_status_without_token_returns_401(self):
        """GET /console/status without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/status?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_console_bundles_without_token_returns_401(self):
        """GET /console/bundles without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/bundles?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_console_legacy_without_token_returns_401(self):
        """GET /console/legacy without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/legacy?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"


class TestConsoleHomeWithAuth:
    """Test console home page with valid auth."""

    def test_console_home_returns_html(self):
        """GET /console/ with valid token returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "AXIOM Console" in response.text

    def test_console_home_shows_institution_select(self):
        """GET /console/ shows institution selection form."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Select Context" in response.text
        assert "institution_id" in response.text

    def test_console_home_shows_runtime_mode(self):
        """GET /console/ shows current runtime mode."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "ACTIVE" in response.text


class TestConsoleStatusPage:
    """Test console status page."""

    def test_console_status_requires_institution_id(self):
        """GET /console/status without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/status",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_console_status_returns_html(self):
        """GET /console/status with institution_id returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/status?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Runtime Status" in response.text

    def test_console_status_shows_active_mode(self):
        """GET /console/status shows ACTIVE mode when runtime is active."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/status?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "ACTIVE" in response.text

    def test_console_status_shows_safe_mode(self):
        """GET /console/status shows SAFE_MODE when runtime is in safe mode."""
        runtime_state.mode = RuntimeMode.SAFE_MODE
        runtime_state.reason_code = "TEST_REASON"

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/status?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "SAFE_MODE" in response.text


class TestConsoleBundlesPage:
    """Test console bundles page."""

    def test_console_bundles_requires_institution_id(self):
        """GET /console/bundles without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/bundles",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_console_bundles_returns_html(self):
        """GET /console/bundles with institution_id returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/bundles?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Pin Status" in response.text


class TestConsoleLegacyPage:
    """Test console legacy page."""

    def test_console_legacy_requires_institution_id(self):
        """GET /console/legacy without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_console_legacy_returns_html(self):
        """GET /console/legacy with institution_id returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Legacy Assets" in response.text


class TestConsoleStaticFiles:
    """Test console static file serving."""

    def test_console_static_css_returns_css(self):
        """GET /console/static/style.css returns CSS."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/static/style.css")

        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]
        assert ":root" in response.text

    def test_console_static_nonexistent_returns_404(self):
        """GET /console/static/nonexistent.css returns 404."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/static/nonexistent.css")

        assert response.status_code == 404


class TestConsoleReadOnly:
    """Test that console is truly read-only (except Mandates Governance)."""

    def test_console_has_no_post_endpoints_except_mandates(self):
        """Console router has no POST endpoints except mandates/EGE governance routes."""
        from engine.console.routes import router

        # Governance routes (Etapa 3.4-3.6) and auth routes intentionally have POST methods
        mutable_allowed_paths = {
            "/console/login",  # Etapa 4.1: browser auth login
            "/console/mandates/proposals",
            "/console/mandates/proposals/{proposal_id}/decide",
            "/console/ege/rollback",  # Etapa 3.5: governed rollback
            "/console/legacy/{asset_id}/verify",  # Etapa 3.6: legacy verify (read-only on source)
            "/console/intake",  # Etapa 3.7: intake assisted (generates draft, no deploy)
            "/console/intake/answer",  # Etapa 3.7: intake answer (updates draft)
            "/console/intake/finalize",  # Etapa 3.7: intake finalize (generates final IDL)
            "/console/onboarding/create-institution",  # Etapa 4.2: onboarding wizard
            "/console/onboarding/generate-bundle",  # Etapa 4.2: onboarding bundle generation
        }

        for route in router.routes:
            # Skip the static file route which uses GET
            if hasattr(route, 'methods'):
                # Ensure no POST, PUT, PATCH, DELETE methods (except mandates)
                methods = set(route.methods)
                mutable_methods = {"POST", "PUT", "PATCH", "DELETE"}
                mutable_used = methods & mutable_methods
                if mutable_used and route.path not in mutable_allowed_paths:
                    assert False, \
                        f"Route {route.path} has mutable methods: {mutable_used}"


class TestConsoleFreezeBypass:
    """Test that console bypasses freeze checks."""

    def test_console_home_accessible_during_freeze(self, tmp_path, monkeypatch):
        """Console home page is accessible even during institution freeze."""
        # Set up a frozen institution config
        monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # Should still return 200, not 503 (frozen)
        assert response.status_code == 200

    def test_console_status_accessible_during_safe_mode(self):
        """Console status page is accessible during safe mode."""
        runtime_state.mode = RuntimeMode.SAFE_MODE
        runtime_state.reason_code = "TEST_SAFE_MODE"

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/status?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # Should still return 200
        assert response.status_code == 200
        assert "SAFE_MODE" in response.text


# =============================================================================
# Etapa 3.2: Explorer Tests
# =============================================================================


@pytest.fixture
def valid_bundle(tmp_path):
    """Create a valid test bundle for explorer tests."""
    bundle_path = tmp_path / "test-bundle"
    bundle_path.mkdir()

    # Create bundle.manifest.json
    manifest = {
        "name": "test-bundle",
        "version": "1.0.0",
        "contracts": [
            {"file": "rbac.json", "sha256": "", "required": True},
            {"file": "policies.json", "sha256": "", "required": True},
        ],
    }

    # Create contract files
    rbac_content = {"version": "1.0.0", "roles": ["admin", "user"]}
    policies_content = {"version": "1.0.0", "policies": []}

    rbac_path = bundle_path / "rbac.json"
    policies_path = bundle_path / "policies.json"

    with open(rbac_path, "w") as f:
        json.dump(rbac_content, f)
    with open(policies_path, "w") as f:
        json.dump(policies_content, f)

    # Compute hashes
    from engine.loader.verify_hashes import compute_sha256
    rbac_hash = compute_sha256(rbac_path)
    policies_hash = compute_sha256(policies_path)

    # Update manifest with hashes
    manifest["contracts"][0]["sha256"] = rbac_hash
    manifest["contracts"][1]["sha256"] = policies_hash

    manifest_path = bundle_path / "bundle.manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)

    manifest_hash = compute_sha256(manifest_path)

    # Create contract_ledger.json
    ledger = {
        "manifest_hash": manifest_hash,
        "source_idl_sha256": "a" * 64,
        "contracts": [
            {"contract_name": "rbac.json", "content_hash": rbac_hash},
            {"contract_name": "policies.json", "content_hash": policies_hash},
        ],
    }

    ledger_path = bundle_path / "contract_ledger.json"
    with open(ledger_path, "w") as f:
        json.dump(ledger, f)

    return bundle_path


class TestConsoleContractsAuth:
    """Test console contracts page authentication."""

    def test_console_contracts_without_token_returns_401(self):
        """GET /console/contracts without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/contracts?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_console_contract_detail_without_token_returns_401(self):
        """GET /console/contracts/{file} without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/contracts/rbac.json?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_console_proof_without_token_returns_401(self):
        """GET /console/proof without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/proof?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"


class TestConsoleContractsPage:
    """Test console contracts listing page."""

    def test_console_contracts_requires_institution_id(self):
        """GET /console/contracts without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/contracts",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_console_contracts_returns_html(self, valid_bundle, monkeypatch):
        """GET /console/contracts returns HTML page."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/contracts?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Contracts" in response.text

    def test_console_contracts_shows_manifest_hash(self, valid_bundle, monkeypatch):
        """GET /console/contracts shows manifest hash."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/contracts?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "SHA256" in response.text
        assert "bundle.manifest.json" in response.text

    def test_console_contracts_lists_contracts(self, valid_bundle, monkeypatch):
        """GET /console/contracts lists contracts from manifest."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/contracts?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "rbac.json" in response.text
        assert "policies.json" in response.text


class TestConsoleContractDetail:
    """Test console contract detail page."""

    def test_console_contract_detail_returns_content(self, valid_bundle, monkeypatch):
        """GET /console/contracts/{file} returns file content."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/contracts/rbac.json?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "rbac.json" in response.text
        # Content should be visible
        assert "admin" in response.text
        assert "user" in response.text

    def test_console_contract_detail_shows_hash(self, valid_bundle, monkeypatch):
        """GET /console/contracts/{file} shows computed hash."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/contracts/rbac.json?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Computed SHA256" in response.text

    def test_console_contract_detail_shows_hash_match(self, valid_bundle, monkeypatch):
        """GET /console/contracts/{file} shows MATCH when hash matches manifest."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/contracts/rbac.json?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "MATCH" in response.text

    def test_console_contract_detail_file_not_found(self, valid_bundle, monkeypatch):
        """GET /console/contracts/{file} returns 404 for missing file."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/contracts/nonexistent.json?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "EXPLORER_FILE_NOT_FOUND"


class TestConsolePathTraversal:
    """Test console path traversal protection."""

    def test_path_traversal_dot_dot_blocked(self, valid_bundle, monkeypatch):
        """Path traversal with .. is blocked."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        # Test via is_safe_path directly since URL normalization
        # may resolve .. before reaching handler
        from engine.proof import is_safe_path

        # These should all be blocked
        assert not is_safe_path(valid_bundle, "../secret.txt")
        assert not is_safe_path(valid_bundle, "../../etc/passwd")
        assert not is_safe_path(valid_bundle, "contracts/../../../etc/passwd")

        # Test HTTP endpoint - may return 400 or 404 depending on path normalization
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/contracts/../../../etc/passwd?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # Should be blocked - either 400 (traversal) or 404 (path normalized and not found)
        assert response.status_code in (400, 404)

    def test_path_traversal_encoded_blocked(self, valid_bundle, monkeypatch):
        """GET /console/contracts/..%2F..%2Fetc/passwd returns 400."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        # Note: FastAPI/Starlette will decode %2F to /
        response = client.get(
            "/console/contracts/..%2F..%2Fetc/passwd?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # Should be blocked either as 400 (traversal) or 404 (not found after normalization)
        assert response.status_code in (400, 404)

    def test_path_traversal_absolute_path_blocked(self, valid_bundle, monkeypatch):
        """Absolute paths in contract file are blocked."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        # This tests the is_safe_path function directly
        from engine.proof import is_safe_path

        assert not is_safe_path(valid_bundle, "/etc/passwd")
        assert not is_safe_path(valid_bundle, "../secret.txt")
        assert not is_safe_path(valid_bundle, "foo/../../../etc/passwd")

    def test_safe_path_allows_valid_files(self, valid_bundle):
        """Valid relative paths are allowed."""
        from engine.proof import is_safe_path

        assert is_safe_path(valid_bundle, "rbac.json")
        assert is_safe_path(valid_bundle, "policies.json")
        assert is_safe_path(valid_bundle, "subdir/file.json")


class TestConsoleProofPage:
    """Test console proof verification page."""

    def test_console_proof_requires_institution_id(self):
        """GET /console/proof without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_console_proof_returns_html(self, valid_bundle, monkeypatch):
        """GET /console/proof returns HTML page."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_console_proof_shows_pass_for_valid_bundle(self, valid_bundle, monkeypatch):
        """GET /console/proof shows PASS for valid bundle."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "PASS" in response.text
        assert "Bundle Verified" in response.text

    def test_console_proof_shows_contracts_verified(self, valid_bundle, monkeypatch):
        """GET /console/proof shows contracts verified count."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Contracts Verified" in response.text
        assert "2" in response.text  # 2 contracts in test bundle

    def test_console_proof_shows_json_when_requested(self, valid_bundle, monkeypatch):
        """GET /console/proof?show_json=true shows JSON result."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id&show_json=true",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Jinja2 HTML-escapes quotes, so check for escaped version
        assert "&#34;passed&#34;: true" in response.text or '"passed": true' in response.text


class TestConsoleProofFailure:
    """Test console proof page with invalid bundle."""

    def test_console_proof_shows_fail_for_missing_manifest(self, tmp_path, monkeypatch):
        """GET /console/proof shows FAIL for bundle without manifest."""
        empty_bundle = tmp_path / "empty-bundle"
        empty_bundle.mkdir()
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(empty_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "FAIL" in response.text

    def test_console_proof_shows_fail_for_hash_mismatch(self, valid_bundle, monkeypatch):
        """GET /console/proof shows FAIL when contract hash doesn't match."""
        # Modify a contract file to cause hash mismatch
        rbac_path = valid_bundle / "rbac.json"
        with open(rbac_path, "w") as f:
            json.dump({"modified": True}, f)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "FAIL" in response.text
        assert "PROOF_CONTRACT_HASH_MISMATCH" in response.text


class TestConsoleExplorerReadOnly:
    """Test that explorer routes are read-only."""

    def test_explorer_routes_are_get_only(self):
        """Explorer routes only support GET method."""
        from engine.console.routes import router

        explorer_paths = ["/contracts", "/contracts/{file_path:path}", "/proof", "/proof.json"]

        for route in router.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                if any(route.path.endswith(p) or p in route.path for p in explorer_paths):
                    methods = set(route.methods)
                    mutable_methods = {"POST", "PUT", "PATCH", "DELETE"}
                    assert methods.isdisjoint(mutable_methods), \
                        f"Route {route.path} has mutable methods: {methods & mutable_methods}"


# =============================================================================
# Etapa 3.3: Proof Console UX + Export Tests
# =============================================================================


class TestConsoleProofChecksTable:
    """Test console proof page checks table (Etapa 3.3)."""

    def test_console_proof_shows_checks_table(self, valid_bundle, monkeypatch):
        """GET /console/proof shows verification checks table."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Verification Checks" in response.text
        assert "Manifest exists" in response.text
        assert "Contracts hashes" in response.text
        assert "Ledger exists" in response.text

    def test_console_proof_checks_all_pass_for_valid_bundle(self, valid_bundle, monkeypatch):
        """GET /console/proof shows all checks PASS for valid bundle."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Should have multiple PASS badges
        assert response.text.count("badge-active") >= 5  # At least 5 pass checks

    def test_console_proof_checks_show_fail_for_hash_mismatch(self, valid_bundle, monkeypatch):
        """GET /console/proof shows FAIL check for hash mismatch."""
        # Modify a contract file to cause hash mismatch
        rbac_path = valid_bundle / "rbac.json"
        with open(rbac_path, "w") as f:
            json.dump({"modified": True}, f)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "badge-error" in response.text  # FAIL badge
        assert "Contracts hashes" in response.text


class TestConsoleProofFailureLinks:
    """Test console proof page failure links to contracts (Etapa 3.3)."""

    def test_console_proof_shows_link_to_affected_file(self, valid_bundle, monkeypatch):
        """GET /console/proof shows link to affected file on hash mismatch."""
        # Modify a contract file to cause hash mismatch
        rbac_path = valid_bundle / "rbac.json"
        with open(rbac_path, "w") as f:
            json.dump({"modified": True}, f)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Affected File" in response.text
        # Should have link to contract detail
        assert "/console/contracts/rbac.json" in response.text

    def test_console_proof_shows_expected_vs_actual_hash(self, valid_bundle, monkeypatch):
        """GET /console/proof shows expected vs actual hash on mismatch."""
        # Modify a contract file to cause hash mismatch
        rbac_path = valid_bundle / "rbac.json"
        with open(rbac_path, "w") as f:
            json.dump({"modified": True}, f)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Expected Hash" in response.text
        assert "Actual Hash" in response.text


class TestConsoleProofJsonExport:
    """Test console proof JSON export (Etapa 3.3)."""

    def test_console_proof_json_requires_token(self):
        """GET /console/proof.json without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/proof.json?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_console_proof_json_requires_institution_id(self):
        """GET /console/proof.json without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof.json",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_console_proof_json_returns_json_content(self, valid_bundle, monkeypatch):
        """GET /console/proof.json returns JSON content type."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof.json?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_console_proof_json_has_download_header(self, valid_bundle, monkeypatch):
        """GET /console/proof.json has Content-Disposition attachment header."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof.json?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "content-disposition" in response.headers
        assert "attachment" in response.headers["content-disposition"]
        assert "proof-" in response.headers["content-disposition"]
        assert ".json" in response.headers["content-disposition"]

    def test_console_proof_json_contains_result_fields(self, valid_bundle, monkeypatch):
        """GET /console/proof.json contains expected result fields."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof.json?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()

        # ProofResult fields
        assert "passed" in data
        assert data["passed"] is True
        assert "bundle_name" in data
        assert "bundle_version" in data
        assert "manifest_hash" in data
        assert "source_idl_sha256" in data
        assert "contracts_verified" in data
        assert data["contracts_verified"] == 2  # 2 contracts in test bundle

        # Additional metadata
        assert "institution_id" in data
        assert data["institution_id"] == "test-inst-id"
        assert "bundle_path" in data

    def test_console_proof_json_shows_fail_for_invalid_bundle(self, valid_bundle, monkeypatch):
        """GET /console/proof.json shows passed=false for invalid bundle."""
        # Modify a contract file to cause hash mismatch
        rbac_path = valid_bundle / "rbac.json"
        with open(rbac_path, "w") as f:
            json.dump({"modified": True}, f)

        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof.json?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["passed"] is False
        assert data["error_code"] == "PROOF_CONTRACT_HASH_MISMATCH"


class TestConsoleProofExportLink:
    """Test console proof page export link (Etapa 3.3)."""

    def test_console_proof_shows_download_link(self, valid_bundle, monkeypatch):
        """GET /console/proof shows Download JSON Report link."""
        monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(valid_bundle))

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/proof?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Download JSON Report" in response.text
        assert "/console/proof.json" in response.text


# =============================================================================
# Etapa 3.4: Mandates Governance UI Tests
# =============================================================================


class TestConsoleMandatesAuth:
    """Test mandates console authentication requirements (Etapa 3.4)."""

    def test_console_mandates_without_token_returns_401(self):
        """GET /console/mandates without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/mandates?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_console_mandates_proposals_without_token_returns_401(self):
        """GET /console/mandates/proposals without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/mandates/proposals?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_console_mandates_proposals_new_without_token_returns_401(self):
        """GET /console/mandates/proposals/new without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/mandates/proposals/new?institution_id=test-id")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"

    def test_console_mandates_proposals_post_without_token_returns_401(self):
        """POST /console/mandates/proposals without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/mandates/proposals",
            data={
                "institution_id": "test-id",
                "operation": "create",
                "mandate_id": "M001",
                "mandate_data": "{}",
                "reason": "test",
            },
        )

        assert response.status_code == 401


class TestConsoleMandatesPage:
    """Test mandates console page (Etapa 3.4)."""

    def test_console_mandates_requires_institution_id(self):
        """GET /console/mandates without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_console_mandates_returns_html(self):
        """GET /console/mandates with institution_id returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Effective Mandates" in response.text

    def test_console_mandates_shows_proposals_link(self):
        """GET /console/mandates shows link to proposals."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "View Proposals" in response.text
        assert "New Proposal" in response.text


class TestConsoleMandatesProposalsPage:
    """Test mandates proposals page (Etapa 3.4)."""

    def test_console_mandates_proposals_requires_institution_id(self):
        """GET /console/mandates/proposals without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates/proposals",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_console_mandates_proposals_returns_html(self):
        """GET /console/mandates/proposals with institution_id returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates/proposals?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Mandate Proposals" in response.text

    def test_console_mandates_proposals_shows_new_proposal_link(self):
        """GET /console/mandates/proposals shows link to new proposal."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates/proposals?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "New Proposal" in response.text


class TestConsoleMandatesProposalNewPage:
    """Test new mandate proposal page (Etapa 3.4)."""

    def test_console_mandates_proposals_new_requires_institution_id(self):
        """GET /console/mandates/proposals/new without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates/proposals/new",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422

    def test_console_mandates_proposals_new_returns_html(self):
        """GET /console/mandates/proposals/new with institution_id returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates/proposals/new?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Create Mandate Proposal" in response.text

    def test_console_mandates_proposals_new_shows_form(self):
        """GET /console/mandates/proposals/new shows form with operation options."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates/proposals/new?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert 'name="operation"' in response.text
        assert 'name="mandate_id"' in response.text
        assert 'name="mandate_data"' in response.text
        assert 'name="reason"' in response.text
        assert "Create new mandate" in response.text
        assert "Update existing mandate" in response.text
        assert "Revoke mandate" in response.text


class TestConsoleMandatesProposalCreate:
    """Test creating mandate proposals via console (Etapa 3.4)."""

    @pytest.fixture(autouse=True)
    def reset_governed(self, tmp_path, monkeypatch):
        """Reset governed mandates state."""
        from engine.core.governed_mandates import (
            reset_governed_mandates_registry,
            invalidate_all_mandates_cache,
        )
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
        reset_governed_mandates_registry()
        invalidate_all_mandates_cache()
        yield
        reset_governed_mandates_registry()
        invalidate_all_mandates_cache()

    def test_console_create_proposal_success(self):
        """POST /console/mandates/proposals creates proposal and redirects."""
        mandate_data = json.dumps({
            "mandate_id": "M001",
            "endpoint_sig": "POST /finance/expenses",  # must be a valid allowed endpoint
            "phase": "pre",  # lowercase required
            "allowed_roles": ["admin"],
            "limits": [],
        })

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/mandates/proposals",
            data={
                "institution_id": "test-inst-id",
                "operation": "create",
                "mandate_id": "M001",
                "mandate_data": mandate_data,
                "reason": "Testing mandate creation",
            },
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/console/mandates/proposals" in response.headers["location"]
        assert "success=proposal_created" in response.headers["location"]

    def test_console_create_proposal_invalid_json_returns_error(self):
        """POST /console/mandates/proposals with invalid JSON returns error."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/mandates/proposals",
            data={
                "institution_id": "test-inst-id",
                "operation": "create",
                "mandate_id": "M001",
                "mandate_data": "{invalid json}",
                "reason": "Testing",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 400
        assert "Invalid JSON" in response.text

    def test_console_create_proposal_empty_data_returns_error(self):
        """POST /console/mandates/proposals with empty data returns error."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/mandates/proposals",
            data={
                "institution_id": "test-inst-id",
                "operation": "create",
                "mandate_id": "M001",
                "mandate_data": "",
                "reason": "Testing",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 400
        assert "required" in response.text.lower()


class TestConsoleMandatesProposalDecide:
    """Test approving/rejecting mandate proposals via console (Etapa 3.4)."""

    @pytest.fixture(autouse=True)
    def reset_governed(self, tmp_path, monkeypatch):
        """Reset governed mandates state."""
        from engine.core.governed_mandates import (
            reset_governed_mandates_registry,
            invalidate_all_mandates_cache,
        )
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
        reset_governed_mandates_registry()
        invalidate_all_mandates_cache()
        yield
        reset_governed_mandates_registry()
        invalidate_all_mandates_cache()

    @pytest.fixture
    def created_proposal(self):
        """Create a proposal for testing decide operations."""
        from engine.core.governed_mandates import propose_mandate_change

        proposal, error_code, error_msg = propose_mandate_change(
            institution_id="test-inst-id",
            operation="create",
            mandate_id="M001",
            mandate_data={
                "mandate_id": "M001",
                "endpoint_sig": "POST /finance/expenses",  # must be a valid allowed endpoint
                "phase": "pre",  # lowercase required
                "allowed_roles": ["admin"],
                "limits": [],
            },
            reason="Test proposal",
            actor_id="TEST",
        )

        assert error_code is None, f"Failed to create proposal: {error_msg}"
        return proposal

    def test_console_approve_proposal_success(self, created_proposal):
        """POST /console/mandates/proposals/{id}/decide approve redirects."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/console/mandates/proposals/{created_proposal.proposal_id}/decide",
            data={
                "institution_id": "test-inst-id",
                "decision": "approve",
                "decision_reason": "Approved for testing",
            },
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "success=proposal_approved" in response.headers["location"]

    def test_console_reject_proposal_success(self, created_proposal):
        """POST /console/mandates/proposals/{id}/decide reject redirects."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/console/mandates/proposals/{created_proposal.proposal_id}/decide",
            data={
                "institution_id": "test-inst-id",
                "decision": "reject",
                "decision_reason": "Rejected for testing",
            },
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "success=proposal_rejected" in response.headers["location"]

    def test_console_reject_without_reason_returns_error(self, created_proposal):
        """POST /console/mandates/proposals/{id}/decide reject without reason returns error."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/console/mandates/proposals/{created_proposal.proposal_id}/decide",
            data={
                "institution_id": "test-inst-id",
                "decision": "reject",
                "decision_reason": "",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 400
        assert "required" in response.text.lower()


class TestConsoleMandatesEffectiveChanges:
    """Test that effective mandates change after approve (Etapa 3.4)."""

    @pytest.fixture(autouse=True)
    def reset_governed(self, tmp_path, monkeypatch):
        """Reset governed mandates state."""
        from engine.core.governed_mandates import (
            reset_governed_mandates_registry,
            invalidate_all_mandates_cache,
        )
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
        reset_governed_mandates_registry()
        invalidate_all_mandates_cache()
        yield
        reset_governed_mandates_registry()
        invalidate_all_mandates_cache()

    def test_effective_mandates_include_governed_after_approve(self):
        """After approving a proposal, effective mandates include the governed mandate."""
        from engine.core.governed_mandates import (
            propose_mandate_change,
            decide_mandate_proposal,
            get_effective_mandates,
        )

        # Create and approve a proposal
        proposal, error_code, error_msg = propose_mandate_change(
            institution_id="test-inst-id",
            operation="create",
            mandate_id="M-GOV-001",
            mandate_data={
                "mandate_id": "M-GOV-001",
                "endpoint_sig": "POST /support/tickets",  # must be a valid allowed endpoint
                "phase": "pre",  # lowercase required
                "allowed_roles": ["admin"],
                "limits": [],
            },
            reason="Test governed mandate",
            actor_id="TEST",
        )

        assert error_code is None, f"Failed to create proposal: {error_msg}"

        # Approve
        decide_mandate_proposal(
            institution_id="test-inst-id",
            proposal_id=proposal.proposal_id,
            decision="approve",
            reason=None,
            actor_id="TEST",
        )

        # Check effective mandates
        effective = get_effective_mandates("test-inst-id", None)
        assert effective is not None
        mandate_ids = [m.mandate_id for m in effective.mandates]
        assert "M-GOV-001" in mandate_ids

        # Verify via console page
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/mandates?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "M-GOV-001" in response.text
        assert "governed" in response.text


class TestConsoleMandatesNavLink:
    """Test that Mandates nav link appears in base template (Etapa 3.4)."""

    def test_base_template_has_mandates_nav_link(self):
        """Navigation includes Mandates link when institution_id is set."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/status?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "/console/mandates" in response.text
        assert ">Mandates<" in response.text


# =============================================================================
# Etapa 3.5: EGE Console Tests
# =============================================================================


class TestConsoleEGEAuth:
    """Test EGE console authentication (Etapa 3.5)."""

    def test_ege_without_token_returns_401(self):
        """GET /console/ege without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/ege?institution_id=test-inst-id")

        assert response.status_code == 401

    def test_ege_proposals_without_token_returns_401(self):
        """GET /console/ege/proposals without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/ege/proposals?institution_id=test-inst-id")

        assert response.status_code == 401

    def test_ege_releases_without_token_returns_401(self):
        """GET /console/ege/releases without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/ege/releases?institution_id=test-inst-id")

        assert response.status_code == 401

    def test_ege_rollback_confirm_without_token_returns_401(self):
        """GET /console/ege/rollback/confirm without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/ege/rollback/confirm?institution_id=test-inst-id")

        assert response.status_code == 401

    def test_ege_rollback_post_without_token_returns_401(self):
        """POST /console/ege/rollback without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/ege/rollback",
            data={"institution_id": "test-inst-id", "confirm": "yes"},
        )

        assert response.status_code == 401


class TestConsoleEGEPage:
    """Test EGE overview page rendering (Etapa 3.5)."""

    def test_ege_page_returns_html(self):
        """GET /console/ege returns HTML page."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_ege_page_contains_drift_status(self):
        """EGE overview page shows drift status."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Drift Status" in response.text

    def test_ege_page_contains_proposals_link(self):
        """EGE overview page has link to proposals."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "/console/ege/proposals" in response.text

    def test_ege_page_contains_releases_link(self):
        """EGE overview page has link to releases."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "/console/ege/releases" in response.text


class TestConsoleEGEProposalsPage:
    """Test EGE proposals page rendering (Etapa 3.5)."""

    def test_ege_proposals_page_returns_html(self):
        """GET /console/ege/proposals returns HTML page."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege/proposals?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_ege_proposals_page_has_back_link(self):
        """EGE proposals page has back link to overview."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege/proposals?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "/console/ege?" in response.text


class TestConsoleEGEReleasesPage:
    """Test EGE releases page rendering (Etapa 3.5)."""

    def test_ege_releases_page_returns_html(self):
        """GET /console/ege/releases returns HTML page."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege/releases?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_ege_releases_page_shows_current_release(self):
        """EGE releases page shows current release info."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege/releases?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Current Release" in response.text


class TestConsoleEGETracePage:
    """Test EGE trace page rendering (Etapa 3.5)."""

    def test_ege_trace_page_returns_html(self):
        """GET /console/ege/traces/{id} returns HTML page."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege/traces/20260119-120000?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_ege_trace_page_shows_unavailable_message(self):
        """EGE trace page shows unavailable message for missing trace."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege/traces/20260119-120000?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Should show unavailable message since trace doesn't exist
        assert "Trace Unavailable" in response.text or "not found" in response.text.lower()


class TestConsoleEGERollbackConfirm:
    """Test EGE rollback confirmation page (Etapa 3.5)."""

    def test_ege_rollback_confirm_page_returns_html(self):
        """GET /console/ege/rollback/confirm returns HTML page."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege/rollback/confirm?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_ege_rollback_confirm_shows_warning(self):
        """EGE rollback confirm page shows warning about no pinned release."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/ege/rollback/confirm?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Should warn that there's no pinned release
        assert "Warning" in response.text or "SAFE_MODE" in response.text


class TestConsoleEGERollbackPost:
    """Test EGE rollback POST action (Etapa 3.5)."""

    def test_ege_rollback_without_confirm_redirects_with_error(self):
        """POST /console/ege/rollback without confirm=yes redirects with error."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/ege/rollback",
            data={"institution_id": "test-inst-id", "confirm": "no"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=not_confirmed" in response.headers["location"]

    def test_ege_rollback_with_confirm_redirects(self):
        """POST /console/ege/rollback with confirm=yes redirects (may fail due to no pinned release)."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/ege/rollback",
            data={"institution_id": "test-inst-id", "confirm": "yes", "reason": "Test rollback"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        # Should redirect - either success or error (no pinned release)
        assert response.status_code == 303
        assert "/console/ege?" in response.headers["location"]


class TestConsoleEGENavLink:
    """Test that EGE nav link appears in base template (Etapa 3.5)."""

    def test_base_template_has_ege_nav_link(self):
        """Navigation includes EGE link when institution_id is set."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/status?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "/console/ege" in response.text
        assert ">EGE<" in response.text


class TestConsolePostEndpointsAllowed:
    """Verify that allowed POST endpoints work (Etapa 3.4-3.5)."""

    def test_mandates_post_routes_allowed(self):
        """POST routes for mandates are accessible (not blocked by read-only check)."""
        client = TestClient(app, raise_server_exceptions=False)

        # This should return 400 (bad request) not 405 (method not allowed)
        response = client.post(
            "/console/mandates/proposals",
            data={
                "institution_id": "test-inst-id",
                "operation": "create",
                "mandate_id": "M001",
                "mandate_data": "{}",  # invalid but should be processed
                "reason": "test",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # Should not be 405 Method Not Allowed - POST should be routed
        assert response.status_code != 405

    def test_ege_rollback_post_route_allowed(self):
        """POST route for EGE rollback is accessible."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/console/ege/rollback",
            data={
                "institution_id": "test-inst-id",
                "confirm": "yes",
            },
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        # Should redirect, not 405
        assert response.status_code == 303


# =============================================================================
# Etapa 3.6: Legacy Console Tests
# =============================================================================


class TestConsoleLegacyAuth:
    """Test legacy console authentication (Etapa 3.6)."""

    def test_legacy_list_requires_admin_token(self):
        """GET /console/legacy without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/legacy?institution_id=test-inst-id")

        assert response.status_code == 401
        data = response.json()
        assert data.get("code") == "CONSOLE_UNAUTHORIZED" or data.get("detail", {}).get("code") == "CONSOLE_UNAUTHORIZED"

    def test_legacy_detail_requires_admin_token(self):
        """GET /console/legacy/{asset_id} without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/legacy/test-asset?institution_id=test-inst-id")

        assert response.status_code == 401
        data = response.json()
        assert data.get("code") == "CONSOLE_UNAUTHORIZED" or data.get("detail", {}).get("code") == "CONSOLE_UNAUTHORIZED"

    def test_legacy_verify_requires_admin_token(self):
        """POST /console/legacy/{asset_id}/verify without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/legacy/test-asset/verify",
            data={"institution_id": "test-inst-id"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data.get("code") == "CONSOLE_UNAUTHORIZED" or data.get("detail", {}).get("code") == "CONSOLE_UNAUTHORIZED"


class TestConsoleLegacyList:
    """Test legacy console list page (Etapa 3.6)."""

    def test_legacy_list_returns_html(self):
        """GET /console/legacy returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Legacy Assets" in response.text

    def test_legacy_list_shows_bridge_available(self):
        """GET /console/legacy shows bridge available badge."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Bridge is available (registry initializes successfully)
        assert "Bridge Available" in response.text or "bridge_available" in response.text.lower()

    def test_legacy_list_shows_empty_state(self):
        """GET /console/legacy shows empty state when no assets."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "No legacy assets registered" in response.text


class TestConsoleLegacyDetail:
    """Test legacy console detail page (Etapa 3.6)."""

    def test_legacy_detail_asset_not_found(self):
        """GET /console/legacy/{asset_id} returns 404 for nonexistent asset."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy/nonexistent-asset?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data.get("detail", {}).get("code") == "ASSET_NOT_FOUND" or "ASSET_NOT_FOUND" in str(data)

    def test_legacy_detail_requires_institution_id(self):
        """GET /console/legacy/{asset_id} without institution_id returns 422."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy/test-asset",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 422


class TestConsoleLegacyVerify:
    """Test legacy console verify action (Etapa 3.6)."""

    def test_legacy_verify_redirects(self):
        """POST /console/legacy/{asset_id}/verify redirects with result."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/legacy/test-asset/verify",
            data={"institution_id": "test-inst-id"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        # Should redirect (303 See Other)
        assert response.status_code == 303
        # Redirect should include verify_result
        assert "verify_result=" in response.headers["location"]
        # Asset not found -> ERROR
        assert "ERROR" in response.headers["location"]

    def test_legacy_verify_preserves_dept_id(self):
        """POST /console/legacy/{asset_id}/verify preserves dept_id in redirect."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/legacy/test-asset/verify",
            data={"institution_id": "test-inst-id", "dept_id": "RH"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "dept_id=RH" in response.headers["location"]


class TestConsoleLegacyWithAsset:
    """Test legacy console with actual registered asset (Etapa 3.6)."""

    @pytest.fixture
    def registered_asset(self, tmp_path, monkeypatch):
        """Create a registered legacy asset for testing."""
        # Set up data root (legacy_bridge uses get_institution_root which uses ENGINE_DATA_ROOT)
        data_root = tmp_path / "data"
        data_root.mkdir(parents=True)
        monkeypatch.setenv("ENGINE_DATA_ROOT", str(data_root))

        # Set up institution directory under data_root
        inst_dir = data_root / "institutions" / "test-inst-id"
        inst_dir.mkdir(parents=True)

        # Create a test file to register
        test_file = inst_dir / "test_data.csv"
        test_file.write_text("col1,col2\nval1,val2\n")

        # Register the asset
        from engine.legacy_bridge import LegacyBridgeRegistry
        registry = LegacyBridgeRegistry("test-inst-id")
        asset = registry.register(
            asset_id="test-csv-asset",
            name="Test CSV Data",
            source_location="test_data.csv",
            source_format="csv",
            source_type="file",
            description="Test CSV file for console tests",
            actor_id="test-setup",
        )

        return {"asset": asset, "file_path": test_file, "inst_dir": inst_dir}

    def test_legacy_list_shows_registered_asset(self, registered_asset):
        """GET /console/legacy shows registered asset."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Test CSV Data" in response.text
        assert "test-csv-asset" in response.text

    def test_legacy_detail_shows_asset(self, registered_asset):
        """GET /console/legacy/{asset_id} shows asset details."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy/test-csv-asset?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Test CSV Data" in response.text
        assert "test_data.csv" in response.text
        assert "csv" in response.text

    def test_legacy_verify_match(self, registered_asset):
        """POST verify returns MATCH when content unchanged."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/legacy/test-csv-asset/verify",
            data={"institution_id": "test-inst-id"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "verify_result=MATCH" in response.headers["location"]

    def test_legacy_verify_drift_detected(self, registered_asset):
        """POST verify returns DRIFT_DETECTED when content changed."""
        # Modify the file to cause drift
        registered_asset["file_path"].write_text("col1,col2\nmodified,data\n")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/legacy/test-csv-asset/verify",
            data={"institution_id": "test-inst-id"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "verify_result=DRIFT_DETECTED" in response.headers["location"]

    def test_legacy_verify_missing(self, registered_asset):
        """POST verify returns MISSING when source file deleted."""
        # Delete the source file
        registered_asset["file_path"].unlink()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/legacy/test-csv-asset/verify",
            data={"institution_id": "test-inst-id"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "verify_result=MISSING" in response.headers["location"]

    def test_legacy_detail_shows_verify_result_match(self, registered_asset):
        """GET detail with verify_result=MATCH shows success message."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy/test-csv-asset?institution_id=test-inst-id&verify_result=MATCH",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Verification passed" in response.text

    def test_legacy_detail_shows_verify_result_drift(self, registered_asset):
        """GET detail with verify_result=DRIFT_DETECTED shows error message."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/legacy/test-csv-asset?institution_id=test-inst-id&verify_result=DRIFT_DETECTED",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Drift detected" in response.text


class TestConsoleLegacyPostRouteAllowed:
    """Verify legacy POST route is allowed (Etapa 3.6)."""

    def test_legacy_verify_post_route_allowed(self):
        """POST route for legacy verify is accessible."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/console/legacy/test-asset/verify",
            data={"institution_id": "test-inst-id"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        # Should redirect (303), not 405 (Method Not Allowed)
        assert response.status_code == 303


# =============================================================================
# Etapa 3.7: Intake Assistido Tests
# =============================================================================


class TestConsoleIntakeAuth:
    """Test intake console authentication (Etapa 3.7)."""

    def test_intake_page_requires_admin_token(self):
        """GET /console/intake without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/intake?institution_id=test-inst-id")

        assert response.status_code == 401

    def test_intake_post_requires_admin_token(self):
        """POST /console/intake without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/intake",
            data={"institution_id": "test-inst-id", "input_text": "test"},
        )

        assert response.status_code == 401

    def test_intake_finalize_requires_admin_token(self):
        """POST /console/intake/finalize without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/intake/finalize",
            data={"institution_id": "test-inst-id", "draft_json": "{}"},
        )

        assert response.status_code == 401


class TestConsoleIntakePage:
    """Test intake console page (Etapa 3.7)."""

    def test_intake_page_returns_html(self):
        """GET /console/intake returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/intake?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Intake Assistido" in response.text

    def test_intake_page_nl_mode_default(self):
        """GET /console/intake defaults to NL mode."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/intake?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Modo NL" in response.text
        assert "linguagem natural" in response.text.lower()

    def test_intake_page_dsl_mode(self):
        """GET /console/intake with mode=dsl shows DSL mode."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/intake?institution_id=test-inst-id&mode=dsl",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Modo DSL" in response.text
        assert "IDL v1.2.2" in response.text


class TestConsoleIntakeNLMode:
    """Test intake NL mode (Etapa 3.7)."""

    def test_intake_nl_generates_draft(self):
        """POST /console/intake with NL text generates draft."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/intake",
            data={
                "institution_id": "test-inst-id",
                "mode": "nl",
                "input_text": "Employees can create expenses up to $5000. Manager approval required for amounts over $1000.",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Should show draft page with gaps
        assert "Rascunho" in response.text or "draft" in response.text.lower()

    def test_intake_nl_shows_gaps(self):
        """POST /console/intake shows detected gaps."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/intake",
            data={
                "institution_id": "test-inst-id",
                "mode": "nl",
                "input_text": "Employees can create expenses.",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Should show gaps section
        assert "Lacunas" in response.text or "gaps" in response.text.lower() or "Pronto para Finalizar" in response.text


class TestConsoleIntakeDSLMode:
    """Test intake DSL mode (Etapa 3.7)."""

    def test_intake_dsl_valid_generates_ir(self):
        """POST /console/intake with valid DSL generates IR."""
        client = TestClient(app, raise_server_exceptions=False)

        # Valid IDL DSL v1.2.2 syntax (uses colons not equals)
        # Authentication must be: none, basic, token, oauth2, or certificate
        dsl_text = """
system TestSystem {
    name: "Test System"
    domain: "test"
}

actors {
    human employee {
        name: "Employee"
        authentication: oauth2
        permissions: [expense.create]
    }
}
"""
        response = client.post(
            "/console/intake",
            data={
                "institution_id": "test-inst-id",
                "mode": "dsl",
                "input_text": dsl_text,
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Should show result page with IR
        assert "IDL Final" in response.text or "ir_version" in response.text

    def test_intake_dsl_invalid_shows_error(self):
        """POST /console/intake with invalid DSL shows error."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/intake",
            data={
                "institution_id": "test-inst-id",
                "mode": "dsl",
                "input_text": "invalid dsl syntax {{{{",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Should show error
        assert "Erro" in response.text or "Error" in response.text


class TestConsoleIntakeFinalize:
    """Test intake finalize (Etapa 3.7)."""

    def test_intake_finalize_produces_idl(self):
        """POST /console/intake/finalize produces final IDL."""
        client = TestClient(app, raise_server_exceptions=False)

        draft = {
            "name": "test-policy",
            "version": "1.0",
            "rbac": {
                "version": "1.0",
                "name": "rbac",
                "roles": [
                    {"name": "employee", "permissions": ["expense.create"]},
                ],
            },
        }

        import json
        response = client.post(
            "/console/intake/finalize",
            data={
                "institution_id": "test-inst-id",
                "draft_json": json.dumps(draft),
                "gaps_json": "[]",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "IDL Final" in response.text or "Finalizado" in response.text

    def test_intake_finalize_with_required_gaps_fails(self):
        """POST /console/intake/finalize with required gaps fails without allow_gaps."""
        client = TestClient(app, raise_server_exceptions=False)

        draft = {"name": "test-policy", "version": "1.0"}
        gaps = [{
            "gap_key": "gap-test",
            "gap_type": "approval",
            "severity": "required",
            "description": "Test required gap",
            "policy_ref": "test",
            "questions": [],
        }]

        import json
        response = client.post(
            "/console/intake/finalize",
            data={
                "institution_id": "test-inst-id",
                "draft_json": json.dumps(draft),
                "gaps_json": json.dumps(gaps),
                "allow_gaps": "false",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Should show error about required gaps
        assert "required" in response.text.lower() or "Erro" in response.text

    def test_intake_finalize_with_allow_gaps_succeeds(self):
        """POST /console/intake/finalize with allow_gaps=true succeeds."""
        client = TestClient(app, raise_server_exceptions=False)

        draft = {
            "name": "test-policy",
            "version": "1.0",
            "rbac": {"version": "1.0", "name": "rbac", "roles": []},
        }
        gaps = [{
            "gap_key": "gap-test",
            "gap_type": "approval",
            "severity": "required",
            "description": "Test required gap",
            "policy_ref": "test",
            "questions": [],
        }]

        import json
        response = client.post(
            "/console/intake/finalize",
            data={
                "institution_id": "test-inst-id",
                "draft_json": json.dumps(draft),
                "gaps_json": json.dumps(gaps),
                "allow_gaps": "true",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        # Should show result with warnings
        assert "Avisos" in response.text or "_warnings" in response.text or "IDL Final" in response.text


class TestConsoleIntakeExport:
    """Test intake export (Etapa 3.7)."""

    def test_intake_export_ir_json(self):
        """GET /console/intake/export returns JSON download."""
        client = TestClient(app, raise_server_exceptions=False)

        import json
        idl = {"name": "test-policy", "version": "1.0"}

        response = client.get(
            f"/console/intake/export?institution_id=test-inst-id&format=ir&idl_json={json.dumps(idl)}",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")

    def test_intake_export_dsl_not_implemented(self):
        """GET /console/intake/export with format=dsl returns 501."""
        client = TestClient(app, raise_server_exceptions=False)

        import json
        idl = {"name": "test-policy", "version": "1.0"}

        response = client.get(
            f"/console/intake/export?institution_id=test-inst-id&format=dsl&idl_json={json.dumps(idl)}",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 501
        assert "DSL_EXPORT_NOT_IMPLEMENTED" in response.text


class TestConsoleIntakeNavLink:
    """Test intake nav link in base template (Etapa 3.7)."""

    def test_base_template_has_intake_nav_link(self):
        """Console pages have Intake nav link."""
        client = TestClient(app, raise_server_exceptions=False)
        # Use intake page itself since it has institution_id and shows the nav
        response = client.get(
            "/console/intake?institution_id=test-inst-id",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "/console/intake" in response.text
        assert "Intake" in response.text


# =============================================================================
# Etapa 4.1: Browser Auth Tests
# =============================================================================


class TestConsoleBrowserAuthLogin:
    """Test browser login functionality (Etapa 4.1)."""

    def test_login_page_accessible_without_auth(self):
        """GET /console/login is accessible without auth."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/login")

        assert response.status_code == 200
        assert "Login" in response.text or "login" in response.text.lower()

    def test_login_page_shows_form(self):
        """Login page shows token form."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/login")

        assert response.status_code == 200
        assert "form" in response.text.lower()
        assert "token" in response.text.lower()

    def test_login_post_invalid_token_shows_error(self):
        """POST /console/login with invalid token shows error."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/login",
            data={"token": "invalid-token", "next": "/console/"},
        )

        assert response.status_code == 401
        assert "Invalid" in response.text or "invalid" in response.text.lower()

    def test_login_post_valid_token_sets_cookie(self):
        """POST /console/login with valid token sets session cookie."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/login",
            data={"token": "test-admin-token", "next": "/console/"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "console_session" in response.headers.get("set-cookie", "")

    def test_login_post_redirects_to_next(self):
        """POST /console/login redirects to next parameter."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/console/login",
            data={"token": "test-admin-token", "next": "/console/status?institution_id=test"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers.get("location") == "/console/status?institution_id=test"


class TestConsoleBrowserAuthLogout:
    """Test browser logout functionality (Etapa 4.1)."""

    def test_logout_clears_cookie(self):
        """GET /console/logout clears session cookie."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/logout", follow_redirects=False)

        assert response.status_code == 303
        # Cookie should be cleared with max_age=0
        set_cookie = response.headers.get("set-cookie", "")
        assert "console_session=" in set_cookie
        assert "max-age=0" in set_cookie.lower() or "max-age=" not in set_cookie.lower()

    def test_logout_redirects_to_login(self):
        """GET /console/logout redirects to login page."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/logout", follow_redirects=False)

        assert response.status_code == 303
        assert "/console/login" in response.headers.get("location", "")


class TestConsoleBrowserAuthCookieAuth:
    """Test cookie-based authentication (Etapa 4.1)."""

    def test_console_accepts_cookie_auth(self):
        """Console page accessible with valid session cookie."""
        client = TestClient(app, raise_server_exceptions=False)

        # First login to get a cookie
        login_response = client.post(
            "/console/login",
            data={"token": "test-admin-token", "next": "/console/"},
            follow_redirects=False,
        )
        assert login_response.status_code == 303

        # Extract cookie value (simplified)
        cookies = login_response.cookies

        # Now access console with cookie
        response = client.get("/console/", cookies=cookies)
        assert response.status_code == 200

    def test_console_header_auth_still_works(self):
        """X-Admin-Token header still works for auth."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200


class TestConsoleBrowserAuthHtmlRedirect:
    """Test HTML request redirect to login (Etapa 4.1)."""

    def test_html_request_without_auth_redirects_to_login(self):
        """HTML request without auth redirects to login page."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/",
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/console/login" in response.headers.get("location", "")

    def test_json_request_without_auth_returns_401(self):
        """JSON request without auth returns 401 JSON error."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/",
            headers={"Accept": "application/json"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "CONSOLE_UNAUTHORIZED"


class TestConsoleBrowserAuthCSRF:
    """Test CSRF protection for POST routes (Etapa 4.1)."""

    def test_post_with_cookie_without_csrf_fails(self):
        """POST with cookie auth but no CSRF token fails."""
        client = TestClient(app, raise_server_exceptions=False)

        # Login first
        login_response = client.post(
            "/console/login",
            data={"token": "test-admin-token", "next": "/console/"},
            follow_redirects=False,
        )
        cookies = login_response.cookies

        # Try POST without CSRF
        response = client.post(
            "/console/intake",
            data={
                "institution_id": "test-inst-id",
                "mode": "nl",
                "input_text": "test policy",
            },
            cookies=cookies,
        )

        assert response.status_code == 403
        assert "CSRF" in response.text or "csrf" in response.text.lower()

    def test_post_with_header_auth_no_csrf_required(self):
        """POST with header auth doesn't require CSRF token."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/console/intake",
            data={
                "institution_id": "test-inst-id",
                "mode": "nl",
                "input_text": "test policy",
            },
            headers={"X-Admin-Token": "test-admin-token"},
        )

        # Should work (may return error from NL processing, but not 403)
        assert response.status_code != 403


class TestConsoleBrowserAuthNavLogout:
    """Test logout link in navigation (Etapa 4.1)."""

    def test_base_template_has_logout_link(self):
        """Console pages have Logout link."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "/console/logout" in response.text
        assert "Logout" in response.text


# =============================================================================
# Onboarding Tests (Etapa 4.2)
# =============================================================================


class TestOnboardingAuth:
    """Test onboarding authentication requirements (Etapa 4.2)."""

    def test_onboarding_without_token_returns_401(self):
        """GET /console/onboarding without token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/console/onboarding")

        assert response.status_code == 401

    def test_onboarding_with_token_returns_html(self):
        """GET /console/onboarding with valid token returns HTML."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/onboarding",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Institution Onboarding" in response.text


class TestOnboardingWizardSteps:
    """Test onboarding wizard step navigation (Etapa 4.2)."""

    def test_onboarding_step1_shows_create_form(self):
        """Step 1 shows institution creation form."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/onboarding?step=1",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Create or Select Institution" in response.text
        assert 'name="slug"' in response.text

    def test_onboarding_step2_requires_institution_id(self):
        """Step 2 shows template selection when institution_id provided."""
        # First create an institution
        client = TestClient(app, raise_server_exceptions=False)
        registry = get_registry()
        inst, _, _ = registry.create(slug="test-onboarding", display_name="Test Onboarding")

        response = client.get(
            f"/console/onboarding?step=2&institution_id={inst.institution_id}",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Choose Template" in response.text
        assert "Finance Pilot" in response.text
        assert "Multi-Department Pilot" in response.text


class TestOnboardingCreateInstitution:
    """Test institution creation via onboarding (Etapa 4.2)."""

    def test_create_institution_with_valid_slug(self):
        """POST /console/onboarding/create-institution creates institution and redirects."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/console/onboarding/create-institution",
            data={"slug": "new-test-inst", "display_name": "New Test"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/console/onboarding?step=2" in response.headers["location"]
        assert "institution_id=" in response.headers["location"]

    def test_create_institution_with_invalid_slug(self):
        """POST with invalid slug redirects with error."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/console/onboarding/create-institution",
            data={"slug": "AB"},  # Too short
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=" in response.headers["location"]

    def test_create_institution_with_duplicate_slug(self):
        """POST with duplicate slug redirects with error."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create first institution
        registry = get_registry()
        registry.create(slug="duplicate-slug")

        # Try to create another with same slug
        response = client.post(
            "/console/onboarding/create-institution",
            data={"slug": "duplicate-slug"},
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=" in response.headers["location"]


class TestOnboardingGenerateBundle:
    """Test bundle generation via onboarding (Etapa 4.2)."""

    def test_generate_bundle_happy_path(self, tmp_path, monkeypatch):
        """POST /console/onboarding/generate-bundle generates bundle and verifies."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create institution
        registry = get_registry()
        inst, _, _ = registry.create(slug="bundle-test", display_name="Bundle Test")

        response = client.post(
            "/console/onboarding/generate-bundle",
            data={
                "institution_id": inst.institution_id,
                "template_id": "finance-pilot",
            },
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        # On success, should redirect to step 4
        assert "/console/onboarding?step=4" in response.headers["location"]
        assert f"institution_id={inst.institution_id}" in response.headers["location"]

    def test_generate_bundle_invalid_template(self):
        """POST with invalid template redirects with error."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create institution
        registry = get_registry()
        inst, _, _ = registry.create(slug="invalid-template-test")

        response = client.post(
            "/console/onboarding/generate-bundle",
            data={
                "institution_id": inst.institution_id,
                "template_id": "nonexistent-template",
            },
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=" in response.headers["location"]

    def test_generate_bundle_invalid_institution(self):
        """POST with invalid institution redirects with error."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/console/onboarding/generate-bundle",
            data={
                "institution_id": "00000000-0000-0000-0000-000000000099",
                "template_id": "finance-pilot",
            },
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=" in response.headers["location"]


class TestOnboardingProofResult:
    """Test proof result display in onboarding (Etapa 4.2)."""

    def test_proof_result_shows_success_after_generation(self, tmp_path, monkeypatch):
        """Step 4 shows successful proof result after bundle generation."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create institution
        registry = get_registry()
        inst, _, _ = registry.create(slug="proof-test", display_name="Proof Test")

        # Generate bundle
        client.post(
            "/console/onboarding/generate-bundle",
            data={
                "institution_id": inst.institution_id,
                "template_id": "finance-pilot",
            },
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        # Check step 4
        response = client.get(
            f"/console/onboarding?step=4&institution_id={inst.institution_id}",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "Bundle Verification" in response.text
        # Should show success (proof passed)
        assert "verified successfully" in response.text or "Bundle Details" in response.text


class TestOnboardingProofRedirect:
    """Test onboarding proof redirect endpoint (Etapa 4.2)."""

    def test_onboarding_proof_redirects_to_step4(self):
        """GET /console/onboarding/proof redirects to step 4."""
        client = TestClient(app, raise_server_exceptions=False)

        # Create institution
        registry = get_registry()
        inst, _, _ = registry.create(slug="proof-redirect-test")

        response = client.get(
            f"/console/onboarding/proof?institution_id={inst.institution_id}",
            headers={"X-Admin-Token": "test-admin-token"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "/console/onboarding?step=4" in response.headers["location"]


class TestOnboardingNavLink:
    """Test onboarding link in navigation (Etapa 4.2)."""

    def test_base_template_has_onboarding_link(self):
        """Console pages have Onboarding link in nav."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/console/",
            headers={"X-Admin-Token": "test-admin-token"},
        )

        assert response.status_code == 200
        assert "/console/onboarding" in response.text
        assert "Onboarding" in response.text


class TestOnboardingTemplateRegistry:
    """Test template registry functionality (Etapa 4.2)."""

    def test_list_templates_returns_available_templates(self):
        """list_templates() returns available bundle templates."""
        from engine.console.templates_registry import list_templates

        templates = list_templates()

        assert len(templates) >= 2
        template_ids = [t.id for t in templates]
        assert "finance-pilot" in template_ids
        assert "multi-pilot" in template_ids

    def test_get_template_returns_template_by_id(self):
        """get_template() returns template by ID."""
        from engine.console.templates_registry import get_template

        template = get_template("finance-pilot")

        assert template is not None
        assert template.id == "finance-pilot"
        assert template.name == "Finance Pilot"
        assert "finance" in template.departments

    def test_get_template_returns_none_for_unknown(self):
        """get_template() returns None for unknown ID."""
        from engine.console.templates_registry import get_template

        template = get_template("nonexistent")

        assert template is None


class TestOnboardingBundleGenerator:
    """Test bundle generator functionality (Etapa 4.2)."""

    def test_generate_bundle_creates_directory(self, tmp_path, monkeypatch):
        """generate_bundle_from_template() creates bundle directory."""
        from engine.console.bundle_generator import generate_bundle_from_template
        from engine.core.data_root import get_institution_root

        # Create institution
        registry = get_registry()
        inst, _, _ = registry.create(slug="bundle-gen-test")

        result = generate_bundle_from_template(
            institution_id=inst.institution_id,
            template_id="finance-pilot",
        )

        # Should succeed
        assert result.success is True
        assert result.bundle_path is not None
        assert result.bundle_path.exists()
        assert result.proof_result is not None
        assert result.proof_result.passed is True

        # CURRENT symlink should exist
        institution_root = get_institution_root(inst.institution_id)
        current_symlink = institution_root / "bundles" / "CURRENT"
        assert current_symlink.is_symlink()

    def test_generate_bundle_invalid_template_fails(self, tmp_path, monkeypatch):
        """generate_bundle_from_template() fails for invalid template."""
        from engine.console.bundle_generator import generate_bundle_from_template

        # Create institution
        registry = get_registry()
        inst, _, _ = registry.create(slug="invalid-template-gen-test")

        result = generate_bundle_from_template(
            institution_id=inst.institution_id,
            template_id="nonexistent-template",
        )

        assert result.success is False
        assert result.error_code == "TEMPLATE_NOT_FOUND"

    def test_generate_bundle_invalid_institution_fails(self, tmp_path, monkeypatch):
        """generate_bundle_from_template() fails for invalid institution."""
        from engine.console.bundle_generator import generate_bundle_from_template

        result = generate_bundle_from_template(
            institution_id="00000000-0000-0000-0000-000000000999",
            template_id="finance-pilot",
        )

        assert result.success is False
        assert "NOT_FOUND" in result.error_code


class TestOnboardingMutableRoutes:
    """Test that onboarding POST routes are included in mutable routes check."""

    def test_onboarding_post_routes_are_mutable(self):
        """Onboarding POST routes should be recognized as mutable."""
        # These routes should require CSRF when using cookie auth
        mutable_routes = [
            "/console/onboarding/create-institution",
            "/console/onboarding/generate-bundle",
        ]

        # Get all routes from the app
        from engine.api.server import app

        post_routes = []
        for route in app.routes:
            if hasattr(route, "methods") and "POST" in route.methods:
                post_routes.append(route.path)

        for mutable_route in mutable_routes:
            assert mutable_route in post_routes, f"{mutable_route} should be a POST route"
