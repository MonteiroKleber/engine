"""E2E (HTTP) proof for Finance in ENGINE_API_MODE=idl + ENGINE_AUTH_MODE=strict.

This is the hard-gate test referenced by docs/specs/migracao/02-finance-reference-idl-mode/spec.md.
"""

import importlib
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
def _reset_globals(monkeypatch):
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


def _make_app(monkeypatch, tmp_path: Path, bundle_path: Path):
    data_root = tmp_path / "data_root"
    institutions_dir = tmp_path / "institutions"
    institutions_registry = tmp_path / "institutions_registry.jsonl"

    monkeypatch.setenv("ENGINE_API_MODE", "idl")
    monkeypatch.setenv("ENGINE_AUTH_MODE", "strict")
    monkeypatch.setenv("ENGINE_INSTALL_MODE", "dev")
    monkeypatch.setenv("ENGINE_CONSOLE_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")
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
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": slug, "display_name": "Test"},
    )
    assert resp.status_code in (200, 201), resp.text
    institution_id = resp.json()["institution_id"]

    resp = client.post(
        f"/admin/institutions/{institution_id}/admin-keys",
        headers={"X-Admin-Token": "test-admin-token"},
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


def test_finance_flow_strict_idl_mode(tmp_path: Path, monkeypatch):
    app = _make_app(monkeypatch, tmp_path, Path("bundles/finance-pilot").resolve())

    with TestClient(app) as client:
        institution_id, admin_key = _create_institution_and_admin_key(client)
        analyst_token = _create_actor_token(client, institution_id, admin_key, "analyst")
        manager_token = _create_actor_token(client, institution_id, admin_key, "manager")

        # Create expense (analyst)
        resp = client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": analyst_token},
            json={"amount": 100, "description": "e2e"},
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert data["status"] == "pending_approval"
        approval_id = data["approval_id"]

        # Analyst cannot decide approvals
        resp = client.post(
            f"/approvals/{approval_id}/decide",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": analyst_token},
            json={"decision": "approve"},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json().get("code") == "APPROVAL_FORBIDDEN"

        # Manager decides
        resp = client.post(
            f"/approvals/{approval_id}/decide",
            headers={"X-Institution-Id": institution_id, "X-Actor-Token": manager_token},
            json={"decision": "approve"},
        )
        assert resp.status_code == 200, resp.text
        decide = resp.json()
        assert decide["decision"] == "approve"
        assert decide["case_status"] == "COMMITTED"


def test_strict_rejects_missing_actor_token(tmp_path: Path, monkeypatch):
    app = _make_app(monkeypatch, tmp_path, Path("bundles/finance-pilot").resolve())

    with TestClient(app) as client:
        institution_id, _admin_key = _create_institution_and_admin_key(client)
        resp = client.get(
            "/health",
            headers={"X-Institution-Id": institution_id},
        )
        assert resp.status_code == 200

        resp = client.post(
            "/finance/expenses",
            headers={"X-Institution-Id": institution_id},
            json={"amount": 1, "description": "no token"},
        )
        assert resp.status_code == 401
        assert resp.json().get("code") == "ACTOR_TOKEN_REQUIRED"
