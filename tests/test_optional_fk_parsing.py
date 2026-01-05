"""Testes para parsing de FKs opcionais v2.

Testa os marcadores de opcionalidade:
- "opcional"
- "optional"
- "pode ser vazio"
- "nao obrigatorio"

E a geracao de campos nullable no SRS.
"""

import pytest
from intake.req_analyst import (
    is_optional_fk,
    parse_field_with_optionality,
    extract_relations_from_fields,
    build_field_structure,
    parse_requirements,
    RequirementsAnalyst,
    EntityDeclaration,
)


# Input com FK opcional
INPUT_WITH_OPTIONAL_FK = """
tutores (nome, cpf, telefone);
pets (nome, especie, tutor);
veterinarios (nome, crmv);
agendamentos (data, pet, veterinario opcional)
"""


class TestIsOptionalFK:
    """Testa deteccao de FK opcional."""

    def test_opcional_marker(self) -> None:
        """Deve detectar 'opcional'."""
        assert is_optional_fk("veterinario opcional") is True

    def test_optional_marker(self) -> None:
        """Deve detectar 'optional'."""
        assert is_optional_fk("veterinario optional") is True

    def test_pode_ser_vazio_marker(self) -> None:
        """Deve detectar 'pode ser vazio'."""
        assert is_optional_fk("veterinario pode ser vazio") is True

    def test_nao_obrigatorio_marker(self) -> None:
        """Deve detectar 'nao obrigatorio'."""
        assert is_optional_fk("veterinario nao obrigatorio") is True

    def test_regular_field_not_optional(self) -> None:
        """Campo normal nao deve ser opcional."""
        assert is_optional_fk("veterinario") is False
        assert is_optional_fk("nome") is False
        assert is_optional_fk("data") is False

    def test_ignores_case(self) -> None:
        """Deve ignorar case."""
        assert is_optional_fk("VETERINARIO OPCIONAL") is True
        assert is_optional_fk("Veterinario Optional") is True

    def test_handles_accents(self) -> None:
        """Deve funcionar com acentos."""
        assert is_optional_fk("veterinário opcional") is True
        assert is_optional_fk("não obrigatório") is True


class TestParseFieldWithOptionality:
    """Testa parsing de campo com opcionalidade."""

    def test_extracts_name_and_optional_true(self) -> None:
        """Deve extrair nome e opcional=True."""
        name, is_optional = parse_field_with_optionality("veterinario opcional")

        assert name == "veterinario"
        assert is_optional is True

    def test_extracts_name_and_optional_false(self) -> None:
        """Deve extrair nome e opcional=False."""
        name, is_optional = parse_field_with_optionality("veterinario")

        assert name == "veterinario"
        assert is_optional is False

    def test_removes_marker_from_name(self) -> None:
        """Deve remover marcador do nome."""
        name, _ = parse_field_with_optionality("cliente pode ser vazio")
        assert name == "cliente"
        assert "pode" not in name
        assert "vazio" not in name

    def test_handles_complex_marker(self) -> None:
        """Deve lidar com marcadores complexos."""
        name, is_optional = parse_field_with_optionality("fornecedor nao obrigatorio")

        assert name == "fornecedor"
        assert is_optional is True

    def test_preserves_snake_case(self) -> None:
        """Deve manter snake_case."""
        name, _ = parse_field_with_optionality("data nascimento opcional")
        assert name == "data_nascimento"


class TestExtractRelationsWithOptionality:
    """Testa extracao de relacoes com opcionalidade."""

    def test_optional_relation_has_optional_flag(self) -> None:
        """Relacao opcional deve ter flag optional=True."""
        entities = [
            EntityDeclaration("pet", ["nome"], "A"),
            EntityDeclaration("veterinario", ["nome"], "A"),
            EntityDeclaration("agendamento", ["data", "pet", "veterinario opcional"], "A"),
        ]

        relations, updated_fields, optional_fields = extract_relations_from_fields(entities)

        # Encontrar relacao veterinario
        vet_rel = next(r for r in relations if r["to"] == "veterinario")
        pet_rel = next(r for r in relations if r["to"] == "pet")

        # veterinario eh opcional, pet nao eh
        assert vet_rel["optional"] is True
        assert pet_rel["optional"] is False

    def test_optional_fk_in_updated_fields(self) -> None:
        """Campo FK opcional deve estar em optional_fields."""
        entities = [
            EntityDeclaration("veterinario", ["nome"], "A"),
            EntityDeclaration("agendamento", ["data", "veterinario opcional"], "A"),
        ]

        relations, updated_fields, optional_fields = extract_relations_from_fields(entities)

        # veterinario_id deve estar marcado como opcional
        assert "veterinario_id" in optional_fields["agendamento"]
        assert optional_fields["agendamento"]["veterinario_id"] is True

    def test_required_fk_not_in_optional_fields(self) -> None:
        """Campo FK obrigatorio nao deve ter opcionalidade."""
        entities = [
            EntityDeclaration("tutor", ["nome"], "A"),
            EntityDeclaration("pet", ["nome", "tutor"], "A"),
        ]

        relations, updated_fields, optional_fields = extract_relations_from_fields(entities)

        # tutor_id existe mas nao eh opcional
        assert "tutor_id" not in optional_fields.get("pet", {}) or \
               optional_fields["pet"].get("tutor_id") is False


class TestBuildFieldStructureWithOptionality:
    """Testa construcao de campo com nullable."""

    def test_optional_fk_has_nullable_true(self) -> None:
        """FK opcional deve ter nullable=True."""
        field = build_field_structure("veterinario_id", is_fk=True, is_optional=True)

        assert field["nullable"] is True
        assert field["required"] is False

    def test_required_fk_has_nullable_false(self) -> None:
        """FK obrigatoria deve ter nullable=False (padrao)."""
        field = build_field_structure("tutor_id", is_fk=True, is_optional=False)

        assert field.get("nullable", False) is False
        assert field["required"] is True

    def test_optional_regular_field(self) -> None:
        """Campo regular opcional deve ter nullable=True."""
        field = build_field_structure("observacao", is_fk=False, is_optional=True)

        assert field["nullable"] is True
        assert field["required"] is False


class TestParseRequirementsWithOptionalFK:
    """Testa parse_requirements com FK opcional."""

    def test_entity_has_optional_fields_map(self) -> None:
        """Entidade deve ter mapa de campos opcionais."""
        result = parse_requirements(INPUT_WITH_OPTIONAL_FK)

        # Encontrar agendamento
        agendamento = next(e for e in result["entities"] if e["name"] == "agendamento")

        assert "optional_fields" in agendamento
        assert "veterinario_id" in agendamento["optional_fields"]
        assert agendamento["optional_fields"]["veterinario_id"] is True

    def test_relation_has_optional_flag(self) -> None:
        """Relacao deve ter flag optional."""
        result = parse_requirements(INPUT_WITH_OPTIONAL_FK)

        # Encontrar relacao agendamento -> veterinario
        rel = next(
            r for r in result["relations"]
            if r["from"] == "agendamento" and r["to"] == "veterinario"
        )

        assert rel["optional"] is True

    def test_required_relation_has_optional_false(self) -> None:
        """Relacao obrigatoria deve ter optional=False."""
        result = parse_requirements(INPUT_WITH_OPTIONAL_FK)

        # Encontrar relacao agendamento -> pet
        rel = next(
            r for r in result["relations"]
            if r["from"] == "agendamento" and r["to"] == "pet"
        )

        assert rel["optional"] is False


class TestSRSWithOptionalFK:
    """Testa SRS gerado com FK opcional."""

    def test_data_requirements_has_nullable_field(self) -> None:
        """data_requirements deve ter campo nullable."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": INPUT_WITH_OPTIONAL_FK},
            "Sistema com FK Opcional"
        )

        # Encontrar agendamento em data_requirements
        agendamento_req = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "agendamento"
        )

        # Encontrar campo veterinario_id
        vet_field = next(
            f for f in agendamento_req["fields"]
            if f["name"] == "veterinario_id"
        )

        assert vet_field["nullable"] is True
        assert vet_field["required"] is False

    def test_relations_have_optional_flag(self) -> None:
        """Relations no SRS devem ter flag optional."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": INPUT_WITH_OPTIONAL_FK},
            "Sistema com FK Opcional"
        )

        # Encontrar relacao para veterinario
        vet_rel = next(
            r for r in srs["relations"]
            if r.get("to") == "veterinario"
        )

        assert "optional" in vet_rel
        assert vet_rel["optional"] is True


class TestMultipleOptionalFKs:
    """Testa multiplas FKs opcionais."""

    def test_multiple_optional_fks_in_same_entity(self) -> None:
        """Deve suportar multiplas FKs opcionais na mesma entidade."""
        text = """
        clientes (nome);
        vendedores (nome);
        fornecedores (nome);
        produtos (nome, cliente opcional, vendedor opcional, fornecedor)
        """
        result = parse_requirements(text)

        # Encontrar produto
        produto = next(e for e in result["entities"] if e["name"] == "produto")

        # cliente e vendedor sao opcionais, fornecedor nao
        assert produto["optional_fields"].get("cliente_id") is True
        assert produto["optional_fields"].get("vendedor_id") is True
        assert produto["optional_fields"].get("fornecedor_id", False) is False

    def test_all_fks_optional(self) -> None:
        """Deve suportar todas as FKs opcionais."""
        text = """
        categoria (nome);
        marca (nome);
        produto (nome, categoria opcional, marca opcional)
        """
        result = parse_requirements(text)

        produto = next(e for e in result["entities"] if e["name"] == "produto")

        assert produto["optional_fields"].get("categoria_id") is True
        assert produto["optional_fields"].get("marca_id") is True


class TestEdgeCases:
    """Testa casos de borda."""

    def test_optional_on_nonexistent_entity_kept_as_field(self) -> None:
        """FK opcional para entidade inexistente deve manter campo."""
        text = "produtos (nome, categoria opcional)"
        result = parse_requirements(text)

        produto = next(e for e in result["entities"] if e["name"] == "produto")

        # "categoria" nao eh entidade, deve manter como campo normal
        assert "categoria" in produto["fields"]
        # Sem _id pois nao eh entidade
        assert "categoria_id" not in produto["fields"]

    def test_optional_marker_in_middle_of_field_name(self) -> None:
        """Marcador no meio do nome nao deve afetar."""
        text = "produtos (nome_opcional_field)"
        result = parse_requirements(text)

        produto = next(e for e in result["entities"] if e["name"] == "produto")

        # Campo deve ser parseado normalmente
        # (nao deve interpretar "opcional" no meio do nome)
        assert len(produto["fields"]) == 1
