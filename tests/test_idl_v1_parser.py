"""Testes do parser IDL v1.

Valida:
1) Parsing de todas as secoes (system, actors, entities, usecases, integrations, nonfunctional)
2) Parsing de tipos primitivos e colecoes
3) Parsing de modificadores e propriedades
4) Tratamento de erros de sintaxe
5) Comentarios e whitespace
"""

import pytest

from idl.idl_v1 import (
    IDL_SCHEMA_VERSION,
    IDLDocument,
    IDLParser,
    IDLParseError,
    ActorType,
    AuthMethod,
    RelationType,
    PriorityLevel,
    ComplexityLevel,
    IntegrationType,
    ProtocolType,
    NFRType,
)


class TestParserSystem:
    """Testes de parsing da secao system."""

    def test_parse_minimal_system(self):
        """[Parser] Parse de system minimo."""
        source = '''
        system MyApp {
            name: "My Application"
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert doc.system is not None
        assert doc.system.id == "MyApp"
        assert doc.system.name == "My Application"

    def test_parse_full_system(self):
        """[Parser] Parse de system completo."""
        source = '''
        system PetClinic {
            name: "Pet Clinic System"
            description: "A sample Spring application"
            version: "2.0.0"
            domain: "veterinary"
            owner: "Spring Team"
            contact: "spring@example.com"
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert doc.system is not None
        assert doc.system.id == "PetClinic"
        assert doc.system.name == "Pet Clinic System"
        assert doc.system.description == "A sample Spring application"
        assert doc.system.version == "2.0.0"
        assert doc.system.domain == "veterinary"
        assert doc.system.owner == "Spring Team"
        assert doc.system.contact == "spring@example.com"


class TestParserActors:
    """Testes de parsing da secao actors."""

    def test_parse_human_actor(self):
        """[Parser] Parse de ator humano."""
        source = '''
        actors {
            human Admin {
                name: "Administrator"
                description: "System administrator"
                permissions: [read, write, delete]
                authentication: oauth2
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert len(doc.actors) == 1
        admin = doc.actors[0]
        assert admin.id == "Admin"
        assert admin.actor_type == ActorType.HUMAN
        assert admin.name == "Administrator"
        assert admin.description == "System administrator"
        assert sorted(admin.permissions) == ["delete", "read", "write"]
        assert admin.authentication == AuthMethod.OAUTH2

    def test_parse_system_actor(self):
        """[Parser] Parse de ator sistema."""
        source = '''
        actors {
            system Scheduler {
                name: "Job Scheduler"
                authentication: token
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert len(doc.actors) == 1
        scheduler = doc.actors[0]
        assert scheduler.actor_type == ActorType.SYSTEM
        assert scheduler.authentication == AuthMethod.TOKEN

    def test_parse_external_actor(self):
        """[Parser] Parse de ator externo."""
        source = '''
        actors {
            external PaymentGateway {
                name: "Payment Gateway"
                authentication: certificate
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert len(doc.actors) == 1
        assert doc.actors[0].actor_type == ActorType.EXTERNAL
        assert doc.actors[0].authentication == AuthMethod.CERTIFICATE

    def test_parse_multiple_actors(self):
        """[Parser] Parse de multiplos atores."""
        source = '''
        actors {
            human User {
                name: "Regular User"
            }
            human Admin {
                name: "Administrator"
            }
            system Cron {
                name: "Cron Job"
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert len(doc.actors) == 3


class TestParserEntities:
    """Testes de parsing da secao entities."""

    def test_parse_entity_with_fields(self):
        """[Parser] Parse de entidade com campos."""
        source = '''
        entities {
            entity Pet {
                field id: uuid required unique
                field name: string required
                field birthDate: datetime
                field weight: decimal
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert len(doc.entities) == 1
        pet = doc.entities[0]
        assert pet.id == "Pet"
        assert len(pet.fields) == 4

        id_field = next(f for f in pet.fields if f.id == "id")
        assert id_field.field_type == "uuid"
        assert id_field.required is True
        assert id_field.unique is True

        name_field = next(f for f in pet.fields if f.id == "name")
        assert name_field.required is True

    def test_parse_entity_with_field_modifiers(self):
        """[Parser] Parse de entidade com modificadores de campo."""
        source = '''
        entities {
            entity Product {
                field price: decimal min(0) max(99999.99)
                field sku: string pattern("[A-Z]{3}-[0-9]{4}")
                field quantity: int default(0) indexed
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        product = doc.entities[0]

        price = next(f for f in product.fields if f.id == "price")
        assert price.min_value == 0
        assert price.max_value == 99999.99

        sku = next(f for f in product.fields if f.id == "sku")
        assert sku.pattern == "[A-Z]{3}-[0-9]{4}"

        qty = next(f for f in product.fields if f.id == "quantity")
        assert qty.default == 0
        assert qty.indexed is True

    def test_parse_entity_with_relations(self):
        """[Parser] Parse de entidade com relacoes."""
        source = '''
        entities {
            entity Owner {
                field id: uuid required
                has_many pets -> Pet cascade_delete
            }
            entity Pet {
                field id: uuid required
                belongs_to owner -> Owner nullable
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        owner = next(e for e in doc.entities if e.id == "Owner")
        assert len(owner.relations) == 1
        pets_rel = owner.relations[0]
        assert pets_rel.relation_type == RelationType.HAS_MANY
        assert pets_rel.target_entity == "Pet"
        assert pets_rel.cascade_delete is True

        pet = next(e for e in doc.entities if e.id == "Pet")
        owner_rel = pet.relations[0]
        assert owner_rel.relation_type == RelationType.BELONGS_TO
        assert owner_rel.nullable is True

    def test_parse_entity_with_many_to_many(self):
        """[Parser] Parse de relacao many_to_many."""
        source = '''
        entities {
            entity Student {
                field id: uuid required
                many_to_many courses -> Course through(Enrollment)
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        student = doc.entities[0]
        courses_rel = student.relations[0]
        assert courses_rel.relation_type == RelationType.MANY_TO_MANY
        assert courses_rel.through == "Enrollment"

    def test_parse_entity_with_constraints(self):
        """[Parser] Parse de entidade com constraints."""
        source = '''
        entities {
            entity Order {
                field id: uuid required
                field total: decimal
                field discount: decimal
                constraint valid_discount: "discount <= total"
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        order = doc.entities[0]
        assert len(order.constraints) == 1
        constraint = order.constraints[0]
        assert constraint.id == "valid_discount"
        assert constraint.expression == "discount <= total"

    def test_parse_entity_with_indexes(self):
        """[Parser] Parse de entidade com indices."""
        source = '''
        entities {
            entity User {
                field id: uuid required
                field email: string required
                field name: string
                index idx_email on (email) unique
                index idx_name on (name)
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        user = doc.entities[0]
        assert len(user.indexes) == 2

        email_idx = next(i for i in user.indexes if i.id == "idx_email")
        assert email_idx.fields == ["email"]
        assert email_idx.unique is True

        name_idx = next(i for i in user.indexes if i.id == "idx_name")
        assert name_idx.unique is False

    def test_parse_entity_with_collection_types(self):
        """[Parser] Parse de tipos colecao."""
        source = '''
        entities {
            entity Profile {
                field tags: list<string>
                field preferences: map<string, string>
                field uniqueTags: set<string>
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        profile = doc.entities[0]

        tags = next(f for f in profile.fields if f.id == "tags")
        assert tags.field_type == "list<string>"

        prefs = next(f for f in profile.fields if f.id == "preferences")
        assert prefs.field_type == "map<string,string>"

        unique_tags = next(f for f in profile.fields if f.id == "uniqueTags")
        assert unique_tags.field_type == "set<string>"


class TestParserUseCases:
    """Testes de parsing da secao usecases."""

    def test_parse_minimal_usecase(self):
        """[Parser] Parse de caso de uso minimo."""
        source = '''
        usecases {
            usecase RegisterPet {
                name: "Register Pet"
                actor: Owner
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert len(doc.usecases) == 1
        uc = doc.usecases[0]
        assert uc.id == "RegisterPet"
        assert uc.name == "Register Pet"
        assert uc.actors == ["Owner"]

    def test_parse_full_usecase(self):
        """[Parser] Parse de caso de uso completo."""
        source = '''
        usecases {
            usecase CreateAppointment {
                name: "Create Appointment"
                description: "Schedule a new appointment for a pet"
                actors: [Owner, Receptionist]
                preconditions: [
                    "User is authenticated",
                    "Pet is registered"
                ]
                postconditions: [
                    "Appointment is created",
                    "Notification is sent"
                ]
                main_flow: [
                    1. "User selects pet",
                    2. "User chooses date and time",
                    3. "System validates availability",
                    4. "System creates appointment"
                ]
                alternative_flows: [
                    no_availability: [
                        1. "System shows alternative slots"
                    ]
                ]
                exception_flows: [
                    system_error: [
                        1. "System shows error message",
                        2. "System logs error"
                    ]
                ]
                priority: high
                complexity: medium
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        uc = doc.usecases[0]
        assert uc.name == "Create Appointment"
        assert sorted(uc.actors) == ["Owner", "Receptionist"]
        assert len(uc.preconditions) == 2
        assert len(uc.postconditions) == 2
        assert len(uc.main_flow) == 4
        assert uc.main_flow[0].number == 1
        assert uc.main_flow[0].description == "User selects pet"
        assert len(uc.alternative_flows) == 1
        assert len(uc.exception_flows) == 1
        assert uc.priority == PriorityLevel.HIGH
        assert uc.complexity == ComplexityLevel.MEDIUM


class TestParserIntegrations:
    """Testes de parsing da secao integrations."""

    def test_parse_rest_api_integration(self):
        """[Parser] Parse de integracao REST API."""
        source = '''
        integrations {
            integration PaymentService {
                name: "Payment Service"
                description: "External payment processing"
                type: rest_api
                protocol: https
                endpoint: "https://api.payment.com/v1"
                timeout_ms: 5000
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert len(doc.integrations) == 1
        integ = doc.integrations[0]
        assert integ.id == "PaymentService"
        assert integ.integration_type == IntegrationType.REST_API
        assert integ.protocol == ProtocolType.HTTPS
        assert integ.endpoint == "https://api.payment.com/v1"
        assert integ.timeout_ms == 5000

    def test_parse_integration_with_auth(self):
        """[Parser] Parse de integracao com autenticacao."""
        source = '''
        integrations {
            integration SecureAPI {
                name: "Secure API"
                type: rest_api
                protocol: https
                endpoint: "https://secure.api.com"
                authentication: {
                    method: oauth2
                    token_url: "https://auth.api.com/token"
                    scope: "read write"
                }
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        integ = doc.integrations[0]
        assert integ.authentication is not None
        assert integ.authentication.method == AuthMethod.OAUTH2
        assert integ.authentication.token_url == "https://auth.api.com/token"
        assert integ.authentication.scope == "read write"

    def test_parse_integration_with_operations(self):
        """[Parser] Parse de integracao com operacoes."""
        source = '''
        integrations {
            integration UserAPI {
                name: "User API"
                type: rest_api
                protocol: https
                endpoint: "https://users.api.com"
                operations: [
                    getUser: {
                        method: GET
                        path: "/users/{id}"
                        response: User
                        errors: [404, 500]
                    },
                    createUser: {
                        method: POST
                        path: "/users"
                        request: CreateUserRequest
                        response: User
                        errors: [400, 500]
                    }
                ]
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        integ = doc.integrations[0]
        assert len(integ.operations) == 2

        get_user = next(o for o in integ.operations if o.id == "getUser")
        assert get_user.method == "GET"
        assert get_user.path == "/users/{id}"
        assert get_user.response_type == "User"
        assert sorted(get_user.error_codes) == [404, 500]

        create_user = next(o for o in integ.operations if o.id == "createUser")
        assert create_user.method == "POST"
        assert create_user.request_type == "CreateUserRequest"

    def test_parse_integration_with_retry_and_circuit_breaker(self):
        """[Parser] Parse de integracao com retry e circuit breaker."""
        source = '''
        integrations {
            integration ReliableAPI {
                name: "Reliable API"
                type: rest_api
                protocol: https
                endpoint: "https://reliable.api.com"
                retry_policy: {
                    max_attempts: 3
                    initial_delay_ms: 1000
                    max_delay_ms: 10000
                    multiplier: 2.0
                }
                circuit_breaker: {
                    failure_threshold: 5
                    success_threshold: 2
                    timeout_ms: 30000
                }
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        integ = doc.integrations[0]

        assert integ.retry_policy is not None
        assert integ.retry_policy.max_attempts == 3
        assert integ.retry_policy.initial_delay_ms == 1000
        assert integ.retry_policy.multiplier == 2.0

        assert integ.circuit_breaker is not None
        assert integ.circuit_breaker.failure_threshold == 5
        assert integ.circuit_breaker.success_threshold == 2


class TestParserNonFunctional:
    """Testes de parsing da secao nonfunctional."""

    def test_parse_performance_nfr(self):
        """[Parser] Parse de NFR de performance."""
        source = '''
        nonfunctional {
            performance ResponseTime {
                name: "API Response Time"
                description: "Maximum response time for API calls"
                metric: "response_time_p99"
                target: "< 200ms"
                measurement: "APM monitoring"
                priority: critical
                verification: "Load testing with 1000 concurrent users"
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert len(doc.nonfunctional) == 1
        nfr = doc.nonfunctional[0]
        assert nfr.id == "ResponseTime"
        assert nfr.nfr_type == NFRType.PERFORMANCE
        assert nfr.metric == "response_time_p99"
        assert nfr.target == "< 200ms"
        assert nfr.priority == PriorityLevel.CRITICAL

    def test_parse_security_nfr(self):
        """[Parser] Parse de NFR de seguranca."""
        source = '''
        nonfunctional {
            security DataEncryption {
                name: "Data Encryption"
                description: "All sensitive data must be encrypted"
                target: "AES-256 encryption"
                verification: "Security audit"
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        nfr = doc.nonfunctional[0]
        assert nfr.nfr_type == NFRType.SECURITY

    def test_parse_multiple_nfr_types(self):
        """[Parser] Parse de multiplos tipos de NFR."""
        source = '''
        nonfunctional {
            availability Uptime {
                name: "System Uptime"
                target: "99.9%"
            }
            scalability LoadCapacity {
                name: "Load Capacity"
                target: "10000 concurrent users"
            }
            maintainability CodeQuality {
                name: "Code Quality"
                target: "80% test coverage"
            }
            usability AccessTime {
                name: "Access Time"
                target: "< 3 clicks to any feature"
            }
            compliance GDPR {
                name: "GDPR Compliance"
                target: "Full compliance"
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert len(doc.nonfunctional) == 5

        types = {nfr.nfr_type for nfr in doc.nonfunctional}
        assert NFRType.AVAILABILITY in types
        assert NFRType.SCALABILITY in types
        assert NFRType.MAINTAINABILITY in types
        assert NFRType.USABILITY in types
        assert NFRType.COMPLIANCE in types


class TestParserComments:
    """Testes de parsing de comentarios."""

    def test_parse_with_line_comments(self):
        """[Parser] Parse com comentarios de linha."""
        source = '''
        // This is the system definition
        system MyApp {
            name: "My App"  // inline comment
        }
        // End of file
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert doc.system is not None
        assert doc.system.name == "My App"

    def test_parse_with_block_comments(self):
        """[Parser] Parse com comentarios de bloco."""
        source = '''
        /*
         * Multi-line block comment
         * describing the system
         */
        system MyApp {
            name: "My App"
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert doc.system is not None


class TestParserErrors:
    """Testes de erros de parsing."""

    def test_error_unterminated_string(self):
        """[Parser] Erro em string nao terminada."""
        source = '''
        system MyApp {
            name: "Unterminated
        }
        '''
        parser = IDLParser()

        with pytest.raises(IDLParseError) as excinfo:
            parser.parse(source)

        assert "Unterminated string" in str(excinfo.value)

    def test_error_unexpected_token(self):
        """[Parser] Erro em token inesperado."""
        source = '''
        system {
            name: "Missing ID"
        }
        '''
        parser = IDLParser()

        with pytest.raises(IDLParseError) as excinfo:
            parser.parse(source)

        assert "Expected IDENTIFIER" in str(excinfo.value)

    def test_error_unexpected_character(self):
        """[Parser] Erro em caractere inesperado."""
        source = '''
        system MyApp {
            name: "Test" @invalid
        }
        '''
        parser = IDLParser()

        with pytest.raises(IDLParseError) as excinfo:
            parser.parse(source)

        assert "Unexpected character" in str(excinfo.value)


class TestParserFullDocument:
    """Testes de parsing de documento completo."""

    def test_parse_full_document(self):
        """[Parser] Parse de documento completo."""
        source = '''
        system PetClinic {
            name: "Pet Clinic System"
            version: "1.0.0"
        }

        actors {
            human Owner {
                name: "Pet Owner"
                permissions: [read, write]
            }
            human Vet {
                name: "Veterinarian"
                permissions: [read, write, admin]
            }
        }

        entities {
            entity Pet {
                field id: uuid required unique
                field name: string required
                field type: string
                belongs_to owner -> Owner
            }
            entity Owner {
                field id: uuid required unique
                field name: string required
                has_many pets -> Pet
            }
        }

        usecases {
            usecase RegisterPet {
                name: "Register Pet"
                actor: Owner
                main_flow: [
                    1. "Owner enters pet information",
                    2. "System validates data",
                    3. "System saves pet"
                ]
            }
        }

        integrations {
            integration EmailService {
                name: "Email Service"
                type: rest_api
                protocol: https
                endpoint: "https://email.service.com"
            }
        }

        nonfunctional {
            performance ApiResponse {
                name: "API Response Time"
                target: "< 100ms"
            }
        }
        '''
        parser = IDLParser()
        doc = parser.parse(source)

        assert doc.system is not None
        assert doc.system.id == "PetClinic"

        assert len(doc.actors) == 2
        assert len(doc.entities) == 2
        assert len(doc.usecases) == 1
        assert len(doc.integrations) == 1
        assert len(doc.nonfunctional) == 1

    def test_parse_empty_document(self):
        """[Parser] Parse de documento vazio."""
        source = ''
        parser = IDLParser()
        doc = parser.parse(source)

        assert doc.system is None
        assert len(doc.actors) == 0
        assert len(doc.entities) == 0
        assert len(doc.usecases) == 0
        assert len(doc.integrations) == 0
        assert len(doc.nonfunctional) == 0
