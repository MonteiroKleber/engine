"""Testes de Pipeline Autônomo de Build.

Verifica o fluxo completo:
- erro -> classificação -> patch -> build ok
- limite de tentativas respeitado
- Fix Loop acionado quando necessário

Critério de aceite Dia 7:
- Build quebrado -> corrigido automaticamente (casos simples)
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

import pytest

from orchestrator.engine import Engine, RunResult
from fix_loop.fix_loop_agent import FixLoopAgent, FixLoopResult, FixAttemptStatus, FixAttempt, FixPatch
from fix_loop.error_classifier import BuildErrorClassifier, BuildErrorType, BuildStep, ClassifiedError
from fix_loop.fix_patch_generator import FixPatchGenerator, FocalPatch
from validators.build_validator import BuildValidator, BuildReport, BuildComponent


# ==================== FIXTURES ====================


@pytest.fixture
def temp_environment():
    """Cria ambiente temporário completo para testes."""
    temp_dir = tempfile.mkdtemp()
    store_dir = Path(temp_dir) / "store"
    generated_dir = Path(temp_dir) / "generated"
    templates_dir = Path(temp_dir) / "templates"

    store_dir.mkdir(parents=True)
    generated_dir.mkdir(parents=True)
    templates_dir.mkdir(parents=True)

    # Criar estrutura de templates mínima
    for template in ["spring-boot", "react-vite", "postgres-flyway"]:
        (templates_dir / template).mkdir()
        (templates_dir / template / "placeholder.txt").write_text("placeholder")

    yield store_dir, generated_dir, templates_dir, temp_dir

    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_project(temp_environment):
    """Cria projeto temporário para testes de fix loop."""
    store_dir, generated_dir, templates_dir, temp_dir = temp_environment
    project_dir = generated_dir / "test_project"
    project_dir.mkdir(parents=True)

    # Criar estrutura backend
    backend_src = project_dir / "backend" / "src" / "main" / "java" / "com" / "example"
    backend_src.mkdir(parents=True)

    # Criar estrutura frontend
    frontend_src = project_dir / "frontend" / "src"
    frontend_src.mkdir(parents=True)

    yield project_dir, generated_dir, store_dir


# ==================== TESTS: ERROR -> CLASSIFICATION ====================


class TestErrorToClassification:
    """Testes: Erro -> Classificação correta."""

    def test_java_error_classified(self):
        """Erro Java deve ser classificado corretamente."""
        classifier = BuildErrorClassifier()

        stderr = """
        [ERROR] /src/Main.java:15:10 - cannot find symbol
          symbol: class ResponseEntity
        """

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert result.is_patchable
        assert result.errors[0].error_type == BuildErrorType.JAVA_MISSING_IMPORT

    def test_typescript_error_classified(self):
        """Erro TypeScript deve ser classificado corretamente."""
        classifier = BuildErrorClassifier()

        stderr = """
        src/App.tsx:10:5 - error TS2322: Type 'string' is not assignable to type 'number'.
        """

        result = classifier.classify(stderr, "", 1, "frontend")

        assert result.has_errors
        assert result.is_patchable
        assert result.errors[0].error_type == BuildErrorType.TS_TYPE_ERROR

    def test_fatal_error_not_patchable(self):
        """Erro fatal não deve ser patchable."""
        classifier = BuildErrorClassifier()

        stderr = "FATAL ERROR: Out of memory"

        result = classifier.classify(stderr, "", 1, "backend")

        assert result.has_errors
        assert not result.is_patchable
        assert result.errors[0].error_type == BuildErrorType.FATAL_UNCLASSIFIED


# ==================== TESTS: CLASSIFICATION -> PATCH ====================


class TestClassificationToPatch:
    """Testes: Classificação -> Patch gerado."""

    def test_java_import_generates_patch(self, temp_project):
        """Erro de import Java deve gerar patch."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo Java sem import
        java_file = project_dir / "Service.java"
        java_file.write_text("""package com.example;

public class Service {
    public ResponseEntity<String> getData() {
        return ResponseEntity.ok("data");
    }
}
""")

        generator = FixPatchGenerator("test_project", str(generated_dir))

        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="cannot find symbol class ResponseEntity",
            file_path="Service.java",
            symbol="ResponseEntity",
        )

        patch = generator.generate(error)

        assert patch is not None
        assert "import org.springframework.http.ResponseEntity" in patch.content

    def test_ts_import_generates_patch(self, temp_project):
        """Erro de import TypeScript deve gerar patch."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo TypeScript
        ts_file = project_dir / "Component.tsx"
        ts_file.write_text("""export default function Component() {
    const [state, setState] = useState(0);
    return <div>{state}</div>;
}
""")

        generator = FixPatchGenerator("test_project", str(generated_dir))

        error = ClassifiedError(
            error_type=BuildErrorType.TS_MISSING_IMPORT,
            step=BuildStep.FRONTEND,
            message="Cannot find name 'useState'",
            file_path="Component.tsx",
            symbol="useState",
        )

        patch = generator.generate(error)

        assert patch is not None
        assert "import { useState } from 'react'" in patch.content


# ==================== TESTS: PATCH -> BUILD OK ====================


class TestPatchToBuildOk:
    """Testes: Patch aplicado -> Build OK."""

    def test_fix_loop_succeeds_after_fix(self, temp_project):
        """Fix Loop deve ter sucesso após aplicar patch."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo Java com problema
        java_file = project_dir / "Main.java"
        java_file.write_text("""package com.example;

public class Main {
    public ResponseEntity<String> hello() {
        return ResponseEntity.ok("Hello");
    }
}
""")

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Mock: primeiro build falha, segundo passa
        build_count = [0]

        def mock_validate(*args):
            build_count[0] += 1
            if build_count[0] == 1:
                return BuildReport(
                    ok=False,
                    project="test_project",
                    errors=["cannot find symbol class ResponseEntity"]
                )
            return BuildReport(ok=True, project="test_project")

        with patch.object(agent.build_validator, 'validate', side_effect=mock_validate):
            with patch.object(agent.patch_engine, 'apply_patches') as mock_apply:
                mock_apply.return_value = MagicMock(success=True, errors=[])

                stderr = "cannot find symbol class ResponseEntity"
                result = agent.run(stderr, "", 1, "backend")

                # Deve ter tentado corrigir
                assert result.total_attempts >= 1

    def test_successful_fix_has_patch_applied(self, temp_project):
        """Fix bem-sucedido deve registrar patch aplicado."""
        project_dir, generated_dir, _ = temp_project

        # Criar arquivo
        (project_dir / "App.tsx").write_text("export default function App() {}")

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Mock para sucesso após 1 tentativa
        with patch.object(agent, '_execute_attempt') as mock_attempt:
            mock_attempt.return_value = FixAttempt(
                attempt_number=1,
                status=FixAttemptStatus.SUCCESS,
                patch_applied=FixPatch(
                    operation="modify",
                    file_path="App.tsx",
                    content="import React...",
                    error_type=BuildErrorType.TS_MISSING_IMPORT,
                    description="Add React import",
                ),
                build_report=BuildReport(ok=True, project="test_project"),
            )

            result = agent.run("Cannot find 'React'", "", 1, "frontend")

            assert result.success
            assert len(result.attempts) == 1
            assert result.attempts[0].patch_applied is not None


# ==================== TESTS: LIMITE DE TENTATIVAS ====================


class TestMaxAttempts:
    """Testes: Limite de tentativas respeitado."""

    def test_max_attempts_is_3(self):
        """MAX_FIX_ATTEMPTS deve ser 3."""
        assert FixLoopAgent.MAX_FIX_ATTEMPTS == 3

    def test_stops_at_max_attempts(self, temp_project):
        """Deve parar após MAX_FIX_ATTEMPTS tentativas."""
        project_dir, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Mock para sempre falhar
        with patch.object(agent, '_execute_attempt') as mock_attempt:
            mock_attempt.return_value = FixAttempt(
                attempt_number=1,
                status=FixAttemptStatus.BUILD_FAILED,
                build_report=BuildReport(
                    ok=False,
                    project="test_project",
                    errors=["persistent error"]
                ),
            )

            result = agent.run("some error", "", 1, "frontend")

            assert not result.success
            assert result.total_attempts == 3
            assert "Max attempts" in result.aborted_reason

    def test_stops_early_on_success(self, temp_project):
        """Deve parar antes de MAX se conseguir corrigir."""
        project_dir, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # Mock: sucesso na 2ª tentativa
        call_count = [0]

        def mock_attempt(*args):
            call_count[0] += 1
            if call_count[0] == 2:
                return FixAttempt(
                    attempt_number=call_count[0],
                    status=FixAttemptStatus.SUCCESS,
                    build_report=BuildReport(ok=True, project="test_project"),
                )
            return FixAttempt(
                attempt_number=call_count[0],
                status=FixAttemptStatus.BUILD_FAILED,
                build_report=BuildReport(
                    ok=False,
                    project="test_project",
                    errors=["error"]
                ),
            )

        with patch.object(agent, '_execute_attempt', side_effect=mock_attempt):
            result = agent.run("error", "", 1, "frontend")

            assert result.success
            assert result.total_attempts == 2  # Parou antes de 3


# ==================== TESTS: FIX LOOP ACIONADO QUANDO NECESSÁRIO ====================


class TestFixLoopTriggered:
    """Testes: Fix Loop acionado quando build falha."""

    def test_engine_calls_fix_loop_on_build_failure(self, temp_environment):
        """Engine deve chamar Fix Loop quando build falha."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        # Mock do run para sucesso nos artefatos
        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        # Mock do _run_fix_loop
        fix_result = FixLoopResult(
            success=True,
            project="test",
            total_attempts=1,
            final_build_ok=True,
        )

        def mock_run_fix_loop(project, build_report, step, result):
            result.fix_attempts = 1
            return fix_result

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch.object(engine, '_run_fix_loop', side_effect=mock_run_fix_loop) as mock_fix:
                        with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                            with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                                with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                    with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                        mock_repo.return_value.repo_exists.return_value = False
                                        mock_repo.return_value.create_repo.return_value = Path("/tmp/test")

                                        mock_pg.return_value.generate.return_value = Mock(patches=[])
                                        mock_pe.return_value.apply_patches.return_value = Mock(success=True)

                                        # Build falha na primeira vez
                                        mock_bv.return_value.validate.return_value = BuildReport(
                                            ok=False,
                                            project="test",
                                            errors=["Type error"]
                                        )

                                        result = engine.run_with_build("test", "input")

                                        # Fix Loop deve ter sido chamado
                                        mock_fix.assert_called_once()

    def test_fix_loop_not_called_when_build_passes(self, temp_environment):
        """Engine NÃO deve chamar Fix Loop quando build passa."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch.object(engine, '_run_fix_loop') as mock_fix:
                        with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                            with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                                with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                    with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                        mock_repo.return_value.repo_exists.return_value = False
                                        mock_repo.return_value.create_repo.return_value = Path("/tmp/test")

                                        mock_pg.return_value.generate.return_value = Mock(patches=[])
                                        mock_pe.return_value.apply_patches.return_value = Mock(success=True)

                                        # Build passa
                                        mock_bv.return_value.validate.return_value = BuildReport(
                                            ok=True,
                                            project="test"
                                        )

                                        result = engine.run_with_build("test", "input")

                                        # Fix Loop NÃO deve ter sido chamado
                                        mock_fix.assert_not_called()
                                        assert result.final_status == "success"


# ==================== TESTS: FLUXO COMPLETO ====================


class TestCompleteFlow:
    """Testes do fluxo completo: erro -> classificação -> patch -> build ok."""

    def test_complete_flow_java_import(self, temp_project):
        """Fluxo completo para import Java faltando."""
        project_dir, generated_dir, _ = temp_project

        # 1. Criar arquivo com erro
        java_file = project_dir / "UserService.java"
        java_file.write_text("""package com.example;

public class UserService {
    public ResponseEntity<User> getUser(Long id) {
        return ResponseEntity.ok(new User());
    }
}
""")

        # 2. Classificar erro
        classifier = BuildErrorClassifier()
        stderr = """
        [ERROR] /UserService.java:4:12 - cannot find symbol
          symbol: class ResponseEntity
        """
        classification = classifier.classify(stderr, "", 1, "backend")

        assert classification.is_patchable
        assert classification.errors[0].error_type == BuildErrorType.JAVA_MISSING_IMPORT

        # 3. Gerar patch
        generator = FixPatchGenerator("test_project", str(generated_dir))
        error = classification.errors[0]
        error.file_path = "UserService.java"
        error.symbol = "ResponseEntity"

        patch = generator.generate(error)

        assert patch is not None
        assert "import org.springframework.http.ResponseEntity" in patch.content

        # 4. Verificar que patch é válido
        assert patch.lines_changed <= generator.MAX_LINES_CHANGED

    def test_complete_flow_ts_import(self, temp_project):
        """Fluxo completo para import TypeScript faltando."""
        project_dir, generated_dir, _ = temp_project

        # 1. Criar arquivo com erro
        ts_file = project_dir / "UserList.tsx"
        ts_file.write_text("""export default function UserList() {
    const [users, setUsers] = useState([]);

    useEffect(() => {
        fetchUsers();
    }, []);

    return <div>{users.map(u => <span>{u.name}</span>)}</div>;
}
""")

        # 2. Classificar erro
        classifier = BuildErrorClassifier()
        stderr = """
        src/UserList.tsx:2:30 - error TS2304: Cannot find name 'useState'.
        """
        classification = classifier.classify(stderr, "", 1, "frontend")

        assert classification.is_patchable

        # 3. Gerar patch
        generator = FixPatchGenerator("test_project", str(generated_dir))
        error = ClassifiedError(
            error_type=BuildErrorType.TS_MISSING_IMPORT,
            step=BuildStep.FRONTEND,
            message="Cannot find name 'useState'",
            file_path="UserList.tsx",
            symbol="useState",
        )

        patch = generator.generate(error)

        assert patch is not None
        assert "import { useState } from 'react'" in patch.content


# ==================== TESTS: INTEGRAÇÃO ENGINE + FIX LOOP ====================


class TestEngineFixLoopIntegration:
    """Testes de integração Engine + Fix Loop."""

    def test_result_includes_fix_info(self, temp_environment):
        """RunResult deve incluir informações do Fix Loop."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
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
                    patch_applied=FixPatch(
                        operation="modify",
                        file_path="test.ts",
                        content="fixed",
                        error_type=BuildErrorType.TS_TYPE_ERROR,
                        description="Fix type error",
                    ),
                ),
            ],
            final_build_ok=True,
        )

        def mock_run_fix_loop(project, build_report, step, result):
            result.fix_attempts = fix_result.total_attempts
            for attempt in fix_result.attempts:
                if attempt.patch_applied:
                    result.fixes_applied.append(attempt.patch_applied.to_dict())
            return fix_result

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch.object(engine, '_run_fix_loop', side_effect=mock_run_fix_loop):
                        with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                            with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                                with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                    with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                        mock_repo.return_value.repo_exists.return_value = False
                                        mock_repo.return_value.create_repo.return_value = Path("/tmp/test")

                                        mock_pg.return_value.generate.return_value = Mock(patches=[])
                                        mock_pe.return_value.apply_patches.return_value = Mock(success=True)

                                        mock_bv.return_value.validate.return_value = BuildReport(
                                            ok=False,
                                            project="test",
                                            errors=["error"]
                                        )

                                        result = engine.run_with_build("test", "input")

                                        # Deve ter info de fix
                                        assert result.fix_attempts == 2
                                        assert len(result.fixes_applied) == 1
                                        assert result.final_status == "fixed"

    def test_rollback_on_fix_failure(self, temp_environment):
        """Deve mover repo para _failed/ se Fix Loop falhar (preserva para debug)."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="rollback_test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        fix_result = FixLoopResult(
            success=False,
            project="rollback_test",
            total_attempts=3,
            final_build_ok=False,
            aborted_reason="Max attempts reached",
        )

        def mock_run_fix_loop(project, build_report, step, result):
            result.fix_attempts = 3
            result.fix_loop_aborted_reason = "Max attempts reached"
            return fix_result

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch.object(engine, '_run_fix_loop', side_effect=mock_run_fix_loop):
                        with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                            with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                                with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                    with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                        mock_repo.return_value.repo_exists.return_value = False
                                        mock_repo.return_value.create_repo.return_value = generated_dir / "rollback_test"
                                        mock_repo.return_value.move_to_failed.return_value = generated_dir / "_failed" / "rollback_test_20260104"

                                        mock_pg.return_value.generate.return_value = Mock(patches=[])
                                        mock_pe.return_value.apply_patches.return_value = Mock(success=True)

                                        mock_bv.return_value.validate.return_value = BuildReport(
                                            ok=False,
                                            project="rollback_test",
                                            errors=["persistent error"]
                                        )

                                        result = engine.run_with_build("rollback_test", "input")

                                        # Deve ter chamado move_to_failed (em vez de delete_repo)
                                        mock_repo.return_value.move_to_failed.assert_called_with("rollback_test")
                                        mock_repo.return_value.delete_repo.assert_not_called()
                                        assert result.final_status == "fatal_error"
                                        # Resultado deve conter path do repo movido
                                        assert any("_failed" in err for err in result.errors)


# ==================== TESTS: DISABLE FIX LOOP ====================


class TestDisableFixLoop:
    """Testes de desabilitação do Fix Loop."""

    def test_enable_fix_loop_false_skips_fix(self, temp_environment):
        """enable_fix_loop=False deve pular Fix Loop."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="skip_fix",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            with patch.object(engine, '_load_artifact', return_value={"tasks": []}):
                with patch.object(engine, '_load_yaml_artifact', return_value={"paths": {}}):
                    with patch.object(engine, '_run_fix_loop') as mock_fix:
                        with patch('orchestrator.engine.RepoGenerator') as mock_repo:
                            with patch('orchestrator.engine.PatchGenerator') as mock_pg:
                                with patch('orchestrator.engine.PatchEngine') as mock_pe:
                                    with patch('orchestrator.engine.BuildValidator') as mock_bv:
                                        mock_repo.return_value.repo_exists.return_value = False
                                        mock_repo.return_value.create_repo.return_value = generated_dir / "skip_fix"

                                        mock_pg.return_value.generate.return_value = Mock(patches=[])
                                        mock_pe.return_value.apply_patches.return_value = Mock(success=True)

                                        # Build falha
                                        mock_bv.return_value.validate.return_value = BuildReport(
                                            ok=False,
                                            project="skip_fix",
                                            errors=["error"]
                                        )

                                        # Chamar com enable_fix_loop=False
                                        result = engine.run_with_build(
                                            "skip_fix",
                                            "input",
                                            enable_fix_loop=False
                                        )

                                        # Fix Loop NÃO deve ter sido chamado
                                        mock_fix.assert_not_called()
                                        assert result.final_status == "build_failed"


# ==================== TESTS: SECURITY ====================


class TestSecurityInPipeline:
    """Testes de segurança no pipeline."""

    def test_patches_respect_project_boundaries(self, temp_project):
        """Patches devem respeitar limites do projeto."""
        project_dir, generated_dir, _ = temp_project

        generator = FixPatchGenerator("test_project", str(generated_dir))

        # Tentar gerar patch para arquivo fora do projeto
        error = ClassifiedError(
            error_type=BuildErrorType.JAVA_MISSING_IMPORT,
            step=BuildStep.BACKEND,
            message="error",
            file_path="../other_project/Main.java",  # Fora do projeto
            symbol="List",
        )

        patch = generator.generate(error)

        # Não deve gerar patch para arquivo fora do projeto
        assert patch is None

    def test_fix_loop_uses_patch_engine_rules(self, temp_project):
        """Fix Loop deve usar regras de segurança do PatchEngine."""
        project_dir, generated_dir, _ = temp_project

        agent = FixLoopAgent("test_project", str(generated_dir))

        # PatchEngine deve estar configurado corretamente
        assert agent.patch_engine is not None
        assert agent.patch_engine.project == "test_project"


# ==================== TESTS: FINAL STATUS VALUES ====================


class TestFinalStatusValues:
    """Testes dos valores de final_status."""

    def test_success_status(self, temp_environment):
        """Build passa na primeira -> success."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
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
                                    mock_repo.return_value.create_repo.return_value = Path("/tmp/test")

                                    mock_pg.return_value.generate.return_value = Mock(patches=[])
                                    mock_pe.return_value.apply_patches.return_value = Mock(success=True)

                                    mock_bv.return_value.validate.return_value = BuildReport(
                                        ok=True,
                                        project="test"
                                    )

                                    result = engine.run_with_build("test", "input")

                                    assert result.final_status == "success"
                                    assert result.success
                                    assert result.build_ok

    def test_artifacts_only_status(self, temp_environment):
        """skip_build=True -> artifacts_only."""
        store_dir, generated_dir, templates_dir, _ = temp_environment

        engine = Engine(str(store_dir))
        engine.GENERATED_ROOT = str(generated_dir)
        engine.TEMPLATES_ROOT = str(templates_dir)

        mock_result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            plan_version=1,
            ir_version=1,
            oas_version=1,
            rbac_version=1,
        )

        with patch.object(engine, 'run', return_value=mock_result):
            result = engine.run_with_build("test", "input", skip_build=True)

            assert result.final_status == "artifacts_only"
