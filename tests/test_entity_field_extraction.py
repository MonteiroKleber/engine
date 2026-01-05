"""Testes de regressão para extração de entidades vs campos.

Estes testes garantem que o bug de "campos virando entidades" não volte.

Regras travadas:
1. Campos como nome/cnpj/endereco NUNCA podem virar entidade
2. Padrão "X com A,B,C" -> X é entidade, A/B/C são campos
3. Plural normalizado para singular
4. Entidades conhecidas são detectadas corretamente
"""

import pytest

from intake.req_analyst import (
    RequirementsAnalyst,
    parse_entities,
    parse_requirements,
    singularize,
    infer_field_type,
    remove_accents,
    to_snake_case,
)


class TestEntityFieldSeparation:
    """Testes para garantir separação correta entre entidades e campos."""

    @pytest.fixture
    def analyst(self):
        """Cria instância do RequirementsAnalyst."""
        return RequirementsAnalyst()

    # ========================================
    # Teste principal: "cadastro de empresas com nome, cnpj e endereço"
    # ========================================

    def test_empresas_com_nome_cnpj_endereco(self, analyst):
        """CRÍTICO: Input que causou o bug original.

        Input: "cadastro de empresas com nome, cnpj e endereço"
        Esperado:
        - 1 entidade: "empresa"
        - 3 campos: "nome", "cnpj", "endereco"
        """
        text = "Quero um sistema de cadastro de empresas com nome, cnpj e endereço"

        result = parse_requirements(text)

        # Deve ter apenas 1 entidade
        assert len(result["entities"]) == 1, f"Esperado 1 entidade, obteve {len(result['entities'])}"
        assert result["entities"][0]["name"] == "empresa"

        # Campos devem estar na entidade empresa
        fields = result["entities"][0]["fields"]

        # Deve ter 3 campos
        assert len(fields) == 3, f"Esperado 3 campos, obteve {len(fields)}: {fields}"

        # Campos esperados (normalizados)
        assert "nome" in fields
        assert "cnpj" in fields
        assert "endereco" in fields

    def test_nome_nao_vira_entidade(self, analyst):
        """Nome NUNCA pode virar entidade."""
        text = "sistema com nome"

        entities, _ = parse_entities(text)
        names = [e.name for e in entities]

        # "nome" não pode aparecer como entidade
        assert "nome" not in names, "Bug: 'nome' virou entidade!"

    def test_cnpj_nao_vira_entidade(self, analyst):
        """CNPJ NUNCA pode virar entidade."""
        text = "cadastro com cnpj"

        entities, _ = parse_entities(text)
        names = [e.name for e in entities]

        # "cnpj" não pode aparecer como entidade
        assert "cnpj" not in names, "Bug: 'cnpj' virou entidade!"

    def test_endereco_nao_vira_entidade(self, analyst):
        """Endereço NUNCA pode virar entidade."""
        text = "sistema de endereço"

        entities, _ = parse_entities(text)
        names = [e.name for e in entities]

        # "endereco" não pode aparecer como entidade
        assert "endereco" not in names, "Bug: 'endereco' virou entidade!"
        assert "endereço" not in names, "Bug: 'endereço' virou entidade!"

    # ========================================
    # Testes de padrões "X com A, B, C"
    # ========================================

    def test_padrao_cadastro_de_x_com_campos(self, analyst):
        """Padrão: cadastro de X com A, B e C."""
        text = "cadastro de produtos com nome e categoria"

        result = parse_requirements(text)

        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "produto"
        assert "nome" in result["entities"][0]["fields"]
        assert "categoria" in result["entities"][0]["fields"]

    def test_padrao_sistema_de_cadastro(self, analyst):
        """Padrão: sistema de cadastro de X com A, B."""
        text = "sistema de cadastro de clientes com nome, email e telefone"

        result = parse_requirements(text)

        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "cliente"
        assert "nome" in result["entities"][0]["fields"]
        assert "email" in result["entities"][0]["fields"]
        assert "telefone" in result["entities"][0]["fields"]

    def test_padrao_gestao_de_x(self, analyst):
        """Padrão: gestão de X com A, B."""
        text = "gestão de funcionários com nome, cpf e data"

        result = parse_requirements(text)

        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "funcionario"

    # ========================================
    # Testes de normalização de plural
    # ========================================

    def test_plural_empresas_vira_empresa(self):
        """Plural 'empresas' deve virar singular 'empresa'."""
        assert singularize("empresas") == "empresa"

    def test_plural_clientes_vira_cliente(self):
        """Plural 'clientes' deve virar singular 'cliente'."""
        assert singularize("clientes") == "cliente"

    def test_plural_usuarios_vira_usuario(self):
        """Plural 'usuarios' deve virar singular 'usuario'."""
        assert singularize("usuarios") == "usuario"

    def test_plural_pedidos_vira_pedido(self):
        """Plural 'pedidos' deve virar singular 'pedido'."""
        assert singularize("pedidos") == "pedido"

    def test_plural_tutores_vira_tutor(self):
        """Plural 'tutores' deve virar singular 'tutor'."""
        assert singularize("tutores") == "tutor"

    # ========================================
    # Testes de data_requirements gerado
    # ========================================

    def test_data_requirements_uma_entidade_com_campos(self, analyst):
        """data_requirements deve ter 1 entidade com 3 campos."""
        normalized_input = {
            "normalized": "sistema de cadastro de empresas com nome, cnpj e endereço"
        }

        srs = analyst.generate_srs(normalized_input, "Sistema Demo")

        # Deve ter 1 data_requirement
        data_reqs = srs.get("data_requirements", [])
        assert len(data_reqs) == 1, f"Esperado 1 data_requirement, obteve {len(data_reqs)}"

        # Deve ser entidade "empresa"
        entity = data_reqs[0]
        assert entity["entity"] == "empresa"

        # Deve ter 3 campos
        fields = entity["fields"]
        assert len(fields) == 3, f"Esperado 3 campos, obteve {len(fields)}"

        field_names = [f["name"] for f in fields]
        assert "nome" in field_names
        assert "cnpj" in field_names
        assert "endereco" in field_names

    def test_data_requirements_nao_gera_entidade_nome(self, analyst):
        """data_requirements NUNCA deve ter entidade chamada "nome"."""
        normalized_input = {
            "normalized": "cadastro de empresas com nome, cnpj"
        }

        srs = analyst.generate_srs(normalized_input, "Sistema")

        data_reqs = srs.get("data_requirements", [])
        entity_names = [d["entity"] for d in data_reqs]

        assert "nome" not in entity_names, "Bug: data_requirements tem entidade 'nome'!"

    def test_data_requirements_nao_gera_entidade_cnpj(self, analyst):
        """data_requirements NUNCA deve ter entidade chamada "cnpj"."""
        normalized_input = {
            "normalized": "cadastro de empresas com cnpj"
        }

        srs = analyst.generate_srs(normalized_input, "Sistema")

        data_reqs = srs.get("data_requirements", [])
        entity_names = [d["entity"] for d in data_reqs]

        assert "cnpj" not in entity_names, "Bug: data_requirements tem entidade 'cnpj'!"

    def test_data_requirements_nao_gera_entidade_endereco(self, analyst):
        """data_requirements NUNCA deve ter entidade chamada "endereco"."""
        normalized_input = {
            "normalized": "cadastro de empresas com endereco"
        }

        srs = analyst.generate_srs(normalized_input, "Sistema")

        data_reqs = srs.get("data_requirements", [])
        entity_names = [d["entity"] for d in data_reqs]

        assert "endereco" not in entity_names, "Bug: data_requirements tem entidade 'endereco'!"
        assert "endereço" not in entity_names, "Bug: data_requirements tem entidade 'endereço'!"


class TestFieldInference:
    """Testes para inferência de propriedades de campos."""

    def test_cnpj_eh_unico(self):
        """Campo CNPJ deve ser unique=True."""
        field_type, required, unique = infer_field_type("cnpj")
        assert unique is True

    def test_cpf_eh_unico(self):
        """Campo CPF deve ser unique=True."""
        field_type, required, unique = infer_field_type("cpf")
        assert unique is True

    def test_email_eh_unico(self):
        """Campo email deve ser unique=True."""
        field_type, required, unique = infer_field_type("email")
        assert unique is True

    def test_telefone_eh_opcional(self):
        """Campo telefone deve ser required=False."""
        field_type, required, unique = infer_field_type("telefone")
        assert required is False

    def test_nome_eh_obrigatorio(self):
        """Campo nome deve ser required=True."""
        field_type, required, unique = infer_field_type("nome")
        assert required is True

    def test_valor_eh_decimal(self):
        """Campo valor deve ser type=decimal."""
        field_type, required, unique = infer_field_type("valor")
        assert field_type == "decimal"


class TestNormalizeFieldName:
    """Testes para normalização de nomes de campos."""

    def test_remove_acentos(self):
        """Deve remover acentos dos nomes de campos."""
        assert remove_accents("endereço") == "endereco"
        assert remove_accents("descrição") == "descricao"
        assert remove_accents("número") == "numero"

    def test_snake_case(self):
        """Deve converter para snake_case."""
        assert to_snake_case("Data Nascimento") == "data_nascimento"
        assert to_snake_case("forma pagamento") == "forma_pagamento"
