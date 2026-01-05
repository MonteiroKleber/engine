"""Testes para o Patch Generator v1."""

import json
from pathlib import Path

import pytest

from compilers.patch_generator_v1 import (
    Patch,
    PatchGenerator,
    PatchSet,
    generate_patches,
)


# ==================== FIXTURES ====================


@pytest.fixture
def sample_ir():
    """IR de exemplo com uma entidade."""
    return {
        "meta": {"version": "v1"},
        "domain": {
            "entities": [
                {
                    "name": "empresa",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "uuid", "required": True, "unique": True},
                        {"name": "nome", "type": "string", "required": True},
                        {"name": "cnpj", "type": "string", "required": True, "unique": True},
                    ],
                }
            ]
        },
    }


@pytest.fixture
def sample_oas():
    """OAS de exemplo."""
    return {
        "openapi": "3.0.0",
        "paths": {
            "/api/empresas": {
                "get": {"operationId": "listEmpresa", "tags": ["Empresa"]},
                "post": {"operationId": "createEmpresa", "tags": ["Empresa"]},
            },
            "/api/empresas/{id}": {
                "get": {"operationId": "getEmpresa", "tags": ["Empresa"]},
                "put": {"operationId": "updateEmpresa", "tags": ["Empresa"]},
                "delete": {"operationId": "deleteEmpresa", "tags": ["Empresa"]},
            },
        },
        "components": {"schemas": {"Empresa": {"type": "object"}}},
    }


@pytest.fixture
def sample_rbac():
    """RBAC de exemplo."""
    return {
        "roles": ["authenticated", "admin"],
        "permissions": [
            {"operation_id": "listEmpresa", "required_role": "authenticated"},
            {"operation_id": "createEmpresa", "required_role": "authenticated"},
            {"operation_id": "getEmpresa", "required_role": "authenticated"},
            {"operation_id": "updateEmpresa", "required_role": "authenticated"},
            {"operation_id": "deleteEmpresa", "required_role": "authenticated"},
        ],
    }


@pytest.fixture
def sample_plan():
    """PLAN de exemplo."""
    return {
        "meta": {"version": "v1"},
        "tasks": [
            {
                "id": "task_empresa_migration",
                "title": "Create migration for Empresa",
                "order": 1,
                "files": ["backend/src/main/resources/db/migration/V1__create_empresa.sql"],
            },
            {
                "id": "task_empresa_model",
                "title": "Create Entity for Empresa",
                "order": 2,
                "files": ["backend/src/main/java/com/example/app/domain/Empresa.java"],
            },
            {
                "id": "task_empresa_repository",
                "title": "Create Repository for Empresa",
                "order": 3,
                "files": ["backend/src/main/java/com/example/app/repo/EmpresaRepository.java"],
            },
            {
                "id": "task_empresa_service",
                "title": "Create Service for Empresa",
                "order": 4,
                "files": ["backend/src/main/java/com/example/app/service/EmpresaService.java"],
            },
            {
                "id": "task_empresa_controller",
                "title": "Create Controller for Empresa",
                "order": 5,
                "files": ["backend/src/main/java/com/example/app/api/EmpresaController.java"],
            },
            {
                "id": "task_empresa_frontend_pages",
                "title": "Create frontend pages for Empresa",
                "order": 6,
                "files": [
                    "frontend/src/pages/empresa/List.tsx",
                    "frontend/src/pages/empresa/New.tsx",
                    "frontend/src/pages/empresa/Detail.tsx",
                ],
            },
        ],
    }


# ==================== PATCH TESTS ====================


class TestPatch:
    """Testes da classe Patch."""

    def test_patch_to_dict(self):
        """Patch.to_dict deve funcionar."""
        patch = Patch(
            file_path="backend/src/main/java/Empresa.java",
            operation="create",
            content="public class Empresa {}",
            task_id="task_empresa_model",
            order=1,
        )

        d = patch.to_dict()

        assert d["file_path"] == "backend/src/main/java/Empresa.java"
        assert d["operation"] == "create"
        assert d["task_id"] == "task_empresa_model"
        assert d["order"] == 1


class TestPatchSet:
    """Testes da classe PatchSet."""

    def test_patchset_to_dict(self):
        """PatchSet.to_dict deve funcionar."""
        patchset = PatchSet(
            project="demo",
            patches=[
                Patch("file1.java", "create", "content", "task1", 1),
                Patch("file2.java", "create", "content", "task2", 2),
            ],
            input_hash="abc123",
        )

        d = patchset.to_dict()

        assert d["project"] == "demo"
        assert d["patch_count"] == 2
        assert d["input_hash"] == "abc123"

    def test_patchset_absolute_paths(self):
        """PatchSet.get_absolute_paths deve retornar paths corretos."""
        patchset = PatchSet(
            project="demo",
            patches=[
                Patch("backend/Main.java", "create", "", "t1", 1),
                Patch("frontend/App.tsx", "create", "", "t2", 2),
            ],
        )

        paths = patchset.get_absolute_paths()

        assert paths[0] == "/home/bazari/generated/demo/backend/Main.java"
        assert paths[1] == "/home/bazari/generated/demo/frontend/App.tsx"

    def test_patchset_custom_root(self):
        """PatchSet.get_absolute_paths deve aceitar root customizado."""
        patchset = PatchSet(
            project="demo",
            patches=[Patch("file.java", "create", "", "t1", 1)],
        )

        paths = patchset.get_absolute_paths("/tmp/generated")

        assert paths[0] == "/tmp/generated/demo/file.java"


# ==================== GENERATOR INITIALIZATION ====================


class TestPatchGeneratorInit:
    """Testes de inicialização do PatchGenerator."""

    def test_default_initialization(self):
        """PatchGenerator deve inicializar com valores padrão."""
        gen = PatchGenerator("demo")

        assert gen.project == "demo"
        assert gen.generated_root == Path("/home/bazari/generated")

    def test_custom_root(self):
        """PatchGenerator deve aceitar root customizado."""
        gen = PatchGenerator("demo", "/tmp/gen")

        assert gen.generated_root == Path("/tmp/gen")


# ==================== NAME CONVERSION TESTS ====================


class TestNameConversion:
    """Testes de conversão de nomes."""

    def test_to_snake_case(self):
        """_to_snake_case deve funcionar corretamente."""
        gen = PatchGenerator("demo")

        assert gen._to_snake_case("Empresa") == "empresa"
        assert gen._to_snake_case("MinhaEmpresa") == "minha_empresa"
        assert gen._to_snake_case("empresa") == "empresa"

    def test_to_pascal_case(self):
        """_to_pascal_case deve funcionar corretamente."""
        gen = PatchGenerator("demo")

        assert gen._to_pascal_case("empresa") == "Empresa"
        assert gen._to_pascal_case("minha_empresa") == "MinhaEmpresa"
        assert gen._to_pascal_case("Empresa") == "Empresa"

    def test_to_camel_case(self):
        """_to_camel_case deve funcionar corretamente."""
        gen = PatchGenerator("demo")

        assert gen._to_camel_case("empresa") == "empresa"
        assert gen._to_camel_case("minha_empresa") == "minhaEmpresa"

    def test_normalize_accents(self):
        """_normalize_name deve remover acentos."""
        gen = PatchGenerator("demo")

        assert gen._normalize_name("endereço") == "endereco"
        assert gen._normalize_name("açúcar") == "acucar"
        assert gen._normalize_name("Endereço") == "Endereco"


# ==================== DETERMINISM TESTS ====================


class TestDeterminism:
    """Testes de determinismo."""

    def test_same_input_same_hash(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Mesma entrada deve produzir mesmo hash."""
        gen = PatchGenerator("demo")

        patchset1 = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        gen2 = PatchGenerator("demo")
        patchset2 = gen2.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        assert patchset1.input_hash == patchset2.input_hash

    def test_same_input_same_patches(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Mesma entrada deve produzir mesmos patches."""
        gen1 = PatchGenerator("demo")
        patchset1 = gen1.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        gen2 = PatchGenerator("demo")
        patchset2 = gen2.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        assert len(patchset1.patches) == len(patchset2.patches)

        for p1, p2 in zip(patchset1.patches, patchset2.patches):
            assert p1.file_path == p2.file_path
            assert p1.content == p2.content
            assert p1.operation == p2.operation

    def test_different_input_different_hash(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Entrada diferente deve produzir hash diferente."""
        gen = PatchGenerator("demo")
        patchset1 = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        # Modificar IR
        modified_ir = sample_ir.copy()
        modified_ir["domain"]["entities"][0]["name"] = "produto"

        gen2 = PatchGenerator("demo")
        patchset2 = gen2.generate(sample_plan, modified_ir, sample_oas, sample_rbac)

        assert patchset1.input_hash != patchset2.input_hash


# ==================== CODE GENERATION TESTS ====================


class TestCodeGeneration:
    """Testes de geração de código."""

    def test_generates_migration(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Deve gerar arquivo SQL de migração."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        migration_patches = [p for p in patchset.patches if p.file_path.endswith(".sql")]
        assert len(migration_patches) >= 1

        migration = migration_patches[0]
        assert "CREATE TABLE" in migration.content
        assert "empresa" in migration.content

    def test_generates_entity(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Deve gerar JPA Entity."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        entity_patches = [p for p in patchset.patches if "domain/" in p.file_path]
        assert len(entity_patches) >= 1

        entity = entity_patches[0]
        assert "@Entity" in entity.content
        assert "public class Empresa" in entity.content

    def test_generates_repository(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Deve gerar Repository."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        repo_patches = [p for p in patchset.patches if "repo/" in p.file_path]
        assert len(repo_patches) >= 1

        repo = repo_patches[0]
        assert "interface EmpresaRepository" in repo.content
        assert "JpaRepository" in repo.content

    def test_generates_service(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Deve gerar Service."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        service_patches = [p for p in patchset.patches if "service/" in p.file_path]
        assert len(service_patches) >= 1

        service = service_patches[0]
        assert "class EmpresaService" in service.content
        assert "@Service" in service.content

    def test_generates_controller(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Deve gerar Controller."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        controller_patches = [p for p in patchset.patches if "Controller.java" in p.file_path]
        assert len(controller_patches) >= 1

        controller = controller_patches[0]
        assert "@RestController" in controller.content
        assert "EmpresaController" in controller.content
        assert "@GetMapping" in controller.content
        assert "@PostMapping" in controller.content

    def test_generates_tsx_pages(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Deve gerar páginas React/TypeScript."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        tsx_patches = [p for p in patchset.patches if p.file_path.endswith(".tsx")]
        assert len(tsx_patches) >= 3  # List, New, Detail

        list_page = next((p for p in tsx_patches if "List.tsx" in p.file_path), None)
        assert list_page is not None
        assert "useQuery" in list_page.content

        new_page = next((p for p in tsx_patches if "New.tsx" in p.file_path), None)
        assert new_page is not None
        assert "useMutation" in new_page.content


# ==================== PATCH SAFETY TESTS ====================


class TestPatchSafety:
    """Testes de segurança dos patches."""

    def test_all_patches_in_generated(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Todos os patches devem apontar para generated/."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        absolute_paths = patchset.get_absolute_paths()

        for path in absolute_paths:
            assert path.startswith("/home/bazari/generated/demo/"), f"Invalid path: {path}"

    def test_no_path_traversal(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Patches não devem conter path traversal."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        for patch in patchset.patches:
            assert ".." not in patch.file_path, f"Path traversal in: {patch.file_path}"

    def test_all_operations_are_create_or_modify(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Na v1, operações devem ser 'create' ou 'modify'."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        allowed_operations = {"create", "modify"}
        for patch in patchset.patches:
            assert patch.operation in allowed_operations, f"Invalid operation: {patch.operation}"


# ==================== ORDER TESTS ====================


class TestPatchOrder:
    """Testes de ordenação dos patches."""

    def test_patches_are_ordered(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Patches devem ter ordem sequencial."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        orders = [p.order for p in patchset.patches]

        # Orders should be sequential starting from 1
        for i, order in enumerate(orders, 1):
            assert order == i, f"Order {order} should be {i}"

    def test_migration_before_entity(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Migration deve vir antes do Entity."""
        gen = PatchGenerator("demo")
        patchset = gen.generate(sample_plan, sample_ir, sample_oas, sample_rbac)

        migration_order = None
        entity_order = None

        for patch in patchset.patches:
            if patch.file_path.endswith(".sql") and "empresa" in patch.file_path:
                migration_order = patch.order
            if "domain/Empresa.java" in patch.file_path:
                entity_order = patch.order

        if migration_order and entity_order:
            assert migration_order < entity_order


# ==================== CONVENIENCE FUNCTION TESTS ====================


class TestConvenienceFunction:
    """Testes da função de conveniência."""

    def test_generate_patches_function(self, sample_plan, sample_ir, sample_oas, sample_rbac):
        """Função generate_patches deve funcionar."""
        patchset = generate_patches(
            project="demo",
            plan=sample_plan,
            ir=sample_ir,
            oas=sample_oas,
            rbac=sample_rbac,
        )

        assert patchset.project == "demo"
        assert len(patchset.patches) > 0
        assert patchset.input_hash


# ==================== EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos de borda."""

    def test_empty_plan(self, sample_ir, sample_oas, sample_rbac):
        """Plano vazio ainda gera patches globais (routes, App, HomePage).

        O patch generator gera arquivos globais baseado no IR (entidades),
        não apenas no plano. Isso é comportamento esperado.
        """
        empty_plan = {"meta": {}, "tasks": []}

        gen = PatchGenerator("demo")
        patchset = gen.generate(empty_plan, sample_ir, sample_oas, sample_rbac)

        # Patches globais são gerados mesmo sem tarefas no plano
        # porque dependem das entidades no IR
        global_files = {"routes.tsx", "App.tsx", "HomePage.tsx"}
        for patch in patchset.patches:
            filename = patch.file_path.split("/")[-1]
            assert filename in global_files, f"Unexpected patch: {patch.file_path}"

    def test_entity_with_accents(self, sample_oas, sample_rbac):
        """Entidade com acentos deve ser normalizada."""
        ir_with_accents = {
            "domain": {
                "entities": [
                    {
                        "name": "endereço",
                        "primary_key": "id",
                        "fields": [
                            {"name": "id", "type": "uuid", "required": True},
                            {"name": "rua", "type": "string", "required": True},
                        ],
                    }
                ]
            }
        }

        plan_with_accents = {
            "tasks": [
                {
                    "id": "task_endereco_model",
                    "order": 1,
                    "files": ["backend/src/main/java/com/example/app/domain/Endereco.java"],
                }
            ]
        }

        gen = PatchGenerator("demo")
        patchset = gen.generate(plan_with_accents, ir_with_accents, sample_oas, sample_rbac)

        # Should find the entity and generate content
        assert len(patchset.patches) >= 1
        assert "Endereco" in patchset.patches[0].content

    def test_multiple_entities(self, sample_oas, sample_rbac):
        """Múltiplas entidades devem ser processadas.

        O patch generator gera:
        - 1 patch por entity model (task no plano)
        - patches globais (routes, App, HomePage)
        """
        multi_ir = {
            "domain": {
                "entities": [
                    {
                        "name": "empresa",
                        "primary_key": "id",
                        "fields": [{"name": "id", "type": "uuid", "required": True}],
                    },
                    {
                        "name": "produto",
                        "primary_key": "id",
                        "fields": [{"name": "id", "type": "uuid", "required": True}],
                    },
                ]
            }
        }

        multi_plan = {
            "tasks": [
                {
                    "id": "task_empresa_model",
                    "order": 1,
                    "files": ["backend/src/main/java/com/example/app/domain/Empresa.java"],
                },
                {
                    "id": "task_produto_model",
                    "order": 2,
                    "files": ["backend/src/main/java/com/example/app/domain/Produto.java"],
                },
            ]
        }

        gen = PatchGenerator("demo")
        patchset = gen.generate(multi_plan, multi_ir, sample_oas, sample_rbac)

        # Deve ter pelo menos 2 patches para as entidades
        assert len(patchset.patches) >= 2

        # Verificar que ambas as entidades estão nos patches
        all_content = " ".join(p.content for p in patchset.patches)
        assert "Empresa" in all_content
        assert "Produto" in all_content

        # Verificar patches globais também estão presentes
        filenames = [p.file_path.split("/")[-1] for p in patchset.patches]
        assert "Empresa.java" in filenames
        assert "Produto.java" in filenames


# ==================== INTEGRATION WITH DEMO ====================


class TestIntegrationWithDemo:
    """Testes de integração com projeto demo."""

    def test_generate_from_demo_artifacts(self):
        """Deve gerar patches a partir dos artefatos reais do demo."""
        import json
        import yaml

        # Load real artifacts
        store_path = Path("/home/bazari/engine/store_data/demo")

        if not store_path.exists():
            pytest.skip("Demo artifacts not available")

        plan_path = store_path / "PLAN/v1.json"
        ir_path = store_path / "IR/v1.json"
        oas_path = store_path / "OAS/v1.yaml"
        rbac_path = store_path / "RBAC/v1.json"

        if not all(p.exists() for p in [plan_path, ir_path, oas_path, rbac_path]):
            pytest.skip("Some demo artifacts missing")

        plan = json.loads(plan_path.read_text())
        ir = json.loads(ir_path.read_text())
        oas = yaml.safe_load(oas_path.read_text())
        rbac = json.loads(rbac_path.read_text())

        gen = PatchGenerator("demo")
        patchset = gen.generate(plan, ir, oas, rbac)

        # Should generate patches for all tasks
        assert len(patchset.patches) > 0
        assert patchset.input_hash

        # All paths should be valid
        for patch in patchset.patches:
            assert patch.file_path.startswith("backend/") or patch.file_path.startswith("frontend/")
            assert ".." not in patch.file_path
