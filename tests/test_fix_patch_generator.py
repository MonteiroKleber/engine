"""Testes para o FixPatchGenerator."""

import shutil
import tempfile
from pathlib import Path

import pytest

from fix_loop.fix_patch_generator import (
    FixPatchGenerator,
    FocalPatch,
    PatchContext,
)
from fix_loop.error_classifier import BuildErrorType, ClassifiedError, BuildStep


@pytest.fixture
def temp_project():
    """Cria projeto temporário para testes."""
    temp_dir = tempfile.mkdtemp()
    generated_dir = Path(temp_dir) / "generated"
    project_dir = generated_dir / "test_project"
    project_dir.mkdir(parents=True)

    # Criar estrutura
    (project_dir / "backend" / "src" / "main" / "java" / "com" / "example").mkdir(parents=True)
    (project_dir / "frontend" / "src").mkdir(parents=True)

    yield project_dir, generated_dir, temp_dir

    shutil.rmtree(temp_dir)


@pytest.fixture
def generator(temp_project):
    """Cria instância do gerador."""
    _, generated_dir, _ = temp_project
    return FixPatchGenerator("test_project", str(generated_dir))


# ==================== BASIC TESTS ====================


class TestFixPatchGeneratorInit:
    """Testes de inicialização."""

    def test_init_with_project(self, temp_project):
        """Deve inicializar com projeto."""
        _, generated_dir, _ = temp_project

        gen = FixPatchGenerator("test_project", str(generated_dir))

        assert gen.project == "test_project"
        assert gen.MAX_LINES_CHANGED == 10

    def test_has_java_imports_map(self, generator):
        """Deve ter mapa de imports Java."""
        assert "ResponseEntity" in generator.JAVA_IMPORTS
        assert "List" in generator.JAVA_IMPORTS
        assert "Entity" in generator.JAVA_IMPORTS

    def test_has_ts_imports_map(self, generator):
        """Deve ter mapa de imports TypeScript."""
        assert "React" in generator.TS_IMPORTS
        assert "useState" in generator.TS_IMPORTS
        assert "axios" in generator.TS_IMPORTS


# ==================== JAVA IMPORT TESTS ====================


class TestJavaImportFix:
    """Testes de correção de import Java."""

    def test_adds_missing_import(self, temp_project, generator):
        """Deve adicionar import faltando."""
        project_dir, _, _ = temp_project

        # Criar arquivo Java sem import
        java_file = project_dir / "Service.java"
        java_file.write_text("""package com.example;

public class Service {
    public ResponseEntity<String> getData() {
        return ResponseEntity.ok("data");
    }
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="cannot find symbol class ResponseEntity",
            file_path="Service.java",
            symbol="ResponseEntity",
        )

        patch = generator.generate(error)

        assert patch is not None
        assert patch.lines_changed == 1
        assert "import org.springframework.http.ResponseEntity" in patch.content
        assert patch.description == "Add import org.springframework.http.ResponseEntity"

    def test_import_after_package(self, temp_project, generator):
        """Import deve ser inserido após package."""
        project_dir, _, _ = temp_project

        java_file = project_dir / "Main.java"
        java_file.write_text("""package com.example;

public class Main {}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="cannot find symbol class List",
            file_path="Main.java",
            symbol="List",
        )

        patch = generator.generate(error)

        assert patch is not None
        # Verificar que import está após package
        lines = patch.content.split("\n")
        package_line = None
        import_line = None
        for i, line in enumerate(lines):
            if line.startswith("package"):
                package_line = i
            if "import java.util.List" in line:
                import_line = i

        assert import_line is not None
        assert package_line is not None
        assert import_line > package_line

    def test_no_duplicate_import(self, temp_project, generator):
        """Não deve duplicar import existente."""
        project_dir, _, _ = temp_project

        java_file = project_dir / "Already.java"
        java_file.write_text("""package com.example;

import java.util.List;

public class Already {
    private List<String> items;
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="cannot find symbol class List",
            file_path="Already.java",
            symbol="List",
        )

        patch = generator.generate(error)

        # Não deve gerar patch pois import já existe
        assert patch is None

    def test_unknown_symbol_returns_none(self, temp_project, generator):
        """Símbolo desconhecido deve retornar None."""
        project_dir, _, _ = temp_project

        java_file = project_dir / "Unknown.java"
        java_file.write_text("""package com.example;
public class Unknown {}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="cannot find symbol class UnknownClass",
            file_path="Unknown.java",
            symbol="UnknownClass",
        )

        patch = generator.generate(error)

        assert patch is None


# ==================== JAVA ANNOTATION TESTS ====================


class TestJavaAnnotationFix:
    """Testes de correção de annotation Java."""

    def test_adds_entity_annotation(self, temp_project, generator):
        """Deve adicionar @Entity."""
        project_dir, _, _ = temp_project

        java_file = project_dir / "User.java"
        java_file.write_text("""package com.example;

public class User {
    private Long id;
    private String name;
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_ANNOTATION,
            step=BuildStep.BACKEND,
            message="Not a managed type: class User",
            file_path="User.java",
            symbol="Entity",
            line_number=3,
        )

        patch = generator.generate(error)

        assert patch is not None
        assert "@Entity" in patch.content
        assert patch.lines_changed == 1


# ==================== TYPESCRIPT IMPORT TESTS ====================


class TestTsImportFix:
    """Testes de correção de import TypeScript."""

    def test_adds_react_import(self, temp_project, generator):
        """Deve adicionar import React."""
        project_dir, _, _ = temp_project

        ts_file = project_dir / "Component.tsx"
        ts_file.write_text("""export default function Component() {
    return <div>Hello</div>;
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.TS_MISSING_IMPORT,
            step=BuildStep.FRONTEND,
            message="Cannot find module 'react'",
            file_path="Component.tsx",
            symbol="React",
        )

        patch = generator.generate(error)

        assert patch is not None
        assert "import React from 'react'" in patch.content
        assert patch.lines_changed == 1

    def test_adds_named_import(self, temp_project, generator):
        """Deve adicionar import nomeado (useState)."""
        project_dir, _, _ = temp_project

        ts_file = project_dir / "Hook.tsx"
        ts_file.write_text("""export default function Hook() {
    const [count, setCount] = useState(0);
    return <div>{count}</div>;
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.TS_MISSING_IMPORT,
            step=BuildStep.FRONTEND,
            message="Cannot find name 'useState'",
            file_path="Hook.tsx",
            symbol="useState",
        )

        patch = generator.generate(error)

        assert patch is not None
        assert "import { useState } from 'react'" in patch.content

    def test_import_at_top_of_file(self, temp_project, generator):
        """Import deve ser no topo do arquivo."""
        project_dir, _, _ = temp_project

        ts_file = project_dir / "TopImport.tsx"
        ts_file.write_text("""const x = 1;
export default function TopImport() {
    return <div>Test</div>;
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.TS_MISSING_IMPORT,
            step=BuildStep.FRONTEND,
            message="Cannot find module 'axios'",
            file_path="TopImport.tsx",
            symbol="axios",
        )

        patch = generator.generate(error)

        assert patch is not None
        lines = patch.content.split("\n")
        # Import deve ser a primeira linha
        assert lines[0].startswith("import axios")


# ==================== TYPESCRIPT EXPORT TESTS ====================


class TestTsExportFix:
    """Testes de correção de export TypeScript."""

    def test_exports_const(self, temp_project, generator):
        """Deve exportar const."""
        project_dir, _, _ = temp_project

        ts_file = project_dir / "utils.ts"
        ts_file.write_text("""const API_URL = 'http://localhost:3000';

function fetchData() {
    return fetch(API_URL);
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.TS_MISSING_EXPORT,
            step=BuildStep.FRONTEND,
            message="export 'API_URL' was not found",
            file_path="utils.ts",
            symbol="API_URL",
        )

        patch = generator.generate(error)

        assert patch is not None
        assert "export const API_URL" in patch.content
        assert patch.lines_changed == 1

    def test_exports_function(self, temp_project, generator):
        """Deve exportar function."""
        project_dir, _, _ = temp_project

        ts_file = project_dir / "helpers.ts"
        ts_file.write_text("""function formatDate(date: Date): string {
    return date.toISOString();
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.TS_MISSING_EXPORT,
            step=BuildStep.FRONTEND,
            message="export 'formatDate' was not found",
            file_path="helpers.ts",
            symbol="formatDate",
        )

        patch = generator.generate(error)

        assert patch is not None
        assert "export function formatDate" in patch.content


# ==================== TYPESCRIPT JSX TESTS ====================


class TestTsJsxFix:
    """Testes de correção de JSX."""

    def test_self_closes_tag(self, temp_project, generator):
        """Deve auto-fechar tag JSX."""
        project_dir, _, _ = temp_project

        ts_file = project_dir / "Broken.tsx"
        ts_file.write_text("""export default function Broken() {
    return <input type="text">
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.TS_JSX_ERROR,
            step=BuildStep.FRONTEND,
            message="JSX element 'input' has no corresponding closing tag",
            file_path="Broken.tsx",
            symbol="input",
            line_number=2,
        )

        patch = generator.generate(error)

        assert patch is not None
        assert "/>" in patch.content or "</input>" in patch.content


# ==================== PATCH SIZE TESTS ====================


class TestPatchSize:
    """Testes de tamanho de patch."""

    def test_patch_has_lines_changed(self, temp_project, generator):
        """Patch deve ter contador de linhas."""
        project_dir, _, _ = temp_project

        java_file = project_dir / "Test.java"
        java_file.write_text("""package com.example;
public class Test {}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="cannot find symbol class List",
            file_path="Test.java",
            symbol="List",
        )

        patch = generator.generate(error)

        assert patch is not None
        assert patch.lines_changed >= 1
        assert patch.lines_changed <= generator.MAX_LINES_CHANGED

    def test_validate_patch_size(self, generator):
        """Deve validar tamanho do patch."""
        small_patch = FocalPatch(
            operation="insert_line",
            file_path="test.java",
            content="import x;",
            line_start=1,
            line_end=1,
            description="Add import",
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            lines_changed=1,
        )

        assert generator.validate_patch_size(small_patch)

        large_patch = FocalPatch(
            operation="replace_all",
            file_path="test.java",
            content="x" * 1000,
            line_start=1,
            line_end=100,
            description="Rewrite file",
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            lines_changed=100,  # Muito grande
        )

        assert not generator.validate_patch_size(large_patch)


# ==================== FOCAL PATCH TESTS ====================


class TestFocalPatch:
    """Testes do FocalPatch."""

    def test_to_dict(self):
        """to_dict deve retornar estrutura correta."""
        patch = FocalPatch(
            operation="insert_line",
            file_path="src/Main.java",
            content="import x;",
            line_start=1,
            line_end=1,
            description="Add import",
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            lines_changed=1,
        )

        d = patch.to_dict()

        assert d["operation"] == "insert_line"
        assert d["file_path"] == "src/Main.java"
        assert d["error_type"] == "java_missing_import"
        assert d["lines_changed"] == 1

    def test_to_patch_dict(self):
        """to_patch_dict deve retornar formato PatchEngine."""
        patch = FocalPatch(
            operation="insert_line",
            file_path="src/Main.java",
            content="full content",
            line_start=1,
            line_end=1,
            description="Add import",
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            lines_changed=1,
        )

        d = patch.to_patch_dict()

        assert d["operation"] == "modify"
        assert d["file_path"] == "src/Main.java"
        assert d["content"] == "full content"


# ==================== PATCH CONTEXT TESTS ====================


class TestPatchContext:
    """Testes do PatchContext."""

    def test_file_lines_property(self):
        """file_lines deve retornar lista de linhas."""
        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="error",
        )

        ctx = PatchContext(
            error=error,
            file_content="line1\nline2\nline3",
        )

        assert ctx.file_lines == ["line1", "line2", "line3"]
        assert ctx.line_count == 3


# ==================== GENERATE MULTIPLE TESTS ====================


class TestGenerateMultiple:
    """Testes de geração de múltiplos patches."""

    def test_generate_multiple_patches(self, temp_project, generator):
        """Deve gerar múltiplos patches."""
        project_dir, _, _ = temp_project

        # Criar arquivos
        (project_dir / "A.java").write_text("package com.example;\npublic class A {}")
        (project_dir / "B.java").write_text("package com.example;\npublic class B {}")

        errors = [
            ClassifiedError(
                error_type=BuildErrorType.JAVA_MISSING_IMPORT,
                step=BuildStep.BACKEND,
                message="cannot find symbol class List",
                file_path="A.java",
                symbol="List",
            ),
            ClassifiedError(
                error_type=BuildErrorType.JAVA_MISSING_IMPORT,
                step=BuildStep.BACKEND,
                message="cannot find symbol class Optional",
                file_path="B.java",
                symbol="Optional",
            ),
        ]

        patches = generator.generate_multiple(errors)

        assert len(patches) == 2

    def test_respects_max_patches(self, temp_project, generator):
        """Deve respeitar limite de patches."""
        project_dir, _, _ = temp_project

        # Criar 5 arquivos
        for i in range(5):
            (project_dir / f"File{i}.java").write_text(f"package com.example;\npublic class File{i} {{}}")

        errors = [
            ClassifiedError(
                error_type=BuildErrorType.JAVA_MISSING_IMPORT,
                step=BuildStep.BACKEND,
                message="cannot find symbol class List",
                file_path=f"File{i}.java",
                symbol="List",
            )
            for i in range(5)
        ]

        patches = generator.generate_multiple(errors, max_patches=2)

        assert len(patches) <= 2


# ==================== EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos limite."""

    def test_file_not_found_returns_none(self, generator):
        """Arquivo não encontrado deve retornar None."""
        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="error",
            file_path="nonexistent.java",
            symbol="List",
        )

        patch = generator.generate(error)

        assert patch is None

    def test_no_file_path_returns_none(self, generator):
        """Sem file_path deve retornar None."""
        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="error",
            file_path=None,
            symbol="List",
        )

        patch = generator.generate(error)

        assert patch is None

    def test_empty_symbol_returns_none(self, temp_project, generator):
        """Símbolo vazio deve retornar None."""
        project_dir, _, _ = temp_project

        (project_dir / "Empty.java").write_text("package com.example;\npublic class Empty {}")

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="error",
            file_path="Empty.java",
            symbol=None,
        )

        patch = generator.generate(error)

        assert patch is None

    def test_unknown_error_type_returns_none(self, temp_project, generator):
        """Tipo de erro desconhecido deve retornar None."""
        project_dir, _, _ = temp_project

        (project_dir / "Unknown.java").write_text("package com.example;\npublic class Unknown {}")

        error = ClassifiedError(
            error_type=BuildErrorType.FATAL_UNCLASSIFIED,
            step=BuildStep.BACKEND,
            message="fatal error",
            file_path="Unknown.java",
        )

        patch = generator.generate(error)

        assert patch is None


# ==================== PROIBIÇÕES ====================


class TestProhibitions:
    """Testes de proibições."""

    def test_max_lines_changed_limit(self, generator):
        """Patches devem respeitar limite de linhas."""
        assert generator.MAX_LINES_CHANGED == 10

    def test_patches_are_minimal(self, temp_project, generator):
        """Patches devem ser mínimos."""
        project_dir, _, _ = temp_project

        java_file = project_dir / "Minimal.java"
        java_file.write_text("""package com.example;

public class Minimal {
    public void method() {
        // many lines
        // of code
        // here
    }
}
""")

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="cannot find symbol class List",
            file_path="Minimal.java",
            symbol="List",
        )

        patch = generator.generate(error)

        assert patch is not None
        # Patch deve modificar apenas 1 linha (o import)
        assert patch.lines_changed == 1
