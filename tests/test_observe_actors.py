"""Basic coverage for /v1/observe/* endpoints.

Ensures the observe router is registered and returns deterministic shape.
"""

import importlib
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


def test_observe_actors_lists_admin_activity(tmp_path: Path, monkeypatch):
    app = _make_app(monkeypatch, tmp_path, Path("bundles/finance-pilot").resolve())

    with TestClient(app) as client:
        # Create institution (emits ADMIN auth events to ledger)
        slug = f"t-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/admin/institutions",
            headers={"X-Admin-Token": "test-admin-token"},
            json={"slug": slug, "display_name": "Test"},
        )
        assert resp.status_code in (200, 201), resp.text
        institution_id = resp.json()["institution_id"]

        # Bootstrap admin key
        resp = client.post(
            f"/admin/institutions/{institution_id}/admin-keys",
            headers={"X-Admin-Token": "test-admin-token"},
            json={},
        )
        assert resp.status_code in (200, 201), resp.text
        admin_key = resp.json()["plaintext_secret"]

        # Create an actor token (generates non-ADMIN ledger events too)
        resp = client.post(
            f"/admin/institutions/{institution_id}/actors",
            headers={"X-Institution-Id": institution_id, "X-Admin-Key": admin_key},
            json={"actor_id": str(uuid.uuid4()), "roles": ["analyst"]},
        )
        assert resp.status_code == 200, resp.text

        # Observe
        resp = client.get(
            "/v1/observe/actors",
            params={"limit": 5},
            headers={"X-Institution-Id": institution_id, "X-Admin-Key": admin_key},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data.get("items"), list)
        assert data.get("next_cursor") is None

        # Should include the legacy admin actor_id used by admin auth telemetry.
        actor_ids = {item.get("actor_id") for item in data["items"]}
        assert "ADMIN" in actor_ids

