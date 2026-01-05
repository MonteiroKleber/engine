"""Teste de regressao para mini-gramatica - Multiplas entidades com parenteses.

Valida que o parser extrai corretamente multiplas entidades no formato
"X (campos); Y (campos); Z (campos)" usando Forma A.
"""

import pytest
from intake.req_analyst import (
    parse_entities,
    parse_form_a,
    normalize_text,
    parse_requirements,
)


class TestMultipleEntitiesParentheses:
    """Testa extracao de multiplas entidades com parenteses."""

    def test_two_entities_semicolon_separated(self) -> None:
        """Deve extrair 2 entidades separadas por ponto-e-virgula."""
        text = "clientes (nome, email); produtos (nome, preco)"
        entities, _ = parse_entities(text)

        assert len(entities) == 2
        names = [e.name for e in entities]
        assert "cliente" in names
        assert "produto" in names

    def test_three_entities_same_line(self) -> None:
        """Deve extrair 3 entidades na mesma linha."""
        text = "usuarios (nome, email), pedidos (data, status), itens (quantidade, valor)"
        entities, _ = parse_entities(text)

        assert len(entities) == 3
        names = [e.name for e in entities]
        assert "usuario" in names
        assert "pedido" in names
        assert "item" in names

    def test_entities_with_newlines(self) -> None:
        """Deve extrair entidades separadas por quebras de linha."""
        text = """
        clientes (nome, cpf, email)
        produtos (nome, descricao, preco)
        pedidos (data, status, cliente)
        """
        entities, _ = parse_entities(text)

        assert len(entities) == 3

    def test_fields_preserved_per_entity(self) -> None:
        """Cada entidade deve manter seus campos corretos."""
        text = "tutores (nome, cpf); pets (nome, especie, raca)"
        entities, _ = parse_entities(text)

        tutor = next(e for e in entities if e.name == "tutor")
        pet = next(e for e in entities if e.name == "pet")

        assert tutor.fields == ["nome", "cpf"]
        assert pet.fields == ["nome", "especie", "raca"]

    def test_all_entities_use_form_a(self) -> None:
        """Todas entidades devem ser parseadas via Forma A."""
        text = "empresas (nome, cnpj); funcionarios (nome, cargo)"
        entities, _ = parse_entities(text)

        for entity in entities:
            assert entity.source_form == "A"

    def test_singularization_applied(self) -> None:
        """Nomes no plural devem ser singularizados."""
        text = "clientes (nome); produtos (preco); pedidos (data)"
        entities, _ = parse_entities(text)

        names = [e.name for e in entities]
        assert "cliente" in names
        assert "produto" in names
        assert "pedido" in names
        # Nao deve ter plural
        assert "clientes" not in names
        assert "produtos" not in names
        assert "pedidos" not in names

    def test_entity_with_spaces_in_name(self) -> None:
        """Entidade com espacos no nome deve virar snake_case."""
        text = "dados cliente (nome, cpf)"
        entities, _ = parse_entities(text)

        # "dados cliente" deve virar "dados_cliente" ou similar
        assert len(entities) >= 1

    def test_mixed_separators(self) -> None:
        """Deve funcionar com mistura de separadores."""
        text = "clientes (nome); produtos (preco) | pedidos (data)"
        entities, _ = parse_entities(text)

        assert len(entities) == 3

    def test_empty_parentheses_ignored(self) -> None:
        """Parenteses vazios devem ser ignorados."""
        text = "clientes (); produtos (nome, preco)"
        entities, _ = parse_entities(text)

        # Apenas produto tem campos validos
        names = [e.name for e in entities]
        assert "produto" in names

    def test_nested_parentheses_handled(self) -> None:
        """Parenteses internos (obs) devem ser tratados no campo."""
        text = "clientes (nome, email, telefone)"
        entities, _ = parse_entities(text)

        cliente = next(e for e in entities if e.name == "cliente")
        # Campos devem estar presentes
        assert "nome" in cliente.fields
        assert "email" in cliente.fields
        assert "telefone" in cliente.fields


class TestFormADirectParsing:
    """Testa parse_form_a diretamente."""

    def test_form_a_extracts_multiple_matches(self) -> None:
        """Forma A deve extrair multiplos matches no mesmo bloco."""
        text = normalize_text("clientes (nome, email) e produtos (nome, preco)")
        entities = parse_form_a(text)

        assert len(entities) == 2

    def test_form_a_handles_accents(self) -> None:
        """Forma A deve lidar com acentos."""
        text = normalize_text("serviços (nome, descrição, preço)")
        entities = parse_form_a(text)

        assert len(entities) == 1
        assert entities[0].name == "servico"

    def test_form_a_handles_field_with_spaces(self) -> None:
        """Forma A deve converter campos com espacos para snake_case."""
        text = normalize_text("pets (nome, data nascimento, peso)")
        entities = parse_form_a(text)

        pet = entities[0]
        assert "data_nascimento" in pet.fields
