"""Testes para IDL Draft V1 Dataclass Validation.

Testa as funcionalidades de validação das dataclasses do Draft:
- is_unknown() helper
- has_unresolved() methods
- get_all_unresolved() methods
- is_compileable() check
- Serialização to_dict() e from_dict()
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
    is_unknown,
    UNKNOWN,
    TBD,
    IDL_DRAFT_SCHEMA_VERSION,
)


class TestIsUnknownHelper:
    """Testes para helper is_unknown()."""

    def test_unknown_string(self):
        """String 'unknown' é unknown."""
        assert is_unknown("unknown") is True

    def test_tbd_string(self):
        """String 'TBD' é unknown."""
        assert is_unknown("TBD") is True
        assert is_unknown("tbd") is True

    def test_unknown_uppercase(self):
        """String 'UNKNOWN' é unknown."""
        assert is_unknown("UNKNOWN") is True

    def test_unknown_mixed_case(self):
        """String 'Unknown' é unknown."""
        assert is_unknown("Unknown") is True

    def test_none_is_unknown(self):
        """None é unknown."""
        assert is_unknown(None) is True

    def test_empty_string_is_unknown(self):
        """String vazia é unknown."""
        assert is_unknown("") is True

    def test_whitespace_string_is_unknown(self):
        """String só com espaços é unknown."""
        assert is_unknown("   ") is True

    def test_valid_string_not_unknown(self):
        """String válida não é unknown."""
        assert is_unknown("admin") is False
        assert is_unknown("string") is False
        assert is_unknown("User") is False

    def test_boolean_not_unknown(self):
        """Boolean não é unknown."""
        assert is_unknown(True) is False
        assert is_unknown(False) is False


class TestDraftActor:
    """Testes para DraftActor."""

    def test_actor_has_unresolved_unknown_role(self):
        """Actor com role unknown tem unresolved."""
        actor = DraftActor(id="admin", role=UNKNOWN)
        assert actor.has_unresolved() is True

    def test_actor_has_unresolved_valid_role(self):
        """Actor com role válido não tem unresolved."""
        actor = DraftActor(id="admin", role="administrator")
        assert actor.has_unresolved() is False

    def test_actor_to_dict(self):
        """Actor serializa corretamente."""
        actor = DraftActor(
            id="admin",
            role="administrator",
            permissions=["read", "write"],
        )
        d = actor.to_dict()
        assert d["id"] == "admin"
        assert d["role"] == "administrator"
        assert d["permissions"] == ["read", "write"]

    def test_actor_from_dict(self):
        """Actor deserializa corretamente."""
        data = {
            "id": "user",
            "role": "customer",
            "permissions": ["browse"],
        }
        actor = DraftActor.from_dict(data)
        assert actor.id == "user"
        assert actor.role == "customer"
        assert actor.permissions == ["browse"]

    def test_actor_from_dict_defaults(self):
        """Actor deserializa com defaults."""
        data = {"id": "guest"}
        actor = DraftActor.from_dict(data)
        assert actor.id == "guest"
        assert actor.role == UNKNOWN
        assert actor.permissions == []


class TestDraftField:
    """Testes para DraftField."""

    def test_field_has_unresolved_unknown_type(self):
        """Field com type unknown tem unresolved."""
        field = DraftField(name="data", type=UNKNOWN, required=True)
        assert field.has_unresolved() is True

    def test_field_has_unresolved_unknown_required(self):
        """Field com required unknown tem unresolved."""
        field = DraftField(name="data", type="string", required=UNKNOWN)
        assert field.has_unresolved() is True

    def test_field_has_unresolved_both_valid(self):
        """Field com tudo válido não tem unresolved."""
        field = DraftField(name="data", type="string", required=True)
        assert field.has_unresolved() is False

    def test_field_to_dict(self):
        """Field serializa corretamente."""
        field = DraftField(name="email", type="string", required=True)
        d = field.to_dict()
        assert d["name"] == "email"
        assert d["type"] == "string"
        assert d["required"] is True

    def test_field_from_dict(self):
        """Field deserializa corretamente."""
        data = {"name": "id", "type": "uuid", "required": True}
        field = DraftField.from_dict(data)
        assert field.name == "id"
        assert field.type == "uuid"
        assert field.required is True


class TestDraftEntity:
    """Testes para DraftEntity."""

    def test_entity_has_unresolved_with_unknown_field(self):
        """Entity com field unknown tem unresolved."""
        entity = DraftEntity(
            id="User",
            fields=[
                DraftField(name="id", type="string", required=True),
                DraftField(name="data", type=UNKNOWN, required=True),
            ]
        )
        assert entity.has_unresolved() is True

    def test_entity_has_unresolved_all_valid(self):
        """Entity com todos campos válidos não tem unresolved."""
        entity = DraftEntity(
            id="User",
            fields=[
                DraftField(name="id", type="string", required=True),
                DraftField(name="name", type="string", required=False),
            ]
        )
        assert entity.has_unresolved() is False

    def test_entity_get_unresolved_fields(self):
        """get_unresolved_fields retorna paths corretos."""
        entity = DraftEntity(
            id="User",
            fields=[
                DraftField(name="id", type="string", required=True),
                DraftField(name="data", type=UNKNOWN, required=True),
                DraftField(name="optional", type="string", required=UNKNOWN),
            ]
        )
        unresolved = entity.get_unresolved_fields()
        assert "fields.data.type" in unresolved
        assert "fields.optional.required" in unresolved
        assert "fields.id.type" not in unresolved

    def test_entity_to_dict(self):
        """Entity serializa corretamente."""
        entity = DraftEntity(
            id="Product",
            fields=[
                DraftField(name="id", type="string", required=True),
            ]
        )
        d = entity.to_dict()
        assert d["id"] == "Product"
        assert len(d["fields"]) == 1
        assert d["fields"][0]["name"] == "id"

    def test_entity_from_dict(self):
        """Entity deserializa corretamente."""
        data = {
            "id": "Order",
            "fields": [
                {"name": "total", "type": "decimal", "required": True},
            ]
        }
        entity = DraftEntity.from_dict(data)
        assert entity.id == "Order"
        assert len(entity.fields) == 1
        assert entity.fields[0].name == "total"


class TestDraftUseCase:
    """Testes para DraftUseCase."""

    def test_usecase_has_unresolved_unknown_actor(self):
        """UseCase com actor unknown tem unresolved."""
        uc = DraftUseCase(id="UC001", actor=UNKNOWN, flow=[])
        assert uc.has_unresolved() is True

    def test_usecase_has_unresolved_valid_actor(self):
        """UseCase com actor válido não tem unresolved."""
        uc = DraftUseCase(id="UC001", actor="admin", flow=[])
        assert uc.has_unresolved() is False

    def test_usecase_to_dict(self):
        """UseCase serializa corretamente."""
        uc = DraftUseCase(
            id="UC001",
            actor="customer",
            flow=[
                DraftFlowStep(step=1, action="Login"),
                DraftFlowStep(step=2, action="Browse"),
            ]
        )
        d = uc.to_dict()
        assert d["id"] == "UC001"
        assert d["actor"] == "customer"
        assert len(d["flow"]) == 2
        assert d["flow"][0]["step"] == 1

    def test_usecase_from_dict(self):
        """UseCase deserializa corretamente."""
        data = {
            "id": "UC002",
            "actor": "admin",
            "flow": [
                {"step": 1, "action": "Manage"},
            ]
        }
        uc = DraftUseCase.from_dict(data)
        assert uc.id == "UC002"
        assert uc.actor == "admin"
        assert len(uc.flow) == 1


class TestDraftIntegration:
    """Testes para DraftIntegration."""

    def test_integration_has_unresolved_unknown_type(self):
        """Integration com type unknown tem unresolved."""
        integ = DraftIntegration(system="External", type=UNKNOWN)
        assert integ.has_unresolved() is True

    def test_integration_has_unresolved_valid_type(self):
        """Integration com type válido não tem unresolved."""
        integ = DraftIntegration(system="PaymentAPI", type="api")
        assert integ.has_unresolved() is False

    def test_integration_to_dict(self):
        """Integration serializa corretamente."""
        integ = DraftIntegration(system="InventoryDB", type="db")
        d = integ.to_dict()
        assert d["system"] == "InventoryDB"
        assert d["type"] == "db"

    def test_integration_from_dict(self):
        """Integration deserializa corretamente."""
        data = {"system": "MessageQueue", "type": "queue"}
        integ = DraftIntegration.from_dict(data)
        assert integ.system == "MessageQueue"
        assert integ.type == "queue"


class TestDraftNonFunctional:
    """Testes para DraftNonFunctional."""

    def test_nonfunctional_has_unresolved_always_false(self):
        """NFR sempre retorna False (não bloqueia)."""
        nf = DraftNonFunctional(performance=UNKNOWN, security=UNKNOWN)
        # NFRs unknown NÃO bloqueiam compilação
        assert nf.has_unresolved() is False

    def test_nonfunctional_to_dict(self):
        """NonFunctional serializa corretamente."""
        nf = DraftNonFunctional(
            performance="p99 < 500ms",
            security="TLS 1.3",
        )
        d = nf.to_dict()
        assert d["performance"] == "p99 < 500ms"
        assert d["security"] == "TLS 1.3"

    def test_nonfunctional_from_dict(self):
        """NonFunctional deserializa corretamente."""
        data = {"performance": "fast", "security": "secure"}
        nf = DraftNonFunctional.from_dict(data)
        assert nf.performance == "fast"
        assert nf.security == "secure"


class TestIDLDraftV1:
    """Testes para IDLDraftV1."""

    def test_has_open_questions_true(self):
        """Draft com open_questions retorna True."""
        draft = IDLDraftV1(
            project="test",
            open_questions=["What about X?"],
        )
        assert draft.has_open_questions() is True

    def test_has_open_questions_false(self):
        """Draft sem open_questions retorna False."""
        draft = IDLDraftV1(project="test")
        assert draft.has_open_questions() is False

    def test_has_assumptions_true(self):
        """Draft com assumptions retorna True."""
        draft = IDLDraftV1(
            project="test",
            assumptions=["Assume X"],
        )
        assert draft.has_assumptions() is True

    def test_has_assumptions_false(self):
        """Draft sem assumptions retorna False."""
        draft = IDLDraftV1(project="test")
        assert draft.has_assumptions() is False

    def test_get_all_unresolved_actors(self):
        """get_all_unresolved inclui actors com role unknown."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role=UNKNOWN)],
        )
        unresolved = draft.get_all_unresolved()
        assert "actors.admin.role" in unresolved

    def test_get_all_unresolved_entities(self):
        """get_all_unresolved inclui entities com campos unknown."""
        draft = IDLDraftV1(
            project="test",
            entities=[
                DraftEntity(
                    id="User",
                    fields=[
                        DraftField(name="data", type=UNKNOWN, required=True),
                    ]
                )
            ],
        )
        unresolved = draft.get_all_unresolved()
        assert "entities.User.fields.data.type" in unresolved

    def test_get_all_unresolved_use_cases(self):
        """get_all_unresolved inclui use_cases com actor unknown."""
        draft = IDLDraftV1(
            project="test",
            use_cases=[DraftUseCase(id="UC001", actor=UNKNOWN)],
        )
        unresolved = draft.get_all_unresolved()
        assert "use_cases.UC001.actor" in unresolved

    def test_get_all_unresolved_integrations(self):
        """get_all_unresolved inclui integrations com type unknown."""
        draft = IDLDraftV1(
            project="test",
            integrations=[DraftIntegration(system="External", type=UNKNOWN)],
        )
        unresolved = draft.get_all_unresolved()
        assert "integrations.External.type" in unresolved

    def test_is_compileable_with_open_questions(self):
        """Draft com open_questions NÃO é compilável."""
        draft = IDLDraftV1(
            project="test",
            open_questions=["What?"],
        )
        assert draft.is_compileable() is False

    def test_is_compileable_with_unknown_fields(self):
        """Draft com campos unknown NÃO é compilável."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role=UNKNOWN)],
        )
        assert draft.is_compileable() is False

    def test_is_compileable_valid_draft(self):
        """Draft completamente válido É compilável."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="administrator")],
            entities=[
                DraftEntity(
                    id="User",
                    fields=[
                        DraftField(name="id", type="string", required=True),
                    ]
                )
            ],
            use_cases=[
                DraftUseCase(
                    id="UC001",
                    actor="admin",
                    flow=[DraftFlowStep(step=1, action="Login")],
                )
            ],
            integrations=[
                DraftIntegration(system="DB", type="db"),
            ],
        )
        assert draft.is_compileable() is True


class TestIDLDraftV1Serialization:
    """Testes de serialização do Draft."""

    def test_to_dict_minimal(self):
        """Draft mínimo serializa corretamente."""
        draft = IDLDraftV1(project="minimal")
        d = draft.to_dict()
        assert d["schema_version"] == IDL_DRAFT_SCHEMA_VERSION
        assert d["project"] == "minimal"
        assert d["source"] == "natural_text"
        assert d["actors"] == []
        assert d["entities"] == []

    def test_to_dict_complete(self):
        """Draft completo serializa corretamente."""
        draft = IDLDraftV1(
            project="complete",
            source=DraftSource.WIZARD,
            actors=[DraftActor(id="admin", role="admin")],
            entities=[
                DraftEntity(
                    id="User",
                    fields=[DraftField(name="id", type="string", required=True)],
                )
            ],
            use_cases=[
                DraftUseCase(
                    id="UC001",
                    actor="admin",
                    flow=[DraftFlowStep(step=1, action="Test")],
                )
            ],
            integrations=[DraftIntegration(system="API", type="api")],
            non_functional=DraftNonFunctional(performance="fast", security="secure"),
            assumptions=["Assumption 1"],
            open_questions=["Question 1"],
        )
        d = draft.to_dict()

        assert d["schema_version"] == IDL_DRAFT_SCHEMA_VERSION
        assert d["project"] == "complete"
        assert d["source"] == "wizard"
        assert len(d["actors"]) == 1
        assert len(d["entities"]) == 1
        assert len(d["use_cases"]) == 1
        assert len(d["integrations"]) == 1
        assert d["non_functional"]["performance"] == "fast"
        assert d["assumptions"] == ["Assumption 1"]
        assert d["open_questions"] == ["Question 1"]

    def test_from_dict_minimal(self):
        """Draft mínimo deserializa corretamente."""
        data = {
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "minimal",
        }
        draft = IDLDraftV1.from_dict(data)
        assert draft.project == "minimal"
        assert draft.source == DraftSource.NATURAL_TEXT
        assert draft.actors == []

    def test_from_dict_complete(self):
        """Draft completo deserializa corretamente."""
        data = {
            "schema_version": IDL_DRAFT_SCHEMA_VERSION,
            "project": "test",
            "source": "wizard",
            "actors": [{"id": "admin", "role": "admin", "permissions": []}],
            "entities": [
                {
                    "id": "User",
                    "fields": [{"name": "id", "type": "string", "required": True}],
                }
            ],
            "use_cases": [
                {
                    "id": "UC001",
                    "actor": "admin",
                    "flow": [{"step": 1, "action": "Test"}],
                }
            ],
            "integrations": [{"system": "API", "type": "api"}],
            "non_functional": {"performance": "fast", "security": "secure"},
            "assumptions": ["Assume X"],
            "open_questions": ["Question?"],
        }
        draft = IDLDraftV1.from_dict(data)

        assert draft.project == "test"
        assert draft.source == DraftSource.WIZARD
        assert len(draft.actors) == 1
        assert draft.actors[0].id == "admin"
        assert len(draft.entities) == 1
        assert len(draft.use_cases) == 1
        assert len(draft.integrations) == 1
        assert draft.non_functional.performance == "fast"
        assert draft.assumptions == ["Assume X"]
        assert draft.open_questions == ["Question?"]

    def test_roundtrip_serialization(self):
        """Draft serializa e deserializa corretamente (roundtrip)."""
        original = IDLDraftV1(
            project="roundtrip",
            source=DraftSource.IMPORTED,
            actors=[
                DraftActor(id="admin", role="admin", permissions=["all"]),
            ],
            entities=[
                DraftEntity(
                    id="Order",
                    fields=[
                        DraftField(name="id", type="uuid", required=True),
                        DraftField(name="total", type="decimal", required=True),
                    ]
                )
            ],
            use_cases=[
                DraftUseCase(
                    id="UC001",
                    actor="admin",
                    flow=[
                        DraftFlowStep(step=1, action="Login"),
                        DraftFlowStep(step=2, action="View orders"),
                    ]
                )
            ],
            integrations=[
                DraftIntegration(system="PaymentAPI", type="api"),
            ],
            non_functional=DraftNonFunctional(
                performance="p99 < 200ms",
                security="PCI-DSS",
            ),
            assumptions=["Users have valid accounts"],
            open_questions=["Support refunds?"],
        )

        # Serializa
        d = original.to_dict()

        # Deserializa
        restored = IDLDraftV1.from_dict(d)

        # Verifica
        assert restored.project == original.project
        assert restored.source == original.source
        assert len(restored.actors) == len(original.actors)
        assert restored.actors[0].id == original.actors[0].id
        assert len(restored.entities) == len(original.entities)
        assert len(restored.use_cases) == len(original.use_cases)
        assert len(restored.integrations) == len(original.integrations)
        assert restored.assumptions == original.assumptions
        assert restored.open_questions == original.open_questions


class TestDraftSourceEnum:
    """Testes para DraftSource enum."""

    def test_natural_text_value(self):
        """DraftSource.NATURAL_TEXT tem valor correto."""
        assert DraftSource.NATURAL_TEXT.value == "natural_text"

    def test_wizard_value(self):
        """DraftSource.WIZARD tem valor correto."""
        assert DraftSource.WIZARD.value == "wizard"

    def test_imported_value(self):
        """DraftSource.IMPORTED tem valor correto."""
        assert DraftSource.IMPORTED.value == "imported"
