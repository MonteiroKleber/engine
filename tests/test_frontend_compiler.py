"""Testes para o FrontendCompiler.

Verifica:
- Geração de tipos TypeScript
- Geração de API client tipado
- Geração de páginas CRUD (List, Form, Detail)
- Geração de hooks React Query
- Geração de router config
- Integração com IR + OAS
"""

import pytest

from compilers.frontend_compiler import (
    FrontendCompiler,
    FrontendOutput,
    GeneratedFile,
    compile_frontend,
)


@pytest.fixture
def sample_ir():
    """IR de exemplo para testes."""
    return {
        "meta": {
            "project_name": "Sistema Teste",
            "version": "1.0.0",
        },
        "domain": {
            "entities": [
                {
                    "name": "empresa",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "uuid", "required": True, "unique": True},
                        {"name": "nome", "type": "string", "required": True, "max_length": 255},
                        {"name": "cnpj", "type": "string", "required": True, "unique": True},
                        {"name": "email", "type": "email", "required": False},
                        {"name": "ativo", "type": "boolean", "required": True},
                    ],
                }
            ],
            "relations": [],
        },
        "api_intent": {
            "resources": ["empresa"],
        },
    }


@pytest.fixture
def sample_oas():
    """OpenAPI de exemplo."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "API Teste", "version": "1.0.0"},
        "paths": {
            "/api/empresas": {
                "get": {
                    "operationId": "listEmpresas",
                    "tags": ["empresa"],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "createEmpresa",
                    "tags": ["empresa"],
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/api/empresas/{id}": {
                "get": {
                    "operationId": "getEmpresa",
                    "tags": ["empresa"],
                    "responses": {"200": {"description": "OK"}},
                },
                "put": {
                    "operationId": "updateEmpresa",
                    "tags": ["empresa"],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "deleteEmpresa",
                    "tags": ["empresa"],
                    "responses": {"204": {"description": "No Content"}},
                },
            },
        },
    }


@pytest.fixture
def compiler():
    """Retorna instância do FrontendCompiler."""
    return FrontendCompiler()


# ==================== TESTS: COMPILER INIT ====================


class TestFrontendCompilerInit:
    """Testes de inicialização do FrontendCompiler."""

    def test_default_project_root(self, compiler):
        """Deve usar project_root padrão."""
        assert str(compiler.project_root) == "/home/bazari/generated"

    def test_custom_project_root(self):
        """Deve aceitar project_root customizado."""
        compiler = FrontendCompiler(project_root="/tmp/test")
        assert str(compiler.project_root) == "/tmp/test"

    def test_to_kebab_case(self, compiler):
        """Deve converter para kebab-case."""
        assert compiler._to_kebab_case("empresaFilial") == "empresa-filial"
        assert compiler._to_kebab_case("MinhaEmpresa") == "minha-empresa"


# ==================== TESTS: TYPES GENERATION ====================


class TestTypesGeneration:
    """Testes de geração de tipos TypeScript."""

    def test_generates_types_file(self, compiler, sample_ir, sample_oas):
        """Deve gerar arquivo de tipos."""
        output = compiler.compile(sample_ir, sample_oas)

        types_files = [f for f in output.files if f.file_type == "types"]
        assert len(types_files) == 1
        assert types_files[0].path == "src/types/index.ts"

    def test_types_has_entity_interface(self, compiler, sample_ir, sample_oas):
        """Tipos devem ter interface da entidade."""
        output = compiler.compile(sample_ir, sample_oas)

        types_file = next(f for f in output.files if f.file_type == "types")
        content = types_file.content

        assert "export interface Empresa {" in content
        assert "id?: string;" in content or "id: string;" in content
        assert "nome: string;" in content

    def test_types_has_request_interface(self, compiler, sample_ir, sample_oas):
        """Tipos devem ter interface de Request."""
        output = compiler.compile(sample_ir, sample_oas)

        types_file = next(f for f in output.files if f.file_type == "types")
        content = types_file.content

        assert "export interface EmpresaRequest {" in content
        # Request não deve ter id
        lines = content.split("\n")
        in_request = False
        for line in lines:
            if "EmpresaRequest" in line:
                in_request = True
            if in_request and "}" in line:
                break
            if in_request and "id:" in line and "operationId" not in line:
                pytest.fail("Request should not have id field")

    def test_types_has_timestamps(self, compiler, sample_ir, sample_oas):
        """Tipos devem ter timestamps opcionais."""
        output = compiler.compile(sample_ir, sample_oas)

        types_file = next(f for f in output.files if f.file_type == "types")
        content = types_file.content

        assert "createdAt?: string;" in content
        assert "updatedAt?: string;" in content

    def test_types_has_api_error(self, compiler, sample_ir, sample_oas):
        """Tipos devem ter interface ApiError."""
        output = compiler.compile(sample_ir, sample_oas)

        types_file = next(f for f in output.files if f.file_type == "types")
        content = types_file.content

        assert "export interface ApiError {" in content


# ==================== TESTS: API CLIENT GENERATION ====================


class TestApiClientGeneration:
    """Testes de geração do API client."""

    def test_generates_client_file(self, compiler, sample_ir, sample_oas):
        """Deve gerar arquivo de client."""
        output = compiler.compile(sample_ir, sample_oas)

        client_files = [f for f in output.files if f.file_type == "client"]
        assert len(client_files) == 1
        assert client_files[0].path == "src/api/client.ts"

    def test_client_has_axios_setup(self, compiler, sample_ir, sample_oas):
        """Client deve ter setup do axios."""
        output = compiler.compile(sample_ir, sample_oas)

        client_file = next(f for f in output.files if f.file_type == "client")
        content = client_file.content

        assert "import axios from 'axios';" in content
        assert "axios.create" in content

    def test_client_has_auth_interceptor(self, compiler, sample_ir, sample_oas):
        """Client deve ter interceptor de autenticação."""
        output = compiler.compile(sample_ir, sample_oas)

        client_file = next(f for f in output.files if f.file_type == "client")
        content = client_file.content

        assert "interceptors.request.use" in content
        assert "localStorage.getItem('token')" in content
        assert "Authorization" in content

    def test_client_has_entity_api(self, compiler, sample_ir, sample_oas):
        """Client deve ter API da entidade."""
        output = compiler.compile(sample_ir, sample_oas)

        client_file = next(f for f in output.files if f.file_type == "client")
        content = client_file.content

        assert "empresaApi = {" in content
        assert "list:" in content
        assert "getById:" in content
        assert "create:" in content
        assert "update:" in content
        assert "delete:" in content

    def test_client_has_typed_methods(self, compiler, sample_ir, sample_oas):
        """Métodos do client devem ser tipados."""
        output = compiler.compile(sample_ir, sample_oas)

        client_file = next(f for f in output.files if f.file_type == "client")
        content = client_file.content

        assert "Promise<Empresa[]>" in content
        assert "Promise<Empresa>" in content
        assert "EmpresaRequest" in content


# ==================== TESTS: HOOKS GENERATION ====================


class TestHooksGeneration:
    """Testes de geração de hooks React Query."""

    def test_generates_hooks_file(self, compiler, sample_ir, sample_oas):
        """Deve gerar arquivo de hooks."""
        output = compiler.compile(sample_ir, sample_oas)

        hooks_files = [f for f in output.files if f.file_type == "hooks"]
        assert len(hooks_files) == 1
        assert hooks_files[0].path == "src/hooks/index.ts"

    def test_hooks_has_react_query_imports(self, compiler, sample_ir, sample_oas):
        """Hooks devem importar React Query."""
        output = compiler.compile(sample_ir, sample_oas)

        hooks_file = next(f for f in output.files if f.file_type == "hooks")
        content = hooks_file.content

        assert "useQuery" in content
        assert "useMutation" in content
        assert "useQueryClient" in content
        assert "@tanstack/react-query" in content

    def test_hooks_has_list_hook(self, compiler, sample_ir, sample_oas):
        """Deve ter hook de listagem."""
        output = compiler.compile(sample_ir, sample_oas)

        hooks_file = next(f for f in output.files if f.file_type == "hooks")
        content = hooks_file.content

        assert "useEmpresaList" in content
        assert "queryKey: ['empresas']" in content

    def test_hooks_has_get_hook(self, compiler, sample_ir, sample_oas):
        """Deve ter hook de busca por ID."""
        output = compiler.compile(sample_ir, sample_oas)

        hooks_file = next(f for f in output.files if f.file_type == "hooks")
        content = hooks_file.content

        assert "useEmpresa(id:" in content
        assert "enabled: !!id" in content

    def test_hooks_has_mutation_hooks(self, compiler, sample_ir, sample_oas):
        """Deve ter hooks de mutação."""
        output = compiler.compile(sample_ir, sample_oas)

        hooks_file = next(f for f in output.files if f.file_type == "hooks")
        content = hooks_file.content

        assert "useCreateEmpresa" in content
        assert "useUpdateEmpresa" in content
        assert "useDeleteEmpresa" in content

    def test_hooks_invalidate_on_mutation(self, compiler, sample_ir, sample_oas):
        """Hooks de mutação devem invalidar cache."""
        output = compiler.compile(sample_ir, sample_oas)

        hooks_file = next(f for f in output.files if f.file_type == "hooks")
        content = hooks_file.content

        assert "invalidateQueries" in content


# ==================== TESTS: LIST PAGE GENERATION ====================


class TestListPageGeneration:
    """Testes de geração de página de listagem."""

    def test_generates_list_page(self, compiler, sample_ir, sample_oas):
        """Deve gerar página de listagem."""
        output = compiler.compile(sample_ir, sample_oas)

        list_pages = [f for f in output.files if "ListPage" in f.path]
        assert len(list_pages) == 1
        assert "empresa/EmpresaListPage.tsx" in list_pages[0].path

    def test_list_page_uses_hook(self, compiler, sample_ir, sample_oas):
        """Página deve usar hook de listagem."""
        output = compiler.compile(sample_ir, sample_oas)

        list_page = next(f for f in output.files if "ListPage" in f.path)
        content = list_page.content

        assert "useEmpresaList" in content

    def test_list_page_has_table(self, compiler, sample_ir, sample_oas):
        """Página deve ter tabela de dados."""
        output = compiler.compile(sample_ir, sample_oas)

        list_page = next(f for f in output.files if "ListPage" in f.path)
        content = list_page.content

        assert "<table" in content
        assert "<thead>" in content
        assert "<tbody>" in content

    def test_list_page_has_actions(self, compiler, sample_ir, sample_oas):
        """Página deve ter ações (ver, editar, excluir)."""
        output = compiler.compile(sample_ir, sample_oas)

        list_page = next(f for f in output.files if "ListPage" in f.path)
        content = list_page.content

        assert "Ver" in content
        assert "Editar" in content
        assert "Excluir" in content

    def test_list_page_has_create_link(self, compiler, sample_ir, sample_oas):
        """Página deve ter link para criar."""
        output = compiler.compile(sample_ir, sample_oas)

        list_page = next(f for f in output.files if "ListPage" in f.path)
        content = list_page.content

        assert "/empresa/new" in content
        assert "Novo" in content


# ==================== TESTS: FORM PAGE GENERATION ====================


class TestFormPageGeneration:
    """Testes de geração de página de formulário."""

    def test_generates_form_page(self, compiler, sample_ir, sample_oas):
        """Deve gerar página de formulário."""
        output = compiler.compile(sample_ir, sample_oas)

        form_pages = [f for f in output.files if "FormPage" in f.path]
        assert len(form_pages) == 1
        assert "empresa/EmpresaFormPage.tsx" in form_pages[0].path

    def test_form_page_uses_hooks(self, compiler, sample_ir, sample_oas):
        """Página deve usar hooks de mutação."""
        output = compiler.compile(sample_ir, sample_oas)

        form_page = next(f for f in output.files if "FormPage" in f.path)
        content = form_page.content

        assert "useCreateEmpresa" in content
        assert "useUpdateEmpresa" in content

    def test_form_page_has_form(self, compiler, sample_ir, sample_oas):
        """Página deve ter formulário."""
        output = compiler.compile(sample_ir, sample_oas)

        form_page = next(f for f in output.files if "FormPage" in f.path)
        content = form_page.content

        assert "<form" in content
        assert "onSubmit" in content

    def test_form_page_has_fields(self, compiler, sample_ir, sample_oas):
        """Formulário deve ter campos da entidade."""
        output = compiler.compile(sample_ir, sample_oas)

        form_page = next(f for f in output.files if "FormPage" in f.path)
        content = form_page.content

        assert 'name="nome"' in content
        assert 'name="cnpj"' in content
        assert 'name="email"' in content

    def test_form_page_handles_edit_mode(self, compiler, sample_ir, sample_oas):
        """Formulário deve suportar modo de edição."""
        output = compiler.compile(sample_ir, sample_oas)

        form_page = next(f for f in output.files if "FormPage" in f.path)
        content = form_page.content

        assert "isEdit" in content
        assert "useParams" in content

    def test_form_page_has_typed_state(self, compiler, sample_ir, sample_oas):
        """Formulário deve ter estado tipado."""
        output = compiler.compile(sample_ir, sample_oas)

        form_page = next(f for f in output.files if "FormPage" in f.path)
        content = form_page.content

        assert "EmpresaRequest" in content
        assert "useState<EmpresaRequest>" in content


# ==================== TESTS: DETAIL PAGE GENERATION ====================


class TestDetailPageGeneration:
    """Testes de geração de página de detalhes."""

    def test_generates_detail_page(self, compiler, sample_ir, sample_oas):
        """Deve gerar página de detalhes."""
        output = compiler.compile(sample_ir, sample_oas)

        detail_pages = [f for f in output.files if "DetailPage" in f.path]
        assert len(detail_pages) == 1
        assert "empresa/EmpresaDetailPage.tsx" in detail_pages[0].path

    def test_detail_page_uses_hook(self, compiler, sample_ir, sample_oas):
        """Página deve usar hook de busca."""
        output = compiler.compile(sample_ir, sample_oas)

        detail_page = next(f for f in output.files if "DetailPage" in f.path)
        content = detail_page.content

        assert "useEmpresa(id)" in content

    def test_detail_page_shows_fields(self, compiler, sample_ir, sample_oas):
        """Página deve mostrar campos."""
        output = compiler.compile(sample_ir, sample_oas)

        detail_page = next(f for f in output.files if "DetailPage" in f.path)
        content = detail_page.content

        assert "item.nome" in content
        assert "item.cnpj" in content

    def test_detail_page_has_actions(self, compiler, sample_ir, sample_oas):
        """Página deve ter ações."""
        output = compiler.compile(sample_ir, sample_oas)

        detail_page = next(f for f in output.files if "DetailPage" in f.path)
        content = detail_page.content

        assert "Voltar" in content
        assert "Editar" in content
        assert "Excluir" in content


# ==================== TESTS: ROUTER GENERATION ====================


class TestRouterGeneration:
    """Testes de geração de rotas."""

    def test_generates_router_file(self, compiler, sample_ir, sample_oas):
        """Deve gerar arquivo de rotas."""
        output = compiler.compile(sample_ir, sample_oas)

        router_files = [f for f in output.files if f.path == "src/routes.tsx"]
        assert len(router_files) == 1

    def test_router_has_crud_routes(self, compiler, sample_ir, sample_oas):
        """Router deve ter rotas CRUD."""
        output = compiler.compile(sample_ir, sample_oas)

        router_file = next(f for f in output.files if f.path == "src/routes.tsx")
        content = router_file.content

        assert "'/empresa'" in content
        assert "'/empresa/new'" in content
        assert "'/empresa/:id'" in content
        assert "'/empresa/:id/edit'" in content

    def test_router_imports_pages(self, compiler, sample_ir, sample_oas):
        """Router deve importar páginas."""
        output = compiler.compile(sample_ir, sample_oas)

        router_file = next(f for f in output.files if f.path == "src/routes.tsx")
        content = router_file.content

        assert "EmpresaListPage" in content
        assert "EmpresaFormPage" in content
        assert "EmpresaDetailPage" in content


# ==================== TESTS: APP GENERATION ====================


class TestAppGeneration:
    """Testes de geração do App.tsx."""

    def test_generates_app_file(self, compiler, sample_ir, sample_oas):
        """Deve gerar App.tsx."""
        output = compiler.compile(sample_ir, sample_oas)

        app_files = [f for f in output.files if f.path == "src/App.tsx"]
        assert len(app_files) == 1

    def test_app_has_query_client(self, compiler, sample_ir, sample_oas):
        """App deve ter QueryClient."""
        output = compiler.compile(sample_ir, sample_oas)

        app_file = next(f for f in output.files if f.path == "src/App.tsx")
        content = app_file.content

        assert "QueryClient" in content
        assert "QueryClientProvider" in content

    def test_app_has_router(self, compiler, sample_ir, sample_oas):
        """App deve ter BrowserRouter."""
        output = compiler.compile(sample_ir, sample_oas)

        app_file = next(f for f in output.files if f.path == "src/App.tsx")
        content = app_file.content

        assert "BrowserRouter" in content
        assert "Routes" in content

    def test_app_has_navigation(self, compiler, sample_ir, sample_oas):
        """App deve ter navegação."""
        output = compiler.compile(sample_ir, sample_oas)

        app_file = next(f for f in output.files if f.path == "src/App.tsx")
        content = app_file.content

        assert "<nav" in content
        assert "NavLink" in content
        assert "/empresa" in content


# ==================== TESTS: OUTPUT STRUCTURE ====================


class TestFrontendOutput:
    """Testes da estrutura de saída."""

    def test_output_has_entities_list(self, compiler, sample_ir, sample_oas):
        """Output deve ter lista de entidades."""
        output = compiler.compile(sample_ir, sample_oas)

        assert "Empresa" in output.entities

    def test_output_to_dict(self, compiler, sample_ir, sample_oas):
        """Output deve converter para dict."""
        output = compiler.compile(sample_ir, sample_oas)
        output_dict = output.to_dict()

        assert "files" in output_dict
        assert "entities" in output_dict
        assert "file_count" in output_dict

    def test_generated_file_count(self, compiler, sample_ir, sample_oas):
        """Deve gerar número correto de arquivos."""
        output = compiler.compile(sample_ir, sample_oas)

        # 1 types + 1 client + 1 hooks + 3 pages + 1 router + 1 app = 8
        assert len(output.files) == 8


# ==================== TESTS: CONVENIENCE FUNCTION ====================


class TestCompileFrontendFunction:
    """Testes da função compile_frontend."""

    def test_compile_frontend_works(self, sample_ir, sample_oas):
        """Função deve funcionar."""
        output = compile_frontend(sample_ir, sample_oas)

        assert isinstance(output, FrontendOutput)
        assert len(output.files) > 0


# ==================== TESTS: MULTIPLE ENTITIES ====================


class TestMultipleEntities:
    """Testes com múltiplas entidades."""

    @pytest.fixture
    def multi_entity_ir(self):
        """IR com múltiplas entidades."""
        return {
            "meta": {"project_name": "Multi", "version": "1.0.0"},
            "domain": {
                "entities": [
                    {
                        "name": "empresa",
                        "primary_key": "id",
                        "fields": [
                            {"name": "id", "type": "uuid", "required": True},
                            {"name": "nome", "type": "string", "required": True},
                        ],
                    },
                    {
                        "name": "endereco",
                        "primary_key": "id",
                        "fields": [
                            {"name": "id", "type": "uuid", "required": True},
                            {"name": "rua", "type": "string", "required": True},
                        ],
                    },
                ],
                "relations": [],
            },
        }

    def test_generates_files_for_all_entities(self, compiler, multi_entity_ir, sample_oas):
        """Deve gerar arquivos para todas as entidades."""
        output = compiler.compile(multi_entity_ir, sample_oas)

        list_pages = [f for f in output.files if "ListPage" in f.path]
        assert len(list_pages) == 2

    def test_types_has_all_entities(self, compiler, multi_entity_ir, sample_oas):
        """Tipos devem ter todas as entidades."""
        output = compiler.compile(multi_entity_ir, sample_oas)

        types_file = next(f for f in output.files if f.file_type == "types")
        content = types_file.content

        assert "interface Empresa" in content
        assert "interface Endereco" in content

    def test_client_has_all_apis(self, compiler, multi_entity_ir, sample_oas):
        """Client deve ter APIs de todas as entidades."""
        output = compiler.compile(multi_entity_ir, sample_oas)

        client_file = next(f for f in output.files if f.file_type == "client")
        content = client_file.content

        assert "empresaApi" in content
        assert "enderecoApi" in content


# ==================== TESTS: EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_empty_entities(self, compiler, sample_oas):
        """Deve lidar com IR sem entidades."""
        empty_ir = {
            "meta": {"project_name": "Empty"},
            "domain": {"entities": [], "relations": []},
        }

        output = compiler.compile(empty_ir, sample_oas)

        # Deve ter arquivos base (types, client, hooks, router, app)
        assert len(output.files) >= 4

    def test_entity_with_special_chars(self, compiler, sample_oas):
        """Deve normalizar nomes com acentos."""
        ir_with_accents = {
            "meta": {"project_name": "Test"},
            "domain": {
                "entities": [
                    {
                        "name": "situação",
                        "primary_key": "id",
                        "fields": [
                            {"name": "id", "type": "uuid", "required": True},
                            {"name": "descrição", "type": "string", "required": True},
                        ],
                    }
                ],
                "relations": [],
            },
        }

        output = compiler.compile(ir_with_accents, sample_oas)

        types_file = next(f for f in output.files if f.file_type == "types")
        # Nome deve ser normalizado sem acentos
        assert "interface Situacao" in types_file.content

    def test_boolean_field_generates_checkbox(self, compiler, sample_ir, sample_oas):
        """Campo boolean deve gerar checkbox no form."""
        output = compiler.compile(sample_ir, sample_oas)

        form_page = next(f for f in output.files if "FormPage" in f.path)
        content = form_page.content

        assert 'type="checkbox"' in content

    def test_email_field_generates_email_input(self, compiler, sample_ir, sample_oas):
        """Campo email deve gerar input type email."""
        output = compiler.compile(sample_ir, sample_oas)

        form_page = next(f for f in output.files if "FormPage" in f.path)
        content = form_page.content

        assert 'type="email"' in content
