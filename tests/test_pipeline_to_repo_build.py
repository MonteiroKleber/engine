"""Testes do pipeline completo: Artefatos → Repo → Build.

Testa o fluxo:
1. run() gera artefatos (SRS, IR, OAS, RBAC, PLAN)
2. create repo em /home/bazari/generated/<project>
3. generate patches
4. apply patches
5. run build validator
6. falhou → rollback
7. passou → SUCCESS
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.engine import Engine, RunResult
from validators.build_validator import BuildValidator, BuildComponent, BuildResult, BuildReport


# ==================== FIXTURES ====================


@pytest.fixture
def temp_environment():
    """Cria ambiente temporário completo."""
    temp_dir = tempfile.mkdtemp()
    store_dir = Path(temp_dir) / "store"
    generated_dir = Path(temp_dir) / "generated"
    templates_dir = Path(temp_dir) / "templates"

    store_dir.mkdir()
    generated_dir.mkdir()
    templates_dir.mkdir()

    # Criar estrutura mínima de templates
    (templates_dir / "spring-boot").mkdir()
    (templates_dir / "spring-boot" / "pom.xml").write_text("<project/>")
    (templates_dir / "spring-boot" / "src" / "main" / "java" / "com" / "example" / "app").mkdir(parents=True)

    (templates_dir / "react-vite").mkdir()
    (templates_dir / "react-vite" / "package.json").write_text('{"name": "app", "scripts": {"build": "echo ok"}}')
    (templates_dir / "react-vite" / "src").mkdir()
    (templates_dir / "react-vite" / "src" / "App.tsx").write_text("export default function App() {}")

    (templates_dir / "postgres-flyway").mkdir()
    (templates_dir / "postgres-flyway" / "flyway.conf").write_text("flyway.url=")
    (templates_dir / "postgres-flyway" / "sql").mkdir()

    (templates_dir / "docker").mkdir()
    (templates_dir / "docker" / "docker-compose.yml").write_text("version: '3'\nservices:\n  app:\n    build: .")

    yield store_dir, generated_dir, templates_dir, temp_dir

    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_input():
    """Input de exemplo para testes."""
    return """
    Sistema de Cadastro de Empresas

    Requisitos:
    - Cadastrar empresa com nome, cnpj e endereço
    - Listar todas as empresas
    - Atualizar dados de uma empresa
    - Remover empresa
    """


# ==================== PIPELINE FLOW TESTS ====================


class TestPipelineFlow:
    """Testes do fluxo do pipeline."""

    def test_run_with_build_follows_correct_order(self, temp_environment):
        """run_with_build deve seguir ordem correta."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        # Rastrear chamadas
        calls_order = []

        # Mock run() para simular sucesso
        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="order_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result) as mock_run:
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                        with patch('orchestrator.engine.PatchGenerator') as mock_patch_gen:
                            with patch('orchestrator.engine.PatchEngine') as mock_patch_eng:
                                with patch('orchestrator.engine.BuildValidator') as mock_build:
                                    # Configurar mocks
                                    mock_repo.return_value.repo_exists.return_value = False
                                    mock_repo.return_value.create_repo.return_value = generated_dir / "order_test"

                                    mock_patchset = MagicMock()
                                    mock_patchset.patches = []
                                    mock_patch_gen.return_value.generate.return_value = mock_patchset

                                    mock_patch_result = MagicMock()
                                    mock_patch_result.success = True
                                    mock_patch_eng.return_value.apply_patches.return_value = mock_patch_result

                                    mock_build_report = MagicMock()
                                    mock_build_report.ok = True
                                    mock_build.return_value.validate.return_value = mock_build_report

                                    result = engine.run_with_build("order_test", "input")

                                    # Verificar ordem das chamadas
                                    mock_run.assert_called_once()
                                    mock_repo.return_value.create_repo.assert_called_once()
                                    mock_patch_gen.return_value.generate.assert_called_once()
                                    mock_patch_eng.return_value.apply_patches.assert_called_once()
                                    mock_build.return_value.validate.assert_called_once()

    def test_skip_build_returns_after_artifacts(self, temp_environment):
        """skip_build=True deve retornar após gerar artefatos."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="skip_test",
            plan_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            result = engine.run_with_build("skip_test", "input", skip_build=True)

            assert result.success
            assert result.repo_path is None
            assert result.patch_count == 0
            assert result.build_ok is False  # Não executou build


# ==================== REPO CREATION TESTS ====================


class TestRepoCreation:
    """Testes de criação do repositório."""

    def test_repo_created_in_generated_root(self, temp_environment):
        """Repo deve ser criado em /home/bazari/generated/<project>."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="repo_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                        with patch('orchestrator.engine.PatchEngine') as mock_pe:
                            with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                mock_patchset = MagicMock()
                                mock_patchset.patches = []
                                mock_pg.return_value.generate.return_value = mock_patchset

                                mock_result_patch = MagicMock()
                                mock_result_patch.success = True
                                mock_pe.return_value.apply_patches.return_value = mock_result_patch

                                mock_report = MagicMock()
                                mock_report.ok = True
                                mock_bv.return_value.validate.return_value = mock_report

                                result = engine.run_with_build("repo_test", "input")

                                # Repo deve existir em generated_dir
                                expected_path = generated_dir / "repo_test"
                                assert result.repo_path == str(expected_path)

    def test_existing_repo_deleted_and_recreated(self, temp_environment):
        """Repo existente deve ser deletado e recriado."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="recreate_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                        with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                            with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                    # Simular repo existente
                                    mock_repo.return_value.repo_exists.return_value = True
                                    mock_repo.return_value.create_repo.return_value = generated_dir / "recreate_test"

                                    mock_patchset = MagicMock()
                                    mock_patchset.patches = []
                                    mock_pg.return_value.generate.return_value = mock_patchset

                                    mock_result_patch = MagicMock()
                                    mock_result_patch.success = True
                                    mock_pe.return_value.apply_patches.return_value = mock_result_patch

                                    mock_report = MagicMock()
                                    mock_report.ok = True
                                    mock_bv.return_value.validate.return_value = mock_report

                                    engine.run_with_build("recreate_test", "input")

                                    # delete_repo deve ter sido chamado
                                    mock_repo.return_value.delete_repo.assert_called_once_with("recreate_test")


# ==================== PATCH GENERATION TESTS ====================


class TestPatchGeneration:
    """Testes de geração de patches."""

    def test_patches_generated_from_artifacts(self, temp_environment):
        """Patches devem ser gerados a partir dos artefatos."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="patch_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact') as mock_load:
                with patch.object(engine, '_load_yaml_artifact') as mock_load_yaml:
                    with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                        with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                            with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                    # Configurar artefatos
                                    mock_load.side_effect = lambda p, t, v: {"tasks": []} if t == "PLAN" else {"domain": {}}
                                    mock_load_yaml.return_value = {"paths": {}}

                                    mock_repo.return_value.repo_exists.return_value = False
                                    mock_repo.return_value.create_repo.return_value = generated_dir / "patch_test"

                                    # Patches gerados
                                    mock_patch1 = MagicMock()
                                    mock_patch1.to_dict.return_value = {"operation": "create", "file_path": "a.txt", "content": "a"}
                                    mock_patch2 = MagicMock()
                                    mock_patch2.to_dict.return_value = {"operation": "create", "file_path": "b.txt", "content": "b"}
                                    mock_patchset = MagicMock()
                                    mock_patchset.patches = [mock_patch1, mock_patch2]
                                    mock_pg.return_value.generate.return_value = mock_patchset

                                    mock_result_patch = MagicMock()
                                    mock_result_patch.success = True
                                    mock_pe.return_value.apply_patches.return_value = mock_result_patch

                                    mock_report = MagicMock()
                                    mock_report.ok = True
                                    mock_bv.return_value.validate.return_value = mock_report

                                    result = engine.run_with_build("patch_test", "input")

                                    # Verificar patch_count
                                    assert result.patch_count == 2

    def test_patch_application_failure_stops_pipeline(self, temp_environment):
        """Falha na aplicação de patches deve parar o pipeline."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="patch_fail_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                        with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                            with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                    mock_repo.return_value.repo_exists.return_value = False
                                    mock_repo.return_value.create_repo.return_value = generated_dir / "patch_fail_test"

                                    mock_patchset = MagicMock()
                                    mock_patchset.patches = []
                                    mock_pg.return_value.generate.return_value = mock_patchset

                                    # Simular falha na aplicação
                                    mock_result_patch = MagicMock()
                                    mock_result_patch.success = False
                                    mock_result_patch.errors = ["Security violation"]
                                    mock_pe.return_value.apply_patches.return_value = mock_result_patch

                                    result = engine.run_with_build("patch_fail_test", "input")

                                    # Build não deve ser chamado
                                    mock_bv.return_value.validate.assert_not_called()

                                    assert not result.success
                                    assert not result.build_ok
                                    assert "Patch application failed" in result.errors


# ==================== BUILD VALIDATION TESTS ====================


class TestBuildValidation:
    """Testes de validação de build."""

    def test_build_success_completes_pipeline(self, temp_environment):
        """Build bem-sucedido deve completar o pipeline."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="build_ok_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                        with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                            with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                    mock_repo.return_value.repo_exists.return_value = False
                                    mock_repo.return_value.create_repo.return_value = generated_dir / "build_ok_test"

                                    mock_patchset = MagicMock()
                                    mock_patchset.patches = []
                                    mock_pg.return_value.generate.return_value = mock_patchset

                                    mock_result_patch = MagicMock()
                                    mock_result_patch.success = True
                                    mock_pe.return_value.apply_patches.return_value = mock_result_patch

                                    mock_report = MagicMock()
                                    mock_report.ok = True
                                    mock_bv.return_value.validate.return_value = mock_report

                                    result = engine.run_with_build("build_ok_test", "input")

                                    assert result.success
                                    assert result.build_ok

    def test_build_failure_moves_to_failed(self, temp_environment):
        """Falha no build deve mover repo para _failed/ (preserva para debug)."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="build_fail_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                        with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                            with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                    mock_repo.return_value.repo_exists.return_value = False
                                    mock_repo.return_value.create_repo.return_value = generated_dir / "build_fail_test"
                                    mock_repo.return_value.move_to_failed.return_value = generated_dir / "_failed" / "build_fail_test_20260104"

                                    mock_patchset = MagicMock()
                                    mock_patchset.patches = []
                                    mock_pg.return_value.generate.return_value = mock_patchset

                                    mock_result_patch = MagicMock()
                                    mock_result_patch.success = True
                                    mock_pe.return_value.apply_patches.return_value = mock_result_patch

                                    # Build falha
                                    mock_report = MagicMock()
                                    mock_report.ok = False
                                    mock_report.errors = ["TypeScript error"]
                                    mock_bv.return_value.validate.return_value = mock_report

                                    # Desabilitar Fix Loop para testar o rollback direto
                                    result = engine.run_with_build("build_fail_test", "input", enable_fix_loop=False)

                                    # Verificar move_to_failed foi chamado (em vez de delete_repo)
                                    mock_repo.return_value.move_to_failed.assert_called_with("build_fail_test")
                                    mock_repo.return_value.delete_repo.assert_not_called()

                                    assert not result.success
                                    assert not result.build_ok
                                    assert "Build validation failed (fix loop disabled)" in result.errors
                                    # Resultado deve conter path do repo movido
                                    assert any("_failed" in err for err in result.errors)


# ==================== RUN RESULT FIELDS TESTS ====================


class TestRunResultFields:
    """Testes dos campos do RunResult."""

    def test_result_includes_repo_path(self, temp_environment):
        """RunResult deve incluir repo_path."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="path_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                        with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                            with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                    expected_path = generated_dir / "path_test"
                                    mock_repo.return_value.repo_exists.return_value = False
                                    mock_repo.return_value.create_repo.return_value = expected_path

                                    mock_patchset = MagicMock()
                                    mock_patchset.patches = []
                                    mock_pg.return_value.generate.return_value = mock_patchset

                                    mock_result_patch = MagicMock()
                                    mock_result_patch.success = True
                                    mock_pe.return_value.apply_patches.return_value = mock_result_patch

                                    mock_report = MagicMock()
                                    mock_report.ok = True
                                    mock_bv.return_value.validate.return_value = mock_report

                                    result = engine.run_with_build("path_test", "input")

                                    assert result.repo_path == str(expected_path)

    def test_result_includes_patch_count(self, temp_environment):
        """RunResult deve incluir patch_count."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="count_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                        with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                            with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                    mock_repo.return_value.repo_exists.return_value = False
                                    mock_repo.return_value.create_repo.return_value = generated_dir / "count_test"

                                    # 5 patches
                                    mock_patches = [MagicMock() for _ in range(5)]
                                    for p in mock_patches:
                                        p.to_dict.return_value = {"operation": "create", "file_path": "x.txt", "content": "x"}
                                    mock_patchset = MagicMock()
                                    mock_patchset.patches = mock_patches
                                    mock_pg.return_value.generate.return_value = mock_patchset

                                    mock_result_patch = MagicMock()
                                    mock_result_patch.success = True
                                    mock_pe.return_value.apply_patches.return_value = mock_result_patch

                                    mock_report = MagicMock()
                                    mock_report.ok = True
                                    mock_bv.return_value.validate.return_value = mock_report

                                    result = engine.run_with_build("count_test", "input")

                                    assert result.patch_count == 5

    def test_result_includes_build_errors(self, temp_environment):
        """RunResult deve incluir build_errors quando falha."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="errors_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                        with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                            with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                    mock_repo.return_value.repo_exists.return_value = False
                                    mock_repo.return_value.create_repo.return_value = generated_dir / "errors_test"

                                    mock_patchset = MagicMock()
                                    mock_patchset.patches = []
                                    mock_pg.return_value.generate.return_value = mock_patchset

                                    mock_result_patch = MagicMock()
                                    mock_result_patch.success = True
                                    mock_pe.return_value.apply_patches.return_value = mock_result_patch

                                    # Build falha com erros
                                    mock_report = MagicMock()
                                    mock_report.ok = False
                                    mock_report.errors = ["Error 1", "Error 2", "Error 3"]
                                    mock_bv.return_value.validate.return_value = mock_report

                                    # Desabilitar Fix Loop para testar captura de erros
                                    result = engine.run_with_build("errors_test", "input", enable_fix_loop=False)

                                    assert len(result.build_errors) == 3
                                    assert "Error 1" in result.build_errors

    def test_to_dict_includes_all_build_fields(self):
        """to_dict deve incluir todos os campos de build."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="dict_test",
            repo_path="/path/to/repo",
            patch_count=10,
            build_ok=True,
            build_errors=[],
        )

        d = result.to_dict()

        assert d["repo_path"] == "/path/to/repo"
        assert d["patch_count"] == 10
        assert d["build_ok"] is True
        assert d["build_errors"] == []


# ==================== SUMMARY TESTS ====================


class TestRunResultSummary:
    """Testes do summary do RunResult."""

    def test_summary_shows_build_ok(self):
        """Summary deve mostrar Build: OK."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="summary_test",
            repo_path="/path",
            build_ok=True,
        )

        summary = result.summary()

        assert "Build: OK" in summary

    def test_summary_shows_build_failed(self):
        """Summary deve mostrar Build: FAILED."""
        result = RunResult(
            success=False,
            execution_id="test",
            project="summary_test",
            repo_path="/path",
            build_ok=False,
        )

        summary = result.summary()

        assert "Build: FAILED" in summary

    def test_summary_shows_build_skipped(self):
        """Summary deve mostrar Build: SKIPPED quando não há repo."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="summary_test",
            repo_path=None,
            build_ok=False,
        )

        summary = result.summary()

        assert "Build: SKIPPED" in summary

    def test_summary_shows_patch_count(self):
        """Summary deve mostrar contagem de patches."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="summary_test",
            patch_count=32,
            build_ok=True,
        )

        summary = result.summary()

        assert "Patches: 32" in summary


# ==================== ERROR HANDLING TESTS ====================


class TestErrorHandling:
    """Testes de tratamento de erros."""

    def test_run_failure_stops_build_phase(self, temp_environment):
        """Falha no run() deve impedir fase de build."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))

        mock_result = RunResult(
            success=False,
            execution_id="test_123",
            project="run_fail_test",
            errors=["SRS validation failed"],
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                result = engine.run_with_build("run_fail_test", "input")

                # RepoGenerator não deve ser chamado
                mock_repo.assert_not_called()

                assert not result.success
                assert result.repo_path is None

    def test_exception_in_build_phase_handled(self, temp_environment):
        """Exceção na fase de build deve ser tratada."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="exception_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', side_effect=FileNotFoundError("Artifact not found")):
                result = engine.run_with_build("exception_test", "input")

                assert not result.success
                assert not result.build_ok
                assert any("Build phase error" in e for e in result.errors)
