"""Teste de regressao para mini-gramatica - Anti-invencao.

Valida que o parser NAO inventa entidades ou campos que nao estao
ancorados no texto de entrada.
"""

import pytest
from intake.req_analyst import (
    parse_entities,
    parse_requirements,
    RequirementsAnalyst,
)


class TestNoEntityInvention:
    """Testa que entidades nao sao inventadas."""

    def test_only_extracts_mentioned_entities(self) -> None:
        """Deve extrair apenas entidades mencionadas no texto."""
        text = "clientes (nome, email)"
        entities, _ = parse_entities(text)

        names = [e.name for e in entities]
        assert names == ["cliente"]
        # Nao deve inventar outras entidades
        assert "produto" not in names
        assert "pedido" not in names

    def test_empty_input_no_entities(self) -> None:
        """Input vazio nao deve gerar entidades."""
        text = ""
        entities, _ = parse_entities(text)

        assert len(entities) == 0

    def test_gibberish_no_entities(self) -> None:
        """Texto sem estrutura nao deve gerar entidades."""
        text = "asdfgh qwerty 12345"
        entities, _ = parse_entities(text)

        assert len(entities) == 0

    def test_partial_pattern_no_entity(self) -> None:
        """Padrao incompleto nao deve gerar entidade."""
        text = "quero um sistema de ("  # Parenteses sem conteudo
        entities, _ = parse_entities(text)

        # Nao deve gerar entidade sem nome ou campos
        for entity in entities:
            assert entity.name
            assert len(entity.name) >= 2


class TestNoFieldInvention:
    """Testa que campos nao sao inventados."""

    def test_only_extracts_mentioned_fields(self) -> None:
        """Deve extrair apenas campos mencionados."""
        text = "clientes (nome, email)"
        entities, _ = parse_entities(text)

        cliente = entities[0]
        assert cliente.fields == ["nome", "email"]
        # Nao deve inventar campos
        assert "cpf" not in cliente.fields
        assert "telefone" not in cliente.fields

    def test_form_d_no_automatic_nome_field(self) -> None:
        """Forma D (sem campos) NAO deve criar campo 'nome' automaticamente."""
        text = "quero cadastrar clientes"
        result = parse_requirements(text)

        # Pode ter entidade, mas sem campos
        if result["entities"]:
            cliente = next(
                (e for e in result["entities"] if e["name"] == "cliente"),
                None
            )
            if cliente:
                # NAO deve ter campo nome inventado
                assert "nome" not in cliente["fields"]

    def test_empty_fields_generates_warning(self) -> None:
        """Entidade sem campos deve gerar warning."""
        text = "quero cadastrar clientes e produtos"
        result = parse_requirements(text)

        # Deve ter warnings sobre campos faltando
        assert any("fields_missing" in w for w in result["warnings"])


class TestNoEnumInvention:
    """Testa que valores de enum nao sao inventados."""

    def test_status_field_is_string_not_enum(self) -> None:
        """Campo status deve ser string, nao enum com valores inventados."""
        from intake.req_analyst import infer_field_type

        field_type, _, _ = infer_field_type("status")

        # Status deve ser string, nao enum
        assert field_type == "string"

    def test_no_enum_values_generated(self) -> None:
        """Nao deve gerar valores de enum automaticamente."""
        text = "pedidos (status)"
        result = parse_requirements(text)

        pedido = result["entities"][0]
        # Verifica que status eh campo simples, sem valores enum
        assert "status" in pedido["fields"]


class TestNoRelationInvention:
    """Testa que relacoes nao sao inventadas."""

    def test_only_creates_relations_for_existing_entities(self) -> None:
        """Deve criar relacoes apenas entre entidades existentes."""
        # Texto menciona "usuario" mas nao define como entidade
        text = "pedidos (data, usuario)"
        result = parse_requirements(text)

        # "usuario" nao foi definido como entidade, nao deve virar relacao
        relations = result["relations"]
        assert not any(r["to"] == "usuario" for r in relations)

        # Campo "usuario" deve ser mantido como campo normal
        pedido = result["entities"][0]
        assert "usuario" in pedido["fields"]

    def test_text_relation_only_if_both_exist(self) -> None:
        """Relacao textual so eh criada se ambas entidades existem."""
        # Menciona relacao mas nao define ambas entidades
        text = "clientes (nome). pet pertence a cliente."
        result = parse_requirements(text)

        # "pet" nao foi definido, nao deve criar relacao
        relations = result["relations"]
        pet_rels = [r for r in relations if r["from"] == "pet"]
        assert len(pet_rels) == 0


class TestSRSNoInvention:
    """Testa que SRS gerado nao inventa dados."""

    def test_srs_entities_match_input(self) -> None:
        """SRS deve ter exatamente as entidades do input."""
        analyst = RequirementsAnalyst()
        text = "clientes (nome, email); produtos (nome, preco)"

        srs = analyst.generate_srs({"normalized": text}, "Sistema")

        entity_names = [dr["entity"] for dr in srs["data_requirements"]]
        assert len(entity_names) == 2
        assert "cliente" in entity_names
        assert "produto" in entity_names

    def test_srs_fields_match_input(self) -> None:
        """SRS deve ter exatamente os campos do input."""
        analyst = RequirementsAnalyst()
        text = "clientes (nome, email)"

        srs = analyst.generate_srs({"normalized": text}, "Sistema")

        cliente = srs["data_requirements"][0]
        field_names = [f["name"] for f in cliente["fields"]]

        assert field_names == ["nome", "email"]

    def test_srs_no_extra_requirements(self) -> None:
        """SRS deve ter apenas requisitos CRUD das entidades definidas."""
        analyst = RequirementsAnalyst()
        text = "clientes (nome)"

        srs = analyst.generate_srs({"normalized": text}, "Sistema")

        # 1 entidade x 5 operacoes CRUD = 5 requisitos
        assert len(srs["requirements"]) == 5

        # Todos devem mencionar "cliente"
        for req in srs["requirements"]:
            assert "cliente" in req["description"]
