"""Tests for one-time admin key bootstrap via X-Admin-Token (non-default institutions)."""

import json

import pytest
from fastapi.testclient import TestClient

from engine.api.server import app
from engine.core.admin_keys import reset_admin_keys_registry
from engine.core.institution_config import reset_config_cache
from engine.core.institutions import reset_registry


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "registry.jsonl"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "institutions"))
    monkeypatch.setenv("ENGINE_ISE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", str(tmp_path / "bundle"))

    # Minimal bundle placeholder (admin APIs do not depend on bundle content, but loader expects a path).
    bundle_path = tmp_path / "bundle"
    bundle_path.mkdir(parents=True, exist_ok=True)
    with open(bundle_path / "manifest.json", "w") as f:
        json.dump({"bundle_hash": "test-hash", "contracts": [], "mode": "single"}, f)

    reset_registry()
    reset_config_cache()
    reset_admin_keys_registry()
    yield
    reset_registry()
    reset_config_cache()
    reset_admin_keys_registry()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_bootstrap_first_admin_key_non_default(client):
    # Create institution (global admin token)
    resp = client.post(
        "/admin/institutions",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"slug": "bazari-bootstrap-test"},
    )
    assert resp.status_code == 201
    institution_id = resp.json()["institution_id"]

    # Bootstrap first key for non-default institution (allowed once)
    resp = client.post(
        f"/admin/institutions/{institution_id}/admin-keys",
        headers={"X-Admin-Token": "test-admin-token"},
        json={},
    )
    assert resp.status_code == 201
    first_key = resp.json()
    assert "plaintext_secret" in first_key

    # Second bootstrap via token must be blocked deterministically
    resp = client.post(
        f"/admin/institutions/{institution_id}/admin-keys",
        headers={"X-Admin-Token": "test-admin-token"},
        json={},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "ADMIN_KEY_BOOTSTRAP_NOT_ALLOWED"

    # Creating additional keys requires X-Admin-Key
    resp = client.post(
        f"/admin/institutions/{institution_id}/admin-keys",
        headers={"X-Admin-Key": first_key["plaintext_secret"]},
        json={},
    )
    assert resp.status_code == 201
    assert "key_id" in resp.json()

