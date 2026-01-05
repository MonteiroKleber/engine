"""Teste de regressao para mini-gramatica - Relacoes por nome de campo.

Valida que quando um campo tem o nome de outra entidade, o parser:
1. Remove o campo original
2. Cria campo <entidade>_id
3. Cria relacao many_to_one
"""

import pytest
from intake.req_analyst import (
    parse_entities,
    parse_requirements,
    extract_relations_from_fields,
    EntityDeclaration,
)


class TestRelationsByFieldname:
    """Testa criacao de relacoes quando campo eh nome de entidade."""

    def test_field_becomes_fk_id(self) -> None:
        """Campo 'tutor' em pet deve virar 'tutor_id'."""
        text = "tutores (nome, cpf); pets (nome, tutor)"
        result = parse_requirements(text)

        pet = next(e for e in result["entities"] if e["name"] == "pet")

        assert "tutor_id" in pet["fields"]
        assert "tutor" not in pet["fields"]

    def test_relation_created(self) -> None:
        """Deve criar relacao many_to_one."""
        text = "tutores (nome); pets (nome, tutor)"
        result = parse_requirements(text)

        rel = next(
            (r for r in result["relations"]
             if r["from"] == "pet" and r["to"] == "tutor"),
            None
        )

        assert rel is not None
        assert rel["type"] == "many_to_one"
        assert rel["field"] == "tutor_id"

    def test_multiple_relations_from_same_entity(self) -> None:
        """Entidade com multiplos campos-entidade deve ter multiplas relacoes."""
        text = """
        pets (nome);
        veterinarios (nome);
        atendimentos (data, pet, veterinario)
        """
        result = parse_requirements(text)

        atend = next(e for e in result["entities"] if e["name"] == "atendimento")

        # Deve ter pet_id e veterinario_id
        assert "pet_id" in atend["fields"]
        assert "veterinario_id" in atend["fields"]
        assert "pet" not in atend["fields"]
        assert "veterinario" not in atend["fields"]

        # Deve ter 2 relacoes
        atend_rels = [r for r in result["relations"] if r["from"] == "atendimento"]
        assert len(atend_rels) == 2

    def test_self_reference_not_created(self) -> None:
        """Campo com mesmo nome da entidade nao deve criar auto-relacao."""
        text = "clientes (nome, cliente_anterior)"
        result = parse_requirements(text)

        # cliente_anterior nao eh igual a "cliente", entao mantem
        cliente = next(e for e in result["entities"] if e["name"] == "cliente")
        assert "cliente_anterior" in cliente["fields"]

    def test_plural_field_recognized(self) -> None:
        """Campo no plural deve ser reconhecido como entidade."""
        text = "tutores (nome); pets (nome, tutores)"
        result = parse_requirements(text)

        pet = next(e for e in result["entities"] if e["name"] == "pet")

        # "tutores" deve ser singularizado para "tutor" e virar tutor_id
        assert "tutor_id" in pet["fields"]

    def test_nonexistent_entity_field_kept(self) -> None:
        """Campo que nao eh nome de entidade deve ser mantido."""
        text = "clientes (nome, categoria)"
        result = parse_requirements(text)

        cliente = next(e for e in result["entities"] if e["name"] == "cliente")

        # categoria nao eh entidade, deve manter
        assert "categoria" in cliente["fields"]

    def test_relation_field_has_correct_type(self) -> None:
        """Campo _id deve ter tipo uuid."""
        from intake.req_analyst import build_field_structure

        field = build_field_structure("tutor_id", is_fk=True)

        assert field["type"] == "uuid"
        assert field["required"] is True


class TestExtractRelationsFromFieldsDirect:
    """Testa extract_relations_from_fields diretamente."""

    def test_extracts_single_relation(self) -> None:
        """Deve extrair relacao simples."""
        entities = [
            EntityDeclaration("tutor", ["nome", "cpf"], "A"),
            EntityDeclaration("pet", ["nome", "tutor"], "A"),
        ]

        relations, updated_fields, optional_fields = extract_relations_from_fields(entities)

        assert len(relations) == 1
        assert relations[0]["from"] == "pet"
        assert relations[0]["to"] == "tutor"
        assert relations[0]["type"] == "many_to_one"

        # Campos atualizados
        assert "tutor_id" in updated_fields["pet"]
        assert "tutor" not in updated_fields["pet"]

    def test_extracts_multiple_relations(self) -> None:
        """Deve extrair multiplas relacoes."""
        entities = [
            EntityDeclaration("pet", ["nome"], "A"),
            EntityDeclaration("veterinario", ["nome"], "A"),
            EntityDeclaration("atendimento", ["data", "pet", "veterinario"], "A"),
        ]

        relations, updated_fields, optional_fields = extract_relations_from_fields(entities)

        assert len(relations) == 2

        # Verifica campos atualizados
        assert "pet_id" in updated_fields["atendimento"]
        assert "veterinario_id" in updated_fields["atendimento"]

    def test_no_relation_for_nonexistent_entity(self) -> None:
        """Nao deve criar relacao para entidade inexistente."""
        entities = [
            EntityDeclaration("pet", ["nome", "dono"], "A"),
        ]

        relations, updated_fields, optional_fields = extract_relations_from_fields(entities)

        # "dono" nao eh entidade, nao deve criar relacao
        assert len(relations) == 0
        assert "dono" in updated_fields["pet"]
