"""Testes para geracao de endpoints de busca no SRS/IR.

Verifica que o sistema gera estrutura correta para:
- Endpoints de busca por entidade
- Query params para campos buscaveis
- Relacoes com optional flag para joins
"""

import pytest
from intake.req_analyst import (
    RequirementsAnalyst,
    parse_requirements,
    infer_field_type,
)


# Input para testes de busca
SEARCH_INPUT = """
tutores (nome, cpf, email, telefone);
pets (nome, especie, raca, tutor);
veterinarios (nome, crmv, especialidade);
atendimentos (data, pet, veterinario, observacoes)
"""


class TestSearchableFields:
    """Testa campos buscaveis no SRS."""

    def test_string_fields_are_searchable(self) -> None:
        """Campos string devem ser buscaveis."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        # Encontrar tutor
        tutor_dr = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "tutor"
        )

        # nome e email sao strings
        nome_field = next(f for f in tutor_dr["fields"] if f["name"] == "nome")
        email_field = next(f for f in tutor_dr["fields"] if f["name"] == "email")

        assert nome_field["type"] == "string"
        assert email_field["type"] == "string"

    def test_cpf_is_string_and_unique(self) -> None:
        """CPF deve ser string e unique."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        tutor_dr = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "tutor"
        )

        cpf_field = next(f for f in tutor_dr["fields"] if f["name"] == "cpf")

        assert cpf_field["type"] == "string"
        assert cpf_field.get("unique") is True

    def test_date_fields_for_range_search(self) -> None:
        """Campos de data devem ser tipo date."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        atendimento_dr = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "atendimento"
        )

        data_field = next(f for f in atendimento_dr["fields"] if f["name"] == "data")

        assert data_field["type"] == "date"


class TestInferFieldType:
    """Testa inferencia de tipos de campo."""

    def test_data_is_date(self) -> None:
        """Campo 'data' deve ser tipo date."""
        field_type, required, unique = infer_field_type("data")
        assert field_type == "date"

    def test_email_is_string_unique(self) -> None:
        """Campo 'email' deve ser string unique."""
        field_type, required, unique = infer_field_type("email")
        assert field_type == "string"
        assert unique is True

    def test_cpf_is_string_unique(self) -> None:
        """Campo 'cpf' deve ser string unique."""
        field_type, required, unique = infer_field_type("cpf")
        assert field_type == "string"
        assert unique is True

    def test_cnpj_is_string_unique(self) -> None:
        """Campo 'cnpj' deve ser string unique."""
        field_type, required, unique = infer_field_type("cnpj")
        assert field_type == "string"
        assert unique is True

    def test_valor_is_decimal(self) -> None:
        """Campo 'valor' deve ser decimal."""
        field_type, required, unique = infer_field_type("valor")
        assert field_type == "decimal"

    def test_preco_is_decimal(self) -> None:
        """Campo 'preco' deve ser decimal."""
        field_type, required, unique = infer_field_type("preco")
        assert field_type == "decimal"

    def test_quantidade_is_integer(self) -> None:
        """Campo 'quantidade' deve ser integer."""
        field_type, required, unique = infer_field_type("quantidade")
        assert field_type == "integer"

    def test_ativo_is_boolean(self) -> None:
        """Campo 'ativo' deve ser boolean."""
        field_type, required, unique = infer_field_type("ativo")
        assert field_type == "boolean"

    def test_telefone_is_string_not_required(self) -> None:
        """Campo 'telefone' deve ser string opcional."""
        field_type, required, unique = infer_field_type("telefone")
        assert field_type == "string"
        assert required is False

    def test_nome_is_string_required(self) -> None:
        """Campo 'nome' deve ser string required."""
        field_type, required, unique = infer_field_type("nome")
        assert field_type == "string"
        assert required is True


class TestRelationsForJoins:
    """Testa relacoes para joins em buscas."""

    def test_relations_have_from_and_to(self) -> None:
        """Relacoes devem ter from e to."""
        result = parse_requirements(SEARCH_INPUT)

        for relation in result["relations"]:
            assert "from" in relation
            assert "to" in relation
            assert "type" in relation

    def test_relations_have_field_name(self) -> None:
        """Relacoes devem ter campo FK."""
        result = parse_requirements(SEARCH_INPUT)

        for relation in result["relations"]:
            assert "field" in relation
            assert relation["field"].endswith("_id")

    def test_relation_type_is_many_to_one(self) -> None:
        """Relacoes devem ser many_to_one."""
        result = parse_requirements(SEARCH_INPUT)

        # Todas as relacoes neste input sao many_to_one
        for relation in result["relations"]:
            assert relation["type"] == "many_to_one"


class TestSearchWithOptionalFK:
    """Testa busca com FK opcional."""

    def test_optional_fk_allows_null_in_search(self) -> None:
        """FK opcional deve permitir NULL em busca."""
        input_with_optional = """
        tutores (nome);
        pets (nome, tutor opcional)
        """
        result = parse_requirements(input_with_optional)

        # Encontrar relacao pet -> tutor
        rel = next(r for r in result["relations"] if r["to"] == "tutor")

        assert rel["optional"] is True

    def test_srs_optional_fk_is_nullable(self) -> None:
        """FK opcional no SRS deve ser nullable."""
        input_with_optional = """
        tutores (nome);
        pets (nome, tutor opcional)
        """
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": input_with_optional}, "Sistema")

        pet_dr = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "pet"
        )

        tutor_id_field = next(
            f for f in pet_dr["fields"]
            if f["name"] == "tutor_id"
        )

        assert tutor_id_field["nullable"] is True


class TestWorkflowEndpoints:
    """Testa endpoints de workflow."""

    def test_workflow_has_endpoint(self) -> None:
        """Workflow deve ter endpoint."""
        input_with_workflow = """
        agendamentos (data);
        atendimentos (data)

        Regras:
        agendamento pode virar atendimento
        """
        result = parse_requirements(input_with_workflow)

        assert len(result["workflows"]) == 1

        workflow = result["workflows"][0]
        assert "endpoint" in workflow
        assert "/convert-to-" in workflow["endpoint"]

    def test_workflow_endpoint_format(self) -> None:
        """Endpoint de workflow deve ter formato correto."""
        input_with_workflow = """
        orcamentos (valor);
        vendas (valor)

        Regras:
        orcamento pode virar venda
        """
        result = parse_requirements(input_with_workflow)

        workflow = result["workflows"][0]

        # Formato: /api/{source}/{id}/convert-to-{target}
        assert workflow["endpoint"] == "/api/orcamento/{id}/convert-to-venda"

    def test_srs_has_workflows_array(self) -> None:
        """SRS deve ter array de workflows."""
        input_with_workflow = """
        leads (nome);
        clientes (nome)

        Regras:
        lead pode virar cliente
        """
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": input_with_workflow}, "Sistema")

        assert "workflows" in srs
        assert len(srs["workflows"]) == 1
        assert srs["workflows"][0]["source"] == "lead"
        assert srs["workflows"][0]["target"] == "cliente"


class TestSRSStructureForSearch:
    """Testa estrutura do SRS para implementacao de busca."""

    def test_srs_has_data_requirements(self) -> None:
        """SRS deve ter data_requirements."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        assert "data_requirements" in srs
        assert len(srs["data_requirements"]) == 4

    def test_srs_has_relations(self) -> None:
        """SRS deve ter relations."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        assert "relations" in srs
        assert len(srs["relations"]) > 0

    def test_srs_has_business_rules(self) -> None:
        """SRS deve ter business_rules."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        assert "business_rules" in srs
        # Sem bloco de regras, deve ser vazio
        assert len(srs["business_rules"]) == 0

    def test_srs_has_workflows(self) -> None:
        """SRS deve ter workflows."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        assert "workflows" in srs
        # Sem bloco de regras, deve ser vazio
        assert len(srs["workflows"]) == 0


class TestComplexSearchScenarios:
    """Testa cenarios complexos de busca."""

    def test_entity_with_multiple_searchable_fields(self) -> None:
        """Entidade com varios campos buscaveis."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        tutor_dr = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "tutor"
        )

        # Tutor tem nome, cpf, email, telefone
        assert len(tutor_dr["fields"]) == 4

        # Todos devem ter tipo
        for field in tutor_dr["fields"]:
            assert "type" in field

    def test_entity_with_fk_and_regular_fields(self) -> None:
        """Entidade com FK e campos normais."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        pet_dr = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "pet"
        )

        field_names = [f["name"] for f in pet_dr["fields"]]

        # Deve ter campos normais
        assert "nome" in field_names
        assert "especie" in field_names
        assert "raca" in field_names

        # Deve ter FK
        assert "tutor_id" in field_names

    def test_fk_field_is_uuid_type(self) -> None:
        """Campo FK deve ser tipo uuid."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SEARCH_INPUT}, "Sistema")

        pet_dr = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "pet"
        )

        tutor_id_field = next(
            f for f in pet_dr["fields"]
            if f["name"] == "tutor_id"
        )

        assert tutor_id_field["type"] == "uuid"
