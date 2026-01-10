"""Valida extração de entidades (petclinic) sem entidades espúrias."""

from intake.normalizer import Normalizer
from intake.req_analyst import RequirementsAnalyst


RAW_INPUT = (
    "Quero um sistema web para controle de clínica veterinária (clínica pet). "
    "Preciso cadastrar tutores (nome, cpf, telefone, email, endereço), "
    "pets (nome, espécie, raça, sexo, data de nascimento, peso, observações, tutor), "
    "veterinários (nome, CRMV, especialidade, telefone, email), "
    "atendimentos/consultas (data/hora, pet, veterinário, motivo, anotações, diagnóstico, prescrição, status), "
    "vacinas (pet, vacina, data aplicação, próxima dose, lote, observações), "
    "agendamentos (data/hora, pet, veterinário opcional, serviço, status) e "
    "pagamentos (atendimento, forma de pagamento, valor, status, data). "
    "Regras: não pode ter atendimento sem pet e sem veterinário; pet sempre pertence a um tutor; "
    "agendamento pode virar atendimento; pagamentos podem ser parciais e o atendimento só fica “concluído” quando estiver pago. "
    "Quero telas com lista, criação, edição, detalhe e exclusão para cada cadastro. "
    "Quero busca por tutor e por pet, e um dashboard inicial com atalhos: "
    "“Novo Agendamento”, “Novo Atendimento”, “Cadastrar Tutor”, “Cadastrar Pet”."
)


def test_entities_are_clean_and_expected():
    normalizer = Normalizer()
    analyst = RequirementsAnalyst()

    normalized = normalizer.normalize(RAW_INPUT)
    srs = analyst.generate_srs(normalized, project_title="Petclinic")

    entities = [req["entity"] for req in srs["data_requirements"]]

    banned_prefixes = ("quero_", "preciso_", "cadastrar_")
    assert not any(e.startswith(banned_prefixes) for e in entities)

    expected = {"tutor", "pet", "veterinario", "atendimento", "vacina", "agendamento", "pagamento"}
    assert set(entities) == expected
