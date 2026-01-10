"""Testes para IDL Draft Compile Blocking - GATE 2.

GATE 2: Draft → IDL Compile Gate
Testa que a compilação FALHA corretamente quando existem:
- open_questions não resolvidas
- campos unknown obrigatórios
- actors sem role
- entities sem tipo
- use_cases sem actor
- integrations sem type
"""

import pytest
from idl.idl_draft_v1 import (
    IDLDraftV1,
    DraftSource,
    DraftActor,
    DraftEntity,
    DraftField,
    DraftUseCase,
    DraftFlowStep,
    DraftIntegration,
    DraftNonFunctional,
    UNKNOWN,
)
from idl.idl_compile import (
    DraftToIDLCompiler,
    CompileResult,
    CompileBlockingError,
    DraftNotCompileableError,
    compile_draft_to_idl,
    compile_draft_to_idl_or_raise,
)


class TestCompileBlockingOpenQuestions:
    """Testes de bloqueio por open_questions."""

    def test_single_open_question_blocks(self):
        """Uma open_question bloqueia compilação."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            open_questions=["What about authentication?"],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error == "UNRESOLVED_QUESTION"
        assert "authentication" in result.errors[0].reason

    def test_multiple_open_questions_block(self):
        """Múltiplas open_questions geram múltiplos erros."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            open_questions=[
                "What about authentication?",
                "How to handle errors?",
                "What is the expected load?",
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert len(result.errors) == 3
        for error in result.errors:
            assert error.error == "UNRESOLVED_QUESTION"

    def test_open_questions_location_format(self):
        """Location inclui índice da question."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            open_questions=["Q1", "Q2"],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.errors[0].location == "open_questions[0]"
        assert result.errors[1].location == "open_questions[1]"


class TestCompileBlockingActors:
    """Testes de bloqueio por actors."""

    def test_actor_unknown_role_blocks(self):
        """Actor com role unknown bloqueia."""
        draft = IDLDraftV1(
            project="test",
            actors=[
                DraftActor(id="admin", role="administrator"),
                DraftActor(id="user", role=UNKNOWN),
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error == "UNKNOWN_ACTOR_ROLE"
        assert "user" in result.errors[0].reason
        assert "actors.user.role" == result.errors[0].location

    def test_multiple_actors_unknown_roles(self):
        """Múltiplos actors com role unknown geram múltiplos erros."""
        draft = IDLDraftV1(
            project="test",
            actors=[
                DraftActor(id="admin", role=UNKNOWN),
                DraftActor(id="user", role=UNKNOWN),
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert len(result.errors) == 2

    def test_actor_tbd_role_blocks(self):
        """Actor com role TBD bloqueia."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="TBD")],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert result.errors[0].error == "UNKNOWN_ACTOR_ROLE"


class TestCompileBlockingEntities:
    """Testes de bloqueio por entities."""

    def test_entity_unknown_field_type_blocks(self):
        """Entity com field type unknown bloqueia."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            entities=[
                DraftEntity(
                    id="User",
                    fields=[
                        DraftField(name="id", type="string", required=True),
                        DraftField(name="data", type=UNKNOWN, required=True),
                    ]
                )
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert any(e.error == "UNKNOWN_FIELD_TYPE" for e in result.errors)
        assert any("entities.User.fields.data.type" in e.location for e in result.errors)

    def test_entity_unknown_required_blocks(self):
        """Entity com field required unknown bloqueia."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            entities=[
                DraftEntity(
                    id="User",
                    fields=[
                        DraftField(name="optional", type="string", required=UNKNOWN),
                    ]
                )
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert any(e.error == "UNKNOWN_FIELD_REQUIRED" for e in result.errors)

    def test_multiple_fields_unknown(self):
        """Múltiplos fields unknown geram múltiplos erros."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            entities=[
                DraftEntity(
                    id="User",
                    fields=[
                        DraftField(name="f1", type=UNKNOWN, required=True),
                        DraftField(name="f2", type=UNKNOWN, required=UNKNOWN),
                        DraftField(name="f3", type="string", required=UNKNOWN),
                    ]
                )
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        # f1: type unknown (1 erro)
        # f2: type unknown + required unknown (2 erros)
        # f3: required unknown (1 erro)
        assert len(result.errors) == 4


class TestCompileBlockingUseCases:
    """Testes de bloqueio por use_cases."""

    def test_usecase_unknown_actor_blocks(self):
        """UseCase com actor unknown bloqueia."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            use_cases=[
                DraftUseCase(
                    id="UC001",
                    actor=UNKNOWN,
                    flow=[DraftFlowStep(step=1, action="Test")],
                )
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert result.errors[0].error == "UNKNOWN_USECASE_ACTOR"
        assert "UC001" in result.errors[0].reason
        assert "use_cases.UC001.actor" == result.errors[0].location

    def test_multiple_usecases_unknown_actors(self):
        """Múltiplos use_cases com actors unknown geram múltiplos erros."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            use_cases=[
                DraftUseCase(id="UC001", actor=UNKNOWN),
                DraftUseCase(id="UC002", actor=UNKNOWN),
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert len(result.errors) == 2


class TestCompileBlockingIntegrations:
    """Testes de bloqueio por integrations."""

    def test_integration_unknown_type_blocks(self):
        """Integration com type unknown bloqueia."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            integrations=[
                DraftIntegration(system="ExternalAPI", type=UNKNOWN),
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert result.errors[0].error == "UNKNOWN_INTEGRATION_TYPE"
        assert "ExternalAPI" in result.errors[0].reason
        assert "integrations.ExternalAPI.type" == result.errors[0].location

    def test_multiple_integrations_unknown_types(self):
        """Múltiplas integrations com types unknown geram múltiplos erros."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            integrations=[
                DraftIntegration(system="API1", type=UNKNOWN),
                DraftIntegration(system="API2", type=UNKNOWN),
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert len(result.errors) == 2


class TestCompileBlockingCombined:
    """Testes de bloqueio combinado (múltiplas fontes de erro)."""

    def test_multiple_error_sources(self):
        """Draft com múltiplas fontes de erro reporta todas."""
        draft = IDLDraftV1(
            project="test",
            actors=[
                DraftActor(id="admin", role=UNKNOWN),  # 1 erro
            ],
            entities=[
                DraftEntity(
                    id="User",
                    fields=[
                        DraftField(name="data", type=UNKNOWN, required=True),  # 1 erro
                    ]
                )
            ],
            use_cases=[
                DraftUseCase(id="UC001", actor=UNKNOWN),  # 1 erro
            ],
            integrations=[
                DraftIntegration(system="API", type=UNKNOWN),  # 1 erro
            ],
            open_questions=["Q1"],  # 1 erro
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is False
        assert len(result.errors) == 5

        # Verifica que todos os tipos de erro estão presentes
        error_types = {e.error for e in result.errors}
        assert "UNRESOLVED_QUESTION" in error_types
        assert "UNKNOWN_ACTOR_ROLE" in error_types
        assert "UNKNOWN_FIELD_TYPE" in error_types
        assert "UNKNOWN_USECASE_ACTOR" in error_types
        assert "UNKNOWN_INTEGRATION_TYPE" in error_types


class TestCompileOrRaise:
    """Testes para compile_or_raise."""

    def test_compile_or_raise_success(self):
        """compile_or_raise retorna IDLDocument quando sucesso."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="administrator")],
        )
        compiler = DraftToIDLCompiler()
        idl = compiler.compile_or_raise(draft)

        assert idl is not None
        assert idl.system.id == "test"

    def test_compile_or_raise_throws(self):
        """compile_or_raise lança exceção quando falha."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role=UNKNOWN)],
        )
        compiler = DraftToIDLCompiler()

        with pytest.raises(DraftNotCompileableError) as exc_info:
            compiler.compile_or_raise(draft)

        assert len(exc_info.value.errors) == 1
        assert "UNKNOWN_ACTOR_ROLE" in str(exc_info.value)


class TestDraftNotCompileableError:
    """Testes para DraftNotCompileableError."""

    def test_error_message_format(self):
        """Mensagem de erro é formatada corretamente."""
        errors = [
            CompileBlockingError(
                error="TEST_ERROR",
                reason="Test reason",
                location="test.location",
            )
        ]
        exc = DraftNotCompileableError(errors)

        assert "Draft cannot be compiled" in str(exc)
        assert "TEST_ERROR" in str(exc)
        assert "Test reason" in str(exc)

    def test_error_to_dict(self):
        """Erro serializa corretamente."""
        errors = [
            CompileBlockingError(
                error="ERROR1",
                reason="Reason 1",
                location="loc1",
            ),
            CompileBlockingError(
                error="ERROR2",
                reason="Reason 2",
                location="loc2",
            ),
        ]
        exc = DraftNotCompileableError(errors)
        d = exc.to_dict()

        assert d["error"] == "DRAFT_NOT_COMPILEABLE"
        assert len(d["blocking_errors"]) == 2
        assert d["blocking_errors"][0]["error"] == "ERROR1"
        assert d["blocking_errors"][1]["error"] == "ERROR2"


class TestCompileResultFormat:
    """Testes do formato do CompileResult."""

    def test_result_to_dict_failure(self):
        """Resultado de falha serializa corretamente."""
        errors = [
            CompileBlockingError(
                error="TEST",
                reason="Test",
                location="loc",
            )
        ]
        result = CompileResult(success=False, errors=errors)
        d = result.to_dict()

        assert d["success"] is False
        assert len(d["errors"]) == 1
        assert d["errors"][0]["error"] == "TEST"

    def test_blocking_error_to_dict(self):
        """CompileBlockingError serializa corretamente."""
        error = CompileBlockingError(
            error="UNKNOWN_FIELD_TYPE",
            reason="Field 'data' has unknown type",
            location="entities.User.fields.data.type",
        )
        d = error.to_dict()

        assert d["error"] == "UNKNOWN_FIELD_TYPE"
        assert d["reason"] == "Field 'data' has unknown type"
        assert d["location"] == "entities.User.fields.data.type"


class TestConvenienceFunctions:
    """Testes para funções de conveniência."""

    def test_compile_draft_to_idl_success(self):
        """compile_draft_to_idl retorna sucesso."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
        )
        result = compile_draft_to_idl(draft)

        assert result.success is True
        assert result.idl is not None

    def test_compile_draft_to_idl_failure(self):
        """compile_draft_to_idl retorna falha."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role=UNKNOWN)],
        )
        result = compile_draft_to_idl(draft)

        assert result.success is False
        assert len(result.errors) > 0

    def test_compile_draft_to_idl_or_raise_success(self):
        """compile_draft_to_idl_or_raise retorna IDL."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
        )
        idl = compile_draft_to_idl_or_raise(draft)

        assert idl is not None

    def test_compile_draft_to_idl_or_raise_throws(self):
        """compile_draft_to_idl_or_raise lança exceção."""
        draft = IDLDraftV1(
            project="test",
            open_questions=["Q?"],
        )

        with pytest.raises(DraftNotCompileableError):
            compile_draft_to_idl_or_raise(draft)


class TestNonFunctionalDoesNotBlock:
    """Testes confirmando que NFRs unknown NÃO bloqueiam."""

    def test_nfr_unknown_does_not_block(self):
        """NFRs unknown NÃO bloqueiam compilação."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            non_functional=DraftNonFunctional(
                performance=UNKNOWN,
                security=UNKNOWN,
            ),
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        # Deve passar - NFRs unknown são permitidos
        assert result.success is True

    def test_nfr_tbd_does_not_block(self):
        """NFRs TBD NÃO bloqueiam compilação."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            non_functional=DraftNonFunctional(
                performance="TBD",
                security="TBD",
            ),
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        assert result.success is True


class TestAssumptionsDoNotBlock:
    """Testes confirmando que assumptions NÃO bloqueiam."""

    def test_assumptions_do_not_block(self):
        """Assumptions NÃO bloqueiam compilação (são removidas)."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            assumptions=[
                "User has valid email",
                "System is online",
            ],
        )
        compiler = DraftToIDLCompiler()
        result = compiler.compile(draft)

        # Assumptions não bloqueiam (são removidas na transformação)
        assert result.success is True
