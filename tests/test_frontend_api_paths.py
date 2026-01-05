"""Teste de regressao para paths de API no frontend.

Valida que os metodos de geracao TSX NAO incluem '/api/' no path,
pois o baseURL do axios ja inclui '/api'.

Bug original: api.get('/api/empresas') resulta em /api/api/empresas -> 404
Correcao: api.get('/empresas') resulta em /api/empresas -> 200
"""

import pytest
from compilers.patch_generator_v1 import PatchGenerator


@pytest.fixture
def generator() -> PatchGenerator:
    """Cria instancia do PatchGenerator."""
    return PatchGenerator(project="test")


@pytest.fixture
def sample_entity() -> dict:
    """Entidade de exemplo para testes."""
    return {
        "name": "Empresa",
        "primary_key": "id",
        "fields": [
            {"name": "id", "type": "uuid", "required": True},
            {"name": "nome", "type": "string", "required": True},
            {"name": "cnpj", "type": "string", "required": True, "unique": True},
            {"name": "endereco", "type": "text"},
        ],
    }


class TestFrontendApiPaths:
    """Testes para validar que paths de API estao corretos."""

    def test_list_page_no_api_prefix(
        self, generator: PatchGenerator, sample_entity: dict
    ) -> None:
        """List page deve usar path sem /api/ prefix."""
        content = generator._generate_tsx_list_page(sample_entity)

        # Deve conter path relativo (sem /api/)
        assert "api.get<Empresa[]>('/empresas')" in content
        # NAO deve conter /api/api/ (bug antigo)
        assert "'/api/empresas'" not in content
        assert "'/api/api/" not in content

    def test_new_page_no_api_prefix(
        self, generator: PatchGenerator, sample_entity: dict
    ) -> None:
        """New page deve usar path sem /api/ prefix."""
        content = generator._generate_tsx_new_page(sample_entity)

        # Deve conter path relativo (sem /api/)
        assert "api.post('/empresas'" in content
        # NAO deve conter /api/api/ (bug antigo)
        assert "'/api/empresas'" not in content
        assert "'/api/api/" not in content

    def test_detail_page_no_api_prefix(
        self, generator: PatchGenerator, sample_entity: dict
    ) -> None:
        """Detail page deve usar paths sem /api/ prefix."""
        content = generator._generate_tsx_detail_page(sample_entity)

        # GET deve usar path relativo
        assert "api.get<Empresa>(`/empresas/${id}`)" in content
        # DELETE deve usar path relativo
        assert "api.delete(`/empresas/${id}`)" in content
        # NAO deve conter /api/api/ (bug antigo)
        assert "'/api/empresas" not in content
        assert "`/api/empresas" not in content
        assert "'/api/api/" not in content

    def test_api_client_entry_no_api_prefix(
        self, generator: PatchGenerator, sample_entity: dict
    ) -> None:
        """API client entry deve usar paths sem /api/ prefix."""
        content = generator._generate_api_client_entry([sample_entity])

        # Paths devem ser relativos ao baseURL
        assert "api.get('/empresas')" in content
        assert "api.post('/empresas'" in content
        assert "api.delete(`/empresas/${id}`)" in content
        # NAO deve conter /api/empresas (seria duplicado)
        assert "'/api/empresas'" not in content


class TestGeneratedPathsIntegration:
    """Testes de integracao para verificar paths em todas as paginas."""

    def test_all_tsx_pages_use_relative_paths(
        self, generator: PatchGenerator, sample_entity: dict
    ) -> None:
        """Todas as paginas TSX devem usar paths relativos."""
        pages = [
            ("List", generator._generate_tsx_list_page(sample_entity)),
            ("New", generator._generate_tsx_new_page(sample_entity)),
            ("Detail", generator._generate_tsx_detail_page(sample_entity)),
        ]

        for page_name, content in pages:
            # Verifica que nenhuma pagina tem /api/ hardcoded no path
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if "api." in line and ("get(" in line or "post(" in line or "delete(" in line or "put(" in line):
                    # Se tem chamada de api, verifica que nao tem /api/ no path
                    assert "'/api/" not in line, (
                        f"{page_name}.tsx linha {i}: path nao deve comecar com /api/\n"
                        f"  Encontrado: {line.strip()}\n"
                        f"  O baseURL do axios ja inclui /api"
                    )
                    assert '"/api/' not in line, (
                        f"{page_name}.tsx linha {i}: path nao deve comecar com /api/\n"
                        f"  Encontrado: {line.strip()}"
                    )
                    assert "`/api/" not in line, (
                        f"{page_name}.tsx linha {i}: path nao deve comecar com /api/\n"
                        f"  Encontrado: {line.strip()}"
                    )
