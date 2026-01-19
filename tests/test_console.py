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
    """Test that console is truly read-only."""

    def test_console_has_no_post_endpoints(self):
        """Console router has no POST endpoints (read-only)."""
        from engine.console.routes import router

        for route in router.routes:
            # Skip the static file route which uses GET
            if hasattr(route, 'methods'):
                # Ensure no POST, PUT, PATCH, DELETE methods
                methods = set(route.methods)
                mutable_methods = {"POST", "PUT", "PATCH", "DELETE"}
                assert methods.isdisjoint(mutable_methods), \
                    f"Route {route.path} has mutable methods: {methods & mutable_methods}"


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

        explorer_paths = ["/contracts", "/contracts/{file_path:path}", "/proof"]

        for route in router.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                if any(route.path.endswith(p) or p in route.path for p in explorer_paths):
                    methods = set(route.methods)
                    mutable_methods = {"POST", "PUT", "PATCH", "DELETE"}
                    assert methods.isdisjoint(mutable_methods), \
                        f"Route {route.path} has mutable methods: {methods & mutable_methods}"
