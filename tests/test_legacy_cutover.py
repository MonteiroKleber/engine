"""Tests for legacy cutover telemetry (ENGINE_API_MODE=both)."""

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.core.data_root import get_institution_root
from engine.core.institution_context import DEFAULT_INSTITUTION_ID


def _make_client(tmp_path: Path, monkeypatch, api_mode: str) -> TestClient:
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "data" / "institutions"))
    monkeypatch.setenv(
        "ENGINE_INSTITUTIONS_REGISTRY_PATH", str(tmp_path / "data" / "institutions_registry.jsonl")
    )
    monkeypatch.setenv("ENGINE_BUNDLE_PATH", "bundles/finance-pilot")
    monkeypatch.setenv("ENGINE_AUTH_MODE", "dev")
    monkeypatch.setenv("ENGINE_API_MODE", api_mode)

    # Ensure server module reads env at import time (legacy routers gated there).
    import engine.api.server as server

    importlib.reload(server)
    return TestClient(server.app, raise_server_exceptions=False)


def _telemetry_file(tmp_path: Path) -> Path:
    os.environ["ENGINE_DATA_ROOT"] = str(tmp_path / "data")
    return get_institution_root(DEFAULT_INSTITUTION_ID) / "legacy_telemetry.jsonl"


def test_records_in_both_mode(tmp_path: Path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, api_mode="both")

    # Hit a legacy route (will be served by legacy router first in both mode).
    resp = client.get(
        "/finance/expenses/nonexistent",
        headers={
            "X-Actor-Id": "11111111-1111-1111-1111-111111111111",
            "X-Actor-Roles": "admin",
            "X-Institution-Id": DEFAULT_INSTITUTION_ID,
        },
    )
    assert resp.status_code in (200, 401, 403, 404, 503)

    telemetry_path = _telemetry_file(tmp_path)
    assert telemetry_path.exists()
    content = telemetry_path.read_text(encoding="utf-8")
    assert "GET /finance/expenses/{expense_id}" in content


def test_skips_in_legacy_mode(tmp_path: Path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, api_mode="legacy")

    resp = client.get(
        "/finance/expenses/nonexistent",
        headers={
            "X-Actor-Id": "11111111-1111-1111-1111-111111111111",
            "X-Actor-Roles": "admin",
            "X-Institution-Id": DEFAULT_INSTITUTION_ID,
        },
    )
    assert resp.status_code in (200, 401, 403, 404, 503)

    telemetry_path = _telemetry_file(tmp_path)
    assert not telemetry_path.exists()
