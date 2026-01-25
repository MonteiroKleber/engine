"""Hard gates for Migration 05: onboarding must produce IDL-ready bundles in ENGINE_API_MODE=idl."""

import shutil
from pathlib import Path

import pytest

from engine.console.bundle_generator import generate_bundle_from_template
from engine.console.templates_registry import BundleTemplate
from engine.core.institutions import get_registry, reset_registry


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path: Path):
    # Use isolated data root (do not touch var/)
    monkeypatch.setenv("ENGINE_DATA_ROOT", str(tmp_path / "data_root"))
    monkeypatch.setenv("ENGINE_INSTITUTIONS_DIR", str(tmp_path / "data_root" / "institutions"))
    monkeypatch.setenv(
        "ENGINE_INSTITUTIONS_REGISTRY_PATH",
        str(tmp_path / "data_root" / "institutions_registry.jsonl"),
    )
    reset_registry()
    yield
    reset_registry()


def _create_institution(slug: str) -> str:
    registry = get_registry()
    inst, code, msg = registry.create(slug=slug, display_name=slug)
    assert inst is not None, (code, msg)
    return inst.institution_id


def _assert_operations_exist(bundle_path: Path) -> None:
    if (bundle_path / "departments").exists():
        for dept_id in [p.name for p in (bundle_path / "departments").iterdir() if p.is_dir()]:
            assert (bundle_path / "departments" / dept_id / "operations.json").exists()
    else:
        assert (bundle_path / "operations.json").exists()


def test_finance_pilot_template_idl_ready(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ENGINE_API_MODE", "idl")
    institution_id = _create_institution("t-finance")
    result = generate_bundle_from_template(institution_id=institution_id, template_id="finance-pilot", overwrite=True)
    assert result.success, (result.error_code, result.error_message)
    assert result.bundle_path is not None
    _assert_operations_exist(result.bundle_path)


def test_multi_pilot_template_idl_ready(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ENGINE_API_MODE", "idl")
    institution_id = _create_institution("t-multi")
    result = generate_bundle_from_template(institution_id=institution_id, template_id="multi-pilot", overwrite=True)
    assert result.success, (result.error_code, result.error_message)
    assert result.bundle_path is not None
    _assert_operations_exist(result.bundle_path)


def test_template_missing_operations_fails_in_idl_mode(monkeypatch, tmp_path: Path):
    """Synthetic template without operations.json must fail deterministically in idl mode."""
    monkeypatch.setenv("ENGINE_API_MODE", "idl")

    # Create a synthetic template directory based on finance-pilot but missing operations.json
    repo_template = Path("bundles/finance-pilot").resolve()
    broken_template_path = tmp_path / "broken_template"
    shutil.copytree(repo_template, broken_template_path)
    ops_path = broken_template_path / "operations.json"
    assert ops_path.exists()
    ops_path.unlink()

    synthetic = BundleTemplate(
        id="broken-template",
        name="Broken Template",
        description="Missing operations.json",
        departments=["finance"],
        path="irrelevant",
        seed_dsl_paths={"finance": "seeds/finance.idl"},
        seed_dsl_version="idl.v1.2.2",
    )

    from engine.console import bundle_generator as gen
    from engine.console import templates_registry as reg

    orig_get_template = gen.get_template
    orig_get_template_path = gen.get_template_path
    monkeypatch.setattr(
        gen,
        "get_template",
        lambda template_id: synthetic if template_id == "broken-template" else orig_get_template(template_id),
    )
    monkeypatch.setattr(
        gen,
        "get_template_path",
        lambda template_id: broken_template_path if template_id == "broken-template" else orig_get_template_path(template_id),
    )

    institution_id = _create_institution("t-broken")
    result = generate_bundle_from_template(institution_id=institution_id, template_id="broken-template", overwrite=True)
    assert not result.success
    assert result.error_code == "MIGRATION_MISSING_OPERATIONS"
