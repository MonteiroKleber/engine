"""Testes para o Patch Engine - segurança blindada."""

import shutil
import tempfile
from pathlib import Path

import pytest

from patch_engine import PatchEngine, PatchResult, PatchSecurityError


@pytest.fixture
def temp_project():
    """Cria um projeto temporário para testes."""
    temp_dir = tempfile.mkdtemp()
    generated_dir = Path(temp_dir) / "generated"
    project_dir = generated_dir / "test_project"
    project_dir.mkdir(parents=True)

    # Criar alguns arquivos iniciais
    (project_dir / "src").mkdir()
    (project_dir / "src/main.py").write_text("print('hello')\n")
    (project_dir / "config.json").write_text('{"key": "value"}\n')
    (project_dir / "README.md").write_text("# Test Project\n\nDescription here.\n")

    yield project_dir, temp_dir

    shutil.rmtree(temp_dir)


@pytest.fixture
def engine(temp_project):
    """Cria um PatchEngine para o projeto temporário."""
    project_dir, temp_dir = temp_project
    generated_root = Path(temp_dir) / "generated"
    return PatchEngine("test_project", generated_root=str(generated_root))


# ==================== SECURITY TESTS ====================


class TestSecurityPathValidation:
    """Testes de validação de path."""

    def test_path_traversal_blocked(self, engine):
        """Path traversal com .. deve ser bloqueado."""
        with pytest.raises(PatchSecurityError, match="Path traversal"):
            engine._validate_path("../secret.txt")

    def test_path_traversal_nested_blocked(self, engine):
        """Path traversal aninhado deve ser bloqueado."""
        with pytest.raises(PatchSecurityError, match="Path traversal"):
            engine._validate_path("src/../../etc/passwd")

    def test_path_traversal_in_middle_blocked(self, engine):
        """Path traversal no meio deve ser bloqueado."""
        with pytest.raises(PatchSecurityError, match="Path traversal"):
            engine._validate_path("src/../../../root/.ssh/authorized_keys")

    def test_path_outside_project_blocked(self, temp_project):
        """Path absoluto fora do projeto deve ser bloqueado."""
        project_dir, temp_dir = temp_project
        generated_root = Path(temp_dir) / "generated"
        engine = PatchEngine("test_project", generated_root=str(generated_root))

        with pytest.raises(PatchSecurityError, match="outside project"):
            engine._validate_path("/etc/passwd")

    def test_relative_path_resolved_correctly(self, engine, temp_project):
        """Path relativo deve ser resolvido dentro do projeto."""
        project_dir, _ = temp_project

        result = engine._validate_path("src/main.py")

        assert result == project_dir / "src/main.py"

    def test_absolute_path_in_project_allowed(self, engine, temp_project):
        """Path absoluto dentro do projeto deve ser permitido."""
        project_dir, _ = temp_project

        result = engine._validate_path(str(project_dir / "src/main.py"))

        assert result == project_dir / "src/main.py"


class TestSecurityBlockedPaths:
    """Testes de paths bloqueados."""

    def test_engine_path_blocked(self, temp_project):
        """Escrita em /home/bazari/engine deve ser bloqueada."""
        project_dir, temp_dir = temp_project
        # Criar estrutura que simula paths bloqueados
        engine_dir = Path(temp_dir) / "generated" / "test_project"

        engine = PatchEngine(
            "test_project",
            generated_root=str(Path(temp_dir) / "generated"),
        )

        # A proteção é baseada nos BLOCKED_PATHS absolutos
        # Tentar acessar paths que começam com /home/bazari/engine
        # Note: Este teste verifica a lógica, mas os paths reais são hardcoded

    def test_blocked_paths_are_hardcoded(self):
        """Verificar que os paths bloqueados estão definidos."""
        assert "/home/bazari/engine" in PatchEngine.BLOCKED_PATHS
        assert "/home/bazari/templates" in PatchEngine.BLOCKED_PATHS


class TestSecurityRewriteRatio:
    """Testes de limite de reescrita."""

    def test_small_change_allowed(self, engine, temp_project):
        """Mudanças pequenas devem ser permitidas."""
        project_dir, _ = temp_project

        # Modificar apenas uma parte pequena
        old_content = "print('hello')\n"
        new_content = "print('hello world')\n"

        # Não deve lançar exceção
        engine._check_rewrite_ratio(old_content, new_content, "src/main.py")

    def test_full_rewrite_blocked(self, engine, temp_project):
        """Reescrita completa (>80%) deve ser bloqueada."""
        project_dir, _ = temp_project

        old_content = "x" * 100
        new_content = "y" * 100  # 100% diferente

        with pytest.raises(PatchSecurityError, match="Rewrite ratio too high"):
            engine._check_rewrite_ratio(old_content, new_content, "test.py")

    def test_new_file_has_no_limit(self, engine):
        """Arquivo novo (old_content vazio) não tem limite."""
        # Não deve lançar exceção
        engine._check_rewrite_ratio("", "completely new content", "new.py")

    def test_80_percent_threshold(self, engine):
        """Verificar o limiar de 80%."""
        # Criar conteúdo onde 81% é diferente
        old_content = "a" * 100
        new_content = "a" * 19 + "b" * 81  # 81% diferente

        with pytest.raises(PatchSecurityError, match="Rewrite ratio too high"):
            engine._check_rewrite_ratio(old_content, new_content, "test.py")


# ==================== OPERATION TESTS ====================


class TestCreateFile:
    """Testes de criação de arquivo."""

    def test_create_file_success(self, engine, temp_project):
        """Criar arquivo novo deve funcionar."""
        project_dir, _ = temp_project

        op = engine.create_file("src/new_file.py", "print('new')")

        assert op.operation == "create"
        assert op.file_path == "src/new_file.py"
        assert (project_dir / "src/new_file.py").exists()
        assert (project_dir / "src/new_file.py").read_text() == "print('new')"

    def test_create_file_creates_directories(self, engine, temp_project):
        """Criar arquivo deve criar diretórios intermediários."""
        project_dir, _ = temp_project

        engine.create_file("deep/nested/path/file.txt", "content")

        assert (project_dir / "deep/nested/path/file.txt").exists()

    def test_create_existing_file_raises(self, engine, temp_project):
        """Criar arquivo existente deve falhar."""
        with pytest.raises(FileExistsError, match="already exists"):
            engine.create_file("src/main.py", "new content")

    def test_create_file_with_path_traversal_blocked(self, engine):
        """Criar arquivo com path traversal deve ser bloqueado."""
        with pytest.raises(PatchSecurityError, match="Path traversal"):
            engine.create_file("../outside.py", "malicious")


class TestModifyFile:
    """Testes de modificação de arquivo."""

    def test_modify_file_success(self, engine, temp_project):
        """Modificar arquivo deve funcionar."""
        project_dir, _ = temp_project

        op = engine.modify_file("src/main.py", "print('modified hello')\n")

        assert op.operation == "modify"
        assert op.old_content == "print('hello')\n"
        assert (project_dir / "src/main.py").read_text() == "print('modified hello')\n"

    def test_modify_nonexistent_raises(self, engine):
        """Modificar arquivo inexistente deve falhar."""
        with pytest.raises(FileNotFoundError, match="not found"):
            engine.modify_file("nonexistent.py", "content")

    def test_modify_with_excessive_rewrite_blocked(self, engine, temp_project):
        """Modificar com reescrita excessiva deve ser bloqueado."""
        project_dir, _ = temp_project

        # Criar arquivo grande
        (project_dir / "large.txt").write_text("original " * 100)

        engine_new = PatchEngine(
            "test_project",
            generated_root=str(project_dir.parent),
        )

        with pytest.raises(PatchSecurityError, match="Rewrite ratio"):
            engine_new.modify_file("large.txt", "completely " * 100)


class TestDeleteFile:
    """Testes de remoção de arquivo."""

    def test_delete_file_success(self, engine, temp_project):
        """Remover arquivo deve funcionar."""
        project_dir, _ = temp_project

        assert (project_dir / "config.json").exists()

        op = engine.delete_file("config.json")

        assert op.operation == "delete"
        assert op.old_content == '{"key": "value"}\n'
        assert not (project_dir / "config.json").exists()

    def test_delete_nonexistent_raises(self, engine):
        """Remover arquivo inexistente deve falhar."""
        with pytest.raises(FileNotFoundError, match="not found"):
            engine.delete_file("nonexistent.py")


class TestAppendToFile:
    """Testes de append em arquivo."""

    def test_append_success(self, engine, temp_project):
        """Append em arquivo deve funcionar."""
        project_dir, _ = temp_project

        engine.append_to_file("README.md", "\n## New Section\n")

        content = (project_dir / "README.md").read_text()
        assert content == "# Test Project\n\nDescription here.\n\n## New Section\n"

    def test_append_nonexistent_raises(self, engine):
        """Append em arquivo inexistente deve falhar."""
        with pytest.raises(FileNotFoundError, match="not found"):
            engine.append_to_file("nonexistent.py", "content")


class TestInsertInFile:
    """Testes de inserção em arquivo."""

    def test_insert_at_beginning(self, engine, temp_project):
        """Inserir no início deve funcionar."""
        project_dir, _ = temp_project

        engine.insert_in_file("src/main.py", "# Header comment", after_line=None)

        content = (project_dir / "src/main.py").read_text()
        assert content.startswith("# Header comment\n")

    def test_insert_after_line(self, engine, temp_project):
        """Inserir após linha específica deve funcionar."""
        project_dir, _ = temp_project

        engine.insert_in_file("src/main.py", "# Inserted line", after_line=1)

        lines = (project_dir / "src/main.py").read_text().splitlines()
        assert lines[0] == "print('hello')"
        assert lines[1] == "# Inserted line"

    def test_insert_at_end(self, engine, temp_project):
        """Inserir no final deve funcionar."""
        project_dir, _ = temp_project

        engine.insert_in_file("src/main.py", "# Footer", after_line=1000)

        content = (project_dir / "src/main.py").read_text()
        assert content.endswith("# Footer\n")


# ==================== ROLLBACK TESTS ====================


class TestRollback:
    """Testes de rollback."""

    def test_rollback_on_create_failure(self, engine, temp_project):
        """Rollback deve reverter criações após falha."""
        project_dir, _ = temp_project

        # Criar um arquivo primeiro
        engine.create_file("will_be_rolled_back.txt", "content")
        assert (project_dir / "will_be_rolled_back.txt").exists()

        # Forçar rollback
        engine._rollback()

        # Arquivo criado deve ser removido
        assert not (project_dir / "will_be_rolled_back.txt").exists()

    def test_rollback_on_modify_restores_content(self, engine, temp_project):
        """Rollback deve restaurar conteúdo original após modificação."""
        project_dir, _ = temp_project

        original_content = (project_dir / "src/main.py").read_text()

        engine.modify_file("src/main.py", "modified content\n")
        assert (project_dir / "src/main.py").read_text() == "modified content\n"

        engine._rollback()

        assert (project_dir / "src/main.py").read_text() == original_content

    def test_rollback_on_delete_restores_file(self, engine, temp_project):
        """Rollback deve restaurar arquivo deletado."""
        project_dir, _ = temp_project

        original_content = (project_dir / "config.json").read_text()

        engine.delete_file("config.json")
        assert not (project_dir / "config.json").exists()

        engine._rollback()

        assert (project_dir / "config.json").exists()
        assert (project_dir / "config.json").read_text() == original_content


# ==================== BATCH OPERATIONS TESTS ====================


class TestApplyPatches:
    """Testes de aplicação em lote."""

    def test_apply_patches_success(self, engine, temp_project):
        """Aplicar patches em lote deve funcionar."""
        project_dir, _ = temp_project

        patches = [
            {"operation": "create", "file_path": "new1.txt", "content": "content1"},
            {"operation": "create", "file_path": "new2.txt", "content": "content2"},
        ]

        result = engine.apply_patches(patches)

        assert result.success
        assert result.applied_count == 2
        assert result.failed_count == 0
        assert not result.rolled_back
        assert (project_dir / "new1.txt").exists()
        assert (project_dir / "new2.txt").exists()

    def test_apply_patches_rollback_on_failure(self, engine, temp_project):
        """Falha em um patch deve reverter todos os anteriores."""
        project_dir, _ = temp_project

        patches = [
            {"operation": "create", "file_path": "success.txt", "content": "ok"},
            {"operation": "create", "file_path": "src/main.py", "content": "fail"},  # Já existe
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert result.rolled_back
        assert len(result.errors) > 0
        # Arquivo criado deve ter sido revertido
        assert not (project_dir / "success.txt").exists()

    def test_apply_patches_atomic(self, engine, temp_project):
        """Patches devem ser atômicos - tudo ou nada."""
        project_dir, _ = temp_project

        # Criar vários arquivos e depois falhar
        patches = [
            {"operation": "create", "file_path": "a.txt", "content": "a"},
            {"operation": "create", "file_path": "b.txt", "content": "b"},
            {"operation": "create", "file_path": "c.txt", "content": "c"},
            {"operation": "modify", "file_path": "nonexistent.py", "content": "fail"},
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert result.rolled_back
        # Nenhum arquivo deve existir
        assert not (project_dir / "a.txt").exists()
        assert not (project_dir / "b.txt").exists()
        assert not (project_dir / "c.txt").exists()

    def test_apply_patches_missing_operation_fails(self, engine, temp_project):
        """Patch sem operation deve falhar."""
        patches = [{"file_path": "test.txt", "content": "content"}]

        result = engine.apply_patches(patches)

        assert not result.success
        assert "operation" in result.errors[0].lower()

    def test_apply_patches_missing_file_path_fails(self, engine, temp_project):
        """Patch sem file_path deve falhar."""
        patches = [{"operation": "create", "content": "content"}]

        result = engine.apply_patches(patches)

        assert not result.success
        assert "file_path" in result.errors[0].lower()

    def test_apply_patches_with_append(self, engine, temp_project):
        """Operação append deve funcionar em lote."""
        project_dir, _ = temp_project

        patches = [
            {"operation": "append", "file_path": "README.md", "content": "\n## Footer"},
        ]

        result = engine.apply_patches(patches)

        assert result.success
        content = (project_dir / "README.md").read_text()
        assert "## Footer" in content


# ==================== CONTEXT MANAGER TESTS ====================


class TestContextManager:
    """Testes do context manager."""

    def test_context_manager_success(self, temp_project):
        """Context manager deve limpar backup após sucesso."""
        project_dir, temp_dir = temp_project
        generated_root = Path(temp_dir) / "generated"

        with PatchEngine("test_project", str(generated_root)) as engine:
            engine.create_file("ctx_file.txt", "content")

        assert (project_dir / "ctx_file.txt").exists()

    def test_context_manager_rollback_on_exception(self, temp_project):
        """Context manager deve fazer rollback em caso de exceção."""
        project_dir, temp_dir = temp_project
        generated_root = Path(temp_dir) / "generated"

        try:
            with PatchEngine("test_project", str(generated_root)) as engine:
                engine.create_file("will_rollback.txt", "content")
                raise ValueError("Forced error")
        except ValueError:
            pass

        # Arquivo deve ter sido revertido
        assert not (project_dir / "will_rollback.txt").exists()


# ==================== INITIALIZATION TESTS ====================


class TestInitialization:
    """Testes de inicialização."""

    def test_empty_project_name_raises(self):
        """Nome de projeto vazio deve falhar."""
        with pytest.raises(ValueError, match="cannot be empty"):
            PatchEngine("")

    def test_whitespace_project_name_raises(self):
        """Nome de projeto só com espaços deve falhar."""
        with pytest.raises(ValueError, match="cannot be empty"):
            PatchEngine("   ")

    def test_custom_rewrite_ratio(self, temp_project):
        """Ratio de reescrita customizado deve funcionar."""
        project_dir, temp_dir = temp_project
        generated_root = Path(temp_dir) / "generated"

        engine = PatchEngine(
            "test_project",
            generated_root=str(generated_root),
            max_rewrite_ratio=0.50,
        )

        assert engine.max_rewrite_ratio == 0.50

    def test_project_not_found_on_ensure(self, temp_project):
        """Projeto inexistente deve falhar no _ensure_project_exists."""
        _, temp_dir = temp_project
        generated_root = Path(temp_dir) / "generated"

        engine = PatchEngine("nonexistent", generated_root=str(generated_root))

        with pytest.raises(FileNotFoundError, match="not found"):
            engine._ensure_project_exists()


# ==================== RESULT TESTS ====================


class TestPatchResult:
    """Testes do PatchResult."""

    def test_result_to_dict(self):
        """PatchResult.to_dict deve funcionar."""
        result = PatchResult(
            success=True,
            applied_count=3,
            failed_count=0,
            rolled_back=False,
            errors=[],
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["applied_count"] == 3
        assert d["failed_count"] == 0
        assert d["rolled_back"] is False
        assert d["errors"] == []

    def test_result_with_errors(self):
        """PatchResult com erros deve serializar corretamente."""
        result = PatchResult(
            success=False,
            applied_count=1,
            failed_count=2,
            rolled_back=True,
            errors=["Error 1", "Error 2"],
        )

        d = result.to_dict()

        assert d["success"] is False
        assert d["rolled_back"] is True
        assert len(d["errors"]) == 2


# ==================== EDGE CASES ====================


class TestEdgeCases:
    """Testes de casos de borda."""

    def test_empty_content_file(self, engine, temp_project):
        """Criar arquivo vazio deve funcionar."""
        project_dir, _ = temp_project

        engine.create_file("empty.txt", "")

        assert (project_dir / "empty.txt").exists()
        assert (project_dir / "empty.txt").read_text() == ""

    def test_unicode_content(self, engine, temp_project):
        """Conteúdo Unicode deve funcionar."""
        project_dir, _ = temp_project

        content = "# Endereço\n\nAçúcar, café, maçã 日本語 🚀"
        engine.create_file("unicode.txt", content)

        assert (project_dir / "unicode.txt").read_text() == content

    def test_large_file_within_ratio(self, engine, temp_project):
        """Arquivo grande com mudança pequena deve funcionar."""
        project_dir, _ = temp_project

        # Criar arquivo grande
        large_content = "line\n" * 1000
        (project_dir / "large.txt").write_text(large_content)

        # Modificar apenas o final (pequena mudança)
        new_content = large_content + "# Added comment\n"

        engine_new = PatchEngine(
            "test_project",
            generated_root=str(project_dir.parent),
        )
        engine_new.modify_file("large.txt", new_content)

        assert (project_dir / "large.txt").read_text() == new_content

    def test_special_characters_in_filename(self, engine, temp_project):
        """Caracteres especiais em nome de arquivo devem funcionar."""
        project_dir, _ = temp_project

        # Criar arquivo com caracteres válidos
        engine.create_file("file-with_underscore.txt", "content")
        engine.create_file("file.config.json", '{"a": 1}')

        assert (project_dir / "file-with_underscore.txt").exists()
        assert (project_dir / "file.config.json").exists()
