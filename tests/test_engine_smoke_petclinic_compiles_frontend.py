"""Smoke test: engine sem release deve gerar frontend consistente (petclinic)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from orchestrator.engine import Engine
from repo.repo_generator import RepoGenerator
from patch_engine.patch_engine import PatchEngine
from compilers.patch_generator_v1 import PatchGenerator


RAW_INPUT = (
    "Quero um sistema web para controle de clínica veterinária (clínica pet). "
    "Preciso cadastrar tutores (nome, cpf, telefone, email, endereço), "
    "pets (nome, espécie, raça, sexo, data de nascimento, peso, observações, tutor), "
    "veterinários (nome, CRMV, especialidade, telefone, email), "
    "atendimentos/consultas (data/hora, pet, veterinário, motivo, anotações, diagnóstico, prescrição, status), "
    "vacinas (pet, vacina, data aplicação, próxima dose, lote, observações), "
    "agendamentos (data/hora, pet, veterinário opcional, serviço, status) e "
    "pagamentos (atendimento, forma de pagamento, valor, status, data)."
)


def _extract_import_paths(content: str):
    imports = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("import ") and "./pages/" in line:
            parts = line.split("from")
            if len(parts) == 2:
                path = parts[1].strip().strip("';\"")
                imports.append(path)
    return imports


def test_engine_generates_consistent_frontend(tmp_path: Path):
    project = "petclinic_smoke_compile"
    generated_root = Path("/home/bazari/generated")
    repo_root = generated_root / project
    if repo_root.exists():
        shutil.rmtree(repo_root)

    store_root = tmp_path / "store"
    engine = Engine(str(store_root))

    # Artefatos sem build/release
    result = engine.run(project=project, raw_input=RAW_INPUT, title="PetClinic")
    assert result.success, f"engine.run falhou: {result.errors}"

    plan = json.loads(Path(result.plan_path).read_text(encoding="utf-8"))
    ir = json.loads(Path(result.ir_path).read_text(encoding="utf-8"))
    oas = yaml.safe_load(Path(result.oas_path).read_text(encoding="utf-8"))
    rbac = json.loads(Path(result.rbac_path).read_text(encoding="utf-8"))

    # Repo base
    repo_generator = RepoGenerator(
        templates_root="/home/bazari/templates",
        output_root=str(generated_root),
    )
    if repo_generator.repo_exists(project):
        repo_generator.delete_repo(project)
    repo_generator.create_repo(project)
    assert repo_root.exists()

    # Patches e aplicação
    patch_generator = PatchGenerator(project, str(generated_root))
    patch_set = patch_generator.generate(plan, ir, oas, rbac)

    patch_engine = PatchEngine(project, str(generated_root))
    patch_result = patch_engine.apply_patches([p.to_dict() for p in patch_set.patches])
    assert patch_result.success, f"PatchEngine falhou: {patch_result.errors}"

    # Validar páginas existentes para cada rota/import
    routes_path = repo_root / "frontend/src/routes.tsx"
    assert routes_path.exists()
    routes_content = routes_path.read_text(encoding="utf-8")

    import_paths = _extract_import_paths(routes_content)
    for import_path in import_paths:
        target = (repo_root / "frontend/src" / Path(import_path + ".tsx")).resolve()
        assert target.exists(), f"Import quebrado em routes.tsx: {import_path}"

    # Verificar que diretórios de páginas contêm List/New/Detail para cada entidade mencionada
    for import_path in import_paths:
        entity_dir = (repo_root / "frontend/src" / Path(import_path)).parent
        list_file = entity_dir / "List.tsx"
        new_file = entity_dir / "New.tsx"
        detail_file = entity_dir / "Detail.tsx"
        assert list_file.exists()
        assert new_file.exists()
        assert detail_file.exists()
