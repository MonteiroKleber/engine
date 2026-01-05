"""Teste de regressao para mini-gramatica - Caso Petclinic completo.

Valida que o parser extrai corretamente as 7 entidades do petclinic
com seus campos e relacoes.
"""

import pytest
from intake.req_analyst import (
    parse_entities,
    parse_requirements,
    extract_relations_from_fields,
    RequirementsAnalyst,
)


# Input padrao do petclinic
PETCLINIC_INPUT = """
tutores (nome, cpf, telefone, email, endereco);
pets (nome, especie, raca, sexo, data nascimento, peso, observacoes, tutor);
veterinarios (nome, crmv, especialidade, telefone, email);
atendimentos (data/hora, pet, veterinario, motivo, anotacoes, diagnostico, prescricao, status);
vacinas (pet, vacina, data aplicacao, proxima dose, lote, observacoes);
agendamentos (data/hora, pet, veterinario, servico, status);
pagamentos (atendimento, forma pagamento, valor, status, data)
"""


class TestPetclinicEntities:
    """Testa extracao de entidades do Petclinic."""

    def test_extracts_7_entities(self) -> None:
        """Deve extrair exatamente 7 entidades."""
        entities, warnings = parse_entities(PETCLINIC_INPUT)
        entity_names = [e.name for e in entities]

        assert len(entities) == 7
        assert "tutor" in entity_names
        assert "pet" in entity_names
        assert "veterinario" in entity_names
        assert "atendimento" in entity_names
        assert "vacina" in entity_names
        assert "agendamento" in entity_names
        assert "pagamento" in entity_names

    def test_tutor_fields(self) -> None:
        """Tutor deve ter campos corretos."""
        entities, _ = parse_entities(PETCLINIC_INPUT)
        tutor = next(e for e in entities if e.name == "tutor")

        expected = ["nome", "cpf", "telefone", "email", "endereco"]
        assert tutor.fields == expected

    def test_pet_fields(self) -> None:
        """Pet deve ter campos corretos (tutor vira tutor_id via relacao)."""
        result = parse_requirements(PETCLINIC_INPUT)
        pet = next(e for e in result["entities"] if e["name"] == "pet")

        # tutor deve virar tutor_id
        assert "tutor_id" in pet["fields"]
        assert "tutor" not in pet["fields"]
        assert "nome" in pet["fields"]
        assert "especie" in pet["fields"]
        assert "raca" in pet["fields"]
        assert "sexo" in pet["fields"]
        assert "data_nascimento" in pet["fields"]
        assert "peso" in pet["fields"]
        assert "observacoes" in pet["fields"]

    def test_veterinario_fields(self) -> None:
        """Veterinario deve ter campos corretos."""
        entities, _ = parse_entities(PETCLINIC_INPUT)
        vet = next(e for e in entities if e.name == "veterinario")

        expected = ["nome", "crmv", "especialidade", "telefone", "email"]
        assert vet.fields == expected

    def test_atendimento_fields_data_hora_split(self) -> None:
        """Atendimento deve ter data e hora separados (data/hora -> data, hora)."""
        result = parse_requirements(PETCLINIC_INPUT)
        atend = next(e for e in result["entities"] if e["name"] == "atendimento")

        # data/hora deve virar data, hora
        assert "data" in atend["fields"]
        assert "hora" in atend["fields"]
        # pet e veterinario viram _id
        assert "pet_id" in atend["fields"]
        assert "veterinario_id" in atend["fields"]
        assert "motivo" in atend["fields"]
        assert "anotacoes" in atend["fields"]
        assert "diagnostico" in atend["fields"]
        assert "prescricao" in atend["fields"]
        assert "status" in atend["fields"]

    def test_vacina_fields(self) -> None:
        """Vacina deve ter campos corretos."""
        result = parse_requirements(PETCLINIC_INPUT)
        vacina = next(e for e in result["entities"] if e["name"] == "vacina")

        assert "pet_id" in vacina["fields"]
        assert "vacina" in vacina["fields"]
        assert "data_aplicacao" in vacina["fields"]
        assert "proxima_dose" in vacina["fields"]
        assert "lote" in vacina["fields"]
        assert "observacoes" in vacina["fields"]

    def test_agendamento_fields(self) -> None:
        """Agendamento deve ter campos corretos."""
        result = parse_requirements(PETCLINIC_INPUT)
        agend = next(e for e in result["entities"] if e["name"] == "agendamento")

        assert "data" in agend["fields"]
        assert "hora" in agend["fields"]
        assert "pet_id" in agend["fields"]
        assert "veterinario_id" in agend["fields"]
        assert "servico" in agend["fields"]
        assert "status" in agend["fields"]

    def test_pagamento_fields(self) -> None:
        """Pagamento deve ter campos corretos."""
        result = parse_requirements(PETCLINIC_INPUT)
        pag = next(e for e in result["entities"] if e["name"] == "pagamento")

        assert "atendimento_id" in pag["fields"]
        assert "forma_pagamento" in pag["fields"]
        assert "valor" in pag["fields"]
        assert "status" in pag["fields"]
        assert "data" in pag["fields"]


class TestPetclinicRelations:
    """Testa extracao de relacoes do Petclinic."""

    def test_pet_tutor_relation(self) -> None:
        """Pet deve ter relacao many_to_one com tutor."""
        result = parse_requirements(PETCLINIC_INPUT)

        rel = next(
            (r for r in result["relations"]
             if r["from"] == "pet" and r["to"] == "tutor"),
            None
        )
        assert rel is not None
        assert rel["type"] == "many_to_one"
        assert rel["field"] == "tutor_id"

    def test_atendimento_pet_relation(self) -> None:
        """Atendimento deve ter relacao many_to_one com pet."""
        result = parse_requirements(PETCLINIC_INPUT)

        rel = next(
            (r for r in result["relations"]
             if r["from"] == "atendimento" and r["to"] == "pet"),
            None
        )
        assert rel is not None
        assert rel["type"] == "many_to_one"
        assert rel["field"] == "pet_id"

    def test_atendimento_veterinario_relation(self) -> None:
        """Atendimento deve ter relacao many_to_one com veterinario."""
        result = parse_requirements(PETCLINIC_INPUT)

        rel = next(
            (r for r in result["relations"]
             if r["from"] == "atendimento" and r["to"] == "veterinario"),
            None
        )
        assert rel is not None
        assert rel["type"] == "many_to_one"
        assert rel["field"] == "veterinario_id"

    def test_vacina_pet_relation(self) -> None:
        """Vacina deve ter relacao many_to_one com pet."""
        result = parse_requirements(PETCLINIC_INPUT)

        rel = next(
            (r for r in result["relations"]
             if r["from"] == "vacina" and r["to"] == "pet"),
            None
        )
        assert rel is not None
        assert rel["type"] == "many_to_one"

    def test_agendamento_pet_relation(self) -> None:
        """Agendamento deve ter relacao many_to_one com pet."""
        result = parse_requirements(PETCLINIC_INPUT)

        rel = next(
            (r for r in result["relations"]
             if r["from"] == "agendamento" and r["to"] == "pet"),
            None
        )
        assert rel is not None
        assert rel["type"] == "many_to_one"

    def test_agendamento_veterinario_relation(self) -> None:
        """Agendamento deve ter relacao many_to_one com veterinario."""
        result = parse_requirements(PETCLINIC_INPUT)

        rel = next(
            (r for r in result["relations"]
             if r["from"] == "agendamento" and r["to"] == "veterinario"),
            None
        )
        assert rel is not None
        assert rel["type"] == "many_to_one"

    def test_pagamento_atendimento_relation(self) -> None:
        """Pagamento deve ter relacao many_to_one com atendimento."""
        result = parse_requirements(PETCLINIC_INPUT)

        rel = next(
            (r for r in result["relations"]
             if r["from"] == "pagamento" and r["to"] == "atendimento"),
            None
        )
        assert rel is not None
        assert rel["type"] == "many_to_one"
        assert rel["field"] == "atendimento_id"

    def test_total_relations_count(self) -> None:
        """Deve ter 7 relacoes no total."""
        result = parse_requirements(PETCLINIC_INPUT)

        # pet->tutor, atend->pet, atend->vet, vacina->pet,
        # agend->pet, agend->vet, pag->atend
        assert len(result["relations"]) == 7


class TestPetclinicSRSGeneration:
    """Testa geracao de SRS para Petclinic."""

    def test_srs_has_7_entities_in_data_requirements(self) -> None:
        """SRS deve ter 7 entidades em data_requirements."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": PETCLINIC_INPUT},
            "Sistema Petclinic"
        )

        assert len(srs["data_requirements"]) == 7

    def test_srs_has_relations(self) -> None:
        """SRS deve ter relacoes."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": PETCLINIC_INPUT},
            "Sistema Petclinic"
        )

        assert "relations" in srs
        assert len(srs["relations"]) == 7

    def test_srs_generation_mode_is_minigrammar_v2(self) -> None:
        """SRS deve ter generation_mode MINIGRAMMAR_V2."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": PETCLINIC_INPUT},
            "Sistema Petclinic"
        )

        assert srs["metadata"]["generation_mode"] == "MINIGRAMMAR_V2"

    def test_srs_has_crud_requirements_for_each_entity(self) -> None:
        """SRS deve ter 5 requisitos CRUD por entidade (35 total)."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": PETCLINIC_INPUT},
            "Sistema Petclinic"
        )

        # 7 entidades x 5 operacoes CRUD = 35
        assert len(srs["requirements"]) == 35

    def test_srs_pet_has_tutor_id_field(self) -> None:
        """SRS pet entity deve ter tutor_id, nao tutor."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": PETCLINIC_INPUT},
            "Sistema Petclinic"
        )

        pet_req = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "pet"
        )
        field_names = [f["name"] for f in pet_req["fields"]]

        assert "tutor_id" in field_names
        assert "tutor" not in field_names
