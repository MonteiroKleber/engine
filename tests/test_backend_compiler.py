"""Testes para o BackendCompiler.

Verifica:
- Geração de JPA Entity completa
- Geração de DTOs (Request/Response)
- Geração de Repository funcional
- Geração de Service com CRUD real
- Geração de Controller com @PreAuthorize
- Integração com IR + OAS + RBAC
"""

import pytest

from compilers.backend_compiler import (
    BackendCompiler,
    BackendOutput,
    GeneratedFile,
    compile_backend,
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
            "operations": [
                {"resource": "empresa", "method": "GET", "path": "/api/empresas"},
                {"resource": "empresa", "method": "POST", "path": "/api/empresas"},
            ],
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
def sample_rbac():
    """RBAC de exemplo."""
    return {
        "roles": ["authenticated", "admin"],
        "permissions": [
            {"operation_id": "listEmpresas", "required_role": "authenticated"},
            {"operation_id": "createEmpresa", "required_role": "admin"},
            {"operation_id": "getEmpresa", "required_role": "authenticated"},
            {"operation_id": "updateEmpresa", "required_role": "admin"},
            {"operation_id": "deleteEmpresa", "required_role": "admin"},
        ],
    }


@pytest.fixture
def compiler():
    """Retorna instância do BackendCompiler."""
    return BackendCompiler()


# ==================== TESTS: COMPILER INIT ====================


class TestBackendCompilerInit:
    """Testes de inicialização do BackendCompiler."""

    def test_default_package(self, compiler):
        """Deve usar pacote padrão."""
        assert compiler.base_package == "com.example.app"

    def test_custom_package(self):
        """Deve aceitar pacote customizado."""
        compiler = BackendCompiler(base_package="br.com.empresa")
        assert compiler.base_package == "br.com.empresa"

    def test_java_path_generation(self, compiler):
        """Deve gerar path Java corretamente."""
        path = compiler._java_path("domain", "Empresa.java")
        assert path == "src/main/java/com/example/app/domain/Empresa.java"


# ==================== TESTS: ENTITY GENERATION ====================


class TestEntityGeneration:
    """Testes de geração de JPA Entity."""

    def test_generates_entity_file(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Deve gerar arquivo de entidade."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        entity_files = [f for f in output.files if f.file_type == "entity"]
        assert len(entity_files) == 1
        assert "Empresa.java" in entity_files[0].path

    def test_entity_has_jpa_annotations(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Entity deve ter annotations JPA."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        entity = next(f for f in output.files if f.file_type == "entity")
        content = entity.content

        assert "@Entity" in content
        assert '@Table(name = "empresa")' in content
        assert "@Id" in content
        assert "@GeneratedValue" in content

    def test_entity_has_lombok(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Entity deve ter Lombok annotations."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        entity = next(f for f in output.files if f.file_type == "entity")
        content = entity.content

        assert "@Data" in content
        assert "@NoArgsConstructor" in content
        assert "@AllArgsConstructor" in content
        assert "@Builder" in content

    def test_entity_has_validation_annotations(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Entity deve ter Bean Validation."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        entity = next(f for f in output.files if f.file_type == "entity")
        content = entity.content

        assert "@NotNull" in content
        assert "@Email" in content

    def test_entity_has_unique_constraint(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Entity deve ter constraint unique."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        entity = next(f for f in output.files if f.file_type == "entity")
        content = entity.content

        assert "unique = true" in content

    def test_entity_has_lifecycle_hooks(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Entity deve ter @PrePersist e @PreUpdate."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        entity = next(f for f in output.files if f.file_type == "entity")
        content = entity.content

        assert "@PrePersist" in content
        assert "@PreUpdate" in content
        assert "createdAt" in content
        assert "updatedAt" in content


# ==================== TESTS: DTO GENERATION ====================


class TestDtoGeneration:
    """Testes de geração de DTOs."""

    def test_generates_request_dto(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Deve gerar DTO de Request."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        dto_files = [f for f in output.files if f.file_type == "dto"]
        request_dto = next((f for f in dto_files if "Request" in f.path), None)

        assert request_dto is not None
        assert "EmpresaRequest.java" in request_dto.path

    def test_generates_response_dto(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Deve gerar DTO de Response."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        dto_files = [f for f in output.files if f.file_type == "dto"]
        response_dto = next((f for f in dto_files if "Response" in f.path), None)

        assert response_dto is not None
        assert "EmpresaResponse.java" in response_dto.path

    def test_request_dto_has_no_id(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Request DTO não deve ter campo ID."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        dto_files = [f for f in output.files if f.file_type == "dto"]
        request_dto = next(f for f in dto_files if "Request" in f.path)

        # ID não deve estar no Request (exceto em campos com nome diferente)
        lines = request_dto.content.split("\n")
        field_lines = [l for l in lines if "private UUID id" in l]
        assert len(field_lines) == 0

    def test_response_dto_has_timestamps(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Response DTO deve ter timestamps."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        dto_files = [f for f in output.files if f.file_type == "dto"]
        response_dto = next(f for f in dto_files if "Response" in f.path)

        assert "createdAt" in response_dto.content
        assert "updatedAt" in response_dto.content

    def test_request_dto_has_validation(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Request DTO deve ter validação."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        dto_files = [f for f in output.files if f.file_type == "dto"]
        request_dto = next(f for f in dto_files if "Request" in f.path)

        assert "@NotNull" in request_dto.content


# ==================== TESTS: REPOSITORY GENERATION ====================


class TestRepositoryGeneration:
    """Testes de geração de Repository."""

    def test_generates_repository(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Deve gerar Repository."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        repo_files = [f for f in output.files if f.file_type == "repository"]
        assert len(repo_files) == 1
        assert "EmpresaRepository.java" in repo_files[0].path

    def test_repository_extends_jpa_repository(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Repository deve estender JpaRepository."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        repo = next(f for f in output.files if f.file_type == "repository")
        assert "extends JpaRepository<Empresa, UUID>" in repo.content

    def test_repository_has_stereotype(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Repository deve ter @Repository."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        repo = next(f for f in output.files if f.file_type == "repository")
        assert "@Repository" in repo.content

    def test_repository_has_custom_finder(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Repository deve ter finder para campo unique."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        repo = next(f for f in output.files if f.file_type == "repository")
        # CNPJ é unique, deve ter findByCnpj
        assert "findByCnpj" in repo.content


# ==================== TESTS: SERVICE GENERATION ====================


class TestServiceGeneration:
    """Testes de geração de Service."""

    def test_generates_service(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Deve gerar Service."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        service_files = [f for f in output.files if f.file_type == "service"]
        assert len(service_files) == 1
        assert "EmpresaService.java" in service_files[0].path

    def test_service_has_annotations(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Service deve ter annotations Spring."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        service = next(f for f in output.files if f.file_type == "service")
        content = service.content

        assert "@Service" in content
        assert "@RequiredArgsConstructor" in content
        assert "@Transactional" in content

    def test_service_has_crud_methods(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Service deve ter métodos CRUD."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        service = next(f for f in output.files if f.file_type == "service")
        content = service.content

        assert "findAll()" in content
        assert "findById(" in content
        assert "create(" in content
        assert "update(" in content
        assert "deleteById(" in content

    def test_service_has_dto_mapping(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Service deve ter mapeamento DTO."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        service = next(f for f in output.files if f.file_type == "service")
        content = service.content

        assert "toEntity(" in content
        assert "toResponse(" in content
        assert "updateEntity(" in content

    def test_service_uses_dtos(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Service deve usar DTOs nos métodos."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        service = next(f for f in output.files if f.file_type == "service")
        content = service.content

        assert "EmpresaRequest request" in content
        assert "EmpresaResponse" in content

    def test_service_read_only_transactions(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Métodos de leitura devem ser readOnly."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        service = next(f for f in output.files if f.file_type == "service")
        content = service.content

        assert "@Transactional(readOnly = true)" in content


# ==================== TESTS: CONTROLLER GENERATION ====================


class TestControllerGeneration:
    """Testes de geração de Controller."""

    def test_generates_controller(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Deve gerar Controller."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        ctrl_files = [f for f in output.files if f.file_type == "controller"]
        assert len(ctrl_files) == 1
        assert "EmpresaController.java" in ctrl_files[0].path

    def test_controller_has_annotations(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Controller deve ter annotations Spring."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        ctrl = next(f for f in output.files if f.file_type == "controller")
        content = ctrl.content

        assert "@RestController" in content
        assert '@RequestMapping("/api/empresas")' in content
        assert "@RequiredArgsConstructor" in content

    def test_controller_has_crud_endpoints(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Controller deve ter endpoints CRUD."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        ctrl = next(f for f in output.files if f.file_type == "controller")
        content = ctrl.content

        assert "@GetMapping" in content
        assert "@PostMapping" in content
        assert "@PutMapping" in content
        assert "@DeleteMapping" in content

    def test_controller_has_preauthorize(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Controller deve ter @PreAuthorize."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        ctrl = next(f for f in output.files if f.file_type == "controller")
        content = ctrl.content

        assert "@PreAuthorize" in content
        assert "hasRole(" in content

    def test_controller_uses_correct_roles(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Controller deve usar roles corretas do RBAC."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        ctrl = next(f for f in output.files if f.file_type == "controller")
        content = ctrl.content

        # List usa authenticated
        assert "hasRole('AUTHENTICATED')" in content
        # Create usa admin
        assert "hasRole('ADMIN')" in content

    def test_controller_has_validation(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Controller deve validar entrada."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        ctrl = next(f for f in output.files if f.file_type == "controller")
        content = ctrl.content

        assert "@Valid" in content
        assert "@RequestBody" in content

    def test_controller_uses_dtos(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Controller deve usar DTOs."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        ctrl = next(f for f in output.files if f.file_type == "controller")
        content = ctrl.content

        assert "EmpresaRequest" in content
        assert "EmpresaResponse" in content


# ==================== TESTS: SECURITY CONFIG ====================


class TestSecurityConfigGeneration:
    """Testes de geração do SecurityConfig."""

    def test_generates_security_config(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Deve gerar SecurityConfig."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        config_files = [f for f in output.files if f.file_type == "config"]
        assert len(config_files) == 1
        assert "SecurityConfig.java" in config_files[0].path

    def test_security_has_method_security(self, compiler, sample_ir, sample_oas, sample_rbac):
        """SecurityConfig deve habilitar method security."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        config = next(f for f in output.files if f.file_type == "config")
        content = config.content

        assert "@EnableMethodSecurity" in content
        assert "prePostEnabled = true" in content


# ==================== TESTS: OUTPUT STRUCTURE ====================


class TestBackendOutput:
    """Testes da estrutura de saída."""

    def test_output_has_entities_list(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Output deve ter lista de entidades."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        assert "Empresa" in output.entities

    def test_output_to_dict(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Output deve converter para dict."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)
        output_dict = output.to_dict()

        assert "files" in output_dict
        assert "entities" in output_dict
        assert "file_count" in output_dict
        assert output_dict["file_count"] > 0

    def test_generated_file_count(self, compiler, sample_ir, sample_oas, sample_rbac):
        """Deve gerar número correto de arquivos."""
        output = compiler.compile(sample_ir, sample_oas, sample_rbac)

        # 1 entity + 2 DTOs + 1 repo + 1 service + 1 controller + 1 security = 7
        assert len(output.files) == 7


# ==================== TESTS: CONVENIENCE FUNCTION ====================


class TestCompileBackendFunction:
    """Testes da função compile_backend."""

    def test_compile_backend_works(self, sample_ir, sample_oas, sample_rbac):
        """Função deve funcionar."""
        output = compile_backend(sample_ir, sample_oas, sample_rbac)

        assert isinstance(output, BackendOutput)
        assert len(output.files) > 0

    def test_compile_backend_with_custom_package(self, sample_ir, sample_oas, sample_rbac):
        """Função deve aceitar pacote customizado."""
        output = compile_backend(
            sample_ir,
            sample_oas,
            sample_rbac,
            base_package="br.com.empresa",
        )

        entity = next(f for f in output.files if f.file_type == "entity")
        assert "package br.com.empresa.domain;" in entity.content


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
                            {"name": "cidade", "type": "string", "required": True},
                        ],
                    },
                ],
                "relations": [
                    {"from": "endereco", "to": "empresa", "type": "many_to_one"},
                ],
            },
        }

    def test_generates_files_for_all_entities(self, compiler, multi_entity_ir, sample_oas, sample_rbac):
        """Deve gerar arquivos para todas as entidades."""
        output = compiler.compile(multi_entity_ir, sample_oas, sample_rbac)

        entity_files = [f for f in output.files if f.file_type == "entity"]
        assert len(entity_files) == 2

    def test_entities_list_has_all(self, compiler, multi_entity_ir, sample_oas, sample_rbac):
        """Lista de entidades deve ter todas."""
        output = compiler.compile(multi_entity_ir, sample_oas, sample_rbac)

        assert "Empresa" in output.entities
        assert "Endereco" in output.entities

    def test_relation_generates_many_to_one(self, compiler, multi_entity_ir, sample_oas, sample_rbac):
        """Relação deve gerar @ManyToOne."""
        output = compiler.compile(multi_entity_ir, sample_oas, sample_rbac)

        endereco_entity = next(
            f for f in output.files
            if f.file_type == "entity" and "Endereco" in f.path
        )

        assert "@ManyToOne" in endereco_entity.content
        assert "private Empresa empresa;" in endereco_entity.content


# ==================== TESTS: EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_empty_entities(self, compiler, sample_oas, sample_rbac):
        """Deve lidar com IR sem entidades."""
        empty_ir = {
            "meta": {"project_name": "Empty"},
            "domain": {"entities": [], "relations": []},
        }

        output = compiler.compile(empty_ir, sample_oas, sample_rbac)

        # Apenas SecurityConfig
        assert len(output.files) == 1
        assert output.files[0].file_type == "config"

    def test_empty_permissions(self, compiler, sample_ir, sample_oas):
        """Deve lidar com RBAC sem permissions."""
        empty_rbac = {"roles": ["authenticated"], "permissions": []}

        output = compiler.compile(sample_ir, sample_oas, empty_rbac)

        # Deve usar role padrão 'authenticated'
        ctrl = next(f for f in output.files if f.file_type == "controller")
        assert "hasRole('AUTHENTICATED')" in ctrl.content

    def test_entity_with_special_chars(self, compiler, sample_oas, sample_rbac):
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

        output = compiler.compile(ir_with_accents, sample_oas, sample_rbac)

        entity = next(f for f in output.files if f.file_type == "entity")
        # Nome deve ser normalizado sem acentos
        assert "Situacao" in entity.path
        assert 'Table(name = "situacao")' in entity.content
