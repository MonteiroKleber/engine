"""E2E: Bazari Phase 1 bundle must be bootable in PROD/STRICT/IDL.

This test compiles `docs/bazari/idl/bazari-phase1.idl` via the canonical path:
DSL v1.2.2 → IRCS v1 → ISE → bundle → proof offline → boot → CRUD flow.
"""

import importlib
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.idl_dsl import parse_dsl
from engine.ise.compiler import compile_from_ircs
from engine.loader.verify_hashes import compute_sha256
from engine.proof.verify import verify_bundle_offline

from engine.core.actor_tokens import ActorTokensRegistry
from engine.core.autonomy import reset_all_autonomy
from engine.core.governed_autonomy import invalidate_all_autonomy_cache
from engine.core.governed_mandates import invalidate_all_mandates_cache
from engine.core.governed_policies import invalidate_all_policies_cache
from engine.core.institutions import reset_registry
from engine.core.ledger import reset_institution_ledgers
from engine.core.mandates import clear_all_mandates
from engine.core.operations import reset_all_operations
from engine.core.policy import clear_all_policies
from engine.core.runtime_state import runtime_state
from engine.core.state_store import reset_all_state_stores
from engine.loader.load_bundle import _set_bundle_context


@pytest.fixture(autouse=True)
def _reset_globals():
    runtime_state.set_active()
    reset_all_operations()
    reset_all_state_stores()
    reset_institution_ledgers()
    clear_all_policies()
    clear_all_mandates()
    reset_all_autonomy()
    invalidate_all_policies_cache()
    invalidate_all_mandates_cache()
    invalidate_all_autonomy_cache()
    _set_bundle_context(None)
    reset_registry()
    ActorTokensRegistry.reset_instance()
    yield


def _patch_manifest_and_ledger_for_contract(bundle_path: Path, contract_file: str) -> None:
    """Update bundle.manifest.json + contract_ledger.json for an already-written contract file."""
    manifest_path = bundle_path / "bundle.manifest.json"
    ledger_path = bundle_path / "contract_ledger.json"

    manifest = json.loads(manifest_path.read_text("utf-8"))
    ledger = json.loads(ledger_path.read_text("utf-8"))

    new_hash_hex = compute_sha256(bundle_path / contract_file)
    new_hash = f"SHA256:{new_hash_hex}"

    for c in manifest.get("contracts", []):
        if c.get("file") == contract_file:
            c["sha256"] = new_hash
            break
    else:
        raise AssertionError(f"{contract_file} not found in bundle.manifest.json contracts[]")

    for c in ledger.get("contracts", []):
        if c.get("contract_name") == contract_file:
            c["content_hash"] = new_hash
            break
    else:
        raise AssertionError(f"{contract_file} not found in contract_ledger.json contracts[]")

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), "utf-8")

    new_manifest_hash_hex = compute_sha256(manifest_path)
    ledger["manifest_hash"] = f"SHA256:{new_manifest_hash_hex}"
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True), "utf-8")


def _hydrate_institutional_contracts_for_bazari_phase1(bundle_path: Path) -> None:
    """ISE emits empty mandates/autonomy for DSL; hydrate minimal allow rules for Phase 1."""
    mandates = {
        "mandate_schema_version": "1.0",
        "mandates": [
            {
                "mandate_id": "reports-create-pre",
                "endpoint_sig": "POST /reports",
                "phase": "pre",
                "allowed_roles": ["user", "admin"],
            },
            {
                "mandate_id": "chat-reports-create-pre",
                "endpoint_sig": "POST /chat/reports",
                "phase": "pre",
                "allowed_roles": ["user", "admin"],
            },
            {
                "mandate_id": "chat-blocks-create-pre",
                "endpoint_sig": "POST /chat/blocks",
                "phase": "pre",
                "allowed_roles": ["user", "admin"],
            },
            {
                "mandate_id": "chat-blocks-delete-pre",
                "endpoint_sig": "DELETE /chat/blocks/{block_id}",
                "phase": "pre",
                "allowed_roles": ["user", "admin"],
            },
            {
                "mandate_id": "moderation-actions-create-pre",
                "endpoint_sig": "POST /moderation/actions",
                "phase": "pre",
                "allowed_roles": ["moderator", "admin"],
            },
            {
                "mandate_id": "reports-my-pre",
                "endpoint_sig": "GET /reports/my",
                "phase": "pre",
                "allowed_roles": ["user", "admin"],
            },
            {
                "mandate_id": "reports-get-pre",
                "endpoint_sig": "GET /reports/{report_id}",
                "phase": "pre",
                "allowed_roles": ["user", "moderator", "admin"],
            },
            {
                "mandate_id": "reports-list-pre",
                "endpoint_sig": "GET /moderation/reports",
                "phase": "pre",
                "allowed_roles": ["moderator", "admin"],
            },
            {
                "mandate_id": "moderation-actions-get-pre",
                "endpoint_sig": "GET /moderation/actions/{action_id}",
                "phase": "pre",
                "allowed_roles": ["moderator", "admin"],
            },
            {
                "mandate_id": "moderation-actions-list-pre",
                "endpoint_sig": "GET /moderation/actions",
                "phase": "pre",
                "allowed_roles": ["moderator", "admin"],
            },
        ],
    }

    autonomy = {
        "autonomy_schema_version": "1.0",
        "current_level": 0,
        "rules": [
            {
                "rule_id": "reports-create-pre",
                "endpoint_sig": "POST /reports",
                "phase": "pre",
                "required_level": 0,
            },
            {
                "rule_id": "chat-reports-create-pre",
                "endpoint_sig": "POST /chat/reports",
                "phase": "pre",
                "required_level": 0,
            },
            {
                "rule_id": "chat-blocks-create-pre",
                "endpoint_sig": "POST /chat/blocks",
                "phase": "pre",
                "required_level": 0,
            },
            {
                "rule_id": "chat-blocks-delete-pre",
                "endpoint_sig": "DELETE /chat/blocks/{block_id}",
                "phase": "pre",
                "required_level": 0,
            },
            {
                "rule_id": "moderation-actions-create-pre",
                "endpoint_sig": "POST /moderation/actions",
                "phase": "pre",
                "required_level": 0,
            },
            {
                "rule_id": "reports-my-pre",
                "endpoint_sig": "GET /reports/my",
                "phase": "pre",
                "required_level": 0,
            },
            {
                "rule_id": "reports-get-pre",
                "endpoint_sig": "GET /reports/{report_id}",
                "phase": "pre",
                "required_level": 0,
            },
            {
                "rule_id": "reports-list-pre",
                "endpoint_sig": "GET /moderation/reports",
                "phase": "pre",
                "required_level": 0,
            },
            {
                "rule_id": "moderation-actions-get-pre",
                "endpoint_sig": "GET /moderation/actions/{action_id}",
                "phase": "pre",
                "required_level": 0,
            },
            {
                "rule_id": "moderation-actions-list-pre",
                "endpoint_sig": "GET /moderation/actions",
                "phase": "pre",
                "required_level": 0,
            },
        ],
    }

    (bundle_path / "mandates.json").write_text(json.dumps(mandates, indent=2, sort_keys=True), "utf-8")
    _patch_manifest_and_ledger_for_contract(bundle_path, "mandates.json")

    (bundle_path / "autonomy.json").write_text(json.dumps(autonomy, indent=2, sort_keys=True), "utf-8")
    _patch_manifest_and_ledger_for_contract(bundle_path, "autonomy.json")


def _compile_bazari_phase1_bundle(tmp_path: Path) -> Path:
    idl_text = Path("docs/bazari/idl/bazari-phase1.idl").read_text("utf-8")
    ir = parse_dsl(idl_text)

    output_dir = tmp_path / "bundles_out"
    result = compile_from_ircs(ir, "bazari-phase1", str(output_dir))
    assert result.success, (result.error_code, result.error_message)

    bundle_path = Path(result.bundle_path)
    _hydrate_institutional_contracts_for_bazari_phase1(bundle_path)

    proof = verify_bundle_offline(bundle_path)
    assert proof.passed, proof.to_dict()
    return bundle_path


def _make_app(monkeypatch, tmp_path: Path, bundle_path: Path):
    data_root = tmp_path / "data_root"
    institutions_dir = tmp_path / "institutions"
    institutions_registry = tmp_path / "institutions_registry.jsonl"

    monkeypatch.setenv("ENGINE_INSTALL_MODE", "prod")
    monkeypatch.setenv("ENGINE_AUTH_MODE", "strict")
    monkeypatch.setenv("ENGINE_API_MODE", "idl")
    monkeypatch.setenv("ENGINE_CONSOLE_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token-32-chars-minimum____")
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(data_root))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(institutions_dir))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(institutions_registry))
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(bundle_path))

    import engine.api.server as server

    importlib.reload(server)
    return server.app


def _create_institution_and_admin_key(client: TestClient) -> tuple[str, str]:
    slug = f"t-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token-32-chars-minimum____"},
        json={"slug": slug, "display_name": "Test"},
    )
    assert resp.status_code in (200, 201), resp.text
    institution_id = resp.json()["institution_id"]

    resp = client.post(
        f"/admin/institutions/{institution_id}/admin-keys",
        headers={"X-Admin-Token": "test-admin-token-32-chars-minimum____"},
        json={},
    )
    assert resp.status_code in (200, 201), resp.text
    admin_key = resp.json()["plaintext_secret"]
    return institution_id, admin_key


def _create_actor_token(client: TestClient, institution_id: str, admin_key: str, role: str) -> str:
    actor_id = str(uuid.uuid4())
    resp = client.post(
        f"/admin/institutions/{institution_id}/actors",
        headers={"X-Institution-Id": institution_id, "X-Admin-Key": admin_key},
        json={"actor_id": actor_id, "roles": [role]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def test_bazari_phase1_prod_strict_idl_flow(tmp_path: Path, monkeypatch):
    bundle_path = _compile_bazari_phase1_bundle(tmp_path)
    app = _make_app(monkeypatch, tmp_path, bundle_path)

    with TestClient(app) as client:
        # Boot checks
        resp = client.get("/health")
        assert resp.status_code == 200
        resp = client.get("/console/login")
        assert resp.status_code == 200

        institution_id, admin_key = _create_institution_and_admin_key(client)
        user_token = _create_actor_token(client, institution_id, admin_key, "user")
        moderator_token = _create_actor_token(client, institution_id, admin_key, "moderator")

        # POST /reports (user)
        resp = client.post(
            "/reports",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": user_token},
            json={
                "content_type": "POST",
                "content_id": "post-123",
                "reason": "spam",
                "description": "spam",
            },
        )
        assert resp.status_code == 200, resp.text
        report_id = resp.json()["id"]

        # GET /reports/{report_id} (moderator)
        resp = client.get(
            f"/reports/{report_id}",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": moderator_token},
        )
        assert resp.status_code == 200, resp.text

        # GET /reports/my (user)
        resp = client.get(
            "/reports/my",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": user_token},
        )
        assert resp.status_code == 200, resp.text
        assert any(
            (item.get("id") or item.get("report_id")) == report_id
            for item in resp.json().get("items", [])
        )

        # GET /moderation/reports (moderator)
        resp = client.get(
            "/moderation/reports",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": moderator_token},
        )
        assert resp.status_code == 200, resp.text

        # POST /chat/reports (user)
        resp = client.post(
            "/chat/reports",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": user_token},
            json={
                "message_id": "m-1",
                "thread_id": "t-1",
                "reason": "harassment",
                "description": "bad",
            },
        )
        assert resp.status_code == 200, resp.text

        # POST /chat/blocks (user)
        resp = client.post(
            "/chat/blocks",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": user_token},
            json={"blocked_profile_id": "p-2"},
        )
        assert resp.status_code == 200, resp.text
        block_id = resp.json()["id"]

        # DELETE /chat/blocks/{block_id} (user)
        resp = client.delete(
            f"/chat/blocks/{block_id}",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": user_token},
        )
        assert resp.status_code == 200, resp.text

        # POST /moderation/actions (moderator)
        resp = client.post(
            "/moderation/actions",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": moderator_token},
            json={
                "target_type": "POST",
                "target_id": "post-123",
                "action_type": "WARN",
                "reason": "test",
            },
        )
        assert resp.status_code == 200, resp.text
        action_id = resp.json()["id"]

        # GET /moderation/actions/{action_id} (moderator)
        resp = client.get(
            f"/moderation/actions/{action_id}",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": moderator_token},
        )
        assert resp.status_code == 200, resp.text

        # GET /moderation/actions (moderator) — list semantics via read
        resp = client.get(
            "/moderation/actions",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": moderator_token},
        )
        assert resp.status_code == 200, resp.text
        assert any(
            (item.get("id") or item.get("action_id")) == action_id
            for item in resp.json().get("items", [])
        )
