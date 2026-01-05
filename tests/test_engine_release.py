"""Tests para Engine.run_release() - Pipeline texto -> rodando.

Testa o modo release que:
1. Gera repo
2. Aplica patches
3. BuildValidator
4. docker compose up -d
5. Smoke tests

Falha: docker compose down + rollback
Sucesso: sistema permanece rodando

NOTA: Estes testes requerem Docker para funcionar corretamente.
Para rodar apenas testes unitários: pytest -m "not docker"
"""

import pytest

# Marcar todo o módulo como integration/docker
pytestmark = [pytest.mark.integration, pytest.mark.docker]
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from orchestrator.engine import Engine, RunResult
from release.docker_compose_validator import (
    DockerComposeValidator,
    DockerComposeValidationResult,
    DockerComposeUpResult,
)
from release.smoke_runner import SmokeRunner, SmokeReport, SmokeResult
from release import smoke_runner as smoke_runner_module


@pytest.fixture
def tmp_store(tmp_path):
    """Store temporário."""
    store_dir = tmp_path / "store"
    store_dir.mkdir(parents=True, exist_ok=True)
    return str(store_dir)


@pytest.fixture
def tmp_generated(tmp_path):
    """Diretório generated temporário."""
    gen_dir = tmp_path / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    return str(gen_dir)


@pytest.fixture
def engine(tmp_store):
    """Engine com store temporário."""
    return Engine(store_root=tmp_store)


@pytest.fixture
def sample_input():
    """Input de exemplo para testes."""
    return """
    Sistema de Biblioteca

    Funcionalidades:
    - Cadastro de livros
    - Empréstimo de livros
    - Devolução de livros
    """


@pytest.fixture
def mock_run_result():
    """RunResult de sucesso para mock."""
    return RunResult(
        success=True,
        execution_id="test_123",
        project="biblioteca",
        srs_version=1,
        ir_version=1,
        oas_version=1,
        rbac_version=1,
        plan_version=1,
        srs_validation_ok=True,
        ir_validation_ok=True,
        oas_validation_ok=True,
        rbac_validation_ok=True,
        plan_validation_ok=True,
        policy_ok=True,
        contracts_policy_ok=True,
        plan_policy_ok=True,
        repo_path="/tmp/generated/biblioteca",
        patch_count=5,
        build_ok=True,
        final_status="success",
    )


class TestRunReleaseBasic:
    """Testes básicos do run_release."""

    def test_run_release_returns_run_result(self, engine, sample_input):
        """run_release deve retornar RunResult."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=False,
                execution_id="test_123",
                project="biblioteca",
                build_ok=False,
            )

            result = engine.run_release("biblioteca", sample_input)

            assert isinstance(result, RunResult)
            assert result.release_mode is True

    def test_run_release_marks_release_mode(self, engine, sample_input):
        """run_release deve marcar release_mode=True."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=True,
                execution_id="test_123",
                project="biblioteca",
                build_ok=True,
            )
            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                mock_compose.return_value = (False, DockerComposeValidationResult(
                    valid=False,
                    file_exists=False,
                    errors=["docker-compose.yml not found"],
                ))
                with patch.object(engine, "_rollback_release"):
                    result = engine.run_release("biblioteca", sample_input)

        assert result.release_mode is True


class TestRunReleaseBuildFailure:
    """Testes para falha na fase de build."""

    def test_build_failed_returns_immediately(self, engine, sample_input):
        """Se build falhar, retorna sem tentar docker/smoke."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=False,
                execution_id="test_123",
                project="biblioteca",
                build_ok=False,
                build_errors=["Compilation failed"],
            )

            result = engine.run_release("biblioteca", sample_input)

            assert result.success is False
            assert result.build_ok is False
            assert result.final_status == "build_failed"
            assert result.docker_compose_ok is False
            assert result.smoke_ok is False

    def test_build_failed_does_not_run_docker(self, engine, sample_input):
        """Se build falhar, não tenta docker compose."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=False,
                execution_id="test_123",
                project="biblioteca",
                build_ok=False,
            )
            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                result = engine.run_release("biblioteca", sample_input)
                mock_compose.assert_not_called()


class TestRunReleaseDockerCompose:
    """Testes para fase de docker compose."""

    def test_docker_compose_invalid_triggers_rollback(self, engine, sample_input):
        """docker-compose.yml inválido deve fazer rollback."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=True,
                execution_id="test_123",
                project="biblioteca",
                build_ok=True,
                repo_path="/tmp/generated/biblioteca",
            )
            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                mock_compose.return_value = (False, DockerComposeValidationResult(
                    valid=False,
                    file_exists=False,
                    errors=["docker-compose.yml not found"],
                ))
                with patch.object(engine, "_rollback_release") as mock_rollback:
                    result = engine.run_release("biblioteca", sample_input)

                    mock_rollback.assert_called_once_with("biblioteca")

        assert result.success is False
        assert result.docker_compose_ok is False
        assert result.final_status == "docker_compose_invalid"

    def test_docker_compose_up_failed_triggers_rollback(self, engine, sample_input):
        """docker compose up falhar deve fazer rollback."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=True,
                execution_id="test_123",
                project="biblioteca",
                build_ok=True,
                repo_path="/tmp/generated/biblioteca",
            )
            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                mock_compose.return_value = (True, DockerComposeValidationResult(
                    valid=True,
                    file_exists=True,
                    services_found=["postgres", "backend", "frontend"],
                ))
                with patch.object(DockerComposeValidator, "test_docker_compose_up") as mock_up:
                    mock_up.return_value = DockerComposeUpResult(
                        success=False,
                        exit_code=1,
                        stderr="Error: port already in use",
                    )
                    with patch.object(DockerComposeValidator, "stop_services") as mock_stop:
                        with patch.object(engine, "_rollback_release") as mock_rollback:
                            result = engine.run_release("biblioteca", sample_input)

                            mock_stop.assert_called_once_with("biblioteca")
                            mock_rollback.assert_called_once_with("biblioteca")

        assert result.success is False
        assert result.final_status == "docker_up_failed"
        assert "port already in use" in result.errors[0]


class TestRunReleaseSmokeTests:
    """Testes para fase de smoke tests."""

    def test_smoke_failed_triggers_rollback(self, engine, sample_input):
        """Smoke tests falhando devem fazer rollback."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=True,
                execution_id="test_123",
                project="biblioteca",
                build_ok=True,
                repo_path="/tmp/generated/biblioteca",
            )
            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                mock_compose.return_value = (True, DockerComposeValidationResult(
                    valid=True,
                    file_exists=True,
                    services_found=["postgres", "backend", "frontend"],
                ))
                with patch.object(DockerComposeValidator, "test_docker_compose_up") as mock_up:
                    mock_up.return_value = DockerComposeUpResult(
                        success=True,
                        services_started=["postgres", "backend", "frontend"],
                    )
                    with patch.object(SmokeRunner, "run_smoke_tests") as mock_smoke:
                        mock_smoke.return_value = SmokeReport(
                            project="biblioteca",
                            repo_path="/tmp/generated/biblioteca",
                            timestamp="2024-01-01T00:00:00",
                            overall_status="FAIL",
                            results=[
                                SmokeResult(name="backend_healthcheck", category="backend", status="FAIL", message="Connection refused"),
                            ],
                        )
                        with patch.object(DockerComposeValidator, "stop_services") as mock_stop:
                            with patch.object(engine, "_rollback_release") as mock_rollback:
                                result = engine.run_release("biblioteca", sample_input)

                                mock_stop.assert_called_once_with("biblioteca")
                                mock_rollback.assert_called_once_with("biblioteca")

        assert result.success is False
        assert result.smoke_ok is False
        assert result.final_status == "smoke_failed"
        assert result.smoke_passed == 0
        assert result.smoke_failed == 1

    def test_smoke_partial_failure_counts(self, engine, sample_input):
        """Deve contar corretamente smoke tests passados e falhados."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=True,
                execution_id="test_123",
                project="biblioteca",
                build_ok=True,
                repo_path="/tmp/generated/biblioteca",
            )
            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                mock_compose.return_value = (True, DockerComposeValidationResult(
                    valid=True,
                    file_exists=True,
                ))
                with patch.object(DockerComposeValidator, "test_docker_compose_up") as mock_up:
                    mock_up.return_value = DockerComposeUpResult(
                        success=True,
                        services_started=["postgres", "backend", "frontend"],
                    )
                    with patch.object(SmokeRunner, "run_smoke_tests") as mock_smoke:
                        mock_smoke.return_value = SmokeReport(
                            project="biblioteca",
                            repo_path="/tmp/generated/biblioteca",
                            timestamp="2024-01-01T00:00:00",
                            overall_status="FAIL",  # Pelo menos 1 falhou
                            results=[
                                SmokeResult(name="backend_exists", category="backend", status="PASS", message="OK"),
                                SmokeResult(name="frontend_exists", category="frontend", status="PASS", message="OK"),
                                SmokeResult(name="backend_healthcheck", category="backend", status="FAIL", message="Failed"),
                            ],
                        )
                        with patch.object(DockerComposeValidator, "stop_services"):
                            with patch.object(engine, "_rollback_release"):
                                result = engine.run_release("biblioteca", sample_input)

        assert result.smoke_passed == 2
        assert result.smoke_failed == 1


class TestRunReleaseSuccess:
    """Testes para sucesso do run_release."""

    def test_success_keeps_services_running(self, engine, sample_input):
        """Sucesso deve manter serviços rodando (não chama stop_services)."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=True,
                execution_id="test_123",
                project="biblioteca",
                build_ok=True,
                repo_path="/tmp/generated/biblioteca",
            )
            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                mock_compose.return_value = (True, DockerComposeValidationResult(
                    valid=True,
                    file_exists=True,
                    services_found=["postgres", "backend", "frontend"],
                ))
                with patch.object(DockerComposeValidator, "test_docker_compose_up") as mock_up:
                    mock_up.return_value = DockerComposeUpResult(
                        success=True,
                        services_started=["postgres", "backend", "frontend"],
                    )
                    with patch.object(SmokeRunner, "run_smoke_tests") as mock_smoke:
                        mock_smoke.return_value = SmokeReport(
                            project="biblioteca",
                            repo_path="/tmp/generated/biblioteca",
                            timestamp="2024-01-01T00:00:00",
                            overall_status="PASS",
                            results=[
                                SmokeResult(name="backend_healthcheck", category="backend", status="PASS", message="OK"),
                                SmokeResult(name="frontend_exists", category="frontend", status="PASS", message="OK"),
                            ],
                        )
                        with patch.object(DockerComposeValidator, "stop_services") as mock_stop:
                            with patch.object(engine, "_rollback_release") as mock_rollback:
                                result = engine.run_release("biblioteca", sample_input)

                                # NÃO deve ter chamado stop_services ou rollback
                                mock_stop.assert_not_called()
                                mock_rollback.assert_not_called()

        assert result.success is True
        assert result.docker_compose_ok is True
        assert result.smoke_ok is True
        assert result.final_status == "running"
        assert result.services_running == ["postgres", "backend", "frontend"]

    def test_success_all_fields_set(self, engine, sample_input):
        """Sucesso deve preencher todos os campos corretamente."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=True,
                execution_id="test_123",
                project="biblioteca",
                build_ok=True,
                repo_path="/tmp/generated/biblioteca",
                srs_version=1,
                ir_version=1,
                oas_version=1,
                rbac_version=1,
                plan_version=1,
            )
            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                mock_compose.return_value = (True, DockerComposeValidationResult(
                    valid=True,
                    file_exists=True,
                ))
                with patch.object(DockerComposeValidator, "test_docker_compose_up") as mock_up:
                    mock_up.return_value = DockerComposeUpResult(
                        success=True,
                        services_started=["postgres", "backend", "frontend"],
                    )
                    with patch.object(SmokeRunner, "run_smoke_tests") as mock_smoke:
                        mock_smoke.return_value = SmokeReport(
                            project="biblioteca",
                            repo_path="/tmp/generated/biblioteca",
                            timestamp="2024-01-01T00:00:00",
                            overall_status="PASS",
                            results=[
                                SmokeResult(name="test1", category="backend", status="PASS", message="OK"),
                                SmokeResult(name="test2", category="frontend", status="PASS", message="OK"),
                            ],
                        )
                        result = engine.run_release("biblioteca", sample_input)

        assert result.success is True
        assert result.release_mode is True
        assert result.build_ok is True
        assert result.docker_compose_ok is True
        assert result.smoke_ok is True
        assert result.smoke_passed == 2
        assert result.smoke_failed == 0
        assert result.final_status == "running"


class TestRunReleaseErrorHandling:
    """Testes para tratamento de erros."""

    def test_exception_during_release_triggers_rollback(self, engine, sample_input):
        """Exceção durante release deve fazer rollback."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=True,
                execution_id="test_123",
                project="biblioteca",
                build_ok=True,
                repo_path="/tmp/generated/biblioteca",
            )
            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                mock_compose.side_effect = Exception("Unexpected error")
                with patch.object(DockerComposeValidator, "stop_services") as mock_stop:
                    with patch.object(engine, "_rollback_release") as mock_rollback:
                        result = engine.run_release("biblioteca", sample_input)

                        mock_rollback.assert_called_once_with("biblioteca")

        assert result.success is False
        assert result.final_status == "release_error"
        assert "Unexpected error" in result.errors[0]


class TestRollbackRelease:
    """Testes para _rollback_release."""

    def test_rollback_moves_repo_to_failed(self, engine, tmp_generated):
        """Rollback deve mover o repositório para _failed/ (preserva para debug)."""
        engine.GENERATED_ROOT = tmp_generated

        # Criar projeto simulado
        project_dir = Path(tmp_generated) / "test_project"
        project_dir.mkdir(parents=True)
        (project_dir / "README.md").write_text("Test")

        assert project_dir.exists()

        with patch("repo.repo_generator.RepoGenerator.repo_exists", return_value=True):
            with patch("repo.repo_generator.RepoGenerator.move_to_failed") as mock_move:
                mock_move.return_value = Path(tmp_generated) / "_failed" / "DOCKER_UP_FAILED" / "test_project_20260104"
                from repo.repo_generator import ReleaseFailureCategory
                result = engine._rollback_release("test_project", ReleaseFailureCategory.DOCKER_UP_FAILED)

                # Verify move_to_failed foi chamado com categoria
                mock_move.assert_called_once_with("test_project", ReleaseFailureCategory.DOCKER_UP_FAILED)
                # Verify retorna o path do diretório de destino
                assert result is not None
                assert "_failed" in str(result)

    def test_rollback_ignores_errors(self, engine):
        """Rollback deve ignorar erros silenciosamente."""
        with patch("repo.repo_generator.RepoGenerator.repo_exists") as mock_exists:
            mock_exists.side_effect = Exception("Error")

            # Não deve levantar exceção
            result = engine._rollback_release("test_project")
            assert result is None


class TestRunResultReleaseFields:
    """Testes para os novos campos do RunResult."""

    def test_run_result_has_release_fields(self):
        """RunResult deve ter campos de release."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
        )

        assert hasattr(result, "docker_compose_ok")
        assert hasattr(result, "services_running")
        assert hasattr(result, "smoke_ok")
        assert hasattr(result, "smoke_passed")
        assert hasattr(result, "smoke_failed")
        assert hasattr(result, "release_mode")

    def test_run_result_to_dict_includes_release_fields(self):
        """to_dict() deve incluir campos de release."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            docker_compose_ok=True,
            services_running=["postgres", "backend"],
            smoke_ok=True,
            smoke_passed=5,
            smoke_failed=1,
            release_mode=True,
        )

        d = result.to_dict()

        assert d["docker_compose_ok"] is True
        assert d["services_running"] == ["postgres", "backend"]
        assert d["smoke_ok"] is True
        assert d["smoke_passed"] == 5
        assert d["smoke_failed"] == 1
        assert d["release_mode"] is True

    def test_run_result_summary_includes_release_info(self):
        """summary() deve incluir informações de release."""
        result = RunResult(
            success=True,
            execution_id="test_123",
            project="test",
            docker_compose_ok=True,
            services_running=["postgres", "backend", "frontend"],
            smoke_ok=True,
            smoke_passed=5,
            smoke_failed=0,
            release_mode=True,
        )

        summary = result.summary()

        assert "Docker Compose: OK" in summary
        assert "postgres" in summary
        assert "Smoke Tests: OK" in summary


class TestRunReleaseEnableFixLoop:
    """Testes para enable_fix_loop parameter."""

    def test_enable_fix_loop_passed_to_run_with_build(self, engine, sample_input):
        """enable_fix_loop deve ser passado para run_with_build."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=False,
                execution_id="test_123",
                project="biblioteca",
                build_ok=False,
            )

            engine.run_release("biblioteca", sample_input, enable_fix_loop=False)

            mock_build.assert_called_once()
            call_kwargs = mock_build.call_args[1]
            assert call_kwargs["enable_fix_loop"] is False

    def test_enable_fix_loop_default_true(self, engine, sample_input):
        """enable_fix_loop deve ser True por padrão."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=False,
                execution_id="test_123",
                project="biblioteca",
                build_ok=False,
            )

            engine.run_release("biblioteca", sample_input)

            call_kwargs = mock_build.call_args[1]
            assert call_kwargs["enable_fix_loop"] is True


class TestRunReleaseIntegration:
    """Testes de integração simplificados."""

    def test_full_pipeline_mocked(self, engine, sample_input):
        """Teste do pipeline completo com mocks."""
        with patch.object(engine, "run_with_build") as mock_build:
            mock_build.return_value = RunResult(
                success=True,
                execution_id="test_123",
                project="biblioteca",
                build_ok=True,
                repo_path="/tmp/generated/biblioteca",
                srs_version=1,
                ir_version=1,
                oas_version=1,
                rbac_version=1,
                plan_version=1,
                srs_validation_ok=True,
                ir_validation_ok=True,
                oas_validation_ok=True,
                rbac_validation_ok=True,
                plan_validation_ok=True,
            )

            with patch.object(DockerComposeValidator, "ensure_valid") as mock_compose:
                mock_compose.return_value = (True, DockerComposeValidationResult(
                    valid=True,
                    file_exists=True,
                    services_found=["postgres", "backend", "frontend"],
                ))

                with patch.object(DockerComposeValidator, "test_docker_compose_up") as mock_up:
                    mock_up.return_value = DockerComposeUpResult(
                        success=True,
                        services_started=["postgres", "backend", "frontend"],
                    )

                    with patch.object(SmokeRunner, "run_smoke_tests") as mock_smoke:
                        mock_smoke.return_value = SmokeReport(
                            project="biblioteca",
                            repo_path="/tmp/generated/biblioteca",
                            timestamp="2024-01-01T00:00:00",
                            overall_status="PASS",
                            results=[
                                SmokeResult(name="backend_healthcheck", category="backend", status="PASS", message="200 OK"),
                                SmokeResult(name="frontend_build", category="frontend", status="PASS", message="Build OK"),
                            ],
                        )

                        result = engine.run_release(
                            "biblioteca",
                            sample_input,
                            title="Sistema de Biblioteca",
                        )

        # Verificar resultado final
        assert result.success is True
        assert result.release_mode is True
        assert result.build_ok is True
        assert result.docker_compose_ok is True
        assert result.smoke_ok is True
        assert result.final_status == "running"
        assert len(result.services_running) == 3
        assert result.smoke_passed == 2
        assert result.smoke_failed == 0
