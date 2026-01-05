"""Testes do Contract Gate IDL v1.

Valida:
1) Contract Gate passa quando JSON esta integro
2) Contract Gate falha quando JSON e adulterado
3) IDLStore salva e carrega corretamente
4) Verificacao de integridade em lote
"""

import json
import pytest
from pathlib import Path

from idl.idl_v1 import (
    IDL_SCHEMA_VERSION,
    IDLDocument,
    IDLParser,
    SystemDefinition,
    ActorDefinition,
    ActorType,
    EntityDefinition,
    FieldDefinition,
    UseCaseDefinition,
    FlowStep,
    IntegrationDefinition,
    NFRDefinition,
    NFRType,
    compute_content_hash_sha256,
    extract_hashable_payload_from_canonical,
)
from idl.idl_store import (
    IDLStore,
    IDLContractGateError,
    parse_and_save,
)


class TestContractGatePasses:
    """Testes para Contract Gate quando JSON esta integro."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretorio de store temporario."""
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_contract_gate_passes_on_valid_save(self, temp_store):
        """[Contract Gate] Passa quando JSON salvo esta integro."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
            actors=[
                ActorDefinition(id="User", actor_type=ActorType.HUMAN, name="User"),
            ],
        )

        # Nao deve lancar excecao
        result = store.save(doc, "test_project", validate_gate=True)

        assert result is not None
        assert "json" in result
        assert "markdown" in result

        # Verificar que arquivos existem
        json_path = Path(result["json"])
        md_path = Path(result["markdown"])
        assert json_path.exists()
        assert md_path.exists()

    def test_contract_gate_passes_with_contract_notes(self, temp_store):
        """[Contract Gate] Passa com contract_notes presente."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
            contract_notes="Test note for contract gate",
        )

        # Nao deve lancar excecao
        result = store.save(doc, "test_project")

        # Verificar que contract_notes esta no JSON
        json_path = Path(result["json"])
        with open(json_path) as f:
            saved = json.load(f)

        assert "contract_notes" in saved
        assert saved["contract_notes"] == "Test note for contract gate"

    def test_contract_gate_passes_on_load(self, temp_store):
        """[Contract Gate] Passa ao carregar JSON valido."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
        )

        result = store.save(doc, "test_project")

        # Nao deve lancar excecao ao carregar
        loaded = store.load(result["json"], validate_gate=True)

        assert loaded is not None
        assert loaded["schema_version"] == IDL_SCHEMA_VERSION

    def test_contract_gate_passes_with_full_document(self, temp_store):
        """[Contract Gate] Passa com documento completo."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="PetClinic", name="Pet Clinic"),
            actors=[
                ActorDefinition(id="Owner", actor_type=ActorType.HUMAN, name="Pet Owner"),
                ActorDefinition(id="Vet", actor_type=ActorType.HUMAN, name="Veterinarian"),
            ],
            entities=[
                EntityDefinition(
                    id="Pet",
                    fields=[
                        FieldDefinition(id="id", field_type="uuid", required=True),
                        FieldDefinition(id="name", field_type="string", required=True),
                    ]
                ),
            ],
            usecases=[
                UseCaseDefinition(
                    id="RegisterPet",
                    name="Register Pet",
                    actors=["Owner"],
                    main_flow=[
                        FlowStep(number=1, description="Enter pet info"),
                        FlowStep(number=2, description="Save pet"),
                    ]
                ),
            ],
            integrations=[
                IntegrationDefinition(id="EmailAPI", name="Email Service"),
            ],
            nonfunctional=[
                NFRDefinition(id="Performance", nfr_type=NFRType.PERFORMANCE, name="Response Time"),
            ],
        )

        # Nao deve lancar excecao
        result = store.save(doc, "petclinic")

        assert result is not None


class TestContractGateFails:
    """Testes para Contract Gate quando JSON e adulterado."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretorio de store temporario."""
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_contract_gate_fails_when_system_modified(self, temp_store):
        """[Contract Gate] Falha quando system e adulterado."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test System"),
        )

        result = store.save(doc, "test_project")
        json_path = Path(result["json"])

        # Adulterar o JSON
        with open(json_path) as f:
            data = json.load(f)

        data["system"]["name"] = "Adulterado"

        with open(json_path, 'w') as f:
            json.dump(data, f)

        # Contract Gate deve falhar
        with pytest.raises(IDLContractGateError) as excinfo:
            store.load(json_path, validate_gate=True)

        assert "Contract Gate FAILED" in str(excinfo.value)
        assert "hash mismatch" in str(excinfo.value)

    def test_contract_gate_fails_when_actor_added(self, temp_store):
        """[Contract Gate] Falha quando ator e adicionado."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            actors=[
                ActorDefinition(id="User", actor_type=ActorType.HUMAN, name="User"),
            ]
        )

        result = store.save(doc, "test_project")
        json_path = Path(result["json"])

        # Adulterar o JSON
        with open(json_path) as f:
            data = json.load(f)

        data["actors"].append({
            "id": "Hacker",
            "actor_type": "human",
            "name": "Hacker",
            "description": "",
            "permissions": ["admin"],
            "authentication": "none",
        })

        with open(json_path, 'w') as f:
            json.dump(data, f)

        # Contract Gate deve falhar
        with pytest.raises(IDLContractGateError):
            store.load(json_path, validate_gate=True)

    def test_contract_gate_fails_when_entity_modified(self, temp_store):
        """[Contract Gate] Falha quando entidade e modificada."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            entities=[
                EntityDefinition(
                    id="User",
                    fields=[
                        FieldDefinition(id="id", field_type="uuid"),
                    ]
                ),
            ]
        )

        result = store.save(doc, "test_project")
        json_path = Path(result["json"])

        # Adulterar o JSON
        with open(json_path) as f:
            data = json.load(f)

        data["entities"][0]["fields"][0]["field_type"] = "string"

        with open(json_path, 'w') as f:
            json.dump(data, f)

        # Contract Gate deve falhar
        with pytest.raises(IDLContractGateError):
            store.load(json_path, validate_gate=True)

    def test_contract_gate_fails_when_hash_removed(self, temp_store):
        """[Contract Gate] Falha quando hash e removido."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        result = store.save(doc, "test_project")
        json_path = Path(result["json"])

        # Adulterar o JSON
        with open(json_path) as f:
            data = json.load(f)

        del data["content_hash_sha256"]

        with open(json_path, 'w') as f:
            json.dump(data, f)

        # Contract Gate deve falhar
        with pytest.raises(IDLContractGateError):
            store.load(json_path, validate_gate=True)

    def test_contract_gate_fails_when_hash_changed(self, temp_store):
        """[Contract Gate] Falha quando hash e alterado."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        result = store.save(doc, "test_project")
        json_path = Path(result["json"])

        # Adulterar o JSON
        with open(json_path) as f:
            data = json.load(f)

        data["content_hash_sha256"] = "0" * 64  # Hash falso

        with open(json_path, 'w') as f:
            json.dump(data, f)

        # Contract Gate deve falhar
        with pytest.raises(IDLContractGateError):
            store.load(json_path, validate_gate=True)

    def test_contract_notes_modification_fails_gate(self, temp_store):
        """[Contract Gate] Modificar contract_notes NAO falha (fora do hash)."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
            contract_notes="Original note",
        )

        result = store.save(doc, "test_project")
        json_path = Path(result["json"])

        # Modificar contract_notes
        with open(json_path) as f:
            data = json.load(f)

        data["contract_notes"] = "Modified note"

        with open(json_path, 'w') as f:
            json.dump(data, f)

        # Contract Gate NAO deve falhar (contract_notes esta fora do hash)
        loaded = store.load(json_path, validate_gate=True)
        assert loaded["contract_notes"] == "Modified note"


class TestIDLStoreOperations:
    """Testes de operacoes do IDLStore."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretorio de store temporario."""
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_list_documents_empty(self, temp_store):
        """[Store] Lista documentos em store vazio."""
        store = IDLStore(str(temp_store))

        docs = store.list_documents()

        assert docs == []

    def test_list_documents_with_files(self, temp_store):
        """[Store] Lista documentos existentes."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(system=SystemDefinition(id="Test", name="Test"))
        store.save(doc, "project1")
        store.save(doc, "project2")

        docs = store.list_documents()

        assert len(docs) == 2

    def test_list_documents_by_project(self, temp_store):
        """[Store] Lista documentos por projeto."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(system=SystemDefinition(id="Test", name="Test"))
        store.save(doc, "project1")
        store.save(doc, "project1")  # Segundo save do mesmo projeto (microsegundos diferentes)
        store.save(doc, "project2")

        project1_docs = store.list_documents("project1")
        project2_docs = store.list_documents("project2")

        assert len(project1_docs) == 2
        assert len(project2_docs) == 1

    def test_get_latest(self, temp_store):
        """[Store] Retorna documento mais recente."""
        store = IDLStore(str(temp_store))

        doc1 = IDLDocument(system=SystemDefinition(id="Test", name="Version 1"))
        store.save(doc1, "project")

        doc2 = IDLDocument(system=SystemDefinition(id="Test", name="Version 2"))
        store.save(doc2, "project")

        latest = store.get_latest("project")

        assert latest is not None
        assert latest["system"]["name"] == "Version 2"

    def test_get_latest_nonexistent(self, temp_store):
        """[Store] Retorna None para projeto inexistente."""
        store = IDLStore(str(temp_store))

        latest = store.get_latest("nonexistent")

        assert latest is None

    def test_verify_all(self, temp_store):
        """[Store] Verifica integridade de todos documentos."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(system=SystemDefinition(id="Test", name="Test"))
        result1 = store.save(doc, "project1")
        result2 = store.save(doc, "project2")

        results = store.verify_all()

        assert len(results) == 2
        assert all(v is True for v in results.values())

    def test_verify_all_detects_corruption(self, temp_store):
        """[Store] Detecta corrupcao em verificacao em lote."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(system=SystemDefinition(id="Test", name="Test"))
        result1 = store.save(doc, "project1")
        result2 = store.save(doc, "project2")

        # Corromper um arquivo
        json_path = Path(result1["json"])
        with open(json_path) as f:
            data = json.load(f)
        data["system"]["name"] = "Corrupted"
        with open(json_path, 'w') as f:
            json.dump(data, f)

        results = store.verify_all()

        assert results[result1["json"]] is False
        assert results[result2["json"]] is True

    def test_skip_contract_gate_on_save(self, temp_store):
        """[Store] Pode pular Contract Gate no save."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(system=SystemDefinition(id="Test", name="Test"))

        # Nao deve lancar excecao
        result = store.save(doc, "project", validate_gate=False)

        assert result is not None

    def test_skip_contract_gate_on_load(self, temp_store):
        """[Store] Pode pular Contract Gate no load."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(system=SystemDefinition(id="Test", name="Test"))
        result = store.save(doc, "project")

        # Corromper
        json_path = Path(result["json"])
        with open(json_path) as f:
            data = json.load(f)
        data["system"]["name"] = "Corrupted"
        with open(json_path, 'w') as f:
            json.dump(data, f)

        # Deve carregar sem validar
        loaded = store.load(json_path, validate_gate=False)

        assert loaded["system"]["name"] == "Corrupted"


class TestParseAndSaveConvenience:
    """Testes da funcao de conveniencia parse_and_save."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretorio de store temporario."""
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_parse_and_save_basic(self, temp_store):
        """[Convenience] parse_and_save funciona."""
        source = '''
        system Test {
            name: "Test System"
        }
        '''

        result = parse_and_save(source, "project", str(temp_store))

        assert result is not None
        assert "json" in result
        assert "markdown" in result

        # Verificar que arquivos existem
        assert Path(result["json"]).exists()
        assert Path(result["markdown"]).exists()

    def test_parse_and_save_with_contract_notes(self, temp_store):
        """[Convenience] parse_and_save com contract_notes."""
        source = '''
        system Test {
            name: "Test System"
        }
        '''

        result = parse_and_save(
            source, "project", str(temp_store),
            contract_notes="Note from convenience function"
        )

        # Verificar que contract_notes esta no JSON
        with open(result["json"]) as f:
            data = json.load(f)

        assert data["contract_notes"] == "Note from convenience function"


class TestContractSchema:
    """Testes do contrato e schema."""

    def test_schema_version_is_idl_v1(self):
        """[Schema] Schema version e idl.v1."""
        assert IDL_SCHEMA_VERSION == "idl.v1"

    def test_canonical_dict_has_schema_version(self):
        """[Schema] to_canonical_dict inclui schema_version."""
        doc = IDLDocument(system=SystemDefinition(id="Test", name="Test"))

        canonical = doc.to_canonical_dict()

        assert canonical["schema_version"] == "idl.v1"

    def test_hashable_dict_has_schema_version(self):
        """[Schema] to_hashable_dict inclui schema_version."""
        doc = IDLDocument(system=SystemDefinition(id="Test", name="Test"))

        hashable = doc.to_hashable_dict()

        assert hashable["schema_version"] == "idl.v1"

    def test_json_output_has_schema_version(self):
        """[Schema] to_json inclui schema_version."""
        doc = IDLDocument(system=SystemDefinition(id="Test", name="Test"))

        json_str = doc.to_json()
        data = json.loads(json_str)

        assert data["schema_version"] == "idl.v1"


class TestHashIntegrity:
    """Testes de integridade do hash."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Cria diretorio de store temporario."""
        store = tmp_path / "store"
        store.mkdir()
        return store

    def test_hash_in_saved_json_is_valid(self, temp_store):
        """[Integridade] Hash no JSON salvo e valido."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
            actors=[
                ActorDefinition(id="User", actor_type=ActorType.HUMAN, name="User"),
            ]
        )

        result = store.save(doc, "project")

        with open(result["json"]) as f:
            saved = json.load(f)

        saved_hash = saved["content_hash_sha256"]
        hashable = extract_hashable_payload_from_canonical(saved)
        recalculated = compute_content_hash_sha256(hashable)

        assert saved_hash == recalculated

    def test_hash_survives_json_roundtrip(self, temp_store):
        """[Integridade] Hash sobrevive roundtrip JSON."""
        store = IDLStore(str(temp_store))

        doc = IDLDocument(
            system=SystemDefinition(id="Test", name="Test"),
        )

        # Save
        result = store.save(doc, "project")

        # Load
        loaded = store.load(result["json"])

        # Hash deve ser identico
        original_hash = doc.to_canonical_dict()["content_hash_sha256"]
        loaded_hash = loaded["content_hash_sha256"]

        assert loaded_hash == original_hash
