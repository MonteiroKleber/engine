"""Hard gates for Migration 05: ISE must not produce half-valid bundles."""

import json
from pathlib import Path

import pytest

from engine.ise import errors
from engine.ise.compiler import compile_from_ircs


def _minimal_ircs(source_idl_sha256: str | None):
    ir = {
        "ir_version": "ircs.v1",
        "source_idl_version": "idl.v1.2.2",
        "system": {"id": "T", "name": "T", "owner": "T", "domain": "t", "description": "t", "contact": "t"},
        "actors": [],
        "entities": [],
        "invariants": [],
        "separation_of_duties": [],
        "workflows": [],
        "operations": {"api": []},
    }
    if source_idl_sha256 is not None:
        ir["source_idl_sha256"] = source_idl_sha256
    return ir


def test_ise_fails_without_source_idl_sha256(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = compile_from_ircs(_minimal_ircs(None), bundle_name="t_bundle", output_dir=str(out_dir))
    assert not result.success
    assert result.error_code == errors.ISE_SOURCE_IDL_SHA256_MISSING
    assert not (out_dir / "t_bundle").exists()


def test_ise_writes_ledger_with_source_idl_sha256(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    sha = "a" * 64
    result = compile_from_ircs(_minimal_ircs(sha), bundle_name="t_bundle", output_dir=str(out_dir))
    assert result.success, (result.error_code, result.error_message)
    bundle_path = Path(result.bundle_path)
    ledger = json.loads((bundle_path / "contract_ledger.json").read_text(encoding="utf-8"))
    assert ledger.get("source_idl_sha256") == sha

