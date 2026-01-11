"""Testes para o sistema de slots do frontend.

Verifica que:
- Templates contêm os marcadores exigidos
- PatchGenerator gera patches para App/HomePage com operation="modify"
- O resultado de substituição preserva os marcadores
- O conteúdo inserido respeita ordering alfabético
- replace_slot levanta ValueError quando marcador ausente
"""

import pytest
from pathlib import Path

from compilers.patch_generator_v1 import (
    PatchGenerator,
    replace_slot,
    read_template,
    SLOT_MARKERS,
    get_template_root,
)

# Backwards compatibility
TEMPLATE_ROOT = get_template_root()


# ==================== FIXTURES ====================


@pytest.fixture
def sample_entities():
    """Entidades de exemplo para testes."""
    return [
        {"name": "veterinario", "fields": [{"name": "id", "type": "uuid"}]},
        {"name": "pet", "fields": [{"name": "id", "type": "uuid"}]},
        {"name": "agendamento", "fields": [{"name": "id", "type": "uuid"}]},
        {"name": "tutor", "fields": [{"name": "id", "type": "uuid"}]},
    ]


@pytest.fixture
def sample_ir(sample_entities):
    """IR de exemplo com entidades."""
    return {
        "domain": {
            "entities": sample_entities,
        }
    }


@pytest.fixture
def sample_plan(sample_entities):
    """PLAN de exemplo."""
    return {
        "tasks": [],
    }


@pytest.fixture
def sample_oas():
    """OAS de exemplo."""
    return {"paths": {}}


@pytest.fixture
def sample_rbac():
    """RBAC de exemplo."""
    return {"permissions": []}


@pytest.fixture
def patch_generator():
    """PatchGenerator de exemplo."""
    return PatchGenerator("test_project")


# ==================== TEMPLATE MARKER TESTS ====================


class TestTemplateMarkers:
    """Testa que templates contêm os marcadores exigidos."""

    def test_app_tsx_has_nav_slot(self):
        """App.tsx deve conter slot nav."""
        content = read_template("src/App.tsx")
        start, end = SLOT_MARKERS["nav"]
        assert start in content, f"Marcador '{start}' ausente em App.tsx"
        assert end in content, f"Marcador '{end}' ausente em App.tsx"

    def test_app_tsx_has_routes_slot(self):
        """App.tsx deve conter slot routes."""
        content = read_template("src/App.tsx")
        start, end = SLOT_MARKERS["routes"]
        assert start in content, f"Marcador '{start}' ausente em App.tsx"
        assert end in content, f"Marcador '{end}' ausente em App.tsx"

    def test_homepage_tsx_has_entities_slot(self):
        """HomePage.tsx deve conter slot entities."""
        content = read_template("src/pages/HomePage.tsx")
        start, end = SLOT_MARKERS["entities"]
        assert start in content, f"Marcador '{start}' ausente em HomePage.tsx"
        assert end in content, f"Marcador '{end}' ausente em HomePage.tsx"

    def test_routes_tsx_has_required_slots(self):
        """routes.tsx deve conter slots imports e routes-array."""
        content = read_template("src/routes.tsx")

        start, end = SLOT_MARKERS["imports"]
        assert start in content, f"Marcador '{start}' ausente em routes.tsx"
        assert end in content, f"Marcador '{end}' ausente em routes.tsx"

        start, end = SLOT_MARKERS["routes-array"]
        assert start in content, f"Marcador '{start}' ausente em routes.tsx"
        assert end in content, f"Marcador '{end}' ausente em routes.tsx"

    def test_app_tsx_has_home_route(self):
        """App.tsx deve manter rota fixa para HomePage."""
        content = read_template("src/App.tsx")
        assert 'path="/"' in content, "Rota '/' ausente em App.tsx"
        assert "HomePage" in content, "Referência a HomePage ausente em App.tsx"


# ==================== REPLACE SLOT TESTS ====================


class TestReplaceSlot:
    """Testa a função replace_slot."""

    def test_replaces_nav_slot(self):
        """Deve substituir conteúdo do slot nav."""
        content = """{/* @engine:nav:start */}
{/* @engine:nav:end */}"""

        new_block = '<Link to="/pet">Pet</Link>'
        result = replace_slot(content, "nav", new_block)

        assert "{/* @engine:nav:start */}" in result
        assert "{/* @engine:nav:end */}" in result
        assert '<Link to="/pet">Pet</Link>' in result

    def test_replaces_routes_slot(self):
        """Deve substituir conteúdo do slot routes."""
        content = """{/* @engine:routes:start */}
{/* @engine:routes:end */}"""

        new_block = "{routes.map((r, i) => <Route key={i} />)}"
        result = replace_slot(content, "routes", new_block)

        assert "{/* @engine:routes:start */}" in result
        assert "{/* @engine:routes:end */}" in result
        assert "routes.map" in result

    def test_replaces_entities_slot(self):
        """Deve substituir conteúdo do slot entities."""
        content = """{/* @engine:entities:start */}
{/* @engine:entities:end */}"""

        new_block = '<li><Link to="/pet">Pet</Link></li>'
        result = replace_slot(content, "entities", new_block)

        assert "{/* @engine:entities:start */}" in result
        assert "{/* @engine:entities:end */}" in result
        assert '<li><Link to="/pet">Pet</Link></li>' in result

    def test_preserves_markers_after_replace(self):
        """Marcadores devem ser preservados após substituição."""
        content = """{/* @engine:nav:start */}
{/* @engine:nav:end */}"""

        result = replace_slot(content, "nav", "content")

        # Marcadores preservados
        assert "{/* @engine:nav:start */}" in result
        assert "{/* @engine:nav:end */}" in result

    def test_preserves_routes_tsx_markers_after_replace(self):
        """Marcadores JS (imports/routes-array) devem ser preservados."""
        content = """import type { RouteObject } from 'react-router-dom';

// @engine:imports:start
// @engine:imports:end

export const routes: RouteObject[] = [
  // @engine:routes-array:start
  // @engine:routes-array:end
];"""

        result = replace_slot(content, "imports", "import PetList from './pages/pet/List';")
        result = replace_slot(result, "routes-array", "  { path: '/pet', element: <PetList /> },")

        assert "// @engine:imports:start" in result
        assert "// @engine:imports:end" in result
        assert "// @engine:routes-array:start" in result
        assert "// @engine:routes-array:end" in result

    def test_raises_on_missing_start_marker(self):
        """Deve levantar ValueError quando marcador start ausente."""
        content = """{/* @engine:nav:end */}"""

        with pytest.raises(ValueError) as exc_info:
            replace_slot(content, "nav", "content", "test.tsx")

        assert "nav" in str(exc_info.value)
        assert "start" in str(exc_info.value).lower()
        assert "test.tsx" in str(exc_info.value)

    def test_raises_on_missing_end_marker(self):
        """Deve levantar ValueError quando marcador end ausente."""
        content = """{/* @engine:nav:start */}"""

        with pytest.raises(ValueError) as exc_info:
            replace_slot(content, "nav", "content", "test.tsx")

        assert "nav" in str(exc_info.value)
        assert "end" in str(exc_info.value).lower()

    def test_raises_on_unknown_slot(self):
        """Deve levantar ValueError para slot desconhecido."""
        content = "qualquer conteudo"

        with pytest.raises(ValueError) as exc_info:
            replace_slot(content, "unknown_slot", "content")

        assert "unknown_slot" in str(exc_info.value)
        assert "Slots válidos" in str(exc_info.value)


# ==================== PATCH GENERATOR OPERATION TESTS ====================


class TestPatchGeneratorOperations:
    """Testa que PatchGenerator gera patches com operation correto."""

    def test_app_tsx_uses_modify_operation(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """App.tsx deve usar operation='modify'."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        app_patches = [p for p in patch_set.patches if p.file_path == "frontend/src/App.tsx"]
        assert len(app_patches) == 1, "Deve haver exatamente 1 patch para App.tsx"
        assert app_patches[0].operation == "modify", "App.tsx deve usar operation='modify'"

    def test_homepage_tsx_uses_modify_operation(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """HomePage.tsx deve usar operation='modify'."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        homepage_patches = [
            p for p in patch_set.patches
            if p.file_path == "frontend/src/pages/HomePage.tsx"
        ]
        assert len(homepage_patches) == 1, "Deve haver exatamente 1 patch para HomePage.tsx"
        assert homepage_patches[0].operation == "modify", "HomePage.tsx deve usar operation='modify'"

    def test_routes_tsx_uses_modify_operation(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """routes.tsx deve usar operation='modify'."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        routes_patches = [
            p for p in patch_set.patches
            if p.file_path == "frontend/src/routes.tsx"
        ]
        assert len(routes_patches) == 1, "Deve haver exatamente 1 patch para routes.tsx"
        assert routes_patches[0].operation == "modify", "routes.tsx deve usar operation='modify'"


# ==================== ALPHABETICAL ORDERING TESTS ====================


class TestAlphabeticalOrdering:
    """Testa que conteúdo é inserido em ordem alfabética."""

    def test_nav_links_alphabetical_order(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """Links de navegação devem estar em ordem alfabética."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        app_patch = next(p for p in patch_set.patches if p.file_path == "frontend/src/App.tsx")
        content = app_patch.content

        # Encontrar posições dos links
        pos_agendamento = content.find('to="/agendamento"')
        pos_pet = content.find('to="/pet"')
        pos_tutor = content.find('to="/tutor"')
        pos_veterinario = content.find('to="/veterinario"')

        # Ordem alfabética: agendamento < pet < tutor < veterinario
        assert pos_agendamento < pos_pet < pos_tutor < pos_veterinario, \
            "Links de navegação devem estar em ordem alfabética"

    def test_entity_list_alphabetical_order(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """Lista de entidades em HomePage deve estar em ordem alfabética."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        homepage_patch = next(
            p for p in patch_set.patches
            if p.file_path == "frontend/src/pages/HomePage.tsx"
        )
        content = homepage_patch.content

        # Encontrar posições dos links
        pos_agendamento = content.find('to="/agendamento"')
        pos_pet = content.find('to="/pet"')
        pos_tutor = content.find('to="/tutor"')
        pos_veterinario = content.find('to="/veterinario"')

        # Ordem alfabética: agendamento < pet < tutor < veterinario
        assert pos_agendamento < pos_pet < pos_tutor < pos_veterinario, \
            "Lista de entidades deve estar em ordem alfabética"

    def test_routes_imports_alphabetical_order(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """Imports em routes.tsx devem estar em ordem alfabética."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)
        routes_patch = next(p for p in patch_set.patches if p.file_path == "frontend/src/routes.tsx")
        content = routes_patch.content

        pos_agendamento = content.find("import AgendamentoList")
        pos_pet = content.find("import PetList")
        pos_tutor = content.find("import TutorList")
        pos_veterinario = content.find("import VeterinarioList")

        assert pos_agendamento != -1 and pos_pet != -1 and pos_tutor != -1 and pos_veterinario != -1
        assert pos_agendamento < pos_pet < pos_tutor < pos_veterinario, \
            "Imports devem estar em ordem alfabética por entity.name"

    def test_routes_paths_alphabetical_order(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """Rotas em routes.tsx devem estar em ordem alfabética."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)
        routes_patch = next(p for p in patch_set.patches if p.file_path == "frontend/src/routes.tsx")
        content = routes_patch.content

        pos_agendamento = content.find("path: '/agendamento'")
        pos_pet = content.find("path: '/pet'")
        pos_tutor = content.find("path: '/tutor'")
        pos_veterinario = content.find("path: '/veterinario'")

        assert pos_agendamento != -1 and pos_pet != -1 and pos_tutor != -1 and pos_veterinario != -1
        assert pos_agendamento < pos_pet < pos_tutor < pos_veterinario, \
            "Rotas devem estar em ordem alfabética por entity.name"


# ==================== CONTENT PRESERVATION TESTS ====================


class TestContentPreservation:
    """Testa que conteúdo do template é preservado."""

    def test_app_preserves_home_route(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """App.tsx deve preservar rota '/' para HomePage."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        app_patch = next(p for p in patch_set.patches if p.file_path == "frontend/src/App.tsx")
        content = app_patch.content

        assert 'path="/"' in content, "Rota '/' deve ser preservada"
        assert "HomePage" in content, "Referência a HomePage deve ser preservada"

    def test_app_preserves_markers(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """App.tsx deve preservar marcadores após substituição."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        app_patch = next(p for p in patch_set.patches if p.file_path == "frontend/src/App.tsx")
        content = app_patch.content

        assert "{/* @engine:nav:start */}" in content
        assert "{/* @engine:nav:end */}" in content
        assert "{/* @engine:routes:start */}" in content
        assert "{/* @engine:routes:end */}" in content

    def test_homepage_preserves_markers(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """HomePage.tsx deve preservar marcadores após substituição."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        homepage_patch = next(
            p for p in patch_set.patches
            if p.file_path == "frontend/src/pages/HomePage.tsx"
        )
        content = homepage_patch.content

        assert "{/* @engine:entities:start */}" in content
        assert "{/* @engine:entities:end */}" in content

    def test_homepage_preserves_structure(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """HomePage.tsx deve preservar estrutura do template."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        homepage_patch = next(
            p for p in patch_set.patches
            if p.file_path == "frontend/src/pages/HomePage.tsx"
        )
        content = homepage_patch.content

        # Estrutura básica preservada
        assert "Bem-vindo ao Sistema" in content
        assert "Cadastros" in content
        assert "<ul>" in content

    def test_routes_preserves_markers(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """routes.tsx deve preservar marcadores após substituição."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        routes_patch = next(p for p in patch_set.patches if p.file_path == "frontend/src/routes.tsx")
        content = routes_patch.content

        assert "// @engine:imports:start" in content
        assert "// @engine:imports:end" in content
        assert "// @engine:routes-array:start" in content
        assert "// @engine:routes-array:end" in content


# ==================== TITLE CASE TESTS ====================


class TestTitleCase:
    """Testa que nomes são formatados corretamente."""

    def test_entity_names_are_title_case(
        self, patch_generator, sample_plan, sample_ir, sample_oas, sample_rbac
    ):
        """Nomes de entidades devem usar Title Case simples."""
        patch_set = patch_generator.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        homepage_patch = next(
            p for p in patch_set.patches
            if p.file_path == "frontend/src/pages/HomePage.tsx"
        )
        content = homepage_patch.content

        # Title Case simples (primeira letra maiúscula)
        assert ">Pet<" in content
        assert ">Tutor<" in content
        assert ">Veterinario<" in content
        assert ">Agendamento<" in content


# ==================== EDGE CASES ====================


class TestEdgeCases:
    """Testa casos de borda."""

    def test_empty_entities_list(self, patch_generator, sample_plan, sample_oas, sample_rbac):
        """Deve funcionar com lista de entidades vazia."""
        empty_ir = {"domain": {"entities": []}}

        # Não deve gerar patches globais sem entidades
        patch_set = patch_generator.generate(sample_plan, empty_ir, sample_oas, sample_rbac)

        app_patches = [p for p in patch_set.patches if "App.tsx" in p.file_path]
        homepage_patches = [p for p in patch_set.patches if "HomePage.tsx" in p.file_path]

        assert len(app_patches) == 0, "Sem entidades, não deve gerar patch para App.tsx"
        assert len(homepage_patches) == 0, "Sem entidades, não deve gerar patch para HomePage.tsx"

    def test_single_entity(self, patch_generator, sample_plan, sample_oas, sample_rbac):
        """Deve funcionar com uma única entidade."""
        single_ir = {
            "domain": {
                "entities": [{"name": "produto", "fields": [{"name": "id", "type": "uuid"}]}]
            }
        }

        patch_set = patch_generator.generate(sample_plan, single_ir, sample_oas, sample_rbac)

        app_patch = next(p for p in patch_set.patches if p.file_path == "frontend/src/App.tsx")
        assert 'to="/produto"' in app_patch.content
