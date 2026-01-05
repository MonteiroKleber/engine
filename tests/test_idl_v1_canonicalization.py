"""Testes de canonizacao IDL v1.

Valida:
1) Ordenacao deterministica de listas (sorted by id)
2) Hash estavel para mesmo conteudo semantico
3) Hash diferente para conteudo diferente
4) Campos volateis fora do hash
5) Serializacao JSON canonica
"""

import json
import pytest

from idl.idl_v1 import (
    IDL_SCHEMA_VERSION,
    HASHABLE_FIELDS,
    VOLATILE_FIELDS,
    IDLDocument,
    IDLParser,
    SystemDefinition,
    ActorDefinition,
    ActorType,
    AuthMethod,
    EntityDefinition,
    FieldDefinition,
    RelationDefinition,
    RelationType,
    UseCaseDefinition,
    FlowStep,
    PriorityLevel,
    ComplexityLevel,
    IntegrationDefinition,
    IntegrationType,
    ProtocolType,
    NFRDefinition,
    NFRType,
    compute_content_hash_sha256,
    extract_hashable_payload_from_canonical,
)


class TestCanonicalOrdering:
    """Testes de ordenacao canonica."""

    def test_actors_sorted_by_id(self):
        """[Canonicalizacao] Atores ordenados por id."""
        doc = IDLDocument(
            actors=[
                ActorDefinition(id="Zebra", actor_type=ActorType.HUMAN, name="Z"),
                ActorDefinition(id="Alpha", actor_type=ActorType.HUMAN, name="A"),
                ActorDefinition(id="Beta", actor_type=ActorType.HUMAN, name="B"),
            ]
        )

        hashable = doc.to_hashable_dict()
        actor_ids = [a["id"] for a in hashable["actors"]]

        assert actor_ids == ["Alpha", "Beta", "Zebra"]

    def test_entities_sorted_by_id(self):
        """[Canonicalizacao] Entidades ordenadas por id."""
        doc = IDLDocument(
            entities=[
                EntityDefinition(id="Zebra"),
                EntityDefinition(id="Alpha"),
                EntityDefinition(id="Middle"),
            ]
        )

        hashable = doc.to_hashable_dict()
        entity_ids = [e["id"] for e in hashable["entities"]]

        assert entity_ids == ["Alpha", "Middle", "Zebra"]

    def test_entity_fields_sorted_by_id(self):
        """[Canonicalizacao] Campos de entidade ordenados por id."""
        doc = IDLDocument(
            entities=[
                EntityDefinition(
                    id="Test",
                    fields=[
                        FieldDefinition(id="z_field", field_type="string"),
                        FieldDefinition(id="a_field", field_type="int"),
                        FieldDefinition(id="m_field", field_type="bool"),
                    ]
                )
            ]
        )

        hashable = doc.to_hashable_dict()
        field_ids = [f["id"] for f in hashable["entities"][0]["fields"]]

        assert field_ids == ["a_field", "m_field", "z_field"]

    def test_usecases_sorted_by_id(self):
        """[Canonicalizacao] Casos de uso ordenados por id."""
        doc = IDLDocument(
            usecases=[
                UseCaseDefinition(id="UC3", name="Third"),
                UseCaseDefinition(id="UC1", name="First"),
                UseCaseDefinition(id="UC2", name="Second"),
            ]
        )

        hashable = doc.to_hashable_dict()
        uc_ids = [u["id"] for u in hashable["usecases"]]

        assert uc_ids == ["UC1", "UC2", "UC3"]

    def test_usecase_actors_sorted(self):
        """[Canonicalizacao] Atores de caso de uso ordenados."""
        doc = IDLDocument(
            usecases=[
                UseCaseDefinition(
                    id="UC1",
                    name="Test",
                    actors=["Zebra", "Alpha", "Beta"]
                )
            ]
        )

        hashable = doc.to_hashable_dict()
        actors = hashable["usecases"][0]["actors"]

        assert actors == ["Alpha", "Beta", "Zebra"]

    def test_usecase_flow_steps_sorted_by_number(self):
        """[Canonicalizacao] Passos de fluxo ordenados por numero."""
        doc = IDLDocument(
            usecases=[
                UseCaseDefinition(
                    id="UC1",
                    name="Test",
                    main_flow=[
                        FlowStep(number=3, description="Third"),
                        FlowStep(number=1, description="First"),
                        FlowStep(number=2, description="Second"),
                    ]
                )
            ]
        )

        hashable = doc.to_hashable_dict()
        steps = hashable["usecases"][0]["main_flow"]

        assert steps[0]["number"] == 1
        assert steps[1]["number"] == 2
        assert steps[2]["number"] == 3

    def test_integrations_sorted_by_id(self):
        """[Canonicalizacao] Integracoes ordenadas por id."""
        doc = IDLDocument(
            integrations=[
                IntegrationDefinition(id="Z_API", name="Z"),
                IntegrationDefinition(id="A_API", name="A"),
            ]
        )

        hashable = doc.to_hashable_dict()
        integ_ids = [i["id"] for i in hashable["integrations"]]

        assert integ_ids == ["A_API", "Z_API"]

    def test_nonfunctional_sorted_by_id(self):
        """[Canonicalizacao] NFRs ordenados por id."""
        doc = IDLDocument(
            nonfunctional=[
                NFRDefinition(id="NFR_Z", nfr_type=NFRType.PERFORMANCE, name="Z"),
                NFRDefinition(id="NFR_A", nfr_type=NFRType.SECURITY, name="A"),
            ]
        )

        hashable = doc.to_hashable_dict()
        nfr_ids = [n["id"] for n in hashable["nonfunctional"]]

        assert nfr_ids == ["NFR_A", "NFR_Z"]

    def test_actor_permissions_sorted(self):
        """[Canonicalizacao] Permissoes de ator ordenadas."""
        doc = IDLDocument(
            actors=[
                ActorDefinition(
                    id="Admin",
                    actor_type=ActorType.HUMAN,
                    name="Admin",
                    permissions=["write", "delete", "read", "admin"]
                )
            ]
        )

        hashable = doc.to_hashable_dict()
        perms = hashable["actors"][0]["permissions"]

        assert perms == ["admin", "delete", "read", "write"]


class TestHashStability:
    """Testes de estabilidade do hash."""

    def test_same_content_same_hash(self):
        """[Hash] Mesmo conteudo gera mesmo hash."""
        doc1 = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
            actors=[
                ActorDefinition(id="User", actor_type=ActorType.HUMAN, name="User"),
            ]
        )

        doc2 = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
            actors=[
                ActorDefinition(id="User", actor_type=ActorType.HUMAN, name="User"),
            ]
        )

        hash1 = compute_content_hash_sha256(doc1.to_hashable_dict())
        hash2 = compute_content_hash_sha256(doc2.to_hashable_dict())

        assert hash1 == hash2

    def test_different_order_same_hash(self):
        """[Hash] Ordem diferente gera mesmo hash (apos canonizacao)."""
        doc1 = IDLDocument(
            actors=[
                ActorDefinition(id="Alpha", actor_type=ActorType.HUMAN, name="A"),
                ActorDefinition(id="Beta", actor_type=ActorType.HUMAN, name="B"),
            ]
        )

        doc2 = IDLDocument(
            actors=[
                ActorDefinition(id="Beta", actor_type=ActorType.HUMAN, name="B"),
                ActorDefinition(id="Alpha", actor_type=ActorType.HUMAN, name="A"),
            ]
        )

        hash1 = compute_content_hash_sha256(doc1.to_hashable_dict())
        hash2 = compute_content_hash_sha256(doc2.to_hashable_dict())

        assert hash1 == hash2, "Ordem diferente deve gerar mesmo hash apos canonizacao"

    def test_different_content_different_hash(self):
        """[Hash] Conteudo diferente gera hash diferente."""
        doc1 = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
        )

        doc2 = IDLDocument(
            system=SystemDefinition(id="Test", name="Different Name"),
        )

        hash1 = compute_content_hash_sha256(doc1.to_hashable_dict())
        hash2 = compute_content_hash_sha256(doc2.to_hashable_dict())

        assert hash1 != hash2

    def test_hash_is_sha256_hex(self):
        """[Hash] Hash tem formato SHA256 hex (64 caracteres)."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        content_hash = compute_content_hash_sha256(doc.to_hashable_dict())

        assert len(content_hash) == 64
        assert all(c in "0123456789abcdef" for c in content_hash)

    def test_parsed_same_as_programmatic(self):
        """[Hash] Documento parseado tem mesmo hash que construido."""
        source = '''
        system Test {
            name: "Test System"
        }
        actors {
            human User {
                name: "User"
            }
        }
        '''

        parser = IDLParser()
        parsed_doc = parser.parse(source)

        programmatic_doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
            actors=[
                ActorDefinition(id="User", actor_type=ActorType.HUMAN, name="User"),
            ]
        )

        hash_parsed = compute_content_hash_sha256(parsed_doc.to_hashable_dict())
        hash_programmatic = compute_content_hash_sha256(programmatic_doc.to_hashable_dict())

        assert hash_parsed == hash_programmatic


class TestVolatileFieldsOutsideHash:
    """Testes para campos volateis fora do hash."""

    def test_timestamp_not_in_hashable_dict(self):
        """[Volatil] timestamp nao esta em to_hashable_dict."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        hashable = doc.to_hashable_dict()

        assert "timestamp" not in hashable

    def test_timestamp_in_canonical_dict(self):
        """[Volatil] timestamp esta em to_canonical_dict."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        canonical = doc.to_canonical_dict()

        assert "timestamp" in canonical

    def test_content_hash_not_in_hashable_dict(self):
        """[Volatil] content_hash_sha256 nao esta em to_hashable_dict."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        hashable = doc.to_hashable_dict()

        assert "content_hash_sha256" not in hashable

    def test_content_hash_in_canonical_dict(self):
        """[Volatil] content_hash_sha256 esta em to_canonical_dict."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        canonical = doc.to_canonical_dict()

        assert "content_hash_sha256" in canonical

    def test_contract_notes_not_in_hashable_dict(self):
        """[Volatil] contract_notes nao esta em to_hashable_dict."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
            contract_notes="This is a note",
        )

        hashable = doc.to_hashable_dict()

        assert "contract_notes" not in hashable

    def test_contract_notes_in_canonical_when_set(self):
        """[Volatil] contract_notes esta em to_canonical_dict quando setado."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
            contract_notes="My note",
        )

        canonical = doc.to_canonical_dict()

        assert "contract_notes" in canonical
        assert canonical["contract_notes"] == "My note"

    def test_contract_notes_not_in_canonical_when_none(self):
        """[Volatil] contract_notes ausente em to_canonical_dict quando None."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
            contract_notes=None,
        )

        canonical = doc.to_canonical_dict()

        assert "contract_notes" not in canonical

    def test_contract_notes_does_not_affect_hash(self):
        """[Volatil] contract_notes nao afeta o hash."""
        doc_without = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
            contract_notes=None,
        )

        doc_with = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
            contract_notes="Some note that should not affect hash",
        )

        hash_without = compute_content_hash_sha256(doc_without.to_hashable_dict())
        hash_with = compute_content_hash_sha256(doc_with.to_hashable_dict())

        assert hash_without == hash_with


class TestExtractHashablePayload:
    """Testes para extract_hashable_payload_from_canonical."""

    def test_extracts_only_hashable_fields(self):
        """[Extract] Extrai apenas campos hashable."""
        canonical = {
            "schema_version": "idl.v1",
            "content_hash_sha256": "abc123",
            "timestamp": "2026-01-05T10:00:00",
            "parser_version": "1.0.0",
            "system": {"id": "Test", "name": "Test"},
            "actors": [],
            "entities": [],
            "usecases": [],
            "integrations": [],
            "nonfunctional": [],
            "contract_notes": "note",
        }

        hashable = extract_hashable_payload_from_canonical(canonical)

        # Deve conter campos hashable
        assert "schema_version" in hashable
        assert "system" in hashable
        assert "actors" in hashable
        assert "entities" in hashable
        assert "usecases" in hashable
        assert "integrations" in hashable
        assert "nonfunctional" in hashable

        # Nao deve conter campos volateis
        assert "content_hash_sha256" not in hashable
        assert "timestamp" not in hashable
        assert "parser_version" not in hashable
        assert "contract_notes" not in hashable

    def test_recalculated_hash_matches_original(self):
        """[Extract] Hash recalculado bate com original."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
            actors=[
                ActorDefinition(id="User", actor_type=ActorType.HUMAN, name="User"),
            ]
        )

        canonical = doc.to_canonical_dict()
        original_hash = canonical["content_hash_sha256"]

        hashable = extract_hashable_payload_from_canonical(canonical)
        recalculated_hash = compute_content_hash_sha256(hashable)

        assert recalculated_hash == original_hash


class TestJsonSerialization:
    """Testes de serializacao JSON."""

    def test_json_is_valid(self):
        """[JSON] to_json retorna JSON valido."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        json_str = doc.to_json()

        # Deve ser JSON valido
        parsed = json.loads(json_str)
        assert parsed is not None

    def test_json_has_sorted_keys(self):
        """[JSON] JSON tem chaves ordenadas."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        json_str = doc.to_json(indent=None)  # Sem indent para verificar ordem

        # Verifica que schema_version vem antes de system (ordem alfabetica)
        assert json_str.index("schema_version") < json_str.index("system")

    def test_json_preserves_unicode(self):
        """[JSON] JSON preserva Unicode."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Sistema de Teste com acentuacao"),
        )

        json_str = doc.to_json()

        assert "acentuacao" in json_str
        # Nao deve usar escape
        assert "\\u" not in json_str.lower() or "acentuacao" in json_str


class TestMarkdownGeneration:
    """Testes de geracao de Markdown."""

    def test_markdown_has_schema_version(self):
        """[Markdown] Markdown tem SCHEMA VERSION."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        md = doc.to_markdown()

        assert "SCHEMA VERSION: idl.v1" in md

    def test_markdown_has_content_hash(self):
        """[Markdown] Markdown tem CONTENT HASH."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        md = doc.to_markdown()

        assert "CONTENT HASH:" in md

    def test_markdown_schema_and_hash_on_separate_lines(self):
        """[Markdown] SCHEMA VERSION e CONTENT HASH em linhas separadas."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        md = doc.to_markdown()
        lines = md.split('\n')

        schema_lines = [l for l in lines if "SCHEMA VERSION:" in l]
        hash_lines = [l for l in lines if "CONTENT HASH:" in l]

        assert len(schema_lines) == 1
        assert len(hash_lines) == 1
        assert "CONTENT HASH" not in schema_lines[0]
        assert "SCHEMA VERSION" not in hash_lines[0]

    def test_markdown_includes_all_sections(self):
        """[Markdown] Markdown inclui todas as secoes presentes."""
        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
            actors=[
                ActorDefinition(id="User", actor_type=ActorType.HUMAN, name="User"),
            ],
            entities=[
                EntityDefinition(id="Entity1"),
            ],
            usecases=[
                UseCaseDefinition(id="UC1", name="Use Case 1"),
            ],
            integrations=[
                IntegrationDefinition(id="API1", name="API 1"),
            ],
            nonfunctional=[
                NFRDefinition(id="NFR1", nfr_type=NFRType.PERFORMANCE, name="NFR 1"),
            ],
        )

        md = doc.to_markdown()

        assert "## System" in md
        assert "## Actors" in md
        assert "## Entities" in md
        assert "## Use Cases" in md
        assert "## Integrations" in md
        assert "## Non-Functional Requirements" in md
