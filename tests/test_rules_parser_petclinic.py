"""Testes para parsing de regras v2 - Petclinic.

Testa os padrao de regras:
- A: todo X deve ter Y -> REQUIRED_RELATION(X, Y)
- B: X pertence a Y -> OWNERSHIP_REQUIRED(X, Y)
- C: X pode virar Y -> CONVERSION(X, Y)
- D: X pode ter valor parcial -> PARTIAL_PAYMENT(X)
- E: status de X depende de pagamento -> STATUS_DEPENDS_ON_PAYMENT(X)
"""

import pytest
from intake.req_analyst import (
    extract_rules_block,
    parse_rules,
    extract_workflows_from_rules,
    parse_requirements,
    RequirementsAnalyst,
)


# Input petclinic com bloco de regras
PETCLINIC_WITH_RULES = """
tutores (nome, cpf, telefone, email);
pets (nome, especie, raca, tutor);
veterinarios (nome, crmv, especialidade);
atendimentos (data/hora, pet, veterinario, observacoes);
vacinas (nome, data, pet);
agendamentos (data/hora, pet, veterinario opcional);
pagamentos (valor, data, atendimento, forma_pagamento)

Regras:
todo pet deve ter tutor;
pet pertence a tutor;
agendamento pode virar atendimento;
pagamento pode ter valor parcial;
status do atendimento depende de pagamento
"""


class TestExtractRulesBlock:
    """Testa extracao do bloco de regras."""

    def test_extracts_entities_and_rules(self) -> None:
        """Deve separar texto de entidades e regras."""
        entities_text, rules_text = extract_rules_block(PETCLINIC_WITH_RULES)

        # Entidades devem estar antes de "Regras:"
        assert "tutores" in entities_text
        assert "pets" in entities_text
        assert "Regras:" not in entities_text

        # Regras devem estar depois de "Regras:"
        assert "todo pet deve ter tutor" in rules_text
        assert "pode virar" in rules_text

    def test_no_rules_block_returns_original(self) -> None:
        """Sem bloco de regras, retorna texto original."""
        text = "tutores (nome); pets (nome, tutor)"
        entities_text, rules_text = extract_rules_block(text)

        assert entities_text == text
        assert rules_text == ""

    def test_handles_lowercase_regras(self) -> None:
        """Deve funcionar com 'regras:' minusculo."""
        text = "pets (nome)\n\nregras:\npet pertence a tutor"
        entities_text, rules_text = extract_rules_block(text)

        assert "pets" in entities_text
        assert "pertence" in rules_text


class TestParseRulesPatterns:
    """Testa parsing dos padroes de regras."""

    def test_required_relation_todo_deve_ter(self) -> None:
        """Padrao A: 'todo X deve ter Y'."""
        rules_text = "todo pet deve ter tutor"
        rules = parse_rules(rules_text, {"pet", "tutor"})

        assert len(rules) == 1
        assert rules[0].rule_type == "required_relation"
        assert rules[0].entity_a == "pet"
        assert rules[0].entity_b == "tutor"

    def test_required_relation_toda_deve_ter(self) -> None:
        """Padrao A: 'toda X deve ter Y'."""
        rules_text = "toda venda deve ter cliente"
        rules = parse_rules(rules_text, {"venda", "cliente"})

        assert len(rules) == 1
        assert rules[0].rule_type == "required_relation"
        assert rules[0].entity_a == "venda"
        assert rules[0].entity_b == "cliente"

    def test_required_relation_cada_deve_ter(self) -> None:
        """Padrao A: 'cada X deve ter Y'."""
        rules_text = "cada pedido deve ter item"
        rules = parse_rules(rules_text, {"pedido", "item"})

        assert len(rules) == 1
        assert rules[0].rule_type == "required_relation"

    def test_ownership_required_pertence_a(self) -> None:
        """Padrao B: 'X pertence a Y'."""
        rules_text = "pet pertence a tutor"
        rules = parse_rules(rules_text, {"pet", "tutor"})

        assert len(rules) == 1
        assert rules[0].rule_type == "ownership_required"
        assert rules[0].entity_a == "pet"
        assert rules[0].entity_b == "tutor"

    def test_ownership_required_deve_pertencer(self) -> None:
        """Padrao B: 'X deve pertencer a Y'."""
        rules_text = "item deve pertencer a pedido"
        rules = parse_rules(rules_text, {"item", "pedido"})

        assert len(rules) == 1
        assert rules[0].rule_type == "ownership_required"

    def test_conversion_pode_virar(self) -> None:
        """Padrao C: 'X pode virar Y'."""
        rules_text = "agendamento pode virar atendimento"
        rules = parse_rules(rules_text, {"agendamento", "atendimento"})

        assert len(rules) == 1
        assert rules[0].rule_type == "conversion"
        assert rules[0].entity_a == "agendamento"
        assert rules[0].entity_b == "atendimento"

    def test_conversion_pode_ser_convertido(self) -> None:
        """Padrao C: 'X pode ser convertido em Y'."""
        rules_text = "orcamento pode ser convertido em venda"
        rules = parse_rules(rules_text, {"orcamento", "venda"})

        assert len(rules) == 1
        assert rules[0].rule_type == "conversion"

    def test_conversion_pode_se_tornar(self) -> None:
        """Padrao C: 'X pode se tornar Y'."""
        rules_text = "lead pode se tornar cliente"
        rules = parse_rules(rules_text, {"lead", "cliente"})

        assert len(rules) == 1
        assert rules[0].rule_type == "conversion"

    def test_partial_payment_valor_parcial(self) -> None:
        """Padrao D: 'X pode ter valor parcial'."""
        rules_text = "pagamento pode ter valor parcial"
        rules = parse_rules(rules_text, {"pagamento"})

        assert len(rules) == 1
        assert rules[0].rule_type == "partial_payment"
        assert rules[0].entity_a == "pagamento"
        assert rules[0].entity_b is None

    def test_partial_payment_aceita_pagamento_parcial(self) -> None:
        """Padrao D: 'X aceita pagamento parcial'."""
        rules_text = "fatura aceita pagamento parcial"
        rules = parse_rules(rules_text, {"fatura"})

        assert len(rules) == 1
        assert rules[0].rule_type == "partial_payment"

    def test_status_depends_on_payment(self) -> None:
        """Padrao E: 'status de X depende de pagamento'."""
        rules_text = "status de atendimento depende de pagamento"
        rules = parse_rules(rules_text, {"atendimento"})

        assert len(rules) == 1
        assert rules[0].rule_type == "status_depends_on_payment"
        assert rules[0].entity_a == "atendimento"

    def test_status_depends_on_payment_do(self) -> None:
        """Padrao E: 'status do X depende de pagamento'."""
        rules_text = "status do pedido depende de pagamento"
        rules = parse_rules(rules_text, {"pedido"})

        assert len(rules) == 1
        assert rules[0].rule_type == "status_depends_on_payment"


class TestMultipleRules:
    """Testa parsing de multiplas regras."""

    def test_parses_all_rules_from_petclinic(self) -> None:
        """Deve parsear todas as regras do petclinic."""
        _, rules_text = extract_rules_block(PETCLINIC_WITH_RULES)
        entity_names = {"pet", "tutor", "agendamento", "atendimento", "pagamento"}

        rules = parse_rules(rules_text, entity_names)

        # 5 regras no texto
        assert len(rules) >= 4

        # Verificar tipos
        rule_types = {r.rule_type for r in rules}
        assert "required_relation" in rule_types
        assert "ownership_required" in rule_types
        assert "conversion" in rule_types
        assert "partial_payment" in rule_types

    def test_deduplicates_rules(self) -> None:
        """Nao deve duplicar regras."""
        rules_text = """
        todo pet deve ter tutor;
        todo pet deve ter tutor;
        pet pertence a tutor
        """
        rules = parse_rules(rules_text, {"pet", "tutor"})

        # required_relation + ownership_required
        assert len(rules) == 2


class TestExtractWorkflows:
    """Testa extracao de workflows de regras de conversao."""

    def test_extracts_workflow_from_conversion(self) -> None:
        """Deve extrair workflow de regra de conversao."""
        rules_text = "agendamento pode virar atendimento"
        rules = parse_rules(rules_text, {"agendamento", "atendimento"})
        workflows = extract_workflows_from_rules(rules)

        assert len(workflows) == 1
        assert workflows[0].source_entity == "agendamento"
        assert workflows[0].target_entity == "atendimento"
        assert workflows[0].action == "convert"

    def test_workflow_generates_endpoint(self) -> None:
        """Workflow deve gerar endpoint correto."""
        rules_text = "orcamento pode virar venda"
        rules = parse_rules(rules_text, {"orcamento", "venda"})
        workflows = extract_workflows_from_rules(rules)

        workflow_dict = workflows[0].to_dict()
        assert workflow_dict["endpoint"] == "/api/orcamento/{id}/convert-to-venda"

    def test_no_workflow_for_non_conversion(self) -> None:
        """Nao deve criar workflow para regras que nao sao conversao."""
        rules_text = "pet pertence a tutor; pagamento pode ter valor parcial"
        rules = parse_rules(rules_text, {"pet", "tutor", "pagamento"})
        workflows = extract_workflows_from_rules(rules)

        assert len(workflows) == 0


class TestRulesInSRS:
    """Testa regras no SRS gerado."""

    def test_srs_has_business_rules(self) -> None:
        """SRS deve ter business_rules."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": PETCLINIC_WITH_RULES},
            "Petclinic com Regras"
        )

        assert "business_rules" in srs
        assert len(srs["business_rules"]) >= 4

    def test_srs_has_workflows(self) -> None:
        """SRS deve ter workflows."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": PETCLINIC_WITH_RULES},
            "Petclinic com Regras"
        )

        assert "workflows" in srs
        assert len(srs["workflows"]) >= 1

        # Verificar workflow agendamento -> atendimento
        workflow = srs["workflows"][0]
        assert workflow["source"] == "agendamento"
        assert workflow["target"] == "atendimento"

    def test_srs_has_workflow_requirement(self) -> None:
        """SRS deve ter requisito para workflow."""
        analyst = RequirementsAnalyst()
        srs = analyst.generate_srs(
            {"normalized": PETCLINIC_WITH_RULES},
            "Petclinic com Regras"
        )

        # Procurar requisito de conversao
        workflow_reqs = [
            r for r in srs["requirements"]
            if "converter" in r["description"].lower()
        ]

        assert len(workflow_reqs) >= 1
        assert "agendamento" in workflow_reqs[0]["description"]
        assert "atendimento" in workflow_reqs[0]["description"]


class TestParseRequirementsWithRules:
    """Testa parse_requirements com regras."""

    def test_returns_rules_array(self) -> None:
        """parse_requirements deve retornar rules."""
        result = parse_requirements(PETCLINIC_WITH_RULES)

        assert "rules" in result
        assert len(result["rules"]) >= 4

    def test_returns_workflows_array(self) -> None:
        """parse_requirements deve retornar workflows."""
        result = parse_requirements(PETCLINIC_WITH_RULES)

        assert "workflows" in result
        assert len(result["workflows"]) >= 1

    def test_entities_parsed_without_rules_text(self) -> None:
        """Entidades devem ser parseadas sem o texto de regras."""
        result = parse_requirements(PETCLINIC_WITH_RULES)

        entity_names = [e["name"] for e in result["entities"]]
        assert "tutor" in entity_names
        assert "pet" in entity_names

        # Texto de regras nao deve virar entidade
        assert "todo" not in entity_names
        assert "regras" not in entity_names


class TestRuleToDict:
    """Testa serializacao de regras."""

    def test_rule_to_dict_with_target(self) -> None:
        """Regra com target_entity deve ter target no dict."""
        rules_text = "pet pertence a tutor"
        rules = parse_rules(rules_text, {"pet", "tutor"})

        rule_dict = rules[0].to_dict()
        assert rule_dict["type"] == "ownership_required"
        assert rule_dict["entity"] == "pet"
        assert rule_dict["target_entity"] == "tutor"
        assert "raw_text" in rule_dict

    def test_rule_to_dict_without_target(self) -> None:
        """Regra sem target_entity nao deve ter target no dict."""
        rules_text = "pagamento pode ter valor parcial"
        rules = parse_rules(rules_text, {"pagamento"})

        rule_dict = rules[0].to_dict()
        assert rule_dict["type"] == "partial_payment"
        assert rule_dict["entity"] == "pagamento"
        assert "target_entity" not in rule_dict
