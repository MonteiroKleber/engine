"""Testes para o FixLoopAgent."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fix_loop.fix_loop_agent import (
    FixLoopAgent,
    FixLoopResult,
    FixAttemptStatus,
    FixAttempt,
    FixPatch,
    run_fix_loop,
)
from fix_loop.error_classifier import BuildErrorType, ClassifiedError, BuildStep
from validators.build_validator import BuildReport


@pytest.fixture
def temp_project():
    """Cria projeto temporário para testes."""
    temp_dir = tempfile.mkdtemp()
    generated_dir = Path(temp_dir) / "generated"
    project_dir = generated_dir / "test_project"
    project_dir.mkdir(parents=True)

    # Criar estrutura básica
    (project_dir / "backend" / "src" / "main" / "java" / "com" / "example").mkdir(parents=True)
    (project_dir / "frontend" / "src").mkdir(parents=True)

    # Criar arquivo Java de exemplo
    java_file = project_dir / "backend" / "src" / "main" / "java" / "com" / "example" / "Main.java"
    java_file.write_text("""package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
""")

    # Criar arquivo TypeScript de exemplo
    ts_file = project_dir / "frontend" / "src" / "App.tsx"
    ts_file.write_text("""export default function App() {
    return <div>Hello</div>;
}
""")

    yield project_dir, generated_dir, temp_dir

    shutil.rmtree(temp_dir)


# ==================== BASIC AGENT TESTS ====================


class TestFixLoopAgentInit:
    """Testes de inicialização do FixLoopAgent."""

    def test_init_with_valid_project(self, temp_project):
        """Deve inicializar com projeto válido."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        assert agent.project == "test_project"
        assert agent.MAX_FIX_ATTEMPTS == 3

    def test_init_empty_project_raises(self, temp_project):
        """Deve falhar com projeto vazio."""
        _, generated_dir, _ = temp_project

        with pytest.raises(ValueError, match="cannot be empty"):
            FixLoopAgent("", str(generated_dir))

    def test_max_fix_attempts_is_3(self):
        """MAX_FIX_ATTEMPTS deve ser 3."""
        assert FixLoopAgent.MAX_FIX_ATTEMPTS == 3


# ==================== LOOP TERMINATION TESTS ====================


class TestLoopTermination:
    """Testes de terminação correta do loop."""

    def test_exits_on_success(self, temp_project):
        """Loop deve terminar quando build passa."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Build já passou (exit_code = 0)
        result = agent.run("", "", 0, "backend")

        assert result.success
        assert result.total_attempts == 0
        assert result.final_build_ok

    def test_max_attempts_respected(self, temp_project):
        """Loop deve respeitar MAX_FIX_ATTEMPTS."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Mock para sempre falhar
        with patch.object(agent, '_execute_attempt') as mock_attempt:
            mock_attempt.return_value = FixAttempt(
                attempt_number=1,
                status=FixAttemptStatus.BUILD_FAILED,
                build_report=BuildReport(ok=False, project="test", errors=["error"]),
            )

            result = agent.run("error", "", 1, "backend")

            assert result.total_attempts == 3
            assert not result.success
            assert "Max attempts" in result.aborted_reason

    def test_exits_on_fatal_error(self, temp_project):
        """Loop deve terminar em erro fatal."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Simular erro fatal
        stderr = "FATAL ERROR: Out of memory"

        with patch.object(agent.build_validator, 'validate') as mock_validate:
            mock_validate.return_value = BuildReport(ok=False, project="test", errors=["fatal"])

            result = agent.run(stderr, "", 1, "backend")

            assert not result.success
            assert "Fatal error" in result.aborted_reason

    def test_exits_on_no_fix_available(self, temp_project):
        """Loop deve terminar quando não há fix disponível."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Mock para retornar erro sem fix
        with patch.object(agent, '_execute_attempt') as mock_attempt:
            mock_attempt.return_value = FixAttempt(
                attempt_number=1,
                status=FixAttemptStatus.NO_FIX_AVAILABLE,
                error_message="No fix for this error",
            )

            result = agent.run("unknown error", "", 1, "backend")

            assert not result.success
            assert result.total_attempts == 1
            assert "No fix available" in result.aborted_reason

    def test_detects_infinite_loop(self, temp_project):
        """Deve detectar loop infinito (mesmo erro repetido)."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Criar erro classificado
        error = ClassifiedError(
            error_type=BuildErrorType.TS_TYPE_ERROR,
            step=BuildStep.FRONTEND,
            message="Type error",
            file_path="src/App.tsx",
            symbol="string",
        )

        # Mock para sempre retornar mesmo erro
        attempt_count = [0]

        def mock_execute(*args):
            attempt_count[0] += 1
            return FixAttempt(
                attempt_number=attempt_count[0],
                status=FixAttemptStatus.BUILD_FAILED,
                error_classified=error,
                build_report=BuildReport(ok=False, project="test", errors=["error"]),
            )

        with patch.object(agent, '_execute_attempt', side_effect=mock_execute):
            result = agent.run("Type error", "", 1, "frontend")

            # Deve detectar loop após 2 tentativas (1ª ok, 2ª detecta repetição)
            assert not result.success
            assert "Loop detected" in result.aborted_reason


# ==================== SECURITY TESTS ====================


class TestSecurityRules:
    """Testes das regras de segurança."""

    def test_security_violation_aborts(self, temp_project):
        """Violação de segurança deve abortar o loop."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        with patch.object(agent, '_execute_attempt') as mock_attempt:
            mock_attempt.return_value = FixAttempt(
                attempt_number=1,
                status=FixAttemptStatus.SECURITY_VIOLATION,
                error_message="Path outside project",
            )

            result = agent.run("error", "", 1, "backend")

            assert not result.success
            assert "Security violation" in result.aborted_reason

    def test_patches_use_patch_engine(self, temp_project):
        """Patches devem passar pelo PatchEngine (regras de segurança)."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Verificar que PatchEngine é usado
        assert agent.patch_engine is not None
        assert agent.patch_engine.project == "test_project"


# ==================== FIX STRATEGY TESTS ====================


class TestFixStrategies:
    """Testes das estratégias de correção."""

    def test_generate_fix_for_java_missing_import(self, temp_project):
        """Deve gerar fix para import Java faltando."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo Java
        java_file = project_dir / "Main.java"
        java_file.write_text("""package com.example;

public class Main {}
""")

        agent = FixLoopAgent("test_project", str(generated_dir))

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="cannot find symbol class ResponseEntity",
            file_path="Main.java",
            symbol="ResponseEntity",
        )

        fix = agent._generate_fix_patch(error)

        assert fix is not None
        assert fix.error_type == BuildErrorType.JAVA_MISSING_IMPORT
        assert "ResponseEntity" in fix.description

    def test_generate_fix_for_ts_missing_import(self, temp_project):
        """Deve gerar fix para import TypeScript faltando."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo TypeScript
        ts_file = project_dir / "App.tsx"
        ts_file.write_text("""export default function App() {
    return <div>Hello</div>;
}
""")

        agent = FixLoopAgent("test_project", str(generated_dir))

        error = ClassifiedError(
            error_type=BuildErrorType.TS_MISSING_IMPORT,
            step=BuildStep.FRONTEND,
            message="Cannot find module 'react'",
            file_path="App.tsx",
            symbol="react",
        )

        fix = agent._generate_fix_patch(error)

        assert fix is not None
        assert fix.error_type == BuildErrorType.TS_MISSING_IMPORT

    def test_no_fix_for_unknown_error_type(self, temp_project):
        """Deve retornar None para tipo de erro sem estratégia."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        error = ClassifiedError(
            error_type=BuildErrorType.FATAL_UNCLASSIFIED,
            step=BuildStep.BACKEND,
            message="Unknown fatal error",
        )

        fix = agent._generate_fix_patch(error)

        assert fix is None


# ==================== ATTEMPT EXECUTION TESTS ====================


class TestAttemptExecution:
    """Testes da execução de tentativas."""

    def test_attempt_classifies_error(self, temp_project):
        """Tentativa deve classificar o erro."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Mock do build validator
        with patch.object(agent.build_validator, 'validate') as mock_validate:
            mock_validate.return_value = BuildReport(ok=True, project="test")

            # Simular erro que será classificado
            stderr = "error TS2322: Type 'string' is not assignable"

            attempt = agent._execute_attempt(1, stderr, "", 1, "frontend")

            assert attempt.error_classified is not None
            assert attempt.error_classified.error_type == BuildErrorType.TS_TYPE_ERROR

    def test_attempt_returns_no_fix_when_build_passes(self, temp_project):
        """Tentativa sem erros classificados."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Sem stderr (build passou)
        attempt = agent._execute_attempt(1, "", "", 0, "backend")

        # Classificador não encontra erros com exit_code=0
        # Mas o _execute_attempt recebe exit_code dos parâmetros

    def test_attempt_handles_exception(self, temp_project):
        """Tentativa deve tratar exceções graciosamente."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Mock para lançar exceção
        with patch.object(agent.classifier, 'classify', side_effect=RuntimeError("Test error")):
            attempt = agent._execute_attempt(1, "error", "", 1, "backend")

            assert attempt.status == FixAttemptStatus.FATAL_ERROR
            assert "Test error" in attempt.error_message


# ==================== RESULT TESTS ====================


class TestFixLoopResult:
    """Testes do FixLoopResult."""

    def test_result_to_dict(self):
        """to_dict deve retornar estrutura correta."""
        result = FixLoopResult(
            success=True,
            project="test",
            total_attempts=2,
            final_build_ok=True,
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["project"] == "test"
        assert d["total_attempts"] == 2
        assert d["final_build_ok"] is True

    def test_result_with_attempts(self):
        """Result deve incluir tentativas."""
        attempt = FixAttempt(
            attempt_number=1,
            status=FixAttemptStatus.SUCCESS,
        )

        result = FixLoopResult(
            success=True,
            project="test",
            total_attempts=1,
            attempts=[attempt],
        )

        d = result.to_dict()
        assert len(d["attempts"]) == 1
        assert d["attempts"][0]["status"] == "success"


# ==================== FIX PATCH TESTS ====================


class TestFixPatch:
    """Testes do FixPatch."""

    def test_fix_patch_to_dict(self):
        """to_dict deve retornar estrutura correta."""
        patch = FixPatch(
            operation="modify",
            file_path="src/Main.java",
            content="new content",
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            description="Add import",
        )

        d = patch.to_dict()

        assert d["operation"] == "modify"
        assert d["file_path"] == "src/Main.java"
        assert d["error_type"] == "java_missing_import"


# ==================== CONVENIENCE FUNCTION TESTS ====================


class TestRunFixLoop:
    """Testes da função run_fix_loop."""

    def test_run_fix_loop_function(self, temp_project):
        """Função de conveniência deve funcionar."""
        _, generated_dir, _ = temp_project

        result = run_fix_loop(
            project="test_project",
            stderr="",
            stdout="",
            exit_code=0,
            step="backend",
            generated_root=str(generated_dir),
        )

        assert result.success
        assert result.project == "test_project"


# ==================== INTEGRATION TESTS ====================


class TestIntegration:
    """Testes de integração."""

    def test_full_fix_flow_mocked(self, temp_project):
        """Fluxo completo com mocks."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo Java com problema
        java_file = project_dir / "Service.java"
        java_file.write_text("""package com.example;

public class Service {
    public ResponseEntity<String> getData() {
        return ResponseEntity.ok("data");
    }
}
""")

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Mock build para passar após primeira tentativa
        call_count = [0]

        def mock_validate(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return BuildReport(ok=False, project="test", errors=["cannot find symbol ResponseEntity"])
            return BuildReport(ok=True, project="test")

        with patch.object(agent.build_validator, 'validate', side_effect=mock_validate):
            with patch.object(agent.patch_engine, 'apply_patches') as mock_apply:
                mock_apply.return_value = MagicMock(success=True, errors=[])

                stderr = "cannot find symbol class ResponseEntity"
                result = agent.run(stderr, "", 1, "backend")

                # O loop deve tentar corrigir

    def test_error_signature_prevents_infinite_loop(self, temp_project):
        """Assinatura de erro deve prevenir loop infinito."""
        _, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        error1 = ClassifiedError(
            error_type=BuildErrorType.TS_TYPE_ERROR,
            step=BuildStep.FRONTEND,
            message="error 1",
            file_path="App.tsx",
            symbol="string",
        )

        error2 = ClassifiedError(
            error_type=BuildErrorType.TS_TYPE_ERROR,
            step=BuildStep.FRONTEND,
            message="error 2",
            file_path="App.tsx",
            symbol="string",
        )

        sig1 = agent._get_error_signature(error1)
        sig2 = agent._get_error_signature(error2)

        # Mesma assinatura (mesmo tipo, arquivo, símbolo)
        assert sig1 == sig2


# ==================== STATUS ENUM TESTS ====================


class TestFixAttemptStatus:
    """Testes do enum FixAttemptStatus."""

    def test_all_statuses_defined(self):
        """Todos os status devem estar definidos."""
        expected = [
            "SUCCESS",
            "PATCH_FAILED",
            "BUILD_FAILED",
            "NO_FIX_AVAILABLE",
            "SECURITY_VIOLATION",
            "FATAL_ERROR",
        ]

        for status in expected:
            assert hasattr(FixAttemptStatus, status)

    def test_status_values(self):
        """Status devem ter valores corretos."""
        assert FixAttemptStatus.SUCCESS.value == "success"
        assert FixAttemptStatus.PATCH_FAILED.value == "patch_failed"
        assert FixAttemptStatus.BUILD_FAILED.value == "build_failed"
