"""Testes para integração do Fix Loop no Engine.

Verifica:
- Fix Loop é chamado quando build falha
- fix_attempts, fixes_applied, final_status no RunResult
- Rollback quando Fix Loop não consegue corrigir
- enable_fix_loop=False desativa Fix Loop
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from orchestrator.engine import Engine, RunResult
from fix_loop.fix_loop_agent import FixLoopResult, FixAttempt, FixAttemptStatus, FixPatch
from fix_loop.error_classifier import BuildErrorType
from validators.build_validator import BuildReport


# ==================== FIXTURES ====================


@pytest.fixture
def engine(tmp_path):
    """Engine com store temporário."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    return Engine(store_root=str(store_dir))


@pytest.fixture
def successful_build_report():
    """BuildReport de sucesso."""
    return BuildReport(
        ok=True,
        project="test",
        results=[],
        errors=[],
    )


@pytest.fixture
def failed_build_report():
    """BuildReport de falha."""
    return BuildReport(
        ok=False,
        project="test",
        results=[],
        errors=["TS2304: Cannot find name 'React'"],
    )


@pytest.fixture
def successful_fix_result():
    """FixLoopResult de sucesso."""
    return FixLoopResult(
        success=True,
        project="test",
        total_attempts=1,
        attempts=[
            FixAttempt(
                attempt_number=1,
                status=FixAttemptStatus.SUCCESS,
                patch_applied=FixPatch(
                    operation="modify",
                    file_path="src/App.tsx",
                    content="import React from 'react';",
                    error_type=BuildErrorType.TS_MISSING_IMPORT,
                    description="Add React import",
                ),
            )
        ],
        final_build_ok=True,
    )


@pytest.fixture
def failed_fix_result():
    """FixLoopResult de falha."""
    return FixLoopResult(
        success=False,
        project="test",
        total_attempts=3,
        attempts=[],
        final_build_ok=False,
        aborted_reason="Max attempts (3) reached",
    )


# ==================== TESTS: RunResult FIELDS ====================


class TestRunResultFields:
    """Testes dos novos campos no RunResult."""

    def test_run_result_has_fix_attempts(self):
        """RunResult deve ter campo fix_attempts."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
        )
        assert hasattr(result, "fix_attempts")
        assert result.fix_attempts == 0

    def test_run_result_has_fixes_applied(self):
        """RunResult deve ter campo fixes_applied."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
        )
        assert hasattr(result, "fixes_applied")
        assert result.fixes_applied == []

    def test_run_result_has_final_status(self):
        """RunResult deve ter campo final_status."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
        )
        assert hasattr(result, "final_status")
        assert result.final_status == ""

    def test_run_result_has_fix_loop_aborted_reason(self):
        """RunResult deve ter campo fix_loop_aborted_reason."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
        )
        assert hasattr(result, "fix_loop_aborted_reason")
        assert result.fix_loop_aborted_reason == ""

    def test_run_result_to_dict_includes_fix_fields(self):
        """to_dict deve incluir campos do fix loop."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            fix_attempts=2,
            fixes_applied=[{"description": "Add import"}],
            final_status="fixed",
        )
        result_dict = result.to_dict()

        assert "fix_attempts" in result_dict
        assert result_dict["fix_attempts"] == 2
        assert "fixes_applied" in result_dict
        assert len(result_dict["fixes_applied"]) == 1
        assert "final_status" in result_dict
        assert result_dict["final_status"] == "fixed"


class TestRunResultSummary:
    """Testes do summary do RunResult."""

    def test_summary_shows_fix_attempts(self):
        """Summary deve mostrar fix_attempts."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            fix_attempts=2,
            final_status="fixed",
        )
        summary = result.summary()

        assert "Fix Attempts: 2" in summary
        assert "Final Status: fixed" in summary

    def test_summary_shows_fixes_applied(self):
        """Summary deve mostrar fixes aplicados."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            fixes_applied=[
                {"description": "Add React import"},
                {"description": "Fix type error"},
            ],
        )
        summary = result.summary()

        assert "Fixes Applied: 2" in summary
        assert "Add React import" in summary

    def test_summary_shows_aborted_reason(self):
        """Summary deve mostrar razão de abort."""
        result = RunResult(
            success=False,
            execution_id="test_123",
            project="test",
            fix_loop_aborted_reason="Max attempts reached",
        )
        summary = result.summary()

        assert "Fix Loop Aborted: Max attempts reached" in summary


# ==================== TESTS: ENGINE INTEGRATION ====================


class TestEngineFixLoopIntegration:
    """Testes de integração do Fix Loop no Engine."""

    def test_engine_has_run_fix_loop_method(self, engine):
        """Engine deve ter método _run_fix_loop."""
        assert hasattr(engine, "_run_fix_loop")
        assert callable(engine._run_fix_loop)

    def test_run_with_build_has_enable_fix_loop_param(self, engine):
        """run_with_build deve ter parâmetro enable_fix_loop."""
        import inspect
        sig = inspect.signature(engine.run_with_build)
        assert "enable_fix_loop" in sig.parameters

    @patch.object(Engine, "run")
    @patch.object(Engine, "_load_artifact")
    @patch.object(Engine, "_load_yaml_artifact")
    def test_fix_loop_not_called_when_build_passes(
        self,
        mock_load_yaml,
        mock_load_artifact,
        mock_run,
        engine,
        successful_build_report,
    ):
        """Fix Loop não deve ser chamado quando build passa."""
        # Setup mocks
        mock_run.return_value = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )
        mock_load_artifact.return_value = {"tasks": []}
        mock_load_yaml.return_value = {"paths": {}}

        with patch("orchestrator.engine.RepoGenerator") as mock_repo_gen, \
             patch("orchestrator.engine.PatchGenerator") as mock_patch_gen, \
             patch("orchestrator.engine.PatchEngine") as mock_patch_engine, \
             patch("orchestrator.engine.BuildValidator") as mock_build_validator, \
             patch("orchestrator.engine.FixLoopAgent") as mock_fix_agent:

            # Setup
            mock_repo_gen.return_value.repo_exists.return_value = False
            mock_repo_gen.return_value.create_repo.return_value = Path("/tmp/test")
            mock_patch_gen.return_value.generate.return_value = Mock(patches=[])
            mock_patch_engine.return_value.apply_patches.return_value = Mock(success=True)
            mock_build_validator.return_value.validate.return_value = successful_build_report

            # Execute
            result = engine.run_with_build("test", "input")

            # Verify Fix Loop não foi chamado
            mock_fix_agent.assert_not_called()
            assert result.final_status == "success"
            assert result.fix_attempts == 0

    @patch.object(Engine, "run")
    @patch.object(Engine, "_load_artifact")
    @patch.object(Engine, "_load_yaml_artifact")
    @patch.object(Engine, "_run_fix_loop")
    def test_fix_loop_called_when_build_fails(
        self,
        mock_run_fix_loop,
        mock_load_yaml,
        mock_load_artifact,
        mock_run,
        engine,
        failed_build_report,
        successful_fix_result,
    ):
        """Fix Loop deve ser chamado quando build falha."""
        # Setup mocks
        mock_run.return_value = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )
        mock_load_artifact.return_value = {"tasks": []}
        mock_load_yaml.return_value = {"paths": {}}
        mock_run_fix_loop.return_value = successful_fix_result

        with patch("orchestrator.engine.RepoGenerator") as mock_repo_gen, \
             patch("orchestrator.engine.PatchGenerator") as mock_patch_gen, \
             patch("orchestrator.engine.PatchEngine") as mock_patch_engine, \
             patch("orchestrator.engine.BuildValidator") as mock_build_validator:

            # Setup
            mock_repo_gen.return_value.repo_exists.return_value = False
            mock_repo_gen.return_value.create_repo.return_value = Path("/tmp/test")
            mock_patch_gen.return_value.generate.return_value = Mock(patches=[])
            mock_patch_engine.return_value.apply_patches.return_value = Mock(success=True)
            mock_build_validator.return_value.validate.return_value = failed_build_report

            # Execute
            result = engine.run_with_build("test", "input")

            # Verify Fix Loop foi chamado
            mock_run_fix_loop.assert_called_once()
            assert result.final_status == "fixed"

    @patch.object(Engine, "run")
    @patch.object(Engine, "_load_artifact")
    @patch.object(Engine, "_load_yaml_artifact")
    def test_fix_loop_disabled_skips_fix(
        self,
        mock_load_yaml,
        mock_load_artifact,
        mock_run,
        engine,
        failed_build_report,
    ):
        """enable_fix_loop=False deve pular o Fix Loop."""
        # Setup mocks
        mock_run.return_value = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )
        mock_load_artifact.return_value = {"tasks": []}
        mock_load_yaml.return_value = {"paths": {}}

        with patch("orchestrator.engine.RepoGenerator") as mock_repo_gen, \
             patch("orchestrator.engine.PatchGenerator") as mock_patch_gen, \
             patch("orchestrator.engine.PatchEngine") as mock_patch_engine, \
             patch("orchestrator.engine.BuildValidator") as mock_build_validator, \
             patch("orchestrator.engine.FixLoopAgent") as mock_fix_agent:

            # Setup
            mock_repo_gen.return_value.repo_exists.return_value = False
            mock_repo_gen.return_value.create_repo.return_value = Path("/tmp/test")
            mock_patch_gen.return_value.generate.return_value = Mock(patches=[])
            mock_patch_engine.return_value.apply_patches.return_value = Mock(success=True)
            mock_build_validator.return_value.validate.return_value = failed_build_report

            # Execute com fix loop desabilitado
            result = engine.run_with_build("test", "input", enable_fix_loop=False)

            # Verify Fix Loop não foi chamado
            mock_fix_agent.assert_not_called()
            assert result.final_status == "build_failed"
            assert result.success is False


# ==================== TESTS: FIX LOOP RESULT HANDLING ====================


class TestFixLoopResultHandling:
    """Testes de como o Engine lida com resultados do Fix Loop."""

    @patch.object(Engine, "run")
    @patch.object(Engine, "_load_artifact")
    @patch.object(Engine, "_load_yaml_artifact")
    @patch.object(Engine, "_run_fix_loop")
    def test_successful_fix_sets_final_status_fixed(
        self,
        mock_run_fix_loop,
        mock_load_yaml,
        mock_load_artifact,
        mock_run,
        engine,
        failed_build_report,
        successful_fix_result,
    ):
        """Fix bem sucedido deve setar final_status='fixed'."""
        mock_run.return_value = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )
        mock_load_artifact.return_value = {"tasks": []}
        mock_load_yaml.return_value = {"paths": {}}
        mock_run_fix_loop.return_value = successful_fix_result

        with patch("orchestrator.engine.RepoGenerator") as mock_repo_gen, \
             patch("orchestrator.engine.PatchGenerator") as mock_patch_gen, \
             patch("orchestrator.engine.PatchEngine") as mock_patch_engine, \
             patch("orchestrator.engine.BuildValidator") as mock_build_validator:

            mock_repo_gen.return_value.repo_exists.return_value = False
            mock_repo_gen.return_value.create_repo.return_value = Path("/tmp/test")
            mock_patch_gen.return_value.generate.return_value = Mock(patches=[])
            mock_patch_engine.return_value.apply_patches.return_value = Mock(success=True)
            mock_build_validator.return_value.validate.return_value = failed_build_report

            result = engine.run_with_build("test", "input")

            assert result.final_status == "fixed"
            assert result.build_ok is True

    @patch.object(Engine, "run")
    @patch.object(Engine, "_load_artifact")
    @patch.object(Engine, "_load_yaml_artifact")
    @patch.object(Engine, "_run_fix_loop")
    def test_failed_fix_sets_final_status_fatal_error(
        self,
        mock_run_fix_loop,
        mock_load_yaml,
        mock_load_artifact,
        mock_run,
        engine,
        failed_build_report,
        failed_fix_result,
    ):
        """Fix falho deve setar final_status='fatal_error'."""
        mock_run.return_value = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )
        mock_load_artifact.return_value = {"tasks": []}
        mock_load_yaml.return_value = {"paths": {}}
        mock_run_fix_loop.return_value = failed_fix_result

        with patch("orchestrator.engine.RepoGenerator") as mock_repo_gen, \
             patch("orchestrator.engine.PatchGenerator") as mock_patch_gen, \
             patch("orchestrator.engine.PatchEngine") as mock_patch_engine, \
             patch("orchestrator.engine.BuildValidator") as mock_build_validator:

            mock_repo_gen.return_value.repo_exists.return_value = False
            mock_repo_gen.return_value.create_repo.return_value = Path("/tmp/test")
            mock_patch_gen.return_value.generate.return_value = Mock(patches=[])
            mock_patch_engine.return_value.apply_patches.return_value = Mock(success=True)
            mock_build_validator.return_value.validate.return_value = failed_build_report

            result = engine.run_with_build("test", "input")

            assert result.final_status == "fatal_error"
            assert result.success is False
            assert result.fix_loop_aborted_reason == "Max attempts (3) reached"

    @patch.object(Engine, "run")
    @patch.object(Engine, "_load_artifact")
    @patch.object(Engine, "_load_yaml_artifact")
    @patch.object(Engine, "_run_fix_loop")
    def test_fix_attempts_recorded(
        self,
        mock_run_fix_loop,
        mock_load_yaml,
        mock_load_artifact,
        mock_run,
        engine,
        failed_build_report,
    ):
        """fix_attempts deve ser registrado no result."""
        fix_patch = FixPatch(
            operation="modify",
            file_path="test.ts",
            content="fixed",
            error_type=BuildErrorType.TS_TYPE_ERROR,
            description="Fix type",
        )
        fix_result = FixLoopResult(
            success=True,
            project="test",
            total_attempts=2,
            attempts=[
                FixAttempt(
                    attempt_number=1,
                    status=FixAttemptStatus.BUILD_FAILED,
                ),
                FixAttempt(
                    attempt_number=2,
                    status=FixAttemptStatus.SUCCESS,
                    patch_applied=fix_patch,
                ),
            ],
            final_build_ok=True,
        )

        mock_run.return_value = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )
        mock_load_artifact.return_value = {"tasks": []}
        mock_load_yaml.return_value = {"paths": {}}

        # Use side_effect to also update the result object (mimic real behavior)
        def run_fix_loop_side_effect(project, build_report, step, result):
            result.fix_attempts = fix_result.total_attempts
            for attempt in fix_result.attempts:
                if attempt.patch_applied:
                    result.fixes_applied.append(attempt.patch_applied.to_dict())
            return fix_result

        mock_run_fix_loop.side_effect = run_fix_loop_side_effect

        with patch("orchestrator.engine.RepoGenerator") as mock_repo_gen, \
             patch("orchestrator.engine.PatchGenerator") as mock_patch_gen, \
             patch("orchestrator.engine.PatchEngine") as mock_patch_engine, \
             patch("orchestrator.engine.BuildValidator") as mock_build_validator:

            mock_repo_gen.return_value.repo_exists.return_value = False
            mock_repo_gen.return_value.create_repo.return_value = Path("/tmp/test")
            mock_patch_gen.return_value.generate.return_value = Mock(patches=[])
            mock_patch_engine.return_value.apply_patches.return_value = Mock(success=True)
            mock_build_validator.return_value.validate.return_value = failed_build_report

            result = engine.run_with_build("test", "input")

            assert result.fix_attempts == 2
            assert len(result.fixes_applied) == 1  # Apenas 1 patch foi aplicado


# ==================== TESTS: ROLLBACK ====================


class TestRollbackOnFixLoopFailure:
    """Testes de rollback quando Fix Loop falha."""

    @patch.object(Engine, "run")
    @patch.object(Engine, "_load_artifact")
    @patch.object(Engine, "_load_yaml_artifact")
    @patch.object(Engine, "_run_fix_loop")
    def test_repo_moved_to_failed_on_fix_failure(
        self,
        mock_run_fix_loop,
        mock_load_yaml,
        mock_load_artifact,
        mock_run,
        engine,
        failed_build_report,
        failed_fix_result,
    ):
        """Repo deve ser movido para _failed/ quando Fix Loop falha (preserva para debug)."""
        mock_run.return_value = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )
        mock_load_artifact.return_value = {"tasks": []}
        mock_load_yaml.return_value = {"paths": {}}
        mock_run_fix_loop.return_value = failed_fix_result

        with patch("orchestrator.engine.RepoGenerator") as mock_repo_gen, \
             patch("orchestrator.engine.PatchGenerator") as mock_patch_gen, \
             patch("orchestrator.engine.PatchEngine") as mock_patch_engine, \
             patch("orchestrator.engine.BuildValidator") as mock_build_validator:

            mock_repo_instance = mock_repo_gen.return_value
            mock_repo_instance.repo_exists.return_value = False
            mock_repo_instance.create_repo.return_value = Path("/tmp/test")
            mock_repo_instance.move_to_failed.return_value = Path("/home/bazari/generated/_failed/test_20260104")
            mock_patch_gen.return_value.generate.return_value = Mock(patches=[])
            mock_patch_engine.return_value.apply_patches.return_value = Mock(success=True)
            mock_build_validator.return_value.validate.return_value = failed_build_report

            result = engine.run_with_build("test", "input")

            # Verify move_to_failed foi chamado (em vez de delete_repo)
            mock_repo_instance.move_to_failed.assert_called_once_with("test")
            # Verify delete_repo NÃO foi chamado
            mock_repo_instance.delete_repo.assert_not_called()
            # Verify resultado contém path do repo movido
            assert any("_failed" in err for err in result.errors)


# ==================== TESTS: FINAL STATUS VALUES ====================


class TestFinalStatusValues:
    """Testes dos valores de final_status."""

    def test_success_status_on_first_build_pass(self):
        """Deve ser 'success' quando build passa de primeira."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="test",
            final_status="success",
        )
        assert result.final_status == "success"

    def test_fixed_status_after_fix_loop(self):
        """Deve ser 'fixed' quando Fix Loop corrige."""
        result = RunResult(
            success=True,
            execution_id="test",
            project="test",
            final_status="fixed",
            fix_attempts=2,
        )
        assert result.final_status == "fixed"

    def test_fatal_error_status_on_fix_failure(self):
        """Deve ser 'fatal_error' quando Fix Loop falha."""
        result = RunResult(
            success=False,
            execution_id="test",
            project="test",
            final_status="fatal_error",
            fix_loop_aborted_reason="Max attempts reached",
        )
        assert result.final_status == "fatal_error"

    def test_build_failed_status_when_fix_disabled(self):
        """Deve ser 'build_failed' quando Fix Loop desabilitado."""
        result = RunResult(
            success=False,
            execution_id="test",
            project="test",
            final_status="build_failed",
        )
        assert result.final_status == "build_failed"
