"""Teste de integração mínimo: gera projeto petclinic (sem --release).

Não executa docker nem build (npm/mvn). Apenas:
- gera artefatos (SRS/IR/OAS/RBAC/PLAN)
- cria repo a partir de templates
- gera patchset determinístico
- aplica patches via PatchEngine
- valida que backend/frontend foram materializados e que routes.tsx foi preenchido
  mantendo marcadores @engine.
"""

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
    "Quero um sistema web para controle de clínica veterinária. "
    "Preciso cadastrar tutores (nome, cpf, telefone, email), "
    "pets (nome, especie, raca, tutor), "
    "veterinarios (nome, crmv) e atendimentos (data/hora, pet, veterinario). "
    "Regras: pet pertence a tutor; atendimento exige pet e veterinario."
)


def test_engine_generates_petclinic_no_release(tmp_path: Path):
    project = "petclinic_slots_ok"

    generated_root = Path("/home/bazari/generated")
    repo_root = generated_root / project
    if repo_root.exists():
        shutil.rmtree(repo_root)

    store_root = tmp_path / "store"
    engine = Engine(str(store_root))

    # 1) Artefatos (entrada bruta)
    result = engine.run(project=project, raw_input=RAW_INPUT, title="PetClinic")
    assert result.success, f"engine.run falhou: {result.errors}"

    plan = json.loads(Path(result.plan_path).read_text(encoding="utf-8"))
    ir = json.loads(Path(result.ir_path).read_text(encoding="utf-8"))
    oas = yaml.safe_load(Path(result.oas_path).read_text(encoding="utf-8"))
    rbac = json.loads(Path(result.rbac_path).read_text(encoding="utf-8"))

    # 2) Repo base a partir dos templates
    repo_generator = RepoGenerator(
        templates_root="/home/bazari/templates",
        output_root=str(generated_root),
    )
    if repo_generator.repo_exists(project):
        repo_generator.delete_repo(project)
    repo_generator.create_repo(project)
    assert repo_root.exists(), f"Repo não criado: {repo_root}"

    # 3) Patchset e aplicação dos patches (sem build)
    patch_generator = PatchGenerator(project, str(generated_root))
    patch_set = patch_generator.generate(plan, ir, oas, rbac)
    assert any(p.file_path == "frontend/src/routes.tsx" for p in patch_set.patches)

    patch_engine = PatchEngine(project, str(generated_root))
    patch_result = patch_engine.apply_patches([p.to_dict() for p in patch_set.patches])
    assert patch_result.success, f"PatchEngine falhou: {patch_result.errors}"

    # 4) Evidências mínimas: backend domain (.java) e frontend pages (tsx)
    java_root = repo_root / "backend/src/main/java"
    assert java_root.exists()
    java_domain_files = list(java_root.rglob("domain/**/*.java"))
    assert java_domain_files, "Esperado pelo menos 1 .java em backend/**/domain/"

    pages_root = repo_root / "frontend/src/pages"
    assert pages_root.exists()
    list_pages = list(pages_root.rglob("List.tsx"))
    new_pages = list(pages_root.rglob("New.tsx"))
    detail_pages = list(pages_root.rglob("Detail.tsx"))
    assert list_pages and new_pages and detail_pages, "Esperadas pages List/New/Detail no frontend"

    # 5) routes.tsx preenchido e com marcadores preservados
    routes_path = repo_root / "frontend/src/routes.tsx"
    assert routes_path.exists()
    routes_content = routes_path.read_text(encoding="utf-8")
    assert "// @engine:imports:start" in routes_content
    assert "// @engine:imports:end" in routes_content
    assert "// @engine:routes-array:start" in routes_content
    assert "// @engine:routes-array:end" in routes_content

    # Evidência mínima de geração (aceita que o parser extraia entidades variáveis, mas espera "pet")
    assert "import PetList" in routes_content
    assert "path: '/pet'" in routes_content

