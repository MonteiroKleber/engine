"""Verifica consistência entre rotas e páginas geradas (petclinic)."""

import json
import re
from pathlib import Path

import pytest
import yaml

from intake.normalizer import Normalizer
from intake.req_analyst import RequirementsAnalyst
from agents.domain_modeler import DomainModeler
from agents.contracts_agent import ContractsAgent
from agents.planner_agent import PlannerAgent
from compilers.patch_generator_v1 import PatchGenerator, SLOT_MARKERS


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


def _build_artifacts():
    normalizer = Normalizer()
    analyst = RequirementsAnalyst()
    domain_modeler = DomainModeler()
    contracts_agent = ContractsAgent()
    planner = PlannerAgent()

    normalized = normalizer.normalize(RAW_INPUT)
    srs = analyst.generate_srs(normalized, project_title="Petclinic")
    ir = domain_modeler.generate_ir(srs)
    openapi_yaml, rbac = contracts_agent.generate_contracts(ir)
    openapi = yaml.safe_load(openapi_yaml)
    plan = planner.generate_plan(ir, openapi, rbac)
    return plan, ir, openapi, rbac


def _extract_routes(content: str):
    start, end = SLOT_MARKERS["routes-array"]
    start_idx = content.index(start) + len(start)
    end_idx = content.index(end, start_idx)
    block = content[start_idx:end_idx]
    return re.findall(r"path:\s*'/([^/']+)", block)


def test_routes_have_corresponding_page_patches():
    plan, ir, openapi, rbac = _build_artifacts()

    patch_generator = PatchGenerator("petclinic_pages_check")
    patch_set = patch_generator.generate(plan, ir, openapi, rbac)

    routes_patch = next(p for p in patch_set.patches if p.file_path == "frontend/src/routes.tsx")
    route_entities = _extract_routes(routes_patch.content)

    # Para cada rota, deve haver patches de página List/New/Detail
    for entity in route_entities:
        expected_files = {
            f"frontend/src/pages/{entity}/List.tsx",
            f"frontend/src/pages/{entity}/New.tsx",
            f"frontend/src/pages/{entity}/Detail.tsx",
        }
        patched_files = {p.file_path for p in patch_set.patches if entity in p.file_path}
        for expected in expected_files:
            assert expected in patched_files, f"Patch ausente para {expected}"
