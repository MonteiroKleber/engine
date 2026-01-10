"""Smoke test local do engine (sem docker) para slots do routes.tsx.

Objetivo:
- Rodar o pipeline de artefatos (SRS/IR/OAS/RBAC/PLAN) a partir de uma entrada bruta
- Criar repo local a partir dos templates
- Gerar patchset determinístico e verificar patch de frontend/src/routes.tsx:
  - operation="modify"
  - preserva os marcadores
  - preenche os slots com pelo menos 1 import e 1 rota quando houver entidades
- Aplicar SOMENTE o patch do routes.tsx via PatchEngine para validar que não
  dispara "Rewrite ratio too high" (sem build, sem docker, sem rede).
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
from compilers.patch_generator_v1 import PatchGenerator, SLOT_MARKERS


RAW_INPUT = (
    "Quero um sistema web para controle de clínica veterinária. "
    "Preciso cadastrar tutores (nome, cpf, telefone, email), "
    "pets (nome, especie, raca, tutor), "
    "veterinarios (nome, crmv) e atendimentos (data/hora, pet, veterinario). "
    "Regras: pet pertence a tutor; atendimento exige pet e veterinario."
)


def _extract_between(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


class TestEngineSmokePetclinicSlots:
    def test_engine_generates_routes_tsx_patch_with_slots(self, tmp_path: Path):
        project = "petclinic_smoke_slots"

        generated_root = Path("/home/bazari/generated")
        repo_root = generated_root / project
        if repo_root.exists():
            shutil.rmtree(repo_root)

        store_root = tmp_path / "store"
        engine = Engine(str(store_root))

        # 1) Executar pipeline de artefatos (sem build)
        result = engine.run(project=project, raw_input=RAW_INPUT, title="PetClinic")
        assert result.success, f"engine.run falhou: {result.errors}"

        # 2) Carregar artefatos do store (input "bruto" realista)
        plan = json.loads(Path(result.plan_path).read_text(encoding="utf-8"))
        ir = json.loads(Path(result.ir_path).read_text(encoding="utf-8"))
        oas = yaml.safe_load(Path(result.oas_path).read_text(encoding="utf-8"))
        rbac = json.loads(Path(result.rbac_path).read_text(encoding="utf-8"))

        # 3) Criar repo a partir dos templates (sem docker)
        repo_generator = RepoGenerator(
            templates_root="/home/bazari/templates",
            output_root=str(generated_root),
        )
        if repo_generator.repo_exists(project):
            repo_generator.delete_repo(project)
        repo_generator.create_repo(project)
        assert (repo_root / "frontend/src/routes.tsx").exists()

        # 4) Gerar patchset e validar patch do routes.tsx
        patch_generator = PatchGenerator(project, str(generated_root))
        patch_set = patch_generator.generate(plan, ir, oas, rbac)

        routes_patches = [p for p in patch_set.patches if p.file_path == "frontend/src/routes.tsx"]
        assert len(routes_patches) == 1, "Deve haver exatamente 1 patch para routes.tsx"
        routes_patch = routes_patches[0]
        assert routes_patch.operation == "modify", "routes.tsx deve usar operation='modify'"

        content = routes_patch.content
        required_markers = [
            SLOT_MARKERS["imports"][0],
            SLOT_MARKERS["imports"][1],
            SLOT_MARKERS["routes-array"][0],
            SLOT_MARKERS["routes-array"][1],
        ]
        for marker in required_markers:
            assert marker in content, f"Marcador '{marker}' ausente no patch de routes.tsx"

        entities = ir.get("domain", {}).get("entities", [])
        if entities:
            imports_block = _extract_between(content, *SLOT_MARKERS["imports"])
            routes_block = _extract_between(content, *SLOT_MARKERS["routes-array"])
            assert "import " in imports_block, "Com entidades, slot imports deve conter pelo menos 1 import"
            assert "path:" in routes_block, "Com entidades, slot routes-array deve conter pelo menos 1 rota"

        # 5) Aplicar SOMENTE o patch do routes.tsx para validar rewrite ratio
        patch_engine = PatchEngine(project, str(generated_root))
        patch_result = patch_engine.apply_patches([routes_patch.to_dict()])
        assert patch_result.success, f"PatchEngine falhou ao aplicar routes.tsx: {patch_result.errors}"

