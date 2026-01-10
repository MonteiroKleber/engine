"""Testes para IDL Draft Compile Success.

Testa a compilação bem-sucedida de Draft → IDL v1:
- Transformação correta de estruturas
- Remoção de assumptions, open_questions, source
- Normalização para IDL v1 canônico
- Mapeamento de tipos
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
)
from idl.idl_compile import (
    DraftToIDLCompiler,
    compile_draft_to_idl,
)
from idl.idl_v1 import (
    ActorType,
    IntegrationType,
    PriorityLevel,
    ComplexityLevel,
    NFRType,
)


class TestBasicCompilation:
    """Testes de compilação básica."""

    def test_minimal_draft_compiles(self):
        """Draft mínimo compila com sucesso."""
        draft = IDLDraftV1(project="minimal")
        result = compile_draft_to_idl(draft)

        assert result.success is True
        assert result.idl is not None
        assert result.idl.system.id == "minimal"

    def test_draft_with_actors_compiles(self):
        """Draft com actors compila."""
        draft = IDLDraftV1(
            project="test",
            actors=[
                DraftActor(id="admin", role="administrator", permissions=["all"]),
                DraftActor(id="user", role="customer", permissions=["read"]),
            ],
        )
        result = compile_draft_to_idl(draft)

        assert result.success is True
        assert len(result.idl.actors) == 2

    def test_draft_with_entities_compiles(self):
        """Draft com entities compila."""
        draft = IDLDraftV1(
            project="test",
            entities=[
                DraftEntity(
                    id="User",
                    fields=[
                        DraftField(name="id", type="string", required=True),
                        DraftField(name="email", type="string", required=True),
                    ]
                )
            ],
        )
        result = compile_draft_to_idl(draft)

        assert result.success is True
        assert len(result.idl.entities) == 1
        assert result.idl.entities[0].id == "User"

    def test_draft_with_usecases_compiles(self):
        """Draft com use_cases compila."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            use_cases=[
                DraftUseCase(
                    id="UC001",
                    actor="admin",
                    flow=[
                        DraftFlowStep(step=1, action="Login"),
                        DraftFlowStep(step=2, action="View dashboard"),
                    ]
                )
            ],
        )
        result = compile_draft_to_idl(draft)

        assert result.success is True
        assert len(result.idl.usecases) == 1

    def test_draft_with_integrations_compiles(self):
        """Draft com integrations compila."""
        draft = IDLDraftV1(
            project="test",
            integrations=[
                DraftIntegration(system="PaymentAPI", type="api"),
                DraftIntegration(system="InventoryDB", type="db"),
            ],
        )
        result = compile_draft_to_idl(draft)

        assert result.success is True
        assert len(result.idl.integrations) == 2


class TestActorTransformation:
    """Testes de transformação de actors."""

    def test_actor_id_preserved(self):
        """ID do actor é preservado."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin_user", role="administrator")],
        )
        result = compile_draft_to_idl(draft)

        assert result.idl.actors[0].id == "admin_user"

    def test_actor_permissions_preserved(self):
        """Permissions do actor são preservadas."""
        draft = IDLDraftV1(
            project="test",
            actors=[
                DraftActor(
                    id="admin",
                    role="admin",
                    permissions=["read", "write", "delete"],
                )
            ],
        )
        result = compile_draft_to_idl(draft)

        assert result.idl.actors[0].permissions == ["read", "write", "delete"]

    def test_actor_type_system_inferred(self):
        """ActorType.SYSTEM é inferido de roles system-like."""
        test_cases = [
            ("system", ActorType.SYSTEM),
            ("service", ActorType.SYSTEM),
            ("api", ActorType.SYSTEM),
            ("bot", ActorType.SYSTEM),
            ("scheduler", ActorType.SYSTEM),
            ("cron job", ActorType.SYSTEM),
        ]
        for role, expected_type in test_cases:
            draft = IDLDraftV1(
                project="test",
                actors=[DraftActor(id="actor", role=role)],
            )
            result = compile_draft_to_idl(draft)
            assert result.idl.actors[0].actor_type == expected_type, f"Failed for role: {role}"

    def test_actor_type_external_inferred(self):
        """ActorType.EXTERNAL é inferido de roles external-like."""
        test_cases = [
            ("external", ActorType.EXTERNAL),
            ("third-party", ActorType.EXTERNAL),
            ("partner", ActorType.EXTERNAL),
            ("gateway", ActorType.EXTERNAL),
        ]
        for role, expected_type in test_cases:
            draft = IDLDraftV1(
                project="test",
                actors=[DraftActor(id="actor", role=role)],
            )
            result = compile_draft_to_idl(draft)
            assert result.idl.actors[0].actor_type == expected_type, f"Failed for role: {role}"

    def test_actor_type_human_default(self):
        """ActorType.HUMAN é default para roles não-específicos."""
        test_cases = ["administrator", "customer", "user", "manager", "employee"]
        for role in test_cases:
            draft = IDLDraftV1(
                project="test",
                actors=[DraftActor(id="actor", role=role)],
            )
            result = compile_draft_to_idl(draft)
            assert result.idl.actors[0].actor_type == ActorType.HUMAN, f"Failed for role: {role}"


class TestEntityTransformation:
    """Testes de transformação de entities."""

    def test_entity_id_preserved(self):
        """ID da entity é preservado."""
        draft = IDLDraftV1(
            project="test",
            entities=[
                DraftEntity(
                    id="UserAccount",
                    fields=[DraftField(name="id", type="string", required=True)],
                )
            ],
        )
        result = compile_draft_to_idl(draft)

        assert result.idl.entities[0].id == "UserAccount"

    def test_entity_fields_preserved(self):
        """Fields da entity são preservados."""
        draft = IDLDraftV1(
            project="test",
            entities=[
                DraftEntity(
                    id="User",
                    fields=[
                        DraftField(name="id", type="uuid", required=True),
                        DraftField(name="email", type="string", required=True),
                        DraftField(name="age", type="integer", required=False),
                    ]
                )
            ],
        )
        result = compile_draft_to_idl(draft)

        entity = result.idl.entities[0]
        assert len(entity.fields) == 3

        # Verifica campos
        field_map = {f.id: f for f in entity.fields}
        assert field_map["id"].field_type == "uuid"
        assert field_map["id"].required is True
        assert field_map["email"].field_type == "string"
        assert field_map["age"].required is False

    def test_field_required_false_when_unknown(self):
        """Field required resolve para False se não boolean."""
        draft = IDLDraftV1(
            project="test",
            entities=[
                DraftEntity(
                    id="User",
                    # Required é string "true" ao invés de boolean
                    fields=[DraftField(name="data", type="string", required="maybe")],
                )
            ],
        )
        # Note: Este draft não deveria compilar normalmente,
        # mas se required não é unknown literal, passa
        # O compilador trata strings não-boolean como False
        result = compile_draft_to_idl(draft)

        assert result.success is True
        assert result.idl.entities[0].fields[0].required is False


class TestUseCaseTransformation:
    """Testes de transformação de use_cases."""

    def test_usecase_id_preserved(self):
        """ID do use case é preservado."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            use_cases=[
                DraftUseCase(
                    id="UC001_CreateUser",
                    actor="admin",
                    flow=[DraftFlowStep(step=1, action="Test")],
                )
            ],
        )
        result = compile_draft_to_idl(draft)

        assert result.idl.usecases[0].id == "UC001_CreateUser"

    def test_usecase_actor_preserved(self):
        """Actor do use case é preservado."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="customer", role="customer")],
            use_cases=[
                DraftUseCase(id="UC001", actor="customer", flow=[]),
            ],
        )
        result = compile_draft_to_idl(draft)

        assert "customer" in result.idl.usecases[0].actors

    def test_usecase_flow_steps_preserved(self):
        """Flow steps são preservados."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="user", role="user")],
            use_cases=[
                DraftUseCase(
                    id="UC001",
                    actor="user",
                    flow=[
                        DraftFlowStep(step=1, action="Open application"),
                        DraftFlowStep(step=2, action="Enter credentials"),
                        DraftFlowStep(step=3, action="Click login"),
                    ]
                )
            ],
        )
        result = compile_draft_to_idl(draft)

        flow = result.idl.usecases[0].main_flow
        assert len(flow) == 3
        assert flow[0].number == 1
        assert flow[0].description == "Open application"
        assert flow[1].number == 2
        assert flow[2].number == 3

    def test_usecase_defaults(self):
        """Use case tem defaults corretos."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="user", role="user")],
            use_cases=[DraftUseCase(id="UC001", actor="user", flow=[])],
        )
        result = compile_draft_to_idl(draft)

        uc = result.idl.usecases[0]
        assert uc.priority == PriorityLevel.MEDIUM
        assert uc.complexity == ComplexityLevel.MEDIUM


class TestIntegrationTransformation:
    """Testes de transformação de integrations."""

    def test_integration_id_from_system(self):
        """Integration id vem do system."""
        draft = IDLDraftV1(
            project="test",
            integrations=[DraftIntegration(system="PaymentGateway", type="api")],
        )
        result = compile_draft_to_idl(draft)

        assert result.idl.integrations[0].id == "PaymentGateway"

    def test_integration_type_mapping_rest(self):
        """Integration type 'api' mapeia para REST_API."""
        test_cases = [
            ("api", IntegrationType.REST_API),
            ("rest", IntegrationType.REST_API),
            ("rest_api", IntegrationType.REST_API),
        ]
        for type_str, expected in test_cases:
            draft = IDLDraftV1(
                project="test",
                integrations=[DraftIntegration(system="API", type=type_str)],
            )
            result = compile_draft_to_idl(draft)
            assert result.idl.integrations[0].integration_type == expected

    def test_integration_type_mapping_db(self):
        """Integration type 'db' mapeia para DATABASE."""
        test_cases = [
            ("db", IntegrationType.DATABASE),
            ("database", IntegrationType.DATABASE),
        ]
        for type_str, expected in test_cases:
            draft = IDLDraftV1(
                project="test",
                integrations=[DraftIntegration(system="DB", type=type_str)],
            )
            result = compile_draft_to_idl(draft)
            assert result.idl.integrations[0].integration_type == expected

    def test_integration_type_mapping_queue(self):
        """Integration type 'queue' mapeia para MESSAGE_QUEUE."""
        test_cases = [
            ("queue", IntegrationType.MESSAGE_QUEUE),
            ("message_queue", IntegrationType.MESSAGE_QUEUE),
        ]
        for type_str, expected in test_cases:
            draft = IDLDraftV1(
                project="test",
                integrations=[DraftIntegration(system="MQ", type=type_str)],
            )
            result = compile_draft_to_idl(draft)
            assert result.idl.integrations[0].integration_type == expected

    def test_integration_type_mapping_others(self):
        """Outros integration types mapeiam corretamente."""
        test_cases = [
            ("graphql", IntegrationType.GRAPHQL),
            ("grpc", IntegrationType.GRPC),
            ("soap", IntegrationType.SOAP),
            ("webhook", IntegrationType.WEBHOOK),
            ("file", IntegrationType.FILE_SYSTEM),
            ("file_system", IntegrationType.FILE_SYSTEM),
        ]
        for type_str, expected in test_cases:
            draft = IDLDraftV1(
                project="test",
                integrations=[DraftIntegration(system="System", type=type_str)],
            )
            result = compile_draft_to_idl(draft)
            assert result.idl.integrations[0].integration_type == expected

    def test_integration_type_unknown_defaults_rest(self):
        """Integration type desconhecido default para REST_API."""
        draft = IDLDraftV1(
            project="test",
            integrations=[DraftIntegration(system="External", type="custom")],
        )
        result = compile_draft_to_idl(draft)

        assert result.idl.integrations[0].integration_type == IntegrationType.REST_API


class TestNonFunctionalTransformation:
    """Testes de transformação de non_functional."""

    def test_nfr_performance_preserved(self):
        """NFR performance é preservado."""
        draft = IDLDraftV1(
            project="test",
            non_functional=DraftNonFunctional(
                performance="p99 < 200ms",
                security="TLS 1.3",
            ),
        )
        result = compile_draft_to_idl(draft)

        nfrs = result.idl.nonfunctional
        perf_nfr = next((n for n in nfrs if n.nfr_type == NFRType.PERFORMANCE), None)
        assert perf_nfr is not None
        assert perf_nfr.target == "p99 < 200ms"

    def test_nfr_security_preserved(self):
        """NFR security é preservado."""
        draft = IDLDraftV1(
            project="test",
            non_functional=DraftNonFunctional(
                performance="fast",
                security="PCI-DSS compliant",
            ),
        )
        result = compile_draft_to_idl(draft)

        nfrs = result.idl.nonfunctional
        sec_nfr = next((n for n in nfrs if n.nfr_type == NFRType.SECURITY), None)
        assert sec_nfr is not None
        assert sec_nfr.target == "PCI-DSS compliant"

    def test_nfr_unknown_not_included(self):
        """NFR unknown não é incluído no IDL."""
        draft = IDLDraftV1(
            project="test",
            non_functional=DraftNonFunctional(
                performance="unknown",
                security="TLS",
            ),
        )
        result = compile_draft_to_idl(draft)

        nfrs = result.idl.nonfunctional
        # Performance é unknown, não deveria estar presente
        perf_nfr = next((n for n in nfrs if n.nfr_type == NFRType.PERFORMANCE), None)
        assert perf_nfr is None

        # Security não é unknown, deveria estar presente
        sec_nfr = next((n for n in nfrs if n.nfr_type == NFRType.SECURITY), None)
        assert sec_nfr is not None


class TestRemovalOfDraftOnlyFields:
    """Testes confirmando remoção de campos Draft-only."""

    def test_assumptions_not_in_idl(self):
        """Assumptions não aparecem no IDL."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            assumptions=["Users have valid emails", "System is online"],
        )
        result = compile_draft_to_idl(draft)

        # IDL não tem campo assumptions
        idl_dict = result.idl.to_canonical_dict()
        assert "assumptions" not in idl_dict

    def test_open_questions_not_compileable(self):
        """Open questions bloqueiam - já coberto em blocking tests."""
        pass  # Coberto em test_idl_draft_compile_blocking.py

    def test_source_not_in_idl(self):
        """Source não aparece no IDL."""
        draft = IDLDraftV1(
            project="test",
            source=DraftSource.WIZARD,
            actors=[DraftActor(id="admin", role="admin")],
        )
        result = compile_draft_to_idl(draft)

        idl_dict = result.idl.to_canonical_dict()
        assert "source" not in idl_dict


class TestCompleteCompilation:
    """Testes de compilação completa."""

    def test_complete_draft_compiles(self):
        """Draft completo compila corretamente."""
        draft = IDLDraftV1(
            project="ecommerce",
            source=DraftSource.WIZARD,
            actors=[
                DraftActor(id="customer", role="buyer", permissions=["browse", "purchase"]),
                DraftActor(id="admin", role="administrator", permissions=["manage_all"]),
                DraftActor(id="payment_service", role="system", permissions=["process_payment"]),
            ],
            entities=[
                DraftEntity(
                    id="Product",
                    fields=[
                        DraftField(name="id", type="uuid", required=True),
                        DraftField(name="name", type="string", required=True),
                        DraftField(name="price", type="decimal", required=True),
                        DraftField(name="stock", type="integer", required=True),
                    ]
                ),
                DraftEntity(
                    id="Order",
                    fields=[
                        DraftField(name="id", type="uuid", required=True),
                        DraftField(name="customer_id", type="uuid", required=True),
                        DraftField(name="total", type="decimal", required=True),
                        DraftField(name="status", type="string", required=True),
                    ]
                ),
            ],
            use_cases=[
                DraftUseCase(
                    id="UC001_BrowseProducts",
                    actor="customer",
                    flow=[
                        DraftFlowStep(step=1, action="Customer opens catalog"),
                        DraftFlowStep(step=2, action="System displays products"),
                        DraftFlowStep(step=3, action="Customer filters by category"),
                    ]
                ),
                DraftUseCase(
                    id="UC002_PlaceOrder",
                    actor="customer",
                    flow=[
                        DraftFlowStep(step=1, action="Customer adds items to cart"),
                        DraftFlowStep(step=2, action="Customer proceeds to checkout"),
                        DraftFlowStep(step=3, action="System calculates total"),
                        DraftFlowStep(step=4, action="Customer confirms payment"),
                    ]
                ),
            ],
            integrations=[
                DraftIntegration(system="PaymentGateway", type="api"),
                DraftIntegration(system="InventoryDB", type="database"),
                DraftIntegration(system="NotificationService", type="queue"),
            ],
            non_functional=DraftNonFunctional(
                performance="p99 < 500ms for all API calls",
                security="PCI-DSS Level 1 compliant",
            ),
            assumptions=[
                "Payment gateway is available 99.9%",
                "Users have verified email addresses",
            ],
        )

        result = compile_draft_to_idl(draft)

        # Deve compilar com sucesso
        assert result.success is True
        idl = result.idl

        # Verifica estrutura básica
        assert idl.system.id == "ecommerce"
        assert len(idl.actors) == 3
        assert len(idl.entities) == 2
        assert len(idl.usecases) == 2
        assert len(idl.integrations) == 3

        # Verifica tipos de actors
        customer = next(a for a in idl.actors if a.id == "customer")
        payment = next(a for a in idl.actors if a.id == "payment_service")
        assert customer.actor_type == ActorType.HUMAN
        assert payment.actor_type == ActorType.SYSTEM

        # Verifica entities
        product = next(e for e in idl.entities if e.id == "Product")
        assert len(product.fields) == 4

        # Verifica use cases
        browse = next(uc for uc in idl.usecases if uc.id == "UC001_BrowseProducts")
        assert len(browse.main_flow) == 3

        # Verifica integrations
        payment_int = next(i for i in idl.integrations if i.id == "PaymentGateway")
        assert payment_int.integration_type == IntegrationType.REST_API

        # Verifica NFRs
        assert len(idl.nonfunctional) == 2

    def test_idl_can_be_serialized(self):
        """IDL compilado pode ser serializado."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
            entities=[
                DraftEntity(
                    id="User",
                    fields=[DraftField(name="id", type="string", required=True)],
                )
            ],
        )
        result = compile_draft_to_idl(draft)

        # Deve poder serializar para JSON
        json_str = result.idl.to_json()
        assert "test" in json_str
        assert "User" in json_str

        # Deve poder serializar para Markdown
        md_str = result.idl.to_markdown()
        assert "test" in md_str

    def test_idl_has_content_hash(self):
        """IDL compilado tem hash de conteúdo."""
        draft = IDLDraftV1(
            project="test",
            actors=[DraftActor(id="admin", role="admin")],
        )
        result = compile_draft_to_idl(draft)

        canonical = result.idl.to_canonical_dict()
        assert "content_hash_sha256" in canonical
        assert len(canonical["content_hash_sha256"]) == 64  # SHA256 hex
