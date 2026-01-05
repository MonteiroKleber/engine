"""Testes de aplicação de patches e rollback."""

import shutil
import tempfile
from pathlib import Path

import pytest

from patch_engine.patch_engine import PatchEngine, PatchResult, PatchSecurityError


@pytest.fixture
def temp_project():
    """Cria um projeto temporário para testes."""
    temp_dir = tempfile.mkdtemp()
    generated_dir = Path(temp_dir) / "generated"
    project_dir = generated_dir / "test_project"
    project_dir.mkdir(parents=True)

    # Criar estrutura inicial
    (project_dir / "backend").mkdir()
    (project_dir / "backend" / "Main.java").write_text("public class Main {}")
    (project_dir / "frontend").mkdir()
    (project_dir / "frontend" / "App.tsx").write_text("export default function App() {}")
    (project_dir / "config.json").write_text('{"key": "value"}')

    yield project_dir, generated_dir, temp_dir

    shutil.rmtree(temp_dir)


class TestPatchApplicationSuccess:
    """Testes de aplicação bem-sucedida de patches."""

    def test_apply_single_create_patch(self, temp_project):
        """Aplicar patch de criação deve funcionar."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "create", "file_path": "new_file.txt", "content": "new content"}
        ]

        result = engine.apply_patches(patches)

        assert result.success
        assert result.applied_count == 1
        assert (project_dir / "new_file.txt").exists()
        assert (project_dir / "new_file.txt").read_text() == "new content"

    def test_apply_multiple_create_patches(self, temp_project):
        """Aplicar múltiplos patches de criação deve funcionar."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "create", "file_path": "file1.txt", "content": "content1"},
            {"operation": "create", "file_path": "file2.txt", "content": "content2"},
            {"operation": "create", "file_path": "file3.txt", "content": "content3"},
        ]

        result = engine.apply_patches(patches)

        assert result.success
        assert result.applied_count == 3
        assert (project_dir / "file1.txt").exists()
        assert (project_dir / "file2.txt").exists()
        assert (project_dir / "file3.txt").exists()

    def test_apply_nested_directory_patch(self, temp_project):
        """Criar arquivos em diretórios aninhados deve funcionar."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {
                "operation": "create",
                "file_path": "deep/nested/path/file.txt",
                "content": "deep content"
            }
        ]

        result = engine.apply_patches(patches)

        assert result.success
        assert (project_dir / "deep/nested/path/file.txt").exists()

    def test_apply_modify_patch(self, temp_project):
        """Aplicar patch de modificação deve funcionar."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        # Modificar arquivo existente (mudança pequena)
        patches = [
            {
                "operation": "modify",
                "file_path": "config.json",
                "content": '{"key": "new_value"}'
            }
        ]

        result = engine.apply_patches(patches)

        assert result.success
        assert (project_dir / "config.json").read_text() == '{"key": "new_value"}'

    def test_apply_append_patch(self, temp_project):
        """Aplicar patch de append deve funcionar."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        original = (project_dir / "config.json").read_text()

        patches = [
            {
                "operation": "append",
                "file_path": "config.json",
                "content": "\n// appended"
            }
        ]

        result = engine.apply_patches(patches)

        assert result.success
        new_content = (project_dir / "config.json").read_text()
        assert new_content == original + "\n// appended"

    def test_apply_delete_patch(self, temp_project):
        """Aplicar patch de delete deve funcionar."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo para deletar
        (project_dir / "to_delete.txt").write_text("delete me")

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "delete", "file_path": "to_delete.txt"}
        ]

        result = engine.apply_patches(patches)

        assert result.success
        assert not (project_dir / "to_delete.txt").exists()


class TestRollbackOnFailure:
    """Testes de rollback quando patches falham."""

    def test_rollback_on_create_existing_file(self, temp_project):
        """Rollback deve ocorrer se criar arquivo que já existe."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        # Primeiro patch cria arquivo novo, segundo tenta criar existente
        patches = [
            {"operation": "create", "file_path": "new_success.txt", "content": "ok"},
            {"operation": "create", "file_path": "config.json", "content": "fail"},  # Já existe
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert result.rolled_back
        # Arquivo criado deve ter sido revertido
        assert not (project_dir / "new_success.txt").exists()

    def test_rollback_on_modify_nonexistent(self, temp_project):
        """Rollback deve ocorrer se modificar arquivo inexistente."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "create", "file_path": "will_rollback.txt", "content": "ok"},
            {"operation": "modify", "file_path": "nonexistent.txt", "content": "fail"},
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert result.rolled_back
        assert not (project_dir / "will_rollback.txt").exists()

    def test_rollback_restores_modified_content(self, temp_project):
        """Rollback deve restaurar conteúdo original de arquivo modificado."""
        project_dir, generated_dir, _ = temp_project

        original_content = (project_dir / "config.json").read_text()

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "modify", "file_path": "config.json", "content": '{"modified": true}'},
            {"operation": "create", "file_path": "config.json", "content": "fail"},  # Erro
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert result.rolled_back
        # Conteúdo original deve ser restaurado
        assert (project_dir / "config.json").read_text() == original_content

    def test_rollback_restores_deleted_file(self, temp_project):
        """Rollback deve restaurar arquivo deletado."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo para deletar
        (project_dir / "important.txt").write_text("important content")

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "delete", "file_path": "important.txt"},
            {"operation": "modify", "file_path": "nonexistent.txt", "content": "fail"},
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert result.rolled_back
        # Arquivo deletado deve ser restaurado
        assert (project_dir / "important.txt").exists()
        assert (project_dir / "important.txt").read_text() == "important content"

    def test_atomic_all_or_nothing(self, temp_project):
        """Patches devem ser atômicos - tudo ou nada."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        # 5 patches, último falha
        patches = [
            {"operation": "create", "file_path": "a.txt", "content": "a"},
            {"operation": "create", "file_path": "b.txt", "content": "b"},
            {"operation": "create", "file_path": "c.txt", "content": "c"},
            {"operation": "create", "file_path": "d.txt", "content": "d"},
            {"operation": "modify", "file_path": "nonexistent.txt", "content": "fail"},
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert result.rolled_back
        # Nenhum arquivo deve existir
        assert not (project_dir / "a.txt").exists()
        assert not (project_dir / "b.txt").exists()
        assert not (project_dir / "c.txt").exists()
        assert not (project_dir / "d.txt").exists()


class TestRollbackOnSecurityViolation:
    """Testes de rollback em violações de segurança."""

    def test_rollback_on_path_traversal(self, temp_project):
        """Rollback deve ocorrer em tentativa de path traversal."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "create", "file_path": "valid.txt", "content": "ok"},
            {"operation": "create", "file_path": "../escape.txt", "content": "malicious"},
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert result.rolled_back
        assert not (project_dir / "valid.txt").exists()

    def test_rollback_on_excessive_rewrite(self, temp_project):
        """Rollback deve ocorrer em reescrita excessiva."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo grande
        (project_dir / "large.txt").write_text("original " * 100)

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "create", "file_path": "valid.txt", "content": "ok"},
            {"operation": "modify", "file_path": "large.txt", "content": "completely " * 100},
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert result.rolled_back
        assert not (project_dir / "valid.txt").exists()
        # Arquivo original não deve ter sido modificado
        assert "original" in (project_dir / "large.txt").read_text()


class TestContextManagerRollback:
    """Testes de rollback via context manager."""

    def test_context_manager_success(self, temp_project):
        """Context manager deve manter mudanças em caso de sucesso."""
        project_dir, generated_dir, _ = temp_project

        with PatchEngine("test_project", str(generated_dir)) as engine:
            engine.create_file("ctx_file.txt", "created in context")

        assert (project_dir / "ctx_file.txt").exists()

    def test_context_manager_rollback_on_exception(self, temp_project):
        """Context manager deve fazer rollback em caso de exceção."""
        project_dir, generated_dir, _ = temp_project

        try:
            with PatchEngine("test_project", str(generated_dir)) as engine:
                engine.create_file("will_rollback.txt", "should not exist")
                raise ValueError("Forced error")
        except ValueError:
            pass

        assert not (project_dir / "will_rollback.txt").exists()

    def test_context_manager_rollback_multiple_operations(self, temp_project):
        """Context manager deve reverter múltiplas operações."""
        project_dir, generated_dir, _ = temp_project

        original_config = (project_dir / "config.json").read_text()

        try:
            with PatchEngine("test_project", str(generated_dir)) as engine:
                engine.create_file("new1.txt", "content1")
                engine.create_file("new2.txt", "content2")
                engine.modify_file("config.json", '{"modified": true}')
                raise RuntimeError("Abort!")
        except RuntimeError:
            pass

        # Tudo deve estar revertido
        assert not (project_dir / "new1.txt").exists()
        assert not (project_dir / "new2.txt").exists()
        assert (project_dir / "config.json").read_text() == original_config


class TestPatchResultDetails:
    """Testes dos detalhes do PatchResult."""

    def test_result_counts(self, temp_project):
        """PatchResult deve ter contagens corretas."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "create", "file_path": "f1.txt", "content": "1"},
            {"operation": "create", "file_path": "f2.txt", "content": "2"},
        ]

        result = engine.apply_patches(patches)

        assert result.applied_count == 2
        assert result.failed_count == 0

    def test_result_errors_on_failure(self, temp_project):
        """PatchResult deve conter erros em caso de falha."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "modify", "file_path": "nonexistent.txt", "content": "fail"},
        ]

        result = engine.apply_patches(patches)

        assert not result.success
        assert len(result.errors) > 0
        assert "not found" in result.errors[0].lower()

    def test_result_to_dict(self, temp_project):
        """PatchResult.to_dict deve funcionar."""
        project_dir, generated_dir, _ = temp_project

        engine = PatchEngine("test_project", str(generated_dir))

        patches = [
            {"operation": "create", "file_path": "f.txt", "content": "ok"},
        ]

        result = engine.apply_patches(patches)
        d = result.to_dict()

        assert d["success"] is True
        assert d["applied_count"] == 1
        assert d["rolled_back"] is False
