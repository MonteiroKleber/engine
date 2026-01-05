"""Testes para geracao de 5 rotas CRUD frontend por entidade.

Verifica que o SRS v2 gera requisitos para 5 paginas:
- List (listar)
- New (cadastrar)
- Detail (visualizar)
- Edit (editar)
- Delete (excluir)

Plus Dashboard com atalhos.
"""

import pytest
from intake.req_analyst import RequirementsAnalyst, parse_requirements


# Input simples para teste
SIMPLE_INPUT = """
produtos (nome, preco, quantidade);
categorias (nome, descricao)
"""

# Input petclinic completo
PETCLINIC_INPUT = """
tutores (nome, cpf, telefone);
pets (nome, especie, tutor);
veterinarios (nome, crmv);
atendimentos (data, pet, veterinario)
"""


class TestCRUD5Requirements:
    """Testa geracao de 5 requisitos CRUD por entidade."""

    def test_generates_5_crud_per_entity(self) -> None:
        """Deve gerar 5 requisitos CRUD por entidade."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        requirements = srs["requirements"]

        # 2 entidades x 5 operacoes = 10
        assert len(requirements) == 10

    def test_crud_operations_for_entity(self) -> None:
        """Deve ter todas as 5 operacoes para cada entidade."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        requirements = srs["requirements"]

        # Filtrar requisitos para "produto"
        produto_reqs = [r for r in requirements if "produto" in r["description"]]

        assert len(produto_reqs) == 5

        # Verificar que tem todas as operacoes
        descriptions = " ".join(r["description"] for r in produto_reqs)
        assert "cadastrar" in descriptions
        assert "listar" in descriptions
        assert "visualizar" in descriptions
        assert "editar" in descriptions
        assert "excluir" in descriptions

    def test_petclinic_has_20_requirements(self) -> None:
        """Petclinic com 4 entidades deve ter 20 requisitos."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": PETCLINIC_INPUT}, "Petclinic")

        requirements = srs["requirements"]

        # 4 entidades x 5 operacoes = 20
        assert len(requirements) == 20

    def test_requirements_have_priority(self) -> None:
        """Cada requisito deve ter prioridade."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        for req in srs["requirements"]:
            assert "priority" in req
            assert req["priority"] in ["high", "medium", "low"]

    def test_cadastrar_is_high_priority(self) -> None:
        """Cadastrar deve ser high priority."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        cadastrar_reqs = [
            r for r in srs["requirements"]
            if "cadastrar" in r["description"]
        ]

        for req in cadastrar_reqs:
            assert req["priority"] == "high"

    def test_excluir_is_low_priority(self) -> None:
        """Excluir deve ser low priority."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        excluir_reqs = [
            r for r in srs["requirements"]
            if "excluir" in r["description"]
        ]

        for req in excluir_reqs:
            assert req["priority"] == "low"

    def test_requirements_have_ids(self) -> None:
        """Requisitos devem ter IDs unicos."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        ids = [r["id"] for r in srs["requirements"]]

        # Todos unicos
        assert len(ids) == len(set(ids))

        # Formato FR-XXX
        for req_id in ids:
            assert req_id.startswith("FR-")


class TestCRUD5PageMapping:
    """Testa mapeamento das 5 operacoes para paginas."""

    OPERATION_PAGE_MAP = {
        "cadastrar": "New",
        "listar": "List",
        "visualizar": "Detail",
        "editar": "Edit",
        "excluir": "Delete",
    }

    def test_each_operation_maps_to_page(self) -> None:
        """Cada operacao CRUD deve mapear para uma pagina."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        # Todas as operacoes devem estar presentes
        for operation in self.OPERATION_PAGE_MAP.keys():
            matching = [
                r for r in srs["requirements"]
                if operation in r["description"]
            ]
            assert len(matching) > 0, f"Operacao '{operation}' nao encontrada"


class TestCRUD5WithWorkflows:
    """Testa CRUD5 + workflows."""

    def test_workflow_adds_extra_requirement(self) -> None:
        """Workflow deve adicionar requisito extra."""
        input_with_workflow = """
        agendamentos (data, pet);
        atendimentos (data, pet)

        Regras:
        agendamento pode virar atendimento
        """
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": input_with_workflow}, "Sistema")

        requirements = srs["requirements"]

        # 2 entidades x 5 = 10 + 1 workflow = 11
        assert len(requirements) == 11

        # Deve ter requisito de conversao
        converter_reqs = [
            r for r in requirements
            if "converter" in r["description"].lower()
        ]
        assert len(converter_reqs) == 1
        assert "agendamento" in converter_reqs[0]["description"]
        assert "atendimento" in converter_reqs[0]["description"]


class TestDataRequirementsStructure:
    """Testa estrutura de data_requirements."""

    def test_each_entity_in_data_requirements(self) -> None:
        """Cada entidade deve estar em data_requirements."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        entities_in_dr = [dr["entity"] for dr in srs["data_requirements"]]

        assert "produto" in entities_in_dr
        assert "categoria" in entities_in_dr

    def test_fields_preserved_in_data_requirements(self) -> None:
        """Campos devem ser preservados em data_requirements."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        produto_dr = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "produto"
        )

        field_names = [f["name"] for f in produto_dr["fields"]]

        assert "nome" in field_names
        assert "preco" in field_names
        assert "quantidade" in field_names

    def test_fields_have_types(self) -> None:
        """Campos devem ter tipos inferidos."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        produto_dr = next(
            dr for dr in srs["data_requirements"]
            if dr["entity"] == "produto"
        )

        for field in produto_dr["fields"]:
            assert "type" in field
            assert field["type"] in ["string", "integer", "decimal", "date", "time", "boolean", "uuid"]


class TestSRSMetadata:
    """Testa metadata do SRS v2."""

    def test_generation_mode_is_v2(self) -> None:
        """generation_mode deve ser MINIGRAMMAR_V2."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        assert srs["metadata"]["generation_mode"] == "MINIGRAMMAR_V2"

    def test_has_created_at(self) -> None:
        """Deve ter created_at."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        assert "created_at" in srs["metadata"]

    def test_has_language(self) -> None:
        """Deve ter language."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs({"normalized": SIMPLE_INPUT}, "Sistema")

        assert "language" in srs["metadata"]
        assert srs["metadata"]["language"] == "pt-BR"


class TestParseRequirementsOutput:
    """Testa saida de parse_requirements."""

    def test_returns_entities_with_fields(self) -> None:
        """parse_requirements deve retornar entidades com campos."""
        result = parse_requirements(SIMPLE_INPUT)

        assert "entities" in result
        assert len(result["entities"]) == 2

        produto = next(e for e in result["entities"] if e["name"] == "produto")
        assert "nome" in produto["fields"]
        assert "preco" in produto["fields"]

    def test_returns_relations(self) -> None:
        """parse_requirements deve retornar relacoes."""
        result = parse_requirements(PETCLINIC_INPUT)

        assert "relations" in result
        assert len(result["relations"]) > 0

    def test_returns_rules_and_workflows(self) -> None:
        """parse_requirements deve retornar rules e workflows."""
        result = parse_requirements(SIMPLE_INPUT)

        assert "rules" in result
        assert "workflows" in result
        # Sem bloco de regras, devem ser vazios
        assert len(result["rules"]) == 0
        assert len(result["workflows"]) == 0
